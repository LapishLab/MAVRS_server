import subprocess
import sys
import unittest
from pathlib import Path


class ConsoleLoggingTests(unittest.TestCase):
    def test_paramiko_routine_messages_are_quiet(self):
        script = """
import logging
from console_logging import configure_logging

configure_logging()
logger = logging.getLogger("paramiko.transport")
logger.info("Authentication (publickey) failed.")
logger.info("Key exchange complete")
logging.getLogger("mavrs").info("Checking Pi status")
logging.getLogger().setLevel(logging.DEBUG)
logger.debug("Packet details")
logger.warning("SSH connection lost")
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertEqual(result.stdout.splitlines(), [
            "INFO: Checking Pi status",
            "WARNING: SSH connection lost",
        ])


if __name__ == "__main__":
    unittest.main()
