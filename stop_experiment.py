#!/usr/bin/env python3
from load_settings import load_pi_connections
import transfer_data
from pi_sysemd import stop_process

def main() -> None:
	stop_pis()
	transfer_data.main()

def stop_pis() -> None:
	print("stopping Pi recordings")
	print("loading pi connections")
	pis = load_pi_connections()
	stop_process(pis)

if __name__ == "__main__":
	main()
