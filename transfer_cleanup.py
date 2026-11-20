"""Compare the Pi inventory with server files and request safe cleanup."""

import json
import logging
import stat
from pathlib import Path, PurePosixPath
from subprocess import CalledProcessError, run

logger = logging.getLogger(__name__)
PI_CLEANUP_SCRIPT = "~/MAVRS_pi/transfer_cleanup.py"
MTIME_TOLERANCE_NS = 10_000_000  # exFAT stores modification times in 10 ms steps.


def _pi_command(host: str, port: str | None, action: str, input_text: str | None = None) -> str:
    command = ["ssh"]
    if port is not None:
        command.extend(("-p", port))
    command.extend((host, f"python3 {PI_CLEANUP_SCRIPT} {action}"))
    try:
        result = run(
            command,
            input=input_text, capture_output=True, text=True, check=True,
        )
    except CalledProcessError as exc:
        raise RuntimeError(f"Pi {host} {action} failed: {exc.stderr.strip()}") from exc
    return result.stdout


def _server_file(root: Path, relative: str):
    path = PurePosixPath(relative)
    parts = path.parts
    if path.is_absolute() or not parts or any(part in ("", ".", "..") or part.startswith(".") for part in parts):
        return None
    current = root
    for part in parts[:-1]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(info.st_mode):
            return None
    try:
        info = (current / parts[-1]).lstat()
    except FileNotFoundError:
        return None
    return info if stat.S_ISREG(info.st_mode) else None


def eligible_files(inventory: list, server_path: str | Path) -> list:
    """Select files with a newer destination or a same-size copy within 10 ms."""
    root = Path(server_path)
    selected = []
    for relative, size, mtime_ns in inventory:
        info = _server_file(root, relative)
        if info is None:
            continue
        if info.st_mtime_ns > mtime_ns or (info.st_size == size and info.st_mtime_ns >= mtime_ns - MTIME_TOLERANCE_NS):
            selected.append([relative, size, mtime_ns])
    return selected


def cleanup_pi(host: str, port: str | None, server_path: str | Path) -> tuple[int, int]:
    inventory = json.loads(_pi_command(host, port, "inventory"))
    selected = eligible_files(inventory, server_path)
    result = json.loads(_pi_command(host, port, "delete", json.dumps(selected)))
    deleted = result["deleted"]
    if deleted != len(selected):
        logger.warning("Deleted %s of %s eligible files from %s; files changed or disappeared during cleanup",
                       deleted, len(selected), host)
    return deleted, len(inventory)
