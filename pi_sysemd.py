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

	for name, health in get_pi_statuses(c).items():
		if health.status in (PiStatus.UNREACHABLE, PiStatus.UNKNOWN):
			logger.warning(f"Aborting: cannot verify recorder state on {name} ({health.summary})")
			return
		if health.status in (PiStatus.RUNNING, PiStatus.STARTING, PiStatus.PARTIAL_FAILURE):
			logger.warning(f"Aborting: {UNIT} is already active on {name} ({health.summary}).")
			return
	pi_cmd = f'{PYTHON_PATH} -u {SCRIPT_PATH} --session {session}'
	sysemd_cmd = f'{ENV} systemctl --user reset-failed; systemd-run --user --setenv=PYTHONUNBUFFERED=1 --unit={UNIT} {pi_cmd}'
	run_on_connections(c, sysemd_cmd, warn=True)
		
	statuses = get_pi_statuses(c)
	if all(v.status in (PiStatus.RUNNING, PiStatus.STARTING) for v in statuses.values()):
		print(f"Launched {UNIT} on all Pis; check recorder status for readiness")
	else:
		for name, health in statuses.items():
			if health.status==PiStatus.UNREACHABLE:
				logger.warning(f"{name} is now unreachable")
			elif health.status not in (PiStatus.RUNNING, PiStatus.STARTING):
				logger.warning(f"{name} recorder status: {health.summary}")

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
