@echo off
rem First-time setup: installs the packages JY Tools needs (PySide6, pywin32).
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo [!] Python was not found.
  echo     Install Python 3.10 or newer from https://www.python.org/downloads/
  echo     and check "Add python.exe to PATH" on the first screen. Then run this file again.
  echo.
  pause
  exit /b 1
)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [!] Installation failed. Check your internet connection and try again.
  pause
  exit /b 1
)
echo.
echo Done. Double-click run_explorer.bat or run_launcher.bat to start.
pause
