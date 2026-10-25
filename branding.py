"""branding.py - Programm-Icon und Startbildschirm (Splash) fuer ReaperPy.

  apply_icon(root)    setzt das Fenster-Icon (eingebettetes PNG; unter Windows zusaetzlich assets/reaperpy.ico)
  Splash(root)        rahmenloses Startfenster mit Icon, Name und Fortschrittsbalken; finish() schliesst es nach der
                      Mindestanzeigedauer und zeigt dann das Hauptfenster
Beides ist reine Zierde: jeder Fehler wird verschluckt, das Programm startet immer.
"""
import os
import time
import tkinter as tk

try:
    import icon_data
except Exception:  # noqa: BLE001
    icon_data = None

import paths

HERE = os.path.dirname(os.path.abspath(__file__))
BG = "#0b1020"
FG = "#e8f0ff"
DIM = "#8aa0c8"
ACCENT = "#22e6c4"


def photo(master, which="PNG_256"):
    if icon_data is None:
        return None
    try:
        return tk.PhotoImage(master=master, data=getattr(icon_data, which))
    except Exception:  # noqa: BLE001
        return None


def apply_icon(root):
    img = photo(root, "PNG_256")
    if img is not None:
        try:
            root.iconphoto(True, img)
            root._reaperpy_icon = img          # Referenz halten, sonst raeumt Tk das Bild weg
        except Exception:  # noqa: BLE001
            pass
    ico = paths.resource("assets", "reaperpy.ico")
    if os.name == "nt" and os.path.isfile(ico):
        try:
            root.iconbitmap(ico)
        except Exception:  # noqa: BLE001
            pass


def apply_icon_to(win, root=None):
    """Icon auch fuer Zusatzfenster (Werkzeuge ...)"""
    img = getattr(root or win.master, "_reaperpy_icon", None)
    if img is not None:
        try:
            win.iconphoto(False, img)
        except Exception:  # noqa: BLE001
            pass


def splash_enabled(cfg=None):
    if os.environ.get("REAPERPY_NO_SPLASH"):
        return False
    return bool((cfg or {}).get("splash", True))


class Splash:
    W, H = 440, 320

    def __init__(self, root, title="REAPERPY", subtitle="PS5 INJECTOR", version="", min_ms=1600):
        self.root = root
        self.min_ms = min_ms
        self.t0 = time.time()
        self.win = None
        self._img = None
        self._job = None
        try:
            w = tk.Toplevel(root)
            self.win = w
            w.overrideredirect(True)
            w.configure(bg=BG)
            try:
                w.attributes("-topmost", True)
            except Exception:  # noqa: BLE001
                pass
            sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
            w.geometry(f"{self.W}x{self.H}+{(sw - self.W) // 2}+{(sh - self.H) // 2}")
            cv = tk.Canvas(w, width=self.W, height=self.H, bg=BG, highlightthickness=1, highlightbackground="#27406e")
            cv.pack(fill="both", expand=True)
            self.cv = cv
            self._img = photo(w, "PNG_256")
            if self._img is not None:
                try:
                    self._img = self._img.subsample(2, 2)          # 128 px
                except Exception:  # noqa: BLE001
                    pass
                cv.create_image(self.W // 2, 108, image=self._img)
            cv.create_text(self.W // 2, 202, text=title, fill=FG, font=("Segoe UI", 22, "bold"))
            cv.create_text(self.W // 2, 232, text=subtitle, fill=DIM, font=("Segoe UI", 10))
            if version:
                cv.create_text(self.W - 10, self.H - 10, text=version, fill=DIM, font=("Segoe UI", 8), anchor="se")
            cv.create_rectangle(70, 262, self.W - 70, 268, outline="", fill="#16213f")
            self.bar = cv.create_rectangle(70, 262, 70, 268, outline="", fill=ACCENT)
            self.status = cv.create_text(self.W // 2, 288, text="", fill=DIM, font=("Segoe UI", 8))
            w.update()
            self._tick()
        except Exception:  # noqa: BLE001
            self.win = None

    def set_status(self, text):
        try:
            self.cv.itemconfigure(self.status, text=text)
            self.win.update_idletasks()
        except Exception:  # noqa: BLE001
            pass

    def _tick(self):
        if self.win is None:
            return
        try:
            frac = min(1.0, (time.time() - self.t0) * 1000 / max(1, self.min_ms))
            self.cv.coords(self.bar, 70, 262, 70 + (self.W - 140) * frac, 268)
            self._job = self.win.after(40, self._tick)
        except Exception:  # noqa: BLE001
            pass

    def finish(self, on_done=None):
        """Nach der Mindestanzeigedauer schliessen, dann on_done (Hauptfenster zeigen)."""
        left = max(0, int(self.min_ms - (time.time() - self.t0) * 1000))

        def close():
            try:
                if self.win is not None:
                    self.win.destroy()
            except Exception:  # noqa: BLE001
                pass
            self.win = None
            if on_done:
                on_done()
        if self.win is None:
            if on_done:
                on_done()
            return
        try:
            self.root.after(left, close)
        except Exception:  # noqa: BLE001
            close()
