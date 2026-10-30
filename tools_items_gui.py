"""tools_items_gui.py - Tab "ITEMS": alle Items eines Unreal-Spiels als fertigen Trainer, in drei Schritten.

  1) SPIEL     Spiel-Ordner waehlen (wird gemerkt) und in ReaperPy verbinden.
  2) ITEMS     ITEMS FINDEN: das Tool sucht selbst die Item-Tabelle und die Funktion, die Items gibt, liest alle Items
               und teilt sie nach Kategorie ein.  Haken setzen/entfernen, Suche, Kategorie-Filter.
  3) TRAINER   Menge eintragen, TRAINER SPEICHERN: je Kategorie Pakete mit 14 Items ("Fische 1", "Fische 2" ...),
               bei sehr vielen Items mehrere Projekte.  Der Ordner wird in ReaperPy als Projekt geladen.

Keine Tabellen-/FName-/ID-Kenntnisse noetig.  Die Logik steckt in ue_items.py (ohne Oberflaeche testbar); die Cave baut
cave_trainer.py / ue_cavegen.py, die Tabelle liest ue_profile.py.  Die alten Tabs UE-LIVE / UE-ENTDECKER bleiben fuer
Spezialfaelle.
"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cave_trainer as TR
import imagebase as IB
import ue_items as IT
import ue_profile as P
import ue_quick as Q
from tools_common import (BG, BG_CARD, ACCENT, ERROR, FONT_HEAD, FONT_LABEL, TEXT, TEXT_DIM, WARN, BaseTab, entry,
                          tree, with_scroll)
from tools_scan_gui import _check, card, clabel, pbtn

MAX_SHOWN = 5000
ALL_CATS = "alle Kategorien"
CHK = {True: "☑", False: "☐"}


class ItemsTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.prof = None
        self.func = None                  # gewaehlte Geben-Funktion (Suggestion)
        self.funcs = []                   # baubare Geben-Funktionen
        self.func_bad = []                # [(Suggestion, Grund)]
        self.live_tables = []             # [(addr, name)] aus dem laufenden Spiel
        self.rated_tables = []            # alle Tabellen bewertet (ue_items.rate_tables), beste zuerst
        self.rated_funcs = []             # alle baubaren Geben-Funktionen bewertet (ue_items.rate_functions)
        self.func_rating = None           # Bewertung der gewaehlten Funktion
        self.cands = []                   # Tabellen-Vorschlaege aus dem SDK
        self.table = None                 # (addr, name) der gelesenen Tabelle
        self.items, self.on, self.view = [], [], []
        self.out_dirs = []
        self.basecheck = None             # imagebase.Result der letzten Pruefung
        self.cap = None                   # {'code': Byte, 'data': Byte} freier Platz fuer die Cave im Spiel
        self._busy = False
        self.v_q = tk.StringVar()
        self.v_cat = tk.StringVar(value=ALL_CATS)
        self.v_amount = tk.StringVar(value="999")
        self.v_table = tk.StringVar()
        self.v_func = tk.StringVar()
        self.v_expert = tk.BooleanVar(value=False)        # Auswahl-Zeile (Tabelle/Funktion) einblenden
        self.v_all = tk.BooleanVar(value=False)           # auch unpassende Tabellen/Funktionen zeigen

        tk.Label(self, text="▸  ITEMS  →  TRAINER", bg=BG, fg=ACCENT, font=FONT_HEAD).pack(anchor="w", padx=14,
                                                                                         pady=(10, 0))
        tk.Label(self, text="Alle Items deines Unreal-Spiels als fertiger Trainer - in drei Schritten, ohne "
                            "Vorkenntnisse.", bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(anchor="w", padx=14, pady=(0, 6))
        self._build_step1()
        self._build_step3()
        self._build_step2()
        self.refresh_status()
        self.bind("<Map>", lambda _e: self.refresh_status())
        self.after(2500, self._tick)

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _build_step1(self):
        outer, body, _h = card(self, "①  SPIEL")
        outer.pack(fill="x", padx=12, pady=(0, 6))
        row = tk.Frame(body, bg=BG_CARD)
        row.pack(fill="x")
        self.lbl_game = tk.Label(row, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w", justify="left")
        self.lbl_game.pack(side="left", fill="x", expand=True)
        pbtn(row, "SPIEL-ORDNER WÄHLEN …", self.pick_game, primary=True).pack(side="right")
        self.lbl_conn = tk.Label(body, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w", justify="left")
        self.lbl_conn.pack(fill="x", pady=(4, 0))

    def _build_step2(self):
        outer, body, _h = card(self, "②  ITEMS FINDEN")
        outer.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        top = tk.Frame(body, bg=BG_CARD)
        top.pack(fill="x")
        self.b_find = pbtn(top, "🔎  ITEMS FINDEN", self.find_items, primary=True)
        self.b_find.pack(side="left")
        self.lbl_found = tk.Label(top, text="Klicke ITEMS FINDEN - alles Weitere passiert automatisch.", bg=BG_CARD,
                                  fg=TEXT_DIM, font=FONT_LABEL, anchor="w", justify="left", wraplength=820)
        self.lbl_found.pack(side="left", padx=12, fill="x", expand=True)
        self.b_base = pbtn(top, "BASIS ÜBERNEHMEN", self.adopt_base)          # nur sichtbar, wenn die Basis nicht stimmt

        opt = tk.Frame(body, bg=BG_CARD)
        opt.pack(fill="x", pady=(4, 0))
        self.chk_expert = _check(opt, "Auswahl selbst ändern (nur für Fortgeschrittene)", self.v_expert)
        self.chk_expert.configure(command=self._toggle_expert)
        self.chk_expert.pack(side="left")
        self.sel = tk.Frame(body, bg=BG_CARD)
        sel = self.sel
        clabel(sel, "Item-Liste").pack(side="left")
        self.cb_table = ttk.Combobox(sel, textvariable=self.v_table, values=[], width=30, state="readonly")
        self.cb_table.pack(side="left", padx=(6, 12))
        self.cb_table.bind("<<ComboboxSelected>>", lambda _e: self.pick_table())
        clabel(sel, "Geben-Funktion").pack(side="left")
        self.cb_func = ttk.Combobox(sel, textvariable=self.v_func, values=[], width=52, state="readonly")
        self.cb_func.pack(side="left", padx=6)
        self.cb_func.bind("<<ComboboxSelected>>", lambda _e: self.pick_func())
        self.chk_all = _check(sel, "auch unpassende zeigen", self.v_all)
        self.chk_all.configure(command=self._fill_choices)
        self.chk_all.pack(side="left", padx=8)
        self.opt_row = opt                                                  # die Auswahl-Zeile 'sel' erscheint darunter

        flt = tk.Frame(body, bg=BG_CARD)
        flt.pack(fill="x", pady=(8, 4))
        clabel(flt, "Suche").pack(side="left")
        q = entry(flt, self.v_q, 22)
        q.pack(side="left", padx=(6, 12))
        q.bind("<KeyRelease>", lambda _e: self.fill())
        clabel(flt, "Kategorie").pack(side="left")
        self.cb_cat = ttk.Combobox(flt, textvariable=self.v_cat, values=[ALL_CATS], width=22, state="readonly")
        self.cb_cat.pack(side="left", padx=(6, 12))
        self.cb_cat.bind("<<ComboboxSelected>>", lambda _e: self.fill())
        pbtn(flt, "ALLE AN", lambda: self.set_visible(True)).pack(side="left")
        pbtn(flt, "ALLE AUS", lambda: self.set_visible(False)).pack(side="left", padx=4)
        self.lbl_count = clabel(flt, "")
        self.lbl_count.pack(side="right")

        fr = tk.Frame(body, bg=BG_CARD)
        fr.pack(fill="both", expand=True)
        self.tv = tree(fr, [("c", "✓"), ("n", "ITEM"), ("k", "KATEGORIE")], [40, 340, 200], height=9,
                       anchors={"c": "center"},
                       actions=[("Auswahl anhaken", lambda: self.set_selected(True)),
                                ("Auswahl abhaken", lambda: self.set_selected(False)),
                                (None, None),
                                ("Nur diese Kategorie anhaken", self.only_category_of_selected),
                                ("Kategorie abhaken", self.uncheck_category_of_selected)])
        with_scroll(fr, self.tv)
        self.tv.bind("<Button-1>", self._click)
        self.tv.bind("<space>", lambda _e: self.set_selected(None))
        self.tv.bind("<Double-1>", self._double)

    def _build_step3(self):
        outer, body, _h = card(self, "③  TRAINER SPEICHERN")
        outer.pack(side="bottom", fill="x", padx=12, pady=(0, 8))
        row = tk.Frame(body, bg=BG_CARD)
        row.pack(fill="x")
        clabel(row, "Menge je Item").pack(side="left")
        e = entry(row, self.v_amount, 8)
        e.pack(side="left", padx=(6, 12))
        e.bind("<KeyRelease>", lambda _e: self.update_summary())
        self.lbl_plan = tk.Label(row, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w")
        self.lbl_plan.pack(side="left", fill="x", expand=True)
        self.b_save = pbtn(row, "💾  TRAINER SPEICHERN", self.save, primary=True)
        self.b_save.pack(side="right")
        pbtn(row, "ORDNER ÖFFNEN", self.open_folder).pack(side="right", padx=6)
        pbtn(row, "TRAINER PRÜFEN / ANPASSEN …", self.check_trainer).pack(side="right")
        self.lbl_done = tk.Label(body, text="", bg=BG_CARD, fg=TEXT_DIM, font=FONT_LABEL, anchor="w", justify="left",
                                 wraplength=1100)
        self.lbl_done.pack(fill="x", pady=(6, 0))

    # ------------------------------------------------------------------
    # Schritt 1: Spiel
    # ------------------------------------------------------------------
    def _ue(self):
        for t in getattr(self.win, "extra_tabs", []):
            if t.__class__.__name__ == "UeLiveTab":
                return t
        return None

    def _proj(self):
        return getattr(self._ue(), "proj", None)

    def pick_game(self):
        ue = self._ue()
        if ue is None:
            self.log("Tab UE-LIVE nicht gefunden - ohne ihn kann das Spiel nicht geladen werden", "err")
            return
        ue.pick_game()
        self.after(1500, self.refresh_status)

    def refresh_status(self):
        proj = self._proj()
        if proj is not None and getattr(proj, "sdk", None) is not None:
            title = getattr(proj, "title", "") or getattr(proj, "name", "") or "Spiel"
            self.lbl_game.configure(text=f"✔  Spiel geladen: {title}", fg=ACCENT)
        else:
            self.lbl_game.configure(text="✗  Noch kein Spiel-Ordner gewählt (Ordner mit offsets.json und SDK_HEADERS).",
                                    fg=WARN)
        if getattr(self.win, "client", None) is not None:
            self.lbl_conn.configure(text="✔  Mit der PS5 verbunden.", fg=ACCENT)
        else:
            self.lbl_conn.configure(text="✗  Nicht verbunden - im Hauptfenster auf VERBINDEN klicken, dann das Spiel "
                                         "starten und den Spielstand laden (nicht im Hauptmenü bleiben).", fg=WARN)

    def _tick(self):
        try:
            self.refresh_status()
            self.after(2500, self._tick)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Schritt 2: Items finden
    # ------------------------------------------------------------------
    def _ilog(self, msg):
        self.win.ui(lambda: self.log(msg, "info"))

    def _found(self, text, color=TEXT):
        self.lbl_found.configure(text=text, fg=color)

    def find_items(self):
        if self._busy:
            return self.log("Es läuft noch ein Auftrag - kurz warten", "warn")
        ue, proj = self._ue(), self._proj()
        if proj is None or getattr(proj, "sdk", None) is None:
            return self._found("Zuerst Schritt ①: Spiel-Ordner wählen.", ERROR)
        client = getattr(self.win, "client", None)
        if client is None:
            return self._found("Nicht verbunden - im Hauptfenster auf VERBINDEN klicken und den Spielstand laden.", ERROR)
        gp = getattr(getattr(self.win, "app", None), "gp", None)
        sdk = proj.sdk
        self._busy = True
        self._found("Suche läuft … (beim ersten Mal kann das je nach Spiel eine Minute dauern)", WARN)

        def job():
            sig = P.signature(sdk)
            prof = None
            if gp is not None and gp.discover and gp.discover.get("sig") == sig:
                try:
                    prof = P.from_json(gp.discover["json"])
                except ValueError:
                    prof = None
            fresh = prof is None
            if fresh:
                prof = P.build(sdk)
            live = Q.connect_live(client, proj, log=self._ilog, cached=getattr(ue, "live", None))
            if live.index is None:
                live.build_index()
            tables = P.find_table_objects(live)
            cands = IT.table_candidates(prof)
            rated_t = IT.rate_tables(cands, tables)                        # ALLE Tabellen des Spiels bewerten
            ranked = IT.choose_table(cands, tables)                        # nur die, die nach Items aussehen
            table = rows = cols = None
            for s, pick in ranked[:6]:                                   # erste Tabelle, die wirklich Zeilen liefert
                r, c = P.read_table(live.rd, live.fname_str, pick[0], s.data.get("columns", []))
                if r:
                    table, rows, cols = pick, r, c
                    break
            rated_f = IT.rate_functions(prof, sdk)                         # nur Funktionen, die der Trainer bauen kann
            funcs, bad = IT.give_candidates(prof, sdk)
            try:                                                      # stimmt die Image-Basis mit der Konsole ueberein?
                bc = IB.check_image_base(client.get_maps_named(), self.base)
            except Exception as e:  # noqa: BLE001
                bc = IB.Result("unknown", None, self.base, f"Image-Basis nicht prüfbar: {e}")
            try:                                                      # wie viel Platz hat die Cave in DIESEM Spiel?
                cap = TR.capacity(client.read_memory, [(m[0], m[1], m[2]) for m in client.get_maps()], self.base)
            except Exception as e:  # noqa: BLE001
                self._ilog(f"Platz fuer die Cave nicht ermittelt: {e}")
                cap = None
            return {"prof": prof, "sig": sig, "fresh": fresh, "live": live, "tables": tables, "cands": cands,
                    "table": table, "rows": rows or [], "cols": cols or [], "funcs": funcs, "bad": bad, "cap": cap, "basecheck": bc,
                    "rated_t": rated_t, "rated_f": rated_f}

        def ok(res):
            self._busy = False
            if gp is not None and res["fresh"]:
                gp.discover = {"sig": res["sig"], "json": P.to_json(res["prof"])}
                gp.save()
            if ue is not None:
                ue.live = res["live"]
            self.prof, self.live_tables, self.cands = res["prof"], res["tables"], res["cands"]
            self.funcs, self.func_bad = res["funcs"], res["bad"]
            self.rated_tables, self.rated_funcs = res["rated_t"], res["rated_f"]
            self.cap = res.get("cap")
            self._set_basecheck(res.get("basecheck"))
            self.func_rating = self.rated_funcs[0] if self.rated_funcs else None      # beste Funktion (erreichbare zuerst)
            good = [r for r in self.rated_funcs if r["relevant"]]
            if good:
                self.func_rating = good[0]
            self.func = self.func_rating["sug"] if self.func_rating else (self.funcs[0] if self.funcs else None)
            self.table = res["table"]
            self._fill_choices()
            self.set_items(res["rows"], res["cols"])
            self._report()

        def fail(e):
            self._busy = False
            self._found("Das hat nicht geklappt: " + (str(e) or e.__class__.__name__), ERROR)
            self.log(str(e), "err")
        self.bg(job, ok, fail)

    def _set_basecheck(self, bc):
        self.basecheck = bc
        if bc is not None and bc.status == "shifted":
            self.b_base.pack(side="right", padx=(8, 0))
            self.log(bc.message, "err")
        else:
            self.b_base.pack_forget()

    def adopt_base(self):
        """Die laut Speicherkarte geprüfte Basis im Hauptfenster einstellen (kein Raten: Wert kommt aus der Konsole)."""
        bc = self.basecheck
        app = getattr(self.win, "app", None)
        if bc is None or bc.status != "shifted" or app is None or not hasattr(app, "apply_imgbase"):
            return
        app.imgbase_var.set(hex(bc.live_base))
        app.apply_imgbase()
        self._set_basecheck(IB.Result("ok", bc.live_base, bc.live_base, ""))
        self.lbl_done.configure(text=f"Image-Basis auf {bc.live_base:#x} gestellt (laut Speicherkarte). "
                                     "Jetzt ITEMS FINDEN erneut klicken.", fg=ACCENT)

    def _toggle_expert(self):
        """Tabelle/Funktion nur auf Wunsch zeigen: fuer Anfaenger genuegt die Statuszeile."""
        if self.v_expert.get():
            self.sel.pack(fill="x", pady=(4, 0), after=self.opt_row)
        else:
            self.sel.pack_forget()

    def _table_choices(self):
        """[(Anzeigename, Bewertung)] - standardmaessig nur Tabellen, die nach Items aussehen."""
        rated = self.rated_tables
        shown = rated if self.v_all.get() else [r for r in rated if r["relevant"]]
        if not shown:
            shown = rated                           # nichts Passendes erkannt -> lieber alles zeigen als eine leere Liste
        return [(r["name"], r) for r in shown]

    def _func_choices(self):
        rated = self.rated_funcs
        shown = rated if self.v_all.get() else [r for r in rated if r["relevant"]]
        if not shown:
            shown = rated
        out = []
        for r in shown:
            label = IT.function_label(r)
            if not r["relevant"] and r["reasons"]:
                label += "   ⚠ " + ", ".join(r["reasons"])
            out.append((label, r))
        return out

    def _fill_choices(self):
        tabs, funcs = self._table_choices(), self._func_choices()
        self.cb_table.configure(values=[n for n, _r in tabs])
        self.cb_func.configure(values=[n for n, _r in funcs])
        self.v_table.set(self.table[1] if self.table else "")
        cur = next((n for n, r in funcs if self.func_rating is not None and r["sug"] is self.func_rating["sug"]), "")
        self.v_func.set(cur)

    @staticmethod
    def _func_title(s):
        return f"{s.data.get('owner', '')}.{s.data.get('name', s.title)}" if s is not None else ""

    def _report(self):
        parts = []
        if self.table and self.items:
            parts.append(f"✔ {len(self.items)} Items aus der Tabelle {self.table[1]}")
        elif self.live_tables:
            parts.append("✗ Keine Item-Liste automatisch erkannt - oben 'Auswahl selbst ändern' ankreuzen und eine Liste "
                         "wählen (Namen mit Item / Weapon / Loot stehen oben)")
        else:
            parts.append("✗ Im Spiel wurden keine Tabellen gefunden - Spielstand geladen (nicht im Hauptmenü)?")
        weak = self.func_rating is not None and not self.func_rating["relevant"]
        if self.func and not weak:
            parts.append(f"✔ Geben-Funktion: {self._func_title(self.func)}")
        elif self.func:
            parts.append(f"⚠ Geben-Funktion: {self._func_title(self.func)} - {self._weak_reason()}")
        else:
            why = self.func_bad[0][1] if self.func_bad else "keine Funktion zum Geben von Items im SDK"
            parts.append("✗ Keine Funktion gefunden, die der Trainer bauen kann (" + why + ") - dafür den Weg über "
                         "UE-ENTDECKER → INVENTAR-EINTRÄGE SUCHEN nutzen")
        if self.basecheck is not None and self.basecheck.status == "shifted":
            parts.insert(0, "✗ " + self.basecheck.message + " → BASIS ÜBERNEHMEN klicken")
        good = bool(self.items and self.func) and not weak and not (self.basecheck and self.basecheck.status == "shifted")
        self._found("   |   ".join(parts), ACCENT if good else WARN)
        self.update_summary()

    def _weak_reason(self):
        """Warum die gewaehlte Funktion nur eine Notloesung ist (leicht verstaendlich)."""
        r = self.func_rating or {}
        if r.get("reach") == "zero":
            return ("Der Trainer erreicht das Spiel-Objekt dieser Funktion nicht - sie bewirkt vermutlich nichts "
                    "(oder stürzt ab). Besser eine andere Funktion wählen, falls es eine gibt.")
        return "passt nur mit Einschränkung (" + ", ".join(r.get("reasons", [])) + ")"

    def pick_table(self):
        name = self.v_table.get()
        pick = next((t for t in self.live_tables if t[1] == name), None)
        ue = self._ue()
        live = getattr(ue, "live", None)
        if pick is None or live is None or self._busy:
            return
        cols = []
        rt = next((r for r in self.rated_tables if (r["addr"], r["name"]) == pick), None)
        if rt is not None and rt["sug"] is not None:
            cols = rt["sug"].data.get("columns", [])
        else:
            for s in self.cands:
                if P.best_table_for(s, [pick]) == pick:
                    cols = s.data.get("columns", [])
                    break
        self._busy = True

        def job():
            return P.read_table(live.rd, live.fname_str, pick[0], cols)

        def ok(res):
            self._busy = False
            self.table = pick
            self.set_items(*res)
            self._report()

        def fail(e):
            self._busy = False
            self.log(str(e), "err")
        self.bg(job, ok, fail)

    def pick_func(self):
        name = self.v_func.get()
        r = next((r for n, r in self._func_choices() if n == name), None)
        if r is not None:
            self.func_rating, self.func = r, r["sug"]
        self._report()

    # --- Liste ----------------------------------------------------------------------------------
    def set_items(self, rows, cols):
        self.items = IT.build_items(rows, cols)
        self.on = [True] * len(self.items)
        cats = sorted({i["category"] for i in self.items}, key=lambda k: (k == IT.OTHER, k.lower()))
        self.cb_cat.configure(values=[ALL_CATS] + cats)
        self.v_cat.set(ALL_CATS)
        self.v_q.set("")
        self.fill()

    def fill(self):
        self.tv.delete(*self.tv.get_children())
        q = self.v_q.get().strip().lower()
        cat = self.v_cat.get()
        self.view = []
        for i, it in enumerate(self.items):
            if q and q not in it["name"].lower():
                continue
            if cat != ALL_CATS and it["category"] != cat:
                continue
            self.view.append(i)
        for i in self.view[:MAX_SHOWN]:
            it = self.items[i]
            self.tv.insert("", "end", iid=str(i), values=(CHK[self.on[i]], it["name"], it["category"]))
        self.update_summary()

    def _refresh_rows(self, idx):
        for i in idx:
            it = self.items[i]
            try:
                self.tv.item(str(i), values=(CHK[self.on[i]], it["name"], it["category"]))
            except tk.TclError:
                pass                                        # Zeile gerade ausgefiltert
        self.update_summary()

    def _click(self, ev):
        try:
            if self.tv.identify_region(ev.x, ev.y) != "cell" or self.tv.identify_column(ev.x) != "#1":
                return None
            iid = self.tv.identify_row(ev.y)
        except Exception:
            return None
        if iid:
            self.on[int(iid)] = not self.on[int(iid)]
            self._refresh_rows([int(iid)])
            return "break"
        return None

    def _double(self, ev):
        try:
            if self.tv.identify_column(ev.x) == "#1":
                return "break"
            iid = self.tv.identify_row(ev.y)
        except Exception:
            return None
        if iid:
            self.on[int(iid)] = not self.on[int(iid)]
            self._refresh_rows([int(iid)])
            return "break"
        return None

    def _sel_idx(self):
        return [int(i) for i in self.tv.selection()]

    def set_selected(self, flag):
        idx = self._sel_idx()
        if not idx:
            return
        if flag is None:                                    # Leertaste: umschalten nach dem ersten Eintrag
            flag = not self.on[idx[0]]
        for i in idx:
            self.on[i] = flag
        self._refresh_rows(idx)

    def set_visible(self, flag):
        for i in self.view:
            self.on[i] = flag
        self.fill()

    def _cat_of_selected(self):
        idx = self._sel_idx()
        return self.items[idx[0]]["category"] if idx else None

    def only_category_of_selected(self):
        cat = self._cat_of_selected()
        if cat is None:
            return
        self.on = [it["category"] == cat for it in self.items]
        self.fill()

    def uncheck_category_of_selected(self):
        cat = self._cat_of_selected()
        if cat is None:
            return
        self.on = [False if it["category"] == cat else f for it, f in zip(self.items, self.on)]
        self.fill()

    # ------------------------------------------------------------------
    # Schritt 3: Trainer speichern
    # ------------------------------------------------------------------
    def _chosen(self):
        return [it for it, f in zip(self.items, self.on) if f]

    def _projects(self):
        groups = IT.group_items(self._chosen())
        pkgs = IT.packages(groups)
        per = IT.rows_per_project(self.cap["code"] if self.cap else 0)
        return pkgs, IT.split_projects(pkgs, max_rows=per)

    def update_summary(self):
        n_all, chosen = len(self.items), self._chosen()
        shown = f"{len(self.view)} sichtbar, " if len(self.view) != n_all else ""
        self.lbl_count.configure(text=f"{shown}{len(chosen)} von {n_all} Items angehakt")
        if not chosen:
            self.lbl_plan.configure(text="Noch keine Items angehakt.", fg=TEXT_DIM)
            return
        pkgs, projects = self._projects()
        self.lbl_plan.configure(
            text=f"→ {len(chosen)} Items in {len(pkgs)} Einträgen" + (f", verteilt auf ca. {len(projects)} Projekte"
                                                                      if len(projects) > 1 else ""), fg=TEXT)

    def _amount(self):
        try:
            v = int(self.v_amount.get().strip() or "1", 0)
        except ValueError:
            raise ValueError("Die Menge muss eine ganze Zahl sein (z. B. 999)") from None
        if not 1 <= v <= 0xFFFFFFFF:
            raise ValueError("Die Menge muss zwischen 1 und 4294967295 liegen")
        return v

    def _base_dir(self):
        import paths
        proj = self._proj()
        game = TR.clean_name(getattr(proj, "title", "") or getattr(proj, "name", "") or "Spiel")
        return os.path.join(paths.sub_dir("trainer"), game)

    def save(self):
        if self._busy:
            return self.log("Es läuft noch ein Auftrag - kurz warten", "warn")
        try:
            amount = self._amount()
        except ValueError as e:
            self.lbl_done.configure(text=str(e), fg=ERROR)
            return
        chosen = self._chosen()
        if not chosen:
            self.lbl_done.configure(text="Erst Items anhaken (Schritt ②).", fg=ERROR)
            return
        if self.func is None:
            self.lbl_done.configure(text="Es gibt keine baubare Geben-Funktion - siehe Meldung bei Schritt ②.", fg=ERROR)
            return
        ue, proj, client = self._ue(), self._proj(), getattr(self.win, "client", None)
        live = getattr(ue, "live", None)
        if proj is None or client is None or live is None:
            self.lbl_done.configure(text="Erst Schritt ① und ITEMS FINDEN (Spiel laden, verbinden).", fg=ERROR)
            return
        if self.basecheck is not None and self.basecheck.status == "shifted":
            self.lbl_done.configure(text="✗ " + self.basecheck.message + " → oben BASIS ÜBERNEHMEN klicken.", fg=ERROR)
            return
        pkgs, _preview = self._projects()
        func, sdk, base, game = self.func, proj.sdk, self.base, getattr(proj, "title", "") or getattr(proj, "name", "")
        self._busy = True
        self.lbl_done.configure(text="Baue den Trainer … (nur Lesen im Spiel, es wird noch nichts verändert)", fg=WARN)

        def job():
            read = client.read_memory
            options, skipped = IT.make_options(pkgs, func, sdk, live, read, base, amount, log=self._ilog)
            pe, slots, notes = IT.hook_targets(sdk, live, read, base)
            for n in notes:
                self._ilog("Haken: " + n)
            maps = [(m[0], m[1], m[2]) for m in client.get_maps()]
            cap = TR.capacity(read, maps, base, log=self._ilog)               # echter freier Platz in diesem Spiel
            groups = TR.fit_options(options, cap["code"])                     # Projekte so gross, wie die Cave passt
            dirs = IT.project_dirs(self._base_dir(), len(groups))
            self._ilog(f"Platz fuer die Cave: {cap['code']} Byte -> {len(groups)} Projekt(e)")
            made = []
            for d, opts in zip(dirs, groups):                               # nur planen (lesend) - noch nichts schreiben
                p = TR.plan(read, maps, base, opts, None, pe, slots, log=self._ilog, client=client)
                made.append((d, len(opts), sum(len(o.rows) for o in opts), p))
            return made, skipped, maps

        def ok(res):
            made, skipped, maps = res
            lines = []
            for m in made:
                lines += ([f"{m[0]}:"] if len(made) > 1 else []) + ["  " + x for x in TR.preview_lines(TR.preview(m[3], maps))]
            if not self._ask_preview("\n".join(lines)):
                self._busy = False
                self.lbl_done.configure(text="Abgebrochen - es wurde nichts geschrieben.", fg=WARN)
                return
            try:
                for d, _n, _r, p in made:
                    TR.write_project(d, p, game=str(game))
            except Exception as e:  # noqa: BLE001
                return fail(e)
            self._busy = False
            self.out_dirs = [m[0] for m in made]
            total = sum(m[2] for m in made)
            msg = [f"✔ Fertig: {total} Items in {sum(m[1] for m in made)} Einträgen, gespeichert in:"]
            msg += [f"      {m[0]}" for m in made]
            if skipped:
                msg.append(f"   ({skipped} Items ohne Zahlen-ID übersprungen)")
            msg.append("So benutzt du ihn: In ReaperPy diesen Ordner als Projekt wählen → '00 BASIS' EINMAL aktivieren → "
                       "dann Einträge anklicken (im Spiel bleiben, Inventar danach neu öffnen).")
            if len(made) > 1:
                msg.append("Wichtig: Es gibt mehrere Projekte - immer nur EINES gleichzeitig aktivieren "
                           "(zum Wechseln erst dessen BASIS ausschalten).")
            msg.append("Am echten Spiel zuerst speichern; bei einem Absturz die Anleitung (README) im Projektordner lesen.")
            self.lbl_done.configure(text="\n".join(msg), fg=ACCENT)
            for w in made[0][3].warnings if made else []:
                self.log("   " + w, "info")
            self.log(f"Item-Trainer geschrieben: {', '.join(self.out_dirs)}", "ok")

        def fail(e):
            self._busy = False
            msg = str(e) or e.__class__.__name__
            self.lbl_done.configure(text="Das hat nicht geklappt: " + msg, fg=ERROR)
            self.log(msg, "err")
        self.bg(job, ok, fail)

    def open_folder(self):
        d = self.out_dirs[0] if self.out_dirs else self._base_dir()
        d = d if os.path.isdir(d) else os.path.dirname(d)
        try:
            os.makedirs(d, exist_ok=True)
            if os.name == "nt":
                os.startfile(d)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:  # noqa: BLE001
            self.log(f"{d}: {e}", "err")

    # ------------------------------------------------------------------
    # Fremden / alten Trainer pruefen und an DIESES Spiel anpassen
    # ------------------------------------------------------------------
    def check_trainer(self):
        """Ordner eines fertigen Item-Trainers waehlen -> pruefen (Spielversion, Item-Nummern) und ggf. anpassen."""
        start = self._base_dir()
        d = filedialog.askdirectory(parent=self.win, title="Trainer-Ordner wählen (mit _trainer_spec.json)",
                                    initialdir=start if os.path.isdir(start) else None)
        if d:
            self._check_dir(d)

    def _live_names(self):
        return {TR.clean_name(it["name"]): it["fname"] for it in self.items}

    def _ask_preview(self, text):
        """Dry-Run: zeigt, wo Cave und Schalter landen wuerden, bevor Dateien geschrieben werden."""
        warn = ""
        if self.func_rating is not None and not self.func_rating["relevant"]:
            warn = "\n\n⚠ " + self._weak_reason()
        return messagebox.askyesno("Trainer speichern?", "So würde der Trainer aussehen (bisher wurde nichts geschrieben):\n\n"
                                   + text + warn + "\n\nJetzt speichern?", parent=self.win)

    def _ask_adapt(self, text):
        return messagebox.askyesno("Trainer anpassen", text, parent=self.win)

    def _check_dir(self, d):
        client = getattr(self.win, "client", None)
        if client is None:
            self.lbl_done.configure(text="Nicht verbunden - im Hauptfenster auf VERBINDEN klicken.", fg=ERROR)
            return
        if self._busy:
            return self.log("Es läuft noch ein Auftrag - kurz warten", "warn")
        names = self._live_names()
        self._busy = True
        self.lbl_done.configure(text="Prüfe den Trainer … (nur Lesen)", fg=WARN)

        def job():
            res = TR.check_project(d, client.read_memory, self.base)
            cmp = TR.compare_fnames(d, names) if names else None
            moved = {}
            spec = TR._load_spec_raw(d)
            if spec and isinstance(spec.get("anchors"), dict) and not res["ok_version"]:
                # Signaturen: liegt die Funktion nur woanders (genau ein Treffer)?  Dann laesst sich das korrigieren.
                maps = [(m[0], m[1], m[2]) for m in client.get_maps()]
                found, rest = TR.moved_rvas(spec, TR.check_anchors(client, maps, self.base, spec), self.base)
                if found and not rest and int(spec.get("image_base", "0x0"), 16) == self.base:
                    moved = found
            return res, cmp, moved

        def ok(r):
            self._busy = False
            res, cmp, moved = r
            lines = [f"Trainer: {d}"]
            if res["ok_version"]:
                lines.append("✔ Passt zur Spielversion (Funktionen und Image-Basis stimmen überein).")
            elif moved:
                lines.append(f"↻ {len(moved)} Funktion(en) liegen in deinem Spiel an anderer Stelle (Update / anderer Build):")
                lines += [f"      +{o:#x} → +{n:#x}" for o, n in list(moved.items())[:3]]
                lines.append("   → Der Trainer kann automatisch auf die neuen Adressen angepasst werden.")
            else:
                lines.append("✗ Dieser Trainer wurde für eine ANDERE Spielversion / Image-Basis gebaut - NICHT aktivieren:")
                lines += ["      " + x for x in res["problems"][:3]]
                lines.append("   → Mit ITEMS FINDEN und TRAINER SPEICHERN einen eigenen Trainer für dein Spiel bauen.")
            if res["base_active"]:
                lines.append("ℹ Die BASIS-Cave dieses Trainers ist im Spiel gerade aktiv.")
            adapt = False
            if cmp is None:
                lines.append("ℹ Item-Nummern nicht geprüft: erst ITEMS FINDEN klicken (liest die Nummern deines Spiels).")
            else:
                good, changed, missing = cmp
                if not changed and not missing:
                    lines.append(f"✔ Alle {len(good)} Item-Nummern stimmen mit deinem Spiel überein.")
                else:
                    lines.append(f"✗ {len(changed)} Item-Nummern sind in deinem Spiel anders (und {len(missing)} Items fehlen) - "
                                 "deshalb passiert im Spiel nichts, wenn du einen Eintrag aktivierst.")
                    adapt = (res["ok_version"] or bool(moved)) and bool(changed)
            fix = bool(moved)
            self.lbl_done.configure(text="\n".join(lines), fg=ACCENT if res["ok_version"] and not adapt else WARN)
            if (adapt or fix) and self._ask_adapt(
                    ("Funktionen dieses Trainers liegen in deinem Spiel an anderer Stelle" if fix else
                     "Die Item-Nummern dieses Trainers passen nicht zu deinem Spiel") + ".\n\n"
                    "Jetzt an dein Spiel anpassen? (Die Dateien in diesem Ordner werden neu geschrieben; "
                    "die BASIS des Trainers muss ausgeschaltet sein.)"):
                self._adapt_dir(d, names, moved)

        def fail(e):
            self._busy = False
            self.lbl_done.configure(text="Prüfen hat nicht geklappt: " + (str(e) or e.__class__.__name__), fg=ERROR)
            self.log(str(e), "err")
        self.bg(job, ok, fail)

    def _adapt_dir(self, d, names, moved=None):
        """Trainer an das laufende Spiel anpassen: Item-Nummern (names) und/oder verschobene Funktionen (moved {alt: neu})."""
        moved = moved or {}
        ue, proj, client = self._ue(), self._proj(), getattr(self.win, "client", None)
        live = getattr(ue, "live", None)
        if proj is None or client is None or live is None or not (names or moved):
            self.lbl_done.configure(text="Erst Schritt ① und ITEMS FINDEN (Spiel laden, verbinden).", fg=ERROR)
            return
        sdk, base, game = proj.sdk, self.base, getattr(proj, "title", "") or getattr(proj, "name", "")
        self._busy = True
        self.lbl_done.configure(text="Passe den Trainer an dein Spiel an …", fg=WARN)

        def job():
            read = client.read_memory
            new, changed, missing = TR.refresh_fnames(TR.load_options(d), names) if names else (TR.load_options(d), [], [])
            n_moved = 0
            if moved:
                new, n_moved = TR.remap_options(new, moved)
            pe, slots, _notes = IT.hook_targets(sdk, live, read, base)
            maps = [(m[0], m[1], m[2]) for m in client.get_maps()]
            cap = TR.capacity(read, maps, base, log=self._ilog)
            if len(TR.fit_options(new, cap["code"])) != 1:
                raise TR.TrainerError("Der Trainer passt in diesem Spiel nicht mehr in eine Cave - bitte mit ITEMS neu bauen "
                                      "(teilt automatisch auf mehrere Projekte auf)")
            p = TR.plan(read, maps, base, new, None, pe, slots, log=self._ilog, client=client)
            TR.write_project(d, p, game=str(game))
            return changed, missing, n_moved

        def ok(r):
            self._busy = False
            changed, missing, n_moved = r
            msg = f"✔ Angepasst: {len(changed)} Item-Nummern ersetzt."
            if n_moved:
                msg += f" {n_moved} Zeile(n) rufen jetzt die verschobene Funktion auf."
            if missing:
                msg += f" {len(missing)} Items gibt es in deinem Spiel nicht - sie behalten die alte Nummer (wirkungslos)."
            msg += "\nIn ReaperPy den Ordner neu laden (ORDNER), BASIS aktivieren und die Einträge testen."
            self.lbl_done.configure(text=msg, fg=ACCENT)
            self.log(f"Trainer angepasst: {d}", "ok")

        def fail(e):
            self._busy = False
            msg = str(e) or e.__class__.__name__
            if "zeigt nicht auf ProcessEvent" in msg:
                msg += " → Die BASIS dieses Trainers ist noch aktiv: erst ausschalten (oder das Spiel neu starten)."
            self.lbl_done.configure(text="Anpassen hat nicht geklappt: " + msg, fg=ERROR)
            self.log(msg, "err")
        self.bg(job, ok, fail)
