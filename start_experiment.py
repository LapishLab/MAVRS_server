import subprocess
import datetime
from load_settings import load_settings, load_experiment_names
import os
from pathlib import Path
import pi_utilities
import re

def main():
    # Change directory for running the following shell scripts 
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    pi_utilities.set_time_on_pis()
    pi_utilities.report_disk_space()

    session = get_session_name()
    create_other_folders(session)
    input("Hit enter when ready to start Pi recording")
    start_pi_recordings(session)

def create_other_folders(session):
    folders = load_settings()['other_folders']
    for label in folders:
        print(f"creating {label} folder")
        
        # create folder in temporary location
        temp = f"{Path.home()}/.temp/"
        folder_name = f"{session}/{label}_{session}"
        cmd = ["mkdir", "-p", f"{temp}{folder_name}"]
        subprocess.run(cmd, check=True)

        # copy folder to destination
        if folders[label]: # assumed to be remote
            dest = folders[label]
        else: #assumed to be local
            dest = load_settings()['local_data_path']

        cmd = ["rsync", "-ah","--info=progress2", temp, dest]
        subprocess.run(cmd, check=True) #TODO handle, error descriptively

        # Delete temporary folder
        cmd = ["rm", "-rf", temp]
        subprocess.run(cmd, check=True)
        print(f"Created: {dest}/{folder_name}")
    
def get_session_name():
    while True:
        suggested = load_settings()['suggested_name_format']
        now  =  datetime.datetime.now()
        suggested = suggested.replace("%date%", now.strftime("%Y-%m-%d"))
        suggested = suggested.replace("%time%", now.strftime("%H-%M-%S"))
        
        if "%experiment%" in suggested:
            exp = choose_experiment_from_file()
            suggested = suggested.replace("%experiment%", exp)
        
        input_pattern=r"%input.*?%"
        while re.search(input_pattern, suggested):
            match = re.search(input_pattern, suggested)
            sub_match = re.search(r"{.*?}", match.group())
            if sub_match:
                label = sub_match.group()[1:-1]
            else:
                label = ""
            val = input(f"Enter {label}: ")
            suggested = re.sub(input_pattern, val, suggested, count=1)

        print(suggested)
        response = input('If the above name is correct, hit enter. If incorrect, type "n" to restart selection: ')
        if not response == "n":
            return suggested

def start_pi_recordings(session):
    print(f"Starting Pi recordings: {session}")
    pi_session =  f"{session}/pi-data_{session}"
    pi_cmd = f"nohup python -u MAVRS_pi/startExperiment.py --session {pi_session} &"
    pi_utilities.send_pi_command(pi_cmd)

def choose_experiment_from_file():
    lines = load_experiment_names()

    while True:
        print("\nSelect an experiment name:")
        for index, line in enumerate(lines, start=1):
            print(f"{index}. {line.strip()}")
        choice = input("\nEnter number or hit enter to choose #1: ") or "1"

        if choice.isdigit():
            choice = int(choice)
            if 1 <= choice <= len(lines):
                return lines[choice - 1].strip()
            else:
                print("\nInvalid input. Enter a number within the valid range.")
        else:
            print("\nInvalid input. Please enter a number.")

if __name__ == "__main__":
    try:
        main()
    except:
        input()