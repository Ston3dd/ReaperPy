"""tools_values_gui.py - Tab "WERTE": Leben, Ausdauer, Gold, Erfahrung, Munition ... als fertige Patches, in drei Schritten.

Gilt fuer Unreal Engine UND Unity:
  1) SPIEL    Spiel-Ordner waehlen (Unreal: wie UE-LIVE, Unity: Ordner mit dump.cs) und verbinden.
  2) WICHTIGES FINDEN   Unreal: die Werte der Spielfigur aus dem SDK (an der Figur geprueft).  Unity: Methoden wie TakeDamage,
              SpendMoney, UseStamina, UseAmmo, ExpToNextLevel.  Haken setzen, was mit soll.
  3) PATCHES SPEICHERN  Unreal: Code-Caves ('Wert kann nicht sinken', Abzieh-Befehl aus, Erfahrung festschreiben).
              Unity: Methoden leer machen bzw. festen Wert liefern.  Ergebnis: .reapproj-Dateien in einem Ordner.
Die Logik steckt in values_auto.py (ohne Oberflaeche testbar).  Items: Tab ITEMS.
"""
import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

import cave_trainer as TR
import cheatmenu as M
import cheatmenu_cave as CV
import il2cpp_dump as D
import tools_i18n as T
import ue_quick as Q
import values_auto as VA
from tools_common import (BG, BG_CARD, ACCENT, ERROR, FONT_HEAD, FONT_LABEL, TEXT, TEXT_DIM, WARN, BaseTab, entry,
                          tree, with_scroll)
from tools_scan_gui import card, clabel, pbtn

ENGINES = ("Automatisch", "Unreal Engine", "Unity")
CHK = {True: "☑", False: "☐"}
OWN_AUTHORS = ("ReaperPy Cheat-Menü", "ReaperPy Werte")


