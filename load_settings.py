from yaml import full_load
from os.path import dirname, realpath

def load_settings():
    script_dir = dirname(realpath(__file__))
    settings_file = script_dir + "/settings.yaml"
    with open(settings_file, 'r') as f:
            settings = full_load(f)
    return settings

def load_experiment_names():
    script_dir = dirname(realpath(__file__))
    names_file = script_dir + "/experiment_names.txt"
    with open(names_file, "r") as file:
            lines = file.readlines()
    return lines