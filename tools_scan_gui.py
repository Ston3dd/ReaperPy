"""tools_scan_gui.py – Cheat-Searcher-Tab (schnelle Memory-Scans + Cheat-Liste).

Aufbau (drei Spalten oben, Adressliste unten):
  TREFFER (links)  |  SCAN (Mitte: Wert, Typ, Vergleich, Buttons)  |  BEREICHE (rechts: eboot.bin aufgesplittet,
                                                                       Libs & Co. ausblenden -> tools_sections_gui.py)
  ADRESSLISTE (unten): Werte setzen, einfrieren, Beschreibung, Pointer-Scan ...
Alle Funktionen sind ueber Rechtsklick-Menues erreichbar; die selteneren Scan-Optionen liegen im Dialog OPTIONEN.
"""
import struct
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import scanner as SC
import pointerscan as PS
from tools_common import (BG, BG_BAR, BG_CARD, BG_CARD_HVR, BORDER, ACCENT, ACCENT_DIM, TEXT, TEXT_DIM, WARN, ERROR,
                          FONT_LABEL, BaseTab, entry, tree, with_scroll)

SCOPES = {"Daten (rw, ohne Code)": "data", "Alles Schreibbare": "rw", "Alles Lesbare": "all"}
PAGE = 500


# Lese-Tempo-Filter: Regionen, die das Payload langsamer als N MB/s liest, werden ausgelassen
SLOW_CHOICES = {"Tempo-Filter: aus": 0, "auslassen < 100 MB/s": 100, "auslassen < 300 MB/s": 300,
                "auslassen < 600 MB/s": 600, "auslassen < 1000 MB/s": 1000}

# Snapshot-RAM (CMD_PROC_TURBOSCAN_CONFIG): so viel vom Snapshot bleibt im PS5-RAM, der Rest wird ausgelagert.
# 0 = Payload-Standard (512 MB).  Die PS5 unterstuetzt nur bis 2048 MB; ab 3072 MB meldet sie "nicht genug Speicher".
RAM_CHOICES = {"512 MB (Standard)": 0, "1024 MB": 1024, "2048 MB (Maximum)": 2048}
SPILL_CHOICES = {"intern /data (langsam, Standard)": "", "M.2-Erweiterung /mnt/ext1 (falls vorhanden)": "/mnt/ext1",
                 "USB-Stick /mnt/usb0 (falls vorhanden)": "/mnt/usb0"}


def fmt_addr(addr):
    """Adresse kompakt anzeigen: 0x7F12A4 statt 00000000007F12A4 (ohne fuehrende Nullen)."""
    return f"0x{int(addr):X}"


# ----------------------------------------------------------------------------------------------------------------
# Kleine Bausteine fuer das einheitliche Aussehen (Karten, Knoepfe)
# ----------------------------------------------------------------------------------------------------------------
def card(parent, title, bg=BG_CARD):
    """Karte mit Titelleiste -> (aussen, innen, titelleiste).  Weitere Knoepfe/Zaehler kommen rechts in die Titelleiste."""
    outer = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=BORDER)
    head = tk.Frame(outer, bg=BG_BAR)
    head.pack(fill="x")
    tk.Label(head, text=title, bg=BG_BAR, fg=ACCENT_DIM, font=FONT_LABEL).pack(side="left", padx=8, pady=3)
    body = tk.Frame(outer, bg=bg)
    body.pack(fill="both", expand=True, padx=8, pady=6)
    return outer, body, head


def clabel(parent, text, dim=True, bg=BG_CARD, **kw):
    return tk.Label(parent, text=text, bg=bg, fg=TEXT_DIM if dim else TEXT, font=FONT_LABEL, anchor="w", **kw)


def pbtn(parent, text, cmd, primary=False, **kw):
    """Knopf im Karten-Stil: primaer = gefuellt in der Akzentfarbe, sonst dezent mit Hover."""
    bg, fg = (ACCENT, "#04110d") if primary else (BG_CARD_HVR, TEXT)
    hov = "#5dffe0" if primary else "#1f2b40"
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, font=FONT_LABEL, relief="flat", bd=0, padx=10,
                  pady=5, cursor="hand2", highlightthickness=0, activebackground=hov,
                  activeforeground="#04110d" if primary else ACCENT, **kw)
    b.bind("<Enter>", lambda _e: b.configure(bg=hov))
    b.bind("<Leave>", lambda _e: b.configure(bg=bg))
    return b


