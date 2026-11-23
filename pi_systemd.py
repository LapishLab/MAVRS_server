from typing import Optional, List
import logging
from load_settings import load_pi_connections
from fabric import Connection
from fabric_tools import run_on_connections
from status_checker import get_pi_statuses, PiStatus
from pi_command_config import ENV, UNIT, PYTHON_PATH, SCRIPT_PATH
from console_logging import configure_logging

logger = logging.getLogger(__name__)

def stop_process(c: List[Connection]):
	logger.info("Stopping Pi recordings")
	results = run_on_connections(c, f"{ENV} systemctl --user stop {UNIT}.service", warn=True, hide=True)
	for connection, result in zip(c, results):
		if isinstance(result, Exception):
			logger.warning("Could not stop %s on %s: %s", UNIT, connection.host, result)
			continue
		if result.exited == 0:
			continue
		error = (result.stderr or result.stdout or "").strip()
		if error == f"Failed to stop {UNIT}.service: Unit {UNIT}.service not loaded.":
			continue
		logger.warning("Could not stop %s on %s: %s", UNIT, connection.host, error or f"exit status {result.exited}")

def start_process(c: List[Connection], session: str):
	logger.info("Checking if Pis are active")

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
		logger.info("Launched %s on all Pis; check recorder status for readiness", UNIT)
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
	configure_logging()
	stream_logs()
