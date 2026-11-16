import unittest
from unittest.mock import patch

from rsync_paths import Location
from transfer_data import copy_to_pi_home


class PiSettingsTransferTests(unittest.TestCase):
    def test_copy_uses_new_settings_filename(self):
        pi = Location("pi@camera.local:2222")
        with patch("transfer_data.load_pi_addresses", return_value=[pi]), patch("transfer_data.run") as run:
            run.return_value.returncode = 0
            copy_to_pi_home()

        command = run.call_args.args[0]
        self.assertTrue(command[-2].endswith("/pi_settings.yaml"))
        self.assertIn("--rsh=ssh -p 2222", command)
        self.assertEqual(command[-1], "pi@camera.local:~/")


if __name__ == "__main__":
    unittest.main()
