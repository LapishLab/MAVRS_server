"""Format local paths for rsync while preserving remote rsync specifications."""

import ipaddress
import os
import re
from copy import copy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WSL_DRIVE = re.compile(r"^/mnt/[A-Za-z](?:/|$)")
_REMOTE_SPEC = re.compile(
    r"""
    ^(?:(?P<username>[^@/:]+)@)?       # Optional SSH user
    (?P<host>\[[^\]]*:[^\]]*\]|[^@/:\\\[\]]+)  # Hostname or bracketed IPv6
    (?:
        :(?=(?:[0-9]+(?:/|:~|$)|/|~|$))  # Port/directory follows a colon
        (?P<port>[0-9]+)?                  # Optional SSH port
        :?                                 # Separator before ~ when port is set
        (?P<directory>/.*|~(?:/.*)?)?     # Absolute or home directory
    )?$
    """,
    re.VERBOSE,
)


def rsync_path(path: str | Path, *, windows: bool | None = None) -> str:
    """Convert a local Windows path to cwRsync syntax, retaining trailing slashes."""
    raw = os.fspath(path)
    if windows is None:
        windows = os.name == "nt"
    if not windows:
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


@dataclass(frozen=True, init=False)
class Location:
    """Parse a local path or SSH location, keeping its path in native form."""

    path: Path | PurePosixPath | None
    host: str | None = None
    username: str | None = None
    port: int | None = None

    def __init__(self, value: str | Path, *, path_override: str | Path | PurePosixPath | None = None):
        username, host, port, path_text = self._parse(value)
        if path_override is not None:
            path_text = str(path_override)
        path: Path | PurePosixPath | None
        if host is None:
            if path_text is None:
                raise ValueError(f"Local locations require a directory path: {value!r}")
            path = self._validated_local_path(path_text)
        else:
            host = self._validated_host(host)
            path = PurePosixPath(path_text) if path_text is not None else None
            self._validate_remote_path(path)
        if port is not None and not 1 <= port <= 65535:
            raise ValueError(f"SSH port must be between 1 and 65535: {port}")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "username", username)
        object.__setattr__(self, "port", port)

    @staticmethod
    def _parse(value: str | Path) -> tuple[str | None, str | None, int | None, str | None]:
        """Return raw components; None denotes a pathless remote host."""
        raw = str(value)
        local_path = Path(raw).expanduser()
        if local_path.is_absolute():
            return None, None, None, str(local_path)

        match = _REMOTE_SPEC.fullmatch(raw)
        if match is None:
            raise ValueError(f"Expected an absolute local path or a remote host: {raw!r}")

        host = match["host"]
        if host.startswith("["):
            host = host[1:-1]
        port = int(match["port"]) if match["port"] else None
        return match["username"], host, port, match["directory"]

    @staticmethod
    def _validated_local_path(value: str) -> Path:
        raw = str(value)
        local_path = Path(raw).expanduser()
        if not local_path.is_absolute():
            raise ValueError(f"Local path is not absolute on this computer: {raw!r}")
        if os.name == "nt":
            if os.path.isreserved(raw):
                raise ValueError(f"Invalid Windows path: {raw!r}")
        return local_path

    @staticmethod
    def _validated_host(host: str) -> str:
        if ":" in host:
            try:
                ipaddress.IPv6Address(host)
            except ipaddress.AddressValueError as exc:
                raise ValueError(f"Invalid IPv6 host: {host!r}") from exc
        elif any(char in host for char in "/\\ "):
            raise ValueError(f"Invalid hostname: {host!r}")
        return host

    @staticmethod
    def _validate_remote_path(path: PurePosixPath | None) -> None:
        if path is not None:
            valid = path.is_absolute() or str(path) == "~" or str(path).startswith("~/")
            if not valid:
                raise ValueError(f"Remote directory must be absolute or start with ~/: {path}")

    def with_path(self, path: str) -> "Location":
        new_path: Path | PurePosixPath
        if self.host is None:
            new_path = self._validated_local_path(path)
        else:
            remote_path = PurePosixPath(path)
            self._validate_remote_path(remote_path)
            new_path = remote_path
        updated = copy(self)
        object.__setattr__(updated, "path", new_path)
        return updated

    @property
    def ssh_host(self) -> str:
        if self.host is None:
            raise ValueError("Local locations have no SSH host")
        return f"{self.username}@{self.host}" if self.username else self.host

    @property
    def local_path(self) -> Path:
        if self.host is not None or not isinstance(self.path, Path):
            raise ValueError("This location is not a local directory")
        return self.path

    def rsync_arg(self) -> str:
        if self.path is None:
            raise ValueError("An rsync directory needs a path")
        if self.host is None:
            local_path = str(self.path)
            return rsync_path(local_path if local_path.endswith(("/", "\\")) else f"{local_path}/")
        hostname = f"[{self.host}]" if ":" in self.host else self.host
        host = f"{self.username}@{hostname}" if self.username else hostname
        return f"{host}:{self.path.as_posix().rstrip('/')}/"

    def __str__(self) -> str:
        if self.host is None:
            return str(self.path)
        hostname = f"[{self.host}]" if ":" in self.host else self.host
        host = f"{self.username}@{hostname}" if self.username else hostname
        if self.path is None:
            return f"{host}:{self.port or ''}"
        path = self.path.as_posix()
        if self.port is None:
            return f"{host}:{path}"
        separator = ":" if path.startswith("~") else ""
        return f"{host}:{self.port}{separator}{path}"


def rsync_command(
    source: Location,
    destination: Location | None = None,
    *,
    update: bool = False,
    exclude: str | None = None,
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
    ports = {location.port for location in (source, destination) if location is not None and location.port is not None}
    if len(ports) > 1:
        raise ValueError("An rsync transfer cannot use two different SSH ports")
    if ports:
        command.append(f"--rsh=ssh -p {ports.pop()}")
    command.append(source.rsync_arg())
    if destination is not None:
        command.append(destination.rsync_arg())
    return command
