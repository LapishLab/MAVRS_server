import subprocess
import os
from load_settings import load_settings
from warnings import warn

def main():
    transfer_med()
    input("Hit enter to begin Pi transfer")
    transfer_pis()

def transfer_pis():
    print("Copying data from Pi")
    server = load_settings()['computers']['server']

    pi_cmd = f"bash MAVRS_pi/transferData.sh {server['username']} {server['data_path']}"
    server_cmd = ["cssh", "piCluster", "-a", pi_cmd]
    p = subprocess.run(server_cmd)

    if p.returncode != 0:
        print(
            f"\n----WARNING!!----"
            f"\nCluster SSH failed to connect to Raspberry Pis."
            f"\n-----------------"
            )
        input("Hit enter to close window")

def transfer_med():
    print("Copying data from MED-PC")
    
    computers = load_settings()['computers']
    med = computers['med_pc']
    med_data = f"{med['username']}@{med['address']}:{med['data_path']}"
    local_data = computers['server']['data_path']
    cmd = ["rsync", "-ah","--info=progress2", med_data, local_data]
    p = subprocess.run(cmd)

    if p.returncode != 0:
        print(
            f"\n----WARNING!!----"
            f"\nMed data failed to transfer."
            f"\nCheck ethernet connections to network switch and med computer." 
            f"\nVerify WSL instance is running on med computer." 
            f"\n-----------------"
            )
    else:
        print("Med data successfully transferred")

if __name__ == "__main__":
    main()
