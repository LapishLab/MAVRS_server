from yaml import full_load
# from os.path import dirname, realpath, join
from pathlib import Path

def load_settings():
    settings_file = Path.home() / ".config/MAVRS_server/settings.yaml"
    with open(settings_file, 'r') as f:
            settings = full_load(f)
    return settings

def load_experiment_names():
    names_file = Path.home() / ".config/MAVRS_server/experiment_names.txt"
    with open(names_file, "r") as file:
            lines = file.readlines()
    return lines

def test():
        settings = load_settings()
        print("Settings loaded successfully.")
        print(settings)
        
        experiment_names = load_experiment_names()
        print("Experiment names loaded successfully.")
        print(experiment_names)

if __name__ == "__main__":
    test()