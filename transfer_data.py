import subprocess
import os
from load_settings import load_settings, load_pi_addresses
from warnings import warn

def main():
    transfer_med()
    input("Hit enter to begin Pi transfer")
    transfer_pis()

def transfer_pis():
    print("Copying data from Pi")
    
    pi_names = load_pi_addresses()
    server_path = load_settings()['computers']['server']['data_path']

    processes = []
    for pi in pi_names:
        pi_path = f'{pi}:/home/pi/MAVRS_pi/data/'
        cmd = ['rsync', '-ah',  '--info=progress2', '--exclude=".*"', pi_path, server_path]
        proc = subprocess.Popen(cmd)
        processes.append(proc)

    failed_transfers = []
    for ind, proc in enumerate(processes):
        proc.wait()
        if (proc.returncode != 0):
            failed_transfers.append(pi_names[ind])
    if (len(failed_transfers)==0):
        print(
            f"\n-----------------------"
            f"\nAll data successfully transfered from Pis"
            f'\nYou can safely delete data from Pis'
            f'\n------------------------'
            )
    else:
        print(
            f"\n----WARNING!!----"
            f"\nFailed to copy data from the following Pis"
            f'\n{failed_transfers}'
            f'\nDo not delete data from the Pis until this has been resolved'
            f'\n------------------------'
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
