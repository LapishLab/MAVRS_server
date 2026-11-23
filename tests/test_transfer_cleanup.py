import json
import stat
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from transfer_cleanup import _pi_command, cleanup_pi, eligible_files


class TransferCleanupTests(unittest.TestCase):
    def setUp(self):
        self.second = 1_800_000_000_000_000_000
        self.files = {
            "session/equal": (4, self.second),
            "session/newer": (6, self.second + 1_000_000_000),
            "session/different_size": (6, self.second),
            "session/older": (4, self.second),
            "session/rounded": (4, self.second - 5_000_000),
            "session/boundary": (4, self.second - 10_000_000),
            "session/too_old": (4, self.second - 10_000_001),
            "session/rounded_different_size": (6, self.second - 5_000_000),
        }

    def fake_lstat(self, path):
        relative = str(path).replace("\\", "/").removeprefix("/server/")
        if relative == "session":
            return SimpleNamespace(st_mode=stat.S_IFDIR)
        if relative not in self.files:
            raise FileNotFoundError(relative)
        size, mtime = self.files[relative]
        return SimpleNamespace(st_mode=stat.S_IFREG, st_size=size, st_mtime_ns=mtime)

    def test_selects_same_size_or_server_copy_not_older_than_pi(self):
        second = self.second
        inventory = [
            ["session/equal", 4, second],
            ["session/newer", 4, second],
            ["session/different_size", 4, second],
            ["session/older", 4, second + 1_000_000_000],
            ["session/rounded", 4, second],
            ["session/boundary", 4, second],
            ["session/too_old", 4, second],
            ["session/rounded_different_size", 4, second],
            ["session/missing", 4, second],
            ["session/.hidden", 4, second],
            ["../outside", 4, second],
            ["/outside", 4, second],
        ]
        with patch.object(Path, "lstat", lambda path: self.fake_lstat(path)), self.assertLogs(
            "transfer_cleanup", level="WARNING"
        ) as warnings:
            selected = eligible_files(inventory, "/server", "pi")
        self.assertEqual(selected,
                         ["session/equal", "session/newer", "session/different_size",
                          "session/older", "session/rounded", "session/boundary",
                          "session/too_old", "session/rounded_different_size"])
        self.assertEqual(len(warnings.output), len(inventory) - len(selected))
        self.assertTrue(any("session/missing" in warning for warning in warnings.output))

    def test_cleanup_uses_inventory_and_sends_only_selected_files(self):
        second = self.second
        calls = []

        def remote(host, port, action, input_text=None):
            calls.append((host, port, action, input_text))
            if action == "inventory":
                return json.dumps([["session/equal", 4, second]])
            self.assertEqual(action, "delete")
            self.assertEqual(json.loads(input_text), ["session/equal"])
            return json.dumps({"deleted": 1, "selected": 1})

        with patch.object(Path, "lstat", lambda path: self.fake_lstat(path)), patch(
            "transfer_cleanup._pi_command", side_effect=remote
        ):
            self.assertEqual(cleanup_pi("pi", "2222", "/server"), (1, 1))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][:2], ("pi", "2222"))

    def test_partial_deletion_is_reported_as_a_warning(self):
        inventory = [["session/equal", 4, self.second]]
        with patch.object(Path, "lstat", lambda path: self.fake_lstat(path)), patch(
            "transfer_cleanup._pi_command",
            side_effect=[json.dumps(inventory), json.dumps({"deleted": 0})],
        ), self.assertLogs("transfer_cleanup", level="WARNING") as warnings:
            self.assertEqual(cleanup_pi("pi", None, "/server"), (0, 1))
        self.assertIn("Deleted 0 of 1 approved files from pi", warnings.output[0])
        self.assertIn("disappeared", warnings.output[0])

    def test_unmatched_files_report_why_they_remain_on_the_pi(self):
        inventory = [
            ["session/missing", 4, self.second],
            ["session/different_size", 4, self.second + 1_000_000_000],
            ["session/rounded_different_size", 4, self.second + 1_000_000_000],
        ]
        with patch.object(Path, "lstat", lambda path: self.fake_lstat(path)), patch(
            "transfer_cleanup._pi_command",
            side_effect=[json.dumps(inventory), json.dumps({"deleted": 0})],
        ) as remote, self.assertLogs("transfer_cleanup", level="WARNING") as warnings:
            self.assertEqual(cleanup_pi("pi", None, "/server"), (0, 3))

        self.assertEqual(json.loads(remote.call_args.args[3]), [])
        self.assertEqual(len(warnings.output), 3)
        self.assertIn("session/missing", warnings.output[0])
        self.assertIn("File not on server", warnings.output[0])
        self.assertIn("File sizes differ and pi file is newer", warnings.output[1])
        self.assertIn("File sizes differ and pi file is newer", warnings.output[2])

    def test_ssh_config_can_choose_default_port(self):
        with patch("transfer_cleanup.run", return_value=SimpleNamespace(stdout="ok")) as run:
            self.assertEqual(_pi_command("pi@camera.local", None, "inventory"), "ok")
        self.assertEqual(run.call_args.args[0][:2], ["ssh", "pi@camera.local"])


if __name__ == "__main__":
    unittest.main()
