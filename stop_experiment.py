import subprocess
from load_settings import load_settings
import transfer_data

def main():
    stop_pis()
    transfer_data.main()

def stop_pis():
    print("stopping Pi recordings")

    cmd = ["cssh", "piCluster","-a", "bash MAVRS_pi/stopExperiment.sh"]
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    main()
