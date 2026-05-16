from subprocess import run
from datetime import datetime
from path_config import PI_ADDRESS_FILE

def send_pi_command(pi_cmd: str) -> None:
    cmd = [
        'parallel-ssh',
        '--timeout', '0',
        '--hosts', str(PI_ADDRESS_FILE),
        '--print',
        pi_cmd
    ]
    run(cmd, check=True)

def send_individual_pi_command(pi_cmd: str, pi_name: str) -> None:
    cmd = [
        'ssh',
        pi_name,
        pi_cmd
    ]
    run(cmd, check=True)

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
