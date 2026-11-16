from pathlib import Path

TEMPLATE_FOLDER = Path(__file__).resolve().parent / "setup" / "config_templates"
CONFIG_FOLDER = Path.home() / "MAVRS_settings"
SETTINGS_FILE = CONFIG_FOLDER / "settings.yaml"
PI_ADDRESS_FILE = CONFIG_FOLDER / "pi_addresses.txt"
EXPERIMENT_NAMES_FILE = CONFIG_FOLDER / "experiment_names.txt"
LOG_FOLDER = CONFIG_FOLDER / "logs"
PI_SETTINGS_FILE = CONFIG_FOLDER / "mavrs_pi_config.yaml"

CONFIG_FOLDER.mkdir(parents=True, exist_ok=True)
LOG_FOLDER.mkdir(exist_ok=True)

for name, destination in (
    ("settings.yaml", SETTINGS_FILE),
    ("pi_addresses.txt", PI_ADDRESS_FILE),
    ("experiment_names.txt", EXPERIMENT_NAMES_FILE),
    ("mavrs_pi_config.yaml", PI_SETTINGS_FILE),
):
    contents = (TEMPLATE_FOLDER / name).read_bytes()
    try:
        with destination.open("xb") as file:
            file.write(contents)
    except FileExistsError:
        pass
    else:
        if name == "settings.yaml":
            (Path.home() / "MAVRS_data").mkdir(exist_ok=True)
