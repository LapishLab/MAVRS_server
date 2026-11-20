"""Generate Linux desktop entries for the MAVRS scripts."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _desktop_arg(value: str) -> str:
    """Quote one Exec argument using desktop-entry escaping rules."""
    value = value.replace("%", "%%").replace("\\", "\\\\\\\\")
    for character in ('"', "`", "$"):
        value = value.replace(character, "\\\\" + character)
    return f'"{value}"'


def generate_desktop_launcher(
    name: str,
    script_path: Path,
    icon_path: Path,
    save_directory: Path,
    *,
    interactive: bool = True,
) -> Path:
    python_path = script_path.parent / ".venv" / "bin" / "python"
    command = [python_path.as_posix()]
    if interactive:
        command.append((script_path.parent / "terminal_launcher.py").as_posix())
    command.append(script_path.as_posix())

    content = (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Comment=Launch {script_path.name}\n"
        f"Exec={' '.join(_desktop_arg(part) for part in command)}\n"
        f"Icon={icon_path.as_posix()}\n"
        f"Path={script_path.parent.as_posix()}\n"
        f"Terminal={'true' if interactive else 'false'}\n"
        "StartupNotify=false\n"
    )
    save_directory.mkdir(parents=True, exist_ok=True)
    desktop_file_path = save_directory / f"{name.lower().replace(' ', '_')}.desktop"
    desktop_file_path.write_text(content, encoding="utf-8")
    desktop_file_path.chmod(0o755)
    return desktop_file_path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    png_folder = repo_root / "setup" / "desktop_launchers" / "png"
    save_folder = Path.home() / "Desktop" / "MAVRS Launchers"

    for name, script, icon, interactive in (
        ("Start Experiment", "start_experiment.py", "start.png", True),
        ("Stop Experiment", "stop_experiment.py", "stop.png", True),
        ("Backup Data", "backup_data.py", "upload.png", True),
        ("GUI", "user_gui.py", "glop.png", False),
    ):
        launcher = generate_desktop_launcher(
            name, repo_root / script, png_folder / icon, save_folder,
            interactive=interactive,
        )
        logger.info("Created launcher for '%s' at: %s", name, launcher)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
