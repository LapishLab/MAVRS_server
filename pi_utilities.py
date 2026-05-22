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

def get_pi_time(pis: SerialGroup) -> dict[str, datetime]:
    """Get the current time from each Pi."""
    results = pis.run("date '+%Y-%m-%d %H:%M:%S'", warn=True, hide=True)
    pi_times = {}
    for conn, task_result in results.items():
        if task_result.failed:
            pi_times[conn.host] = None
        else:
            pi_time_str = task_result.stdout.strip()
            pi_times[conn.host] = datetime.strptime(pi_time_str, "%Y-%m-%d %H:%M:%S")
    return pi_times

def set_time_on_pis(pis: SerialGroup) -> None:
    """Set clock time on Pis, only updating if off by more than 1 second."""
    local_time = datetime.now()
    pi_times = get_pi_time(pis)
    
    # Check which Pis need time updates
    need_updated = []
    for t in pi_times:
        if pi_times[t] is None:
            need_updated.append(t)
        else:
            time_diff = abs((local_time - pi_times[t]).total_seconds())
            if time_diff > 1.0:
                need_updated.append(t)

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