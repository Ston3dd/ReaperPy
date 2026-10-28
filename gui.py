"""gui.py - ReaperPy v5.7 (PS5) - Hacker-Style GUI + Shnext/ReapProj + DE/EN.

Neu in 4.1: Karten mit Akzentstreifen, Bibliothek, Auto-Reconnect (PID-Watchdog),
Sitzungen, Fortschrittsbalken bei Sammel-Aktionen.
"""
import json, os, queue, shutil, threading, time, tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from ps5_backend import PS5Backend
from reapatch import ReapPatch, is_patch_file
from patch_engine import (apply_patch, deactivate_patch, detect_patched, is_cave_patch,
                          _asm_or_empty)
from i18n import Translator
from ps5_notify import Notifier
from tools_common import style_ttk
import projects
import imagebase as IMB
import session
import aob as AOB


BG          = "#06080d"
BG_BAR      = "#0a0f18"
BG_CARD     = "#0e1420"
BG_CARD_HVR = "#161f30"
BG_CARD_ON  = "#0e2018"
BORDER      = "#182130"
BORDER_HVR  = "#2a3950"
ACCENT      = "#00ffc8"
ACCENT_DIM  = "#008a6a"
ACCENT_BG   = "#0e2018"
TEXT        = "#e6edf3"
TEXT_DIM    = "#7d8590"
TEXT_DIM2   = "#4a5567"
WARN        = "#ffb000"
ERROR       = "#ff3366"
OK          = "#00ffc8"

FONT_MONO   = ("Consolas", 10)
FONT_TITLE  = ("Consolas", 10, "bold")
FONT_NAME   = ("Consolas", 11, "bold")
FONT_SUB    = ("Consolas", 8)
FONT_HEAD   = ("Consolas", 11, "bold")
FONT_LABEL  = ("Consolas", 9)

CARD_MIN_W  = 320          # Mindestbreite einer Karte -> Spaltenanzahl


class St:
    OFF     = "off"
    LOAD    = "load"
    ON      = "on"
    ERROR   = "error"


# ------------------------------------------------------------------
# Zustandsdatei (applied.json): bytes -> hex, atomar schreiben
# ------------------------------------------------------------------
def _enc(o):
    if isinstance(o, (bytes, bytearray)):
        return bytes(o).hex()
    if isinstance(o, dict):
        return {k: _enc(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_enc(v) for v in o]
    return o


def _dec_state(st):
    def fix(d):
        for k in ("original_bytes", "new_bytes"):
            if isinstance(d.get(k), str):
                d[k] = bytes.fromhex(d[k])
        return d
    fix(st)
    st["sites"] = [fix(dict(s)) for s in st.get("sites", [])] if "sites" in st else None
    if st["sites"] is None:
        del st["sites"]
    return st


# ------------------------------------------------------------------
# Dünner Fortschrittsbalken (ttk.Progressbar rendert unter ~18 px nur den Trog)
# ------------------------------------------------------------------
class ThinBar(tk.Canvas):
    def __init__(self, parent, height=3):
        super().__init__(parent, height=height, bg=BG_BAR, highlightthickness=0, bd=0)
        self._pct = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, pct):
        self._pct = max(0.0, min(100.0, float(pct)))
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        fill = int(w * self._pct / 100.0)
        if fill > 0:
            self.create_rectangle(0, 0, fill, h, fill=ACCENT, outline="")
            self.create_rectangle(max(0, fill - 24), 0, fill, h, fill="#7dffe3", outline="")  # Glanzkante


# ------------------------------------------------------------------
# Karte
# ------------------------------------------------------------------
class CheatCard(tk.Frame):
    def __init__(self, parent, path, reapatch, app):
        super().__init__(parent, bg=BG_CARD, highlightthickness=1,
                         highlightbackground=BORDER, bd=0)
        self.path = path
        self.rp = reapatch
        self.app = app
        self.state = St.OFF
        self.cave_addr = None
        self._angle = 0
        self._hovering = False
        self._spinning = False

        # Akzentstreifen links (BORDER = aus, ACCENT = an, WARN = lädt, ERROR = Fehler)
        self.stripe = tk.Frame(self, width=3, bg=BORDER, bd=0, highlightthickness=0)
        self.stripe.grid(row=0, column=0, rowspan=2, sticky="ns")

        self.cv = tk.Canvas(self, width=32, height=32, bg=BG_CARD,
                            highlightthickness=0, bd=0)
        self.cv.grid(row=0, column=1, rowspan=2, padx=(14, 12), pady=14, sticky="w")

        self.lbl_name = tk.Label(self, text=reapatch.name or "?", bg=BG_CARD,
                                 fg=TEXT, font=FONT_NAME, anchor="w", justify="left")
        self.lbl_name.grid(row=0, column=2, sticky="we", pady=(14, 0))

        sub = f"by : {reapatch.author}" if reapatch.author else " "
        self.lbl_sub = tk.Label(self, text=sub, bg=BG_CARD, fg=TEXT_DIM,
                                font=FONT_SUB, anchor="w", justify="left")
        self.lbl_sub.grid(row=1, column=2, sticky="we", pady=(0, 14))

        self.lbl_info = tk.Label(self, text="\u24d8", bg=BG_CARD, fg=TEXT_DIM2,
                                 font=("Segoe UI", 13), cursor="hand2")
        self.lbl_info.grid(row=0, column=3, rowspan=2, padx=(6, 14), sticky="e")

        self.columnconfigure(2, weight=1)
        self.bind("<Configure>", self._on_resize)

        for w in (self, self.cv, self.lbl_name, self.lbl_sub):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._hover_in)
            w.bind("<Leave>", self._hover_out)
        self.lbl_info.bind("<Button-1>", self._info)
        self.refresh_meta()
        for w in (self, self.cv, self.lbl_name, self.lbl_sub, self.lbl_info):
            w.bind("<Button-3>", self._menu)
            w.bind("<Button-2>", self._menu)

        self._apply()

    def _on_resize(self, ev):
        """Langer Name -> umbrechen statt abschneiden (Karten-Breite minus Icon/Streifen/Info)."""
        wl = max(120, ev.width - 118)
        # NICHT per cget zuruecklesen: je nach Tk/Python-Version kommt ein Tcl_Obj statt einer Zahl zurueck
        if getattr(self, "_wraplen", None) != wl:
            self._wraplen = wl
            self.lbl_name.configure(wraplength=wl)

    # --- Farben aus Zustand + Hover berechnen (ein Ort, kein Auseinanderlaufen) ---
    def _apply(self):
        if self.state == St.ON:
            bg = BG_CARD_ON
            stripe = ACCENT
        else:
            bg = BG_CARD_HVR if self._hovering else BG_CARD
            stripe = {St.ERROR: ERROR, St.LOAD: WARN}.get(
                self.state, BORDER_HVR if self._hovering else BORDER)
        self.configure(bg=bg)
        for w in (self.cv, self.lbl_name, self.lbl_sub, self.lbl_info):
            w.configure(bg=bg)
        self.stripe.configure(bg=stripe)
        self.draw()

    def draw(self):
        c = self.cv
        c.delete("all")
        cx, cy, r = 16, 16, 12
        if self.state == St.ON:
            c.create_oval(cx-r-1, cy-r-1, cx+r+1, cy+r+1,
                          outline=ACCENT_DIM, width=1, fill="")
            c.create_oval(cx-r, cy-r, cx+r, cy+r,
                          outline=ACCENT, width=2, fill=ACCENT_BG)
            c.create_line(cx-6, cy+1, cx-2, cy+5, cx+7, cy-5,
                          fill=ACCENT, width=2, capstyle="round", joinstyle="round")
        elif self.state == St.OFF:
            c.create_oval(cx-r, cy-r, cx+r, cy+r,
                          outline=BORDER_HVR, width=2, fill="")
        elif self.state == St.LOAD:
            c.create_oval(cx-r, cy-r, cx+r, cy+r,
                          outline=WARN, width=2, fill="")
            c.create_arc(cx-r, cy-r, cx+r, cy+r, start=self._angle,
                         extent=90, outline=WARN, width=3, style="arc")
        elif self.state == St.ERROR:
            c.create_oval(cx-r, cy-r, cx+r, cy+r,
                          outline=ERROR, width=2, fill="")
            c.create_line(cx-6, cy-6, cx+6, cy+6,
                          fill=ERROR, width=2, capstyle="round")
            c.create_line(cx-6, cy+6, cx+6, cy-6,
                          fill=ERROR, width=2, capstyle="round")

    def set_state(self, st, cave=None):
        self.state = st
        if cave is not None:
            self.cave_addr = cave
        self._apply()

    def _hover_in(self, ev):
        self._hovering = True
        self._apply()

    def _hover_out(self, ev):
        self._hovering = False
        self._apply()

    def _click(self, ev=None):
        self.app.card_clicked(self)

    def _info(self, ev=None):
        self.app.show_info(self.rp)

    def refresh_meta(self):
        """Name (mit Stern bei Favoriten) und Zeile darunter (Autor, Gruppe, Hotkey) aus dem Spiel-Profil."""
        gp = getattr(self.app, "gp", None)
        fn = os.path.basename(self.path)
        fav = bool(gp and fn in gp.favorites)
        self.lbl_name.configure(text=("★ " if fav else "") + (self.rp.name or "?"))
        parts = [f"by : {self.rp.author}"] if self.rp.author else []
        if gp and gp.groups.get(fn):
            parts.append(f"[{gp.groups[fn]}]")
        if gp and gp.hotkeys.get(fn):
            parts.append(f"\u2328 {gp.hotkeys[fn]}")
        self.lbl_sub.configure(text="  \u00b7  ".join(parts) if parts else " ")

    def menu_items(self):
        """Rechtsklick-Menue der Karte (reine Daten, testbar): [(Text, Funktion)]"""
        tr = self.app.tr.t
        on = self.state == St.ON
        gp = getattr(self.app, "gp", None)
        fn = os.path.basename(self.path)
        items = [(tr("ctx_deactivate") if on else tr("ctx_activate"), self._click),
                 (tr("ctx_info"), self._info),
                 (None, None),
                 (tr("ctx_fav_off") if gp and fn in gp.favorites else tr("ctx_fav_on"), lambda: self.app.toggle_favorite(self)),
                 (tr("ctx_group"), lambda: self.app.set_card_group(self)),
                 (tr("ctx_hotkey"), lambda: self.app.capture_hotkey(self))]
        if gp and fn in gp.hotkeys:
            items.append((tr("ctx_hotkey_off"), lambda: self.app.clear_card_hotkey(self)))
        items += [(None, None), (tr("ctx_copy_name"), self._copy_name), (tr("ctx_show_file"), self._show_file)]
        return items

    def _copy_name(self):
        self.clipboard_clear()
        self.clipboard_append(self.rp.name or os.path.basename(self.path))

    def _show_file(self):
        import subprocess
        import sys
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(self.path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", self.path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(self.path)])
        except Exception as e:  # noqa: BLE001
            self.app.log_msg(f"[ctx] {e}", "warn")

    def _menu(self, ev):
        import tools_ctx
        tools_ctx.show_menu(self, ev, self.menu_items())
        return "break"

    def start_spinner(self):
        """Startet die Drehanimation (höchstens eine Schleife pro Karte)."""
        if self._spinning or self.state != St.LOAD:
            return
        self._spinning = True
        self._spin()

    def _spin(self):
        if self.state != St.LOAD:
            self._spinning = False
            return
        self._angle = (self._angle + 20) % 360
        self.draw()
        self.after(80, self._spin)


class InfoDialog(tk.Toplevel):
    def __init__(self, parent, rp, image_base, tr):
        super().__init__(parent)
        self.tr = tr
        self.configure(bg=BG)
        self.title(tr.t("info_title"))
        self.geometry("640x500")
        self.transient(parent)

        head = tk.Frame(self, bg=BG_BAR, height=42)
        head.pack(fill="x")
        tk.Label(head, text=f"\u25b8  {rp.name}", bg=BG_BAR, fg=ACCENT,
                 font=FONT_HEAD, anchor="w").pack(side="left", padx=12)
        tk.Label(head, text=tr.t("info_by", author=rp.author or "?"),
                 bg=BG_BAR, fg=TEXT_DIM, font=FONT_SUB).pack(side="right", padx=12)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=10)

        hook = image_base + rp.origin_source[0] if rp.origin_source else 0
        typ = tr.t("type_cave") if is_cave_patch(rp) else tr.t("type_patch")
        ftype = {"reapproj": tr.t("filetype_reapproj"),
                 "shnext": tr.t("filetype_shnext"),
                 "json": tr.t("filetype_json")}.get(rp.file_type, rp.file_type)

        meta = [
            (tr.t("info_typ"), f"{typ} ({ftype})"),
            (tr.t("info_hook"), f"{hook:#x}"),
            (tr.t("info_offset"), f"+{rp.origin_source[0]:#x}" if rp.origin_source else "-"),
            (tr.t("info_labels"), str(len(rp.labels))),
        ]
        for i, (k, v) in enumerate(meta):
            tk.Label(body, text=k, bg=BG, fg=TEXT_DIM, font=FONT_SUB,
                     anchor="w", width=16).grid(row=i, column=0, sticky="w", pady=2)
            tk.Label(body, text=v, bg=BG, fg=TEXT, font=FONT_MONO,
                     anchor="w").grid(row=i, column=1, sticky="w", pady=2)

        tk.Label(body, text=tr.t("info_labels"), bg=BG, fg=TEXT_DIM, font=FONT_SUB,
                 anchor="w").grid(row=len(meta), column=0, sticky="nw", pady=(8, 2))

        box = tk.Text(body, bg="#02040a", fg=TEXT, insertbackground=ACCENT,
                      font=FONT_MONO, relief="flat", highlightthickness=1,
                      highlightbackground=BORDER, height=14, wrap="none")
        box.grid(row=len(meta), column=1, sticky="nsew", pady=(8, 2))
        body.rowconfigure(len(meta), weight=1)
        body.columnconfigure(1, weight=1)

        for name, asm in rp.labels:
            box.insert("end", f"\u25b8 {name}\n", "name")
            for ln in (asm or "").splitlines():
                box.insert("end", f"    {ln}\n")
            box.insert("end", "\n")
        box.tag_config("name", foreground=ACCENT, font=FONT_TITLE)
        box.configure(state="disabled")

        btnbar = tk.Frame(self, bg=BG)
        btnbar.pack(fill="x", padx=14, pady=(0, 12))
        tk.Button(btnbar, text=tr.t("info_close"), bg=BG_CARD, fg=TEXT,
                  activebackground=BG_CARD_HVR, activeforeground=ACCENT,
                  font=FONT_LABEL, relief="flat", bd=0,
                  padx=16, pady=6, cursor="hand2",
                  command=self.destroy).pack(side="right")


