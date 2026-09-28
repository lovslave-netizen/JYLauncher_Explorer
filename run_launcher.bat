@echo off
rem Starts JY Launcher without a console window.
cd /d "%~dp0"
start "" pythonw JYLauncher.py %*
