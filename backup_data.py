from load_settings import load_settings
import subprocess

def backup_data():
    print("backing up data")
    local_path = load_settings()['local_data_path']
    backup_data = load_settings()['backup_data_path']

    cmd = ["rsync", "-ah","--info=progress2", local_path, backup_data]
    p = subprocess.run(cmd)

    if p.returncode != 0:
        print(
            f"\n----WARNING!!----"
            f"\nRsyncing to Datastar failed!"
            f"\n-----------------"
            )
    else:
        print(
            f"\n---Transfer Complete---"
            f"\nData has been backed up to Datastar"
            f"\n-----------------------"
        )
    input("\nHit enter to close window")

if __name__ == "__main__":
    backup_data()