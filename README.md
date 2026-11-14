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
to cwRsync's `/cygdrive/c/...` form when calling `rsync`; remote `host:/path`
settings are passed through. Keep the trailing slash if you want rsync to copy
the contents of a directory. Paths such as `/mnt/c/data/` are for WSL and must
be changed to `C:/data/` when running native Windows Python. Linux paths are
unchanged.