class ValuesTab(BaseTab):
    def __init__(self, parent, win, engine=None):
        """engine: None = beide Spiel-Typen (Auswahl "Automatisch"), "ue" = nur Unreal, "unity" = nur Unity.
        Mit fester Engine verschwindet alles, was zur anderen gehoert (Ordner-Zeile, Spiel-Typ-Auswahl)."""
        super().__init__(parent, win)
        self.fixed = {"ue": ENGINES[1], "unity": ENGINES[2]}.get(engine)
        self.kind = None                  # "ue" | "unity": was die Liste gerade enthaelt
        self.rows, self.on = [], []       # Zeilen: dict(cat, label, effect, warn, obj)
        self.menu = None                  # CheatMenu (Unreal)
        self.out_dir = None
        self._busy = False
        self.v_engine = tk.StringVar(value=self.fixed or ENGINES[0])
        self.v_xp = tk.StringVar(value=VA.XP_DEFAULT)

        tk.Label(self, text="▸  WERTE  →  PATCHES", bg=BG, fg=ACCENT, font=FONT_HEAD).pack(anchor="w", padx=14, pady=(10, 0))
        tk.Label(self, text="Leben, Ausdauer, Gold, Erfahrung, Munition ... als fertige Patches - für Unreal Engine und "
                            "Unity, ohne Vorkenntnisse.", bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(anchor="w", padx=14,
                                                                                                  pady=(0, 6))
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
        r1 = tk.Frame(body, bg=BG_CARD)
        if self.fixed != ENGINES[2]:
            r1.pack(fill="x")
        self.lbl_ue = tk.Label(r1, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w")
        self.lbl_ue.pack(side="left", fill="x", expand=True)
        pbtn(r1, "UNREAL-SPIEL-ORDNER WÄHLEN …", self.pick_ue).pack(side="right")
        r2 = tk.Frame(body, bg=BG_CARD)
        if self.fixed != ENGINES[1]:
            r2.pack(fill="x", pady=(4, 0))
        self.lbl_unity = tk.Label(r2, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w")
        self.lbl_unity.pack(side="left", fill="x", expand=True)
        pbtn(r2, "UNITY-ORDNER WÄHLEN …", self.pick_unity).pack(side="right")
        self.lbl_conn = tk.Label(body, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w")
        self.lbl_conn.pack(fill="x", pady=(4, 0))

    def _build_step2(self):
        outer, body, _h = card(self, "②  WICHTIGES FINDEN")
        outer.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        top = tk.Frame(body, bg=BG_CARD)
        top.pack(fill="x")
        self.b_find = pbtn(top, "🔎  WICHTIGES FINDEN", self.find, primary=True)
        self.b_find.pack(side="left")
        if not self.fixed:
            clabel(top, "Spiel-Typ").pack(side="left", padx=(14, 4))
            ttk.Combobox(top, textvariable=self.v_engine, values=list(ENGINES), width=14, state="readonly").pack(side="left")
        self.lbl_found = tk.Label(top, text="Klicke WICHTIGES FINDEN - Leben, Gold, Ausdauer, Munition, Erfahrung ...",
                                  bg=BG_CARD, fg=TEXT_DIM, font=FONT_LABEL, anchor="w", justify="left", wraplength=640)
        self.lbl_found.pack(side="left", padx=12, fill="x", expand=True)
        flt = tk.Frame(body, bg=BG_CARD)
        flt.pack(fill="x", pady=(8, 4))
        pbtn(flt, "ALLE AN", lambda: self.set_all(True)).pack(side="left")
        pbtn(flt, "ALLE AUS", lambda: self.set_all(False)).pack(side="left", padx=4)
        self.lbl_count = clabel(flt, "")
        self.lbl_count.pack(side="right")
        fr = tk.Frame(body, bg=BG_CARD)
        fr.pack(fill="both", expand=True)
        self.tv = tree(fr, [("c", "✓"), ("k", "KATEGORIE"), ("w", "WERT / METHODE"), ("e", "WIRKUNG")],
                       [40, 130, 330, 300], height=9, anchors={"c": "center"},
                       actions=[("Auswahl anhaken", lambda: self.set_selected(True)),
                                ("Auswahl abhaken", lambda: self.set_selected(False)),
                                (None, None),
                                ("Nur diese Kategorie anhaken", self.only_category_of_selected)])
        with_scroll(fr, self.tv)
        self.tv.bind("<Button-1>", self._click)
        self.tv.bind("<space>", lambda _e: self.set_selected(None))
        self.tv.bind("<Double-1>", self._double)

    def _build_step3(self):
        outer, body, _h = card(self, "③  PATCHES SPEICHERN")
        outer.pack(side="bottom", fill="x", padx=12, pady=(0, 8))
        row = tk.Frame(body, bg=BG_CARD)
        row.pack(fill="x")
        if self.fixed != ENGINES[2]:                         # nur Unreal schreibt die Erfahrung fest
            clabel(row, "Erfahrung festschreiben auf (Unreal)").pack(side="left")
            entry(row, self.v_xp, 8).pack(side="left", padx=(6, 12))
        self.lbl_plan = tk.Label(row, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w")
        self.lbl_plan.pack(side="left", fill="x", expand=True)
        self.b_save = pbtn(row, "💾  PATCHES SPEICHERN", self.save, primary=True)
        self.b_save.pack(side="right")
        pbtn(row, "ORDNER ÖFFNEN", self.open_folder).pack(side="right", padx=6)
        self.lbl_done = tk.Label(body, text="", bg=BG_CARD, fg=TEXT_DIM, font=FONT_LABEL, anchor="w", justify="left",
                                 wraplength=1100)
        self.lbl_done.pack(fill="x", pady=(6, 0))

    # ------------------------------------------------------------------
    # Schritt 1: Spiel
    # ------------------------------------------------------------------
    def _tab(self, clsname):
        for t in getattr(self.win, "extra_tabs", []):
            if t.__class__.__name__ == clsname:
                return t
        return None

    def _ue(self):
        return self._tab("UeLiveTab")

    def _unity(self):
        return self._tab("UnityTab")

    def _ue_proj(self):
        p = getattr(self._ue(), "proj", None)
        return p if p is not None and getattr(p, "sdk", None) is not None else None

    def _unity_game(self):
        return getattr(self._unity(), "game", None)

    def pick_ue(self):
        ue = self._ue()
        if ue is None:
            return self.log("Tab UE-LIVE nicht gefunden - ohne ihn kann das Spiel nicht geladen werden", "err")
        ue.pick_game()
        self.after(1500, self.refresh_status)

    def pick_unity(self):
        un = self._unity()
        if un is None:
            return self.log("Tab UNITY nicht gefunden - ohne ihn kann das Spiel nicht geladen werden", "err")
        un.pick_game()
        self.after(1500, self.refresh_status)

    def refresh_status(self):
        proj, game = self._ue_proj(), self._unity_game()
        if proj is not None:
            title = getattr(proj, "title", "") or getattr(proj, "name", "") or "Spiel"
            self.lbl_ue.configure(text=f"✔  Unreal-Spiel geladen: {title}", fg=ACCENT)
        else:
            self.lbl_ue.configure(text="–  Kein Unreal-Spiel geladen (Ordner mit offsets.json und SDK_HEADERS).", fg=TEXT_DIM)
        if game is not None:
            self.lbl_unity.configure(text=f"✔  Unity-Spiel geladen: {getattr(game, 'title', '') or 'Spiel'}", fg=ACCENT)
        else:
            self.lbl_unity.configure(text="–  Kein Unity-Spiel geladen (Ordner mit dump.cs und script.json).", fg=TEXT_DIM)
        if getattr(self.win, "client", None) is not None:
            self.lbl_conn.configure(text="✔  Mit der PS5 verbunden.", fg=ACCENT)
        else:
            self.lbl_conn.configure(text="✗  Nicht verbunden - im Hauptfenster auf VERBINDEN klicken, dann das Spiel starten "
                                         "und den Spielstand laden (nicht im Hauptmenü bleiben).", fg=WARN)

    def _tick(self):
        try:
            self.refresh_status()
            self.after(2500, self._tick)
        except tk.TclError:
            pass

    def _engine(self):
        """'ue' | 'unity' | None - nach Auswahl, sonst nach dem, was geladen ist (beides: Unreal)."""
        v = self.v_engine.get()
        if v == "Unreal Engine":
            return "ue"
        if v == "Unity":
            return "unity"
        if self._ue_proj() is not None:
            return "ue"
        return "unity" if self._unity_game() is not None else None

    # ------------------------------------------------------------------
    # Schritt 2: Finden
    # ------------------------------------------------------------------
    def _ilog(self, msg, kind="info"):
        self.win.ui(lambda: self.log(msg, kind))

    def _found(self, text, color=TEXT):
        self.lbl_found.configure(text=text, fg=color)

    def find(self):
        if self._busy:
            return self.log("Es läuft noch ein Auftrag - kurz warten", "warn")
        eng = self._engine()
        if eng is None:
            return self._found("Zuerst Schritt ①: Spiel-Ordner wählen (Unreal oder Unity).", ERROR)
        (self._find_ue if eng == "ue" else self._find_unity)()

    def _find_unity(self):
        game = self._unity_game()
        if game is None:
            return self._found("Kein Unity-Spiel geladen - Schritt ①: UNITY-ORDNER WÄHLEN.", ERROR)
        self._busy = True
        self._found("Suche die wichtigen Methoden …", WARN)

        def job():
            return VA.find_unity_candidates(game)

        def ok(cands):
            self._busy = False
            self.kind, self.menu = "unity", None
            self.rows = [dict(cat=c.cat, label=c.label, effect=c.effect + (f"  ⚠ {c.warn}" if c.warn else ""),
                              warn=c.warn, obj=c) for c in cands]
            self.on = [c.default_on for c in cands]
            self.fill()
            n = len(cands)
            self._found(f"✔ {n} Methoden erkannt (Namenserkennung). Haken setzen, was mit soll - angehakt sind die "
                        "wahrscheinlichsten für den Spieler." if n else
                        "✗ Keine passenden Methoden gefunden (das Spiel nutzt andere Namen). Im Tab UNITY lässt sich von Hand "
                        "suchen.", ACCENT if n else WARN)

        def fail(e):
            self._busy = False
            self._found("Das hat nicht geklappt: " + (str(e) or e.__class__.__name__), ERROR)
        self.bg(job, ok, fail)

    def _find_ue(self):
        ue, proj = self._ue(), self._ue_proj()
        client = getattr(self.win, "client", None)
        if proj is None:
            return self._found("Kein Unreal-Spiel geladen - Schritt ①: UNREAL-SPIEL-ORDNER WÄHLEN.", ERROR)
        if client is None:
            return self._found("Nicht verbunden - im Hauptfenster auf VERBINDEN klicken und den Spielstand laden.", ERROR)
        self._busy = True
        self._found("Suche die Werte der Spielfigur … (beim ersten Mal kann das eine Minute dauern)", WARN)

        def job():
            live = Q.connect_live(client, proj, log=self._ilog, cached=getattr(ue, "live", None))
            if live.index is None:
                live.build_index()
            if self.menu is not None:
                self.menu.release_all(restore=False)
            menu = M.CheatMenu(live, proj.sdk, client, log=lambda m, k="info": self._ilog(m, k))
            menu.build()
            menu.check_live()
            return live, menu

        def ok(res):
            self._busy = False
            live, menu = res
            if ue is not None:
                ue.live = live
            self.kind, self.menu = "ue", menu
            ents = VA.ue_entries(menu)
            self.rows = [dict(cat=e.cat, label=e.label, effect=self._ue_effect(e), warn="", obj=e) for e in ents]
            self.on = [e.cat != "Schalter" for e in ents]
            self.fill()
            n = len(ents)
            self._found(f"✔ {n} Werte an der Spielfigur gefunden. Haken setzen, was mit soll." if n else
                        "✗ Keine Werte an der Spielfigur gefunden - Spielstand geladen (nicht im Hauptmenü)?",
                        ACCENT if n else WARN)

        def fail(e):
            self._busy = False
            self._found("Das hat nicht geklappt: " + (str(e) or e.__class__.__name__), ERROR)
            self.log(str(e), "err")
        self.bg(job, ok, fail)

    @staticmethod
    def _ue_effect(e):
        if e.cat == VA.XP_CATEGORY:
            return "wird auf den eingestellten Wert festgeschrieben (Level-Up)"
        if e.kind == "toggle":
            return "Schalter wird festgeschrieben"
        return "Wert sinkt nicht mehr (oder Abziehen wird abgeschaltet)"

    # --- Liste ----------------------------------------------------------------------------------
    def fill(self):
        self.tv.delete(*self.tv.get_children())
        order = VA.group_by_category(range(len(self.rows)), lambda i: self.rows[i]["cat"])
        self.view = [i for lst in order.values() for i in lst]
        for i in self.view:
            self.tv.insert("", "end", iid=str(i), values=self._cells(i))
        self.update_summary()

    def _cells(self, i):
        r = self.rows[i]
        return (CHK[self.on[i]], T.translate(r["cat"]), r["label"], T.translate(r["effect"]))

    def _refresh_rows(self, idx):
        for i in idx:
            try:
                self.tv.item(str(i), values=self._cells(i))
            except tk.TclError:
                pass
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
        if flag is None:
            flag = not self.on[idx[0]]
        for i in idx:
            self.on[i] = flag
        self._refresh_rows(idx)

    def set_all(self, flag):
        self.on = [flag] * len(self.rows)
        self.fill()

    def only_category_of_selected(self):
        idx = self._sel_idx()
        if not idx:
            return
        cat = self.rows[idx[0]]["cat"]
        self.on = [r["cat"] == cat for r in self.rows]
        self.fill()

    def _chosen(self):
        return [r for r, f in zip(self.rows, self.on) if f]

    def update_summary(self):
        chosen = self._chosen()
        self.lbl_count.configure(text=f"{len(chosen)} von {len(self.rows)} angehakt")
        cats = sorted({r["cat"] for r in chosen}, key=lambda c: VA.CATEGORY_ORDER.index(c) if c in VA.CATEGORY_ORDER else 99)
        self.lbl_plan.configure(text=("→ " + ", ".join(cats)) if chosen else "Noch nichts angehakt.",
                                fg=TEXT if chosen else TEXT_DIM)

    # ------------------------------------------------------------------
    # Schritt 3: Speichern
    # ------------------------------------------------------------------
    def _base_dir(self, kind):
        import paths
        if kind == "unity":
            title = getattr(self._unity_game(), "title", "") or "Spiel"
        else:
            proj = self._ue_proj()
            title = getattr(proj, "title", "") or getattr(proj, "name", "") or "Spiel"
        return os.path.join(paths.sub_dir("trainer"), TR.clean_name(title), "Unity-Werte" if kind == "unity" else "Werte")

    @staticmethod
    def _clean_old(folder):
        """Frueher von diesem Tab erzeugte Patch-Dateien entfernen (sonst sammeln sich Kopien); fremde Dateien bleiben."""
        if not os.path.isdir(folder):
            return
        for fn in os.listdir(folder):
            if not fn.endswith(".reapproj"):
                continue
            try:
                with open(os.path.join(folder, fn), encoding="utf-8") as f:
                    author = json.load(f).get("author", "")
            except (OSError, ValueError):
                continue
            if author in OWN_AUTHORS:
                os.remove(os.path.join(folder, fn))

    def save(self):
        if self._busy:
            return self.log("Es läuft noch ein Auftrag - kurz warten", "warn")
        chosen = self._chosen()
        if not chosen or self.kind is None:
            self.lbl_done.configure(text="Erst WICHTIGES FINDEN und etwas anhaken (Schritt ②).", fg=ERROR)
            return
        client = getattr(self.win, "client", None)
        if client is None:
            self.lbl_done.configure(text="Nicht verbunden - im Hauptfenster auf VERBINDEN klicken.", fg=ERROR)
            return
        (self._save_unity if self.kind == "unity" else self._save_ue)(chosen, client)

    def _save_unity(self, chosen, client):
        un = self._unity()
        out = self._base_dir("unity")
        self._busy = True
        self.lbl_done.configure(text="Baue die Patches … (nur Lesen im Spiel, es wird nichts verändert)", fg=WARN)

        def job():
            live = un._ensure_base(client)                       # IL2CPP-Modul-Basis (wie im Tab UNITY)
            self._clean_old(out)
            made, failed = [], []
            for r in chosen:
                c = r["obj"]
                try:
                    doc = VA.unity_patch_doc(c, live.base, client.read_memory)
                    made.append((c, D.write_reapproj(out, doc)))
                except (ValueError, TypeError, OSError) as e:
                    failed.append((c.label, str(e)))
            return live.base, made, failed

        def ok(res):
            self._busy = False
            base, made, failed = res
            self.out_dir = out
            lines = [f"✔ Fertig: {len(made)} Patch-Dateien in:", f"      {out}"] if made else \
                ["✗ Es konnte kein Patch gebaut werden."]
            lines += [f"✗ {lab}: {why}" for lab, why in failed[:6]]
            if made:
                lines.append(f"So benutzt du sie: In ReaperPy diesen Ordner als Projekt wählen und die Image-Basis auf die "
                             f"IL2CPP-Modul-Basis {base:#x} stellen, dann die Patches aktivieren.")
                lines.append("Die Patches prüfen vor dem Schreiben die Original-Bytes: bei einer anderen Spielversion werden "
                             "sie verweigert statt etwas zu überschreiben. Methoden gelten für alle Objekte dieser Klasse.")
            self.lbl_done.configure(text="\n".join(lines), fg=ACCENT if made else ERROR)
            self.log(f"Unity-Werte: {len(made)} gebaut, {len(failed)} fehlgeschlagen", "ok" if made else "err")

        def fail(e):
            self._busy = False
            msg = str(e) or e.__class__.__name__
            self.lbl_done.configure(text="Das hat nicht geklappt: " + msg, fg=ERROR)
            self.log(msg, "err")
        self.bg(job, ok, fail)

    def _save_ue(self, chosen, client):
        _ue, proj, menu = self._ue(), self._ue_proj(), self.menu
        if menu is None or proj is None:
            self.lbl_done.configure(text="Erst WICHTIGES FINDEN (Spiel laden, verbinden).", fg=ERROR)
            return
        xp = self.v_xp.get().strip() or VA.XP_DEFAULT
        try:
            float(xp)
        except ValueError:
            self.lbl_done.configure(text="Der Erfahrungs-Wert muss eine Zahl sein (z. B. 99999).", fg=ERROR)
            return
        entries = [r["obj"] for r in chosen]
        out, base = self._base_dir("ue"), self.base
        self._busy = True
        self.lbl_done.configure(text="Suche im Spiel-Code und baue die Patches … (einige Minuten möglich, nur Lesen)", fg=WARN)

        def job():
            import ue_instr as U
            dis = getattr(proj, "dis", None) or U.get_disasm()
            if getattr(proj, "dm", None) is not None:
                code = CV.code_from_project(proj)
            else:
                code = CV.code_from_console(client, base)
            self._clean_old(out)
            return VA.build_ue_patches(menu, entries, code, dis, out, xp_value=xp, log=lambda m: self._ilog(m, "warn"))

        def ok(res):
            self._busy = False
            done, failed = res
            self.out_dir = out
            lines = [f"✔ Fertig: {len(done)} Patches in:", f"      {out}"] if done else ["✗ Es konnte kein Patch gebaut werden."]
            lines += [f"      {d['entry'].cat}: {d['entry'].label} → {CV.mode_text(d['mode'])}" for d in done[:8]]
            lines += [f"✗ {e.label}: {why}" for e, why in failed[:6]]
            if done:
                lines.append("So benutzt du sie: In ReaperPy diesen Ordner als Projekt wählen und die Patches aktivieren. Sie "
                             "suchen ihre Stelle per Signatur im Code. Achtung: sie gelten für ALLE Objekte, die diesen Code "
                             "benutzen (auch Gegner).")
            self.lbl_done.configure(text="\n".join(lines), fg=ACCENT if done else ERROR)
            self.log(f"Werte: {len(done)} gebaut, {len(failed)} fehlgeschlagen", "ok" if done else "err")

        def fail(e):
            self._busy = False
            msg = str(e) or e.__class__.__name__
            self.lbl_done.configure(text="Das hat nicht geklappt: " + msg, fg=ERROR)
            self.log(msg, "err")
        self.bg(job, ok, fail)

    def open_folder(self):
        d = self.out_dir or self._base_dir(self.kind or ("ue" if self._ue_proj() is not None else "unity"))
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
