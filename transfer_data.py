#!/usr/bin/env python3
from subprocess import run, Popen, PIPE, STDOUT
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from threading import Lock
import codecs
import os
import logging
from load_settings import load_settings, load_pi_addresses, Settings, other_folders_save_root
from path_config import PI_SETTINGS_FOLDER
from rsync_paths import Location, rsync_command
from transfer_cleanup import cleanup_pi

logger = logging.getLogger(__name__)
progress_lock = Lock()

def main() -> None:
	settings = load_settings()
	if settings.other_folders:
		get_remote_folders(settings)
	transfer_pis(settings)
	
def copy_to_pi_home() -> None:
	print("Copying settings to the Pi")

	pi_names = load_pi_addresses()
	local_settings_path = Location(PI_SETTINGS_FOLDER)
	remote_home = "~"

	for fullname in pi_names:
		remote_target = fullname.with_path(f"{remote_home}/")
		cmd = rsync_command(
			local_settings_path, remote_target,
		)
		result = run(cmd, capture_output=True, text=True)
		if result.returncode == 0:
			print(f"Successfully copied settings to {fullname.ssh_host}")
		else:
			logger.warning(f"Failed to copy settings to {fullname.ssh_host}: {result.stderr}")

def stream_rsync(cmd: list[str], label: str) -> tuple[bool, str]:
	proc = Popen(cmd, stdout=PIPE, stderr=STDOUT)
	assert proc.stdout is not None
	decoder = codecs.getincrementaldecoder("utf-8")("replace")
	pending = ""
	recent = deque(maxlen=20)
	while chunk := os.read(proc.stdout.fileno(), 4096):
		pending += decoder.decode(chunk)
		parts = pending.replace("\r", "\n").split("\n")
		pending = parts.pop()
		for line in parts:
			if line.strip():
				recent.append(line)
				with progress_lock:
					print(f"[{label}] {line}", flush=True)
	pending += decoder.decode(b"", final=True)
	if pending.strip():
		recent.append(pending)
		with progress_lock:
			print(f"[{label}] {pending}", flush=True)
	return proc.wait() == 0, "\n".join(recent)

def transfer_pi(fullname: Location, server_path: Location) -> tuple[str, str | None, bool, str]:
	pi, port = fullname.ssh_host, str(fullname.port) if fullname.port is not None else None
	cmd = rsync_command(
		fullname, server_path,
		update=True, exclude=".*",
	)
	try:
		success, output = stream_rsync(cmd, str(fullname))
		return pi, port, success, output
	except OSError as exc:
		return pi, port, False, str(exc)


def transfer_pis(settings: Settings) -> None:
	print("Copying data from Pi")

	pi_names = load_pi_addresses()
	server_path = settings.local_data_path

	if not pi_names:
		print("No Pis configured for transfer")
		return
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
			print(f"{fullname}: transferred successfully; deleted {deleted} of {total} visible source files")
		except Exception as exc:
			logger.warning("Cleanup failed for %s: %s. Data remains on this Pi where cleanup did not complete.", fullname, exc)
			failed_transfers.append(str(fullname))
	if not failed_transfers:
		print(
			f"\n-----------------------"
			f"\nAll Pi transfers and cleanup completed"
			f'\n------------------------'
			)
	else:
		print(
			f"\n----WARNING!!----"
			f"\nTransfer or cleanup failed for the following Pis"
			f'\n{failed_transfers}'
			f'\nCheck these Pis before manually deleting data'
			f'\n------------------------'
			)

def get_remote_folders(settings: Settings) -> None:
	local_data = settings.local_data_path
	folders = other_folders_save_root(settings)
	for label, remote_path in folders.items():
		if remote_path == local_data: #Skip transfer if already saved in local path
			continue
		print(f"Getting {label} folder")
		cmd = rsync_command(remote_path, local_data, update=True)
		try:
			success, output = stream_rsync(cmd, label)
		except OSError as exc:
			success, output = False, str(exc)
		if not success:
			logger.warning('Failed to copy %s data from %s\n%s', label, remote_path, output)

if __name__ == "__main__":
	main()
