import time
from enum import Enum
from typing import List, Dict, Optional
from subprocess import run, CompletedProcess

from load_settings import load_pi_connections, other_folders_save_root
from config import ENV, UNIT
from fabric_tools import run_on_connections
from fabric import Connection

class PiStatus(Enum):
    UNREACHABLE = "unreachable"
    REACHABLE = "reachable"
    RUNNING = "running"
    UNKNOWN = "unknown"

class RemoteFolderStatus(Enum):
    UNREACHABLE = "unreachable"
    REACHABLE = "reachable"
    RSYNC_ERROR = "rsync error"
    UNKNOWN_ERROR = "unknown error"


def get_pi_statuses(pi_group: Optional[List[Connection]] = None) -> Dict[str, PiStatus]:
    if pi_group is None:
        pi_group = load_pi_connections()
    results = run_on_connections(pi_group, f"{ENV} systemctl --user is-active {UNIT}.service", warn=True, hide=True, timeout=2)
    statuses = [result_2_status(r) for r in results]
    names = [str(c.host) for c in pi_group]
    return dict(zip(names, statuses)) 

def result_2_status(result):  
    if isinstance(result, BaseException):
        return PiStatus.UNREACHABLE
    if getattr(result, "stdout", "").strip() == "active":
        return PiStatus.RUNNING
    else:
        return PiStatus.REACHABLE
    

def check_other_folders_statuses(folders: Optional[dict[str, str]] = None) -> Dict[str, RemoteFolderStatus]:
    statuses: Dict[str, RemoteFolderStatus] = {}
    if folders is None:
        folders = other_folders_save_root()

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


def stream_statuses(interval: int = 5) -> None:
    while True:
        print('--- Pi Statuses ---')
        statuses = get_pi_statuses()
        for name, status in statuses.items():
            print(f'{name}: {status.value}')
        
        print('--- Other Folder Statuses ---')
        statuses = check_other_folders_statuses()
        for name, status in statuses.items():
            print(f'{name}: {status.value}')
        time.sleep(interval)


def main() -> None:
    stream_statuses()

if __name__ == "__main__":
    main()