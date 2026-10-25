"""tools_uelive_gui.py - Tab "UE-LIVE": der einfache Weg.

  1) SPIEL-ORDNER waehlen (wird gemerkt, beim naechsten Start automatisch geladen)
  2) links einen Wert anklicken (z.B. UHealthComponent.Health) - es wird NICHTS ausgeblendet,
     jeder Zahlen-/Bool-Member jeder Klasse steht in der Liste; das Suchfeld sucht nur Text
  3) rechts erscheinen alle Live-Instanzen mit dem aktuellen Wert (aktualisiert sich selbst)
  4) Doppelklick auf eine Zeile oder Wert eintippen -> SETZEN; EINFRIEREN haelt ihn fest

Logik in ue_quick.py (testbar ohne Konsole), Objekt-Leser in ue_live.py, Spiel-Laden in ue_project.py.
"""

import json
import os
import tkinter as tk
from tkinter import filedialog, simpledialog, ttk

import ue_quick as Q
from tools_common import ACCENT, BG, FONT_LABEL, TEXT_DIM, WARN, BaseTab, button, entry, label, tree, with_scroll

CFG = os.path.join(os.path.expanduser("~"), ".reaperpy_uelive.json")
TICK_MS = 400
MAX_LIST_ROWS = 5000  # Anzeige-Grenze der linken Liste (Suche findet trotzdem alles)
MAX_LIVE_ROWS = 120  # so viele sichtbare Zeilen werden je Tick neu gelesen
SNOW = "❄"


