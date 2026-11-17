import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional
from subprocess import run, CompletedProcess

from load_settings import load_pi_connections, other_folders_save_root
from config import ENV, UNIT, PYTHON_PATH, STATUS_SCRIPT_PATH
from fabric_tools import run_on_connections
from fabric import Connection
from locations import rsync_command
from locations import Location

class PiStatus(Enum):
	UNREACHABLE = "unreachable"
	STOPPED = "stopped"
	RUNNING = "recording"
	STARTING = "starting"
	PARTIAL_FAILURE = "partial failure"
	FAILED = "failed"
	UNKNOWN = "unknown"


@dataclass(frozen=True)
class PiHealth:
	status: PiStatus
	components: dict[str, dict] = field(default_factory=dict)
	session: str | None = None

	@property
	def summary(self) -> str:
		if self.status == PiStatus.PARTIAL_FAILURE:
			failed = [name for name, detail in self.components.items()
			          if detail.get("state") == "failed"]
			return f"partial failure: {', '.join(failed)}" if failed else self.status.value
		return self.status.value

class RemoteFolderStatus(Enum):
	UNREACHABLE = "unreachable"
	REACHABLE = "reachable"
	RSYNC_ERROR = "rsync error"
	UNKNOWN_ERROR = "unknown error"


def get_pi_statuses(pi_group: Optional[List[Connection]] = None) -> Dict[str, PiHealth]:
	auto_close = False
	if pi_group is None:
		pi_group = load_pi_connections()
		auto_close = True #If we automatically open, then we should also close
	try:
		command = f"{ENV} {PYTHON_PATH} {STATUS_SCRIPT_PATH} --unit {UNIT}"
		results = run_on_connections(pi_group, command, warn=True, hide=True, timeout=5)
		return {str(connection.host): result_2_status(result)
		        for connection, result in zip(pi_group, results)}
	finally:
		if auto_close:
			for connection in pi_group:
				connection.close()

def result_2_status(result) -> PiHealth:
	if isinstance(result, BaseException):
		return PiHealth(PiStatus.UNREACHABLE)
	if getattr(result, "exited", 0) != 0:
		return PiHealth(PiStatus.UNKNOWN)
	try:
		report = json.loads(result.stdout)
		status = PiStatus(report["state"].replace("_", " "))
		components = report.get("components", {})
		if (not isinstance(components, dict)
		    or any(not isinstance(detail, dict) or detail.get("state") not in
		           ("starting", "recording", "failed", "stopped") for detail in components.values())):
			raise ValueError("Invalid component status")
		return PiHealth(status, components, report.get("session"))
	except (AttributeError, KeyError, TypeError, ValueError):
		return PiHealth(PiStatus.UNKNOWN)
	

def check_other_folders_statuses(folders: Optional[dict[str, Location]] = None) -> Dict[str, RemoteFolderStatus]:
	statuses: Dict[str, RemoteFolderStatus] = {}
	if folders is None:
		folders = other_folders_save_root()

	for label, remote_path in folders.items():
		id = f"{label}({remote_path})"

		# Use rsync --list-only to check accessibility without transferring data
		try:
			result: CompletedProcess = run(
				rsync_command(remote_path),
				capture_output=True,
				timeout=10,
				check=False
			)
		except Exception as e:
			statuses[id] = RemoteFolderStatus.UNREACHABLE
			continue
		if result.returncode == 0:
			statuses[id] = RemoteFolderStatus.REACHABLE
		else:
			stderr = result.stderr.decode(errors="ignore") if isinstance(result.stderr, bytes) else str(result.stderr)
			if "No such file or directory" in stderr or "failed to stat" in stderr or "stat failed" in stderr:
				statuses[id] = RemoteFolderStatus.RSYNC_ERROR
			elif "No route to host" in stderr or "Connection timed out" in stderr or "Connection refused" in stderr or "Could not resolve hostname" in stderr:
				statuses[id] = RemoteFolderStatus.UNREACHABLE
			else:
				statuses[id] = RemoteFolderStatus.UNKNOWN_ERROR
	return statuses


def stream_statuses(interval: int = 5) -> None:
	while True:
		print('--- Pi Statuses ---')
		statuses = get_pi_statuses()
		for name, health in statuses.items():
			print(f'{name}: {health.summary}')
			for component, detail in health.components.items():
				print(f'  {component}: {detail["state"]}')
		
		print('--- Other Folder Statuses ---')
		statuses = check_other_folders_statuses()
		for name, status in statuses.items():
			print(f'{name}: {status.value}')
		time.sleep(interval)


def main() -> None:
	stream_statuses()

if __name__ == "__main__":
	main()
