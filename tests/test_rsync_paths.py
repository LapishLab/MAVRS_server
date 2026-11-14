import unittest
from pathlib import Path
from unittest.mock import patch

from rsync_paths import rsync_command, rsync_path


class RsyncPathTests(unittest.TestCase):
    def test_windows_drive_paths(self):
        self.assertEqual(rsync_path("C:\\data\\session\\", windows=True), "/cygdrive/c/data/session/")
        self.assertEqual(rsync_path("E:/recordings/", windows=True), "/cygdrive/e/recordings/")
        self.assertEqual(rsync_path(Path("D:/folder with spaces"), windows=True), "/cygdrive/d/folder with spaces")

    def test_windows_unc_and_relative_paths(self):
        self.assertEqual(rsync_path("\\\\server\\share\\data\\", windows=True), "//server/share/data/")
        self.assertEqual(rsync_path("recordings\\session\\", windows=True), "recordings/session/")

    def test_remote_paths_are_preserved(self):
        for remote in (
            "pi:/home/pi/MAVRS_pi/data/",
            "user@example.org:/backup with spaces/",
            "rsync://example.org/module/data/",
        ):
            with self.subTest(remote=remote):
                self.assertEqual(rsync_path(remote, windows=True), remote)

    def test_linux_paths_are_unchanged(self):
        self.assertEqual(rsync_path("/mnt/c/data/", windows=False), "/mnt/c/data/")
        self.assertEqual(rsync_path("user@host:/data/", windows=False), "user@host:/data/")

    def test_windows_rejects_wsl_and_drive_relative_paths(self):
        with self.assertRaisesRegex(ValueError, "WSL path"):
            rsync_path("/mnt/c/data/", windows=True)
        with self.assertRaisesRegex(ValueError, "absolute Windows drive path"):
            rsync_path("C:data", windows=True)

    def test_command_converts_only_path_arguments(self):
        convert_for_windows = lambda path: rsync_path(path, windows=True)
        with patch("rsync_paths.rsync_path", side_effect=convert_for_windows):
            self.assertEqual(
                rsync_command(
                    "pi:/home/pi/data/", "E:/recordings/",
                    update=True, exclude=".*", ssh_port=2222,
                ),
                ["rsync", "--archive", "--human-readable", "--info=progress2", "--update",
                 "--exclude=.*", "--rsh=ssh -p 2222",
                 "pi:/home/pi/data/", "/cygdrive/e/recordings/"],
            )
            self.assertEqual(
                rsync_command("C:/data/", "user@backup:/data/", update=True),
                ["rsync", "--archive", "--human-readable", "--info=progress2", "--update",
                 "/cygdrive/c/data/", "user@backup:/data/"],
            )
            self.assertEqual(
                rsync_command("E:/data/", list_only=True),
                ["rsync", "--list-only", "/cygdrive/e/data/"],
            )
            self.assertEqual(
                rsync_command("C:/settings/", "pi:/home/pi/"),
                ["rsync", "--archive", "--human-readable", "--info=progress2",
                 "/cygdrive/c/settings/", "pi:/home/pi/"],
            )


if __name__ == "__main__":
    unittest.main()