def _load_cfg():
    try:
        with open(CFG, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def _save_cfg(d):
    try:
        with open(CFG, "w", encoding="utf-8") as handle:
            json.dump(d, handle)
    except Exception:
        pass


class UeLiveTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.proj = self.live = None
        self.targets, self.shown, self.cands = [], [], []  # alle Ziele / aktuell gelistete / Kandidaten
        self.cur = None  # gewaehltes Target
        self.promo = {}  # key -> ue_promising.Promising (Modus "beste Werte")
        self.rows = []  # Instanzen des gewaehlten Ziels
        self.freezer = Q.Freezer()
        self._busy = False
        self._pending = None
        self._cfg = _load_cfg()

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=8, pady=(8, 2))
        button(top, "SPIEL-ORDNER…", self.pick_game, accent=True).pack(side="left", padx=2)
        self.v_game = tk.StringVar(value=self._cfg.get("game", ""))
        entry(top, self.v_game, 60).pack(side="left", padx=4, fill="x", expand=True)
        button(top, "↻ NEU LADEN", self.load).pack(side="left", padx=2)
        button(top, "★ BESTE WERTE", self.best_values, accent=True).pack(side="left", padx=2)
        button(top, "ALLE WERTE", self._rebuild_targets).pack(side="left", padx=2)
        self.lbl = label(
            self, "① Spiel-Ordner wählen   ② links einen Namen suchen (z. B. Health, Money, Ammo) und anklicken   "
            "③ rechts Zeile wählen → neuen Wert eintippen → SETZEN"
        )
        self.lbl.pack(anchor="w", padx=10, pady=(0, 2))

        pan = ttk.PanedWindow(self, orient="horizontal")
        pan.pack(fill="both", expand=True, padx=8, pady=4)

        left = tk.Frame(pan, bg=BG)
        pan.add(left, weight=2)
        frame = tk.Frame(left, bg=BG)
        frame.pack(fill="x")
        label(frame, "NAME SUCHEN").pack(side="left")
        self.v_q = tk.StringVar()
        search_entry = entry(frame, self.v_q, 24)
        search_entry.pack(side="left", padx=4)
        search_entry.bind("<KeyRelease>", lambda _e: self._fill_targets())
        self.tl = tree(
            left,
            [("k", "KLASSE.MEMBER"), ("t", "TYP / INSTANZEN / WERT")],
            [330, 190],
            height=18,
            details=self._target_details,
        )
        with_scroll(left, self.tl)
        self.lbl_list = label(left, "")
        self.lbl_list.pack(anchor="w")
        self.tl.bind("<<TreeviewSelect>>", lambda _e: self._on_pick())

        right = tk.Frame(pan, bg=BG)
        pan.add(right, weight=3)
        self.lbl_cur = label(right, "← links einen Wert anklicken", dim=False)
        self.lbl_cur.pack(anchor="w")
        fr2 = tk.Frame(right, bg=BG)
        fr2.pack(fill="x", pady=2)
        self.v_live = tk.BooleanVar(value=True)
        tk.Checkbutton(
            fr2,
            text="live aktualisieren",
            variable=self.v_live,
            bg=BG,
            fg=TEXT_DIM,
            selectcolor=BG,
            activebackground=BG,
            font=FONT_LABEL,
        ).pack(side="left", padx=4)
        button(fr2, "↻ INSTANZEN NEU", lambda: self.refind(force=True)).pack(side="right", padx=2)

        row_actions = [
            ("Wert ändern…", self.edit_dialog),
            (f"{SNOW} Einfrieren", self.freeze_sel),
            ("Auftauen", self.unfreeze_sel),
            ("Alle auftauen", self.unfreeze_all),
            (None, None),
            ("Im Speicher zeigen", self.to_memory),
            ("Schreiber finden", self.to_watch),
        ]
        self.tr = tree(
            right,
            [("f", SNOW), ("v", "LIVE-WERT"), ("n", "INSTANZ"), ("a", "ADRESSE")],
            [28, 130, 260, 130],
            height=14,
            actions=row_actions,
            details=self._row_details,
        )
        with_scroll(right, self.tr)
        self.tr.bind("<Double-1>", lambda _e: self.edit_dialog())
        self.tr.bind("<<TreeviewSelect>>", lambda _e: self._on_row())

        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill="x", padx=8, pady=(0, 2))
        edit_row = tk.Frame(bottom, bg=BG)
        edit_row.pack(fill="x", pady=2)
        label(edit_row, "NEUER WERT").pack(side="left")
        self.v_val = tk.StringVar()
        value_entry = entry(edit_row, self.v_val, 14)
        value_entry.pack(side="left", padx=4)
        value_entry.bind("<Return>", lambda _e: self.set_value())
        button(edit_row, "SETZEN", self.set_value, accent=True).pack(side="left", padx=2)
        self.v_scope = tk.StringVar(value="Auswahl")
        ttk.Combobox(
            edit_row, textvariable=self.v_scope, values=("Auswahl", "alle Instanzen"), width=14, state="readonly"
        ).pack(side="left", padx=6)
        self.quick = tk.Frame(edit_row, bg=BG)
        self.quick.pack(side="left", padx=6)
        self.btn_max = button(edit_row, "= MAX", self.set_to_max)
        self.btn_max.pack(side="left", padx=2)
        freeze_row = tk.Frame(bottom, bg=BG)
        freeze_row.pack(fill="x", pady=2)
        button(freeze_row, f"{SNOW} EINFRIEREN", self.freeze_sel, accent=True).pack(side="left", padx=2)
        button(freeze_row, "AUFTAUEN", self.unfreeze_sel).pack(side="left", padx=2)
        self.lbl_fz = label(freeze_row, "")
        self.lbl_fz.pack(side="left", padx=8)
        label(
            self,
            "Doppelklick ändert den Wert, Rechtsklick öffnet weitere Aktionen. '+100' und '*2' rechnen "
            "vom aktuellen Wert aus.",
            dim=True,
        ).pack(anchor="w", padx=10, pady=(0, 4))

        self._build_quick(None)
        self.after(300, self._autoload)
        self.after(TICK_MS, self._tick)

    def _autoload(self):
        g = self.v_game.get().strip()
        if g and os.path.isdir(g) and self.proj is None:
            self.load()

    def pick_game(self):
        d = filedialog.askdirectory(parent=self.win, title="Spielordner (mit offsets.json, SDK_HEADERS ...)")
        if d:
            self.v_game.set(d)
            self.load()

    def load(self):
        folder = self.v_game.get().strip()
        if not folder or not os.path.isdir(folder):
            return self.log("UE-LIVE: erst SPIEL-ORDNER wählen", "warn")

        def job():
            import dumpmem
            import ue_project

            files = dumpmem.find_game_files(folder)
            files["dump_bin"] = files["dump_json"] = None  # fuer UE-LIVE nicht noetig -> schneller
            if not (files.get("sdk") or files.get("offsets")):
                raise FileNotFoundError("weder SDK_HEADERS noch offsets.json im Ordner gefunden")
            proj = ue_project.GameProject(
                files=files, native="rva", log=lambda m: self.win.ui(lambda: self.log(m, "warn"))
            ).load()
            return proj

        def ok(r):
            self.proj = r
            self.live = None
            self.freezer.clear()
            self._cfg["game"] = folder
            _save_cfg(self._cfg)
            self._rebuild_targets()
            stats = self.proj.sdk.stats
            self.lbl.configure(
                text=f"{self.proj.title or os.path.basename(folder)}: {stats['classes']} Klassen, "
                f"{len(self.targets)} Werte  -  jetzt links einen Wert anklicken",
                fg=ACCENT,
            )

        self.bg(job, ok)

    def _rebuild_targets(self):
        if not self.proj:
            return
        self.promo = {}
        # ALLE Zahlen-/Bool-Member aller Klassen - nichts wird vorab aussortiert
        self.targets = sorted(Q.targets_from_all_members(self.proj.sdk), key=lambda t: (t.cls.lower(), t.offset))
        self._fill_targets()

    def _fill_targets(self):
        self.tl.delete(*self.tl.get_children())
        q = self.v_q.get().strip().lower()
        self.shown = [target for target in self.targets if not q or q in target.key.lower()]
        for i, t in enumerate(self.shown[:MAX_LIST_ROWS]):
            info = self.promo.get(t.key)
            shown_type = t.type if info is None else f"{t.type}  ×{info.count}  {info.sample}".rstrip()
            self.tl.insert("", "end", iid=str(i), values=(t.key, shown_type))
        if len(self.shown) > MAX_LIST_ROWS:
            self.lbl_list.configure(
                text=f"{len(self.shown)} Treffer - nur die ersten {MAX_LIST_ROWS} sichtbar, Suchwort eingeben", fg=WARN
            )
        else:
            self.lbl_list.configure(text=f"{len(self.shown)} Werte", fg=TEXT_DIM)

    def best_values(self):
        """Nur die vielversprechendsten Werte: Klassen mit echten Instanzen im Spiel + Standard-Engine-Werte,
        mit live gelesenen Offsets und Wert-Stichprobe (ue_promising)."""
        if not self.proj:
            return self.log("UE-LIVE: erst Spiel-Ordner laden", "warn")
        client = self.win.client
        if client is None:
            return self.log("UE-LIVE: nicht verbunden (Haupt-Fenster: VERBINDEN)", "err")
        self.lbl.configure(text="Suche die vielversprechendsten Werte im laufenden Spiel …", fg=WARN)

        def job():
            import ue_promising

            log = lambda m: self.win.ui(lambda: self.log(m, "info"))  # noqa: E731
            live = Q.connect_live(client, self.proj, log=log, cached=self.live)
            if self.live is live:
                live.drop_cache()  # Level kann gewechselt haben
            if live.index is None:
                live.build_index()
            return live, ue_promising.find_promising(live, self.proj.sdk, read=client.read_memory)

        def ok(res):
            live, found = res
            self.live = live
            self.promo = {p.key: p for p in found}
            self.targets = [p.target for p in found]
            self._fill_targets()
            self.lbl.configure(
                text=f"{len(found)} vielversprechende Werte (alle mit Instanzen im Spiel)  -  Zahl hinter dem Typ = Anzahl "
                "Objekte, danach der gelesene Wert",
                fg=ACCENT,
            )

        self.bg(job, ok, lambda e: (self.log(f"UE-LIVE: {e}", "err"), self.lbl.configure(text=f"Fehler: {e}", fg="#ff3366")))

    def _on_pick(self):
        sel = self.tl.selection()
        if not sel:
            return
        self.cur = self.shown[int(sel[0])]
        self.rows = []
        self._render()
        self.lbl_cur.configure(text=f"{self.cur.key}  [{self.cur.type}]  - suche Instanzen im Spiel …", fg=WARN)
        self._build_quick(self.cur)
        self._cancel_pending()
        self._pending = self.after(250, self.refind)  # kurz warten, falls man durch die Liste scrollt

    def _cancel_pending(self):
        if self._pending is not None:
            try:
                self.after_cancel(self._pending)
            except Exception:
                pass
            self._pending = None

    def _build_quick(self, target):
        for child in self.quick.winfo_children():
            child.destroy()
        if target is None:
            self.btn_max.pack_forget()
            return
        if target.is_bool:
            button(self.quick, "AN", lambda: self._quick("an"), accent=True).pack(side="left", padx=1)
            button(self.quick, "AUS", lambda: self._quick("aus")).pack(side="left", padx=1)
        else:
            for txt, val in (
                ("×2", "*2"),
                ("×10", "*10"),
                ("+10", "+10"),
                ("+100", "+100"),
                ("+1000", "+1000"),
                ("0", "0"),
                ("99999", "99999"),
            ):
                button(self.quick, txt, lambda v=val: self._quick(v)).pack(side="left", padx=1)
        if self._companions(target):
            self.btn_max.pack(side="left", padx=2)
        else:
            self.btn_max.pack_forget()

    def _target_details(self, row):
        target = self.shown[int(row)]
        return [
            ("Klasse", target.cls),
            ("Member", target.member),
            ("Typ", target.type),
            ("Offset", f"{target.offset:#x}"),
            ("Bit", target.bit if target.bit >= 0 else "-"),
        ]

    def _row_details(self, row):
        hit = self.rows[int(row)]
        target = self.cur
        return [
            ("Wert", f"{target.key} ({target.type})"),
            ("Objekt-Adresse", f"{hit['addr']:#x}"),
            ("Wert-Adresse", f"{hit['vaddr']:#x}"),
            ("Klasse der Instanz", hit["class"]),
            ("Eingefroren", "ja" if hit["vaddr"] in self.freezer else "nein"),
        ]

    def _quick(self, val):
        self.v_val.set(val)
        self.set_value()

    def refind(self, force=False):
        """Instanzen des gewählten Werts im Spiel suchen.  Der Objekt-Index wird nur einmal gebaut; force=True
        (Button INSTANZEN NEU, z.B. nach Levelwechsel) liest ihn neu."""
        self._pending = None
        cur = self.cur
        client = self.win.client
        if cur is None or not self.proj:
            return self.log("UE-LIVE: erst Spiel laden und einen Wert anklicken", "warn")
        if client is None:
            return self.log("UE-LIVE: nicht verbunden (Haupt-Fenster: VERBINDEN)", "err")

        def job():
            live = Q.connect_live(
                client, self.proj, log=lambda m: self.win.ui(lambda: self.log(m, "info")), cached=self.live
            )
            if self.live is not live:
                self.live = live
                self.win.ui(lambda: self.log(f"UE-LIVE: {live.num_elements} Objekte im Spiel erkannt", "ok"))
            elif force:
                live.drop_cache()  # frisch lesen (Level kann gewechselt haben)
            if live.index is None:
                self.win.ui(
                    lambda: self.log(
                        "UE-LIVE: Objekt-Index wird gebaut (einmalig, kann je nach Spiel einige Sekunden dauern) …",
                        "info",
                    )
                )
            rows = Q.find_instances(live, cur)
            if not rows:
                why = Q.explain_no_instances(live, cur)
                self.win.ui(lambda: self.log(f"UE-LIVE: {why}", "warn"))
            for row in rows:
                try:
                    row["val"], row["txt"] = Q.read_value(client.read_memory, row["vaddr"], cur)
                except Exception:
                    row["val"], row["txt"] = None, "?"
            rows.sort(
                key=lambda r: (
                    "player" not in (r.get("owner", "") + r["name"]).lower(),  # Spieler zuerst
                    r["val"] is None,
                    Q.is_zero(r["val"]) if r["val"] is not None else True,
                    r.get("owner", "") + r["name"],
                )
            )
            return rows

        def ok(rows):
            if cur is not self.cur:
                return
            self.rows = rows
            self._render()
            nz = sum(1 for row in rows if row["val"] is not None and not Q.is_zero(row["val"]))
            self.lbl_cur.configure(
                text=f"{cur.key}  [{cur.type}]  -  {len(rows)} Instanz(en), {nz} mit Wert ≠ 0",
                fg=ACCENT if rows else WARN,
            )

        self.bg(
            job,
            ok,
            lambda e: (
                self.lbl_cur.configure(text=f"{cur.key}  -  Fehler", fg="#ff3366"),
                self.log(f"UE-LIVE: {e}", "err"),
            ),
        )

    def _visible(self):
        return list(range(len(self.rows)))  # keine Filter: jede gefundene Instanz wird gezeigt

    def _render(self):
        keep = {self.rows[int(i)]["vaddr"] for i in self.tr.selection() if int(i) < len(self.rows)}
        self.tr.delete(*self.tr.get_children())
        new_sel = []
        for i in self._visible():
            r = self.rows[i]
            self.tr.insert("", "end", iid=str(i), values=self._values(r))
            if r["vaddr"] in keep:
                new_sel.append(str(i))
        if new_sel:
            self.tr.selection_set(new_sel)
        self._update_fz_label()

    def _values(self, row):
        return (SNOW if row["vaddr"] in self.freezer else "", row.get("txt", ""), (row.get("owner") + " › " if row.get("owner") else "") + row["name"], f"{row['vaddr']:#x}")

    def _update_fz_label(self):
        n = len(self.freezer)
        self.lbl_fz.configure(text=(f"{SNOW} {n} Wert(e) eingefroren" if n else ""), fg=ACCENT)

    def _sel_rows(self):
        if self.v_scope.get() == "alle Instanzen":
            return [self.rows[i] for i in self._visible()]
        return [self.rows[int(i)] for i in self.tr.selection() if int(i) < len(self.rows)]

    def _on_row(self):
        pass

    # Live-Tick: Freeze schreiben + sichtbare Werte neu lesen
    def _tick(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        self.after(TICK_MS, self._tick)
        client = self.win.client
        if self._busy or client is None or self.cur is None or not self.rows:
            return
        freezing = len(self.freezer) > 0
        if not freezing and not self.v_live.get():
            return
        cur = self.cur
        rows = [self.rows[i] for i in self._visible()][:MAX_LIVE_ROWS] if self.v_live.get() else []
        self._busy = True

        def job():
            if freezing:
                self.freezer.tick(client)
            out = []
            for row in rows:
                try:
                    out.append(Q.read_value(client.read_memory, row["vaddr"], cur))
                except Exception:
                    out.append((None, "?"))
            return out

        def done(vals):
            self._busy = False
            if cur is not self.cur:
                return
            for r, (v, txt) in zip(rows, vals):
                r["val"], r["txt"] = v, txt
            self._refresh_texts(rows)

        def err(e):
            self._busy = False
            self.log(f"UE-LIVE Live/Freeze: {e}", "err")

        self.win.bg(job, done, err)

    def _refresh_texts(self, rows):
        shown = set(self.tr.get_children())
        pos = {id(row): str(i) for i, row in enumerate(self.rows)}
        for row in rows:
            iid = pos.get(id(row))
            if iid in shown:
                self.tr.item(iid, values=self._values(row))

    def _targets_or_warn(self):
        if self.cur is None or not self.rows:
            self.log("UE-LIVE: erst links einen Wert anklicken", "warn")
            return None
        rows = self._sel_rows()
        if not rows:
            self.log("UE-LIVE: rechts eine Zeile wählen (oder Ziel 'alle Instanzen')", "warn")
            return None
        if self.win.client is None:
            self.log("UE-LIVE: nicht verbunden", "err")
            return None
        return rows

    def set_value(self, text=None, rows=None):
        rows = rows or self._targets_or_warn()
        if not rows:
            return
        cur, client = self.cur, self.win.client
        text = self.v_val.get() if text is None else text
        try:
            jobs = [(row, Q.parse_input(cur, text, row["val"])) for row in rows]
        except ValueError as error:
            return self.log(f"UE-LIVE: {error}", "err")

        def job():
            done = 0
            for row, value in jobs:
                Q.write_value(client.read_memory, client.write_memory, row["vaddr"], cur, value)
                if row["vaddr"] in self.freezer:  # eingefroren -> neuer Wert wird gehalten
                    self.freezer.add(row["vaddr"], cur, value)
                row["val"], row["txt"] = Q.read_value(client.read_memory, row["vaddr"], cur)
                done += 1
            return done

        self.bg(
            job,
            lambda n: (
                self._refresh_texts([r for r, _v in jobs]),
                self.log(f"UE-LIVE: {cur.member} = {jobs[0][0]['txt']}  ({n} Instanz(en))", "ok"),
            ),
        )

    def edit_dialog(self):
        sel = [self.rows[int(i)] for i in self.tr.selection() if int(i) < len(self.rows)]
        if not sel or self.cur is None:
            return
        row = sel[0]
        txt = simpledialog.askstring(
            "Wert ändern",
            f"{self.cur.key}\n{row['name']}\naktuell: {row.get('txt', '?')}\n\n"
            "Neuer Wert  ('+100', '*2', 'an'/'aus' sind erlaubt):",
            parent=self.win,
        )
        if txt is not None and txt.strip():
            self.set_value(txt, [row])

    def _companions(self, target):
        if not self.proj or target is None or target.is_bool:
            return []
        import uecheat

        try:
            return [
                Q.Target(target.cls, m.name, m.type, m.offset, m.bit)
                for m in uecheat.companions(self.proj.sdk, target)
                if Q.PACK.get(Q.norm_type(m.type)) and m.bit < 0 and "max" in m.name.lower()
            ]
        except Exception:
            return []

    def set_to_max(self):
        rows = self._targets_or_warn()
        comp = self._companions(self.cur) if rows else []
        if not rows or not comp:
            return
        cur, client, max_target = self.cur, self.win.client, comp[0]

        def job():
            for row in rows:
                mv, _ = Q.read_value(client.read_memory, row["vaddr"] - row.get("off", cur.offset) + max_target.offset, max_target)
                disp = mv / Q.FIXED_SCALE if max_target.is_fixed else mv
                v = Q.parse_input(cur, repr(disp))
                Q.write_value(client.read_memory, client.write_memory, row["vaddr"], cur, v)
                if row["vaddr"] in self.freezer:
                    self.freezer.add(row["vaddr"], cur, v)
                row["val"], row["txt"] = Q.read_value(client.read_memory, row["vaddr"], cur)
            return len(rows)

        self.bg(
            job, lambda n: (self._refresh_texts(rows), self.log(f"UE-LIVE: {cur.member} = {max_target.member}", "ok"))
        )

    def freeze_sel(self):
        rows = self._targets_or_warn()
        if not rows:
            return
        cur, client = self.cur, self.win.client
        text = self.v_val.get().strip()
        try:
            planned = [(row, Q.parse_input(cur, text, row["val"]) if text else row["val"]) for row in rows]
        except ValueError as error:
            return self.log(f"UE-LIVE: {error}", "err")
        if any(v is None for _r, v in planned):
            return self.log("UE-LIVE: Wert nicht lesbar - nicht einfrieren", "err")

        def job():
            for row, value in planned:
                Q.write_value(client.read_memory, client.write_memory, row["vaddr"], cur, value)
                self.freezer.add(row["vaddr"], cur, value)
                row["val"], row["txt"] = Q.read_value(client.read_memory, row["vaddr"], cur)
            return len(planned)

        self.bg(
            job,
            lambda n: (
                self._render(),
                self.log(f"UE-LIVE: {n} Wert(e) eingefroren bei {planned[0][0]['txt']} (AUFTAUEN zum Lösen)", "ok"),
            ),
        )

    def unfreeze_sel(self):
        n = 0
        for r in self._sel_rows() if self.cur else []:
            if r["vaddr"] in self.freezer:
                self.freezer.remove(r["vaddr"])
                n += 1
        self._render()
        self.log(f"UE-LIVE: {n} aufgetaut", "ok")

    def unfreeze_all(self):
        self.freezer.clear()
        self._render()
        self.log("UE-LIVE: alles aufgetaut", "ok")

    def _sel_row_addr(self):
        sel = [self.rows[int(i)] for i in self.tr.selection() if int(i) < len(self.rows)]
        if not sel:
            raise ValueError("erst eine Zeile wählen")
        return sel[0]["vaddr"]

    def to_memory(self):
        try:
            self.win.goto_memory(self._sel_row_addr())
        except Exception as error:
            self.log(f"UE-LIVE: {error}", "err")

    def to_watch(self):
        try:
            self.win.to_debug_watch(self._sel_row_addr(), min(self.cur.size or 4, 8))
        except Exception as error:
            self.log(f"UE-LIVE: {error}", "err")

    def shutdown(self):
        self.freezer.clear()
        if self.proj:
            self.proj.close()
