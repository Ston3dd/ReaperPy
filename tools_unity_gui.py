"""tools_unity_gui.py - Tab "UNITY": das Gegenstueck zu UE-LIVE fuer Unity-(IL2CPP)-Spiele.

  1) SPIEL-ORDNER waehlen: der Ordner mit der Ausgabe von Il2CppDumper (dump.cs, script.json, DummyDll ...).
     Verschachtelte Ordner (entpackte ZIPs) sind egal - die Dateien werden gesucht.
  2) Spiel auf der Konsole starten, bis ein Spielstand geladen ist, dann MODUL ERKENNEN.
  3) WERTE:    Feld anklicken (z. B. Gold, Health) -> Live-Instanzen -> aendern / einfrieren
     METHODEN: Methode suchen (z. B. AddMoney, IsDead) -> Rueckgabewert festlegen / Methode leer machen -> AN/AUS
     NAMEN:    Enum-Tabellen (Item-IDs, Rezepte, ...) nach Namen durchsuchen - nie wieder Zahlen raten

Logik in il2cpp_dump.py (testbar ohne Konsole); Schreib-/Einfrier-Logik teilt sich der Tab mit UE-LIVE (ue_quick.py).
"""

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import il2cpp_dump as D
import ue_quick as Q
from tools_common import ACCENT, BG, FONT_LABEL, TEXT_DIM, WARN, BaseTab, button, entry, label, tree, with_scroll

CFG = os.path.join(os.path.expanduser("~"), ".reaperpy_unity.json")
TICK_MS = 400
MAX_ROWS = 4000
MAX_LIVE_ROWS = 120
SNOW = "❄"


