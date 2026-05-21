import time
from enum import Enum
from typing import List, Dict
from subprocess import run, CompletedProcess
from fabric.group import SerialGroup

from load_settings import load_pi_connections
from pi_sysemd import is_active, is_reachable
from transfer_data import remote_directories

class PiStatus(Enum):
    UNREACHABLE = "unreachable"
    REACHABLE = "reachable"
    RUNNING = "running"

class RemoteFolderStatus(Enum):
    UNREACHABLE = "unreachable"
    REACHABLE = "reachable"

def check_pi_statuses(pi_group: SerialGroup) -> List[PiStatus]:
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
    return statuses

def check_remote_folders(folders: dict[str, str] = None) -> Dict[str, RemoteFolderStatus]:
    statuses: Dict[str, RemoteFolderStatus] = {}
    if folders is None:
        folders = remote_directories()

    for label, remote_path in folders.items():
        id = f"{label}({remote_path})"
        try:
            # Use rsync --list-only to check accessibility without transferring data
            result: CompletedProcess = run(
                ["rsync", "--list-only", remote_path],
                capture_output=True,
                timeout=10,
                check=False
            )
            if result.returncode == 0:
                statuses[id] = RemoteFolderStatus.REACHABLE
            else:
                statuses[id] = RemoteFolderStatus.UNREACHABLE
        except Exception:
            statuses[id] = RemoteFolderStatus.UNREACHABLE
    return statuses


def watch_pi_statuses(interval: int = 5) -> None:
    pi_group = load_pi_connections()
    while True:
        statuses = check_pi_statuses(pi_group)
        print([status.value for status in statuses])
        time.sleep(interval)


def main() -> None:
    watch_pi_statuses()

if __name__ == "__main__":
    main()