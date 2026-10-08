@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup_demo.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" demo_app.py --port 8020 --open
pause
