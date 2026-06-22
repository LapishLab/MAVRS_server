#!/usr/bin/env python3
import yaml 
from pathlib import Path
from typing import Dict, Optional, List, Union
from pydantic import BaseModel, field_validator
from path_config import EXPERIMENT_NAMES_FILE, PI_ADDRESS_FILE, SETTINGS_FILE
from fabric import Config, Connection

class Settings(BaseModel):
    local_data_path: str
    other_folders: Dict[str, Optional[str]] = {}
    suggested_name_format: str = "%date%_%time%_%experiment%_rat%input{rat number}%"
    backup_data_path: Optional[str]

    @field_validator("other_folders", mode="before")
    @classmethod
    def none2dict(cls, v):
        if v is None:
            return {}
        return v

def load_settings() -> Settings:
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Error parsing YAML: {exc}")
    except FileNotFoundError:
        raise RuntimeError(f"File not found: {SETTINGS_FILE}")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred when loading {SETTINGS_FILE}: {e}")
    
    return Settings.model_validate(settings)

def load_experiment_names() -> List[str]:
    return read_lines(EXPERIMENT_NAMES_FILE)    

def load_pi_addresses() -> List[str]:
    return read_lines(PI_ADDRESS_FILE)

def load_pi_connections() -> List[Connection]:
    pi_names = load_pi_addresses()
    config = Config(overrides={
        'sudo': {'password': ' '},
        'timeouts':{'connect':5},
        'transport':{'keepalive', 30},
        })
    return [Connection(host=h, config=config) for h in pi_names]

def read_lines(file: Union[str, Path]) -> List[str]:
    with open(file, "r") as f:
        lines = f.readlines()
    lines = [l.partition('#')[0].strip() for l in lines] # remove any thing after '#' character
    lines = [l for l in lines if l] #remove empty lines
    return lines

def other_folders_save_root(settings: Optional[Settings] = None) -> dict[str, str]:
    if not settings:
        settings = load_settings()
    folders = settings.other_folders
    # Add local data path if none specified
    folders = {k: (settings.local_data_path if v is None else v) for k, v in folders.items()}
    return folders

def test() -> None:
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