def _check(parent, text, var, bg=BG_CARD):
    return tk.Checkbutton(parent, text=text, variable=var, bg=bg, fg=TEXT_DIM, selectcolor=BG_CARD,
                          activebackground=bg, activeforeground=ACCENT, font=FONT_LABEL, anchor="w")


class ScanTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.sc = None
        self.running = False
        self.page = 0
        self.entries = []            # Cheat-Liste
        self._tick_n = 0
        self._busy_tick = False

        # Scan-Optionen (Werte leben hier; der Dialog OPTIONEN zeigt sie nur an)
        self.slow_sel = tk.StringVar(value=list(SLOW_CHOICES)[1])
        self.o_float = tk.BooleanVar(value=True)
        self.o_par = tk.BooleanVar(value=True)
        self.o_alias = tk.BooleanVar(value=False)
        self.o_debug = tk.BooleanVar(value=False)
        self.o_small = tk.BooleanVar(value=False)
        self.ram_sel = tk.StringVar(value=list(RAM_CHOICES)[2])
        self.spill_sel = tk.StringVar(value=list(SPILL_CHOICES)[0])

        pw = tk.PanedWindow(self, orient="vertical", bg=BG, sashwidth=5, sashrelief="flat", bd=0)
        pw.pack(fill="both", expand=True, padx=8, pady=8)
        top = tk.Frame(pw, bg=BG)
        bottom = tk.Frame(pw, bg=BG)
        pw.add(top, minsize=260, stretch="always")
        pw.add(bottom, minsize=150, stretch="always")

        # Spalten oben: Bereiche (rechts) und Scan (Mitte) zuerst packen, Treffer nimmt den Rest
        col_c = tk.Frame(top, bg=BG, width=410)
        col_c.pack(side="right", fill="y", padx=(8, 0))
        col_c.pack_propagate(False)
        col_b = tk.Frame(top, bg=BG, width=300)
        col_b.pack(side="right", fill="y", padx=(8, 0))
        col_b.pack_propagate(False)
        col_a = tk.Frame(top, bg=BG)
        col_a.pack(side="left", fill="both", expand=True)

        self._build_results(col_a)
        self._build_scan(col_b)
        self._build_sections(col_c)
        self._build_list(bottom)

        self._ct_values(first=True)
        self._ct_changed()
        self.after(150, self._tick)
        self.after(900, self.panel.auto)
        self.bind("<Map>", lambda _e: self.panel.auto())

    # ------------------------------------------------------------------
    # Aufbau der drei Spalten + Adressliste
    # ------------------------------------------------------------------
    def _build_results(self, parent):
        outer, body, head = card(parent, "TREFFER")
        outer.pack(fill="both", expand=True)
        self.lbl_res = tk.Label(head, text="GEFUNDEN: 0", bg=BG_BAR, fg=TEXT, font=FONT_LABEL)
        self.lbl_res.pack(side="left", padx=(10, 0))
        pbtn(head, "▶", lambda: self._page(1)).pack(side="right", padx=(2, 4), pady=2)
        pbtn(head, "◀", lambda: self._page(-1)).pack(side="right", padx=2, pady=2)
        fr = tk.Frame(body, bg=BG_CARD)
        fr.pack(fill="both", expand=True)
        self.rt = tree(fr, [("a", "ADRESSE"), ("c", "AKTUELL"), ("p", "VORHER"), ("f", "ERSTER")],
                       [140, 100, 100, 100], height=12, anchors={},
                       actions=[("→ Zur Adressliste hinzufügen", self.add_selected),
                                ("→ Alle (Seite) hinzufügen", self.add_all),
                                (None, None),
                                ("Im Speicher anzeigen", self._res_to_hex),
                                ("Adresse kopieren", self._res_copy)])
        with_scroll(fr, self.rt)
        self.rt.bind("<Double-1>", lambda _e: self.add_selected())
        lb = tk.Frame(body, bg=BG_CARD)
        lb.pack(fill="x", pady=(6, 0))
        pbtn(lb, "→ AUSGEWÄHLTE HINZUFÜGEN", self.add_selected, primary=True).pack(side="left")
        pbtn(lb, "→ ALLE (SEITE)", self.add_all).pack(side="left", padx=6)
        clabel(lb, "Doppelklick oder Rechtsklick", dim=True).pack(side="right")

    def _build_scan(self, parent):
        outer, g, _head = card(parent, "SCAN")
        outer.pack(fill="both", expand=True)
        g.grid_columnconfigure(0, weight=3)
        g.grid_columnconfigure(1, weight=2)

        clabel(g, "WERT").grid(row=0, column=0, sticky="w")
        clabel(g, "WERTTYP").grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.v1 = tk.StringVar()
        self.e1 = entry(g, self.v1, 10)
        self.e1.grid(row=1, column=0, sticky="ew", ipady=3)
        self.e1.bind("<Return>", lambda _e: self.scan_first() if not self.sc or not self.sc.first_scan_done
                     else self.scan_next())
        self.vt = tk.StringVar(value="Int32")
        ttk.Combobox(g, textvariable=self.vt, values=list(SC.VTYPES), width=8, state="readonly").grid(
            row=1, column=1, sticky="ew", padx=(8, 0))

        clabel(g, "VERGLEICH").grid(row=2, column=0, sticky="w", pady=(8, 0))
        clabel(g, "BIS").grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(8, 0))
        self.ct = tk.StringVar(value="Genau")
        self.cb_ct = ttk.Combobox(g, textvariable=self.ct, width=20, state="readonly")
        self.cb_ct.grid(row=3, column=0, sticky="ew")
        self.cb_ct.bind("<<ComboboxSelected>>", lambda _e: self._ct_changed())
        self.v2 = tk.StringVar()
        self.e2 = entry(g, self.v2, 8)
        self.e2.grid(row=3, column=1, sticky="ew", padx=(8, 0), ipady=3)

        clabel(g, "BEREICH").grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.scope = tk.StringVar(value="Daten (rw, ohne Code)")
        cb_scope = ttk.Combobox(g, textvariable=self.scope, values=list(SCOPES), width=24, state="readonly")
        cb_scope.grid(row=5, column=0, columnspan=2, sticky="ew")
        cb_scope.bind("<<ComboboxSelected>>", lambda _e: self.panel.on_scope_changed())

        self.b_first = pbtn(g, "ERSTER SCAN", self.scan_first, primary=True)
        self.b_first.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        self.b_next = pbtn(g, "NÄCHSTER SCAN", self.scan_next, primary=True)
        self.b_next.grid(row=6, column=1, sticky="ew", padx=(8, 0), pady=(12, 0))
        pbtn(g, "NEUER SCAN", self.new_scan).grid(row=7, column=0, sticky="ew", pady=(6, 0))
        pbtn(g, "ABBRECHEN", self.cancel).grid(row=7, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))

        self.pb = ttk.Progressbar(g, orient="horizontal", mode="determinate", length=200, maximum=100)
        self.pb.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.lbl = tk.Label(g, text="bereit", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w", justify="left",
                            wraplength=270)
        self.lbl.grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.lbl_mode = clabel(g, "")
        self.lbl_mode.grid(row=10, column=0, columnspan=2, sticky="w")
        pbtn(g, "⚙ OPTIONEN …", self.open_options).grid(row=11, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _build_sections(self, parent):
        from tools_sections_gui import SectionPanel
        outer, body, _head = card(parent, "SPEICHERBEREICHE  -  was gescannt wird")
        outer.pack(fill="both", expand=True)
        self.panel = SectionPanel(body, self)
        self.panel.pack(fill="both", expand=True)

    def _build_list(self, parent):
        outer, body, head = card(parent, "ADRESSLISTE")
        outer.pack(fill="both", expand=True)
        self.v_live = tk.BooleanVar(value=True)
        tk.Checkbutton(head, text="live", variable=self.v_live, bg=BG_BAR, fg=TEXT_DIM, selectcolor=BG_CARD,
                       activebackground=BG_BAR, activeforeground=ACCENT, font=FONT_LABEL).pack(side="right", padx=8)
        fr2 = tk.Frame(body, bg=BG_CARD)
        fr2.pack(fill="both", expand=True)
        self.lt = tree(fr2, [("z", "❄"), ("d", "BESCHREIBUNG"), ("a", "ADRESSE"), ("t", "TYP"), ("v", "WERT")],
                       [30, 220, 160, 80, 140], height=6, anchors={"z": "center"},
                       actions=[("Wert setzen ...", self.set_value),
                                ("Einfrieren / Freigeben", self.toggle_freeze),
                                ("Beschreibung ...", self.rename),
                                (None, None),
                                ("Wer schreibt hierher?", self.who_writes),
                                ("Im Speicher anzeigen", self.to_hex),
                                ("→ Pointer-Scan", self.to_pointer),
                                ("Adresse kopieren", self._list_copy),
                                (None, None),
                                ("Entfernen", self.remove)])
        with_scroll(fr2, self.lt)
        self.lt.bind("<Double-1>", lambda _e: self.set_value())
        self.lt.bind("<Delete>", lambda _e: self.remove())
        ac = tk.Frame(body, bg=BG_CARD)
        ac.pack(fill="x", pady=(6, 0))
        pbtn(ac, "WERT SETZEN", self.set_value, primary=True).pack(side="left")
        pbtn(ac, "❄ FREEZE", self.toggle_freeze).pack(side="left", padx=4)
        pbtn(ac, "BESCHREIBUNG", self.rename).pack(side="left")
        pbtn(ac, "ENTFERNEN", self.remove).pack(side="left", padx=4)
        pbtn(ac, "WER SCHREIBT?", self.who_writes).pack(side="left", padx=(14, 4))
        pbtn(ac, "→ HEX", self.to_hex).pack(side="left")
        pbtn(ac, "→ POINTER-SCAN", self.to_pointer).pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Dialog OPTIONEN (seltene Einstellungen) + Werkzeuge
    # ------------------------------------------------------------------
    def open_options(self):
        if getattr(self, "_dlg", None) is not None:
            try:
                if self._dlg.winfo_exists():
                    return self._dlg.lift()
            except Exception:
                pass
        dlg = tk.Toplevel(self)
        self._dlg = dlg
        dlg.title("Scan-Optionen")
        dlg.configure(bg=BG)
        try:
            dlg.transient(self.winfo_toplevel())
        except Exception:
            pass
        outer, body, _h = card(dlg, "SCAN-OPTIONEN")
        outer.pack(fill="both", expand=True, padx=10, pady=10)
        clabel(body, "Tempo").pack(anchor="w")
        ttk.Combobox(body, textvariable=self.slow_sel, values=list(SLOW_CHOICES), width=30,
                     state="readonly").pack(anchor="w", pady=(0, 6))
        for text, var in (("Float vereinfachen", self.o_float), ("Parallel (schneller)", self.o_par),
                          ("Aliasing (experimentell)", self.o_alias),
                          ("kleine Segmente (<256 KB) auslassen", self.o_small), ("Debug-Log", self.o_debug)):
            _check(body, text, var).pack(anchor="w")
        clabel(body, "SNAPSHOT-RAM").pack(anchor="w", pady=(10, 0))
        ttk.Combobox(body, textvariable=self.ram_sel, values=list(RAM_CHOICES), width=30,
                     state="readonly").pack(anchor="w")
        clabel(body, "AUSLAGERN NACH").pack(anchor="w", pady=(6, 0))
        ttk.Combobox(body, textvariable=self.spill_sel, values=list(SPILL_CHOICES), width=40,
                     state="readonly").pack(anchor="w")
        clabel(body, "(nur 'Unbekannter Startwert': mehr RAM = viel schneller, belegt aber PS5-Speicher)",
               dim=True).pack(anchor="w", pady=(4, 8))
        row = tk.Frame(body, bg=BG_CARD)
        row.pack(fill="x")
        pbtn(row, "SELBSTTEST", self.selftest).pack(side="left")
        pbtn(row, "REGIONEN-BERICHT", self.region_report).pack(side="left", padx=6)
        pbtn(row, "SCHLIESSEN", dlg.destroy, primary=True).pack(side="right")

    def scope_key(self):
        return SCOPES.get(self.scope.get(), "data")

    # ------------------------------------------------------------------
    # Vergleichs-Auswahl
    # ------------------------------------------------------------------
    def _ct_values(self, first):
        vals = [k for k in SC.CTYPES if (k not in SC.NEXT_ONLY if first else k not in SC.FIRST_ONLY)]
        self.cb_ct["values"] = vals
        if self.ct.get() not in vals:
            self.ct.set(vals[0])

    def _ct_changed(self):
        need = SC.CTYPES[self.ct.get()][1]
        self.e1.configure(state="normal" if need >= 1 else "disabled")
        self.e2.configure(state="normal" if need >= 2 else "disabled")

    def _opts(self):
        return {"float_simple": self.o_float.get(), "aliasing": self.o_alias.get(), "parallel": self.o_par.get(),
                "min_region": 256 * 1024 if self.o_small.get() else 0,
                "snap_ram_mb": RAM_CHOICES[self.ram_sel.get()], "spill_dir": SPILL_CHOICES[self.spill_sel.get()]}

    # ------------------------------------------------------------------
    # Sitzung
    # ------------------------------------------------------------------
    def _status(self, text, color=TEXT):
        self.lbl.configure(text=text, fg=color)

    def _progress(self, frac, text=""):
        def upd():
            self.pb["value"] = max(0, min(100, frac * 100))
            if text:
                self.lbl.configure(text=text, fg=TEXT)
        self.win.ui(upd)

    def _ensure(self):
        """Scanner verbinden (läuft im Hintergrund-Thread)."""
        be = self.win.app.backend
        want_debug = self.o_debug.get()
        if self.sc is None or self.sc.client is None or self.sc.client.sock is None:
            self.sc = SC.Scanner(be.host, be.port, be.pid, log=lambda m: self.win.ui(lambda: self.log(m)),
                                 debug=want_debug)
            self.sc.connect()
            self.win.ui(lambda: self.lbl_mode.configure(
                text=f"Modus: {self.sc.mode}" + ("  (Turbo)" if self.sc.mode == "turbo" else "  (Fallback)")))
        self.sc.debug = want_debug
        self.sc.io.debug = want_debug
        return self.sc

    def _run(self, job, done):
        if self.running:
            return self.log("Es läuft schon ein Scan", "warn")
        self.running = True
        self.pb["value"] = 0
        self._status("läuft ...", WARN)

        def ok(r):
            self.running = False
            self.pb["value"] = 100
            done(r)

        def err(e):
            self.running = False
            self.pb["value"] = 0
            self._status(f"Fehler: {e}", ERROR)
            self.log(f"{type(e).__name__}: {e}", "err")
        self.win.bg(job, ok, err, lock=False)

    # ------------------------------------------------------------------
    # Scans
    # ------------------------------------------------------------------
    def scan_first(self):
        vname, ctype = self.vt.get(), self.ct.get()
        t1, t2 = self.v1.get(), self.v2.get()
        scope = SCOPES[self.scope.get()]
        min_mbps = SLOW_CHOICES[self.slow_sel.get()]
        opts = self._opts()
        pick = self.panel.make_pick(scope)       # Bereichsfilter: nur angehakte, nicht ausgeblendete Regionen
        try:        # früh validieren (Meldung im UI-Thread)
            if ctype not in SC.FIRST_ONLY:
                if SC.CTYPES[ctype][1] >= 1:
                    SC.encode_value(vname, t1)
                if SC.CTYPES[ctype][1] >= 2:
                    SC.encode_value(vname, t2)
        except Exception as e:
            return messagebox.showerror("Wert", str(e))

        def job():
            sc = self._ensure()
            sc.reset()
            regs = sc.regions(scope, min_mbps=min_mbps, report=True, pick=pick)
            total = sum(e - s for s, e in regs)
            self.win.ui(lambda: self.log(f"Scanne {len(regs)} Region(en), {total / 1048576:.0f} MB", "info"))
            return sc.first_scan(vname, ctype, t1, t2, regs, opts, self._progress)

        def done(n):
            self._ct_values(first=False)
            self._ct_changed()
            self._status(f"{n} Treffer", ACCENT if n else WARN)
            self._show_results(0)
            self.panel.update_summary()
        self._run(job, done)

    def scan_next(self):
        if not self.sc or not self.sc.first_scan_done:
            return self.log("Erst ERSTER SCAN", "warn")
        ctype, t1, t2 = self.ct.get(), self.v1.get(), self.v2.get()
        opts = self._opts()
        try:
            if SC.CTYPES[ctype][1] >= 1:
                SC.encode_value(self.sc.vname, t1)
            if SC.CTYPES[ctype][1] >= 2:
                SC.encode_value(self.sc.vname, t2)
        except Exception as e:
            return messagebox.showerror("Wert", str(e))

        def job():
            return self._ensure().next_scan(ctype, t1, t2, opts, self._progress)

        def done(n):
            self._status(f"{n} Treffer", ACCENT if n else WARN)
            self._show_results(0)
        self._run(job, done)

    def new_scan(self):
        if self.running:
            return self.log("Erst abbrechen", "warn")
        sc = self.sc

        def job():
            if sc:
                sc.reset()
            return True

        def done(_r):
            self.rt.delete(*self.rt.get_children())
            self.lbl_res.configure(text="GEFUNDEN: 0")
            self._ct_values(first=True)
            self._ct_changed()
            self._status("bereit")
        self._run(job, done)

    def cancel(self):
        if self.sc and self.running:
            self._status("breche ab ...", WARN)
            import threading
            threading.Thread(target=self.sc.cancel, daemon=True).start()

    # ------------------------------------------------------------------
    # Ergebnisse
    # ------------------------------------------------------------------
    def _page(self, d):
        if not self.sc or self.running:
            return
        last = max(0, (self.sc.count - 1) // PAGE)
        self._show_results(max(0, min(last, self.page + d)))

    def _show_results(self, page):
        self.page = page
        sc = self.sc
        if sc is None:
            return
        start = page * PAGE
        vname = sc.vname

        def job():
            return sc.results(start, PAGE)

        def done(rows):
            self.rt.delete(*self.rt.get_children())
            for r in rows:
                self.rt.insert("", "end", iid=str(r["addr"]), values=(
                    fmt_addr(r['addr']), SC.fmt_value(vname, r["cur"]), SC.fmt_value(vname, r["prev"]),
                    SC.fmt_value(vname, r["first"]) if r["first"] else ""))
            last = max(0, (sc.count - 1) // PAGE) + 1
            self.lbl_res.configure(text=f"GEFUNDEN: {sc.count}  (Seite {page + 1}/{last})")
        self._run_light(job, done)

    def _run_light(self, job, done):
        """Kurze Abfragen (Ergebnisseite) ohne den 'running'-Zustand zu blockieren."""
        self.win.bg(job, done, lambda e: self.log(f"{type(e).__name__}: {e}", "err"), lock=False)

    # ------------------------------------------------------------------
    # Cheat-Liste
    # ------------------------------------------------------------------
    def add_selected(self):
        if not self.sc:
            return
        vname = self.sc.vname
        for iid in self.rt.selection():
            a = int(iid)
            if any(e["addr"] == a for e in self.entries):
                continue
            vals = self.rt.item(iid, "values")
            self.entries.append({"addr": a, "vname": vname, "desc": "", "frozen": False,
                                 "freeze": None, "cur": vals[1]})
        self._refresh_list()

    def add_all(self):
        """Alle Treffer der aktuell angezeigten Seite in die Adressliste."""
        self.rt.selection_set(self.rt.get_children())
        self.add_selected()

    def add_pointer(self, root_off, offsets, vname):
        """Pointer-Pfad als Eintrag; die Adresse wird bei jedem Tick neu aufgelöst."""
        key = (root_off, tuple(offsets))
        if any(e.get("ptr") == key for e in self.entries):
            return
        self.entries.append({"addr": 0, "vname": vname, "desc": "ptr", "frozen": False,
                             "freeze": None, "cur": "?", "ptr": key})
        self._refresh_list()

    def _addr_of(self, e, client):
        """Aktuelle Adresse eines Eintrags (Pointer-Pfade werden frisch aufgelöst)."""
        if e.get("ptr"):
            a = PS.resolve(client, self.base + e["ptr"][0], e["ptr"][1])
            e["addr"] = a or 0
        return e["addr"]

    def to_pointer(self):
        sel = self._sel_entries()
        if sel and sel[0]["addr"]:
            self.win.to_pointer(sel[0]["addr"], sel[0]["vname"])

    def _sel_entries(self):
        idx = [int(i) for i in self.lt.selection()]
        return [self.entries[i] for i in idx if i < len(self.entries)]

    def _refresh_list(self):
        sel = self.lt.selection()
        self.lt.delete(*self.lt.get_children())
        for i, e in enumerate(self.entries):
            self.lt.insert("", "end", iid=str(i), values=(
                "❄" if e["frozen"] else "", e["desc"], fmt_addr(e["addr"]) if e["addr"] else "?",
                e["vname"], e["cur"]))
        for s in sel:
            if self.lt.exists(s):
                self.lt.selection_add(s)

    def set_value(self):
        sel = self._sel_entries()
        if not sel:
            return
        e = sel[0]
        txt = simpledialog.askstring("Wert setzen", f"Neuer Wert ({e['vname']}) für {e['addr']:#x}:",
                                     initialvalue=str(e["cur"]), parent=self)
        if txt is None:
            return
        try:
            data = SC.encode_value(e["vname"], txt)
        except Exception as ex:
            return messagebox.showerror("Wert", str(ex))
        targets = sel

        def job():
            for t in targets:
                a = self._addr_of(t, self.win.client)
                if not a:
                    continue
                self.win.client.write_memory(a, data)
                if t["frozen"]:
                    t["freeze"] = data
            return True
        self.win.bg(job, lambda _r: self.log(f"{len(targets)} Wert(e) geschrieben", "ok"))

    def toggle_freeze(self):
        sel = self._sel_entries()
        if not sel:
            return

        def job():
            for e in sel:
                if e["frozen"]:
                    e["frozen"] = False
                else:
                    a = self._addr_of(e, self.win.client)
                    if not a:
                        continue
                    e["freeze"] = self.win.client.read_memory(a, SC.VTYPES[e["vname"]][1])
                    e["frozen"] = True
            return True
        self.win.bg(job, lambda _r: self._refresh_list())

    def rename(self):
        sel = self._sel_entries()
        if not sel:
            return
        t = simpledialog.askstring("Beschreibung", "Beschreibung:", initialvalue=sel[0]["desc"], parent=self)
        if t is not None:
            sel[0]["desc"] = t
            self._refresh_list()

    def remove(self):
        for e in self._sel_entries():
            self.entries.remove(e)
        self._refresh_list()

    def _res_to_hex(self):
        sel = self.rt.selection()
        if sel:
            self.win.goto_memory(int(sel[0]))

    def _res_copy(self):
        sel = self.rt.selection()
        if sel:
            self._clip(" ".join(fmt_addr(int(i)) for i in sel))

    def _list_copy(self):
        sel = [e for e in self._sel_entries() if e["addr"]]
        if sel:
            self._clip(" ".join(fmt_addr(e["addr"]) for e in sel))

    def _clip(self, text):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    def who_writes(self):
        sel = self._sel_entries()
        if sel and sel[0]["addr"]:
            self.win.to_debug_watch(sel[0]["addr"], SC.VTYPES[sel[0]["vname"]][1])

    def to_hex(self):
        sel = self._sel_entries()
        if sel and sel[0]["addr"]:
            self.win.goto_memory(sel[0]["addr"])

    # ------------------------------------------------------------------
    # Live-Werte + Freeze
    # ------------------------------------------------------------------
    def _tick(self):
        if not self.winfo_exists():
            return
        self.after(150, self._tick)
        if not self.entries or self._busy_tick or self.win.client is None:
            return
        self._tick_n += 1
        frozen = [e for e in self.entries if e["frozen"] and e["freeze"] is not None]
        refresh = self.v_live.get() and self._tick_n % 4 == 0
        if not frozen and not refresh:
            return
        self._busy_tick = True
        entries = list(self.entries)

        def job():
            c = self.win.client
            writes = []
            for e in frozen:
                a = self._addr_of(e, c)
                if a:
                    writes.append((a, e["freeze"]))
            if writes:
                # ein Austausch fuer alle eingefrorenen Werte (und nicht im Journal); aeltere
                # Payloads ohne write_multi -> Einzelschreiben
                if not getattr(self, "_no_multi", False):
                    try:
                        import ps5_more
                        ps5_more.write_multi(c, writes)
                    except Exception:
                        self._no_multi = True
                        for a, d in writes:
                            c.write_memory(a, d)
                else:
                    for a, d in writes:
                        c.write_memory(a, d)
            out = []
            if refresh:
                for e in entries:
                    try:
                        a = self._addr_of(e, c)
                        out.append(SC.fmt_value(e["vname"], c.read_memory(a, SC.VTYPES[e["vname"]][1]))
                                   if a else "?")
                    except Exception:
                        out.append("?")
            return out

        def done(vals):
            self._busy_tick = False
            for e, v in zip(entries, vals):
                e["cur"] = v
            if vals:
                self._refresh_list()

        def err(ex):
            self._busy_tick = False
            self.log(f"Live/Freeze: {ex}", "err")
        self.win.bg(job, done, err)

    # ------------------------------------------------------------------
    # Selbsttest
    # ------------------------------------------------------------------
    def region_report(self):
        """Alle Speicherregionen des Spiels (Name, Groesse, Rechte) in die Datei regionen_<PID>.txt schreiben."""
        def job():
            import os
            import paths
            import ps5_ext
            import regionreport
            cl = self.win.app.backend.client
            if cl is None or cl.pid is None:
                raise RuntimeError("nicht verbunden - im Hauptfenster VERBINDEN")
            text = regionreport.report(ps5_ext.maps_named(cl))
            path = os.path.join(paths.data_dir(), f"regionen_{cl.pid}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return path, text

        def ok(res):
            path, text = res
            for line in text.splitlines()[:12]:
                self.log(line)
            self.log(f"Regionen-Bericht gespeichert: {path}", "ok")

        self.win.bg(job, ok, lambda e: self.log(f"Regionen-Bericht: {e}", "err"))

    def selftest(self):
        """Kleiner Scan über 1 MB: prüft Verbindung, Auth, Turbo, Ergebnis-Abruf."""
        if self.running:
            return

        def job():
            self.win.ui(lambda: self.log("--- Selbsttest ---", "info"))
            be = self.win.app.backend
            sc = SC.Scanner(be.host, be.port, be.pid, debug=True,
                            log=lambda m: self.win.ui(lambda: self.log(m)))
            try:
                sc.connect()
                regs = [(s, e) for s, e in sc.regions("data") if e - s >= 0x10000][:1]
                if not regs:
                    raise SC.ScanError("Keine geeignete Region gefunden")
                s, e = regs[0]
                end = min(e, s + 0x100000)
                data = sc.client.read_memory(s, 8)
                val = str(struct.unpack("<I", data[:4])[0])
                self.win.ui(lambda: self.log(f"Region {s:#x}-{end:#x}, suche UInt32 {val}", "info"))
                n = sc.first_scan("UInt32", "Genau", val, None, [(s, end)], {})
                res = sc.results(0, 50)
                hit = any(r["addr"] == s for r in res)
                n2 = sc.next_scan("Unverändert", "", None, {})
                return (sc.mode, n, hit, n2)
            finally:
                sc.close()

        def done(r):
            mode, n, hit, n2 = r
            ok = hit and n2 >= 1
            self.log(f"Selbsttest {'OK' if ok else 'AUFFÄLLIG'}: Modus={mode}, Treffer={n}, "
                     f"Startadresse gefunden={hit}, 'Unverändert' behält {n2}", "ok" if ok else "warn")
            self._status("Selbsttest fertig", ACCENT if ok else WARN)
        self._run(job, done)

    def shutdown(self):
        try:
            if self.sc:
                self.sc.close()
        except Exception:
            pass
