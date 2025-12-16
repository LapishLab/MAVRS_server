#!/usr/bin/env python3
import transfer_data
from pi_utilities import send_pi_command

def main():
    stop_pis()
    transfer_data.main()

def stop_pis():
    print("stopping Pi recordings")
    send_pi_command("bash MAVRS_pi/stopExperiment.sh")

if __name__ == "__main__":
    main()
