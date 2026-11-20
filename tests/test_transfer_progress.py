import unittest
from unittest.mock import Mock, patch

from locations import Location
from transfer_data import get_remote_folders, stream_rsync


class TransferProgressTests(unittest.TestCase):
    def test_streams_carriage_return_progress_before_rsync_exits(self):
        events = []
        process = Mock()
        process.stdout.fileno.return_value = 7
        process.wait.side_effect = lambda: events.append("wait") or 0
        chunks = iter((b"10%\r20", b"%\r", b"done", b""))

        with patch("transfer_data.Popen", return_value=process), patch(
            "transfer_data.os.read", side_effect=lambda *_: next(chunks)
        ), patch("transfer_data.logger.info", side_effect=lambda _format, label, message: events.append(f"[{label}] {message}")):
            success, output = stream_rsync(["rsync"], "ephys")

        self.assertTrue(success)
        self.assertEqual(output, "10%\n20%\ndone")
        self.assertEqual(events, ["[ephys] 10%", "[ephys] 20%", "[ephys] done", "wait"])

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
        self.assertEqual(command[-2:], [source.rsync_arg(), destination.rsync_arg()])
        warning.assert_called_once()
        self.assertIn("connection lost", warning.call_args.args)


if __name__ == "__main__":
    unittest.main()
