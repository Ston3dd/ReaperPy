"""paths.py - wo liegen Programm, mitgelieferte Dateien und Benutzerdaten?

  Normal (python gui.py): alles neben den Quelldateien (wie bisher).
  Gepackt (PyInstaller, Ordner-Version): neben der EXE (Konfiguration, Profile, Logs bleiben beim Verschieben des Ordners
                           zusammen); ist dieser Ordner nicht beschreibbar (z. B. C:\\Programme), dann %APPDATA%\\ReaperPy
                           bzw. ~/.reaperpy.
  REAPERPY_HOME=<Ordner>   erzwingt einen Datenordner (z. B. fuer einen USB-Stick oder Tests).
"""
import os
import sys


def app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def resource(*parts):
    """Mitgelieferte Datei (assets/...): neben dem Quellcode bzw. im PyInstaller-Entpackordner."""
    base = getattr(sys, "_MEIPASS", None) or app_dir()
    return os.path.join(base, *parts)


def data_dir():
    env = os.environ.get("REAPERPY_HOME")
    if env:
        d = env
    elif is_frozen():
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.access(exe_dir, os.W_OK):
            d = exe_dir
        else:
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
            d = os.path.join(base, "ReaperPy" if os.environ.get("APPDATA") else ".reaperpy")
    else:
        d = app_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def sub_dir(name):
    d = os.path.join(data_dir(), name)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def logs_dir():
    return sub_dir("logs")


def profiles_dir():
    return sub_dir("profiles")
