"""update_ui.py - the update dialog: offer -> download/unpack/install with progress -> "restart required".

All logic lives in updater.py (UpdateJob); this file only draws it.  Every text comes from i18n (keys "upd_*").
"""
import queue
import tkinter as tk
from tkinter import ttk

import updater

BG, BG_BAR, BG_CARD, BG_CARD_HVR = "#06080d", "#0a0f18", "#0e1420", "#161f30"
ACCENT, TEXT, TEXT_DIM, ERROR = "#00ffc8", "#e6edf3", "#7d8590", "#ff3366"
FONT_MONO, FONT_HEAD, FONT_LABEL = ("Consolas", 10), ("Consolas", 11, "bold"), ("Consolas", 9)


def _mb(n):
    return f"{n / (1 << 20):.1f}"


class UpdateDialog(tk.Toplevel):
    """on_skip(version): user chose "skip this version".  on_restart(): user chose "restart now"."""

    def __init__(self, parent, tr, rel, current, target, frozen, on_skip=None, on_restart=None, job_factory=None):
        super().__init__(parent)
        self.tr, self.rel, self.target, self.frozen = tr, rel, target, frozen
        self.on_skip, self.on_restart = on_skip, on_restart
        self.job_factory = job_factory or updater.UpdateJob
        self.job = None
        self.configure(bg=BG)
        self.title(tr.t("upd_title"))
        self.geometry("560x420")
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        head = tk.Frame(self, bg=BG_BAR, height=42)
        head.pack(fill="x")
        tk.Label(head, text="\u25b8  " + tr.t("upd_headline", new=rel.version, cur=current), bg=BG_BAR, fg=ACCENT,
                 font=FONT_HEAD, anchor="w").pack(side="left", padx=12, pady=10)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=10)
        tk.Label(body, text=tr.t("upd_notes"), bg=BG, fg=TEXT_DIM, font=FONT_LABEL, anchor="w").pack(fill="x")
        box = tk.Text(body, bg="#02040a", fg=TEXT, font=FONT_MONO, relief="flat", height=10, wrap="word",
                      highlightthickness=1, highlightbackground="#182130")
        box.pack(fill="both", expand=True, pady=(4, 8))
        box.insert("end", (rel.notes or "").strip() or "-")
        box.configure(state="disabled")

        self.status = tk.Label(body, text="", bg=BG, fg=TEXT, font=FONT_LABEL, anchor="w", justify="left")
        self.status.pack(fill="x")
        self.bar = ttk.Progressbar(body, mode="determinate", maximum=100)

        self.btns = tk.Frame(self, bg=BG)
        self.btns.pack(fill="x", padx=14, pady=(0, 12))
        self._buttons_offer()

    # ---- buttons -----------------------------------------------------
    def _btn(self, key, cmd, primary=False):
        b = tk.Button(self.btns, text=self.tr.t(key), command=cmd, bg=ACCENT if primary else BG_CARD,
                      fg=BG if primary else TEXT, activebackground=BG_CARD_HVR, activeforeground=ACCENT,
                      font=FONT_LABEL, relief="flat", bd=0, padx=16, pady=6, cursor="hand2")
        b.pack(side="right", padx=(8, 0))
        return b

    def _clear_buttons(self):
        for w in self.btns.winfo_children():
            w.destroy()

    def _buttons_offer(self):
        self._clear_buttons()
        self._btn("upd_install", self.start_install, primary=True)
        self._btn("upd_later", self.destroy)
        self._btn("upd_skip", self._skip)

    def _skip(self):
        if self.on_skip:
            self.on_skip(self.rel.version)
        self.destroy()

    def _on_close(self):
        if self.job is not None and self.job.thread is not None and self.job.thread.is_alive():
            self.job.cancel.set()                         # closing during the download = cancel
            return
        self.destroy()

    # ---- install -----------------------------------------------------
    def start_install(self):
        self._clear_buttons()
        self._btn("upd_cancel", lambda: self.job.cancel.set())
        self.bar.pack(fill="x", pady=(6, 0))
        self.status.configure(text=self.tr.t("upd_stage_download"), fg=TEXT)
        self.job = self.job_factory(self.rel, self.target, self.frozen).start()
        self.after(80, self._poll)

    def _poll(self):
        try:
            while True:
                self._handle(self.job.events.get_nowait())
        except queue.Empty:
            pass
        if self.winfo_exists() and self.job is not None and not self._finished:
            self.after(80, self._poll)

    _finished = False

    def _handle(self, ev):
        kind = ev[0]
        if kind == "stage":
            self.status.configure(text=self.tr.t("upd_stage_" + ev[1]))
            if ev[1] != "download":
                self.bar.configure(mode="indeterminate")
                self.bar.start(12)
        elif kind == "progress":
            done, total = ev[1], ev[2]
            if total:
                self.bar.configure(value=100.0 * done / total)
                self.status.configure(text=self.tr.t("upd_progress", done=_mb(done), total=_mb(total)))
        elif kind == "done":
            self._finished = True
            self.bar.stop()
            self._show_done()
        elif kind == "cancelled":
            self._finished = True
            self.bar.stop()
            self.destroy()
        elif kind == "error":
            self._finished = True
            self.bar.stop()
            self.status.configure(text=self.tr.t("upd_error", err=ev[1]), fg=ERROR)
            self._clear_buttons()
            self._btn("info_close", self.destroy, primary=True)

    def _show_done(self):
        self.status.configure(text=self.tr.t("upd_done_text", new=self.rel.version), fg=ACCENT)
        self.bar.configure(mode="determinate", value=100)
        self._clear_buttons()
        self._btn("upd_restart_now", self._restart, primary=True)
        self._btn("upd_restart_later", self.destroy)

    def _restart(self):
        self.destroy()
        if self.on_restart:
            self.on_restart()
