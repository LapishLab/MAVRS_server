from datetime import datetime
from fabric import Connection
from fabric_tools import run_on_connections
from typing import Optional, List

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
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Get current local time again to minimize time difference
    results = run_on_connections(pis, f"timedatectl set-time {time_str}", warn=True, pty=True, hide=True) # Set the time

    # Verify time was set correctly
    local_time = datetime.now()
    pi_times = get_pi_time(pis)

    unparsable = [conn.host for conn, t in zip(pis, pi_times) if t is None]
    if unparsable:
        raise RuntimeError(f"Failed to get time from the following Pis: {', '.join(unparsable)}. Cannot verify time was set correctly.")
    
    t_threshold = 20.0 # seconds
    t_diff = [abs((local_time-t).total_seconds()) for t in pi_times]
    over_threshold = [conn.host for conn, diff in zip(pis, t_diff) if diff > t_threshold]
    if over_threshold:
        raise RuntimeError(f"Time on the following Pis is off by more than {t_threshold} seconds: {', '.join(over_threshold)}. Time may not have been set correctly.")    
    print("Time successfully set on all Pis.")

def report_disk_space(pis: List[Connection]) -> None:
    run_on_connections(pis, "sh MAVRS_pi/reportDiskSpace.sh", warn=False)