# ------------------------------------------------------------------
# Anwendung
# ------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.cfg = projects.load_config()

        self.backend = PS5Backend(
            host=self.cfg.get("ps5_ip", "192.168.178.25"),
            port=int(self.cfg.get("ps5_port", 744)),
        )
        self.patches = {}
        self.cards = {}
        self.gp = None               # Spiel-Profil (Favoriten, Gruppen, Hotkeys, Notizen) des offenen Projekts
        self._hotkeys = {}           # "Ctrl+F5" -> Patch-Pfad
        self._last_hot = ("", 0.0)
        self.applied = {}            # path -> Zustand der aktiven Patches
        self.wanted = set()          # Patches, die der Anwender an haben will (für Auto-Reconnect)
        self.PATCH_DIR = None
        self.IMAGE_BASE = 0x400000
        self.current_project = None
        self.tools_stash = None      # Cheat-Liste/Pointer, wenn das Werkzeug-Fenster zu ist
        self._tools = None
        self._library = None
        self._saved_entries = {}     # aus applied.json (nur zum Anreichern, nie blind vertraut)
        self._saved_pid = None

        self.tr = Translator(self.cfg.get("language", "de"))
        self.notifier = Notifier(self.backend, self.cfg, self.tr)    # Meldungen auf dem PS5-Bildschirm (ps5_notify.py)
        try:
            import logsetup
            logsetup.init()                         # Log-Datei mit Rotation + Absturzberichte
            logsetup.install_tk(root)
        except Exception:
            pass
        try:
            import tools_ctx
            tools_ctx.install(root)                 # Rechtsklick-Menues fuer Listen, Felder und Logs
        except Exception:
            pass
        try:
            import tkinter.simpledialog as _sd
            import tools_i18n
            tools_i18n.set_lang(self.tr.lang)       # Werkzeug-Tabs folgen der Sprache des Hauptfensters
            tools_i18n.install_var_hook(tk.StringVar)
            tools_i18n.install_combobox_hook(ttk)
            tools_i18n.install_toplevel_hook(tk)
            tools_i18n.install_dialog_hooks(messagebox, _sd, filedialog)
            self._i18n_note = tools_i18n.status()
        except Exception:
            self._i18n_note = (0, "tools_i18n konnte nicht geladen werden")

        self.q = queue.Queue()
        self._connected = False
        self._want_connected = False         # nach erstem erfolgreichem Verbinden: Watchdog aktiv
        self._watch_busy = False
        self.debug_busy = False          # Debugger attached/attacht gerade: Waechter pausiert
        self._watch_misses = 0
        self._lost_notified = False
        self._auto = bool(self.cfg.get("auto_reconnect", False))
        self._patch_lock = threading.RLock()
        self._blink_on = True
        self._title_base = ""
        self._cols = 0
        self._pb_visible = False

        root.title(self.tr.t("window_title"))
        root.geometry("1400x900")
        root.minsize(1100, 700)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._setup_style()
        self._build_topbar()
        self._build_header()
        self._build_progress()
        self._build_actions()
        self._build_cards_area()
        self._build_log()

        self.project_list = []
        self.reload_projects()
        last = self.cfg.get("last_project", "")
        if last:
            self.select_project_by_name(last)
        if not self.current_project:
            self._set_title(self.tr.t("no_project"))

        root.after(80, self.poll)
        root.after(500, self._blink)
        root.after(2000, self._watch_pid)

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _setup_style(self):
        style_ttk(self.root)         # gemeinsames Theme inkl. lesbarer Comboboxen

    def _build_topbar(self):
        top = tk.Frame(self.root, bg=BG_BAR, height=44)
        top.pack(fill="x")
        top.pack_propagate(False)

        def lbl(text, key=None):
            l = tk.Label(top, text=text, bg=BG_BAR, fg=TEXT_DIM, font=FONT_LABEL)
            if key:
                self.tr.bind(l, "text", key)
            return l

        lbl("", "label_project").pack(side="left", padx=(14, 4), pady=6)
        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(top, textvariable=self.project_var,
                                          width=40, state="readonly", font=FONT_MONO)
        self.project_combo.pack(side="left", padx=4)
        self.project_combo.bind("<<ComboboxSelected>>", self.on_project_selected)

        tk.Button(top, text="\u21bb", bg=BG_CARD, fg=ACCENT, font=FONT_LABEL,
                  relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
                  activebackground=BG_CARD_HVR, activeforeground=ACCENT,
                  command=self.reload_projects).pack(side="left", padx=2)

        btn_folder = tk.Button(top, text="ORDNER", bg=BG_CARD, fg=TEXT_DIM,
                               font=FONT_LABEL, relief="flat", bd=0, padx=10, pady=2,
                               cursor="hand2",
                               activebackground=BG_CARD_HVR, activeforeground=ACCENT,
                               command=self.pick_project_folder)
        btn_folder.pack(side="left", padx=2)
        self.tr.bind(btn_folder, "text", "btn_folder")

        btn_lib = tk.Button(top, text="BIBLIOTHEK", bg=BG_CARD, fg=ACCENT,
                            font=FONT_LABEL, relief="flat", bd=0, padx=10, pady=2,
                            cursor="hand2",
                            activebackground=BG_CARD_HVR, activeforeground=ACCENT,
                            command=self.open_library)
        btn_lib.pack(side="left", padx=(8, 2))
        self.tr.bind(btn_lib, "text", "btn_library")

        btn_gh = tk.Button(top, text="GOLDHEN-JSON", bg=BG_CARD, fg=ACCENT,
                           font=FONT_LABEL, relief="flat", bd=0, padx=10, pady=2,
                           cursor="hand2",
                           activebackground=BG_CARD_HVR, activeforeground=ACCENT,
                           command=self.open_goldhen_export)
        btn_gh.pack(side="left", padx=2)

        self.lang_btn_de = tk.Button(top, text="DE", bg=BG_CARD, fg=TEXT_DIM,
                                     font=FONT_LABEL, relief="flat", bd=0,
                                     padx=8, pady=2, cursor="hand2",
                                     activebackground=BG_CARD_HVR,
                                     activeforeground=ACCENT,
                                     command=lambda: self.set_language("de"))
        self.lang_btn_en = tk.Button(top, text="EN", bg=BG_CARD, fg=TEXT_DIM,
                                     font=FONT_LABEL, relief="flat", bd=0,
                                     padx=8, pady=2, cursor="hand2",
                                     activebackground=BG_CARD_HVR,
                                     activeforeground=ACCENT,
                                     command=lambda: self.set_language("en"))
        self.lang_btn_de.pack(side="right", padx=(2, 14))
        self.lang_btn_en.pack(side="right", padx=2)
        self._refresh_lang_buttons()
        n_i18n, err_i18n = getattr(self, "_i18n_note", (0, ""))
        if self.tr.lang == "en" and (err_i18n or n_i18n < 100):
            self.root.after(800, lambda: self.log_msg(f"[i18n] English dictionary not loaded ({n_i18n} entries) {err_i18n} - texts stay German", "warn"))

        self.btn_connect = tk.Button(top, text="VERBINDEN", bg=BG_CARD, fg=ACCENT,
                                     font=FONT_LABEL, relief="flat", bd=0,
                                     padx=12, pady=2, cursor="hand2",
                                     activebackground=BG_CARD_HVR,
                                     activeforeground=ACCENT,
                                     command=self.connect)
        self.btn_connect.pack(side="right", padx=(4, 8))
        self.tr.bind(self.btn_connect, "text", "btn_connect")

        self.port_var = tk.StringVar(value=str(self.cfg.get("ps5_port", 744)))
        tk.Entry(top, textvariable=self.port_var, bg=BG, fg=ACCENT,
                 insertbackground=ACCENT, font=FONT_MONO, relief="flat",
                 width=5, bd=0, highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT_DIM).pack(side="right", padx=2)
        lbl("", "label_ps5_port").pack(side="right", padx=(4, 0))

        self.ip_var = tk.StringVar(value=self.cfg.get("ps5_ip", "192.168.178.25"))
        tk.Entry(top, textvariable=self.ip_var, bg=BG, fg=ACCENT,
                 insertbackground=ACCENT, font=FONT_MONO, relief="flat",
                 width=16, bd=0, highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT_DIM).pack(side="right", padx=4)
        lbl("", "label_ps5_ip").pack(side="right", padx=(10, 2))

    def _refresh_lang_buttons(self):
        active = self.tr.lang
        for code, btn in (("de", self.lang_btn_de), ("en", self.lang_btn_en)):
            if code == active:
                btn.configure(fg=ACCENT, bg=BG_CARD_HVR)
            else:
                btn.configure(fg=TEXT_DIM, bg=BG_CARD)

    def set_language(self, lang):
        if lang == self.tr.lang:
            return
        self.tr.set_lang(lang)
        try:
            import tools_i18n
            tools_i18n.set_lang(lang)
            w = self._tools
            if w is not None and w.winfo_exists():
                w.apply_language()                  # offenes Werkzeug-Fenster sofort umschalten
        except Exception:
            pass
        self.cfg["language"] = lang
        projects.save_config(self.cfg)
        self._refresh_lang_buttons()
        self.root.title(self.tr.t("window_title"))
        self._refresh_title()
        self._update_count()
        self._refresh_group_values()

    # --- Titel mit blinkendem Cursor ---
    def _set_title(self, text):
        self._title_base = text
        self._render_title()

    def _refresh_title(self):
        if self.current_project:
            self._set_title(f"\u25b8  {self.current_project.upper()}")
        else:
            self._set_title(self.tr.t("no_project"))

    def _render_title(self):
        cursor = "\u2588" if self._blink_on else " "
        self.lbl_project.configure(text=f"{self._title_base} {cursor}")

    def _blink(self):
        self._blink_on = not self._blink_on
        self._render_title()
        self.root.after(500, self._blink)

    def _build_header(self):
        head = tk.Frame(self.root, bg=BG, height=64)
        head.pack(fill="x", padx=14, pady=(10, 4))
        head.pack_propagate(False)

        left = tk.Frame(head, bg=BG)
        left.pack(side="left", fill="y")

        self.lbl_project = tk.Label(left, text="", bg=BG,
                                    fg=ACCENT, font=("Consolas", 15, "bold"), anchor="w")
        self.lbl_project.pack(anchor="w")

        self.lbl_status = tk.Label(left, text=self.tr.t("status_ready"), bg=BG,
                                   fg=TEXT_DIM, font=FONT_SUB, anchor="w")
        self.lbl_status.pack(anchor="w")

        right = tk.Frame(head, bg=BG)
        right.pack(side="right", fill="y")

        top_row = tk.Frame(right, bg=BG)
        top_row.pack(anchor="e")
        self.auto_var = tk.BooleanVar(value=self._auto)
        chk = tk.Checkbutton(top_row, text="AUTO-RECONNECT", variable=self.auto_var,
                             command=self._auto_toggled, bg=BG, fg=TEXT_DIM,
                             selectcolor=BG_CARD, activebackground=BG,
                             activeforeground=ACCENT, font=FONT_SUB, bd=0,
                             highlightthickness=0, cursor="hand2")
        chk.pack(side="right", padx=(10, 0))
        self.tr.bind(chk, "text", "chk_auto_reconnect")
        lbl_base = tk.Label(top_row, text=self.tr.t("label_imgbase"), bg=BG,
                            fg=TEXT_DIM, font=FONT_SUB)
        lbl_base.pack(side="right")
        self.tr.bind(lbl_base, "text", "label_imgbase")

        row = tk.Frame(right, bg=BG)
        row.pack(anchor="e")
        self.imgbase_var = tk.StringVar(value=self.cfg.get("image_base", "0x400000"))
        tk.Entry(row, textvariable=self.imgbase_var, bg=BG, fg=ACCENT,
                 insertbackground=ACCENT, font=FONT_MONO, relief="flat",
                 width=14, bd=0, highlightthickness=1,
                 highlightbackground=BORDER, highlightcolor=ACCENT_DIM,
                 justify="center").pack(side="left")
        btn_ok = tk.Button(row, text="OK", bg=BG_CARD, fg=ACCENT, font=FONT_LABEL,
                           relief="flat", bd=0, padx=10, cursor="hand2",
                           activebackground=BG_CARD_HVR, activeforeground=ACCENT,
                           command=self.apply_imgbase)
        btn_ok.pack(side="left", padx=4)
        self.tr.bind(btn_ok, "text", "btn_ok")

    def _auto_toggled(self):
        self._auto = bool(self.auto_var.get())
        self.cfg["auto_reconnect"] = self._auto
        projects.save_config(self.cfg)

    def _build_progress(self):
        """Dünner Streifen unter dem Header; der Balken erscheint nur bei Sammel-Aktionen."""
        self.pb_wrap = tk.Frame(self.root, bg=BG, height=4)
        self.pb_wrap.pack(fill="x", padx=14)
        self.pb_wrap.pack_propagate(False)
        self.pb = ThinBar(self.pb_wrap, height=3)

    def _progress(self, i, n):
        if not self._pb_visible:
            self.pb.pack(fill="x", pady=0)
            self._pb_visible = True
        self.pb.set(100.0 * i / max(n, 1))

    def _progress_done(self):
        def hide():
            if self._pb_visible:
                self.pb.pack_forget()
                self._pb_visible = False
        self.root.after(450, hide)

    def _build_actions(self):
        bar = tk.Frame(self.root, bg=BG, height=38)
        bar.pack(fill="x", padx=14, pady=(4, 8))

        def btn(key, cmd, accent=False):
            fg = ACCENT if accent else TEXT
            b = tk.Button(bar, text=key, bg=BG_CARD, fg=fg, font=FONT_LABEL,
                          relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
                          activebackground=BG_CARD_HVR, activeforeground=ACCENT,
                          command=cmd)
            b.pack(side="left", padx=(0, 6))
            self.tr.bind(b, "text", key)
            return b

        btn("btn_load_patches", self.load_patches, accent=True)
        btn("btn_status_scan", self.refresh_status)
        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", padx=8)
        btn("btn_all_on", self.activate_all)
        btn("btn_all_off", self.deactivate_all)
        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", padx=8)
        btn("btn_tools", self.open_tools, accent=True)
        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", padx=8)
        lbl = tk.Label(bar, text="", bg=BG, fg=TEXT_DIM, font=FONT_LABEL)
        lbl.pack(side="left")
        self.tr.bind(lbl, "text", "search_label")
        self.v_search = tk.StringVar()
        ent = tk.Entry(bar, textvariable=self.v_search, width=16, bg=BG_CARD, fg=TEXT, insertbackground=TEXT,
                       relief="flat", font=FONT_LABEL)
        ent.pack(side="left", padx=(4, 6), ipady=4)
        self.v_group = tk.StringVar()
        self.group_combo = ttk.Combobox(bar, textvariable=self.v_group, state="readonly", width=14)
        self.group_combo.pack(side="left", padx=(0, 6))
        self.v_favonly = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(bar, text="", variable=self.v_favonly, bg=BG, fg=TEXT_DIM, selectcolor=BG_CARD,
                             activebackground=BG, activeforeground=ACCENT, font=FONT_LABEL)
        chk.pack(side="left")
        self.tr.bind(chk, "text", "filter_fav")
        self._refresh_group_values()
        self.v_search.trace_add("write", self._apply_filter)
        self.v_group.trace_add("write", self._apply_filter)
        self.v_favonly.trace_add("write", self._apply_filter)

        self.lbl_count = tk.Label(bar, text="", bg=BG, fg=TEXT_DIM, font=FONT_LABEL)
        self.lbl_count.pack(side="right", padx=8)

    def _build_cards_area(self):
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self.cards_canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        self.cards_scroll = ttk.Scrollbar(wrap, orient="vertical",
                                          command=self.cards_canvas.yview,
                                          style="Vertical.TScrollbar")
        self.cards_frame = tk.Frame(self.cards_canvas, bg=BG)
        self.cards_window = self.cards_canvas.create_window((0, 0),
                                                            window=self.cards_frame,
                                                            anchor="nw")
        self.cards_frame.bind("<Configure>",
                              lambda e: self.cards_canvas.configure(
                                  scrollregion=self.cards_canvas.bbox("all")))
        self.cards_canvas.bind("<Configure>", self._canvas_resized)
        self.cards_canvas.configure(yscrollcommand=self.cards_scroll.set)
        self.cards_canvas.pack(side="left", fill="both", expand=True)
        self.cards_scroll.pack(side="right", fill="y")
        # add="+": überschreibt keine Bindings anderer Fenster; _wheel filtert selbst
        self.root.bind_all("<MouseWheel>", self._wheel, add="+")
        self.root.bind_all("<KeyPress>", self._on_key, add="+")        # Cheat-Hotkeys (Programmfenster)
        self.root.after(4000, self._update_check_async)               # nur wenn "update_url" gesetzt ist

    def _wheel(self, e):
        """Mausrad scrollt die Karten nur, wenn der Zeiger im Hauptfenster über der Kartenfläche steht
        (vorher scrollte das globale Binding auch beim Scrollen im Werkzeug-Fenster)."""
        try:
            if e.widget.winfo_toplevel() is not self.root:
                return
            c = self.cards_canvas
            x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
            if not (c.winfo_rootx() <= x < c.winfo_rootx() + c.winfo_width()
                    and c.winfo_rooty() <= y < c.winfo_rooty() + c.winfo_height()):
                return
            step = int(-1 * (e.delta / 120)) or (-1 if e.delta > 0 else 1)
            c.yview_scroll(step, "units")
        except Exception:
            pass

    def _canvas_resized(self, e):
        self.cards_canvas.itemconfig(self.cards_window, width=e.width)
        cols = max(1, e.width // CARD_MIN_W)
        if cols != self._cols and self.cards:
            self._grid_cards(cols)

    def _build_log(self):
        wrap = tk.Frame(self.root, bg=BG_BAR, height=170)
        wrap.pack(fill="x")
        wrap.pack_propagate(False)

        head = tk.Frame(wrap, bg=BG_BAR, height=22)
        head.pack(fill="x")
        lbl_log = tk.Label(head, text=self.tr.t("label_log"), bg=BG_BAR,
                           fg=ACCENT, font=FONT_SUB, anchor="w")
        lbl_log.pack(side="left", padx=14)
        self.tr.bind(lbl_log, "text", "label_log")

        tk.Button(head, text="\u2715", bg=BG_BAR, fg=TEXT_DIM, font=FONT_SUB,
                  relief="flat", bd=0, cursor="hand2",
                  activebackground=BG_BAR, activeforeground=ERROR,
                  command=self._clear_log).pack(side="right", padx=10)

        self.log = tk.Text(wrap, bg="#02040a", fg=TEXT, insertbackground=ACCENT,
                           font=("Consolas", 9), relief="flat", bd=0,
                           highlightthickness=0, wrap="none")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.log.yview,
                           style="Vertical.TScrollbar")
        self.log.configure(yscrollcommand=sb.set)
        self.log._is_log = True
        self.log._save_log = self._save_log
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        for tag, color in (("ok", OK), ("err", ERROR), ("warn", WARN),
                           ("info", TEXT_DIM), ("accent", ACCENT)):
            self.log.tag_config(tag, foreground=color)
        self.log.tag_config("head", foreground=ACCENT, font=FONT_TITLE)

    def _clear_log(self):
        self.log.delete("1.0", "end")

    # ------------------------------------------------------------------
    # Hilfen
    # ------------------------------------------------------------------
    def _hook(self, rp):
        """Hook-Adresse: per Signatur (falls im Patch) sonst Image-Base + Offset."""
        return AOB.resolve_hook(self.backend, rp, self.IMAGE_BASE,
                                log=lambda m: self.q.put(("log", (m, "info"))))

    def _qlog(self, msg, tag="info"):
        self.q.put(("log", (msg, tag)))

    def open_tools(self):
        if self.backend.client is None or self.backend.pid is None:
            messagebox.showinfo("ReaperPy", self.tr.t("log_not_conn"))
            return
        try:
            from tools_gui import ToolsWindow
        except Exception as e:
            messagebox.showerror(self.tr.t("dlg_error"), f"tools_gui: {e}")
            return
        w = self._tools
        if w is not None:
            try:
                if w.winfo_exists():
                    w.lift()
                    return
            except Exception:
                pass
        self._tools = ToolsWindow(self)

    def open_goldhen_export(self):
        try:
            from export_goldhen import ExportDialog
        except Exception as e:
            messagebox.showerror(self.tr.t("dlg_error"), f"export_goldhen: {e}")
            return
        if not self.patches:
            messagebox.showerror(self.tr.t("dlg_error"), "Keine Patches geladen.")
            return
        ExportDialog(self)

    def open_library(self):
        try:
            from library_gui import LibraryWindow
        except Exception as e:
            messagebox.showerror(self.tr.t("dlg_error"), f"library_gui: {e}")
            return
        w = self._library
        if w is not None:
            try:
                if w.winfo_exists():
                    w.lift()
                    return
            except Exception:
                pass
        self._library = LibraryWindow(self)

    def _save_log(self):
        path = filedialog.asksaveasfilename(title=self.tr.t("ctx_save_log"), defaultextension=".txt",
                                            initialfile="reaperpy_log.txt", filetypes=[("Text", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log.get("1.0", "end-1c"))

    def log_msg(self, msg, tag=None):
        if tag is None:
            m = str(msg)
            if m.startswith("OK") or m.startswith("[cave]") or m.startswith("[prot]"):
                tag = "ok"
            elif m.startswith("FEHLER") or m.startswith("ERROR") or "Error" in m or "Exception" in m:
                tag = "err"
            elif m.startswith("WARN") or m.startswith("SKIP"):
                tag = "warn"
            elif m.startswith("---") or m.startswith("==="):
                tag = "head"
            else:
                tag = "info"
        try:
            import tools_i18n
            msg = tools_i18n.translate(str(msg))        # freie Meldungen aus den Modulen (EN-Modus)
        except Exception:
            pass
        try:
            import logsetup
            logsetup.log(msg, tag)
        except Exception:
            pass
        self.log.insert("end", str(msg) + "\n", tag)
        self.log.see("end")
        if int(self.log.index("end-1c").split(".")[0]) > 2000:
            self.log.delete("1.0", "500.0")

    def set_status(self, txt):
        self.lbl_status.configure(text=txt)

    # ------------------------------------------------------------------
    # Projekte
    # ------------------------------------------------------------------
    def reload_projects(self):
        root_dir = self.cfg.get("projects_root", "")
        self.project_list = []
        if root_dir and os.path.isdir(root_dir):
            for name, folder, patches_dir in projects.list_projects(root_dir):
                self.project_list.append((name, folder, patches_dir))
        known = {p[2] for p in self.project_list}
        for key, meta in self.cfg.get("projects", {}).items():
            if key in known or not os.path.isdir(key):
                continue
            nm = meta.get("name") or os.path.basename(os.path.dirname(key))
            self.project_list.append((nm, os.path.dirname(key), key))
        names = [p[0] for p in self.project_list]
        self.project_combo["values"] = names
        self.log_msg(self.tr.t("log_projects_found", n=len(names)), "info")

    def pick_project_folder(self):
        d = filedialog.askdirectory(title=self.tr.t("dlg_pick_project"))
        if not d:
            return
        ok, patches_dir = projects.has_patches(d)
        if not ok:
            messagebox.showerror(self.tr.t("dlg_error"),
                                 self.tr.t("dlg_no_patches", folder=d))
            return
        name = os.path.basename(d)
        self.cfg.setdefault("projects", {}).setdefault(patches_dir, {})
        self.cfg["projects"][patches_dir]["name"] = name
        projects.save_config(self.cfg)
        self.reload_projects()
        self.select_project_by_name(name)

    def select_project_by_name(self, name):
        for nm, _, _ in self.project_list:
            if nm == name:
                self.project_var.set(nm)
                self.on_project_selected(None)
                return

    def open_library_entry(self, entry):
        """Aus der Bibliothek: das Projekt (Patch-Ordner) des Spiels im Hauptfenster öffnen."""
        pdir = entry.project_dir
        if not pdir or not os.path.isdir(pdir):
            self.log_msg(f"[library] {entry.title}: kein Patch-Ordner", "warn")
            return False
        for nm, _folder, patches_dir in self.project_list:
            if os.path.abspath(patches_dir) == os.path.abspath(pdir):
                self.select_project_by_name(nm)
                return True
        name = entry.title or os.path.basename(pdir)
        self.cfg.setdefault("projects", {}).setdefault(pdir, {})["name"] = name
        projects.save_config(self.cfg)
        self.reload_projects()
        self.select_project_by_name(name)
        return True

    def add_patch_from_file(self, path, target_dir=None):
        """Patch-Datei hinzufügen.

        Mit geöffnetem Projekt wird sie in dessen Patch-Ordner kopiert (oder in `target_dir`).
        Ohne Projekt wird der Ordner der Datei selbst als Projekt angelegt.  Rückgabe: Zielpfad."""
        if not is_patch_file(path):
            raise ValueError(f"Keine bekannte Patch-Datei: {os.path.basename(path)}")
        ReapPatch.load(path)                        # wirft bei kaputten/verschlüsselten Dateien
        dest_dir = target_dir or self.PATCH_DIR
        if not dest_dir or not os.path.isdir(dest_dir):
            folder = os.path.dirname(os.path.abspath(path))
            self.cfg.setdefault("projects", {}).setdefault(folder, {})["name"] = \
                os.path.basename(folder) or folder
            projects.save_config(self.cfg)
            self.reload_projects()
            self.select_project_by_name(self.cfg["projects"][folder]["name"])
            self.log_msg(self.tr.t("log_added_patch", name=os.path.basename(path)), "ok")
            return path
        dest = os.path.join(dest_dir, os.path.basename(path))
        if os.path.abspath(dest) != os.path.abspath(path):
            base, ext = os.path.splitext(dest)
            n = 1
            while os.path.exists(dest):                # nichts überschreiben
                n += 1
                dest = f"{base}_{n}{ext}"
            shutil.copy2(path, dest)
        self.log_msg(self.tr.t("log_added_patch", name=os.path.basename(dest)), "ok")
        if os.path.abspath(dest_dir) == os.path.abspath(self.PATCH_DIR or ""):
            self.load_patches()
        return dest

    def on_project_selected(self, ev):
        name = self.project_var.get()
        for nm, folder, patches_dir in self.project_list:
            if nm != name:
                continue
            self.current_project = nm
            self.PATCH_DIR = patches_dir
            self.IMAGE_BASE = projects.get_image_base(self.cfg, nm, patches_dir)
            self.imgbase_var.set(hex(self.IMAGE_BASE))
            self.cfg["last_project"] = nm
            projects.save_config(self.cfg)
            self._set_title(f"\u25b8  {nm.upper()}")
            self.log_msg(self.tr.t("log_project", name=nm), "accent")
            self.log_msg(self.tr.t("log_patches_dir", path=patches_dir), "info")
            self.log_msg(self.tr.t("log_base", base=f"{self.IMAGE_BASE:#x}"), "info")
            self.tools_stash = None
            try:
                self._load_game_profile()
            except Exception as e:
                self.log_msg(f"[profil] {e}", "warn")
            self.load_patches()
            self._auto_load_session()
            return

    def _auto_load_session(self):
        """Liegt neben dem Patch-Ordner eine .cheatsession.json, wird sie geladen - ohne etwas
        auf der Konsole zu verändern (nur Merkliste, Cheat-Liste, Pointer)."""
        path = session.find_auto(self.PATCH_DIR)
        if not path:
            return
        try:
            info = session.apply(self, session.load(path), activate=False)
            self.log_msg(f"[session] {os.path.basename(path)}: {info['cheats']} Cheat(s), "
                         f"{info['patches']} Patch(es) vorgemerkt", "accent")
        except Exception as e:
            self.log_msg(f"[session] {os.path.basename(path)}: {e}", "warn")

    def apply_imgbase(self):
        try:
            v = int(self.imgbase_var.get(), 16)
        except Exception:
            messagebox.showerror(self.tr.t("dlg_error"), self.tr.t("dlg_imgbase_bad"))
            return
        self.IMAGE_BASE = v
        self.cfg["image_base"] = hex(v)
        if self.current_project and self.PATCH_DIR:
            projects.set_image_base(self.cfg, self.current_project, self.PATCH_DIR, v)
        AOB.clear_cache()
        self.log_msg(self.tr.t("log_base_set", base=f"{v:#x}"), "accent")
        self.load_patches()

    # ------------------------------------------------------------------
    # Verbindung
    # ------------------------------------------------------------------
    def connect(self):
        """Werte hier (UI-Thread) lesen - Tk-Variablen dürfen nicht aus Threads angefasst werden."""
        host = self.ip_var.get().strip()
        try:
            port = int(self.port_var.get())
        except ValueError:
            port = 744
        self.set_status(self.tr.t("status_connecting"))
        self.log_msg(self.tr.t("log_connecting", ip=host, port=port), "info")
        threading.Thread(target=self._do_connect, args=(host, port), daemon=True).start()

    def _do_connect(self, host, port):
        try:
            self.backend.host = host
            self.backend.port = port
            self.cfg["ps5_ip"] = host
            self.cfg["ps5_port"] = port
            projects.save_config(self.cfg)

            try:
                self.backend.connect()
                pid = self.backend.find_pid()
            except Exception as first_err:
                self.q.put(("log",
                    (f"[net] Port {self.backend.port} fehlgeschlagen "
                     f"({first_err}) - suche Payload...", "warn")))
                from ps5_client import PS5DebugClient
                client, port_used = PS5DebugClient.connect_auto(
                    self.backend.host, timeout=2.5
                )
                old = self.backend.client
                if old is not None and old is not client:
                    old.close()
                self.backend.client = client
                self.backend.port = port_used
                self.q.put(("port", port_used))
                self.cfg["ps5_port"] = port_used
                projects.save_config(self.cfg)
                pid = self.backend.find_pid()
                self.q.put(("log",
                    (f"[net] Auto-Detect erfolgreich: Port {port_used}", "ok")))

            AOB.clear_cache()
            self._check_image_base()
            self._connected = True
            self._want_connected = True
            self._lost_notified = False
            self.q.put(("status", self.tr.t("status_connected", pid=pid)))
            self.q.put(("log", (self.tr.t("log_conn_ok", pid=pid), "ok")))
            self.q.put(("fx", ("granted", {"host": self.backend.host, "port": self.backend.port, "pid": pid})))
            self.notifier.connected(pid)
            # Anzeige mit der Wirklichkeit abgleichen (Spiel evtl. neu gestartet seit letzter Sitzung)
            self._sync_all()
            self._detect_codes()

        except Exception as e:
            self._connected = False
            self.q.put(("status", self.tr.t("status_conn_fail", err=e)))
            self.q.put(("log", (self.tr.t("log_conn_fail", err=e), "err")))
            self.q.put(("fx", ("denied", {"error": e})))

    def _trainer_preflight(self, card):
        """Cave-Trainer: vor dem Aktivieren der BASIS pruefen, ob die gespeicherten Signaturen zum laufenden Build passen.
        Wirft RuntimeError mit klarem Text statt blind zu schreiben.  Trainer ohne Signaturen werden nicht geprueft."""
        import json as _json
        import cave_trainer as _TR
        if os.path.basename(card.path) != _TR.BASE_FILE:
            return
        spec_path = os.path.join(os.path.dirname(card.path), _TR.SPEC_FILE)
        try:
            with open(spec_path, encoding="utf-8") as f:
                spec = _json.load(f)
            maps = [(m[0], m[1], m[2]) for m in self.backend.client.get_maps()]
            res = _TR.check_anchors(self.backend.client, maps, self.IMAGE_BASE, spec)
        except FileNotFoundError:
            return
        except Exception as e:  # noqa: BLE001 - Pruefung ist nur eine Hilfe
            self.q.put(("log", (f"[trainer] Build-Pruefung nicht moeglich: {e}", "warn")))
            return
        problem = _TR.anchor_problem(res, self.IMAGE_BASE)
        if problem:
            raise RuntimeError(problem)
        if res:
            self.q.put(("log", ("[trainer] Build-Pruefung: Signaturen passen zum laufenden Spiel", "ok")))

    def _check_image_base(self):
        """Image-Basis mit dem laufenden Spiel abgleichen (Thread-sicher: Aenderungen gehen ueber die Queue).
        Ein falscher Wert (frueher fest 0x400000) fuehrt zu 'kein Platz fuer die Cave', 'schon aktiv' oder
        Patches ohne Wirkung."""
        try:
            maps = self.backend.client.get_maps_named()
        except Exception as e:
            self.q.put(("log", (f"[basis] Memory-Maps nicht lesbar: {e}", "warn")))
            return
        det, ok, text = IMB.check_base(maps, self.IMAGE_BASE)
        if det is None:
            mods = ", ".join(f"{n}@{a:#x}" for n, a, _b, _c in IMB.module_summary(maps, 8))
            self.q.put(("log", (f"[basis] {text}. Module: {mods}", "warn")))
            return
        if ok:
            self.q.put(("log", (f"[basis] {text}", "info")))
            return
        self.q.put(("log", (f"[basis] {text}", "warn")))
        self.q.put(("log", (f"[basis] Setze Image-Basis automatisch auf {det:#x}", "accent")))
        self.q.put(("imgbase", det))

    # ------------------------------------------------------------------
    # Patches laden / Karten
    # ------------------------------------------------------------------
    def load_patches(self):
        if not self.PATCH_DIR or not os.path.isdir(self.PATCH_DIR):
            self.log_msg(self.tr.t("log_patches_none"), "warn")
            return
        self.patches.clear()
        self.applied.clear()
        self.wanted = set()
        self._load_state()

        for f in sorted(os.listdir(self.PATCH_DIR)):
            if not is_patch_file(f):
                continue
            path = os.path.join(self.PATCH_DIR, f)
            try:
                rp = ReapPatch.load(path)
                if not rp.origin_source:
                    self.log_msg(self.tr.t("log_patch_noorigin", name=f), "warn")
                    continue
                self.patches[path] = rp
            except Exception as e:
                self.log_msg(self.tr.t("log_patch_error", name=f, err=e), "err")

        self.log_msg(self.tr.t("log_patches_load", n=len(self.patches)), "accent")
        if self.gp is not None:                                  # Profil-Eintraege geloeschter Cheat-Dateien aufraeumen
            before = (len(self.gp.favorites), len(self.gp.groups), len(self.gp.hotkeys))
            self.gp.forget_missing([f for f in os.listdir(self.PATCH_DIR) if is_patch_file(f)])
            if before != (len(self.gp.favorites), len(self.gp.groups), len(self.gp.hotkeys)):
                self.gp.save()
        self.wanted &= set(self.patches)
        self._rebuild_cards()
        if self._connected:
            threading.Thread(target=self._sync_all, daemon=True).start()

    def _rebuild_cards(self):
        for c in self.cards_frame.winfo_children():
            c.destroy()
        self.cards.clear()
        self._cols = 0

        for path, rp in sorted(self.patches.items(), key=lambda kv: kv[1].name.lower()):
            card = CheatCard(self.cards_frame, path, rp, self)
            self.cards[path] = card
            if path in self.applied:
                card.set_state(St.ON, self.applied[path].get("cave_addr"))
        self._rebuild_hotkeys()
        width = self.cards_canvas.winfo_width()
        self._grid_cards(max(1, width // CARD_MIN_W) if width > 1 else 4)
        self._update_count()

    def _grid_cards(self, cols):
        """Karten auf `cols` Spalten verteilen (passt sich der Fensterbreite an)."""
        for c in range(max(cols, self._cols)):
            self.cards_frame.columnconfigure(c, weight=1 if c < cols else 0,
                                             uniform="card" if c < cols else "")
        order = self._visible_paths()
        shown = set(order)
        for path, card in self.cards.items():
            if path not in shown:
                card.grid_remove()
        for idx, path in enumerate(order):
            self.cards[path].grid(row=idx // cols, column=idx % cols, padx=8, pady=10, sticky="nsew")
        self._cols = cols

    # ------------------------------------------------------------------
    # Suche / Favoriten / Gruppen / Hotkeys (Spiel-Profil)
    # ------------------------------------------------------------------
    def _group_filter(self):
        import cheatlist
        sel = self.v_group.get() if hasattr(self, "v_group") else ""
        if sel == self.tr.t("filter_nogroup"):
            return cheatlist.NO_GROUP
        if sel in ("", self.tr.t("filter_all")):
            return cheatlist.ALL
        return sel

    def _visible_paths(self):
        import cheatlist
        items = [(p, c.rp.name or os.path.basename(p)) for p, c in self.cards.items()]
        return cheatlist.visible_order(items, self.gp, self.v_search.get() if hasattr(self, "v_search") else "",
                                       self._group_filter(), bool(getattr(self, "v_favonly", None) and self.v_favonly.get()))

    def _refresh_group_values(self):
        if not hasattr(self, "group_combo"):
            return
        names = self.gp.group_names() if self.gp else []
        keep = self.v_group.get()
        self.group_combo.configure(values=[self.tr.t("filter_all"), self.tr.t("filter_nogroup")] + names)
        if keep not in [self.tr.t("filter_all"), self.tr.t("filter_nogroup")] + names:
            self.v_group.set(self.tr.t("filter_all"))

    def _apply_filter(self, *_):
        if self.gp is not None:
            self.gp.ui["group"] = self.v_group.get()
            self.gp.ui["only_fav"] = bool(self.v_favonly.get())
        if self.cards:
            self._grid_cards(self._cols or 4)

    def _load_game_profile(self):
        """Profil des offenen Projekts laden (Titel-ID aus Projektname/-pfad, sonst Projektname)."""
        import gameprofile
        import library
        tid = library.extract_id(self.current_project, self.PATCH_DIR)
        key = gameprofile.key_for(tid, self.current_project or "")
        if self.gp is None or self.gp.key != key:
            self.gp = gameprofile.load(key)
        self.gp.title = self.current_project or self.gp.title
        if hasattr(self, "v_group"):
            self.v_group.set(self.gp.ui.get("group") or self.tr.t("filter_all"))
            self.v_favonly.set(bool(self.gp.ui.get("only_fav")))
        self._refresh_group_values()

    def _profile_changed(self):
        """Nach Favorit/Gruppe/Hotkey: speichern und Anzeige auffrischen."""
        if self.gp is not None:
            self.gp.save()
        for c in self.cards.values():
            c.refresh_meta()
        self._refresh_group_values()
        self._rebuild_hotkeys()
        self._grid_cards(self._cols or 4)

    def toggle_favorite(self, card):
        self.gp.toggle_favorite(os.path.basename(card.path))
        self._profile_changed()

    def set_card_group(self, card):
        fn = os.path.basename(card.path)
        name = simpledialog.askstring(self.tr.t("dlg_group_title"), self.tr.t("dlg_group_prompt", name=card.rp.name or fn),
                                      initialvalue=self.gp.groups.get(fn, ""), parent=self.root)
        if name is None:
            return
        self.gp.set_group(fn, name)
        self._profile_changed()

    def clear_card_hotkey(self, card):
        self.gp.clear_hotkey(os.path.basename(card.path))
        self._profile_changed()

    def _rebuild_hotkeys(self):
        self._hotkeys = {}
        if self.gp:
            for path in self.cards:
                spec = self.gp.hotkeys.get(os.path.basename(path))
                if spec:
                    self._hotkeys[spec] = path

    def _hotkey_chosen(self, card, spec):
        """Ergebnis der Tastenwahl anwenden -> 'ok' | 'bad' | 'conflict:<Name>' | 'wait' (nur Modifier gedrueckt)."""
        import cheatlist
        if spec is None:
            return "wait"
        if not cheatlist.valid_spec(spec):
            self.log_msg(self.tr.t("log_hotkey_bad", hk=spec), "warn")
            return "bad"
        owner = self.gp.set_hotkey(os.path.basename(card.path), spec)
        if owner:
            self.log_msg(self.tr.t("log_hotkey_conflict", hk=spec, owner=owner), "warn")
            return f"conflict:{owner}"
        self.log_msg(self.tr.t("log_hotkey_set", hk=spec, name=card.rp.name), "ok")
        self._profile_changed()
        return "ok"

    def capture_hotkey(self, card):
        """Kleines Fenster: naechste Tastenkombination aufnehmen (Esc = abbrechen)."""
        import cheatlist
        top = tk.Toplevel(self.root)
        top.title(self.tr.t("dlg_hotkey_title"))
        top.configure(bg=BG)
        top.transient(self.root)
        tk.Label(top, text=self.tr.t("dlg_hotkey_prompt", name=card.rp.name or "?"), bg=BG, fg=TEXT, font=FONT_LABEL,
                 justify="left", padx=24, pady=20).pack()

        def on_key(ev):
            if ev.keysym == "Escape":
                top.destroy()
                return "break"
            res = self._hotkey_chosen(card, cheatlist.spec_from_event(ev.keysym, ev.state))
            if res != "wait":
                top.destroy()
            return "break"
        top.bind("<KeyPress>", on_key)
        top.focus_force()
        try:
            top.grab_set()
        except Exception:
            pass

    def _on_key(self, ev):
        """Globaler (Programmfenster-)Hotkey: schaltet den zugeordneten Cheat um."""
        import cheatlist
        if not self._hotkeys:
            return None
        try:
            cls = ev.widget.winfo_class()
        except Exception:
            cls = ""
        if cheatlist.typing_in_text(cls):
            return None
        spec = cheatlist.spec_from_event(ev.keysym, ev.state)
        card = self.cards.get(self._hotkeys.get(spec))
        if card is None:
            return None
        now = time.time()
        if self._last_hot[0] == spec and now - self._last_hot[1] < 0.4:        # Tastenwiederholung ignorieren
            return "break"
        self._last_hot = (spec, now)
        self.log_msg(self.tr.t("log_hotkey_fire", hk=spec, name=card.rp.name), "info")
        card._click()
        return "break"

    def _update_count(self):
        total = len(self.cards)
        active = sum(1 for c in self.cards.values() if c.state == St.ON)
        self.lbl_count.configure(
            text=self.tr.t("count_format", active=active, total=total))

    # ------------------------------------------------------------------
    # Zustand (applied.json)
    # ------------------------------------------------------------------
    def _state_file(self):
        return os.path.join(self.PATCH_DIR, "applied.json") if self.PATCH_DIR else None

    def _save_state(self):
        p = self._state_file()
        if not p:
            return
        try:
            data = {"_meta": {"pid": self.backend.pid, "wanted": sorted(self.wanted)},
                    "entries": {k: _enc(st) for k, st in self.applied.items()}}
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
            os.replace(tmp, p)                      # atomar: nie eine halb geschriebene Datei
        except Exception as e:
            self.q.put(("log", (f"[state] {e}", "err")))

    def _load_state(self):
        """Lädt Merkliste + gespeicherte Zustände. Die Zustände gelten nur, solange die PID noch
        dieselbe ist - nach einem Spiel-Neustart ist nichts mehr gepatcht."""
        self._saved_entries, self._saved_pid = {}, None
        p = self._state_file()
        if not p or not os.path.isfile(p):
            return
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            if "entries" in data:                    # neues Format
                meta, entries = data.get("_meta", {}), data["entries"]
            else:                                    # altes Format: Datei = Einträge, ohne PID
                meta, entries = {}, data
            self._saved_pid = meta.get("pid")
            self.wanted = set(meta.get("wanted", [])) | set(entries)
            for k, st in entries.items():
                self._saved_entries[k] = _dec_state(st)
            if self._saved_pid is not None and self._saved_pid == self.backend.pid:
                self.applied.update(self._saved_entries)
        except Exception as e:
            self.log_msg(f"[state] {e}", "err")

    def _make_state(self, path, rp, hook, cave):
        """Zustand eines bereits aktiven Patches rekonstruieren (Original-Bytes aus gespeichertem
        Zustand, falls dieselbe PID, sonst aus dem defaultValue)."""
        st = self._saved_entries.get(path)
        if st and self._saved_pid == self.backend.pid and st.get("hook_addr") == hook:
            return st
        try:
            orig = _asm_or_empty(self.backend, rp.origin_source[1], hook)
        except Exception:
            orig = None
        return {"hook_addr": hook, "cave_addr": cave, "original_bytes": orig,
                "size": len(orig) if orig else 8, "cave_region_size": 0x4000,
                "simple": not is_cave_patch(rp)}

    # ------------------------------------------------------------------
    # Aktivieren / Deaktivieren
    # ------------------------------------------------------------------
    def card_clicked(self, card):
        if not self._connected:
            self.log_msg(self.tr.t("log_not_conn"), "warn")
            return
        if card.state == St.LOAD:
            return
        if card.state == St.ON:
            threading.Thread(target=self._do_deactivate, args=(card,), daemon=True).start()
        else:
            threading.Thread(target=self._do_activate, args=(card,), daemon=True).start()

    def _do_activate(self, card):
        with self._patch_lock:
            self.q.put(("card_state", (card, St.LOAD, None)))
            try:
                rp = card.rp
                if not rp.origin_source:
                    raise RuntimeError(self.tr.t("log_patch_noorigin", name=rp.name))
                hook = self._hook(rp)
                self._trainer_preflight(card)
                typ = self.tr.t("type_cave") if is_cave_patch(rp) else self.tr.t("type_patch")

                patched, cave0, _t = detect_patched(self.backend, rp, hook)
                if patched:                          # schon aktiv: NICHT erneut patchen
                    self.applied[card.path] = self._make_state(card.path, rp, hook, cave0)
                    self.wanted.add(card.path)
                    self._save_state()
                    self.q.put(("log", (self.tr.t("log_skip_active", name=rp.name), "warn")))
                    self.q.put(("card_state", (card, St.ON, cave0)))
                    return

                self.q.put(("log", (self.tr.t("log_activate", name=rp.name, typ=typ,
                                              hook=f"{hook:#x}"), "head")))
                state = apply_patch(self.backend, rp, hook)
                self.applied[card.path] = state
                self.wanted.add(card.path)
                self._save_state()
                cave = state.get("cave_addr")
                info = f"cave={cave:#x}" if cave else f"size={state.get('size', 0)}"
                self.q.put(("log", (self.tr.t("log_activated", name=rp.name, info=info), "ok")))
                self.q.put(("card_state", (card, St.ON, cave)))
                self.notifier.cheat(True, rp.name)

            except Exception as e:
                self.q.put(("log", (self.tr.t("log_error", name=card.rp.name, err=e), "err")))
                self.q.put(("card_state", (card, St.ERROR, None)))

    def _do_deactivate(self, card):
        with self._patch_lock:
            self.q.put(("card_state", (card, St.LOAD, None)))
            try:
                rp = card.rp
                state = self.applied.get(card.path)
                if state is None:                    # z.B. nach Neustart von ReaperPy
                    hook = self._hook(rp)
                    patched, cave, _t = detect_patched(self.backend, rp, hook)
                    if patched:
                        state = self._make_state(card.path, rp, hook, cave)
                if state is not None:
                    deactivate_patch(self.backend, rp, state)
                self.applied.pop(card.path, None)
                self.wanted.discard(card.path)
                self._save_state()
                self.q.put(("log", (self.tr.t("log_deactivated", name=rp.name), "ok")))
                self.q.put(("card_state", (card, St.OFF, None)))
                self.notifier.cheat(False, rp.name)

            except Exception as e:
                self.q.put(("log", (self.tr.t("log_error", name=card.rp.name, err=e), "err")))
                self.q.put(("card_state", (card, St.ERROR, None)))

    def show_info(self, rp):
        InfoDialog(self.root, rp, self.IMAGE_BASE, self.tr)

    # --- Sammel-Aktionen mit Fortschrittsbalken ---
    def _run_bulk(self, cards, fn):
        n = len(cards)
        if not n:
            return
        self.notifier.bulk_begin()                  # Sammelaktion: eine Zusammenfassung statt n Meldungen
        try:
            for i, card in enumerate(cards):
                self.q.put(("progress", (i, n)))
                fn(card)
        finally:
            self.notifier.bulk_end()
        self.q.put(("progress", (n, n)))
        self.q.put(("progress_done", None))

    def activate_all(self):
        if not self._connected:
            self.log_msg(self.tr.t("log_not_conn"), "warn"); return
        threading.Thread(target=self._do_all_on, daemon=True).start()

    def _do_all_on(self):
        cards = [c for c in self.cards.values() if c.state in (St.OFF, St.ERROR)]
        self._run_bulk(cards, self._do_activate)

    def activate_paths(self, paths):
        """Bestimmte Patches (z.B. aus einer Sitzung) einschalten."""
        if not self._connected:
            self.log_msg(self.tr.t("log_not_conn"), "warn"); return
        cards = [self.cards[p] for p in paths if p in self.cards and self.cards[p].state != St.ON]
        threading.Thread(target=self._run_bulk, args=(cards, self._do_activate), daemon=True).start()

    def deactivate_all(self):
        if not self._connected:
            self.log_msg(self.tr.t("log_not_conn"), "warn"); return
        if not messagebox.askyesno(self.tr.t("dlg_deact_all"),
                                   self.tr.t("dlg_deact_all_q", n=len(self.applied))):
            return
        threading.Thread(target=self._do_all_off, daemon=True).start()

    def _do_all_off(self):
        cards = [c for c in self.cards.values() if c.state == St.ON]
        self._run_bulk(cards, self._do_deactivate)

    # ------------------------------------------------------------------
    # Status-Scan / Abgleich
    # ------------------------------------------------------------------
    def refresh_status(self):
        if not self._connected:
            self.log_msg(self.tr.t("log_not_conn"), "warn"); return
        self.log_msg(self.tr.t("log_scan_start"), "head")
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        self._sync_all(verbose=True)

    def _sync_all(self, verbose=False):
        """Liest für jeden Patch, ob er im Speicher gepatcht ist, und passt Karten/Zustand an."""
        active = 0
        with self._patch_lock:
            items = list(self.patches.items())
            for i, (path, rp) in enumerate(items):
                if not rp.origin_source:
                    continue
                try:
                    hook = self._hook(rp)
                    patched, cave, typ = detect_patched(self.backend, rp, hook)
                except Exception as e:
                    self.q.put(("log", (f"{rp.name}: {e}", "err")))
                    continue
                card = self.cards.get(path)
                if patched:
                    active += 1
                    if path not in self.applied:
                        self.applied[path] = self._make_state(path, rp, hook, cave)
                    if card and card.state != St.ON:
                        self.q.put(("card_state", (card, St.ON, cave)))
                    if verbose:
                        self.q.put(("log", (self.tr.t("log_scan_active", name=rp.name, typ=typ), "ok")))
                else:
                    self.applied.pop(path, None)
                    if card and card.state != St.OFF:
                        self.q.put(("card_state", (card, St.OFF, None)))
                    if verbose:
                        self.q.put(("log", (self.tr.t("log_scan_inactive", name=rp.name), "info")))
            self._save_state()
        if not verbose and active:
            self.q.put(("log", (self.tr.t("log_sync", n=active), "info")))
        return active

    # ------------------------------------------------------------------
    # Watchdog: PID-Wechsel / Verbindungsverlust / Auto-Reconnect
    # ------------------------------------------------------------------
    def _watch_pid(self):
        self.root.after(2000, self._watch_pid)
        if not self._want_connected or self._watch_busy or self.debug_busy:
            return
        self._watch_busy = True
        threading.Thread(target=self._watch_job, daemon=True).start()

    def _watch_job(self):
        try:
            be, auto = self.backend, self._auto
            try:
                alive = bool(be.client) and be.client.ping()
            except Exception:
                alive = False

            if alive:
                self._watch_misses = 0
            elif self._connected and self._watch_misses < 2:
                self._watch_misses += 1                         # ein/zwei verpasste Pings (Last, WLAN) sind noch kein Abbruch
                return
            if not alive:                                       # Verbindung weg
                if self._connected or not self._lost_notified:
                    self._connection_lost()
                if not auto:
                    return
                try:
                    be.connect()                                # Payload wieder da?
                except Exception:
                    return                                      # nächster Tick
                alive = True                                    # weiter mit PID-Prüfung

            try:
                pid = be.lookup_pid()
            except Exception:
                return
            if pid is None:                                     # Spiel läuft nicht
                if self._connected or not self._lost_notified:
                    self._game_closed()
                return
            if pid == be.pid and self._connected:
                return                                          # alles beim Alten

            # neue PID oder wieder erreichbar
            if not auto:
                if self._connected or not self._lost_notified:
                    self._connection_lost(new_pid=pid if pid != be.pid else None)
                return
            self._adopt_game(pid)
        finally:
            self._watch_busy = False

    def _connection_lost(self, new_pid=None):
        self._connected = False
        self._lost_notified = True
        self.q.put(("status", self.tr.t("status_lost")))
        self.q.put(("log", (self.tr.t("log_watch_lost") if new_pid is None
                            else self.tr.t("log_watch_pid", old=self.backend.pid, new=new_pid), "warn")))
        self._forget_active()

    def _game_closed(self):
        self._connected = False
        self._lost_notified = True
        self.q.put(("status", self.tr.t("status_waiting_game")))
        self.q.put(("log", (self.tr.t("log_watch_gone"), "warn")))
        self._forget_active()
        self.q.put(("game_changed", None))

    def _update_check_async(self):
        """Hintergrund-Pruefung auf neue Version (nur mit eingestellter "update_url"; laedt nichts herunter)."""
        url = self.cfg.get("update_url", "")
        if not url or not self.cfg.get("auto_update_check", True):
            return
        import update_check
        import version

        def job():
            self.q.put(("update", update_check.check(url, version.__version__)))
        threading.Thread(target=job, daemon=True).start()

    def _on_update(self, res):
        if res.status == "newer":
            self.log_msg(self.tr.t("log_update_new", ver=res.remote, cur=res.local, url=res.url or "-"), "accent")

    def _detect_codes(self):
        """Arbeits-Thread: Vordergrund-Spiel erkennen und passende Codes (Patches) vorschlagen -> UI-Queue."""
        if not self.cfg.get("auto_codes", True):
            return
        import autocodes
        det = autocodes.detect(self.backend.client, self.cfg, projects.DEFAULTS)
        if det.error and not det.title_id:
            self.q.put(("log", (self.tr.t("log_codes_noid", err=det.error), "info")))
            return
        self.q.put(("codes", det))

    def _apply_codes(self, det):
        """UI-Thread: Codes des erkannten Spiels laden oder die Liste leeren."""
        import autocodes
        cur = f"{self.current_project or ''} {self.PATCH_DIR or ''}".strip()
        action, entry = autocodes.decide(det, cur)
        game = f"{det.name or det.title_id} ({det.title_id})"
        if action == "load":
            if self.open_library_entry(entry):
                self.log_msg(self.tr.t("log_codes_loaded", game=game, n=len(self.patches)), "ok")
        elif action == "clear":
            self.current_project = None
            self.PATCH_DIR = ""
            self.project_var.set("")
            self.patches.clear()
            self.applied.clear()
            self.wanted = set()
            self._rebuild_cards()
            self._update_count()
            self._set_title(self.tr.t("no_project"))
            self.log_msg(self.tr.t("log_codes_none", game=game), "info")
        else:
            self.log_msg(self.tr.t("log_codes_keep", game=game), "info")

    def _forget_active(self):
        """Nichts ist mehr gepatcht (Spiel beendet / Verbindung weg): Karten zurück auf AUS.
        Die Merkliste `wanted` bleibt für die Wiederherstellung erhalten."""
        with self._patch_lock:
            self.applied.clear()
        for card in list(self.cards.values()):
            if card.state != St.OFF:
                self.q.put(("card_state", (card, St.OFF, None)))
        AOB.clear_cache()

    def _wait_game_ready(self, timeout=90):
        """Wartet, bis das frisch gestartete Spiel seine Speicherkarte fertig aufgebaut hat
        (zwei gleiche Messungen hintereinander + Mindestwartezeit). Zu frühes Patchen kann das Spiel
        beim Laden abstürzen lassen."""
        settle = float(self.cfg.get("reconnect_settle", 4))
        t0, last, stable = time.time(), None, 0
        while time.time() - t0 < timeout:
            maps = self.backend.get_maps(force=True)
            sig = (len(maps), sum(1 for _s, _e, p in maps if p & 4))
            stable = stable + 1 if (sig == last and sig[1] > 0) else 0
            last = sig
            if stable >= 2 and time.time() - t0 >= settle:
                return True
            time.sleep(1.5)
        return False

    def _adopt_game(self, pid):
        be = self.backend
        old = be.pid
        be.adopt_pid(pid)
        AOB.clear_cache()
        if old != pid:
            self.q.put(("log", (self.tr.t("log_watch_pid", old=old, new=pid), "accent")))
            self.q.put(("status", self.tr.t("status_waiting_game")))
            self._wait_game_ready()
        self._connected = True
        self._lost_notified = False
        self.q.put(("status", self.tr.t("status_reconnected", pid=pid)))
        self.notifier.connected(pid)
        self.q.put(("game_changed", None))
        self._detect_codes()
        self._sync_all()                                        # was ist (noch) gepatcht?
        self._restore_applied()

    def _restore_applied(self):
        """Merkt sich der Anwender Patches (wanted), die jetzt nicht aktiv sind, werden sie wieder
        eingeschaltet - mit Fortschrittsbalken."""
        todo = [self.cards[p] for p in sorted(self.wanted)
                if p in self.cards and p not in self.applied]
        if not todo:
            return
        self.q.put(("log", (self.tr.t("log_watch_ready", n=len(todo)), "accent")))
        self._run_bulk(todo, self._do_activate)
        ok = sum(1 for c in todo if c.path in self.applied)
        self.q.put(("log", (self.tr.t("log_restore_done", ok=ok, n=len(todo)),
                            "ok" if ok == len(todo) else "warn")))

    # ------------------------------------------------------------------
    # UI-Queue
    # ------------------------------------------------------------------
    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    if isinstance(val, tuple):
                        self.log_msg(val[0], val[1])
                    else:
                        self.log_msg(val)
                elif kind == "status":
                    self.set_status(val)
                elif kind == "port":
                    self.port_var.set(str(val))
                elif kind == "imgbase":
                    self.imgbase_var.set(hex(val))
                    self.apply_imgbase()
                elif kind == "card_state":
                    card, st, cave = val
                    if card.winfo_exists():
                        card.set_state(st, cave)
                        if st == St.LOAD:
                            card.start_spinner()
                    self._update_count()
                elif kind == "progress":
                    self._progress(*val)
                elif kind == "progress_done":
                    self._progress_done()
                elif kind == "codes":
                    self._apply_codes(val)
                elif kind == "update":
                    self._on_update(val)
                elif kind == "fx":
                    import hackfx
                    hackfx.show(self.root, val[0], val[1], self.cfg)
                elif kind == "game_changed":
                    w = self._tools
                    try:
                        if w is not None and w.winfo_exists():
                            w.on_game_changed()
                    except Exception:
                        pass
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    # ------------------------------------------------------------------
    def on_close(self):
        """Beenden: Debugger sauber lösen (sonst bleibt das Spiel angehalten)."""
        self._want_connected = False
        w = self._tools
        try:
            if w is not None and w.winfo_exists():
                w.close()
        except Exception:
            pass
        try:
            self.notifier.flush(1.0)                # letzte Meldung (z.B. "Debugger detached") noch abschicken
        except Exception:
            pass
        self.root.destroy()


def main():
    import branding
    root = tk.Tk()
    branding.apply_icon(root)
    splash = None
    try:
        cfg = projects.load_config()
    except Exception:
        cfg = {}
    if branding.splash_enabled(cfg):
        root.withdraw()                          # Hauptfenster erst zeigen, wenn der Startbildschirm fertig ist
        import version
        splash = branding.Splash(root, version=f"v{version.__version__}")
        splash.set_status("lade ...")
    App(root)
    if splash is not None:
        splash.finish(on_done=root.deiconify)
    root.mainloop()


if __name__ == "__main__":
    main()
