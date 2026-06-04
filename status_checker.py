import time
from enum import Enum
from typing import List, Dict, Optional
from subprocess import run, CompletedProcess

from load_settings import load_pi_connections
from pi_sysemd import is_active, is_reachable
from transfer_data import remote_directories
from fabric_tools import run_on_connections
from fabric import Connection

class PiStatus(Enum):
    UNREACHABLE = "unreachable"
    REACHABLE = "reachable"
    RUNNING = "running"

class RemoteFolderStatus(Enum):
    UNREACHABLE = "unreachable"
    REACHABLE = "reachable"
    RSYNC_ERROR = "rsync error"
    UNKNOWN_ERROR = "unknown error"

def check_pi_statuses(pi_group: List[Connection]) -> Dict[str, PiStatus]:
    reachable = is_reachable(pi_group)
    active = is_active(pi_group)

    statuses: List[PiStatus] = []
    for reach, act in zip(reachable, active):
        if not reach:
            statuses.append(PiStatus.UNREACHABLE)
        elif act:
            statuses.append(PiStatus.RUNNING)
        else:
            statuses.append(PiStatus.REACHABLE)

    names = [str(c.host) for c in pi_group]
    return dict(zip(names, statuses))

def check_remote_folders(folders: Optional[dict[str, str]] = None) -> Dict[str, RemoteFolderStatus]:
    statuses: Dict[str, RemoteFolderStatus] = {}
    if folders is None:
        folders = remote_directories()

    for label, remote_path in folders.items():
        id = f"{label}({remote_path})"

        # Use rsync --list-only to check accessibility without transferring data
        try:
            result: CompletedProcess = run(
                ["rsync", "--list-only", remote_path],
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


def watch_pi_statuses(interval: int = 5) -> None:
    pi_group = load_pi_connections()
    while True:
        statuses = check_pi_statuses(pi_group)
        print([status.value for status in statuses.values()])
        time.sleep(interval)


def main() -> None:
    watch_pi_statuses()

if __name__ == "__main__":
    main()