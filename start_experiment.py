from subprocess import run
from datetime import datetime
from load_settings import load_pi_connections, load_settings, load_experiment_names, Settings
from pathlib import Path
from pi_utilities import set_time_on_pis, report_disk_space
from re import search, sub
from pi_sysemd import start_process
from fabric_tools import run_on_connections
from typing import Optional, List
from fabric import Connection

def main() -> None:
    pis = load_pi_connections()
    settings = load_settings()
    session = get_session_name(settings)
    initialize(pis, settings, session)
    input("Hit enter when ready to start Pi recording")
    start_pi_recordings(pis, session)

def initialize(pis: List[Connection], settings: Settings, session: str) -> None:
    set_time_on_pis(pis)
    report_disk_space(pis)
    create_other_folders(session, settings)

def create_other_folders(session: str, settings: Settings) -> None:
    folders = settings.other_folders or {}
    for label in folders:
        print(f"creating {label} folder")
        
        # create folder in temporary location
        temp = f"{Path.home()}/.temp/"
        folder_name = f"{session}/{label}_{session}"
        cmd = ["mkdir", "-p", f"{temp}{folder_name}"]
        run(cmd, check=True)

        # copy folder to destination
        dest: str = folders[label] if folders[label] else settings.local_data_path

        cmd = ["rsync", "-ah","--info=progress2", temp, dest]
        run(cmd, check=True) #TODO handle, error descriptively

        # Delete temporary folder
        cmd = ["rm", "-rf", temp]
        run(cmd, check=True)
        print(f"Created: {dest}/{folder_name}")
    
def get_session_name(settings: Settings) -> str:
    while True:
        suggested = settings.suggested_name_format
        now = datetime.now()
        suggested = suggested.replace("%date%", now.strftime("%Y-%m-%d"))
        suggested = suggested.replace("%time%", now.strftime("%H-%M-%S"))
        
        if "%experiment%" in suggested:
            exp = choose_experiment_from_file()
            suggested = suggested.replace("%experiment%", exp)
        
        input_pattern=r"%input.*?%"
        while search(input_pattern, suggested):
            match = search(input_pattern, suggested)
            sub_match = search(r"{.*?}", match.group())
            if sub_match:
                label = sub_match.group()[1:-1]
            else:
                label = ""
            val = input(f"Enter {label}: ")
            suggested = sub(input_pattern, val, suggested, count=1)

        print(suggested)
        response = input('If the above name is correct, hit enter. If incorrect, type "n" to restart selection: ')
        if not response == "n":
            return suggested

def start_pi_recordings(pis: List[Connection], session: str) -> None:
    print(f"Starting Pi recordings: {session}")
    pi_session =  f"{session}/pi-data_{session}"
    start_process(pis, pi_session)

def choose_experiment_from_file() -> str:
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
    main()