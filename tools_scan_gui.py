"""tools_scan_gui.py – Cheat-Searcher-Tab (schnelle Memory-Scans + Cheat-Liste)."""
import struct
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import scanner as SC
import pointerscan as PS
from tools_common import (BG, BG_CARD, ACCENT, TEXT, TEXT_DIM, WARN, ERROR, FONT_LABEL,
                          BaseTab, button, label, entry, tree, with_scroll, hexs)

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


class ScanTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.sc = None
        self.running = False
        self.page = 0
        self.entries = []            # Cheat-Liste
        self._tick_n = 0
        self._busy_tick = False

        # Layout wie im PS5 Debug Toolkit: oben Treffer (links) + Scan-Steuerung (rechts), unten die Adressliste.
        pw = tk.PanedWindow(self, orient="vertical", bg=BG, sashwidth=5, sashrelief="flat", bd=0)
        pw.pack(fill="both", expand=True, padx=8, pady=8)
        top = tk.Frame(pw, bg=BG)
        bottom = tk.Frame(pw, bg=BG)
        pw.add(top, minsize=220, stretch="always")
        pw.add(bottom, minsize=170, stretch="always")
        left = tk.Frame(top, bg=BG); left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(top, bg=BG); right.pack(side="left", fill="y", padx=(10, 0))

        # --- links: Treffer ---
        hd = tk.Frame(left, bg=BG); hd.pack(fill="x")
        self.lbl_res = label(hd, "GEFUNDEN: 0"); self.lbl_res.pack(side="left")
        button(hd, "▶", lambda: self._page(1)).pack(side="right", padx=2)
        button(hd, "◀", lambda: self._page(-1)).pack(side="right", padx=2)
        fr = tk.Frame(left, bg=BG); fr.pack(fill="both", expand=True, pady=(2, 0))
        self.rt = tree(fr, [("a", "ADRESSE"), ("c", "AKTUELL"), ("p", "VORHER"), ("f", "ERSTER")],
                       [150, 100, 100, 100], height=12, anchors={})
        with_scroll(fr, self.rt)
        self.rt.bind("<Double-1>", lambda _e: self.add_selected())
        lb = tk.Frame(left, bg=BG); lb.pack(fill="x", pady=4)
        button(lb, "→ AUSGEWÄHLTE HINZUFÜGEN", self.add_selected, accent=True).pack(side="left", padx=2)
        button(lb, "→ ALLE (SEITE)", self.add_all).pack(side="left", padx=2)

        # --- rechts: Scan-Steuerung ---
        r1 = tk.Frame(right, bg=BG); r1.pack(fill="x")
        self.b_first = button(r1, "ERSTER SCAN", self.scan_first, accent=True)
        self.b_first.pack(side="left", padx=2)
        self.b_next = button(r1, "NÄCHSTER SCAN", self.scan_next, accent=True)
        self.b_next.pack(side="left", padx=2)
        r1b = tk.Frame(right, bg=BG); r1b.pack(fill="x", pady=(4, 0))
        button(r1b, "ABBRECHEN", self.cancel).pack(side="left", padx=2)
        button(r1b, "NEUER SCAN", self.new_scan).pack(side="left", padx=2)
        button(r1b, "SELBSTTEST", self.selftest).pack(side="left", padx=2)
        button(r1b, "REGIONEN-BERICHT", self.region_report).pack(side="left", padx=2)

        r3 = tk.Frame(right, bg=BG); r3.pack(fill="x", pady=(8, 0))
        self.pb = ttk.Progressbar(r3, orient="horizontal", mode="determinate", length=300, maximum=100)
        self.pb.pack(fill="x")
        self.lbl = label(right, "bereit", dim=False); self.lbl.pack(anchor="w", pady=(2, 0))
        self.lbl_mode = label(right, ""); self.lbl_mode.pack(anchor="w")

        rv = tk.Frame(right, bg=BG); rv.pack(fill="x", pady=(8, 2))
        label(rv, "WERT").pack(side="left")
        self.v1 = tk.StringVar()
        self.e1 = entry(rv, self.v1, 14); self.e1.pack(side="left", padx=(6, 8))
        self.e1.bind("<Return>", lambda _e: self.scan_first() if not self.sc or not self.sc.first_scan_done
                     else self.scan_next())
        label(rv, "BIS").pack(side="left")
        self.v2 = tk.StringVar()
        self.e2 = entry(rv, self.v2, 10); self.e2.pack(side="left", padx=(6, 0))

        rt_ = tk.Frame(right, bg=BG); rt_.pack(fill="x", pady=2)
        label(rt_, "VERGLEICH").pack(side="left")
        self.ct = tk.StringVar(value="Genau")
        self.cb_ct = ttk.Combobox(rt_, textvariable=self.ct, width=24, state="readonly")
        self.cb_ct.pack(side="left", padx=6)
        self.cb_ct.bind("<<ComboboxSelected>>", lambda _e: self._ct_changed())
        rv2 = tk.Frame(right, bg=BG); rv2.pack(fill="x", pady=2)
        label(rv2, "WERTTYP").pack(side="left")
        self.vt = tk.StringVar(value="Int32")
        ttk.Combobox(rv2, textvariable=self.vt, values=list(SC.VTYPES), width=10,
                     state="readonly").pack(side="left", padx=(14, 6))
        rs = tk.Frame(right, bg=BG); rs.pack(fill="x", pady=2)
        label(rs, "BEREICH").pack(side="left")
        self.scope = tk.StringVar(value="Daten (rw, ohne Code)")
        ttk.Combobox(rs, textvariable=self.scope, values=list(SCOPES), width=24,
                     state="readonly").pack(side="left", padx=(14, 6))

        # --- Optionen (Rahmen wie "Memory scan options" im Toolkit) ---
        opt = tk.LabelFrame(right, text=" SCAN-OPTIONEN ", bg=BG, fg=TEXT_DIM, font=FONT_LABEL,
                            bd=1, relief="groove", labelanchor="nw")
        opt.pack(fill="x", pady=(8, 0))
        o1 = tk.Frame(opt, bg=BG); o1.pack(fill="x", padx=4, pady=2)
        self.slow_sel = tk.StringVar(value=list(SLOW_CHOICES)[1])
        ttk.Combobox(o1, textvariable=self.slow_sel, values=list(SLOW_CHOICES), width=24,
                     state="readonly").pack(side="left", padx=2)
        o2 = tk.Frame(opt, bg=BG); o2.pack(fill="x", padx=4)
        self.o_float = self._chk(o2, "Float vereinfachen", True)
        self.o_par = self._chk(o2, "Parallel (schneller)", True)
        o3 = tk.Frame(opt, bg=BG); o3.pack(fill="x", padx=4)
        self.o_alias = self._chk(o3, "Aliasing (experimentell)", False)
        self.o_debug = self._chk(o3, "Debug-Log", False)
        o4 = tk.Frame(opt, bg=BG); o4.pack(fill="x", padx=4)
        self.o_small = self._chk(o4, "kleine Segmente (<256 KB) auslassen", False)
        o5 = tk.Frame(opt, bg=BG); o5.pack(fill="x", padx=4, pady=(4, 0))
        label(o5, "SNAPSHOT-RAM").pack(side="left")
        self.ram_sel = tk.StringVar(value=list(RAM_CHOICES)[2])
        ttk.Combobox(o5, textvariable=self.ram_sel, values=list(RAM_CHOICES), width=26,
                     state="readonly").pack(side="left", padx=4)
        o6 = tk.Frame(opt, bg=BG); o6.pack(fill="x", padx=4, pady=(2, 0))
        label(o6, "AUSLAGERN NACH").pack(side="left")
        self.spill_sel = tk.StringVar(value=list(SPILL_CHOICES)[0])
        ttk.Combobox(o6, textvariable=self.spill_sel, values=list(SPILL_CHOICES), width=26,
                     state="readonly").pack(side="left", padx=4)
        label(opt, "(nur 'Unbekannter Startwert': mehr RAM = viel schneller, belegt aber PS5-Speicher)",
              dim=True).pack(anchor="w", padx=4, pady=(2, 4))

        # --- unten: Adressliste (Cheat-Liste) ---
        hd = tk.Frame(bottom, bg=BG); hd.pack(fill="x")
        label(hd, "ADRESSLISTE").pack(side="left")
        self.v_live = tk.BooleanVar(value=True)
        tk.Checkbutton(hd, text="live", variable=self.v_live, bg=BG, fg=TEXT_DIM, selectcolor=BG_CARD,
                       activebackground=BG, activeforeground=ACCENT, font=FONT_LABEL).pack(side="right")
        fr2 = tk.Frame(bottom, bg=BG); fr2.pack(fill="both", expand=True, pady=(2, 0))
        self.lt = tree(fr2, [("z", "❄"), ("d", "BESCHREIBUNG"), ("a", "ADRESSE"), ("t", "TYP"), ("v", "WERT")],
                       [30, 220, 160, 80, 140], height=7, anchors={"z": "center"})
        with_scroll(fr2, self.lt)
        self.lt.bind("<Double-1>", lambda _e: self.set_value())
        ac = tk.Frame(bottom, bg=BG); ac.pack(fill="x", pady=(4, 0))
        button(ac, "WERT SETZEN", self.set_value, accent=True).pack(side="left", padx=2)
        button(ac, "FREEZE", self.toggle_freeze).pack(side="left", padx=2)
        button(ac, "BESCHREIBUNG", self.rename).pack(side="left", padx=2)
        button(ac, "ENTFERNEN", self.remove).pack(side="left", padx=2)
        button(ac, "WER SCHREIBT?", self.who_writes).pack(side="left", padx=(14, 2))
        button(ac, "→ HEX", self.to_hex).pack(side="left", padx=2)
        button(ac, "→ POINTER-SCAN", self.to_pointer).pack(side="left", padx=2)

        self._ct_values(first=True)
        self._ct_changed()
        self.after(150, self._tick)

    def _chk(self, parent, text, default):
        v = tk.BooleanVar(value=default)
        tk.Checkbutton(parent, text=text, variable=v, bg=BG, fg=TEXT_DIM, selectcolor=BG_CARD,
                       activebackground=BG, activeforeground=ACCENT, font=FONT_LABEL).pack(side="left", padx=4)
        return v

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
            regs = sc.regions(scope, min_mbps=min_mbps, report=True)
            total = sum(e - s for s, e in regs)
            self.win.ui(lambda: self.log(f"Scanne {len(regs)} Region(en), {total / 1048576:.0f} MB", "info"))
            return sc.first_scan(vname, ctype, t1, t2, regs, opts, self._progress)

        def done(n):
            self._ct_values(first=False)
            self._ct_changed()
            self._status(f"{n} Treffer", ACCENT if n else WARN)
            self._show_results(0)
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
