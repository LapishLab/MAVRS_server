import subprocess
from load_settings import load_settings

def main():
    stop_pis()
    move_med()

def stop_pis():
    print("stopping Pi recordings")

    cmd = ["cssh", "piCluster","-a", "bash MAVRS_pi/stopExperiment.sh"]
    subprocess.run(cmd, check=True)

def move_med():
    print("moving med file to archive")
    med = load_settings()['computers']['med_pc']
    temp = med['data_path_temp']
    archive = med['data_path']
    pc = f"{med['username']}@{med['address']}"

    med_cmd = f"find /{temp}/ -maxdepth 1 -mindepth 1 -exec mv {{}} {archive}  \;"
    
    cmd = ["ssh", pc, med_cmd]
    p = subprocess.run(cmd)

    if p.returncode != 0:
        print(
            f"\n----WARNING!!----"
            f"\nMoving med data from NOW folder to archive folder failed."
            f"\nCheck ethernet connections to network switch and med computer." 
            f"\nVerify WSL instance is running on med computer." 
            f"\n-----------------"
            )

if __name__ == "__main__":
    main()
