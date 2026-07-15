from pathlib import Path

CONFIG_FOLDER = Path.home() / "MAVRS_settings"
SETTINGS_FILE = CONFIG_FOLDER / "settings.yaml"
PI_ADDRESS_FILE = CONFIG_FOLDER / "pi_addresses.txt"
EXPERIMENT_NAMES_FILE = CONFIG_FOLDER / "experiment_names.txt"
LOG_FOLDER = CONFIG_FOLDER / "logs"

PI_SETTINGS_FOLDER = CONFIG_FOLDER / "pi_settings"

LOG_FOLDER.mkdir(exist_ok=True)
PI_SETTINGS_FOLDER.mkdir(exist_ok=True)