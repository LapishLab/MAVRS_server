#!/usr/bin/env python3
import yaml 
from pathlib import Path
from typing import Dict, Optional, List, Union
from pydantic import BaseModel, ValidationInfo, field_validator
from path_config import EXPERIMENT_NAMES_FILE, PI_ADDRESS_FILE, SETTINGS_FILE
from fabric import Config, Connection
from rsync_paths import Location

PI_DATA_PATH = "~/MAVRS_pi/data"

class PiConnection(Connection):
	def open(self):
		result = super().open()
		if self.transport is not None:
			self.transport.set_keepalive(30)
		return result

class Settings(BaseModel):
	local_data_path: Location
	other_folders: Dict[str, Optional[Location]] = {}
	suggested_name_format: str = "%date%_%time%_%experiment%_rat%input{rat number}%"
	backup_data_path: Optional[Location]

	@field_validator("local_data_path", "backup_data_path", mode="before")
	@classmethod
	def parse_directory(cls, value, info: ValidationInfo):
		location = Location(value) if isinstance(value, str) else value
		if isinstance(location, Location) and location.path is None:
			raise ValueError(f"{info.field_name} requires a directory path")
		if info.field_name == "local_data_path" and isinstance(location, Location) and location.host is not None:
			raise ValueError("local_data_path must be a local directory")
		return location

	@field_validator("other_folders", mode="before")
	@classmethod
	def none2dict(cls, v):
		if v is None:
			return {}
		folders = {label: Location(path) if isinstance(path, str) else path for label, path in v.items()}
		if any(location is not None and location.path is None for location in folders.values()):
			raise ValueError("Each other_folders location needs a directory path")
		return folders

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

def load_pi_addresses() -> List[Location]:
	pis = [Location(line) for line in read_lines(PI_ADDRESS_FILE)]
	if any(pi.host is None for pi in pis):
		raise ValueError("Pi addresses must contain a remote host")
	return [pi.with_path(PI_DATA_PATH) if pi.path is None else pi for pi in pis]

def load_pi_connections() -> List[Connection]:
	pi_names = load_pi_addresses()
	config = Config(overrides={
		'sudo': {'password': ' '},
		'timeouts':{'connect':5},
		})
	return [PiConnection(host=pi.host, user=pi.username, port=pi.port, config=config) for pi in pi_names]

def read_lines(file: Union[str, Path]) -> List[str]:
	with open(file, "r") as f:
		lines = f.readlines()
	lines = [l.partition('#')[0].strip() for l in lines] # remove any thing after '#' character
	lines = [l for l in lines if l] #remove empty lines
	return lines

def other_folders_save_root(settings: Optional[Settings] = None) -> dict[str, Location]:
	if not settings:
		settings = load_settings()
	return {
		label: location if location is not None else settings.local_data_path
		for label, location in settings.other_folders.items()
	}

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
