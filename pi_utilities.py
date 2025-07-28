import subprocess
import datetime
from pathlib import Path

def send_pi_command(pi_cmd):
    names_file = Path.home() / ".config/MAVRS_server/pi_addresses.txt"
    cmd = [
        'parallel-ssh',
        '--timeout', '0',
        '--hosts', str(names_file),
        '--inline', '--print',
        pi_cmd
    ]
    subprocess.run(cmd, check=True)