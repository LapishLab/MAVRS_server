import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config import ENV, UNIT
from pi_sysemd import stop_process


class StopProcessTests(unittest.TestCase):
    def test_ignores_only_unloaded_unit_response(self):
        connections = [SimpleNamespace(host="camera-a"), SimpleNamespace(host="camera-b")]
        results = [
            SimpleNamespace(exited=1, stdout="", stderr="Failed to stop mavrs.service: Unit mavrs.service not loaded.\n"),
            SimpleNamespace(exited=0, stdout="", stderr=""),
        ]

        with patch("pi_sysemd.run_on_connections", return_value=results) as run, patch(
            "pi_sysemd.logger.warning"
        ) as warning:
            stop_process(connections)

        run.assert_called_once_with(connections, f"{ENV} systemctl --user stop {UNIT}.service", warn=True, hide=True)
        warning.assert_not_called()

    def test_reports_other_stop_failures_with_pi_name(self):
        connections = [SimpleNamespace(host="camera-a"), SimpleNamespace(host="camera-b")]
        results = [
            SimpleNamespace(exited=1, stdout="", stderr="Failed to connect to bus"),
            OSError("SSH connection lost"),
        ]

        with patch("pi_sysemd.run_on_connections", return_value=results), patch(
            "pi_sysemd.logger.warning"
        ) as warning:
            stop_process(connections)

        self.assertEqual(warning.call_count, 2)
        self.assertEqual(warning.call_args_list[0].args, ("Could not stop %s on %s: %s", UNIT, "camera-a", "Failed to connect to bus"))
        self.assertEqual(warning.call_args_list[1].args, ("Could not stop %s on %s: %s", UNIT, "camera-b", results[1]))


if __name__ == "__main__":
    unittest.main()
