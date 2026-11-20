#!/usr/bin/env python3
import logging
from os.path import expanduser
from subprocess import run

from load_settings import load_pi_connections, load_settings, Settings
import transfer_data
from pi_sysemd import stop_process
from video_repair import repair_directory
from console_logging import configure_logging

logger = logging.getLogger(__name__)

def main() -> bool:
	stop_pis()
	settings = load_settings()
	transfers_ok = transfer_data.main(settings)
	try:
		failed_repairs = repair_directory(settings.local_data_path.local_path)
		repair_ok = failed_repairs == 0
	except Exception as exc:
		logger.warning("Video repair failed: %s", exc)
		repair_ok = False
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

def stop_pis() -> None:
	logger.info("Stopping Pi recordings")
	logger.info("Loading Pi connections")
	pis = load_pi_connections()
	stop_process(pis)

if __name__ == "__main__":
	configure_logging()
	raise SystemExit(0 if main() else 1)
