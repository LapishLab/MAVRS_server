from pathlib import Path
def main():
    print("This script generates .desktop launchers for Linux.")
    repo_root = Path(__file__).parent.parent.parent.resolve()
    png_folder = repo_root / "setup" / "desktop_launchers" / "png"
    
    save_folder = Path.home() / "Desktop" / "MAVRS Launchers"
    save_folder.mkdir(parents=True, exist_ok=True)

    generate_desktop_launcher(
        name="Start Experiment",
        script_path = repo_root / "start_experiment.py",
        icon_path = png_folder / "start.png",
        save_directory = save_folder
        )
    generate_desktop_launcher(
        name="Stop Experiment",
        script_path = repo_root / "stop_experiment.py",
        icon_path = png_folder / "stop.png",
        save_directory = save_folder
    )
    generate_desktop_launcher(
        name="Backup Data",
        script_path = repo_root / "backup_data.py",
        icon_path = png_folder / "upload.png",
        save_directory = save_folder
    )

def generate_desktop_launcher(name: str, script_path: Path, icon_path: Path, save_directory: Path):
    content = f"""[Desktop Entry]
    Version=1.0
    Type=Application
    Name={name}
    Comment=Launch {script_path.name}
    Exec= sh -c 'python3 {script_path.name}; echo "Press enter to close window..."; read dummy'
    Icon={icon_path.as_posix()}
    Path={script_path.parent.as_posix()}
    Terminal=true
    StartupNotify=false
    """
    file_slug = name.lower().replace(" ", "_")
    desktop_file_path = save_directory / f"{file_slug}.desktop"
    desktop_file_path.write_text(content)
    desktop_file_path.chmod(0o755)
    print(f"Created launcher for '{name}' at: {desktop_file_path}")


if __name__ == "__main__":
    main()