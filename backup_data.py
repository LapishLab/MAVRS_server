#!/usr/bin/env python3
import logging
from load_settings import load_settings
from subprocess import run
from locations import rsync_command
from console_logging import configure_logging

logger = logging.getLogger(__name__)

def backup_data() -> None:
	logger.info("Backing up data")
	settings = load_settings()
	local_path = settings.local_data_path
	backup_path = settings.backup_data_path

	if not backup_path:
		raise RuntimeError("Missing required setting: 'backup_data_path'")

	cmd = rsync_command(local_path, backup_path, update=True)
	p = run(cmd)

	if p.returncode != 0:
		logger.warning("Backup rsync to %s failed with status %s", backup_path, p.returncode)
	else:
		logger.info("Data has been backed up to %s", backup_path)

if __name__ == "__main__":
	configure_logging()
	backup_data()
