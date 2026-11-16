# Agent guidance for MAVRS_server

## Purpose and architecture

This repository runs on the control computer for a fleet of Raspberry Pis running the sibling `MAVRS_pi` repository. It selects a shared session name, sets Pi clocks, starts and stops each Pi recorder over SSH using a user systemd unit, reports status, and collects recordings with rsync. It can also collect other data folders and back up the assembled data. Read the relevant code in both repositories when changing their shared behavior.

## Working preferences

- Write clean, readable code with clear names and straightforward control flow. Keep changes small and focused on the requested behavior.
- The user reviews all changes and personally performs all git commits. Leave changes uncommitted and describe their scope clearly.
- Keep core operations available from the command line. GUI actions should call the same underlying functions or scripts instead of implementing separate behavior.
- If the user asks why code was written a certain way, discuss the reasoning and tradeoffs. Do not treat that question alone as a request to change code.
- Mention unrelated concerns found during review separately so they can be considered for a separate commit. Do not fold them into the current change without a reason tied to the request.

## System behavior to protect

- Pi addresses, SSH ports, paths, session names, and local/remote rsync locations are configurable. Preserve those distinctions when changing command construction or file transfer.
- Starting an experiment must use the same session name across the Pis and configured other data folders. Status checks and failures should be visible to the operator.
- GPIO edges on the Pis are used to synchronize recordings with behavioral control, electrophysiology, fiber photometry, and ultrasonic playback systems. Changes to clock setting, start/stop orchestration, session naming, or transfer of timestamped files can affect that alignment. Explain the timing consequences of such changes and avoid claiming tighter synchronization than the code establishes.
- Treat recording data as valuable. Keep transfer and cleanup behavior deliberate, and preserve the existing checks that select which Pi files can be deleted after collection.
