@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" media_setup.py
) else (
  py -3 media_setup.py
)
echo.
pause
