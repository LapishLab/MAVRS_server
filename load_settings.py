#!/usr/bin/env python3
import logging
import yaml 
from pathlib import Path
from typing import Dict, Optional, List, Union
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from path_config import EXPERIMENT_NAMES_FILE, PI_ADDRESS_FILE, SETTINGS_FILE
from fabric import Config, Connection
from locations import Location
from console_logging import configure_logging

logger = logging.getLogger(__name__)

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
	post_session_scripts: Dict[str, List[str]] = Field(default_factory=dict)
	repair_videos_on_stop: bool = True
	suggested_name_format: str = "%date%_%time%_%experiment%_rat%input{rat number}%"
	backup_data_path: Optional[Location]

	@field_validator("post_session_scripts")
	@classmethod
	def require_commands(cls, scripts: Dict[str, List[str]]) -> Dict[str, List[str]]:
		for label, command in scripts.items():
			if not label.strip():
				raise ValueError("post_session_scripts labels cannot be blank")
			if not command or not command[0].strip():
				raise ValueError(f"post_session_scripts entry {label!r} needs an executable")
		return scripts

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
		if not isinstance(v, dict):
			return v
		folders = {}
		for label, path in v.items():
			try:
				location = Location(path) if isinstance(path, str) else path
			except ValueError as exc:
				raise ValueError(f"Folder {label!r}: {exc}") from exc
			if isinstance(location, Location) and location.path is None:
				raise ValueError(f"Folder {label!r} needs a directory path")
			folders[label] = location
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
	logger.info("Settings loaded successfully.")
	logger.info("%s", settings)
	
	experiment_names = load_experiment_names()
	logger.info("Experiment names loaded successfully.")
	logger.info("%s", experiment_names)

	pi_names = load_pi_addresses()
	logger.info("Pi names loaded successfully.")
	logger.info("%s", pi_names)

if __name__ == "__main__":
	configure_logging()
	test()
