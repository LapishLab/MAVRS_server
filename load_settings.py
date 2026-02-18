#!/usr/bin/env python3
import yaml 
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel

def settings_folder():
    return Path.home() / "MAVRS_settings"

def load_settings():
    settings_file = settings_folder()/"settings.yaml"
    try:
        with open(settings_file, 'r') as f:
            settings = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Error parsing YAML: {exc}")
    except FileNotFoundError:
        raise RuntimeError(f"File not found: {settings_file}")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred when loading {settings_file}: {e}")
    
    validated = Settings.parse_obj(settings)
    return validated

class Settings(BaseModel):
    local_data_path: str
    other_folders: Dict[str, Optional[str]]
    suggested_name_format: Optional[str] = "%date%_%time%_%experiment%_rat%input{rat number}%"
    backup_data_path: Optional[str]

def load_experiment_names():
    file = settings_folder()/"experiment_names.txt"
    return read_lines(file)

def pi_address_file():
    return settings_folder()/"pi_addresses.txt"

def load_pi_addresses():
    file = pi_address_file()
    return read_lines(file)

def read_lines(file):
    with open(file, "r") as f:
        lines = f.readlines()
    lines = [l.partition('#')[0].strip() for l in lines] # remove any thing after '#' character
    lines = [l for l in lines if l] #remove empty lines
    return lines

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