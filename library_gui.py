"""library_gui.py – Bibliotheks-Fenster: Spiele als Karten (Icon + Titel + ID + Patch-Anzahl).

Klick auf eine Karte öffnet das Projekt des Spiels im Hauptfenster.
"""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import projects
from library import Library, GameEntry
from tools_common import (BG, BG_BAR, BG_CARD, BG_CARD_HVR, BORDER, BORDER_HVR, ACCENT, ACCENT_DIM,
                          TEXT, TEXT_DIM, WARN, ERROR, FONT_MONO, FONT_LABEL, FONT_HEAD, style_ttk)

try:
    from PIL import Image, ImageTk
    HAVE_PIL = True
except Exception:                       # Pillow fehlt -> Initialen-Fallback
    Image = ImageTk = None
    HAVE_PIL = False

ICON = 96
CARD_W = 200
FONT_NAME = ("Consolas", 10, "bold")
FONT_SUB = ("Consolas", 8)
_PALETTE = ("#12353a", "#2a2f55", "#3a2a4d", "#10403a", "#40302a", "#1f3a52", "#3d3a1c", "#2c4a2c")


def initials(entry):
    """Zwei Buchstaben für den Fallback-Icon: erste Buchstaben der ersten zwei Wörter."""
    words = [w for w in "".join(c if c.isalnum() else " " for c in entry.title).split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    if words:
        return words[0][:2].upper()
    return (entry.id[:2] or "?").upper()


def load_icon_image(path):
    """PhotoImage (ICON x ICON) oder None.  Mit Pillow jedes Format; ohne Pillow nur PNG/GIF
    (ganzzahlig verkleinert) - sonst None -> Initialen."""
    try:
        if HAVE_PIL:
            im = Image.open(path).convert("RGBA")
            im.thumbnail((ICON, ICON), Image.LANCZOS)
            canvas = Image.new("RGBA", (ICON, ICON), BG_CARD)
            canvas.paste(im, ((ICON - im.width) // 2, (ICON - im.height) // 2), im)
            return ImageTk.PhotoImage(canvas)
        if path.lower().endswith((".png", ".gif")):
            img = tk.PhotoImage(file=path)
            f = max(1, max(img.width(), img.height()) // ICON)
            return img.subsample(f, f) if f > 1 else img
    except Exception:
        pass
    return None


class GameCard(tk.Frame):
    def __init__(self, parent, entry, on_click):
        super().__init__(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER, bd=0,
                         cursor="hand2")
        self.entry = entry
        self._img = None
        self.cv = tk.Canvas(self, width=ICON, height=ICON, bg=BG_CARD, highlightthickness=0, bd=0)
        self.cv.pack(padx=12, pady=(12, 6))
        self._draw_icon()
        self.lbl_title = tk.Label(self, text=entry.title, bg=BG_CARD, fg=TEXT, font=FONT_NAME,
                                  wraplength=CARD_W - 28, justify="center")
        self.lbl_title.pack(padx=8)
        self.lbl_id = tk.Label(self, text=entry.id or "-", bg=BG_CARD, fg=ACCENT_DIM, font=FONT_SUB)
        self.lbl_id.pack()
        n = len(entry.patches)
        self.lbl_n = tk.Label(self, text=f"{n} Patch{'es' if n != 1 else ''}", bg=BG_CARD,
                              fg=TEXT_DIM if n else BORDER_HVR, font=FONT_SUB)
        self.lbl_n.pack(pady=(0, 12))
        self._kids = (self, self.cv, self.lbl_title, self.lbl_id, self.lbl_n)
        for w in self._kids:
            w.bind("<Button-1>", lambda _e: on_click(entry))
            w.bind("<Enter>", lambda _e: self._hover(True))
            w.bind("<Leave>", lambda _e: self._hover(False))

    def _draw_icon(self):
        self._img = load_icon_image(self.entry.icon) if self.entry.icon else None
        c = self.cv
        c.delete("all")
        if self._img is not None:
            c.create_image(ICON // 2, ICON // 2, image=self._img)
            return
        col = _PALETTE[sum(map(ord, self.entry.id or self.entry.title)) % len(_PALETTE)]
        c.create_rectangle(2, 2, ICON - 2, ICON - 2, fill=col, outline=BORDER_HVR)
        c.create_text(ICON // 2, ICON // 2, text=initials(self.entry), fill=ACCENT,
                      font=("Consolas", 28, "bold"))

    def _hover(self, on):
        bg = BG_CARD_HVR if on else BG_CARD
        for w in self._kids:
            w.configure(bg=bg)
        self.configure(highlightbackground=ACCENT_DIM if on else BORDER)


class LibraryWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.tr = app.tr
        self.title(f"REAPERPY  //  {self.tr.t('lib_title')}")
        self.configure(bg=BG)
        self.geometry("1000x700")
        self.minsize(560, 400)
        style_ttk(self)

        self.lib = None
        self.cards = []
        self._cols = 0
        self._q = queue.Queue()
        self._scanning = False

        head = tk.Frame(self, bg=BG_BAR)
        head.pack(fill="x")
        tk.Label(head, text=f"\u25b8  {self.tr.t('lib_title')}", bg=BG_BAR, fg=ACCENT,
                 font=FONT_HEAD).pack(side="left", padx=12, pady=8)
        self.lbl_count = tk.Label(head, text="", bg=BG_BAR, fg=TEXT_DIM, font=FONT_LABEL)
        self.lbl_count.pack(side="right", padx=12)

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=8)
        tk.Label(bar, text=self.tr.t("lib_search"), bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left")
        self.v_search = tk.StringVar()
        self.v_search.trace_add("write", lambda *_: self._render())
        tk.Entry(bar, textvariable=self.v_search, width=28, bg=BG_CARD, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", font=FONT_MONO, highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT_DIM).pack(side="left", padx=8)
        for key, cmd, acc in (("lib_rescan", self.rescan, True), ("lib_folder", self.pick_folder, False),
                              ("lib_add_patch", self.add_patch, False)):
            tk.Button(bar, text=self.tr.t(key), command=cmd, bg=BG_CARD, fg=ACCENT if acc else TEXT,
                      font=FONT_LABEL, relief="flat", bd=0, padx=12, pady=4, cursor="hand2",
                      activebackground=BG_CARD_HVR, activeforeground=ACCENT).pack(side="left", padx=3)

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview, style="Vertical.TScrollbar")
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.win_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resized)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.bind_all("<MouseWheel>", self._wheel, add="+")

        self.lbl_empty = tk.Label(self.inner, text="", bg=BG, fg=TEXT_DIM, font=FONT_MONO, justify="center")

        self.after(100, self._poll)
        self.rescan()                                   # Auto-Scan beim Öffnen

    # ------------------------------------------------------------------
    def _library_dir(self):
        d = self.app.cfg.get("library_dir") or projects.DEFAULTS["library_dir"]
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        return d

    def rescan(self):
        if self._scanning:
            return
        self._scanning = True
        self.lbl_count.configure(text=self.tr.t("lib_scanning"), fg=WARN)
        cfg = self.app.cfg
        lib = Library(self._library_dir(), cfg.get("projects_root", ""),
                      [k for k in cfg.get("projects", {})])

        def job():
            try:
                lib.scan()
                self._q.put(("done", lib))
            except Exception as e:
                self._q.put(("err", e))
        threading.Thread(target=job, daemon=True).start()

    def _poll(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, val = self._q.get_nowait()
                self._scanning = False
                if kind == "done":
                    self.lib = val
                    self._render()
                else:
                    self.lbl_count.configure(text=str(val), fg=ERROR)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ------------------------------------------------------------------
    def _render(self):
        if self.lib is None:
            return
        for c in self.cards:
            c.destroy()
        self.cards = []
        entries = self.lib.filter(self.v_search.get())
        self.lbl_count.configure(text=self.tr.t("lib_found", n=len(entries)), fg=TEXT_DIM)
        if not entries:
            self.lbl_empty.configure(text=self.tr.t("lib_empty", folder=self._library_dir()))
            self.lbl_empty.grid(row=0, column=0, pady=60, padx=20)
            return
        self.lbl_empty.grid_forget()
        for e in entries:
            self.cards.append(GameCard(self.inner, e, self.open_entry))
        self._grid(max(1, self.canvas.winfo_width() // (CARD_W + 16)) if self.canvas.winfo_width() > 1 else 4)

    def _grid(self, cols):
        for c in range(max(cols, self._cols)):
            self.inner.columnconfigure(c, weight=0, minsize=CARD_W if c < cols else 0)
        for i, card in enumerate(self.cards):
            card.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="n")
        self._cols = cols

    def _resized(self, e):
        self.canvas.itemconfig(self.win_id, width=e.width)
        cols = max(1, e.width // (CARD_W + 16))
        if cols != self._cols and self.cards:
            self._grid(cols)

    def _wheel(self, e):
        try:
            if e.widget.winfo_toplevel() is not self:
                return
            self.canvas.yview_scroll(int(-1 * (e.delta / 120)) or (-1 if e.delta > 0 else 1), "units")
        except Exception:
            pass

    # ------------------------------------------------------------------
    def open_entry(self, entry: GameEntry):
        if self.app.open_library_entry(entry):
            self.destroy()

    def pick_folder(self):
        d = filedialog.askdirectory(parent=self, title=self.tr.t("lib_pick_dir"),
                                    initialdir=self._library_dir())
        if d:
            self.app.cfg["library_dir"] = d
            projects.save_config(self.app.cfg)
            self.rescan()

    def add_patch(self):
        fn = filedialog.askopenfilename(parent=self, title=self.tr.t("lib_pick_patch"))
        if not fn:
            return
        try:
            self.app.add_patch_from_file(fn)
        except Exception as e:
            return messagebox.showerror(self.tr.t("dlg_error"), str(e), parent=self)
        self.rescan()

    def destroy(self):
        try:
            self.unbind_all("<MouseWheel>")        # nur unser Binding wäre falsch -> Hauptfenster neu setzen
            self.app.root.bind_all("<MouseWheel>", self.app._wheel, add="+")
        except Exception:
            pass
        super().destroy()
