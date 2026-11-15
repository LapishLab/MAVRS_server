"""Open interactive MAVRS scripts in a native console on Windows or Linux."""

import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def _console_python() -> str:
    executable = Path(sys.executable)
    if sys.platform == "win32" and executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    return str(executable)


def find_terminal_emulator() -> tuple[str, list[str]]:
    candidates = [
        ("x-terminal-emulator", ["-e"]),
        ("gnome-terminal", ["--"]),
        ("konsole", ["-e"]),
        ("xfce4-terminal", ["--command"]),
        ("xterm", ["-e"]),
    ]
    for executable, arguments in candidates:
        if shutil.which(executable):
            return executable, arguments
    raise RuntimeError("No terminal emulator found. Install a supported terminal emulator.")


def launch_script_in_terminal(script_path: Path) -> None:
    command = [_console_python(), str(Path(__file__).resolve()), str(script_path)]
    if sys.platform == "win32":
        subprocess.Popen(command, cwd=script_path.parent, creationflags=subprocess.CREATE_NEW_CONSOLE)
        return

    terminal, arguments = find_terminal_emulator()
    if arguments == ["--command"]:
        terminal_command = [terminal, *arguments, shlex.join(command)]
    else:
        terminal_command = [terminal, *arguments, *command]
    subprocess.Popen(terminal_command, cwd=script_path.parent)


def _run_script(script_path: Path) -> int:
    try:
        result = subprocess.run([_console_python(), str(script_path)], cwd=script_path.parent)
        if result.returncode:
            print(f"\nScript exited with status {result.returncode}.")
        return result.returncode
    finally:
        try:
            input("\nPress Enter to close this window...")
        except EOFError:
            pass


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Expected a script path")
    raise SystemExit(_run_script(Path(sys.argv[1]).resolve()))
