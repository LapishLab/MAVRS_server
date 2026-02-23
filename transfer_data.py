#!/usr/bin/env python3
from subprocess import run, Popen
from load_settings import load_settings, load_pi_addresses
from pi_utilities import send_individual_pi_command
from warnings import warn
import re
from pathlib import Path

def main():
    settings = load_settings()
    if settings.other_folders:
        get_remote_folders(settings)
    transfer_pis(settings)

def transfer_pis(settings):
    print("Copying data from Pi")

    pi_names = load_pi_addresses()
    server_path = settings.local_data_path

    processes = []
    log_files = []
    for pi in pi_names:
        pi_data_path = f'/home/pi/MAVRS_pi/data/'
        pi_path = f'{pi}:{pi_data_path}'
        log = f'{server_path}/{pi}_transfer_log.txt'
        log_files.append(log)
        cmd = ['rsync', '-ah',  '--info=progress2', '--exclude=".*"',
               pi_path, server_path,
               f'--log-file={log}', '--log-file-format=""']
        proc = Popen(cmd)
        processes.append(proc)

    failed_transfers = []
    for ind, proc in enumerate(processes):
        proc.wait()
        if (proc.returncode == 0):
            print(f'\nSuccessfully transfered data from {pi_names[ind]}: Automatically deleting data')
            try:
                scanned_folders = parse_log(log_files[ind])
                scanned_folders = [f'{pi_data_path}{f}' for f in scanned_folders]
                pi_cmd = 'rm -rf ' + ' '.join(scanned_folders)
                send_individual_pi_command(pi_cmd, pi_names[ind])
            except Exception as e:
                warn(f"\nError automatically deleting data from {pi_names[ind]}: {e} \nYou will need to manually delete data from this Pi if this issue is not resolved")
        else:
            failed_transfers.append(pi_names[ind])
    if (len(failed_transfers)==0):
        print(
            f"\n-----------------------"
            f"\nAll data successfully transfered from Pis"
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

def get_remote_folders(settings):
    local_data = settings.local_data_path
    folders = settings.other_folders
    for label in folders:
        if folders[label]: # assumed to be remote
            print(f"Getting {label} folder")
            remote = f"{folders[label]}" 
            cmd = ["rsync", "-ah","--info=progress2", remote, local_data]
            run(cmd, check=True) #TODO handle, error descriptively

def parse_log(log_file):
    """
    Parses an rsync log file and returns a list of top-level files/folders scanned by rsync.
    """ 
    with open(log_file) as f:
        lines = f.readlines()
    
    # Find the line where the file list starts
    start_pat = 'receiving file list\n'
    start_line = [i for i, l in enumerate(lines) if re.search(start_pat, l)]
    if len(start_line)==0:
        raise ValueError(f"Cannot parse rsync log file: {log_file} \nCannot find starting pattern: {start_pat}")
    elif len(start_line) > 1:
        warn(f"Parsing rsync log file found multiple lines with the starting pattern, using last match: {log_file}")
    start_line = start_line[-1] + 2 # Skip the "receiving file list" line and the next line which is the root directory (./)
    lines = lines[start_line:]

    # Find the line where the file list ends, which is the summary line starting with "sent [number] bytes  received [number] bytes  total size [number]"
    stop_pat = 'sent [0-9]* bytes  received [0-9]* bytes  total size [0-9]*\n'
    stop_line = [i for i, l in enumerate(lines) if re.search(stop_pat, l)]
    if len(stop_line)==0:
        raise ValueError(f"Cannot parse rsync log file: {log_file} \nCannot find stopping pattern: {stop_pat}")
    elif len(stop_line) > 1:
        warn(f"Parsing rsync log file found multiple lines with the stopping pattern, using first match: {log_file}")
    stop_line = stop_line[0]
    lines = lines[:stop_line]

    # Parse the lines to find the top-level items
    items = [l.strip().split()[3] for l in lines] # The file/folder name is the 4th item in the line
    top_level = [Path(l).parts[0] for l in items] # Get the top-level folder (the first part of the path)
    top_level = list(set(top_level)) # Get only unique items
    return top_level

if __name__ == "__main__":
    main()
