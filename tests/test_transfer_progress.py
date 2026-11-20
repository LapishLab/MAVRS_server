import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from locations import Location
from transfer_data import count_pi_files, get_remote_folders, stream_rsync, transfer_pi, transfer_pis


class TransferProgressTests(unittest.TestCase):
    def test_summarizes_completed_files_and_preserves_errors(self):
        process = Mock()
        process.stdout = io.StringIO(">f+++++++++ 1024\ncd+++++++++ 0\n>f+++++++++ 2048\nrsync: connection lost\n")
        process.wait.return_value = 12

        with patch("transfer_data.Popen", return_value=process), patch(
            "transfer_data.logger.warning"
        ) as warning, patch("transfer_data.logger.info") as info:
            success, output = stream_rsync(["rsync"], "ephys")

        self.assertFalse(success)
        self.assertEqual(output, "rsync: connection lost")
        warning.assert_called_once_with("[%s] %s", "ephys", "rsync: connection lost")
        info.assert_not_called()

    def test_reports_while_a_large_file_is_still_transferring(self):
        script = "import time; time.sleep(0.3); print('>f+++++++++ 1024', flush=True)"
        with patch("transfer_data.PROGRESS_INTERVAL_SECONDS", 0.05), patch(
            "transfer_data.logger.info"
        ) as info:
            success, output = stream_rsync([sys.executable, "-c", script], "camera")

        self.assertTrue(success)
        self.assertEqual(output, "")
        messages = [call.args[0] for call in info.call_args_list]
        self.assertIn("[%s] Transferring: %s files completed, %s transferred", messages)
        self.assertIn("[%s] Transfer complete: %s files, %s transferred", messages)
        self.assertIn(("camera", 0, "0 B"), [call.args[1:] for call in info.call_args_list])
        self.assertIn(("camera", 1, "1.0 KiB"), [call.args[1:] for call in info.call_args_list])

    def test_other_folder_transfer_uses_streaming_and_reports_failure(self):
        source = Location("user@host:/recordings")
        destination = Location("C:/data")
        settings = Mock(local_data_path=destination)

        with patch("transfer_data.other_folders_save_root", return_value={"ephys": source}), patch(
            "transfer_data.stream_rsync", return_value=(False, "connection lost")
        ) as stream, patch("transfer_data.logger.warning") as warning, patch("builtins.print"):
            get_remote_folders(settings)

        stream.assert_called_once()
        command, label = stream.call_args.args
        self.assertEqual(label, "ephys")
        self.assertIn("--out-format=%i %b", command)
        self.assertNotIn("--info=progress2", command)
        self.assertEqual(command[-2:], [source.rsync_arg(), destination.rsync_arg()])
        warning.assert_called_once()
        self.assertIn("connection lost", warning.call_args.args)

    def test_pi_transfer_uses_compact_file_output(self):
        source = Location("pi@camera.local:2222", path_override="~/MAVRS_pi/data")
        destination = Location("/data")

        with patch("transfer_data.stream_rsync", return_value=(True, "")) as stream:
            transfer_pi(source, destination)

        command, label = stream.call_args.args
        self.assertEqual(label, str(source))
        self.assertEqual(stream.call_args.kwargs, {"on_file_completed": None, "on_warning": None})
        self.assertIn("--out-format=%i %b", command)
        self.assertIn("--outbuf=L", command)
        self.assertNotIn("--info=progress2", command)
        self.assertEqual(command[-2:], [source.rsync_arg(), destination.rsync_arg()])

    def test_pi_file_count_matches_files_scheduled_by_rsync(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            destination = Path(directory) / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "existing.txt").write_text("already copied")
            shutil.copy2(source / "existing.txt", destination / "existing.txt")
            (source / "new.txt").write_text("copy me")
            (source / ".hidden.txt").write_text("excluded")

            self.assertEqual(count_pi_files(Location(source), Location(destination)), 1)
            self.assertFalse((destination / "new.txt").exists())

    def test_parallel_pi_transfers_report_one_combined_file_count(self):
        pis = [Location("pi@camera-a:/data"), Location("pi@camera-b:/data")]
        settings = Mock(local_data_path=Location("/data"))
        script = "import time; print('>f+++++++++ 1024', flush=True); time.sleep(0.15)"

        with patch("transfer_data.load_pi_addresses", return_value=pis), patch(
            "transfer_data.count_pi_files", return_value=1
        ), patch(
            "transfer_data.rsync_command", return_value=[sys.executable, "-c", script]
        ), patch("transfer_data.cleanup_pi", return_value=(1, 1)), patch(
            "transfer_data.PROGRESS_INTERVAL_SECONDS", 0.05
        ), patch("transfer_data.logger.info") as info, redirect_stdout(io.StringIO()) as output:
            self.assertTrue(transfer_pis(settings))

        self.assertEqual(output.getvalue(), "Pi Transfer progress: 0% -> 100%\n")
        self.assertIn(
            ("All data successfully transferred from Pis (%s/%s total files)", 2, 2),
            [call.args for call in info.call_args_list],
        )
        self.assertIn(("All eligible Pi files deleted successfully",), [call.args for call in info.call_args_list])
        self.assertFalse(any("transferred successfully; deleted" in call.args[0] for call in info.call_args_list))
        self.assertFalse(any(call.args[0].startswith("[%s] Transfer complete") for call in info.call_args_list))

    def test_pi_transfer_continues_when_file_count_is_unavailable(self):
        pi = Location("pi@camera:/data")
        settings = Mock(local_data_path=Location("/data"))
        script = "print('>f+++++++++ 1024')"

        with patch("transfer_data.load_pi_addresses", return_value=[pi]), patch(
            "transfer_data.count_pi_files", return_value=None
        ), patch("transfer_data.rsync_command", return_value=[sys.executable, "-c", script]), patch(
            "transfer_data.cleanup_pi", return_value=(1, 1)
        ), patch("transfer_data.logger.info") as info, redirect_stdout(io.StringIO()) as output:
            self.assertTrue(transfer_pis(settings))

        self.assertEqual(output.getvalue(), "Pi Transfer progress: 0 files -> 1 file\n")
        self.assertIn(
            ("All data successfully transferred from Pis (%s files; total unavailable)", 1),
            [call.args for call in info.call_args_list],
        )

    def test_pi_warnings_follow_the_progress_line(self):
        pi = Location("pi@camera:/data")
        settings = Mock(local_data_path=Location("/data"))
        script = "print('rsync: minor warning', flush=True); print('>f+++++++++ 1024', flush=True)"
        output = io.StringIO()

        def check_warning(*args):
            self.assertTrue(output.getvalue().endswith("\n"))

        with patch("transfer_data.load_pi_addresses", return_value=[pi]), patch(
            "transfer_data.count_pi_files", return_value=1
        ), patch("transfer_data.rsync_command", return_value=[sys.executable, "-c", script]), patch(
            "transfer_data.cleanup_pi", return_value=(1, 1)
        ), patch("transfer_data.logger.warning", side_effect=check_warning) as warning, redirect_stdout(output):
            self.assertTrue(transfer_pis(settings))

        self.assertEqual(output.getvalue(), "Pi Transfer progress: 0% -> 100%\n")
        warning.assert_called_once_with("[%s] %s", str(pi), "rsync: minor warning")

    def test_failed_pi_transfer_reports_error_without_success_summary(self):
        pi = Location("pi@camera:/data")
        settings = Mock(local_data_path=Location("/data"))

        with patch("transfer_data.load_pi_addresses", return_value=[pi]), patch(
            "transfer_data.count_pi_files", return_value=1
        ), patch("transfer_data.rsync_command", return_value=[sys.executable, "-c", "raise SystemExit(12)"]), patch(
            "transfer_data.cleanup_pi"
        ) as cleanup, patch("transfer_data.logger.info") as info, patch(
            "transfer_data.logger.warning"
        ) as warning, redirect_stdout(io.StringIO()) as output:
            self.assertFalse(transfer_pis(settings))

        self.assertEqual(output.getvalue(), "Pi Transfer progress: 0%\n")
        self.assertFalse(any(call.args[0].startswith("All data successfully transferred from Pis") for call in info.call_args_list))
        self.assertTrue(any(call.args[0] == "Rsync failed for %s: %s" for call in warning.call_args_list))
        cleanup.assert_not_called()

    def test_cleanup_error_is_reported_for_its_pi_without_success_summary(self):
        pi = Location("pi@camera:/data")
        settings = Mock(local_data_path=Location("/data"))

        with patch("transfer_data.load_pi_addresses", return_value=[pi]), patch(
            "transfer_data.count_pi_files", return_value=1
        ), patch("transfer_data.rsync_command", return_value=[sys.executable, "-c", "print('>f+++++++++ 1024')"]), patch(
            "transfer_data.cleanup_pi", side_effect=RuntimeError("Deleted 0 of 1 eligible files")
        ), patch("transfer_data.logger.info") as info, patch(
            "transfer_data.logger.warning"
        ) as warning, redirect_stdout(io.StringIO()):
            self.assertFalse(transfer_pis(settings))

        self.assertFalse(any("successfully" in call.args[0] for call in info.call_args_list))
        self.assertTrue(any(call.args[0] == "Cleanup failed for %s: %s. Data remains on this Pi where cleanup did not complete." for call in warning.call_args_list))


if __name__ == "__main__":
    unittest.main()
