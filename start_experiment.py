import subprocess
import datetime
from load_settings import load_settings, load_experiment_names
import os
from pathlib import Path
def main():
    # Change directory for running the following shell scripts 
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    print("Setting clock time on Pis")
    subprocess.run(["./setTime.sh"], check=True)

    print("Reporting disk space on Pis")
    subprocess.run(["./reportDiskSpace.sh"], check=True)

    session = get_session_name()
    create_med_folder(session)
    create_local_folders(session)
    input("Hit enter when ready to start Pi recording")
    start_pi_recordings(session)

def create_local_folders(session):
    data_path = load_settings()['computers']['server']['data_path']
    session_path = f"{data_path}/{session}/"
    print(f"Creating ephys and anymaze folders at: {session_path}")
    ephys_folder = f"{session_path}/ephys_{session}"
    subprocess.run(["mkdir", "-p", ephys_folder], check=True)
    anymaze_folder = f"{session_path}/anymaze_{session}"
    subprocess.run(["mkdir", "-p", anymaze_folder], check=True)
    
def get_session_name():
    while True:
        # exp = input("Enter experiment name: ")
        exp = choose_experiment_from_file()
        rat = input("Enter rat number: ")
        time_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        suggested = f"{time_str}_{exp}_rat{rat}"
        print(suggested)
        response = input('If the above name is correct, hit enter. If incorrect, type "n" to restart selection: ')
        if not response == "n":
            return suggested

def create_med_folder(session):
    settings = load_settings()
    med = settings['computers']['med_pc']
    folder_name = f"/{session}/med-pc_{session}"
    print(f"Creating MED-PC folder: {med['data_path']}{folder_name}")

    remote_data_folder = f"{med['username']}@{med['address']}:{med['data_path']}"
    create_remote_folder_via_rsync(folder_name, remote_data_folder)

def create_remote_folder_via_rsync(folder, remote): 
    # Hacky way to create folder on remote PC running rsync without having to deal with Windows vs. Linux OS issues
    # Create folder locally in home/temp
    temp_folder = f"{Path.home()}/temp/"
    cmd = ["mkdir", "-p", f"{temp_folder}{folder}"]
    subprocess.run(cmd, check=True)

    # Sync local folder to remote
    cmd = ["rsync", "-ah","--info=progress2", temp_folder, remote]
    subprocess.run(cmd, check=True)

    # Delete local folder
    cmd = ["rm", "-rf", temp_folder]
    subprocess.run(cmd, check=True)

def start_pi_recordings(session):
    print(f"Starting Pi recordings: {session}")
    pi_session =  f"{session}/pi-data_{session}"
    pi_cmd = f"python -u MAVRS_pi/startExperiment.py --session {pi_session}"
    cmd = ["cssh", "piCluster", "-a", pi_cmd]
    subprocess.run(cmd, check=True)

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