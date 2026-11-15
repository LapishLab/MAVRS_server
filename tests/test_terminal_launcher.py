import shlex
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import terminal_launcher


class TerminalLauncherTests(unittest.TestCase):
    def setUp(self):
        self.script = Path.cwd() / "folder with spaces" / "start_experiment.py"

    def test_windows_opens_native_console(self):
        with patch("terminal_launcher.sys.platform", "win32"), patch.object(
            subprocess, "CREATE_NEW_CONSOLE", 16, create=True
        ), patch("terminal_launcher.subprocess.Popen") as popen, patch(
            "terminal_launcher.find_terminal_emulator"
        ) as find_terminal:
            terminal_launcher.launch_script_in_terminal(self.script)

        command = popen.call_args.args[0]
        self.assertEqual(command[-1], str(self.script))
        self.assertEqual(Path(command[1]).name, "terminal_launcher.py")
        self.assertEqual(popen.call_args.kwargs["cwd"], self.script.parent)
        self.assertEqual(popen.call_args.kwargs["creationflags"], 16)
        find_terminal.assert_not_called()

    def test_linux_terminal_receives_argument_list(self):
        with patch("terminal_launcher.sys.platform", "linux"), patch(
            "terminal_launcher.find_terminal_emulator", return_value=("gnome-terminal", ["--"])
        ), patch("terminal_launcher.subprocess.Popen") as popen:
            terminal_launcher.launch_script_in_terminal(self.script)

        self.assertEqual(popen.call_args.args[0][:2], ["gnome-terminal", "--"])
        self.assertEqual(popen.call_args.args[0][-1], str(self.script))
        self.assertNotIn("sh", popen.call_args.args[0])

    def test_xfce_command_preserves_spaces(self):
        with patch("terminal_launcher.sys.platform", "linux"), patch(
            "terminal_launcher.find_terminal_emulator", return_value=("xfce4-terminal", ["--command"])
        ), patch("terminal_launcher.subprocess.Popen") as popen:
            terminal_launcher.launch_script_in_terminal(self.script)

        command = popen.call_args.args[0]
        self.assertEqual(command[:2], ["xfce4-terminal", "--command"])
        self.assertEqual(shlex.split(command[2])[-1], str(self.script))

    def test_runner_preserves_exit_status_and_waits(self):
        with patch("terminal_launcher.subprocess.run", return_value=SimpleNamespace(returncode=7)) as run, patch(
            "builtins.input", return_value=""
        ) as user_input, patch("builtins.print"):
            self.assertEqual(terminal_launcher._run_script(self.script), 7)

        self.assertEqual(run.call_args.args[0][-1], str(self.script))
        self.assertEqual(run.call_args.kwargs["cwd"], self.script.parent)
        user_input.assert_called_once()


if __name__ == "__main__":
    unittest.main()
