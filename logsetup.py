"""logsetup.py - Log-Datei mit Rotation + Absturzberichte.

  init()               logs/reaperpy.log (1 MB, 5 Sicherungen = hoechstens ~6 MB), auch unbehandelte Fehler landen dort
  install_tk(root)     Fehler in Tk-Callbacks (wie der Resize-Absturz) werden mit Traceback protokolliert
  log(msg, kind)       Zeile ins Log (kind: ok/info/warn/err/accent ...) - vom Hauptfenster und von den Werkzeugen benutzt
Alles hier ist abgesichert: ein kaputtes Logging darf das Programm nie stoppen.
"""
import logging
import logging.handlers
import os
import sys
import threading
import traceback

import paths

NAME = "reaperpy"
MAX_BYTES = 1_000_000
BACKUPS = 5
LEVELS = {"err": logging.ERROR, "warn": logging.WARNING}
_inited = False


def logger():
    return logging.getLogger(NAME)


def init(log_dir=None, max_bytes=MAX_BYTES, backups=BACKUPS, hook_exceptions=True):
    """-> Pfad der Log-Datei oder None."""
    global _inited
    lg = logger()
    if _inited and lg.handlers:
        return getattr(lg, "_file", None)
    try:
        d = log_dir or paths.logs_dir()
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "reaperpy.log")
        h = logging.handlers.RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
        lg.setLevel(logging.INFO)
        lg.addHandler(h)
        lg.propagate = False
        lg._file = path
        _inited = True
    except Exception:  # noqa: BLE001
        return None
    if hook_exceptions:
        _hook_exceptions()
    try:
        import version
        ver = version.__version__
    except Exception:  # noqa: BLE001
        ver = "?"
    lg.info("=== ReaperPy %s gestartet (Python %s) ===", ver, sys.version.split()[0])
    return path


def _hook_exceptions():
    old = sys.excepthook

    def hook(etype, value, tb):
        try:
            logger().error("Unbehandelter Fehler:\n%s", "".join(traceback.format_exception(etype, value, tb)))
        except Exception:  # noqa: BLE001
            pass
        old(etype, value, tb)
    sys.excepthook = hook

    def thook(args):
        try:
            logger().error("Fehler im Thread %s:\n%s", getattr(args.thread, "name", "?"),
                           "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
        except Exception:  # noqa: BLE001
            pass
    threading.excepthook = thook


def install_tk(root):
    """Fehler in Tk-Callbacks protokollieren (Tk schreibt sie sonst nur auf die Konsole)."""
    prev = getattr(root, "report_callback_exception", None)

    def report(etype, value, tb):
        try:
            logger().error("Tk-Callback-Fehler:\n%s", "".join(traceback.format_exception(etype, value, tb)))
        except Exception:  # noqa: BLE001
            pass
        if prev:
            prev(etype, value, tb)
    root.report_callback_exception = report


def log(msg, kind="info"):
    try:
        logger().log(LEVELS.get(kind, logging.INFO), "%s", str(msg).replace("\n", " | "))
    except Exception:  # noqa: BLE001
        pass


def current_file():
    return getattr(logger(), "_file", None)


def log_files():
    """Alle Log-Dateien (aktuell + Sicherungen), neueste zuerst."""
    f = current_file()
    if not f:
        return []
    d, base = os.path.split(f)
    out = [os.path.join(d, n) for n in os.listdir(d) if n == base or n.startswith(base + ".")]
    return sorted(out, key=lambda p: os.path.getmtime(p), reverse=True)
