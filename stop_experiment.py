#!/usr/bin/env python3
from load_settings import load_pi_connections, load_settings
import transfer_data
from pi_sysemd import stop_process
from console_logging import configure_logging


def main() -> bool:
	pis = load_pi_connections()
	stop_process(pis)
	settings = load_settings()
	if settings.transfer_on_stop:
		return transfer_data.main(settings)
	return True


if __name__ == "__main__":
	configure_logging()
	raise SystemExit(0 if main() else 1)
