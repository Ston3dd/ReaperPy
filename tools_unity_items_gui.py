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
import unity_items as U
from tools_common import (BG, BG_CARD, ACCENT, ERROR, FONT_HEAD, FONT_LABEL, TEXT, TEXT_DIM, WARN, BaseTab, entry,
                          tree, with_scroll)
from tools_scan_gui import card, clabel, pbtn

MAX_SHOWN = 5000
ALL_CATS = "alle Kategorien"
CHK = {True: "☑", False: "☐"}
MAX_ENUMS = 60


class UnityItemsTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.enums, self.enum = [], None            # [(Klasse, Score)] und die gewählte Item-Liste
        self.gives, self.give_bad, self.give = [], [], None
        self.hooks, self.hook = [], None
        self.items, self.on, self.view = [], [], []
        self.out_dirs = []
        self.cap = None
        self._busy = False
        self.v_q = tk.StringVar()
        self.v_cat = tk.StringVar(value=ALL_CATS)
        self.v_amount = tk.StringVar(value="999")
        self.v_enum = tk.StringVar()
        self.v_give = tk.StringVar()
        self.v_hook = tk.StringVar()

        tk.Label(self, text="▸  ITEMS  →  TRAINER", bg=BG, fg=ACCENT, font=FONT_HEAD).pack(anchor="w", padx=14, pady=(10, 0))
        tk.Label(self, text="Alle Items deines Unity-Spiels als fertiger Trainer - in drei Schritten, ohne Vorkenntnisse.",
                 bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(anchor="w", padx=14, pady=(0, 6))
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

        sel = tk.Frame(body, bg=BG_CARD)
        sel.pack(fill="x", pady=(6, 0))
        clabel(sel, "Item-Liste").pack(side="left")
        self.cb_enum = ttk.Combobox(sel, textvariable=self.v_enum, values=[], width=24, state="readonly")
        self.cb_enum.pack(side="left", padx=(6, 12))
        self.cb_enum.bind("<<ComboboxSelected>>", lambda _e: self.pick_enum())
        clabel(sel, "Geben-Methode").pack(side="left")
        self.cb_give = ttk.Combobox(sel, textvariable=self.v_give, values=[], width=34, state="readonly")
        self.cb_give.pack(side="left", padx=(6, 12))
        self.cb_give.bind("<<ComboboxSelected>>", lambda _e: self.pick_give())
        clabel(sel, "Einstieg").pack(side="left")
        self.cb_hook = ttk.Combobox(sel, textvariable=self.v_hook, values=[], width=34, state="readonly")
        self.cb_hook.pack(side="left", padx=6)
        self.cb_hook.bind("<<ComboboxSelected>>", lambda _e: self.pick_hook())
        clabel(body, "(alles automatisch gewählt - nur ändern, falls die Liste falsch aussieht)").pack(anchor="w")

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
        e.pack(side="left", padx=(6, 12))
        e.bind("<KeyRelease>", lambda _e: self.update_summary())
        self.lbl_plan = tk.Label(row, text="", bg=BG_CARD, fg=TEXT, font=FONT_LABEL, anchor="w")
        self.lbl_plan.pack(side="left", fill="x", expand=True)
        self.b_save = pbtn(row, "💾  TRAINER SPEICHERN", self.save, primary=True)
        self.b_save.pack(side="right")
        pbtn(row, "ORDNER ÖFFNEN", self.open_folder).pack(side="right", padx=6)
        pbtn(row, "TRAINER PRÜFEN …", self.check_trainer).pack(side="right")
        self.lbl_done = tk.Label(body, text="", bg=BG_CARD, fg=TEXT_DIM, font=FONT_LABEL, anchor="w", justify="left",
                                 wraplength=1100)
        self.lbl_done.pack(fill="x", pady=(6, 0))

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

    def _analyse(self, game, enum_cls=None):
        """Im Job-Thread: Item-Liste, Geben-Methoden und Einstiege ermitteln (nur aus dump.cs)."""
        enums = U.item_enums(game, {g.id_param["type"] for g in U.give_candidates(game, None)[0]
                                    if g.id_param["kind"] == "enum"})
        if enum_cls is None and enums:
            enum_cls = enums[0][0]
        gives, bad = U.give_candidates(game, enum_cls)
        give = gives[0] if gives else None
        hooks = U.hook_candidates(game, give) if give else []
        items = U.build_items(enum_cls) if enum_cls is not None else []
        return {"enums": enums[:MAX_ENUMS], "enum": enum_cls, "gives": gives, "bad": bad, "give": give, "hooks": hooks,
                "items": items}

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

    def _adopt(self, res, keep_list=False):
        self._busy = False
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
        parts = []
        if self.items:
            parts.append(f"✔ {len(self.items)} Items aus der Liste {self.enum.name}")
        else:
            parts.append("✗ Keine Item-Liste erkannt - oben bei 'Item-Liste' eine auswählen (Namen mit Item zuerst), "
                         "oder im Reiter EXPERTE ▸ NAMEN von Hand suchen")
        if self.give:
            parts.append(f"✔ Geben-Methode: {self._give_title(self.give)}")
        else:
            why = self.give_bad[0][1] if self.give_bad else "keine Methode zum Geben von Items im Dump"
            parts.append(f"✗ Keine Methode gefunden, die der Trainer aufrufen kann ({why}) - "
                         "dann bleibt der Weg über ▸ WERTE oder ▸ EXPERTE")
        if self.give and self.hook:
            parts.append(f"✔ Einstieg: {self.hook.title}")
        elif self.give:
            parts.append("✗ Kein Einstieg (Update-Methode) für diese Methode gefunden - eine andere Geben-Methode wählen")
        good = bool(self.items and self.give and self.hook)
        self._found("   |   ".join(parts), ACCENT if good else WARN)
        self.update_summary()

    def _reanalyse(self, enum_cls):
        game = self._game()
        if game is None or self._busy:
            return
        self._busy = True
        self.bg(lambda: self._analyse(game, enum_cls), lambda r: self._adopt(r, keep_list=True), self._fail)

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
            dirs = U.project_dirs(self._base_dir(), len(groups))
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
