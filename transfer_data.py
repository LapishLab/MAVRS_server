#!/usr/bin/env python3
from subprocess import run, Popen, PIPE, STDOUT
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
import logging
from threading import Event, Lock, Thread
from load_settings import load_settings, load_pi_addresses, Settings, other_folders_save_root
from path_config import PI_SETTINGS_FILE
from locations import Location, rsync_command
from transfer_cleanup import cleanup_pi
from console_logging import configure_logging

logger = logging.getLogger(__name__)
PROGRESS_INTERVAL_SECONDS = 30


def _format_bytes(size: int) -> str:
	amount = float(size)
	for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
		if amount < 1024 or unit == "TiB":
			return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
		amount /= 1024
	raise AssertionError("unreachable")

def main(settings: Settings | None = None) -> bool:
	settings = settings or load_settings()
	folders_ok = True
	if settings.other_folders:
		folders_ok = get_remote_folders(settings)
	pis_ok = transfer_pis(settings)
	return folders_ok and pis_ok
	
def copy_to_pi_home(pis: list[Location] | None = None) -> list[tuple[Location, str | None]]:
	logger.info("Copying settings to the Pi")

	pi_names = load_pi_addresses() if pis is None else pis
	local_settings_path = Location(PI_SETTINGS_FILE)
	remote_home = "~"
	results: list[tuple[Location, str | None]] = []

	for fullname in pi_names:
		remote_target = fullname.with_path(f"{remote_home}/")
		cmd = rsync_command(
			local_settings_path, remote_target,
			source_is_file=True,
		)
		try:
			result = run(cmd, capture_output=True, text=True)
			error = None if result.returncode == 0 else (result.stderr or "").strip() or f"rsync exited with code {result.returncode}"
		except OSError as exc:
			error = str(exc)
		results.append((fullname, error))
		if error is None:
			logger.info("Successfully copied settings to %s", fullname.ssh_host)
		else:
			logger.warning("Failed to copy settings to %s: %s", fullname.ssh_host, error)
	return results

def stream_rsync(cmd: list[str], label: str) -> tuple[bool, str]:
	proc = Popen(cmd, stdout=PIPE, stderr=STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
	assert proc.stdout is not None
	recent = deque(maxlen=20)
	files_completed = 0
	bytes_transferred = 0
	progress_lock = Lock()
	stop_reporting = Event()

	def report_progress() -> None:
		while not stop_reporting.wait(PROGRESS_INTERVAL_SECONDS):
			with progress_lock:
				files, size = files_completed, bytes_transferred
			logger.info("[%s] Transferring: %s files completed, %s transferred", label, files, _format_bytes(size))

	reporter = Thread(target=report_progress, daemon=True)
	reporter.start()
	try:
		for raw_line in proc.stdout:
			line = raw_line.strip()
			if not line:
				continue
			item, separator, size = line.rpartition(" ")
			if separator and len(item) == 11 and item[1] in "fdLDS" and size.isdecimal():
				# The %b record arrives when a file finishes; directories are not counted.
				if item.startswith((">f", "<f")):
					with progress_lock:
						files_completed += 1
						bytes_transferred += int(size)
			else:
				recent.append(line)
				logger.warning("[%s] %s", label, line)
	finally:
		stop_reporting.set()
		reporter.join()
		proc.stdout.close()

	returncode = proc.wait()
	output = "\n".join(recent)
	if returncode == 0:
		logger.info("[%s] Transfer complete: %s files, %s transferred", label, files_completed, _format_bytes(bytes_transferred))
		return True, output
	return False, output or f"rsync exited with code {returncode}"

def transfer_pi(fullname: Location, server_path: Location) -> tuple[str, str | None, bool, str]:
	pi, port = fullname.ssh_host, str(fullname.port) if fullname.port is not None else None
	cmd = rsync_command(
		fullname, server_path,
		update=True, exclude=".*", summarize_files=True,
	)
	try:
		success, output = stream_rsync(cmd, str(fullname))
		return pi, port, success, output
	except OSError as exc:
		return pi, port, False, str(exc)


def transfer_pis(settings: Settings) -> bool:
	logger.info("Copying data from Pi")

	pi_names = load_pi_addresses()
	server_path = settings.local_data_path

	if not pi_names:
		logger.info("No Pis configured for transfer")
		return True
	with ThreadPoolExecutor(max_workers=len(pi_names)) as executor:
		futures = {executor.submit(transfer_pi, name, server_path): name for name in pi_names}
		results = {futures[future]: future.result() for future in as_completed(futures)}

	failed_transfers = []
	for fullname in pi_names:
		pi, port, success, output = results[fullname]
		if not success:
			logger.warning("Rsync failed for %s: %s", fullname, output)
			failed_transfers.append(str(fullname))
			continue
		try:
			deleted, total = cleanup_pi(pi, port, server_path.local_path)
			logger.info("%s: transferred successfully; deleted %s of %s visible source files", fullname, deleted, total)
		except Exception as exc:
			logger.warning("Cleanup failed for %s: %s. Data remains on this Pi where cleanup did not complete.", fullname, exc)
			failed_transfers.append(str(fullname))
	if not failed_transfers:
		logger.info("All Pi transfers and cleanup completed")
		return True
	else:
		logger.warning("Transfer or cleanup failed for Pis: %s. Check these Pis before manually deleting data", ", ".join(failed_transfers))
		return False

def get_remote_folders(settings: Settings) -> bool:
	local_data = settings.local_data_path
	folders = other_folders_save_root(settings)
	all_succeeded = True
	for label, remote_path in folders.items():
		if remote_path == local_data: #Skip transfer if already saved in local path
			continue
		logger.info("Getting %s folder", label)
		cmd = rsync_command(remote_path, local_data, update=True, summarize_files=True)
		try:
			success, output = stream_rsync(cmd, label)
		except OSError as exc:
			success, output = False, str(exc)
		if not success:
			logger.warning('Failed to copy %s data from %s\n%s', label, remote_path, output)
			all_succeeded = False
	return all_succeeded

if __name__ == "__main__":
	configure_logging()
	raise SystemExit(0 if main() else 1)
