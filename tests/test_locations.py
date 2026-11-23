import unittest
import os
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from locations import Location, build_rsh_command, rsync_command, local_path_for_rsync


class RsyncPathTests(unittest.TestCase):
    def test_windows_drive_paths(self):
        self.assertEqual(local_path_for_rsync("C:\\data\\session\\", windows=True), "/cygdrive/c/data/session/")
        self.assertEqual(local_path_for_rsync("E:/recordings/", windows=True), "/cygdrive/e/recordings/")
        self.assertEqual(local_path_for_rsync(Path("D:/folder with spaces"), windows=True), "/cygdrive/d/folder with spaces")

    def test_windows_unc_and_relative_paths(self):
        self.assertEqual(local_path_for_rsync("\\\\server\\share\\data\\", windows=True), "//server/share/data/")
        self.assertEqual(local_path_for_rsync("recordings\\session\\", windows=True), "recordings/session/")

    def test_linux_paths_are_unchanged(self):
        self.assertEqual(local_path_for_rsync("/mnt/c/data/", windows=False), "/mnt/c/data/")

    def test_windows_rejects_wsl_and_drive_relative_paths(self):
        with self.assertRaisesRegex(ValueError, "WSL path"):
            local_path_for_rsync("/mnt/c/data/", windows=True)
        with self.assertRaisesRegex(ValueError, "absolute Windows drive path"):
            local_path_for_rsync("C:data", windows=True)

    @unittest.skipUnless(os.name == "nt", "requires native Windows paths")
    def test_command_converts_only_path_arguments(self):
        convert_for_windows = lambda path: local_path_for_rsync(path, windows=True)
        rsync_executable = str(Path(__file__).resolve().parents[1] / ".tools" / "cwrsync" / "bin" / "rsync.exe")
        with patch("locations.local_path_for_rsync", side_effect=convert_for_windows), patch(
            "locations.build_rsh_command",
            side_effect=lambda port: f"--rsh=ssh -p {port}" if port is not None else "--rsh=ssh",
        ):
            self.assertEqual(
                rsync_command(
                    Location("pi:2222/home/pi/data/"),
                    Location("E:/recordings/"), update=True, exclude=".*",
                ),
                [rsync_executable, "--rsh=ssh -p 2222", "--exclude=.*",
                 "--archive", "--human-readable", "--info=progress2", "--update",
                 "pi:/home/pi/data/", "/cygdrive/e/recordings/"],
            )
            self.assertEqual(
                rsync_command(Location("C:/data/"), Location("user@backup:/data/"), update=True),
                [rsync_executable, "--rsh=ssh", "--archive", "--human-readable", "--info=progress2", "--update",
                 "/cygdrive/c/data/", "user@backup:/data/"],
            )
            self.assertEqual(
                rsync_command(Location("E:/data/")),
                [rsync_executable, "--rsh=ssh", "--list-only", "/cygdrive/e/data/"],
            )
            self.assertEqual(
                rsync_command(Location("C:/settings/"), Location("pi:/home/pi/")),
                [rsync_executable, "--rsh=ssh", "--archive", "--human-readable", "--info=progress2",
                 "/cygdrive/c/settings/", "pi:/home/pi/"],
            )

    @unittest.skipUnless(os.name == "nt", "requires native Windows paths")
    def test_windows_rsh_uses_bundled_ssh_and_user_config(self):
        ssh_executable = Path(__file__).resolve().parents[1] / ".tools" / "cwrsync" / "bin" / "ssh.exe"
        with patch("locations.Path.home", return_value=Path("C:/Users/Test User")), patch(
            "locations.Path.is_file", return_value=True
        ):
            self.assertEqual(
                build_rsh_command(2222),
                f'--rsh="{local_path_for_rsync(ssh_executable)}" '
                '-F "/cygdrive/c/Users/Test User/.ssh/config" '
                '-i "/cygdrive/c/Users/Test User/.ssh/id_ed25519" '
                '-o "UserKnownHostsFile=/cygdrive/c/Users/Test User/.ssh/known_hosts" -p 2222',
            )

    @unittest.skipUnless(os.name == "nt", "requires native Windows paths")
    def test_windows_rsh_without_optional_config_or_identity(self):
        with patch("locations.Path.is_file", return_value=False):
            command = build_rsh_command(None)
        self.assertIn("/.tools/cwrsync/bin/ssh.exe", command)
        self.assertNotIn(" -F ", command)
        self.assertNotIn(" -i ", command)
        self.assertIn("UserKnownHostsFile=", command)

    @unittest.skipIf(os.name == "nt", "requires POSIX local paths")
    def test_command_with_posix_paths(self):
        self.assertEqual(
            rsync_command(Location("pi:2222/recordings"), Location("/data"), update=True),
            ["rsync", "--rsh=ssh -p 2222", "--archive", "--human-readable",
             "--info=progress2", "--update", "pi:/recordings/", "/data/"],
        )

    def test_directory_slashes_are_independent_of_config_spelling(self):
        self.assertEqual(Location("user@backup:/data").rsync_arg(), "user@backup:/data/")
        self.assertEqual(Location("user@backup:/data/").rsync_arg(), "user@backup:/data/")
        local = "C:/data" if os.name == "nt" else "/data"
        self.assertEqual(Location(local).rsync_arg(), Location(f"{local}/").rsync_arg())
        if os.name == "nt":
            self.assertEqual(Location("C:/").rsync_arg(), "/cygdrive/c/")
        else:
            self.assertEqual(Location("/").rsync_arg(), "/")

    def test_pi_address_parsing(self):
        pi = Location("pi@10.0.0.2:2222")
        self.assertEqual((pi.username, pi.host, pi.port), ("pi", "10.0.0.2", 2222))
        changed = pi.with_path("/home/pi/data")
        self.assertIsNot(changed, pi)
        self.assertIsNone(pi.path)
        self.assertEqual((changed.host, changed.username, changed.port), (pi.host, pi.username, pi.port))
        self.assertEqual(changed.rsync_arg(), "pi@10.0.0.2:/home/pi/data/")
        self.assertEqual(Location("pi@10.0.0.2:2222", path_override="~/MAVRS_pi/data").rsync_arg(),
                         "pi@10.0.0.2:~/MAVRS_pi/data/")
        self.assertEqual(Location("pi@10.0.0.2:/custom/data", path_override="~/MAVRS_pi/data").rsync_arg(),
                         "pi@10.0.0.2:~/MAVRS_pi/data/")

    def test_local_path_override_and_copy(self):
        original, replacement, next_path = (
            ("C:/original", "E:/replacement", "D:/next") if os.name == "nt"
            else ("/original", "/replacement", "/next")
        )
        local = Location(original, path_override=replacement)
        self.assertEqual(local.rsync_arg(), Location(replacement).rsync_arg())
        updated = local.with_path(next_path)
        self.assertIsNot(updated, local)
        self.assertEqual(updated.local_path, Path(next_path))
        self.assertEqual(local.local_path, Path(replacement))

    def test_local_home_paths_expand_for_native_filesystem(self):
        self.assertEqual(Location("~/data").local_path, Path.home() / "data")
        self.assertEqual(Location("~").local_path, Path.home())
        original = "C:/data" if os.name == "nt" else "/data"
        self.assertEqual(Location(original, path_override="~/other").local_path, Path.home() / "other")
        self.assertEqual(Location("host:~/data").rsync_arg(), "host:~/data/")

    def test_remote_forms_and_defaults(self):
        self.assertEqual(Location("a:22").port, 22)
        camera = Location("camera.local:")
        self.assertEqual((camera.host, camera.port), ("camera.local", None))
        named_camera = Location("pi@camera.local")
        self.assertEqual((named_camera.host, named_camera.username), ("camera.local", "pi"))
        self.assertEqual((named_camera.port, named_camera.path), (None, None))
        self.assertEqual(Location("camera.local").host, "camera.local")
        self.assertEqual(Location("data").host, "data")
        self.assertEqual(Location("backup:/archive").rsync_arg(), "backup:/archive/")
        self.assertEqual(Location("user@backup:2222/archive").port, 2222)
        self.assertEqual(Location("user@backup:~/data").rsync_arg(), "user@backup:~/data/")
        home = Location("user@backup:2222:~/data")
        self.assertEqual((home.port, home.rsync_arg()), (2222, "user@backup:~/data/"))
        ipv6 = Location("user@[2001:db8::1]:/data")
        self.assertEqual(ipv6.host, "2001:db8::1")
        self.assertEqual(ipv6.ssh_host, "user@2001:db8::1")
        self.assertEqual(ipv6.rsync_arg(), "user@[2001:db8::1]:/data/")

    def test_rejects_relative_local_and_invalid_remote_specs(self):
        for value in ("data/session", "C:data", "host:relative/path", "host:~data",
                      "host:22~/data", "host::~/data", "host:22:/data",
                      "host:0/data", "host:65536/data", "user@[bad]:/data"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Location(value)
        with self.assertRaisesRegex(ValueError, "Invalid IPv6 host"):
            Location("user@[bad:host]:/data")
        if os.name == "nt":
            with self.assertRaisesRegex(ValueError, "Invalid Windows path"):
                Location("C:/data?invalid")
        with self.assertRaisesRegex(ValueError, "Remote directory must"):
            Location("backup:", path_override="relative/data")

    def test_settings_loads_typed_locations(self):
        with TemporaryDirectory() as temp, patch.object(Path, "home", return_value=Path(temp)):
            from load_settings import Settings, other_folders_save_root

        local = "C:/data" if os.name == "nt" else "/data"
        settings = Settings.model_validate({
            "local_data_path": local,
            "backup_data_path": "user@backup:/archive",
            "other_folders": {"ephys": None, "med": "user@med:/AUTO_med"},
        })
        backup_data_path = settings.backup_data_path
        if backup_data_path is None:
            self.fail("backup_data_path should be populated")
        self.assertIsInstance(settings.local_data_path.path, Path)
        self.assertIsInstance(backup_data_path.path, PurePosixPath)
        self.assertEqual(other_folders_save_root(settings)["ephys"], settings.local_data_path)
        self.assertEqual(backup_data_path.rsync_arg(), "user@backup:/archive/")
        with self.assertRaises(ValueError):
            Settings.model_validate({"local_data_path": "backup:/data", "backup_data_path": None})
        with self.assertRaises(ValueError):
            Settings.model_validate({"local_data_path": local, "backup_data_path": "backup:"})

    def test_pi_connection_uses_parsed_user_and_port(self):
        with TemporaryDirectory() as temp, patch.object(Path, "home", return_value=Path(temp)):
            from load_settings import load_pi_addresses, load_pi_connections

        with patch("load_settings.read_lines", return_value=["pi@camera.local:2222"]), patch(
            "load_settings.PiConnection"
        ) as connection:
            self.assertEqual(load_pi_addresses()[0].rsync_arg(),
                             "pi@camera.local:~/MAVRS_pi/data/")
            load_pi_connections()
        self.assertEqual(connection.call_args.kwargs["host"], "camera.local")
        self.assertEqual(connection.call_args.kwargs["user"], "pi")
        self.assertEqual(connection.call_args.kwargs["port"], 2222)
        with patch("load_settings.read_lines", return_value=["camera.local:"]), patch(
            "load_settings.PiConnection"
        ) as connection:
            load_pi_connections()
        self.assertIsNone(connection.call_args.kwargs["port"])
        with patch("load_settings.read_lines", return_value=["pi@camera.local:/custom/data"]), patch(
            "load_settings.logger.warning"
        ) as warning:
            self.assertEqual(load_pi_addresses()[0].rsync_arg(), "pi@camera.local:~/MAVRS_pi/data/")
        warning.assert_called_once_with(
            "Ignoring data path %s for Pi %s; using %s",
            PurePosixPath("/custom/data"), "pi@camera.local", "~/MAVRS_pi/data",
        )
        with patch("load_settings.read_lines", return_value=["pi@[2001:db8::1]:"]), patch(
            "load_settings.PiConnection"
        ) as connection:
            load_pi_connections()
        self.assertEqual(connection.call_args.kwargs["host"], "2001:db8::1")

    def test_pi_connection_sets_keepalive_after_opening(self):
        from fabric import Connection
        from load_settings import PiConnection

        transport = Mock()

        def open_connection(connection):
            connection.transport = transport

        with patch.object(Connection, "open", open_connection):
            PiConnection(host="camera.local").open()
        transport.set_keepalive.assert_called_once_with(30)


if __name__ == "__main__":
    unittest.main()
