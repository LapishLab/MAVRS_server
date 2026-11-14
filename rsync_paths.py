"""Format local paths for rsync while preserving remote rsync specifications."""

import os
import re
from pathlib import Path


_REMOTE_PATH = re.compile(r"^[^/\\:]+:")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WSL_DRIVE = re.compile(r"^/mnt/[A-Za-z](?:/|$)")


def rsync_path(path: str | Path, *, windows: bool | None = None) -> str:
    """Convert Windows paths to cwRsync paths, retaining trailing slashes.

    A remote ``host:path`` (or ``rsync://`` URL) is already in rsync's syntax
    and must not be interpreted as a local Windows path.
    """
    raw = os.fspath(path)
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return raw

    if _REMOTE_PATH.match(raw) and not _WINDOWS_DRIVE.match(raw):
        return raw

    normalized = raw.replace("\\", "/")
    if _WSL_DRIVE.match(normalized):
        raise ValueError(
            f"WSL path {raw!r} cannot be used by native Windows cwRsync; "
            "use a Windows drive path such as C:/data/ in settings.yaml"
        )
    if _WINDOWS_DRIVE.match(normalized):
        if len(normalized) < 3 or normalized[2] != "/":
            raise ValueError(f"Expected an absolute Windows drive path: {raw}")
        return f"/cygdrive/{normalized[0].lower()}{normalized[2:]}"

    # Cygwin accepts UNC shares as //server/share. Relative and already-POSIX
    # paths require no other change.
    return normalized


def rsync_command(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    update: bool = False,
    exclude: str | None = None,
    ssh_port: str | int | None = None,
    list_only: bool = False,
) -> list[str]:
    """Build an rsync command, converting only its path arguments."""
    command = ["rsync"]
    if list_only:
        command.append("--list-only")
    else:
        command.extend(("--archive", "--human-readable", "--info=progress2"))
    if update:
        command.append("--update")
    if exclude is not None:
        command.append(f"--exclude={exclude}")
    if ssh_port is not None:
        command.append(f"--rsh=ssh -p {ssh_port}")
    command.append(rsync_path(source))
    if destination is not None:
        command.append(rsync_path(destination))
    return command
