from yaml import full_load
# from os.path import dirname, realpath, join
from pathlib import Path

def settings_folder():
    return Path.home() / "MAVRS_settings"

def load_settings():
    settings_file = settings_folder()/"settings.yaml"
    with open(settings_file, 'r') as f:
        settings = full_load(f)
    return settings

def load_experiment_names():
    names_file = settings_folder()/"experiment_names.txt"
    with open(names_file, "r") as file:
        lines = file.readlines()
    return lines

def pi_address_file():
    return settings_folder()/"pi_addresses.txt"

def load_pi_addresses():
    names_file = pi_address_file()
    with open(names_file, 'r') as file:
        names = file.read().splitlines()
    return names

def test():
    settings = load_settings()
    print("Settings loaded successfully.")
    print(settings)
    
    experiment_names = load_experiment_names()
    print("Experiment names loaded successfully.")
    print(experiment_names)

    pi_names = load_pi_addresses()
    print("Pi names loaded successfully.")
    print(pi_names)

if __name__ == "__main__":
    test()