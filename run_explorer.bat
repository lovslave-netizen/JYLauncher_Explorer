@echo off
rem Starts JY Explorer without a console window.
cd /d "%~dp0"
start "" pythonw JYExplorer.py %*
