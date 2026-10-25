"""hackfx.py - "ACCESS GRANTED" / "ACCESS DENIED" im Hacker-Stil beim Verbinden (reine Zierde, ~3 Sekunden).

  Grün : Matrix-Regen, Schreibmaschinen-Text, kurzes Glitch-Flackern, danach Ausblenden
  Rot  : gleicher Aufbau, aber der Rahmen zittert; darunter der wahrscheinliche Grund (falsche IP / Payload aus ...)
Klick auf das Banner schliesst es sofort.  Abschaltbar: "hack_fx": false in der Konfiguration oder REAPERPY_NO_FX=1.
Die Zeitlogik steckt in reinen Funktionen (typed/glitch/rain_step/classify_error) und ist ohne Oberflaeche testbar;
jeder Fehler in der Oberflaeche wird verschluckt - Verbinden funktioniert immer.
"""
import os
import random
import time

GREEN = "#00ff66"
GREEN_DIM = "#0a7a3a"
RED = "#ff2a2a"
RED_DIM = "#7a1010"
BG = "#020a04"
BG_RED = "#0a0202"
FONT = "Consolas"
RAIN = "01ABCDEF<>/\\|=+*#$%&アイウエオカキクケコ"
TITLE_CPS = 24.0            # Zeichen pro Sekunde beim Tippen der Ueberschrift
LINE_CPS = 55.0
FADE_S = 0.35
GRANTED_S = 2.9
DENIED_S = 3.2
W, H = 600, 260


def enabled(cfg=None):
    if os.environ.get("REAPERPY_NO_FX"):
        return False
    return bool((cfg or {}).get("hack_fx", True))


def classify_error(err):
    """Verbindungsfehler -> kurzer Klartext im Hacker-Stil (Zeilen fuer das rote Banner)."""
    e = str(err).lower()
    if any(w in e for w in ("refused", "10061", "errno 111", "verweigert", "payload", "ps5debug")):
        return ["> CONNECTION REFUSED", "> PAYLOAD NOT RUNNING? (PORT CLOSED)"]
    if any(w in e for w in ("unreachable", "no route", "getaddrinfo", "name or service", "nodename", "10051", "10065",
                            "nicht erreichbar", "invalid ip", "ungültige")):
        return ["> HOST UNREACHABLE", "> CHECK IP ADDRESS / NETWORK"]
    if any(w in e for w in ("timed out", "timeout", "zeitüberschreitung", "zeitueberschreitung")):
        return ["> NO RESPONSE FROM HOST", "> CHECK IP ADDRESS / PAYLOAD"]
    if any(w in e for w in ("kein spiel", "no game", "pid", "prozess", "process")):
        return ["> LINK OK - NO GAME PROCESS", "> START THE GAME FIRST"]
    short = " ".join(str(err).split())[:44].upper()
    return ["> CONNECTION FAILED", f"> {short}" if short else "> UNKNOWN ERROR"]


def granted_lines(host="", port="", pid=None):
    lines = ["> HANDSHAKE ............ OK"]
    if host:
        lines.append(f"> TARGET {host}:{port}")
    if pid is not None:
        lines.append(f"> GAME PROCESS {pid} ATTACHED")
    return lines


def typed(text, t, cps, start=0.0):
    """Sichtbarer Teil von `text`, wenn seit `start` t Sekunden vergangen sind (Schreibmaschine)."""
    n = int(max(0.0, t - start) * cps)
    return text[:min(len(text), n)]


def glitch(t, seed=0, window=(0.95, 1.5)):
    """(dx, dy, hell?) - kurzes Flackern zwischen window[0] und window[1] Sekunden, sonst ruhig."""
    if not window[0] <= t <= window[1]:
        return 0, 0, True
    r = random.Random(int(t * 40) + seed)
    return r.randint(-5, 5), r.randint(-2, 2), r.random() > 0.35


def shake(t, amp=6.0):
    """Zittern des roten Rahmens: klingt in ~1.2 s ab."""
    if t > 1.2:
        return 0
    return int(amp * (1 - t / 1.2) * (1 if int(t * 45) % 2 else -1))


def alpha(t, total, fade=FADE_S):
    """Deckkraft 0..1: voll, in den letzten `fade` Sekunden ausblenden."""
    if t >= total:
        return 0.0
    if t > total - fade:
        return max(0.0, (total - t) / fade)
    return 1.0


def rain_step(cols, rng, height, step=14):
    """Matrix-Regen: cols = [y, speed, char]; jede Spalte faellt, bei Unterlauf neu oben."""
    out = []
    for y, sp, ch in cols:
        y += sp
        if y > height + step:
            y = -rng.randint(0, 120)
            sp = rng.choice((4, 6, 8, 10))
            ch = rng.choice(RAIN)
        elif rng.random() < 0.25:
            ch = rng.choice(RAIN)
        out.append([y, sp, ch])
    return out


