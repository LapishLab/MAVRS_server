import subprocess
import os
from load_settings import load_settings, load_pi_addresses
from warnings import warn
from pi_utilities import delete_pi_data

def main():
    get_remote_folders()
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
            f'\nAutomatically deleting data from Pis to free up space'
            f'\n------------------------'
            )
        delete_pi_data()
    else:
        print(
            f"\n----WARNING!!----"
            f"\nFailed to copy data from the following Pis"
            f'\n{failed_transfers}'
            f'\nDo not delete data from the Pis until this has been resolved'
            f'\n------------------------'
            )

    input("Hit enter to close window")

def get_remote_folders():
    local_data = load_settings()['local_data_destination']['data_path']
    folders = load_settings()['other_folders']
    for label in folders:
        if folders[label]: # assumed to be remote
            print(f"Getting {label} folder")
            f = folders[label]
            remote = f"{f['username']}@{f['address']}:{f['data_path']}/" #TODO check that f contains address/username/data_path

            cmd = ["rsync", "-ah","--info=progress2", remote, local_data]
            subprocess.run(cmd, check=True) #TODO handle, error descriptively

if __name__ == "__main__":
    main()
