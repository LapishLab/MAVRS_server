#!/usr/bin/env python3
from subprocess import run, Popen, PIPE
from load_settings import load_settings, load_pi_addresses, Settings
from pi_utilities import send_individual_pi_command
from warnings import warn
from pathlib import Path
from typing import List, Union
from datetime import datetime

def main() -> None:
    settings = load_settings()
    if settings.other_folders:
        get_remote_folders(settings)
    transfer_pis(settings)

def transfer_pis(settings: Settings) -> None:
    print("Copying data from Pi")

    pi_names = load_pi_addresses()
    server_path = settings.local_data_path

    processes: List[tuple[Popen, str, str]] = []
    for pi in pi_names:
        pi_data_path = f'/home/pi/MAVRS_pi/data/'
        pi_path = f'{pi}:{pi_data_path}'
        # Use --out-format to print transferred file/dir names to stdout
        cmd = [
            'rsync', '-ah', '--info=progress2', '--exclude=.*',
            f"--out-format=%n",
            pi_path, server_path
        ]
        proc = Popen(cmd, stdout=PIPE, stderr=PIPE, text=True)
        processes.append((proc, pi, pi_data_path))

    failed_transfers: List[str] = []
    for proc, pi_name, pi_data_path in processes:
        stdout, stderr = proc.communicate()
        if proc.returncode == 0:
            print(f'\nSuccessfully transfered data from {pi_name}: Automatically deleting data')
            try:
                scanned_folders = parse_rsync_stdout(stdout)
                scanned_folders = [f'{pi_data_path}{f}' for f in scanned_folders]
                if scanned_folders:
                    pi_cmd = 'rm -rf ' + ' '.join(scanned_folders)
                    send_individual_pi_command(pi_cmd, pi_name)
            except Exception as e:
                warn(f"\nError automatically deleting data from {pi_name}: {e} \nYou will need to manually delete data from this Pi if this issue is not resolved")
        else:
            warn(f"Rsync failed for {pi_name}: {stderr}")
            failed_transfers.append(pi_name)
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

def get_remote_folders(settings: Settings) -> None:
    local_data = settings.local_data_path
    folders = settings.other_folders or {}
    for label in folders:
        val = folders[label]
        if val:  # assumed to be remote
            print(f"Getting {label} folder")
            remote = f"{val}"
            cmd = ["rsync", "-ah","--info=progress2", remote, local_data]
            run(cmd, check=True)  # TODO handle, error descriptively

def parse_rsync_stdout(output: str) -> List[str]:
    """
    Parse rsync stdout produced with `--out-format=%n` and return unique top-level paths.
    """
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    # Remove any surrounding quotes
    items = [l.strip('"') for l in lines]
    top_level = []
    for it in items:
        try:
            first = Path(it).parts[0]
        except Exception:
            continue
        if first not in top_level:
            top_level.append(first)
    return top_level

if __name__ == "__main__":
    main()
