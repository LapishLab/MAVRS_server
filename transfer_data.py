#!/usr/bin/env python3
from subprocess import run, Popen, PIPE, STDOUT
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
import logging
from os.path import expanduser
from threading import Event, Lock, Thread
from typing import Callable
from load_settings import load_settings, load_pi_addresses, Settings, other_folders_save_root
from path_config import PI_SETTINGS_FILE
from locations import Location, rsync_command
from transfer_cleanup import cleanup_pi
from console_logging import configure_logging
from video_repair import repair_directory

logger = logging.getLogger(__name__)
PROGRESS_INTERVAL_SECONDS = 10


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
	transfers_ok = folders_ok and pis_ok
	repair_ok = True
	if settings.repair_videos_on_transfer:
		try:
			failed_repairs = repair_directory(settings.local_data_path.local_path)
			repair_ok = failed_repairs == 0
		except Exception as exc:
			logger.warning("Video repair failed: %s", exc)
			repair_ok = False
	else:
		logger.debug("Video repair skipped (repair_videos_on_transfer is false)")
	scripts_ok = run_post_session_scripts(settings)
	return transfers_ok and repair_ok and scripts_ok


def run_post_session_scripts(settings: Settings) -> bool:
	"""Run labeled commands in order, inheriting this terminal's output streams."""
	all_succeeded = True
	data_directory = str(settings.local_data_path.local_path)
	for label, command in settings.post_session_scripts.items():
		arguments = [expanduser(part.replace("{local_data_directory}", data_directory)) for part in command]
		logger.info("Running post-session script: %s", label)
		try:
			result = run(arguments, check=False)
		except OSError as exc:
			logger.warning("Could not run post-session script %s: %s", label, exc)
			all_succeeded = False
			continue
		if result.returncode != 0:
			logger.warning("Post-session script %s exited with status %s", label, result.returncode)
			all_succeeded = False
	return all_succeeded
	
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

def stream_rsync(
	cmd: list[str], label: str,
	on_file_completed: Callable[[], None] | None = None,
	on_warning: Callable[[str, str], None] | None = None,
) -> tuple[bool, str]:
	proc = Popen(cmd, stdout=PIPE, stderr=STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
	assert proc.stdout is not None
	recent: deque[str] = deque(maxlen=20)
	files_completed = 0
	bytes_transferred = 0
	progress_lock = Lock()
	stop_reporting = Event()

	def report_progress() -> None:
		while not stop_reporting.wait(PROGRESS_INTERVAL_SECONDS):
			with progress_lock:
				files, size = files_completed, bytes_transferred
			logger.info("[%s] Transferring: %s files completed, %s transferred", label, files, _format_bytes(size))

	reporter = Thread(target=report_progress, daemon=True) if on_file_completed is None else None
	if reporter is not None:
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
					if on_file_completed is not None:
						on_file_completed()
					else:
						with progress_lock:
							files_completed += 1
							bytes_transferred += int(size)
			else:
				recent.append(line)
				if on_warning is None:
					logger.warning("[%s] %s", label, line)
				else:
					on_warning(label, line)
	finally:
		if reporter is not None:
			stop_reporting.set()
			reporter.join()
		proc.stdout.close()

	returncode = proc.wait()
	output = "\n".join(recent)
	if returncode == 0:
		if on_file_completed is None:
			logger.info("[%s] Transfer complete: %s files, %s transferred", label, files_completed, _format_bytes(bytes_transferred))
		return True, output
	return False, output or f"rsync exited with code {returncode}"

def _pi_transfer_command(fullname: Location, server_path: Location) -> list[str]:
	return rsync_command(
		fullname, server_path,
		update=True, exclude=".*", summarize_files=True,
	)


def count_pi_files(fullname: Location, server_path: Location) -> int | None:
	cmd = _pi_transfer_command(fullname, server_path)
	cmd.insert(-2, "--dry-run")
	count = 0

	def count_file() -> None:
		nonlocal count
		count += 1

	try:
		success, output = stream_rsync(cmd, str(fullname), on_file_completed=count_file)
	except OSError as exc:
		success, output = False, str(exc)
	if not success:
		logger.warning("Could not count files for %s: %s", fullname, output)
		return None
	return count


def transfer_pi(
	fullname: Location, server_path: Location,
	on_file_completed: Callable[[], None] | None = None,
	on_warning: Callable[[str, str], None] | None = None,
) -> tuple[str, str | None, bool, str]:
	pi, port = fullname.ssh_host, str(fullname.port) if fullname.port is not None else None
	cmd = _pi_transfer_command(fullname, server_path)
	try:
		success, output = stream_rsync(cmd, str(fullname), on_file_completed=on_file_completed, on_warning=on_warning)
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
	logger.info("Counting files to transfer from Pis")
	with ThreadPoolExecutor(max_workers=len(pi_names)) as executor:
		counts = list(executor.map(lambda name: count_pi_files(name, server_path), pi_names))
	valid_counts = [count for count in counts if count is not None]
	total_files = sum(valid_counts) if len(valid_counts) == len(counts) else None
	files_completed = 0
	progress_lock = Lock()
	stop_reporting = Event()
	warnings: list[tuple[str, str]] = []
	last_progress: int | None = None

	def record_completed_file() -> None:
		nonlocal files_completed
		with progress_lock:
			files_completed += 1

	def record_warning(label: str, line: str) -> None:
		with progress_lock:
			warnings.append((label, line))

	def show_progress(count: int) -> None:
		nonlocal last_progress
		progress = count if total_files is None else (min(100, count * 100 // total_files) if total_files else 100)
		if progress == last_progress:
			return
		prefix = "Pi Transfer progress: " if last_progress is None else " -> "
		unit = (" file" if progress == 1 else " files") if total_files is None else "%"
		print(f"{prefix}{progress}{unit}", end="", flush=True)
		last_progress = progress

	def report_progress() -> None:
		while not stop_reporting.wait(PROGRESS_INTERVAL_SECONDS):
			with progress_lock:
				count = files_completed
			show_progress(count)

	show_progress(0)
	reporter = Thread(target=report_progress, daemon=True)
	reporter.start()
	try:
		with ThreadPoolExecutor(max_workers=len(pi_names)) as executor:
			futures = {executor.submit(transfer_pi, name, server_path, record_completed_file, record_warning): name for name in pi_names}
			results = {futures[future]: future.result() for future in as_completed(futures)}
	finally:
		stop_reporting.set()
		reporter.join()
		show_progress(files_completed)
		print(flush=True)
	for label, line in warnings:
		logger.warning("[%s] %s", label, line)

	failed_transfers = []
	for fullname in pi_names:
		pi, port, success, output = results[fullname]
		if not success:
			logger.warning("Rsync failed for %s: %s", fullname, output)
			failed_transfers.append(str(fullname))
			continue
		try:
			cleanup_pi(pi, port, server_path.local_path)
		except Exception as exc:
			logger.warning("Cleanup failed for %s: %s. Data remains on this Pi where cleanup did not complete.", fullname, exc)
			failed_transfers.append(str(fullname))
	if not failed_transfers:
		if total_files is None:
			logger.info("All data successfully transferred from Pis (%s files; total unavailable)", files_completed)
		else:
			logger.info("All data successfully transferred from Pis (%s/%s total files)", files_completed, total_files)
		logger.debug("All Pi files deleted successfully")
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
