from subprocess import run
import logging
from datetime import datetime
from load_settings import load_pi_connections, load_settings, load_experiment_names, Settings, other_folders_save_root
from pathlib import Path
from tempfile import TemporaryDirectory
from pi_utilities import set_time_on_pis, report_disk_space
from re import search, sub
from pi_systemd import start_process
from fabric_tools import run_on_connections
from typing import Optional, List
from fabric import Connection
from locations import Location, rsync_command
from console_logging import configure_logging

logger = logging.getLogger(__name__)

def main() -> None:
	pis = load_pi_connections()
	settings = load_settings()
	session = get_session_name(settings)
	if not initialize(pis, settings, session):
		return
	input("Hit enter when ready to start Pi recording")
	
	logger.info("Starting Pi recordings: %s", session)
	if settings.other_folders:
		pi_session =  f"{session}/pi-data_{session}"
	else:
		pi_session = session # If no other computers or folders, just save pi data in the root of the session
	start_process(pis, pi_session)

def initialize(pis: List[Connection], settings: Settings, session: str) -> bool:
	set_time_on_pis(pis)
	report_disk_space(pis)
	if not create_other_folders(session, settings):
		return False
	return True

def create_other_folders(session: str, settings: Settings) -> bool:
	folders = other_folders_save_root(settings)
	for label, dest in folders.items():
		logger.info("Creating %s folder", label)
		folder_name = f"{session}/{label}_{session}"
		with TemporaryDirectory(prefix="mavrs_") as temp:
			(Path(temp) / session / f"{label}_{session}").mkdir(parents=True)
			cmd = rsync_command(Location(temp), dest)
			try:
				run(cmd, check=True)
			except Exception:
				ans = input(f'Failed to create {label} folder at {dest} \n'
					  'Continue anyway? (y/N): ')
				if ans.lower() not in ("y", "yes"):
					return False
		logger.info("Created: %s/%s", dest, folder_name)
	return True
	
def get_session_name(settings: Settings) -> str:
	while True:
		suggested = settings.suggested_name_format
		now = datetime.now()
		suggested = suggested.replace("%date%", now.strftime("%Y-%m-%d"))
		suggested = suggested.replace("%time%", now.strftime("%H-%M-%S"))
		
		if "%experiment%" in suggested:
			exp = choose_experiment_from_file()
			suggested = suggested.replace("%experiment%", exp)
		
		input_pattern=r"%input.*?%"
		while (match := search(input_pattern, suggested)) is not None:
			sub_match = search(r"{.*?}", match.group())
			if sub_match:
				label = sub_match.group()[1:-1]
			else:
				label = ""
			val = input(f"Enter {label}: ")
			suggested = sub(input_pattern, val, suggested, count=1)

		print(f"Suggested session name: {suggested}")
		response = input('If the above name is correct, hit enter. If incorrect, type "n" to restart selection: ')
		if not response == "n":
			return suggested

def choose_experiment_from_file() -> str:
	lines = load_experiment_names()

	while True:
		print("Select an experiment name:")
		for index, line in enumerate(lines, start=1):
			print(f"{index}. {line.strip()}")
		choice = input("\nEnter number or hit enter to choose #1: ") or "1"

		if choice.isdigit():
			choice = int(choice)
			if 1 <= choice <= len(lines):
				return lines[choice - 1].strip()
			else:
				logger.warning("Invalid input. Enter a number within the valid range.")
		else:
			logger.warning("Invalid input. Please enter a number.")

if __name__ == "__main__":
	configure_logging()
	main()
