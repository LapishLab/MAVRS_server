# MAVRS_server
 Modular audio and video recording system for rat behavior. Code for DHCP server.

## Native Windows paths with cwRsync

Install cwRsync and add its `bin` directory to the Windows `PATH`. Open a new
terminal and check that `rsync --version` runs. Run MAVRS with native Windows
Python and set `local_data_path` in `~/MAVRS_settings/settings.yaml` to a native
Windows path, for example:

```yaml
local_data_path: "C:/data/"
backup_data_path: "user@backup-host:/path/to/backup/"
other_folders:
  ephys: "E:/ephys/"
  med_pc: "user@other-host:/data/"
```

Use forward slashes for Windows paths in YAML. MAVRS converts local drive paths
to cwRsync's `/cygdrive/c/...` form when calling `rsync`. Settings paths are
directories; MAVRS copies their contents whether or not you write a trailing
slash. Remote `user@host:/path` settings retain their host and Linux directory
path. Paths such as `/mnt/c/data/` are for WSL and must be changed to `C:/data/`
when running native Windows Python. Linux paths are unchanged.

Pi addresses use `[user@]host[:port]`, for example `pi@camera.local` or
`pi@camera.local:2222`. They default to `~/MAVRS_pi/data` for the
recording directory; an explicit path such as `pi@camera.local:/custom/data`
overrides that default. Remote directory settings can use
`user@backup-host:/archive`, `user@backup-host:2222/archive`,
`user@backup-host:~/archive`, or `user@backup-host:2222:~/archive`.
Brackets distinguish IPv6 hosts, such as
`user@[2001:db8::1]:/archive`. Local settings must be absolute paths.
Omitted usernames and ports are left to SSH configuration and defaults.
For a local directory under the server user's home, use a quoted path such as
`local_data_path: "~/data"`. A remote `host:~/data` uses the remote user's home.
