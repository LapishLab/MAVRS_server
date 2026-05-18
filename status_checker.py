import time
from enum import Enum
from typing import List
from fabric.group import SerialGroup

from load_settings import load_pi_connections
from pi_sysemd import is_active, is_reachable

class PiStatus(Enum):
    UNREACHABLE = "unreachable"
    REACHABLE = "reachable"
    RUNNING = "running"

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