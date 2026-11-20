"""Parse local and remote locations and format them for rsync."""

import ipaddress
import logging
import os
import re
import subprocess
from copy import copy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WSL_DRIVE = re.compile(r"^/mnt/[A-Za-z](?:/|$)")
_CWRSYNC_BIN = Path(__file__).resolve().parent / ".tools" / "cwrsync" / "bin"


def _refresh_cwrsync_accounts() -> None:
    """Refresh the local account cache when the Windows login changes."""
    if os.name != "nt" or not (_CWRSYNC_BIN / "rsync.exe").is_file():
        return
    script = Path(__file__).resolve().parent / "setup" / "cache_cwrsync_accounts.ps1"
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            capture_output=True, text=True, check=False,
        )
    except OSError as exc:
        logging.warning("Could not check the cwRsync account cache: %s", exc)
        return
    if result.returncode != 0:
        logging.warning("Could not refresh the cwRsync account cache: %s", result.stderr.strip())


_refresh_cwrsync_accounts()

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


def local_path_for_rsync(path: str | Path, *, windows: bool | None = None) -> str:
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

    def rsync_arg(self, *, is_file: bool = False) -> str:
        if self.path is None:
            raise ValueError("An rsync path is required")
        if self.host is None:
            argument = local_path_for_rsync(str(self.path))
        else:
            hostname = f"[{self.host}]" if ":" in self.host else self.host
            host = f"{self.username}@{hostname}" if self.username else hostname
            argument = f"{host}:{self.path.as_posix()}"
        if not is_file and not argument.endswith("/"):
            argument += "/"
        return argument

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
    source_is_file: bool = False,
    update: bool = False,
    exclude: str | None = None,
    summarize_files: bool = False,
) -> list[str]:
    """Build an rsync command, converting only its path arguments."""
    port  = get_port([source, destination])
    rsh = build_rsh_command(port)

    rsync_executable = str(_CWRSYNC_BIN / "rsync.exe") if os.name == "nt" else "rsync"
    command = [rsync_executable, rsh]
    if exclude is not None:
        command.append(f"--exclude={exclude}")
    if destination is None:
        command.append("--list-only")     
    else:
        command.extend(("--archive", "--human-readable"))
        if summarize_files:
            command.extend(("--out-format=%i %b", "--outbuf=L"))
        else:
            command.append("--info=progress2")
        if update:
            command.append("--update") 

    source_str = source.rsync_arg(is_file=source_is_file)
    command.append(source_str)
    if destination is not None:
        command.append(destination.rsync_arg())
    return command


def build_rsh_command(port: int|None) -> str:
    """Build the ssh portion of the rsync command."""
    ssh_command = "ssh"
    if os.name == "nt":
        ssh_command = f'"{local_path_for_rsync(_CWRSYNC_BIN / "ssh.exe")}"'
        ssh_files = Path.home() / ".ssh"
        config = ssh_files / "config"
        if config.is_file():
            ssh_command += f' -F "{local_path_for_rsync(config)}"'
        identity = ssh_files / "id_ed25519"
        if identity.is_file():
            ssh_command += f' -i "{local_path_for_rsync(identity)}"'
        known_hosts = ssh_files / "known_hosts"
        ssh_command += f' -o "UserKnownHostsFile={local_path_for_rsync(known_hosts)}"'
    if port is not None:
        ssh_command += f" -p {port}"
    return f"--rsh={ssh_command}"


def get_port(locations: list[Location | None]) -> int | None:
    """Get the port number from the source or destination Location."""
    for loc in locations:
        if loc is not None and loc.port is not None:
            return loc.port
    return None
