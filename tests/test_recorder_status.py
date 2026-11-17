import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from status_checker import PiStatus, result_2_status, get_pi_statuses


class RecorderStatusTests(unittest.TestCase):
    def test_parses_partial_failure_with_component_name(self):
        result = SimpleNamespace(exited=0, stdout=json.dumps({
            "state": "partial_failure", "session": "session-one",
            "components": {"Video": {"state": "failed", "exit_code": 1},
                           "Audio": {"state": "recording", "exit_code": None}},
        }))
        health = result_2_status(result)
        self.assertEqual(health.status, PiStatus.PARTIAL_FAILURE)
        self.assertEqual(health.summary, "partial failure: Video")

    def test_unknown_response_does_not_look_stopped(self):
        self.assertEqual(result_2_status(SimpleNamespace(exited=1, stdout="")).status,
                         PiStatus.UNKNOWN)
        self.assertEqual(result_2_status(SimpleNamespace(exited=0, stdout="invalid")).status,
                         PiStatus.UNKNOWN)

    def test_status_query_uses_existing_connections(self):
        connection = SimpleNamespace(host="camera.local")
        result = SimpleNamespace(exited=0, stdout='{"state":"recording","components":{}}')
        with patch("status_checker.run_on_connections", return_value=[result]) as run:
            statuses = get_pi_statuses([connection])
        self.assertEqual(statuses["camera.local"].status, PiStatus.RUNNING)
        self.assertIn("recording_status.py", run.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
