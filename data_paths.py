"""Read and update the path fields in the server settings file."""

import os
import tempfile
from pathlib import Path

import yaml

from load_settings import Settings
from path_config import SETTINGS_FILE


def _load_settings(settings_file: Path) -> dict:
    settings = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise ValueError("Settings must contain a YAML mapping")
    return settings


def read_data_paths(
    settings_file: Path = SETTINGS_FILE,
) -> tuple[str, str | None, dict[str, str | None], str]:
    settings = _load_settings(settings_file)

    local_path = settings.get("local_data_path", "")
    backup_path = settings.get("backup_data_path")
    folders = settings.get("other_folders")
    suggested_name_format = settings.get(
        "suggested_name_format",
        Settings.model_fields["suggested_name_format"].default,
    )
    if folders is None:
        folders = {}
    if (
        not isinstance(local_path, str)
        or (backup_path is not None and not isinstance(backup_path, str))
    ):
        raise ValueError("Data paths must be text or null")
    if not isinstance(suggested_name_format, str):
        raise ValueError("Suggested session name format must be text")
    if not isinstance(folders, dict) or any(
        not isinstance(name, str) or (path is not None and not isinstance(path, str))
        for name, path in folders.items()
    ):
        raise ValueError("Other folders must map names to text paths or null")
    return local_path, backup_path, folders, suggested_name_format


def save_data_paths(
    local_path: str,
    backup_path: str | None,
    folders: dict[str, str | None],
    suggested_name_format: str,
    settings_file: Path = SETTINGS_FILE,
) -> None:
    """Update data-path and session-name fields while retaining other settings."""
    settings = _load_settings(settings_file)
    settings["local_data_path"] = local_path
    settings["backup_data_path"] = backup_path
    settings["other_folders"] = folders
    settings["suggested_name_format"] = suggested_name_format
    Settings.model_validate(settings)
    updated = yaml.safe_dump(settings, sort_keys=False, allow_unicode=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=settings_file.parent, delete=False) as file:
            temporary_path = Path(file.name)
            file.write(updated)
        os.replace(temporary_path, settings_file)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
