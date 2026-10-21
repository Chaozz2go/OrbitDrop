@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto dependencies
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.10 oder neuer fehlt. Bitte von https://www.python.org/downloads/windows/ installieren.
  echo Anschliessend Start.cmd erneut starten.
  pause
  exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 goto failed
:dependencies
if exist ".venv\requirements.installed.txt" (
  fc /b requirements.txt ".venv\requirements.installed.txt" >nul 2>&1
  if not errorlevel 1 goto launch
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
copy /y requirements.txt ".venv\requirements.installed.txt" >nul
:launch
".venv\Scripts\python.exe" orbitdrop.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Start fehlgeschlagen. Bitte den Fehler oberhalb kopieren.
pause
exit /b 1
