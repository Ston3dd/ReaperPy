@echo off
setlocal
cd /d "%~dp0"
title ReaperPy - EXE bauen
set "PY=py -3"
%PY% --version >nul 2>&1 || set "PY=python"
echo [..] Pakete installieren
%PY% -m pip install --upgrade pyinstaller keystone-engine capstone pillow || goto :fail
echo [..] Versionsinfo schreiben
%PY% buildtools.py || goto :fail
echo [..] baue Ordner-Version aus ReaperPy.spec (alle Module, Icon, Assets, Versionsinfo)
%PY% -m PyInstaller --noconfirm --clean ReaperPy.spec || goto :fail
for /f %%V in ('%PY% -c "import version; print(version.__version__)"') do set "VER=%%V"
echo [..] packe dist\ReaperPy_v%VER%_win64.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\ReaperPy\*' -DestinationPath 'dist\ReaperPy_v%VER%_win64.zip' -Force" || goto :fail
echo.
echo [OK] fertig:
echo      dist\ReaperPy\ReaperPy.exe
echo      dist\ReaperPy_v%VER%_win64.zip
echo      (bewusst KEIN --onefile: Konfiguration, Profile und Logs liegen neben der EXE)
pause
exit /b 0
:fail
echo [FEHLER] Build fehlgeschlagen
pause
exit /b 1
