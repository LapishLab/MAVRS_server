@echo off
set DISTRO=Ubuntu

:: Define the absolute LINUX paths to your venv and your script
set VENV_PATH=/home/lapishla/MAVRS_server/.venv/bin/python
set SCRIPT_PATH=/home/lapishla/MAVRS_server/user_gui.py

echo Running Python script in %DISTRO% using virtual environment...

wsl -d %DISTRO% %VENV_PATH% %SCRIPT_PATH%
