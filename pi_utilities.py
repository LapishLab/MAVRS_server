import logging
from datetime import datetime, timezone
from tzlocal import get_localzone_name
from fabric import Connection
from fabric_tools import run_on_connections
from typing import Optional, List

logger = logging.getLogger(__name__)


def send_individual_pi_command(pi_cmd: str, pi_name: str) -> None:
    """Execute a command on a single Pi using Fabric."""
    conn = Connection(host=pi_name)
    result = conn.run(pi_cmd, warn=False)
    if result.failed:
        raise RuntimeError(f"Command failed on {pi_name}: {result.stderr}")

def get_pi_time(pis: List[Connection]) -> list[datetime]:
    """Get the current time from each Pi."""
    results = run_on_connections(pis,"date '+%Y-%m-%d %H:%M:%S'", warn=True, hide=True)
    results = [getattr(v, "stdout", "").strip() for v in results] # get stdout if it exists
    pi_times = []
    for r in results:
        try:
            pi_times.append(datetime.strptime(r, "%Y-%m-%d %H:%M:%S"))
        except Exception:
            pi_times.append(None)
    return pi_times

def set_time_on_pis(pis: List[Connection]) -> None:
    """Set clock time on Pis"""
    tz_name = get_localzone_name()
    utc_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")    
    cmd = (
        f"sudo timedatectl set-timezone {tz_name}; "
        f"sudo timedatectl set-time '{utc_time} UTC'"
    )
    run_on_connections(pis, cmd, warn=True, pty=True, hide=True, timeout=2)
    verify_times(pis)

def verify_times(pis):
    # Verify time was set correctly
    local_time = datetime.now()
    pi_times = get_pi_time(pis)

    unparsable = [str(conn.host) for conn, t in zip(pis, pi_times) if t is None]
    if unparsable:
        logger.warning(f"Failed to get time from the following Pis: {', '.join(unparsable)}. Cannot verify time was set correctly.")
        return
    
    t_threshold = 20.0 # seconds
    t_diff = [abs((local_time-t).total_seconds()) for t in pi_times]
    over_threshold = [str(conn.host) for conn, diff in zip(pis, t_diff) if diff > t_threshold]
    if over_threshold:
        logger.warning(f"Time on the following Pis is off by more than {t_threshold} seconds: {', '.join(over_threshold)}. Time may not have been set correctly.")
        return
    print("Time successfully set on all Pis.")

def report_disk_space(pis: List[Connection]) -> None:
    run_on_connections(pis, "sh MAVRS_pi/reportDiskSpace.sh", warn=False)