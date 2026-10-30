"""tools_pointer_gui.py – Pointer-Scanner-Tab."""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import pointerscan as PS
import scanner as SC
import ps5_ext as X
from tools_common import (BG, ACCENT, TEXT, WARN, ERROR, BaseTab, button, label, entry, tree, with_scroll, hexs)


class PointerTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.pm = None               # PointerMap
        self.static = []             # statische Bereiche
        self.paths = []              # [(root_off, offsets)]
        self.running = False
        self.cancel_flag = False
        self.sc = None

        r1 = tk.Frame(self, bg=BG); r1.pack(fill="x", padx=8, pady=(8, 2))
        label(r1, "ZIELADRESSE").pack(side="left")
        self.v_target = tk.StringVar()
        entry(r1, self.v_target, 20).pack(side="left", padx=(6, 12))
        label(r1, "TIEFE").pack(side="left")
        self.v_depth = tk.StringVar(value="4")
        ttk.Combobox(r1, textvariable=self.v_depth, values=["1", "2", "3", "4", "5", "6"],
                     width=3, state="readonly").pack(side="left", padx=(6, 12))
        label(r1, "MAX. OFFSET").pack(side="left")
        self.v_off = tk.StringVar(value="0x400")
        entry(r1, self.v_off, 8).pack(side="left", padx=(6, 12))
        label(r1, "STATISCH (Name)").pack(side="left")
        self.v_static = tk.StringVar(value="eboot")
        entry(r1, self.v_static, 12).pack(side="left", padx=(6, 12))
        label(r1, "TYP").pack(side="left")
        self.v_type = tk.StringVar(value="Int32")
        ttk.Combobox(r1, textvariable=self.v_type, values=list(SC.VTYPES), width=8,
                     state="readonly").pack(side="left", padx=6)

        r2 = tk.Frame(self, bg=BG); r2.pack(fill="x", padx=8, pady=2)
        button(r2, "1) KARTE ERSTELLEN", self.build, accent=True).pack(side="left", padx=2)
        button(r2, "2) PFADE SUCHEN", self.search, accent=True).pack(side="left", padx=2)
        button(r2, "3) PRÜFEN (neues Ziel)", self.verify).pack(side="left", padx=2)
        button(r2, "⚡ SCHNELL-SCAN (Konsole)", self.fast_search, accent=True).pack(side="left", padx=(12, 2))
        button(r2, "ABBRECHEN", self.cancel).pack(side="left", padx=(12, 2))
        button(r2, "SPEICHERN…", self.save).pack(side="right", padx=2)
        button(r2, "LADEN…", self.load).pack(side="right", padx=2)

        r3 = tk.Frame(self, bg=BG); r3.pack(fill="x", padx=8, pady=2)
        self.pb = ttk.Progressbar(r3, orient="horizontal", mode="determinate", length=260, maximum=100)
        self.pb.pack(side="left")
        self.lbl = label(r3, "Ablauf: 1) Karte (einmal pro Spielzustand)  2) Pfade suchen  "
                             "3) Spiel neu starten, neue Adresse suchen, hier eintragen, PRÜFEN",
                         dim=True)
        self.lbl.pack(side="left", padx=10)

        fr = tk.Frame(self, bg=BG); fr.pack(fill="both", expand=True, padx=8, pady=4)
        self.tv = tree(fr, [("p", "PFAD  (Basis+Root → Offsets)"), ("d", "TIEFE"), ("l", "LIVE-ZIEL")],
                       [560, 60, 160], height=18)
        with_scroll(fr, self.tv)

        r4 = tk.Frame(self, bg=BG); r4.pack(fill="x", padx=8, pady=6)
        button(r4, "→ CHEAT-LISTE", self.to_list, accent=True).pack(side="left", padx=2)
        button(r4, "TOP 10 → CHEAT-LISTE", lambda: self.to_list(top=10)).pack(side="left", padx=2)
        button(r4, "LIVE AUFLÖSEN", self.live).pack(side="left", padx=(12, 2))
        self.lbl_info = label(r4, ""); self.lbl_info.pack(side="right")

    # ------------------------------------------------------------------
    def set_target(self, address, vname="Int32"):
        self.v_target.set(hexs(address))
        self.v_type.set(vname)

    def _set(self, text, color=TEXT):
        self.lbl.configure(text=text, fg=color)

    def _progress(self, frac, text=""):
        def upd():
            self.pb["value"] = max(0, min(100, frac * 100))
            if text:
                self.lbl.configure(text=text, fg=TEXT)
        self.win.ui(upd)

    def _run(self, job, done, lock=False):
        if self.running:
            return self.log("Es läuft schon etwas", "warn")
        self.running = True
        self.cancel_flag = False
        self.pb["value"] = 0
        self._set("läuft ...", WARN)

        def ok(r):
            self.running = False
            self.pb["value"] = 100
            done(r)

        def err(e):
            self.running = False
            self._set(f"Fehler: {e}", ERROR)
            self.log(f"{type(e).__name__}: {e}", "err")
        self.win.bg(job, ok, err, lock=lock)

    def cancel(self):
        self.cancel_flag = True
        if self.sc:
            threading.Thread(target=self.sc.cancel, daemon=True).start()
        self._set("breche ab ...", WARN)

    # ------------------------------------------------------------------
    # 1) Karte
    # ------------------------------------------------------------------
    def build(self):
        be = self.win.app.backend
        flt = self.v_static.get()
        base = self.base

        def job():
            sc = SC.Scanner(be.host, be.port, be.pid,
                            log=lambda m: self.win.ui(lambda: self.log(m)))
            self.sc = sc
            try:
                sc.connect()
                if sc.mode != "turbo":
                    self.win.ui(lambda: self.log("Kein Turbo-Scan: Karte wird langsam (Fallback)", "warn"))
                maps = sc.client.get_maps()
                rd = [(s, e) for s, e, p in maps if p & 1]
                regs = sc.regions("data", min_mbps=100)
                pm = PS.build_map(sc, regs, (min(s for s, _ in rd), max(e for _, e in rd)), self._progress)
                named = X.maps_named(sc.client)
                return pm, PS.static_ranges(named, flt, base)
            finally:
                sc.close()
                self.sc = None

        def done(r):
            self.pm, self.static = r
            tot = sum(e - s for s, e in self.static)
            self._set(f"Karte fertig: {self.pm.count} Zeiger, statisch: {len(self.static)} Region(en) "
                      f"({tot / 1048576:.1f} MB)", ACCENT)
            if not self.static:
                self.log("Keine statische Region gefunden - Namensfilter anpassen", "warn")
        self._run(job, done)

    # ------------------------------------------------------------------
    # 2) Suchen
    # ------------------------------------------------------------------
    def search(self):
        if not self.pm:
            return self.log("Erst KARTE ERSTELLEN", "warn")
        try:
            target = self.addr(self.v_target.get())
            depth = int(self.v_depth.get())
            max_off = int(self.v_off.get(), 0)
        except Exception as e:
            return self.log(str(e), "err")
        pm, static, base = self.pm, self.static, self.base

        def job():
            def prog(d, i, n, found):
                self._progress(i / max(n, 1), f"Ebene {d}: {i}/{n} Knoten, {found} Pfade")
            return pm.find_paths(target, static, depth, max_off, progress=prog,
                                 cancelled=lambda: self.cancel_flag)

        def done(r):
            res, truncated = r
            self.paths = [(a - base, offs) for a, offs in res]
            self._fill()
            self._set(f"{len(self.paths)} Pfad(e)" + ("  (gekürzt)" if truncated else ""),
                      ACCENT if self.paths else WARN)
        self._run(job, done)

    def fast_search(self):
        """Pointer-Scan ohne Karte: die Konsole sucht Ebene fuer Ebene (ptrscan_server.py).
        Braucht die ps5debug-NG-Erweiterung 0xBDAACC30."""
        try:
            target = self.addr(self.v_target.get())
            depth = int(self.v_depth.get())
            max_off = int(self.v_off.get(), 0)
        except Exception as e:
            return self.log(str(e), "err")
        be, flt, base = self.win.app.backend, self.v_static.get(), self.base
        import ptrscan_server as PSV

        def job():
            sc = SC.Scanner(be.host, be.port, be.pid, log=lambda m: self.win.ui(lambda: self.log(m)))
            self.sc = sc
            try:
                sc.connect()
                maps = sc.client.get_maps()
                segs = [(s, e - s) for s, e, p in maps if (p & 3) == 3 and e - s >= 0x1000]
                static = PS.static_ranges(X.maps_named(sc.client), flt, base)
                if not static:
                    raise RuntimeError("keine statische Region gefunden - Namensfilter anpassen")
                lvl = {"n": 0}

                def prog(done, total):
                    self._progress(done / max(total, 1), f"Ebene {lvl['n'] + 1}: {done}/{total}")

                fn = PSV.server_level_fn(sc.client, segs, max_off, prog)
                chains, info = PSV.scan(
                    fn, target, segs, static, max_off, depth,
                    on_level=lambda d, n, r: (lvl.__setitem__("n", d), self.win.ui(
                        lambda: self._set(f"Ebene {d}: {n} Treffer, {r} statische Wurzeln", WARN))),
                    should_stop=lambda: self.cancel_flag)
                return chains, info
            finally:
                sc.close()
                self.sc = None

        def done(r):
            chains, info = r
            self.paths = [(c.static - base, tuple(c.offsets)) for c in chains]
            self._fill()
            self._set(f"{len(self.paths)} Pfad(e) (Schnell-Scan, {info['levels']} Ebenen)"
                      + ("  (gekürzt)" if info["capped"] else ""), ACCENT if self.paths else WARN)
        self._run(job, done)

    def _fill(self, live=None):
        self.tv.delete(*self.tv.get_children())
        for i, (r, o) in enumerate(self.paths):
            self.tv.insert("", "end", iid=str(i), values=(
                PS.fmt_path(r, o), len(o), "" if live is None else (hexs(live[i]) if live[i] else "—")))
        self.lbl_info.configure(text=f"{len(self.paths)} Pfade")

    # ------------------------------------------------------------------
    # 3) Prüfen / Live
    # ------------------------------------------------------------------
    def verify(self):
        if not self.paths:
            return self.log("Keine Pfade", "warn")
        try:
            expect = self.addr(self.v_target.get())
        except Exception as e:
            return self.log(str(e), "err")
        paths, base = list(self.paths), self.base

        def job():
            return PS.verify(self.win.client, paths, expect, base, self._progress)

        def done(keep):
            self.log(f"Prüfung: {len(keep)}/{len(paths)} Pfade lösen auf {expect:#x} auf", "ok" if keep else "warn")
            self.paths = keep
            self._fill()
            self._set(f"{len(keep)} Pfad(e) bestätigt", ACCENT if keep else WARN)
        self._run(job, done, lock=True)

    def live(self):
        if not self.paths:
            return
        paths, base = list(self.paths), self.base

        def job():
            return [PS.resolve(self.win.client, base + r, o) for r, o in paths[:500]]
        self.win.bg(job, lambda res: self._fill(res + [None] * (len(paths) - len(res))))

    # ------------------------------------------------------------------
    # Liste / Dateien
    # ------------------------------------------------------------------
    def to_list(self, top=None):
        if not self.win.scan_tab:
            return self.log("Searcher-Tab fehlt", "err")
        if top:
            items = self.paths[:top]
        else:
            items = [self.paths[int(i)] for i in self.tv.selection()]
        if not items:
            return self.log("Nichts ausgewählt", "warn")
        for r, o in items:
            self.win.scan_tab.add_pointer(r, o, self.v_type.get())
        self.log(f"{len(items)} Pfad(e) in die Cheat-Liste übernommen", "ok")

    def save(self):
        if not self.paths:
            return
        fn = filedialog.asksaveasfilename(parent=self, defaultextension=".json",
                                          filetypes=[("Pfade", "*.json")], initialfile="pointer_paths.json")
        if fn:
            PS.save_paths(fn, self.paths, {"type": self.v_type.get()})
            self.log(f"Gespeichert: {fn}", "ok")

    def load(self):
        fn = filedialog.askopenfilename(parent=self, filetypes=[("Pfade", "*.json")])
        if not fn:
            return
        try:
            self.paths, info = PS.load_paths(fn)
            if info.get("type") in SC.VTYPES:
                self.v_type.set(info["type"])
            self._fill()
            self.log(f"{len(self.paths)} Pfade geladen", "ok")
        except Exception as e:
            messagebox.showerror("Laden", str(e))

    def shutdown(self):
        self.cancel_flag = True
