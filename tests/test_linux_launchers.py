import shlex
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from setup.desktop_launchers.generate_linux_launchers import generate_desktop_launcher


class LinuxLauncherTests(unittest.TestCase):
    def test_interactive_launcher_uses_console_runner_and_quotes_paths(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "MAVRS Server"
            script = root / "start_experiment.py"
            launcher = generate_desktop_launcher(
                "Start Experiment", script, root / "start.png", Path(temp) / "launchers"
            )
            lines = launcher.read_text().splitlines()

        self.assertEqual(lines[0], "[Desktop Entry]")
        exec_line = next(line.removeprefix("Exec=") for line in lines if line.startswith("Exec="))
        self.assertEqual(shlex.split(exec_line), [
            (root / ".venv" / "bin" / "python").as_posix(),
            (root / "terminal_launcher.py").as_posix(),
            script.as_posix(),
        ])
        self.assertIn("Terminal=true", lines)

    def test_gui_launcher_runs_without_console_runner(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "MAVRS Server"
            launcher = generate_desktop_launcher(
                "GUI", root / "user_gui.py", root / "glop.png", Path(temp) / "launchers",
                interactive=False,
            )
            lines = launcher.read_text().splitlines()

        exec_line = next(line.removeprefix("Exec=") for line in lines if line.startswith("Exec="))
        self.assertEqual(shlex.split(exec_line), [
            (root / ".venv" / "bin" / "python").as_posix(), (root / "user_gui.py").as_posix(),
        ])
        self.assertIn("Terminal=false", lines)


if __name__ == "__main__":
    unittest.main()
