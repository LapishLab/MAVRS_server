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
from rsync_paths import rsync_command
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
	local_settings_path = f"{PI_SETTINGS_FOLDER}/"
	remote_home = "/home/pi"

	for fullname in pi_names:
		if ":" in fullname:
			pi, port = fullname.split(":")
		else:
			pi = fullname
			port = "22"

		remote_target = f"{pi}:{remote_home}/"
		cmd = rsync_command(
			local_settings_path, remote_target,
			ssh_port=port,
		)
		result = run(cmd, capture_output=True, text=True)
		if result.returncode == 0:
			print(f"Successfully copied settings to {pi}")
		else:
			logger.warning(f"Failed to copy settings to {pi}: {result.stderr}")

def transfer_pi(fullname: str, server_path: str) -> tuple[str, str, bool, str]:
	pi, _, port = fullname.partition(":")
	port = port or "22"
	cmd = rsync_command(
		f"{pi}:/home/pi/MAVRS_pi/data/", server_path,
		update=True, exclude=".*", ssh_port=port,
	)
	try:
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
						print(f"[{fullname}] {line}", flush=True)
		pending += decoder.decode(b"", final=True)
		if pending.strip():
			recent.append(pending)
			with progress_lock:
				print(f"[{fullname}] {pending}", flush=True)
		return pi, port, proc.wait() == 0, "\n".join(recent)
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
			failed_transfers.append(fullname)
			continue
		try:
			deleted, total = cleanup_pi(pi, port, server_path)
			print(f"{fullname}: transferred successfully; deleted {deleted} of {total} visible source files")
		except Exception as exc:
			logger.warning("Cleanup failed for %s: %s. Data remains on this Pi where cleanup did not complete.", fullname, exc)
			failed_transfers.append(fullname)
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
		result = run(cmd, capture_output=True,text=True)
		if not result.returncode == 0:
			logger.warning(f'Failed to copy {label} data from {remote_path} \n{result.stderr}')

if __name__ == "__main__":
	main()
