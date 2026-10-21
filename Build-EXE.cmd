@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 py -3 -m venv .venv
 if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt "pyinstaller>=6,<7"
if errorlevel 1 goto failed
set "ORBIT_PACKAGE_MODE=--onedir"
if /i "%~1"=="--onefile" set "ORBIT_PACKAGE_MODE=--onefile"
set "ORBIT_MEDIA_FLAGS="
if exist "bin\ffmpeg.exe" if exist "bin\ffprobe.exe" set ORBIT_MEDIA_FLAGS=--add-binary "bin\ffmpeg.exe;bin" --add-binary "bin\ffprobe.exe;bin"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean %ORBIT_PACKAGE_MODE% --windowed --name OrbitDrop --version-file version_info.txt --collect-all pillow_heif --collect-all pymupdf --collect-all av --collect-all yt_dlp --collect-all yt_dlp_ejs --add-data "README.md;." %ORBIT_MEDIA_FLAGS% orbitdrop.py
if errorlevel 1 goto failed
echo.
echo Fertig. Ausgabe im Ordner dist.
echo Bei Ordner-Paket: den GESAMTEN Ordner dist\OrbitDrop weitergeben.
echo Python ist fuer den Empfaenger nicht erforderlich.
pause
exit /b 0
:failed
echo.
echo Build fehlgeschlagen. Fehlermeldung oberhalb pruefen.
pause
exit /b 1
