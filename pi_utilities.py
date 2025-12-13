import subprocess
import datetime
from load_settings import pi_address_file

def send_pi_command(pi_cmd):
    cmd = [
        'parallel-ssh',
        '--timeout', '0',
        '--hosts', str(pi_address_file()),
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

def shutdown_pis():
    print("shutting down Pis")
    send_pi_command("sudo shutdown now")
