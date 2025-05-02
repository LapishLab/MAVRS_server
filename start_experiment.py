import subprocess
import datetime
from load_settings import load_settings, load_experiment_names
def main():
    print("Setting clock time on Pis")
    subprocess.run(["./setTime.sh"], check=True)

    print("Reporting disk space on Pis")
    subprocess.run(["./reportDiskSpace.sh"], check=True)

    session = get_session_name()
    create_med_folder(session)
    input("Hit enter when ready to start Pi recording")
    start_pi_recordings(session)

def get_session_name():
    while True:
        # exp = input("Enter experiment name: ")
        exp = choose_experiment_from_file()
        group = input("Enter group number: ")
        time_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        suggested = f"{time_str}_{exp}_group{group}"
        print(suggested)
        response = input('If the above name is correct, hit enter. If incorrect, type "n" to restart selection: ')
        if not response == "n":
            return suggested

def create_med_folder(session):
    settings = load_settings()
    med = settings['computers']['med_pc']
    folder_name = f"{med['data_path_temp']}/{session}/med-pc_{session}"
    print(f"Creating MED-PC folder: {folder_name}")

    pc_name = f"{med['username']}@{med['address']}"
    cmd = ["ssh", pc_name, f"mkdir -p /{folder_name}"]
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
    main()