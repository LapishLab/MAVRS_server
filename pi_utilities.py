import subprocess
import datetime
from pathlib import Path

def send_pi_command(pi_cmd):
    names_file = Path.home() / ".config/MAVRS_server/pi_addresses.txt"
    cmd = [
        'parallel-ssh',
        '--timeout', '0',
        '--hosts', str(names_file),
        '--print',
        pi_cmd
    ]
    subprocess.run(cmd, check=True)

def set_time_on_pis():
    print("Setting clock time on Pis")
    now = datetime.datetime.now()
    day = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    print(f"setting time on all Pis to {day} {time_str}")
    pi_cmd = f"sudo sh MAVRS_pi/setTime.sh {day} {time_str}"
    send_pi_command(pi_cmd)

def report_disk_space():
    print("Reporting disk space on Pis")
    send_pi_command("sh MAVRS_pi/reportDiskSpace.sh")

def delete_pi_data():
    print("deleting all data from Pis")
    send_pi_command("bash MAVRS_pi/nuke.sh")
