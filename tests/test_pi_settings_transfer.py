from subprocess import CompletedProcess
import unittest
from unittest.mock import patch

from locations import Location
from transfer_data import copy_to_pi_home


class PiSettingsTransferTests(unittest.TestCase):
    def test_copy_uses_settings_filename_and_configured_ssh_port(self):
        pi = Location("pi@camera.local:2222")
        with patch("transfer_data.load_pi_addresses", return_value=[pi]), patch("transfer_data.run") as run:
            run.return_value.returncode = 0
            results = copy_to_pi_home()

        self.assertEqual(results, [(pi, None)])
        command = run.call_args.args[0]
        self.assertTrue(command[1].startswith("--rsh="))
        self.assertTrue(command[1].endswith(" -p 2222"))
        self.assertTrue(command[-2].endswith("/mavrs_pi_config.yaml"))
        self.assertEqual(command[-1], "pi@camera.local:~/")

    def test_copy_only_selected_pis_and_report_each_failure(self):
        selected = [Location("pi@one.local"), Location("pi@two.local")]
        with patch("transfer_data.load_pi_addresses") as load_pis, patch(
            "transfer_data.run", side_effect=[
                CompletedProcess([], 23, stderr="SSH failed"),
                OSError("rsync unavailable"),
            ]
        ) as run:
            results = copy_to_pi_home(selected)

        load_pis.assert_not_called()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(results, [(selected[0], "SSH failed"), (selected[1], "rsync unavailable")])


if __name__ == "__main__":
    unittest.main()
