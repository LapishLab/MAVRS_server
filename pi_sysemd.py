ENV = "XDG_RUNTIME_DIR=/run/user/$(id -u)"
UNIT = "mavrs"
SCRIPT_PATH = "/home/pi/MAVRS_pi/startExperiment.py"
PYTHON_PATH = "/home/pi/MAVRS_pi/.venv/bin/python3"

from fabric.group import ThreadingGroup
from typing import Optional
from load_settings import load_pi_connections

def is_active(c: Optional[ThreadingGroup] = None) -> list[bool]:
    """Checks if the specific systemd unit is active."""
    if c is None:
        c = load_pi_connections()
    result = c.run(f"{ENV} systemctl --user is-active {UNIT}.service", warn=True, hide=True, timeout=2)
    return [getattr(v, "stdout", "").strip() == "active" for v in result.values()]

def is_reachable(c: Optional[ThreadingGroup] = None) -> list[bool]:
    """Checks if the hosts in the SerialGroup are reachable."""
    if c is None:
        c = load_pi_connections()
    result = c.run("true", warn=True, hide=True, timeout=5)
    return [getattr(v, "ok", False) for v in result.values()]

def stop_process(c: ThreadingGroup):
    print("checking if pis are active")
    if not any(is_active(c)):
        print(f"{UNIT} is not running on any hosts.")
        return
    print("Sending stop command to Pis")
    c.run(f"{ENV} systemctl --user stop {UNIT}.service", warn=True)
    print("Double Checking that Pis have stopped")
    if any(is_active(c)):
        raise RuntimeError(f"Failed to stop {UNIT} on one or more hosts.")

def start_process(c: ThreadingGroup, session: str):
    print("checking if pis are active")
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

def stream_logs(c: Optional[ThreadingGroup] = None):
    """Stream journal logs for `UNIT` from each host in the ThreadingGroup.

    This spawns a thread per host and prints each log line prefixed with the host.
    Interrupt with Ctrl-C to stop streaming.
    """
    if c is None:
        from load_settings import load_pi_connections
        c = load_pi_connections()
    c.run(f"{ENV} journalctl --user -u {UNIT}.service -f --no-pager", warn=True)

if __name__ == "__main__":
    print("Checking if Pis are reachable...")
    is_reachable()
    print("Checking if Pis are active...")
    is_active()
    print("Streaming logs...")
    stream_logs()
