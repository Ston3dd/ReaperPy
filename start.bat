@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title ReaperPy Launcher
echo.
echo  === ReaperPy Launcher ===
echo.

rem ---------- 1. Python suchen ----------
set "PYCMD="
python --version >nul 2>&1
if not errorlevel 1 set "PYCMD=python"
if not defined PYCMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD goto :nopython

rem ---------- 2. Version pruefen (min. 3.8) ----------
%PYCMD% -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 8) else 1)" >nul 2>&1
if errorlevel 1 goto :oldpython
set "PYVER=?"
for /f "tokens=2" %%V in ('%PYCMD% --version 2^>^&1') do set "PYVER=%%V"
echo [OK] Python %PYVER%

rem ---------- 3. tkinter pruefen ----------
%PYCMD% -c "import tkinter" >nul 2>&1
if errorlevel 1 goto :notk
echo [OK] tkinter

rem ---------- 4. pip pruefen ----------
%PYCMD% -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [..] pip fehlt - versuche ensurepip
    %PYCMD% -m ensurepip --upgrade >nul 2>&1
)
%PYCMD% -m pip --version >nul 2>&1
if errorlevel 1 goto :nopip

rem ---------- 5. requirements.txt abarbeiten ----------
set "REQ=%~dp0requirements.txt"
set "FAILED=0"
if not exist "%REQ%" (
    echo [..] keine requirements.txt - Paketpruefung uebersprungen
    goto :run
)
for /f "usebackq eol=# tokens=* delims=" %%L in ("%REQ%") do call :check "%%L"
if "%FAILED%"=="1" (
    echo.
    echo [!!] Einige Pakete konnten nicht installiert werden - ReaperPy startet trotzdem.
    echo      Ohne keystone-engine wird der Assembler der PS5 genutzt, ohne capstone
    echo      fehlt der Disassembler, ohne pillow zeigt die Bibliothek nur Initialen.
)

rem ---------- 6. Starten ----------
:run
if not exist "%~dp0gui.py" (
    echo [FEHLER] gui.py nicht gefunden in %~dp0
    pause
    exit /b 1
)
echo.
echo [OK] starte gui.py ...
echo.
%PYCMD% "%~dp0gui.py"
if errorlevel 1 (
    echo.
    echo [FEHLER] ReaperPy wurde mit Fehler beendet ^(Code %errorlevel%^).
    pause
)
exit /b 0

:nopython
echo [FEHLER] Python wurde nicht gefunden.
echo          Bitte Python 3.8 oder neuer von https://www.python.org/downloads/ installieren
echo          und beim Setup "Add python.exe to PATH" anhaken.
echo          ^(Der "python"-Alias des Microsoft Store zaehlt nicht.^)
pause
exit /b 1

:oldpython
echo [FEHLER] Python ist zu alt - benoetigt wird 3.8 oder neuer.
%PYCMD% --version
pause
exit /b 1

:notk
echo [FEHLER] tkinter fehlt in dieser Python-Installation.
echo          Python neu installieren und im Setup "tcl/tk and IDLE" aktiviert lassen.
pause
exit /b 1

:nopip
echo [FEHLER] pip ist nicht verfuegbar und ensurepip hat nicht geholfen.
pause
exit /b 1


rem ======================================================================
rem  :check "<zeile aus requirements.txt>"
rem  - ignoriert Leerzeilen, Kommentare und Options-Zeilen (-r, -e, --index-url ...)
rem  - testet per "import <modul>", installiert nur Fehlendes
rem ======================================================================
:check
set "LINE=%~1"
set "PKG="
set "SPEC="
if not defined LINE exit /b 0
if "%LINE:~0,1%"=="-" exit /b 0
for /f "tokens=1 delims=<>=!~;[ " %%N in ("%LINE%") do set "PKG=%%N"
if not defined PKG exit /b 0
if "%PKG:~0,1%"=="#" exit /b 0

rem Installations-Spezifikation: ohne Inline-Kommentar und ohne Leerzeichen am Ende
for /f "tokens=1 delims=#" %%S in ("%LINE%") do set "SPEC=%%S"
:trim
if "%SPEC:~-1%"==" " (
    set "SPEC=%SPEC:~0,-1%"
    goto :trim
)

rem Paketname -> Import-Name (Sonderfaelle)
set "MOD=%PKG%"
if /i "%PKG%"=="keystone-engine"        set "MOD=keystone"
if /i "%PKG%"=="pillow"                 set "MOD=PIL"
if /i "%PKG%"=="pillow-simd"            set "MOD=PIL"
if /i "%PKG%"=="opencv-python"          set "MOD=cv2"
if /i "%PKG%"=="opencv-python-headless" set "MOD=cv2"
if /i "%PKG%"=="opencv-contrib-python"  set "MOD=cv2"
if /i "%PKG%"=="pyyaml"                 set "MOD=yaml"
if /i "%PKG%"=="beautifulsoup4"         set "MOD=bs4"
if /i "%PKG%"=="scikit-learn"           set "MOD=sklearn"
if /i "%PKG%"=="scikit-image"           set "MOD=skimage"
if /i "%PKG%"=="python-dateutil"        set "MOD=dateutil"
if /i "%PKG%"=="python-dotenv"          set "MOD=dotenv"
if /i "%PKG%"=="pyserial"               set "MOD=serial"
if /i "%PKG%"=="pyusb"                  set "MOD=usb"
if /i "%PKG%"=="pyzmq"                  set "MOD=zmq"
if /i "%PKG%"=="pynacl"                 set "MOD=nacl"
if /i "%PKG%"=="pymupdf"                set "MOD=fitz"
if /i "%PKG%"=="pycryptodome"           set "MOD=Crypto"
if /i "%PKG%"=="pycryptodomex"          set "MOD=Cryptodome"
if /i "%PKG%"=="pywin32"                set "MOD=win32api"
if /i "%PKG%"=="protobuf"               set "MOD=google.protobuf"
if /i "%PKG%"=="attrs"                  set "MOD=attr"
if /i "%PKG%"=="msgpack-python"         set "MOD=msgpack"
if /i "%PKG%"=="websocket-client"       set "MOD=websocket"
rem Standard: Bindestriche -> Unterstriche
set "MOD=%MOD:-=_%"

%PYCMD% -c "import %MOD%" >nul 2>&1
if not errorlevel 1 (
    echo [OK] %PKG%
    exit /b 0
)
echo [..] %PKG% fehlt - installiere "%SPEC%"
%PYCMD% -m pip install --disable-pip-version-check "%SPEC%"
if errorlevel 1 (
    echo [!!] Installation von %PKG% fehlgeschlagen
    set "FAILED=1"
    exit /b 0
)
%PYCMD% -c "import %MOD%" >nul 2>&1
if errorlevel 1 (
    echo [!!] %PKG% installiert, Import "%MOD%" klappt aber nicht
    set "FAILED=1"
) else (
    echo [OK] %PKG% installiert
)
exit /b 0
