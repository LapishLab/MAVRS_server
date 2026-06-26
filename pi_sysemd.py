from typing import Optional, List
import logging
from load_settings import load_pi_connections
from fabric import Connection
from fabric_tools import run_on_connections
from status_checker import get_pi_statuses, PiStatus
from config import ENV, UNIT, PYTHON_PATH, SCRIPT_PATH

logger = logging.getLogger(__name__)

def stop_process(c: List[Connection]):
	print("Sending stop command to Pis")
	run_on_connections(c, f"{ENV} systemctl --user stop {UNIT}.service", warn=True)
	print("Double Checking that Pis have stopped")

def start_process(c: List[Connection], session: str):
	print("checking if pis are active")

	for name, status in get_pi_statuses(c).items():
		if status==PiStatus.UNREACHABLE:
			logger.warning(f"Aborting: {name} is unreachable")
			return
		if status==PiStatus.RUNNING:
			logger.warning(f"Aborting: {UNIT} is already running on {name}.")
			return
	pi_cmd = f'{PYTHON_PATH} -u {SCRIPT_PATH} --session {session}'
	sysemd_cmd = f'{ENV} systemctl --user reset-failed; systemd-run --user --unit={UNIT} {pi_cmd}'
	run_on_connections(c, sysemd_cmd, warn=True)
		
	statuses = get_pi_statuses(c)
	if all(PiStatus.RUNNING == v for v in statuses.values()):
		print(f"Started {UNIT} on all Pis")
	else:
		for name, status in statuses.values():
			if status==PiStatus.UNREACHABLE:
				logger.warning(f"{name} is now unreachable")
			elif status == PiStatus.REACHABLE:
				logger.warning(f"{name} did not sucessfully start {UNIT}")

def stream_logs(c: Optional[List[Connection]] = None):
	"""Stream journal logs for `UNIT` from each host.

	This spawns a thread per host and prints each log line prefixed with the host.
	Interrupt with Ctrl-C to stop streaming.
	"""
	if c is None:
		from load_settings import load_pi_connections
		c = load_pi_connections()
	run_on_connections(c, f"{ENV} journalctl --user -u {UNIT}.service -f --no-pager", warn=True)

if __name__ == "__main__":
	stream_logs()