class Banner:
    """Rahmenloses Overlay ueber dem Hauptfenster."""

    def __init__(self, root, ok, lines, host="", on_done=None, tk=None):
        if tk is None:
            import tkinter as tk
        self.tk = tk
        self.root, self.ok, self.on_done = root, ok, on_done
        self.title = "ACCESS GRANTED" if ok else "ACCESS DENIED"
        self.lines = list(lines)
        self.total = GRANTED_S if ok else DENIED_S
        self.fg, self.dim, self.bg = (GREEN, GREEN_DIM, BG) if ok else (RED, RED_DIM, BG_RED)
        self.t0 = time.time()
        self.win = None
        self.closed = False
        self.rng = random.Random()
        self.cols = []
        self._job = None
        try:
            tk_ = self.tk
            w = tk_.Toplevel(root)
            self.win = w
            w.overrideredirect(True)
            w.configure(bg=self.bg)
            try:
                w.attributes("-topmost", True)
            except Exception:  # noqa: BLE001
                pass
            try:
                x = root.winfo_rootx() + (root.winfo_width() - W) // 2
                y = root.winfo_rooty() + (root.winfo_height() - H) // 3
            except Exception:  # noqa: BLE001
                x, y = 200, 200
            self.x0, self.y0 = max(0, x), max(0, y)
            w.geometry(f"{W}x{H}+{self.x0}+{self.y0}")
            cv = tk_.Canvas(w, width=W, height=H, bg=self.bg, highlightthickness=0)
            cv.pack(fill="both", expand=True)
            self.cv = cv
            cv.bind("<Button-1>", lambda _e: self.close())
            w.bind("<Button-1>", lambda _e: self.close())
            self.cols = [[-self.rng.randint(0, H), self.rng.choice((4, 6, 8, 10)), self.rng.choice(RAIN)] for _ in range(W // 16)]
            self._tick()
        except Exception:  # noqa: BLE001
            self.win = None
            self.closed = True

    # ------------------------------------------------------------------
    def _tick(self):
        if self.closed or self.win is None:
            return
        t = time.time() - self.t0
        try:
            if t >= self.total:
                self.close()
                return
            self._draw(t)
            self._job = self.win.after(45, self._tick)
        except Exception:  # noqa: BLE001
            self.close()

    def _draw(self, t):
        cv = self.cv
        cv.delete("all")
        dxs = shake(t) if not self.ok else 0
        # Regen
        self.cols = rain_step(self.cols, self.rng, H)
        for i, (y, _sp, ch) in enumerate(self.cols):
            cv.create_text(8 + i * 16 + dxs, y, text=ch, fill=self.dim, font=(FONT, 11))
        # Scanlines
        for yy in range(0, H, 4):
            cv.create_line(0, yy, W, yy, fill=self.bg)
        # Rahmen (rot: zittert)
        cv.create_rectangle(3 + dxs, 3, W - 3 + dxs, H - 3, outline=self.fg, width=2)
        cv.create_rectangle(10 + dxs, 10, W - 10 + dxs, H - 10, outline=self.dim, width=1)
        # Ueberschrift
        gx, gy, bright = glitch(t, seed=0 if self.ok else 7)
        txt = typed(self.title, t, TITLE_CPS, 0.1)
        cursor = "█" if (int(t * 4) % 2 == 0 and len(txt) < len(self.title) + 6) else ""
        col = self.fg if bright else self.dim
        if gx or gy:                                    # Glitch: Geisterbild in Gegenfarbe
            cv.create_text(W // 2 + gx + 4, 78 + gy, text=txt, fill=(RED if self.ok else GREEN), font=(FONT, 40, "bold"))
        cv.create_text(W // 2 + gx + dxs, 78 + gy, text=txt + cursor, fill=col, font=(FONT, 40, "bold"))
        # Zeilen
        start = 0.1 + len(self.title) / TITLE_CPS + 0.15
        for i, line in enumerate(self.lines[:5]):
            st = typed(line, t, LINE_CPS, start + i * 0.45)
            if st:
                cv.create_text(40 + dxs, 142 + i * 22, text=st, fill=self.fg, font=(FONT, 12), anchor="w")
        try:
            a = alpha(t, self.total)
            if a < 1.0:
                self.win.attributes("-alpha", a)
        except Exception:  # noqa: BLE001
            pass

    def close(self):
        if self.closed and self.win is None:
            return
        self.closed = True
        try:
            if self._job is not None and self.win is not None:
                self.win.after_cancel(self._job)
        except Exception:  # noqa: BLE001
            pass
        try:
            if self.win is not None:
                self.win.destroy()
        except Exception:  # noqa: BLE001
            pass
        self.win = None
        cb, self.on_done = self.on_done, None
        if cb:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass


_current = None


def show(root, kind, info=None, cfg=None, tk=None):
    """kind 'granted' | 'denied'; info: dict(host, port, pid, error).  -> Banner oder None (abgeschaltet/Fehler)."""
    global _current
    if not enabled(cfg):
        return None
    info = info or {}
    try:
        if _current is not None:
            _current.close()
        if kind == "granted":
            lines = granted_lines(info.get("host", ""), info.get("port", ""), info.get("pid"))
        else:
            lines = classify_error(info.get("error", ""))
        _current = Banner(root, kind == "granted", lines, tk=tk)
        return _current if _current.win is not None else None
    except Exception:  # noqa: BLE001
        return None