def _load_cfg():
    try:
        with open(CFG, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def _save_cfg(d):
    try:
        with open(CFG, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
    except Exception:  # noqa: BLE001
        pass


def _hex_or_none(text):
    try:
        return int((text or "").strip(), 16)
    except ValueError:
        return None


class AppliedPatch:
    def __init__(self, method, mode, value, addr, original, new):
        self.method, self.mode, self.value = method, mode, value
        self.addr, self.original, self.new = addr, original, new
        self.on = True

    @property
    def title(self):
        what = {"true": "gibt immer TRUE", "false": "gibt immer FALSE", "noop": "macht nichts",
                "value": f"gibt immer {self.value}"}[self.mode]
        return f"{self.method.cls.name}.{self.method.name}: {what}"


class UnityTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.game = self.live = None
        self.mod_base = None        # IL2CPP-Modul-Basis (live) - eigener Name, BaseTab.base ist die eboot-Basis
        self.targets, self.shown, self.cur = [], [], None
        self.rows = []
        self.static_keys = set()
        self.counts = None          # Ergebnis des Spiel-Scans: {Klasse: Objekte inkl. Unterklassen}
        self.inited = set()         # Klassen, die im Spiel schon initialisiert sind
        self.freezer = Q.Freezer()
        self.applied = []
        self.mshown = []
        self._busy = False
        self._pending = None
        self._cfg = _load_cfg()

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=8, pady=(8, 2))
        button(top, "SPIEL-ORDNER…", self.pick_game, accent=True).pack(side="left", padx=2)
        self.v_game = tk.StringVar(value=self._cfg.get("game", ""))
        entry(top, self.v_game, 60).pack(side="left", padx=4, fill="x", expand=True)
        button(top, "↻ LADEN", self.load).pack(side="left", padx=2)
        mod = tk.Frame(self, bg=BG)
        mod.pack(fill="x", padx=8, pady=2)
        button(mod, "② MODUL ERKENNEN", self.detect_base, accent=True).pack(side="left", padx=2)
        label(mod, "MODUL-BASIS").pack(side="left", padx=(8, 2))
        self.v_base = tk.StringVar()
        entry(mod, self.v_base, 16).pack(side="left", padx=2)
        label(mod, "STATIC-OFFSET").pack(side="left", padx=(8, 2))
        self.v_static = tk.StringVar(value=hex(D.K_STATIC_FIELDS))
        entry(mod, self.v_static, 6).pack(side="left", padx=2)
        self.lbl = label(
            self,
            "① Spiel-Ordner wählen (dump.cs + script.json von Il2CppDumper)   ② Spiel starten, Spielstand laden, "
            "MODUL ERKENNEN   ③ unten WERTE / METHODEN / NAMEN benutzen",
        )
        self.lbl.pack(anchor="w", padx=10, pady=2)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)
        self._build_values(tk.Frame(self.nb, bg=BG))
        self._build_methods(tk.Frame(self.nb, bg=BG))
        self._build_names(tk.Frame(self.nb, bg=BG))
        self.after(300, self._autoload)
        self.after(TICK_MS, self._tick)

    # ------------------------------------------------------------------ Seiten
    def _build_values(self, page):
        self.nb.add(page, text="WERTE")
        pan = ttk.PanedWindow(page, orient="horizontal")
        pan.pack(fill="both", expand=True)
        left = tk.Frame(pan, bg=BG)
        pan.add(left, weight=2)
        fr = tk.Frame(left, bg=BG)
        fr.pack(fill="x")
        label(fr, "NAME SUCHEN").pack(side="left")
        self.v_q = tk.StringVar()
        e = entry(fr, self.v_q, 24)
        e.pack(side="left", padx=4)
        e.bind("<KeyRelease>", lambda _e: self._fill_targets())
        self.v_only = tk.BooleanVar(value=True)
        tk.Checkbutton(fr, text="nur Spiel-Code", variable=self.v_only, command=self._rebuild_targets, bg=BG,
                       fg=TEXT_DIM, selectcolor=BG, activebackground=BG, font=FONT_LABEL).pack(side="left", padx=6)
        fr2 = tk.Frame(left, bg=BG)
        fr2.pack(fill="x", pady=2)
        self.v_gen = tk.BooleanVar(value=True)
        tk.Checkbutton(fr2, text="Compiler-Kram ausblenden", variable=self.v_gen, command=self._rebuild_targets, bg=BG,
                       fg=TEXT_DIM, selectcolor=BG, activebackground=BG, font=FONT_LABEL).pack(side="left", padx=4)
        self.v_live_only = tk.BooleanVar(value=True)
        tk.Checkbutton(fr2, text="nur Klassen mit Objekten im Speicher", variable=self.v_live_only,
                       command=self._fill_targets, bg=BG, fg=TEXT_DIM, selectcolor=BG, activebackground=BG,
                       font=FONT_LABEL).pack(side="left", padx=4)
        button(fr2, "② b. SPIEL SCANNEN", self.scan_game, accent=True).pack(side="right", padx=2)
        self.tl = tree(left, [("k", "KLASSE.FELD"), ("n", "ANZ."), ("t", "TYP"), ("o", "OFFSET")], [300, 50, 70, 60], height=16)
        with_scroll(left, self.tl)
        self.tl.bind("<<TreeviewSelect>>", lambda _e: self._on_pick())
        self.lbl_list = label(left, "")
        self.lbl_list.pack(anchor="w")

        right = tk.Frame(pan, bg=BG)
        pan.add(right, weight=3)
        self.lbl_cur = label(right, "← links ein Feld anklicken (z. B. gold, hp, money)", dim=False)
        self.lbl_cur.pack(anchor="w")
        bar = tk.Frame(right, bg=BG)
        bar.pack(fill="x", pady=2)
        self.v_live = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="live aktualisieren", variable=self.v_live, bg=BG, fg=TEXT_DIM, selectcolor=BG,
                       activebackground=BG, font=FONT_LABEL).pack(side="left", padx=4)
        button(bar, "↻ INSTANZEN NEU", lambda: self.refind(force=True)).pack(side="right", padx=2)
        self.tr = tree(right, [("f", SNOW), ("v", "LIVE-WERT"), ("a", "OBJEKT-ADRESSE"), ("w", "WERT-ADRESSE")],
                       [28, 130, 140, 140], height=12,
                       actions=[("Wert ändern…", self.edit_dialog), (f"{SNOW} Einfrieren", self.freeze_sel),
                                ("Auftauen", self.unfreeze_sel), ("Alle auftauen", self.unfreeze_all),
                                (None, None), ("Im Speicher zeigen", self.to_memory)])
        with_scroll(right, self.tr)
        self.tr.bind("<Double-1>", lambda _e: self.edit_dialog())
        ed = tk.Frame(right, bg=BG)
        ed.pack(fill="x", pady=2)
        label(ed, "NEUER WERT").pack(side="left")
        self.v_val = tk.StringVar()
        ve = entry(ed, self.v_val, 14)
        ve.pack(side="left", padx=4)
        ve.bind("<Return>", lambda _e: self.set_value())
        button(ed, "SETZEN", self.set_value, accent=True).pack(side="left", padx=2)
        self.v_scope = tk.StringVar(value="Auswahl")
        ttk.Combobox(ed, textvariable=self.v_scope, values=("Auswahl", "alle Instanzen"), width=14,
                     state="readonly").pack(side="left", padx=6)
        for txt, val in (("×2", "*2"), ("+100", "+100"), ("+1000", "+1000"), ("99999", "99999")):
            button(ed, txt, lambda v=val: self.set_value(v)).pack(side="left", padx=1)
        fz = tk.Frame(right, bg=BG)
        fz.pack(fill="x", pady=2)
        button(fz, f"{SNOW} EINFRIEREN", self.freeze_sel, accent=True).pack(side="left", padx=2)
        button(fz, "AUFTAUEN", self.unfreeze_sel).pack(side="left", padx=2)
        self.lbl_fz = label(fz, "")
        self.lbl_fz.pack(side="left", padx=8)
        label(right, "Doppelklick ändert den Wert. '+100' und '*2' rechnen vom aktuellen Wert aus. Statische Felder "
                     "(Singletons, Spielstand-Daten) haben genau eine Zeile.", dim=True).pack(anchor="w")

    def _build_methods(self, page):
        self.nb.add(page, text="METHODEN (Cheats)")
        fr = tk.Frame(page, bg=BG)
        fr.pack(fill="x", pady=2)
        label(fr, "METHODE SUCHEN").pack(side="left")
        self.v_mq = tk.StringVar()
        e = entry(fr, self.v_mq, 30)
        e.pack(side="left", padx=4)
        e.bind("<Return>", lambda _e: self._fill_methods())
        button(fr, "SUCHEN", self._fill_methods, accent=True).pack(side="left", padx=2)
        label(fr, "Beispiele: 'Money', 'IsDead', 'Damage', 'Stamina' - mehrere Wörter = alle müssen vorkommen",
              dim=True).pack(side="left", padx=8)
        self.ml = tree(page, [("k", "KLASSE.METHODE"), ("s", "SIGNATUR"), ("r", "RVA")], [300, 420, 90], height=11)
        with_scroll(page, self.ml)
        act = tk.Frame(page, bg=BG)
        act.pack(fill="x", pady=2)
        button(act, "gibt immer TRUE", lambda: self.apply_patch("true"), accent=True).pack(side="left", padx=2)
        button(act, "gibt immer FALSE", lambda: self.apply_patch("false")).pack(side="left", padx=2)
        button(act, "gibt Wert zurück…", lambda: self.apply_patch("value")).pack(side="left", padx=2)
        button(act, "Methode leer machen (void)", lambda: self.apply_patch("noop")).pack(side="left", padx=2)
        label(act, "wirkt sofort im laufenden Spiel", dim=True).pack(side="left", padx=8)
        label(page, "ANGEWENDET").pack(anchor="w")
        self.al = tree(page, [("s", "AN"), ("t", "PATCH"), ("a", "ADRESSE")], [40, 520, 140], height=5)
        with_scroll(page, self.al)
        ab = tk.Frame(page, bg=BG)
        ab.pack(fill="x", pady=2)
        button(ab, "AN / AUS", self.toggle_patch).pack(side="left", padx=2)
        button(ab, "ENTFERNEN (Original zurück)", self.remove_patch).pack(side="left", padx=2)
        button(ab, "ALLE ZURÜCK", self.remove_all).pack(side="left", padx=2)
        button(ab, "EXPORT .reapproj…", self.export_patches, accent=True).pack(side="right", padx=2)

    def _build_names(self, page):
        self.nb.add(page, text="NAMEN (Items, IDs)")
        fr = tk.Frame(page, bg=BG)
        fr.pack(fill="x", pady=2)
        label(fr, "ENUM DURCHSUCHEN").pack(side="left")
        self.v_nq = tk.StringVar()
        e = entry(fr, self.v_nq, 30)
        e.pack(side="left", padx=4)
        e.bind("<KeyRelease>", lambda _e: self._fill_names())
        label(fr, "z. B. 'Item Apple' - links der Enum-Name, rechts der Zahlenwert für Give-/Set-Funktionen",
              dim=True).pack(side="left", padx=8)
        self.nl = tree(page, [("e", "ENUM"), ("n", "NAME"), ("v", "WERT"), ("h", "HEX")], [260, 360, 90, 90], height=20)
        with_scroll(page, self.nl)
        self.nl.bind("<Double-1>", lambda _e: self._copy_name_value())
        self.lbl_names = label(page, "")
        self.lbl_names.pack(anchor="w")

    # ------------------------------------------------------------------ Laden
    def _autoload(self):
        g = self.v_game.get().strip()
        if g and os.path.isdir(g) and self.game is None:
            self.load()

    def pick_game(self):
        d = filedialog.askdirectory(parent=self.win, title="Ordner mit dump.cs / script.json / DummyDll")
        if d:
            self.v_game.set(d)
            self.load()

    def load(self):
        folder = self.v_game.get().strip()
        if not folder or not os.path.isdir(folder):
            return self.log("UNITY: erst SPIEL-ORDNER wählen", "warn")
        self.lbl.configure(text="Lade dump.cs und script.json (große Spiele: bis ~20 Sekunden) …", fg=WARN)

        def job():
            files = D.find_game_files(folder)
            return D.GameDump(files, log=lambda m: self.win.ui(lambda: self.log(f"UNITY: {m}", "info"))).load()

        def ok(g):
            self.game, self.live, self.mod_base = g, None, None
            self.freezer.clear()
            self.counts, self.inited = None, set()
            self.rows, self.cur = [], None
            self._cfg["game"] = folder
            _save_cfg(self._cfg)
            self._rebuild_targets()
            self._fill_names()
            self.lbl.configure(
                text=f"{g.title}: {len(g.classes)} Klassen, {len(self.targets)} Werte, {len(g.all_methods())} Methoden "
                     "- jetzt Spiel starten und ② MODUL ERKENNEN", fg=ACCENT)

        def err(e):
            self.lbl.configure(text=f"Fehler: {e}", fg="#ff3366")
            self.log(f"UNITY: {e}", "err")

        self.bg(job, ok, err)

    def _rebuild_targets(self):
        if not self.game:
            return
        self.targets, self.static_keys = [], set()
        hide = self.v_gen.get()
        for c, f, prim, _s in self.game.value_targets(self.v_only.get()):
            if hide and D.is_generated(c, f):
                continue
            self.targets.append(Q.Target(c.full, D.clean_field_name(f.name), prim, f.offset, category="alle"))
        for c, f in self.game.static_targets():
            if self.v_only.get() and not c.image.startswith("Assembly-CSharp"):
                continue
            if hide and D.is_generated(c, f):
                continue
            t = Q.Target(c.full, D.clean_field_name(f.name), D.PRIMS[f.prim] if f.prim in D.PRIMS else f.prim, f.offset,
                         category="statisch")
            if t.writable and f.offset >= 0:
                self.targets.append(t)
                self.static_keys.add(t.key)
        self.targets.sort(key=lambda t: (t.cls.lower(), t.offset))
        self._fill_targets()

    def _count_of(self, t):
        """Objekte im Speicher fuer das Ziel (None = noch kein Scan). Statische Felder: 1, wenn die Klasse initialisiert ist."""
        if self.counts is None:
            return None
        if t.key in self.static_keys:
            return 1 if (t.cls in self.inited or self.counts.get(t.cls)) else 0
        return self.counts.get(t.cls, 0)

    def _fill_targets(self):
        self.tl.delete(*self.tl.get_children())
        q = self.v_q.get().strip().lower().split()
        only_live = self.v_live_only.get() and self.counts is not None
        self.shown = []
        for t in self.targets:
            if not all(p in t.key.lower() for p in q):
                continue
            if only_live and not self._count_of(t):
                continue
            self.shown.append(t)
        for i, t in enumerate(self.shown[:MAX_ROWS]):
            typ = t.type + (" (statisch)" if t.key in self.static_keys else "")
            n = self._count_of(t)
            self.tl.insert("", "end", iid=str(i), values=(t.key, "" if n is None else n, typ, f"{t.offset:#x}"))
        n = len(self.shown)
        hint = ""
        if self.counts is None:
            hint = "  - ② b. SPIEL SCANNEN zeigt nur Felder von Klassen, die im Spiel wirklich existieren"
        elif only_live:
            hint = f"  - nur Klassen mit Objekten im Speicher ({len([c for c, v in self.counts.items() if v])} Klassen)"
        self.lbl_list.configure(
            text=f"{n} Werte" + (f" - nur die ersten {MAX_ROWS} sichtbar, Suchwort eingeben" if n > MAX_ROWS else hint),
            fg=WARN if n > MAX_ROWS else TEXT_DIM)

    def scan_game(self):
        client = self._need_client()
        if not client:
            return

        def job():
            live = self._ensure_base(client)
            live.set_maps(self._maps(client))
            live.drop_cache()

            def prog(done, total):
                self.win.ui(lambda: self.lbl.configure(
                    text=f"Scanne Spiel-Speicher … {done * 100 // total}% ({done >> 20} / {total >> 20} MB)", fg=WARN))

            counts, inited = live.census(progress=prog)
            return self._roll_up(counts), inited

        def ok(r):
            self.counts, self.inited = r
            n = len([c for c, v in self.counts.items() if v])
            self.lbl.configure(text=f"Scan fertig: {n} Klassen haben Objekte im Speicher - die Liste zeigt jetzt nur diese",
                               fg=ACCENT)
            self.log(f"UNITY: Scan fertig, {n} Klassen mit Objekten", "ok")
            self._fill_targets()

        self.bg(job, ok, lambda e: (self.lbl.configure(text=f"Fehler beim Scan: {e}", fg="#ff3366"),
                                    self.log(f"UNITY: {e}", "err")))

    def _roll_up(self, counts):
        """Objekte einer Unterklasse zaehlen auch fuer ihre Basisklassen (geerbte Felder stehen im Dump bei der Basis)."""
        out = dict(counts)
        for full, n in counts.items():
            c = self.game.by_full.get(full)
            seen = 0
            while c is not None and seen < 30:
                c = self.game.parent_of(c)
                if c is None:
                    break
                out[c.full] = out.get(c.full, 0) + n
                seen += 1
        return out

    # ------------------------------------------------------------------ Modul / Live
    def _need_client(self):
        if self.win.client is None:
            self.log("UNITY: nicht verbunden (Haupt-Fenster: VERBINDEN)", "err")
            return None
        if not self.game:
            self.log("UNITY: erst Spiel-Ordner laden", "warn")
            return None
        return self.win.client

    @staticmethod
    def _maps(client):
        return client.get_maps_named() if hasattr(client, "get_maps_named") else client.get_maps()

    def _make_live(self, client, base):
        try:
            st = int(self.v_static.get().strip(), 16)
        except ValueError:
            st = D.K_STATIC_FIELDS
        return D.Il2CppLive(client.read_memory, self.game, base, self._maps(client), static_off=st,
                            log=lambda m: self.win.ui(lambda: self.log(f"UNITY: {m}", "info")))

    def detect_base(self):
        client = self._need_client()
        if not client:
            return
        manual = _hex_or_none(self.v_base.get())
        self.lbl.configure(text="Suche das IL2CPP-Modul im Spiel …", fg=WARN)

        def job():
            maps = client.get_maps_named() if hasattr(client, "get_maps_named") else client.get_maps()
            if manual:
                ok_n, tried = D.check_base(client.read_memory, manual, self.game, maps=maps)
                if ok_n == 0:
                    raise D.DumpError(f"Die eingetragene Basis {manual:#x} passt nicht zu den Klassennamen aus dump.cs.")
                return manual, ok_n
            base = D.find_module_base(client.read_memory, maps, self.game,
                                      log=lambda m: self.win.ui(lambda: self.log(f"UNITY: {m}", "ok")))
            return base, D.check_base(client.read_memory, base, self.game)[0]

        def ok(r):
            self.mod_base, n = r
            self.v_base.set(hex(self.mod_base))
            self.live = None
            self.lbl.configure(text=f"IL2CPP-Modul bei {self.mod_base:#x} bestätigt ({n} Klassen) - WERTE / METHODEN sind bereit",
                               fg=ACCENT)

        self.bg(job, ok, lambda e: (self.lbl.configure(text=f"Fehler: {e}", fg="#ff3366"), self.log(f"UNITY: {e}", "err")))

    def _ensure_base(self, client):
        """Im Job-Thread: Basis kennen (Feld oder automatisch) und Il2CppLive bereitstellen."""
        if self.mod_base is None:
            m = _hex_or_none(self.v_base.get())
            self.mod_base = m or D.find_module_base(client.read_memory, self._maps(client), self.game)
            self.win.ui(lambda: self.v_base.set(hex(self.mod_base)))
        if self.live is None or self.live.base != self.mod_base:
            self.live = self._make_live(client, self.mod_base)
        return self.live

    def _on_pick(self):
        sel = self.tl.selection()
        if not sel:
            return
        self.cur = self.shown[int(sel[0])]
        self.rows = []
        self._render()
        self.lbl_cur.configure(text=f"{self.cur.key}  [{self.cur.type}]  - suche Instanzen im Spiel …", fg=WARN)
        if self._pending is not None:
            try:
                self.after_cancel(self._pending)
            except Exception:  # noqa: BLE001
                pass
        self._pending = self.after(250, self.refind)

    def refind(self, force=False):
        self._pending = None
        cur, client = self.cur, self.win.client
        if cur is None:
            return self.log("UNITY: erst ein Feld anklicken", "warn")
        if self._need_client() is None:
            return
        is_static = cur.key in self.static_keys

        def job():
            live = self._ensure_base(client)
            if force:
                live.drop_cache()
                live.set_maps(self._maps(client))
            cls = self.game.by_full.get(cur.cls)
            self.win.ui(lambda: self.log("UNITY: suche Klasse/Instanzen im Speicher (beim ersten Mal etwas Geduld) …", "info"))
            if is_static:
                sb = live.static_base(cls)
                return [{"addr": sb, "vaddr": sb + cur.offset, "val": None, "txt": "?"}] if sb else []
            return [{"addr": a, "vaddr": a + cur.offset, "val": None, "txt": "?"} for a in live.instances(cls, use_cache=not force)]

        def ok(rows):
            if cur is not self.cur:
                return
            self.rows = rows
            for r in rows[:MAX_LIVE_ROWS]:
                try:
                    r["val"], r["txt"] = Q.read_value(client.read_memory, r["vaddr"], cur)
                except Exception:  # noqa: BLE001
                    pass
            self._render()
            if rows:
                src = {"cache": "sofort aus dem Scan", "scan": "Speicher durchsucht"}.get(getattr(self.live, "last_source", ""), "")
                self.lbl_cur.configure(text=f"{cur.key}  [{cur.type}]  - {len(rows)} Instanz(en)" + (f" ({src})" if src else ""),
                                       fg=ACCENT)
            else:
                self.lbl_cur.configure(text=self._why_none(cur, is_static), fg=WARN)

        self.bg(job, ok, lambda e: (self.log(f"UNITY: {e}", "err"), self.lbl_cur.configure(text=f"Fehler: {e}", fg="#ff3366")))

    def _why_none(self, t, is_static):
        if is_static:
            return (f"{t.key}: Klasse im Spiel noch nicht initialisiert (oder STATIC-OFFSET passt nicht). Spielstand laden, "
                    "dann ↻ INSTANZEN NEU.")
        return (f"{t.key}: kein Objekt dieser Klasse im Speicher. Die Klasse wird oft erst im Spiel erzeugt - "
                "Spielstand laden / Menü öffnen, dann ↻ INSTANZEN NEU. Alternativ ein anderes Feld derselben Klasse versuchen.")

    def _render(self):
        self.tr.delete(*self.tr.get_children())
        for i, r in enumerate(self.rows[:MAX_ROWS]):
            self.tr.insert("", "end", iid=str(i), values=(SNOW if r["vaddr"] in self.freezer else "", r["txt"],
                                                          f"{r['addr']:#x}", f"{r['vaddr']:#x}"))
        self.lbl_fz.configure(text=f"{len(self.freezer)} eingefroren" if len(self.freezer) else "")

    def _sel_rows(self):
        if not self.rows:
            self.log("UNITY: keine Instanzen - erst ein Feld anklicken", "warn")
            return []
        if self.v_scope.get() == "alle Instanzen":
            return list(self.rows)
        sel = [self.rows[int(i)] for i in self.tr.selection()]
        if not sel:
            self.log("UNITY: erst eine Zeile rechts wählen (oder Bereich 'alle Instanzen')", "warn")
        return sel

    def _tick(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:  # noqa: BLE001
            return
        self.after(TICK_MS, self._tick)
        client = self.win.client
        if self._busy or client is None or self.cur is None or not self.rows:
            return
        freezing = len(self.freezer) > 0
        if not freezing and not self.v_live.get():
            return
        cur = self.cur
        rows = self.rows[:MAX_LIVE_ROWS] if self.v_live.get() else []
        self._busy = True

        def job():
            if freezing:
                self.freezer.tick(client)
            out = []
            for r in rows:
                try:
                    out.append(Q.read_value(client.read_memory, r["vaddr"], cur))
                except Exception:  # noqa: BLE001
                    out.append((None, "?"))
            return out

        def done(vals):
            self._busy = False
            if cur is not self.cur:
                return
            for r, (v, txt) in zip(rows, vals):
                r["val"], r["txt"] = v, txt
            for i, r in enumerate(rows):
                if self.tr.exists(str(i)):
                    self.tr.set(str(i), "v", r["txt"])

        def err(e):
            self._busy = False
            self.log(f"UNITY Live/Freeze: {e}", "err")

        self.win.bg(job, done, err)

    def set_value(self, text=None):
        rows = self._sel_rows()
        if not rows:
            return
        cur, client = self.cur, self.win.client
        text = self.v_val.get() if text is None else text
        try:
            jobs = [(r, Q.parse_input(cur, text, r["val"])) for r in rows]
        except ValueError as e:
            return self.log(f"UNITY: {e}", "err")

        def job():
            for r, v in jobs:
                Q.write_value(client.read_memory, client.write_memory, r["vaddr"], cur, v)
                if r["vaddr"] in self.freezer:
                    self.freezer.add(r["vaddr"], cur, v)
                r["val"], r["txt"] = Q.read_value(client.read_memory, r["vaddr"], cur)
            return len(jobs)

        self.bg(job, lambda n: (self._render(), self.log(f"UNITY: {cur.member} = {jobs[0][0]['txt']} ({n} Instanz(en))", "ok")))

    def edit_dialog(self):
        sel = self.tr.selection()
        if not sel or self.cur is None:
            return
        r = self.rows[int(sel[0])]
        v = simpledialog.askstring("Wert ändern", f"{self.cur.key}\naktuell: {r['txt']}\nneuer Wert:", parent=self.win)
        if v:
            self.set_value(v)

    def freeze_sel(self):
        rows = self._sel_rows()
        if not rows:
            return
        cur, client = self.cur, self.win.client

        def job():
            for r in rows:
                v, _t = Q.read_value(client.read_memory, r["vaddr"], cur)
                self.freezer.add(r["vaddr"], cur, v)
            return len(rows)

        self.bg(job, lambda n: (self._render(), self.log(f"UNITY: {n} Wert(e) eingefroren (aktueller Wert wird gehalten)", "ok")))

    def unfreeze_sel(self):
        for r in self._sel_rows():
            self.freezer.remove(r["vaddr"])
        self._render()

    def unfreeze_all(self):
        self.freezer.clear()
        self._render()

    def to_memory(self):
        sel = self.tr.selection()
        mem = getattr(self.win, "t_mem", None)
        if not sel or mem is None:
            return
        try:
            mem.v_addr.set(f"{self.rows[int(sel[0])]['vaddr']:#x}")
            self.win.show_tab(mem)
        except Exception as e:  # noqa: BLE001
            self.log(f"UNITY: Speicher-Tab nicht erreichbar: {e}", "warn")

    # ------------------------------------------------------------------ Methoden-Patches
    def _fill_methods(self):
        self.ml.delete(*self.ml.get_children())
        if not self.game:
            return self.log("UNITY: erst Spiel-Ordner laden", "warn")
        self.mshown = self.game.search_methods(self.v_mq.get())
        for i, m in enumerate(self.mshown[:MAX_ROWS]):
            self.ml.insert("", "end", iid=str(i), values=(m.key, m.sig, f"{m.rva:#x}"))

    def apply_patch(self, mode):
        client = self._need_client()
        sel = self.ml.selection()
        if not client or not sel:
            return self.log("UNITY: erst eine Methode in der Liste wählen", "warn") if client else None
        m = self.mshown[int(sel[0])]
        value = None
        if mode == "value":
            value = simpledialog.askstring("Rückgabewert", f"{m.sig}\nWert, den die Methode immer liefern soll "
                                           "(Zahl, z. B. 99999 oder 1.5):", parent=self.win)
            if value is None:
                return
        if m.n_params > 0 and mode in ("true", "false", "value", "noop"):
            pass  # Parameter sind fuer diese Patches egal (Methode kehrt sofort zurueck)
        if m.static is False and m.name in (".ctor", ".cctor"):
            return self.log("UNITY: Konstruktoren werden nicht gepatcht", "warn")
        try:
            new = D.make_patch(m, mode, value)
        except (ValueError, TypeError) as e:
            return messagebox.showwarning("Nicht möglich", str(e), parent=self.win)

        def job():
            live = self._ensure_base(client)
            addr = live.method_addr(m)
            orig = client.read_memory(addr, len(new))
            if orig[:1] == b"\xc3" or orig == new:
                raise RuntimeError("Dort steht schon ein ret / der Patch - Methode evtl. schon gepatcht oder nicht lesbar")
            client.write_memory(addr, new)
            return AppliedPatch(m, mode, value, addr, orig, new)

        def ok(p):
            self.applied.append(p)
            self._fill_applied()
            self.log(f"UNITY: {p.title}  @ {p.addr:#x}", "ok")

        self.bg(job, ok, lambda e: self.log(f"UNITY: Patch fehlgeschlagen: {e}", "err"))

    def _fill_applied(self):
        self.al.delete(*self.al.get_children())
        for i, p in enumerate(self.applied):
            self.al.insert("", "end", iid=str(i), values=("AN" if p.on else "aus", p.title, f"{p.addr:#x}"))

    def _sel_applied(self):
        return [self.applied[int(i)] for i in self.al.selection()]

    def toggle_patch(self):
        client = self.win.client
        ps = self._sel_applied()
        if not ps or client is None:
            return

        def job():
            for p in ps:
                client.write_memory(p.addr, p.original if p.on else p.new)
                p.on = not p.on

        self.bg(job, lambda _r: self._fill_applied())

    def remove_patch(self):
        self._restore(self._sel_applied())

    def remove_all(self):
        self._restore(list(self.applied))

    def _restore(self, ps):
        client = self.win.client
        if not ps or client is None:
            return

        def job():
            for p in ps:
                if p.on:
                    client.write_memory(p.addr, p.original)
                    p.on = False
            return ps

        def ok(done):
            for p in done:
                if p in self.applied:
                    self.applied.remove(p)
            self._fill_applied()
            self.log(f"UNITY: {len(done)} Patch(es) zurückgesetzt", "ok")

        self.bg(job, ok)

    def export_patches(self):
        if not self.applied:
            return self.log("UNITY: nichts angewendet - erst Methoden patchen", "warn")
        folder = filedialog.askdirectory(parent=self.win, title="Ordner für die .reapproj-Dateien")
        if not folder:
            return
        n = 0
        for p in self.applied:
            doc = D.reapproj_for_patch(
                p.title, p.method.rva, p.original, p.new,
                info=f"Unity/IL2CPP: {p.method.sig}  RVA {p.method.rva:#x} im IL2CPP-Modul. Image-Basis = IL2CPP-Modul-Basis.")
            D.write_reapproj(folder, doc)
            n += 1
        self.log(f"UNITY: {n} Datei(en) in {folder}. In ReaperPy die Image-Basis auf die IL2CPP-Modul-Basis stellen "
                 f"({self.v_base.get() or 'siehe MODUL-BASIS'}).", "ok")

    # ------------------------------------------------------------------ Namen
    def _fill_names(self):
        self.nl.delete(*self.nl.get_children())
        if not self.game:
            return
        q = self.v_nq.get().strip()
        if not q:
            self.lbl_names.configure(text=f"{sum(1 for c in self.game.classes if c.kind == 'enum')} Enums - Suchwort eingeben",
                                     fg=TEXT_DIM)
            return
        self.nshown = self.game.enum_search(q, limit=MAX_ROWS)
        for i, (c, n, v) in enumerate(self.nshown):
            self.nl.insert("", "end", iid=str(i), values=(c.name, n, v, hex(v) if v >= 0 else ""))
        self.lbl_names.configure(text=f"{len(self.nshown)} Treffer - Doppelklick kopiert den Wert", fg=TEXT_DIM)

    def _copy_name_value(self):
        sel = self.nl.selection()
        if sel:
            v = str(self.nshown[int(sel[0])][2])
            self.clipboard_clear()
            self.clipboard_append(v)
            self.log(f"UNITY: Wert {v} kopiert", "ok")
