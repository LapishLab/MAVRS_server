import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from load_settings import Settings
from stop_experiment import main as stop_main
from transfer_data import main as transfer_main, run_post_session_scripts


class PostSessionScriptTests(unittest.TestCase):
    def settings(self, scripts=None, other_folders=None, **options):
        return Settings.model_validate({
            "local_data_path": str(Path.cwd().resolve() / "data with spaces"),
            "backup_data_path": None,
            "other_folders": other_folders or {},
            "post_session_scripts": scripts or {},
            **options,
        })

    def test_runs_labeled_commands_in_order_with_unquoted_directory_argument(self):
        settings = self.settings({
            "Med": ["python-a", "handling.py", "{local_data_directory}"],
            "Other": ["other-tool", "--input={local_data_directory}"],
        })
        with patch("transfer_data.run", return_value=SimpleNamespace(returncode=0)) as run, patch(
            "transfer_data.logger.info"
        ) as output:
            self.assertTrue(run_post_session_scripts(settings))

        directory = str(settings.local_data_path.local_path)
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["python-a", "handling.py", directory],
            ["other-tool", f"--input={directory}"],
        ])
        self.assertTrue(all(call.kwargs == {"check": False} for call in run.call_args_list))
        self.assertEqual([call.args for call in output.call_args_list], [
            ("Running post-session script: %s", "Med"), ("Running post-session script: %s", "Other")
        ])

    def test_reports_failure_and_continues_to_next_command(self):
        settings = self.settings({"Missing": ["missing"], "Failed": ["failed"]})
        with patch("transfer_data.run", side_effect=[OSError("not found"), SimpleNamespace(returncode=2)]) as run, patch(
            "transfer_data.logger.warning"
        ) as warning:
            self.assertFalse(run_post_session_scripts(settings))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(warning.call_count, 2)

    def test_expands_home_directory_in_command_items(self):
        settings = self.settings({
            "Med": ["~/med_handling/.venv/Scripts/python.exe", "~/med_handling/handling.py", "{local_data_directory}"]
        })
        with patch("transfer_data.run", return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(run_post_session_scripts(settings))

        home = Path.home()
        arguments = run.call_args.args[0]
        self.assertEqual(Path(arguments[0]), home / "med_handling/.venv/Scripts/python.exe")
        self.assertEqual(Path(arguments[1]), home / "med_handling/handling.py")
        self.assertEqual(arguments[2], str(settings.local_data_path.local_path))

    def test_stop_only_skips_transfer_and_processing(self):
        settings = self.settings(transfer_on_stop=False)
        with patch("stop_experiment.load_pi_connections", return_value=[]) as connections, patch(
            "stop_experiment.stop_process"
        ) as stop, patch("stop_experiment.load_settings", return_value=settings), patch(
            "stop_experiment.transfer_data.main"
        ) as transfer:
            self.assertTrue(stop_main())
        connections.assert_called_once_with()
        stop.assert_called_once_with([])
        transfer.assert_not_called()

    def test_stop_with_transfer_uses_full_transfer_command(self):
        settings = self.settings()
        with patch("stop_experiment.load_pi_connections", return_value=[]), patch(
            "stop_experiment.stop_process"
        ), patch("stop_experiment.load_settings", return_value=settings), patch(
            "stop_experiment.transfer_data.main", return_value=False
        ) as transfer:
            self.assertFalse(stop_main())
        transfer.assert_called_once_with(settings)

    def test_transfer_runs_repair_and_scripts_even_after_collection_failure(self):
        settings = self.settings({"Med": ["python", "handling.py"]}, {"ephys": None})
        events = []
        with patch("transfer_data.get_remote_folders", side_effect=lambda _: events.append("folders") or False), patch(
            "transfer_data.transfer_pis", side_effect=lambda _: events.append("pis") or True
        ), patch("transfer_data.repair_directory", side_effect=lambda _: events.append("repair") or 0), patch(
            "transfer_data.run_post_session_scripts", side_effect=lambda _: events.append("scripts") or True
        ):
            self.assertFalse(transfer_main(settings))
        self.assertEqual(events, ["folders", "pis", "repair", "scripts"])

    def test_repair_failure_keeps_transfer_result_failed(self):
        settings = self.settings()
        with patch("transfer_data.transfer_pis", return_value=True), patch(
            "transfer_data.repair_directory", return_value=1
        ) as repair, patch("transfer_data.run_post_session_scripts", return_value=True) as scripts:
            self.assertFalse(transfer_main(settings))
        repair.assert_called_once_with(settings.local_data_path.local_path)
        scripts.assert_called_once_with(settings)

    def test_legacy_repair_setting_is_accepted(self):
        self.assertFalse(self.settings(repair_videos_on_stop=False).repair_videos_on_transfer)

    def test_rejects_empty_commands_and_non_string_arguments(self):
        for scripts in ({"Med": []}, {"Med": [""]}, {"Med": ["python", 3]}):
            with self.subTest(scripts=scripts), self.assertRaises(ValidationError):
                self.settings(scripts)


if __name__ == "__main__":
    unittest.main()
