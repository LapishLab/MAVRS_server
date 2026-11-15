@echo off
cd /d "%~dp0..\..\.."
".venv\Scripts\python.exe" "stop_experiment.py"
pause
