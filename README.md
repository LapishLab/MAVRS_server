# MAVRS_server
 Modular audio and video recording system for rat behavior. Code for DHCP server.

## Recorder status

The GUI shows each Pi as recording, starting, partially failed, failed,
stopped, unreachable, or unknown. Expand a Pi row to see the enabled GPIO,
Audio, and Video recorder states. A partial failure names the failed recorder;
healthy recorders continue until the experiment is stopped. Double-click a Pi
or component row to open that Pi's journal log. `python status_checker.py`
prints the same status at the command line.

Deploy the matching `MAVRS_pi` code to each Pi before using this server status
checker. An older Pi without `recording_status.py` appears as unknown. Status
checks detect a recorder that exits or fails to become ready within 60 seconds;
they do not detect a live process that has stopped producing useful data.

On first launch, MAVRS creates `~/MAVRS_settings` and copies the missing
`settings.yaml`, `pi_addresses.txt`, `experiment_names.txt`, and
`mavrs_pi_config.yaml` files from `setup/config_templates`. Existing files are
preserved. The default settings use `~/MAVRS_data` on both Windows and Linux;
MAVRS creates that directory with
the new settings file. Edit `settings.yaml` to use your intended data drive.
The GUI's **Preferences > Data Paths** dialog can edit the local data path,
backup destination, and other folders. A blank other-folder path uses the local
data path; a blank backup destination leaves backup unconfigured.
**Preferences > Pi fleet Settings** opens a window for
`~/MAVRS_settings/mavrs_pi_config.yaml`. If missing, MAVRS copies
`setup/config_templates/mavrs_pi_config.yaml` there. Open the file in your
system editor, save changes, then deploy to the selected Pis. The table shows
addresses and comments from `pi_addresses.txt`; active Pis start selected, while
commented-out Pis start unselected. The header checkbox selects or clears all
valid addresses. Each Pi reads the file as `~/mavrs_pi_config.yaml` when
recording processes start.

## Native Windows paths with cwRsync

Install cwRsync with `setup/install_cwrsync.ps1`. MAVRS uses the executables
under `.tools/cwrsync/bin` on Windows. Run MAVRS with native Windows
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

## Post-session scripts

Add labeled command lists to `post_session_scripts` in
`~/MAVRS_settings/settings.yaml`. These commands run when stopping an
experiment, after its data collection finishes. Running `transfer_data.py`
directly only collects data. For example, to run `med_handling` with its own
virtual environment:

```yaml
post_session_scripts:
  Med:
    - '~/Documents/GitHub/med_handling/.venv/Scripts/python.exe'
    - '~/Documents/GitHub/med_handling/handling.py'
    - '{local_data_directory}'
```

The first item is the executable; the rest are separate arguments. Commands
can run any local program. Use forward slashes or single-quoted backslash
paths in Windows YAML. `{local_data_directory}` is replaced with the configured
local data path as a single argument, including paths with spaces. A leading
`~` in any command item expands to the current user's home directory. Commands run
in settings order, and their stdout and stderr print in the transfer terminal.
They inherit MAVRS's working directory. A failed command is reported and does
not prevent later commands from running. Commands also run after a transfer or
Pi cleanup failure, once all transfer attempts have finished; check the
transfer warnings before relying on the collected data. Existing settings
files can omit this field; the default is an empty mapping.

## Video timestamp repair after stopping

After transfer attempts, **Stop Experiment** runs the bundled
`video_repair.repair_directory` on `local_data_path`, before the configured
post-session commands. It examines every `.mp4` below that directory, repairs
each video in place using its matching `.pts` camera timestamps, and skips
videos already marked by a matching `.pts.bak` file. The repair prints progress
in the stop terminal and writes `repair_report.csv` in the local data directory.
Per-video errors are appended to `repair_error.log`; other videos and
post-session commands still run. Any repair failure gives the stop command a
failure exit status.

Successful repair replaces the original MP4 and `.pts` files. The original
`.pts` is saved beside the video as `.pts.bak`, and original packet timestamps
are saved as `.mp4.timestamps.csv.bak`; the original MP4 bytes are not kept.
The repair accepts single-stream H.264 videos without B-frames. It changes
frame order when camera timestamps are out of order, so frame-indexed labels
made before repair may need remapping. Repair runs after recording has stopped
and does not change capture timing or the Pi clock.

On a Windows domain account, cwRsync may pause while looking up account groups.
The installer also caches the current account and groups under
`.tools/cwrsync/etc`. When MAVRS starts, it checks the signed-in Windows account
and group IDs and refreshes the cache if they changed. Normal checks are quick;
a refresh can take a few minutes. The cache is local to this machine and is not
committed to the repository.

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
