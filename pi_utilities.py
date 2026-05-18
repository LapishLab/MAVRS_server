from datetime import datetime
from fabric import Connection
from fabric.group import SerialGroup
from time import sleep

def send_individual_pi_command(pi_cmd: str, pi_name: str) -> None:
    """Execute a command on a single Pi using Fabric."""
    conn = Connection(host=pi_name)
    result = conn.run(pi_cmd, warn=False)
    if result.failed:
        raise RuntimeError(f"Command failed on {pi_name}: {result.stderr}")

def set_time_on_pis(pis: SerialGroup) -> None:
    """Set clock time on Pis, only updating if off by more than 1 second."""
    local_time = datetime.now()
    results = pis.run("date '+%Y-%m-%d %H:%M:%S'", warn=True, hide=True)
    
    # Check which Pis need time updates
    need_updated = []
    for conn, task_result in results.items():
        if task_result.failed:
            raise RuntimeError(f"{conn.host}: Failed to query time")
        pi_time_str = task_result.stdout.strip()
        pi_time = datetime.strptime(pi_time_str, "%Y-%m-%d %H:%M:%S")
        time_diff = abs((local_time - pi_time).total_seconds())
        if time_diff > 1.0: need_updated.append(conn)

    # Update time on Pis if needed
    for conn in pis:
        conn.sudo("timedatectl set-ntp no", warn=True, hide=True) # Turn off NTP
        sleep(0.1)  # Small delay to ensure NTP is turned off before setting time
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Get current local time again to minimize time difference
        conn.sudo(f"timedatectl set-time {time_str}", warn=True, pty=True, hide=True) # Set the time
        sleep(0.1)  # Small delay to ensure time is set before turning NTP back on
        conn.sudo("timedatectl set-ntp yes", warn=True, pty=True, hide=True) # Turn on NTP

def report_disk_space(pis: SerialGroup) -> None:
    pis.run("sh MAVRS_pi/reportDiskSpace.sh", warn=False)