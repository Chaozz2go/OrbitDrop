@echo off
setlocal
cd /d "%~dp0"
if not exist ".build-venv\Scripts\python.exe" (
 py -3.12 -m venv .build-venv
 if errorlevel 1 goto failed
)
".build-venv\Scripts\python.exe" -m pip install --only-binary=:all: -r requirements-dev.txt "pyinstaller>=6,<7"
if errorlevel 1 goto failed
".build-venv\Scripts\python.exe" -c "from media_setup import install_media; install_media()"
if errorlevel 1 goto failed
".build-venv\Scripts\python.exe" -c "from ocr_data import install_languages; install_languages('tessdata')"
if errorlevel 1 goto failed
".build-venv\Scripts\python.exe" windows_build.py %1
if errorlevel 1 goto failed
echo Fertig. Ausgabe unter dist\release. Python ist beim Empfaenger nicht erforderlich.
pause
exit /b 0
:failed
echo Build fehlgeschlagen. Python 3.12 x64, Inno Setup 6 und Meldung oberhalb pruefen.
pause
exit /b 1
