ENV = "XDG_RUNTIME_DIR=/run/user/$(id -u)"
UNIT = "mavrs"
SCRIPT_PATH = "/home/pi/MAVRS_pi/startExperiment.py"
PYTHON_PATH = "/home/pi/MAVRS_pi/.venv/bin/python3"

from fabric.group import SerialGroup

def is_active(c: SerialGroup) -> list[bool]:
    """Checks if the specific systemd unit is active."""
    result = c.run(f"{ENV} systemctl --user is-active {UNIT}.service", warn=True, hide=True)
    return [getattr(v, "stdout", "").strip() == "active" for v in result.values()]

def is_reachable(c: SerialGroup) -> list[bool]:
    """Checks if the hosts in the SerialGroup are reachable."""
    result = c.run("true", warn=True, hide=True)
    return [getattr(v, "ok", False) for v in result.values()]

def stop_process(c: SerialGroup):
    if not any(is_active(c)):
        print(f"{UNIT} is not running on any hosts.")
        return
    c.run(f"{ENV} systemctl --user stop {UNIT}.service", warn=True)
    if any(is_active(c)):
        raise RuntimeError(f"Failed to stop {UNIT} on one or more hosts.")

def start_process(c: SerialGroup, session: str):
    if any(is_active(c)):
        print(f"Aborting: {UNIT} is already running on one or more hosts.")
        return
    pi_cmd = f'{PYTHON_PATH} -u {SCRIPT_PATH} --session {session}'
    sysemd_cmd = f'{ENV} systemctl --user reset-failed; systemd-run --user --unit={UNIT} {pi_cmd}'
    c.run(sysemd_cmd, warn=True)
    if all(is_active(c)):
        print(f"Started {UNIT} on all Pis")
    else:
        raise RuntimeError(f"Failed to start {UNIT} on one or more Pis")
    