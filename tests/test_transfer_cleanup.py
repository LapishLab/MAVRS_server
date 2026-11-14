import json
import stat
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from transfer_cleanup import cleanup_pi, eligible_files


class TransferCleanupTests(unittest.TestCase):
    def setUp(self):
        self.second = 1_800_000_000_000_000_000
        self.files = {
            "session/equal": (4, self.second),
            "session/newer": (6, self.second + 1_000_000_000),
            "session/different_size": (6, self.second),
            "session/older": (4, self.second),
        }

    def fake_lstat(self, path):
        relative = str(path).replace("\\", "/").removeprefix("/server/")
        if relative == "session":
            return SimpleNamespace(st_mode=stat.S_IFDIR)
        if relative not in self.files:
            raise FileNotFoundError(relative)
        size, mtime = self.files[relative]
        return SimpleNamespace(st_mode=stat.S_IFREG, st_size=size, st_mtime_ns=mtime)

    def test_selects_equal_or_newer_files_only(self):
        second = self.second
        inventory = [
            ["session/equal", 4, second],
            ["session/newer", 4, second],
            ["session/different_size", 4, second],
            ["session/older", 4, second + 1_000_000_000],
            ["session/missing", 4, second],
            ["session/.hidden", 4, second],
            ["../outside", 4, second],
            ["/outside", 4, second],
        ]
        with patch.object(Path, "lstat", lambda path: self.fake_lstat(path)):
            result = eligible_files(inventory, "/server")
        self.assertEqual([row[0] for row in result], ["session/equal", "session/newer"])

    def test_cleanup_uses_inventory_and_sends_only_selected_files(self):
        second = self.second
        calls = []

        def remote(host, port, action, input_text=None):
            calls.append((host, port, action, input_text))
            if action == "inventory":
                return json.dumps([["session/equal", 4, second], ["session/missing", 4, second]])
            self.assertEqual(action, "delete")
            self.assertEqual(json.loads(input_text), [["session/equal", 4, second]])
            return json.dumps({"deleted": 1, "selected": 1})

        with patch.object(Path, "lstat", lambda path: self.fake_lstat(path)), patch(
            "transfer_cleanup._pi_command", side_effect=remote
        ):
            self.assertEqual(cleanup_pi("pi", "2222", "/server"), (1, 2))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][:2], ("pi", "2222"))


if __name__ == "__main__":
    unittest.main()
