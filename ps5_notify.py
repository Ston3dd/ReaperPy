"""ps5_notify.py - Benachrichtigungen auf dem PS5-Bildschirm (ueber CMD_CONSOLE_NOTIFY des ps5debug-NG-Payloads).

Der Notifier sendet nie aus dem UI-Thread, blockiert nie und kann nie etwas kaputt machen: jeder Fehler wird
verschluckt, und scheitert das Senden, schaltet das Backend die Meldungen selbst ab (siehe PS5Backend.notify).

Ereignisse:
  Verbunden               ReaperPy verbunden (PID ...)
  Cheat an / aus          einzeln: eine Meldung; Sammelaktionen (ALLE AN/AUS, Wiederherstellen): eine Zusammenfassung
  Debugger                attached / detached / Verbindung verloren, optional jeder Breakpoint-Treffer
  Cheat bei Debugger      Meldungen von Cheats tragen den Zusatz "(Debugger attached)", solange eine Sitzung steht

Konfiguration (reaperpy_config.json):
  "ps5_notifications": true    alle Meldungen an/aus
  "ps5_notify_hits":   false   zusaetzlich jeder Breakpoint-/Watchpoint-Treffer (hoechstens eine Meldung je 5 s)
"""
import queue
import threading
import time

HIT_MIN_INTERVAL = 5.0      # Sekunden zwischen zwei Treffer-Meldungen (ein heisser Breakpoint wuerde sonst fluten)
MAX_NAMES = 3               # so viele Namen stehen in einer Sammelmeldung, der Rest wird als "+N" gezaehlt
MAX_LEN = 180               # laengere Texte kuerzen (die Anzeige der Konsole ist klein)
_QUEUE_MAX = 32


def shorten(text, limit=MAX_LEN):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def summarize_names(names, max_names=MAX_NAMES):
    """["A", "B", "C", "D"] -> "A, B, C +1" (reine Funktion, ohne Oberflaeche testbar)."""
    names = [str(n) for n in names]
    if len(names) <= max_names:
        return ", ".join(names)
    return ", ".join(names[:max_names]) + f" +{len(names) - max_names}"


class Notifier:
    """tr: Translator (i18n.py).  backend: PS5Backend.  cfg: Konfig-Dict.  sender: Testhaken statt backend.notify."""

    def __init__(self, backend, cfg, tr, sender=None):
        self.backend = backend
        self.cfg = cfg
        self.tr = tr
        self._sender = sender or backend.notify
        self.debugger_attached = False
        self._dbg_state = "detached"
        self._q = queue.Queue(maxsize=_QUEUE_MAX)
        self._worker = None
        self._lock = threading.Lock()
        self._bulk_depth = 0
        self._bulk = []                  # (an?, Name) waehrend einer Sammelaktion
        self._last_hit = 0.0

    # ------------------------------------------------------------------
    # Grundfunktionen
    # ------------------------------------------------------------------
    @property
    def enabled(self):
        return bool(self.cfg.get("ps5_notifications", True))

    def _t(self, key, **kw):
        return self.tr.t(key, **kw)

    def send(self, text):
        """Meldung in die Warteschlange; kehrt sofort zurueck.  False = abgeschaltet oder Schlange voll."""
        if not self.enabled or not text:
            return False
        try:
            self._q.put_nowait(shorten(text))
        except queue.Full:
            return False
        self._start_worker()
        return True

    def _start_worker(self):
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._run, name="ps5-notify", daemon=True)
            self._worker.start()

    def _run(self):
        while True:
            try:
                text = self._q.get(timeout=5)
            except queue.Empty:
                return                   # beim naechsten send() startet ein neuer Thread
            try:
                self._sender(text)
            except Exception:            # noqa: BLE001 - Meldungen duerfen nie etwas stoeren
                pass

    def flush(self, timeout=2.0):
        """Wartet, bis die Schlange leer ist (Programmende, Tests)."""
        end = time.time() + timeout
        while time.time() < end and not self._q.empty():
            time.sleep(0.01)
        w = self._worker
        if w is not None:
            w.join(max(0.0, min(0.2, end - time.time())))

    # ------------------------------------------------------------------
    # Ereignisse
    # ------------------------------------------------------------------
    def connected(self, pid=None):
        self.send(self._t("notify_connected", pid=pid if pid is not None else "-"))

    def cheat(self, on, name):
        """Ein Cheat wurde an-/ausgeschaltet.  In einer Sammelaktion wird nur gesammelt."""
        with self._lock:
            if self._bulk_depth > 0:
                self._bulk.append((bool(on), str(name)))
                return
        self.send(self._cheat_text(on, [name]))

    def _cheat_text(self, on, names):
        key = "notify_on" if on else "notify_off"
        if self.debugger_attached:
            key += "_dbg"
        return self._t(key, name=summarize_names(names))

    def bulk_begin(self):
        with self._lock:
            self._bulk_depth += 1

    def bulk_end(self):
        """Ende einer Sammelaktion: eine Meldung fuer alle eingeschalteten, eine fuer alle ausgeschalteten Cheats."""
        with self._lock:
            self._bulk_depth = max(0, self._bulk_depth - 1)
            if self._bulk_depth > 0:
                return
            events, self._bulk = self._bulk, []
        for on in (True, False):
            names = [n for flag, n in events if flag is on]
            if not names:
                continue
            if len(names) == 1:
                self.send(self._cheat_text(on, names))
            else:
                key = ("notify_many_on" if on else "notify_many_off") + ("_dbg" if self.debugger_attached else "")
                self.send(self._t(key, n=len(names), names=summarize_names(names)))

    def debugger(self, state, pid=None):
        """state: "attached" | "reconnecting" | "lost" | "detached" (die Zustaende der DebugSession).

        Wiederholte Zustaende und der Wiederaufbau (reconnecting -> attached) bleiben stumm."""
        old, self._dbg_state = self._dbg_state, state
        self.debugger_attached = state in ("attached", "reconnecting")
        if state == old or state == "reconnecting" or (old == "reconnecting" and state == "attached"):
            return
        key = {"attached": "notify_dbg_attached", "detached": "notify_dbg_detached",
               "lost": "notify_dbg_lost"}.get(state)
        if key:
            self.send(self._t(key, pid=pid if pid is not None else "-"))

    def hit(self, kind, addr):
        """Breakpoint-/Watchpoint-Treffer; nur mit "ps5_notify_hits": true und hoechstens alle HIT_MIN_INTERVAL s."""
        if not self.cfg.get("ps5_notify_hits", False):
            return False
        now = time.time()
        if now - self._last_hit < HIT_MIN_INTERVAL:
            return False
        self._last_hit = now
        return self.send(self._t("notify_dbg_hit", kind=kind, addr=f"{int(addr):#x}"))
