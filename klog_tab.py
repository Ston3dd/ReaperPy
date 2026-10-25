"""klog_tab.py - Kernel-Log der Konsole (ps5debug-NG: TCP 3232) mit Fehler-Hervorhebung.

Zeigt Abstuerze, Page-Faults und Fehler rot - hilft, wenn ein Patch/Cave das Spiel beendet.
Die Verbindung baut sich bei Abbruch selbst neu auf, solange START aktiv ist.
"""
import collections
import re
import socket
import threading
import time
import tkinter as tk
from tkinter import filedialog

from tools_common import (ACCENT, BG, BG_BAR, ERROR, FONT_LABEL, TEXT_DIM, WARN, BaseTab,
                          button, entry, label, textbox)

KLOG_PORT = 3232
ERR_RE = re.compile(r"(fault|panic|crash|sigsegv|sigill|sigbus|sigabrt|abort|fatal|exception|"
                    r"killed|trap|segmentation)", re.I)
WARN_RE = re.compile(r"(error|fail|warn|denied|invalid|unable|timeout)", re.I)
MAX_LINES = 50000
SHOW_LINES = 5000


def classify(line):
    if ERR_RE.search(line):
        return "err"
    if WARN_RE.search(line):
        return "warn"
    return ""


class KlogReader:
    """Liest /dev/klog-Stream in einem Thread; on_lines(list[str]) kommt aus diesem Thread."""

    def __init__(self, host, port=KLOG_PORT, on_lines=None, on_state=None):
        self.host, self.port = host, port
        self.on_lines = on_lines or (lambda ls: None)
        self.on_state = on_state or (lambda s: None)
        self._stop = threading.Event()
        self._thread = None
        self._sock = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        s = self._sock
        if s:
            try:
                s.close()
            except Exception:
                pass

    def _run(self):
        while not self._stop.is_set():
            buf = b""
            try:
                self.on_state("verbinde ...")
                s = socket.create_connection((self.host, self.port), timeout=4)
                s.settimeout(1.0)
                self._sock = s
                self.on_state("verbunden")
                while not self._stop.is_set():
                    try:
                        data = s.recv(65536)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    buf += data
                    parts = buf.split(b"\n")
                    buf = parts.pop()
                    if parts:
                        self.on_lines([p.decode("utf-8", "replace").rstrip("\r") for p in parts])
                    if len(buf) > 1 << 20:               # Schutz gegen Endlos-Zeile
                        self.on_lines([buf.decode("utf-8", "replace")])
                        buf = b""
                try:
                    s.close()
                except Exception:
                    pass
                self.on_state("getrennt")
            except Exception as e:
                self.on_state(f"Fehler: {e}")
            for _ in range(20):                          # 2 s warten, aber abbrechbar
                if self._stop.is_set():
                    return
                time.sleep(0.1)


class KlogTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.lines = collections.deque(maxlen=MAX_LINES)     # (text, tag)
        self.incoming = collections.deque()
        self.reader = None
        self.v_filter = tk.StringVar()
        self.v_err = tk.BooleanVar(value=False)
        self.v_scroll = tk.BooleanVar(value=True)
        self.v_state = tk.StringVar(value="gestoppt")

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=6, pady=6)
        self.btn = button(bar, "START", self.toggle, accent=True)
        self.btn.pack(side="left")
        button(bar, "LEEREN", self.clear).pack(side="left", padx=4)
        button(bar, "SPEICHERN…", self.save).pack(side="left")
        label(bar, "Filter").pack(side="left", padx=(14, 3))
        e = entry(bar, self.v_filter, width=24)
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda _e: self._render())
        for txt, var, cmd in (("nur Fehler/Warnungen", self.v_err, self._render),
                              ("Autoscroll", self.v_scroll, None)):
            tk.Checkbutton(bar, text=txt, variable=var, command=cmd, bg=BG, fg=TEXT_DIM,
                           selectcolor=BG_BAR, activebackground=BG, activeforeground=ACCENT,
                           font=FONT_LABEL).pack(side="left", padx=6)
        tk.Label(bar, textvariable=self.v_state, bg=BG, fg=WARN, font=FONT_LABEL).pack(side="right")

        self.txt = textbox(self, height=20, width=100)
        self.txt.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.txt.configure(state="disabled", undo=False)
        self.txt.tag_configure("err", foreground=ERROR)
        self.txt.tag_configure("warn", foreground=WARN)
        self.after(150, self._drain)

    # -- Steuerung -----------------------------------------------------
    def toggle(self):
        if self.reader:
            self.reader.stop()
            self.reader = None
            self.btn.configure(text="START")
            self.v_state.set("gestoppt")
            return
        host = self.win.app.backend.host
        self.reader = KlogReader(host, KLOG_PORT, self._on_lines,
                                 lambda s: self.win.ui(lambda: self.v_state.set(s)))
        self.reader.start()
        self.btn.configure(text="STOP")

    def shutdown(self):
        if self.reader:
            self.reader.stop()
            self.reader = None

    def _on_lines(self, lines):
        self.incoming.extend(lines)

    def clear(self):
        self.lines.clear()
        self._render()

    def save(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".log",
                                            initialfile="klog.log", filetypes=[("Log", "*.log *.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(t for t, _ in self.lines) + "\n")
            self.log(f"klog gespeichert: {path}", "ok")

    # -- Anzeige ---------------------------------------------------------
    def _match(self, text, tag):
        if self.v_err.get() and not tag:
            return False
        f = self.v_filter.get().strip().lower()
        return not f or f in text.lower()

    def _drain(self):
        n = 0
        batch = []
        while self.incoming and n < 2000:
            t = self.incoming.popleft()
            tag = classify(t)
            self.lines.append((t, tag))
            if self._match(t, tag):
                batch.append((t, tag))
            n += 1
        if batch:
            self.txt.configure(state="normal")
            for t, tag in batch:
                self.txt.insert("end", t + "\n", tag or ())
            extra = int(self.txt.index("end-1c").split(".")[0]) - SHOW_LINES
            if extra > 0:
                self.txt.delete("1.0", f"{extra + 1}.0")
            if self.v_scroll.get():
                self.txt.see("end")
            self.txt.configure(state="disabled")
        try:
            if self.winfo_exists():
                self.after(150, self._drain)
        except Exception:
            pass

    def _render(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        shown = [(t, g) for t, g in self.lines if self._match(t, g)][-SHOW_LINES:]
        for t, tag in shown:
            self.txt.insert("end", t + "\n", tag or ())
        if self.v_scroll.get():
            self.txt.see("end")
        self.txt.configure(state="disabled")
