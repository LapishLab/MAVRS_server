import io
import sys
import unittest
from unittest.mock import Mock, patch

from locations import Location
from transfer_data import get_remote_folders, stream_rsync, transfer_pi


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
        self.assertIn("--out-format=%i %b", command)
        self.assertIn("--outbuf=L", command)
        self.assertNotIn("--info=progress2", command)
        self.assertEqual(command[-2:], [source.rsync_arg(), destination.rsync_arg()])


if __name__ == "__main__":
    unittest.main()
