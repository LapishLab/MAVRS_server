from datetime import datetime
from load_settings import load_pi_addresses
from fabric import Connection
from fabric.group import SerialGroup


def send_pi_command(pi_cmd: str) -> None:
    """Execute a command on all Pis in parallel using Fabric."""
    pi_names = load_pi_addresses()
    hosts = SerialGroup(*[Connection(host=pi) for pi in pi_names])
    result = hosts.run(pi_cmd, warn=False)
    
    # Check if any host failed
    for connection, task_result in result.items():
        if task_result.failed:
            raise RuntimeError(f"Command failed on {connection.host}: {task_result.stderr}")


def send_individual_pi_command(pi_cmd: str, pi_name: str) -> None:
    """Execute a command on a single Pi using Fabric."""
    conn = Connection(host=pi_name)
    result = conn.run(pi_cmd, warn=False)
    if result.failed:
        raise RuntimeError(f"Command failed on {pi_name}: {result.stderr}")

def set_time_on_pis() -> None:
    print("Setting clock time on Pis")
    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    print(f"setting time on all Pis to {day} {time_str}")
    pi_cmd = f"sudo sh MAVRS_pi/setTime.sh {day} {time_str}"
    send_pi_command(pi_cmd)

def report_disk_space() -> None:
    print("Reporting disk space on Pis")
    send_pi_command("sh MAVRS_pi/reportDiskSpace.sh")

def delete_pi_data() -> None:
    print("deleting all data from Pis")
    send_pi_command("bash MAVRS_pi/nuke.sh")

def shutdown_pis() -> None:
    print("shutting down Pis")
    send_pi_command("sudo shutdown now")
