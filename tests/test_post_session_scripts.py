import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from load_settings import Settings
from stop_experiment import main as stop_main, run_post_session_scripts
from transfer_data import main as transfer_main


class PostSessionScriptTests(unittest.TestCase):
    def settings(self, scripts=None, other_folders=None):
        return Settings.model_validate({
            "local_data_path": str(Path.cwd().resolve() / "data with spaces"),
            "backup_data_path": None,
            "other_folders": other_folders or {},
            "post_session_scripts": scripts or {},
        })

    def test_runs_labeled_commands_in_order_with_unquoted_directory_argument(self):
        settings = self.settings({
            "Med": ["python-a", "handling.py", "{local_data_directory}"],
            "Other": ["other-tool", "--input={local_data_directory}"],
        })
        with patch("stop_experiment.run", return_value=SimpleNamespace(returncode=0)) as run, patch(
            "builtins.print"
        ) as output:
            self.assertTrue(run_post_session_scripts(settings))

        directory = str(settings.local_data_path.local_path)
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["python-a", "handling.py", directory],
            ["other-tool", f"--input={directory}"],
        ])
        self.assertTrue(all(call.kwargs == {"check": False} for call in run.call_args_list))
        self.assertEqual([call.args[0] for call in output.call_args_list], [
            "Running post-session script: Med", "Running post-session script: Other"
        ])

    def test_reports_failure_and_continues_to_next_command(self):
        settings = self.settings({"Missing": ["missing"], "Failed": ["failed"]})
        with patch("stop_experiment.run", side_effect=[OSError("not found"), SimpleNamespace(returncode=2)]) as run, patch(
            "stop_experiment.logger.warning"
        ) as warning, patch("builtins.print"):
            self.assertFalse(run_post_session_scripts(settings))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(warning.call_count, 2)

    def test_expands_home_directory_in_command_items(self):
        settings = self.settings({
            "Med": ["~/med_handling/.venv/Scripts/python.exe", "~/med_handling/handling.py", "{local_data_directory}"]
        })
        with patch("stop_experiment.run", return_value=SimpleNamespace(returncode=0)) as run, patch("builtins.print"):
            self.assertTrue(run_post_session_scripts(settings))

        home = Path.home()
        arguments = run.call_args.args[0]
        self.assertEqual(Path(arguments[0]), home / "med_handling/.venv/Scripts/python.exe")
        self.assertEqual(Path(arguments[1]), home / "med_handling/handling.py")
        self.assertEqual(arguments[2], str(settings.local_data_path.local_path))

    def test_stop_runs_scripts_after_collection_even_when_it_fails(self):
        settings = self.settings({"Med": ["python", "handling.py"]}, {"ephys": None})
        events = []
        with patch("stop_experiment.stop_pis", side_effect=lambda: events.append("stop")), patch(
            "stop_experiment.load_settings", return_value=settings
        ), patch("stop_experiment.transfer_data.main", side_effect=lambda _: events.append("transfer") or True), patch(
            "stop_experiment.run_post_session_scripts", side_effect=lambda _: events.append("scripts") or True
        ), patch("builtins.print"):
            self.assertTrue(stop_main())
        self.assertEqual(events, ["stop", "transfer", "scripts"])

        events.clear()
        with patch("stop_experiment.stop_pis", side_effect=lambda: events.append("stop")), patch(
            "stop_experiment.load_settings", return_value=settings
        ), patch("stop_experiment.transfer_data.main", side_effect=lambda _: events.append("transfer") or False), patch(
            "stop_experiment.run_post_session_scripts", side_effect=lambda _: events.append("scripts") or True
        ), patch("builtins.print"):
            self.assertFalse(stop_main())
        self.assertEqual(events, ["stop", "transfer", "scripts"])

    def test_direct_transfer_does_not_run_scripts(self):
        settings = self.settings({"Med": ["python", "handling.py"]}, {"ephys": None})
        with patch("transfer_data.get_remote_folders", return_value=True) as folders, patch(
            "transfer_data.transfer_pis", return_value=True
        ) as pis, patch("stop_experiment.run_post_session_scripts") as scripts:
            self.assertTrue(transfer_main(settings))
        folders.assert_called_once_with(settings)
        pis.assert_called_once_with(settings)
        scripts.assert_not_called()

    def test_rejects_empty_commands_and_non_string_arguments(self):
        for scripts in ({"Med": []}, {"Med": [""]}, {"Med": ["python", 3]}):
            with self.subTest(scripts=scripts), self.assertRaises(ValidationError):
                self.settings(scripts)


if __name__ == "__main__":
    unittest.main()
