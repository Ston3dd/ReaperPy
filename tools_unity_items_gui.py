"""tools_unity_items_gui.py - Tab "ITEMS" im Reiter UNITY: alle Items eines Unity-Spiels als fertiger Trainer, in drei Schritten.

Das Gegenstück zum Tab ITEMS bei Unreal (tools_items_gui.py), gleiche Bedienung:
  1) SPIEL     Spiel-Ordner (dump.cs + script.json) wählen und in ReaperPy verbinden.
  2) ITEMS     ITEMS FINDEN: das Tool sucht selbst die Item-Liste (Enum), die Methode, die Items gibt, und einen Einstieg
               (Update-Methode).  Haken setzen/entfernen, Suche, Kategorie-Filter.  Funktioniert schon ohne Konsole.
  3) TRAINER   Menge eintragen, TRAINER SPEICHERN: je Kategorie Pakete mit 14 Items ("Waffen 1", "Waffen 2" ...), bei sehr
               vielen Items mehrere Projekte.  Der Ordner wird in ReaperPy als Projekt geladen.

Keine Enum-/RVA-/Offset-Kenntnisse nötig.  Die Logik steckt in unity_items.py (ohne Oberfläche testbar).
"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cave_trainer as TR
import item_finder as F
import tools_i18n
import unity_items as U
import unity_live as UL
from tools_common import (BG, BG_CARD, ACCENT, ERROR, FONT_HEAD, FONT_LABEL, TEXT, TEXT_DIM, WARN, BaseTab, entry,
                          tree, with_scroll)
from tools_scan_gui import card, clabel, pbtn

MAX_SHOWN = 5000
ALL_CATS = "alle Kategorien"
CHK = {True: "☑", False: "☐"}
LEVEL_TEXT = {"strict": "streng", "normal": "normal", "off": "aus (alles zeigen)"}
MAX_ENUMS = 60


def _L(de, en):
    """Meldung in der gerade gewaehlten Sprache (Texte, die erst zur Laufzeit zusammengesetzt werden)."""
    return en if tools_i18n.lang() == "en" else de


class UnityItemsTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.enums, self.enum = [], None            # [(Klasse, Score)] und die gewählte Item-Liste
        self.gives, self.give_bad, self.give = [], [], None
        self.hooks, self.hook = [], None
        self.items, self.on, self.view = [], [], []
        self.out_dirs = []
        self.cap = None
        self.verified = {}                          # Geben-Methode -> 'ok' | 'bad' (Ergebnis von 1 ITEM TESTEN)
        self.found_by = "name"                      # wie die Item-Liste gefunden wurde: name | give | content | search | manual
        self.loosened = False                       # Geben-Methode nur mit gelockertem Filter gefunden
        self.n_enums = 0                            # Anzahl Enums im Dump (fuer die Meldung "nichts erkannt")
        self.cand_probes, self.cand_by = [], "content"
        self._note = None                           # einmalige Zusatzmeldung fuer _report
        self._help_shown = False
        self.level = "normal"                       # Filter der Geben-Methoden: strict | normal | off
        self.v_level = tk.StringVar(value=LEVEL_TEXT["normal"])
        self._busy = False
        self.v_q = tk.StringVar()
        self.v_cat = tk.StringVar(value=ALL_CATS)
        self.v_amount = tk.StringVar(value="999")
        self.v_enum = tk.StringVar()
        self.v_give = tk.StringVar()
        self.v_hook = tk.StringVar()

        tk.Label(self, text="▸  ITEMS  →  TRAINER", bg=BG, fg=ACCENT, font=FONT_HEAD).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(self, text="Alle Items deines Unity-Spiels als fertiger Trainer - in drei Schritten, ohne Vorkenntnisse.",
                 bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(anchor="w", padx=16, pady=(0, 8))
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
        outer.pack(fill="x", padx=12, pady=(0, 8))
        row = tk.Frame(body, bg=BG_CARD)
        row.pack(fill="x")
        self.lbl_game = tk.Label(row, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w", justify="left")
        self.lbl_game.pack(side="left", fill="x", expand=True)
        pbtn(row, "SPIEL-ORDNER WÄHLEN …", self.pick_game, primary=True).pack(side="right")
        self.lbl_conn = tk.Label(body, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w", justify="left")
        self.lbl_conn.pack(fill="x", pady=(4, 0))

    def _build_step2(self):
        outer, body, _h = card(self, "②  ITEMS FINDEN")
        outer.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        top = tk.Frame(body, bg=BG_CARD)
        top.pack(fill="x")
        self.b_find = pbtn(top, "🔎  ITEMS FINDEN", self.find_items, primary=True)
        self.b_find.pack(side="left")
        self.lbl_found = tk.Label(top, text="Klicke ITEMS FINDEN - alles Weitere passiert automatisch.", bg=BG_CARD,
                                  fg=TEXT_DIM, font=FONT_LABEL, anchor="w", justify="left", wraplength=820)
        self.lbl_found.pack(side="left", padx=12, fill="x", expand=True)

        sel = tk.Frame(body, bg=BG_CARD)
        sel.pack(fill="x", pady=(8, 0))
        clabel(sel, "Item-Liste").pack(side="left")
        self.cb_enum = ttk.Combobox(sel, textvariable=self.v_enum, values=[], width=24, state="readonly")
        self.cb_enum.pack(side="left", padx=(8, 12))
        self.cb_enum.bind("<<ComboboxSelected>>", lambda _e: self.pick_enum())
        clabel(sel, "Geben-Methode").pack(side="left")
        self.cb_give = ttk.Combobox(sel, textvariable=self.v_give, values=[], width=34, state="readonly")
        self.cb_give.pack(side="left", padx=(8, 12))
        self.cb_give.bind("<<ComboboxSelected>>", lambda _e: self.pick_give())
        clabel(sel, "Einstieg").pack(side="left")
        self.cb_hook = ttk.Combobox(sel, textvariable=self.v_hook, values=[], width=34, state="readonly")
        self.cb_hook.pack(side="left", padx=8)
        self.cb_hook.bind("<<ComboboxSelected>>", lambda _e: self.pick_hook())
        lv = tk.Frame(body, bg=BG_CARD)
        lv.pack(fill="x", pady=(4, 0))
        clabel(lv, "Filter der Geben-Methoden").pack(side="left")
        self.cb_level = ttk.Combobox(lv, textvariable=self.v_level, values=list(LEVEL_TEXT.values()), width=18,
                                     state="readonly")
        self.cb_level.pack(side="left", padx=(8, 12))
        self.cb_level.bind("<<ComboboxSelected>>", lambda _e: self.pick_level())
        clabel(lv, "streng = nur Add/Give/Grant ...   normal = auch Put/Craft/Equip ...   aus = jede Methode mit Item-Parameter "
                   "(dann mit 1 ITEM TESTEN prüfen)").pack(side="left")
        clabel(body, "(alles automatisch gewählt - nur ändern, falls die Liste falsch aussieht)").pack(anchor="w")

        self._flt = flt = tk.Frame(body, bg=BG_CARD)
        flt.pack(fill="x", pady=(8, 4))
        self.row_help = tk.Frame(body, bg=BG_CARD)               # Hilfe, wenn die Liste nicht am Namen erkannt wird
        h1 = tk.Frame(self.row_help, bg=BG_CARD)
        h1.pack(fill="x")
        clabel(h1, "Kennst du ein Item aus dem Spiel? Tippe seinen Namen:").pack(side="left")
        self.v_known = tk.StringVar(value="")
        ek = entry(h1, self.v_known, 22)
        ek.pack(side="left", padx=(8, 8))
        ek.bind("<Return>", lambda _e: self.search_known())
        pbtn(h1, "IN ALLEN LISTEN SUCHEN", self.search_known).pack(side="left")
        pbtn(h1, "ALLE LISTEN PRÜFEN", self.check_all_lists).pack(side="left", padx=(8, 0))
        self.h2 = tk.Frame(self.row_help, bg=BG_CARD)
        clabel(self.h2, "Mögliche Item-Listen").pack(side="left")
        self.v_cand = tk.StringVar(value="")
        self.cb_cand = ttk.Combobox(self.h2, textvariable=self.v_cand, values=[], width=95, state="readonly")
        self.cb_cand.pack(side="left", padx=8)
        self.cb_cand.bind("<<ComboboxSelected>>", lambda _e: self.pick_candidate())
        clabel(flt, "Suche").pack(side="left")
        q = entry(flt, self.v_q, 22)
        q.pack(side="left", padx=(8, 12))
        q.bind("<KeyRelease>", lambda _e: self.fill())
        clabel(flt, "Kategorie").pack(side="left")
        self.cb_cat = ttk.Combobox(flt, textvariable=self.v_cat, values=[ALL_CATS], width=22, state="readonly")
        self.cb_cat.pack(side="left", padx=(8, 12))
        self.cb_cat.bind("<<ComboboxSelected>>", lambda _e: self.fill())
        pbtn(flt, "ALLE AN", lambda: self.set_visible(True)).pack(side="left")
        pbtn(flt, "ALLE AUS", lambda: self.set_visible(False)).pack(side="left", padx=4)
        self.lbl_count = clabel(flt, "")
        self.lbl_count.pack(side="right")

        fr = tk.Frame(body, bg=BG_CARD)
        fr.pack(fill="both", expand=True)
        self.tv = tree(fr, [("c", "✓"), ("n", "ITEM"), ("k", "KATEGORIE"), ("i", "ID")], [40, 320, 180, 80], height=9,
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
        e.pack(side="left", padx=(8, 12))
        e.bind("<KeyRelease>", lambda _e: self.update_summary())
        self.lbl_plan = tk.Label(row, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w")
        self.lbl_plan.pack(side="left", fill="x", expand=True)
        self.b_save = pbtn(row, "💾  TRAINER SPEICHERN", self.save, primary=True)
        self.b_save.pack(side="right")
        pbtn(row, "ORDNER ÖFFNEN", self.open_folder).pack(side="right", padx=8)
        pbtn(row, "TRAINER PRÜFEN …", self.check_trainer).pack(side="right")
        live = tk.Frame(body, bg=BG_CARD)
        live.pack(fill="x", pady=(8, 0))
        clabel(live, "Sofort im laufenden Spiel (ohne Trainer):").pack(side="left")
        pbtn(live, "🧪  1 ITEM TESTEN", self.test_one).pack(side="left", padx=(8, 4))
        pbtn(live, "🧪  ANGEHAKTE TESTEN", self.test_checked).pack(side="left", padx=4)
        pbtn(live, "⚡  JETZT GEBEN", self.give_live, primary=True).pack(side="left", padx=4)
        self.lbl_done = tk.Label(body, text="", bg=BG_CARD, fg=TEXT_DIM, font=FONT_LABEL, anchor="w", justify="left",
                                 wraplength=1100)
        self.lbl_done.pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------------
    # Schritt 1: Spiel
    # ------------------------------------------------------------------
    def _unity(self):
        for t in getattr(self.win, "extra_tabs", []):
            if t.__class__.__name__ == "UnityTab":
                return t
        return None

    def _game(self):
        return getattr(self._unity(), "game", None)

    def pick_game(self):
        un = self._unity()
        if un is None:
            return self.log("Tab EXPERTE (Unity) nicht gefunden - ohne ihn kann das Spiel nicht geladen werden", "err")
        un.pick_game()
        self.after(1500, self.refresh_status)

    def refresh_status(self):
        game = self._game()
        if game is not None:
            self.lbl_game.configure(text=f"✔  Spiel geladen: {getattr(game, 'title', '') or 'Spiel'}", fg=ACCENT)
        else:
            self.lbl_game.configure(text="✗  Noch kein Spiel-Ordner gewählt (Ordner mit dump.cs und script.json).", fg=WARN)
        if getattr(self.win, "client", None) is not None:
            self.lbl_conn.configure(text="✔  Mit der PS5 verbunden.", fg=ACCENT)
        else:
            self.lbl_conn.configure(text="Nicht verbunden - zum Finden der Items nicht nötig, zum Speichern schon: im "
                                         "Hauptfenster auf VERBINDEN klicken, Spiel starten, Spielstand laden.", fg=WARN)

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

    @staticmethod
    def _give_title(g):
        return f"{g.method.cls.name}.{g.method.name}({g.method.params})" if g is not None else ""

    def _analyse(self, game, enum_cls=None, level=None):
        """Im Job-Thread: Item-Liste, Geben-Methoden und Einstiege ermitteln (nur aus dump.cs)."""
        level = level or self.level
        give_types = {g.id_param["type"] for g in U.give_candidates(game, None, level=level)[0] if g.id_param["kind"] == "enum"}
        give_types |= U.give_enum_types(game, level)               # auch Enums mit unpassendem Namen (E_Obj, Buki ...)
        enums = U.item_enums(game, give_types)
        if enum_cls is None and enums:
            enum_cls = enums[0][0]
        gives, bad = U.give_candidates(game, enum_cls, level=level)
        loosened = False
        if not gives and level != "off":                          # strenger Filter fand nichts: einmal gelockert versuchen
            gives2, bad2 = U.give_candidates(game, enum_cls, level="off")
            if gives2:
                gives, bad, loosened = gives2, bad2, True
        gives = UL.rank_gives(gives, self.verified)
        give = gives[0] if gives else None
        hooks = U.hook_candidates(game, give) if give else []
        items = U.build_items(enum_cls) if enum_cls is not None else []
        how = U.enum_how(enum_cls, give_types) if enum_cls is not None else "name"
        return {"enums": enums[:MAX_ENUMS], "enum": enum_cls, "gives": gives, "bad": bad, "give": give, "hooks": hooks,
                "items": items, "how": how, "loosened": loosened,
                "n_enums": sum(1 for c in game.classes if c.kind == "enum")}

    def find_items(self):
        if self._busy:
            return self.log("Es läuft noch ein Auftrag - kurz warten", "warn")
        game = self._game()
        if game is None:
            return self._found("Zuerst Schritt ①: Spiel-Ordner wählen.", ERROR)
        self._busy = True
        self._found("Suche läuft … (bei großen Spielen kann das einen Moment dauern)", WARN)
        self.bg(lambda: self._analyse(game), self._adopt, self._fail)

    def _fail(self, e):
        self._busy = False
        self._found("Das hat nicht geklappt: " + (str(e) or e.__class__.__name__), ERROR)
        self.log(str(e), "err")

    def _adopt(self, res, keep_list=False, how=None, note=None):
        self._busy = False
        self.found_by = how or res.get("how", "name")
        self.loosened = bool(res.get("loosened"))
        self.n_enums = res.get("n_enums", self.n_enums)
        self._note = note
        self.enums, self.enum = res["enums"], res["enum"]
        self.gives, self.give_bad, self.give = res["gives"], res["bad"], res["give"]
        self.hooks = res["hooks"]
        self.hook = self.hooks[0] if self.hooks else None
        if not keep_list:
            self.cb_enum.configure(values=[c.full for c, _s in self.enums])
        self.cb_give.configure(values=[self._give_title(g) for g in self.gives])
        self.cb_hook.configure(values=[h.title for h in self.hooks])
        self.v_enum.set(self.enum.full if self.enum else "")
        self.v_give.set(self._give_title(self.give))
        self.v_hook.set(self.hook.title if self.hook else "")
        self._set_items(res["items"])
        self._report()

    def _set_items(self, items):
        self.items = items
        self.on = [True] * len(items)
        cats = sorted({i["category"] for i in items}, key=lambda k: (k == U.IT.OTHER, k.lower()))
        self.cb_cat.configure(values=[ALL_CATS] + cats)
        self.v_cat.set(ALL_CATS)
        self.v_q.set("")
        self.fill()

    def _report(self):
        parts, lang = [], tools_i18n.lang()
        if self._note:                                                     # Meldung der Suche / Auswahl (einmalig)
            parts.append(self._note)
            self._note = None
        if self.items and self.found_by == "content":
            parts.append("⚠ " + F.msg_content_pick(self.enum.name, len(self.items), [i["name"] for i in self.items], lang))
        elif self.items:
            parts.append(f"✔ {len(self.items)} Items aus der Liste {self.enum.name}")
        else:
            parts.append("✗ " + F.msg_nothing(self.n_enums, 0, False, "enum", lang) + " " + F.msg_next_step(lang))
        if self.give and self.loosened:
            why = _L("Notlösung: der Filter fand keine passende Methode, ich habe ihn gelockert - bitte mit "
                     "1 ITEM TESTEN prüfen", "fallback: the filter found no matching method, so I loosened it - "
                     "please check it with TEST 1 ITEM")
            parts.append(f"⚠ Geben-Methode: {self._give_title(self.give)} - {why}")
        elif self.give:
            parts.append(f"✔ Geben-Methode: {self._give_title(self.give)}")
        else:
            why = self.give_bad[0][1] if self.give_bad else "keine Methode zum Geben von Items im Dump"
            parts.append(f"✗ Keine Methode gefunden, die der Trainer aufrufen kann ({why}) - "
                         "dann bleibt der Weg über ▸ WERTE oder ▸ EXPERTE")
        if self.give and self.hook:
            parts.append(f"✔ Einstieg: {self.hook.title}")
        elif self.give:
            parts.append("✗ Kein Einstieg (Update-Methode) für diese Methode gefunden - eine andere Geben-Methode wählen")
        good = bool(self.items and self.give and self.hook) and self.found_by != "content" and not self.loosened
        self._found("   |   ".join(parts), ACCENT if good else WARN)
        self._show_help(not self.items or self.found_by == "content")
        self.update_summary()

    def _reanalyse(self, enum_cls, how="manual", note=None):
        game = self._game()
        if game is None or self._busy:
            return
        self._busy = True
        self.bg(lambda: self._analyse(game, enum_cls, self.level),
                lambda r: self._adopt(r, keep_list=True, how=how, note=note), self._fail)

    # ------------------------------------------------------------------
    # Hilfe, wenn die Liste nicht am Namen erkannt wird (alles in dieser Karte, kein eigenes Fenster)
    # ------------------------------------------------------------------
    def _show_help(self, show):
        if show and not self._help_shown:
            self.row_help.pack(fill="x", pady=(4, 0), before=self._flt)
            self._help_shown = True
        elif not show and self._help_shown:
            self.row_help.pack_forget()
            self._help_shown = False

    def _set_candidates(self, probes, by="content"):
        self.cand_probes, self.cand_by = list(probes), by
        lang = tools_i18n.lang()
        self.cb_cand.configure(values=[p.label(lang) for p in self.cand_probes])
        self.v_cand.set("")
        if self.cand_probes:
            self.h2.pack(fill="x", pady=(4, 0))
        else:
            self.h2.pack_forget()

    def pick_candidate(self):
        i = self.cb_cand.current()
        if not 0 <= i < len(self.cand_probes):
            return
        game = self._game()
        cls = next((c for c in game.classes if c.kind == "enum" and c.full == self.cand_probes[i].key), None) if game else None
        if cls is not None:
            self._reanalyse(cls, how="search" if self.cand_by == "search" else "manual")

    def _need_game(self):
        game = self._game()
        if self._busy:
            self.log("Es läuft noch ein Auftrag - kurz warten", "warn")
            return None
        if game is None:
            self._found(_L("Zuerst Schritt ①: Spiel-Ordner wählen.", "First step ①: choose the game folder."), ERROR)
        return game

    def check_all_lists(self):
        """ALLE LISTEN PRÜFEN: jedes Enum des Dumps am Inhalt bewerten, die besten als Auswahl anbieten."""
        game = self._need_game()
        if game is None:
            return
        self._busy = True
        self._found(_L("Prüfe alle Listen …", "Checking all lists …"), WARN)

        def ok(probes):
            self._busy = False
            ranked = sorted((p for p in probes if p.score >= F.CONTENT_MAYBE), key=lambda p: (-p.score, -p.count, p.name.lower()))
            self._set_candidates(ranked[:12], "content")
            best = next((p for p in ranked if p.score >= F.CONTENT_OK), None)
            lang = tools_i18n.lang()
            if best is not None and not self.items:
                cls = next(c for c in game.classes if c.kind == "enum" and c.full == best.key)
                self._reanalyse(cls, how="content")
            elif ranked:
                self._found(_L(f"{len(ranked[:12])} mögliche Item-Listen gefunden - wähle unten eine aus.",
                               f"{len(ranked[:12])} possible item lists found - pick one below."), ACCENT)
            else:
                self._found("✗ " + F.msg_nothing(len(probes), len(probes), False, "enum", lang) + " " + F.msg_next_step(lang), WARN)
        self.bg(lambda: U.enum_probes(game), ok, self._fail)

    def search_known(self):
        """Der Nutzer tippt den Namen eines Items, das er im Spiel sieht: das Enum, in dem er steht, wird zur Item-Liste."""
        q = self.v_known.get().strip()
        if len(F.norm(q)) < 2:
            return self._found(_L("Tippe den Namen (oder einen Teil davon) eines Items, das du im Spiel siehst.",
                                  "Type the name (or part of it) of an item you can see in the game."), ERROR)
        game = self._need_game()
        if game is None:
            return
        self._busy = True
        self._found(_L(f"Suche „{q}“ in allen Listen …", f"Searching “{q}” in all lists …"), WARN)

        def ok(found):
            self._busy = False
            lang = tools_i18n.lang()
            if not found:
                return self._found("✗ " + F.msg_search_none(q, len(U.enum_probes(game)), len(U.enum_probes(game)), False, lang), WARN)
            self._set_candidates([f.probe for f in found[:12]], "search")
            cls = next(c for c in game.classes if c.kind == "enum" and c.full == found[0].probe.key)
            self._reanalyse(cls, how="search", note="✔ " + F.msg_search_found(q, found[0], len(found) - 1, lang))
        self.bg(lambda: U.search_enums(game, q), ok, self._fail)

    def pick_level(self):
        name = self.v_level.get()
        lv = next((k for k, v in LEVEL_TEXT.items() if v == name), "normal")
        if lv != self.level:
            self.level = lv
            self._reanalyse(self.enum)

    def pick_enum(self):
        name = self.v_enum.get()
        cls = next((c for c, _s in self.enums if c.full == name), None)
        if cls is not None and cls is not self.enum:
            self._reanalyse(cls)

    def pick_give(self):
        name = self.v_give.get()
        self.give = next((g for g in self.gives if self._give_title(g) == name), self.give)
        game = self._game()
        self.hooks = U.hook_candidates(game, self.give) if (game and self.give) else []
        self.hook = self.hooks[0] if self.hooks else None
        self.cb_hook.configure(values=[h.title for h in self.hooks])
        self.v_hook.set(self.hook.title if self.hook else "")
        self._report()

    def pick_hook(self):
        name = self.v_hook.get()
        self.hook = next((h for h in self.hooks if h.title == name), self.hook)
        self._report()

    # --- Liste ----------------------------------------------------------------------------------
    def _row(self, i):
        it = self.items[i]
        return (CHK[self.on[i]], it["name"], it["category"], it["id"])

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
            self.tv.insert("", "end", iid=str(i), values=self._row(i))
        self.update_summary()

    def _refresh_rows(self, idx):
        for i in idx:
            try:
                self.tv.item(str(i), values=self._row(i))
            except tk.TclError:
                pass                                        # Zeile gerade ausgefiltert
        self.update_summary()

    def _toggle_at(self, ev, need_check_col):
        try:
            col = self.tv.identify_column(ev.x)
            if need_check_col and (self.tv.identify_region(ev.x, ev.y) != "cell" or col != "#1"):
                return None
            if not need_check_col and col == "#1":
                return "break"
            iid = self.tv.identify_row(ev.y)
        except Exception:  # noqa: BLE001
            return None
        if iid:
            self.on[int(iid)] = not self.on[int(iid)]
            self._refresh_rows([int(iid)])
            return "break"
        return None

    def _click(self, ev):
        return self._toggle_at(ev, True)

    def _double(self, ev):
        return self._toggle_at(ev, False)

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

    def set_visible(self, flag):
        for i in self.view:
            self.on[i] = flag
        self.fill()

    def _cat_of_selected(self):
        idx = self._sel_idx()
        return self.items[idx[0]]["category"] if idx else None

    def only_category_of_selected(self):
        cat = self._cat_of_selected()
        if cat is not None:
            self.on = [it["category"] == cat for it in self.items]
            self.fill()

    def uncheck_category_of_selected(self):
        cat = self._cat_of_selected()
        if cat is not None:
            self.on = [False if it["category"] == cat else f for it, f in zip(self.items, self.on)]
            self.fill()

    # ------------------------------------------------------------------
    # Schritt 3: Trainer speichern
    # ------------------------------------------------------------------
    def _chosen(self):
        return [it for it, f in zip(self.items, self.on) if f]

    def update_summary(self):
        n_all, chosen = len(self.items), self._chosen()
        shown = f"{len(self.view)} sichtbar, " if len(self.view) != n_all else ""
        self.lbl_count.configure(text=f"{shown}{len(chosen)} von {n_all} Items angehakt")
        if not chosen:
            self.lbl_plan.configure(text="Noch keine Items angehakt.", fg=TEXT_DIM)
            return
        pkgs = U.packages(U.group_items(chosen))
        self.lbl_plan.configure(text=f"→ {len(chosen)} Items in {len(pkgs)} Einträgen", fg=TEXT)

    def _amount(self):
        try:
            v = int(self.v_amount.get().strip() or "1", 0)
        except ValueError:
            raise ValueError("Die Menge muss eine ganze Zahl sein (z. B. 999)") from None
        if not 1 <= v <= 0x7FFFFFFF:
            raise ValueError("Die Menge muss zwischen 1 und 2147483647 liegen")
        return v

    def _base_dir(self):
        import paths
        game = TR.clean_name(getattr(self._game(), "title", "") or "Unity-Spiel")
        return os.path.join(paths.sub_dir("trainer"), game)

    def _ask_preview(self, text):
        return messagebox.askyesno("Trainer speichern?", "So würde der Trainer aussehen (bisher wurde nichts geschrieben):\n\n"
                                   + text + "\n\nJetzt speichern?", parent=self.win)

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
        if self.give is None or self.hook is None:
            self.lbl_done.configure(text="Es gibt keine baubare Geben-Methode mit Einstieg - siehe Meldung bei Schritt ②.",
                                    fg=ERROR)
            return
        un, client = self._unity(), getattr(self.win, "client", None)
        if un is None or un.game is None or client is None:
            self.lbl_done.configure(text="Zum Speichern muss das Spiel laufen: Schritt ① und im Hauptfenster VERBINDEN, "
                                         "Spielstand laden.", fg=ERROR)
            return
        pkgs = U.packages(U.group_items(chosen))
        give, hook = self.give, self.hook
        game = getattr(un.game, "title", "")
        self._busy = True
        self.lbl_done.configure(text="Baue den Trainer … (nur Lesen im Spiel, es wird noch nichts verändert)", fg=WARN)

        def job():
            live = un._ensure_base(client)                       # IL2CPP-Modul-Basis (wie im Tab EXPERTE)
            base, read = live.base, client.read_memory
            maps = [(m[0], m[1], m[2]) for m in client.get_maps()]
            cap = TR.capacity(read, maps, base, log=self._ilog)
            call = U.make_call(give, hook)
            options, skipped = U.make_options(pkgs, call, amount, log=self._ilog)
            groups = U.fit_options(options, cap["code"])
            dirs = U.project_dirs(self._base_dir(), len(groups), os.path.basename(self._base_dir()) + " Items")   # Spiel-ID + Items 1 ...
            self._ilog(f"Platz für die Cave: {cap['code']} Byte -> {len(groups)} Projekt(e)")
            made = []
            for d, opts in zip(dirs, groups):                    # nur planen (lesend) - noch nichts schreiben
                p = U.plan(read, maps, base, opts, call, hook.method.rva, hook.title, log=self._ilog, client=client)
                made.append((d, len(opts), sum(len(o.rows) for o in opts), p))
            return made, skipped, maps

        def ok(res):
            made, skipped, maps = res
            lines = []
            for m in made:
                lines += ([f"{m[0]}:"] if len(made) > 1 else []) + ["  " + x for x in U.preview_lines(m[3], maps)]
            if not self._ask_preview("\n".join(lines)):
                self._busy = False
                self.lbl_done.configure(text="Abgebrochen - es wurde nichts geschrieben.", fg=WARN)
                return
            try:
                for d, _n, _r, p in made:
                    U.write_project(d, p, game=str(game))
            except Exception as e:  # noqa: BLE001
                return fail(e)
            self._busy = False
            self.out_dirs = [m[0] for m in made]
            msg = [f"✔ Fertig: {sum(m[2] for m in made)} Items in {sum(m[1] for m in made)} Einträgen, gespeichert in:"]
            msg += [f"      {m[0]}" for m in made]
            if skipped:
                msg.append(f"   ({skipped} Items ohne Zahlen-ID übersprungen)")
            msg.append("So benutzt du ihn: In ReaperPy diesen Ordner als Projekt wählen → '00 BASIS' EINMAL aktivieren → "
                       "dann Einträge anklicken (im Spiel bleiben, Inventar danach neu öffnen).")
            if len(made) > 1:
                msg.append("Wichtig: Es gibt mehrere Projekte - immer nur EINES gleichzeitig aktivieren.")
            if hook.this_mode == "member":
                msg.append("Hinweis: Die Items gehen an das erste passende Objekt, das nach dem Klick läuft - normalerweise "
                           "deine Spielfigur.")
            msg.append("Nicht an einem echten Spiel getestet: vorher speichern; Anleitung (LIESMICH_TRAINER.txt) im Ordner.")
            self.lbl_done.configure(text="\n".join(msg), fg=ACCENT)
            for w in made[0][3].warnings if made else []:
                self.log("   " + w, "info")
            self.log(f"Unity-Item-Trainer geschrieben: {', '.join(self.out_dirs)}", "ok")

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
    # Fertigen Trainer gegen das laufende Spiel prüfen
    # ------------------------------------------------------------------
    def check_trainer(self):
        start = self._base_dir()
        d = filedialog.askdirectory(parent=self.win, title="Trainer-Ordner wählen (mit _trainer_spec.json)",
                                    initialdir=start if os.path.isdir(start) else None)
        if d:
            self._check_dir(d)

    def _check_dir(self, d):
        un, client = self._unity(), getattr(self.win, "client", None)
        if un is None or un.game is None or client is None:
            self.lbl_done.configure(text="Nicht verbunden - Spiel laden und im Hauptfenster auf VERBINDEN klicken.", fg=ERROR)
            return
        if self._busy:
            return self.log("Es läuft noch ein Auftrag - kurz warten", "warn")
        self._busy = True
        self.lbl_done.configure(text="Prüfe den Trainer … (nur Lesen)", fg=WARN)

        def job():
            live = un._ensure_base(client)
            maps = [(m[0], m[1], m[2]) for m in client.get_maps()]
            return U.check_project(d, client, maps, live.base)

        def ok(r):
            self._busy = False
            if r["ok"]:
                self.lbl_done.configure(text="✔ Der Trainer passt zu diesem Spiel" + (" (BASIS ist gerade aktiv)." if r["active"]
                                                                                     else "."), fg=ACCENT)
            else:
                self.lbl_done.configure(text="✗ " + "\n✗ ".join(r["problems"]) + "\nNicht aktivieren - ITEMS FINDEN und neu "
                                             "speichern.", fg=ERROR)

        def fail(e):
            self._busy = False
            self.lbl_done.configure(text="Das hat nicht geklappt: " + (str(e) or e.__class__.__name__), fg=ERROR)
        self.bg(job, ok, fail)

    # ------------------------------------------------------------------
    # Live geben / testen
    # ------------------------------------------------------------------
    def _live_ready(self):
        """-> (client, give) oder None (Hinweis steht dann im Statusfeld)."""
        if self._busy:
            self.log("Es läuft noch ein Auftrag - kurz warten", "warn")
            return None
        client = getattr(self.win, "client", None)
        if self.give is None or self._game() is None:
            self._found("Erst Schritt ① und ITEMS FINDEN (Spiel laden).", ERROR)
            return None
        if client is None:
            self._found("Erst mit der Konsole verbinden - Live-Geben braucht das laufende Spiel.", ERROR)
            return None
        return client, self.give

    def _live_job(self, fn, ok, what):
        """fn(live, client) im Hintergrund; ok(res) im UI-Thread."""
        self._busy = True
        self._found(what, WARN)
        un, client = self._unity(), self.win.client

        def job():
            live = un._ensure_base(client)
            try:
                live.set_maps(un._maps(client))
            except Exception:  # noqa: BLE001
                pass
            return fn(live, client)

        def done(res):
            self._busy = False
            ok(res)

        def fail(e):
            self._busy = False
            self._found("✗ Geben abgebrochen: " + (str(e) or e.__class__.__name__), ERROR)
            self.log(str(e), "err")
        self.bg(job, done, fail)

    def _selected_item(self):
        idx = self._sel_idx()
        if idx:
            return self.items[idx[0]]
        chosen = self._chosen()
        return chosen[0] if chosen else None

    def test_one(self):
        r = self._live_ready()
        if r is None:
            return
        client, give = r
        it = self._selected_item()
        if it is None:
            return self._found("Erst ein Item in der Liste anklicken.", ERROR)
        try:
            amount = min(self._amount(), 5)
        except ValueError as e:
            return self._found(str(e), ERROR)
        if not messagebox.askyesno("1 Item testen", f"{it['name']} x {amount} wird über {UL.give_key(give)} im laufenden Spiel "
                                   "gegeben. Im Spiel bleiben (nicht im Hauptmenü), vorher speichern.\n\nTesten?",
                                   parent=self.win):
            return
        game = give

        def fn(live, cl):
            return UL.give_one(cl, live, game, it["id"], amount)

        def ok(_rax):
            has = messagebox.askyesno("Ergebnis", f"Ist {it['name']} jetzt im Spiel angekommen (Inventar ansehen)?",
                                      parent=self.win)
            self.mark_verified(game, has)
        self._live_job(fn, ok, f"Teste {it['name']} …")

    def mark_verified(self, give, worked):
        self.verified[UL.give_key(give)] = UL.VERIFIED_OK if worked else UL.VERIFIED_BAD
        self.gives = UL.rank_gives(self.gives, self.verified)
        self.cb_give.configure(values=[self._give_title(g) for g in self.gives])
        if worked:
            self._found(f"✔ {self._give_title(give)} funktioniert - als getestet gemerkt", ACCENT)
            return
        self._found(f"✗ {self._give_title(give)} gibt nichts - die nächste Methode ist jetzt vorn", WARN)
        nxt = next((g for g in self.gives if UL.give_key(g) != UL.give_key(give)), None)
        if nxt is not None:
            self.v_give.set(self._give_title(nxt))
            self.pick_give()

    def test_checked(self):
        r = self._live_ready()
        if r is None:
            return
        client, give = r
        chosen = self._chosen()[:UL.MAX_TEST_ALL]
        if not chosen:
            return self._found("Erst Items anhaken (Schritt ②).", ERROR)
        if not messagebox.askyesno("Angehakte testen", f"{len(chosen)} angehakte Items werden nacheinander mit Menge 1 "
                                   "gegeben, um zu sehen, ob der Aufruf bei jedem durchgeht. Vorher speichern.\n\nTesten?",
                                   parent=self.win):
            return
        self._live_job(lambda live, cl: UL.give_many(cl, live, give, chosen, 1),
                       lambda res: self._test_done(res, len(chosen)), f"Teste {len(chosen)} Items …")

    def _test_done(self, res, n):
        done, errors = res
        if errors:
            it, why = errors[0]
            return self._found(f"✗ {done} von {n} Items durchgegangen, Abbruch bei {it['name']}: {why}", ERROR)
        self._found(f"✔ {done} von {n} Items ohne Fehler aufgerufen - Inventar im Spiel ansehen", ACCENT)

    def give_live(self):
        r = self._live_ready()
        if r is None:
            return
        client, give = r
        chosen = self._chosen()
        if not chosen:
            return self._found("Erst Items anhaken (Schritt ②).", ERROR)
        try:
            amount = self._amount()
        except ValueError as e:
            return self._found(str(e), ERROR)
        hint = "" if self.verified.get(UL.give_key(give)) == UL.VERIFIED_OK else \
            "\n\nDiese Methode ist noch nicht getestet - erst '1 ITEM TESTEN'."
        if not messagebox.askyesno("Jetzt geben", f"{len(chosen)} Items x {amount} werden SOFORT über {UL.give_key(give)} "
                                   "ins laufende Spiel gegeben (ohne Trainer). Vorher speichern, im Spiel bleiben."
                                   + hint + "\n\nJetzt geben?", parent=self.win):
            return
        prog = lambda k, n: self.win.ui(lambda: self._found(f"Gebe Items … {k + 1}/{n}", WARN))  # noqa: E731
        self._live_job(lambda live, cl: UL.give_many(cl, live, give, chosen, amount, progress=prog, log=self._ilog),
                       lambda res: self._give_done(res, amount), f"Gebe {len(chosen)} Items … (nicht anfassen)")

    def _give_done(self, res, amount):
        done, errors = res
        if errors:
            it, why = errors[0]
            return self._found(f"✗ {done} Items gegeben, dann Abbruch bei {it['name']}: {why}", ERROR)
        self._found(f"✔ {done} Items x {amount} gegeben - im Spiel nachsehen", ACCENT)
