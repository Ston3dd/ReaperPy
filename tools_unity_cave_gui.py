"""tools_unity_cave_gui.py - Tab "CAVEMAKER" im Reiter UNITY: Cheats aus der dump.cs - auswählen, Wert setzen, Cave bauen,
testen, ins Projekt übernehmen.  Die Logik steckt in cavemaker.py (ohne Oberfläche, mit Tests), hier ist nur die Bedienung.

  1) Im Tab MANUELL den Spiel-Ordner laden (dump.cs + script.json), verbinden, MODUL ERKENNEN - der CAVEMAKER benutzt
     dieselbe Verbindung, dasselbe Spiel und dieselbe Modul-Basis, es wird nichts zweimal geladen
  2) In der Liste eine Methode oder ein Feld wählen, WAS PASSIEREN SOLL und den Wert eintragen
  3) HINZUFÜGEN: liest die Original-Bytes live von der Konsole und baut Patch oder Code-Cave samt Signatur
     (statische Felder: HAKEN AUTOMATISCH FINDEN probiert Methoden live durch, bis der Wert wirklich gesetzt wird)
  4) TEST AN / TEST AUS direkt auf der Konsole, dann IN PROJEKT ÜBERNEHMEN: jeder Hook wird vorher mit ReaperPys eigenem
     Parser und Cave-Assembler geprüft (cave_check.py) und kommt als normale Karte ins Hauptfenster
"""
import tkinter as tk
from tkinter import messagebox, ttk

import cave_check as CC
import cavemaker as CM
from tools_cave_common import CaveCollectionMixin, Item, out_dir_for
from tools_common import (ACCENT, BG, BG_CARD, BORDER_HVR, FONT_LABEL, TEXT_DIM, WARN, BaseTab, button, entry, label,
                          tree, with_scroll)
from tools_unity_gui import _load_cfg, _save_cfg

MAX_ROWS = 3000
ALL = "Alle"
KIND_STATIC = "Statisch (live)"


class UnityCaveTab(CaveCollectionMixin, BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.model = self.model_of = None
        self.cands, self.shown = [], []
        self.actions, self.hooks = [], []
        self.items = []
        self.live, self.cur = {}, None
        self._busy = False
        self._after = None
        self._cfg = _load_cfg()
        CM.init_reaperpy()

        self.v_info = tk.StringVar(value="Erst im Tab MANUELL den Spiel-Ordner laden, verbinden und MODUL ERKENNEN - "
                                         "dann hier LISTE LADEN.")
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=8, pady=(8, 2))
        button(top, "LISTE LADEN", self.load_list, accent=True).pack(side="left", padx=2)
        label(top, "SUCHE").pack(side="left", padx=(8, 2))
        self.v_search = tk.StringVar()
        e_search = entry(top, self.v_search, 22)
        e_search.pack(side="left", padx=2)
        e_search.bind("<KeyRelease>", lambda _e: self._refilter_later())
        self.v_cat = tk.StringVar(value=ALL)
        self.cb_cat = ttk.Combobox(top, textvariable=self.v_cat, width=14, state="readonly",
                                   values=[ALL] + [c for c, _ in CM.CATS] + ["Sonstige"])
        self.cb_cat.pack(side="left", padx=4)
        self.cb_cat.bind("<<ComboboxSelected>>", lambda _e: self._refilter())
        self.v_kind = tk.StringVar(value=ALL)
        self.cb_kind = ttk.Combobox(top, textvariable=self.v_kind, width=14, state="readonly",
                                    values=[ALL, "Methode", "Feld", KIND_STATIC])
        self.cb_kind.pack(side="left", padx=4)
        self.cb_kind.bind("<<ComboboxSelected>>", lambda _e: self._refilter())
        self.v_libs = tk.BooleanVar(value=False)
        self.v_scored = tk.BooleanVar(value=True)
        for txt, var in (("Unity/System", self.v_libs), ("nur sinnvolle Cheats", self.v_scored)):
            tk.Checkbutton(top, text=txt, variable=var, command=self._refilter, bg=BG, fg=TEXT_DIM, selectcolor=BG,
                           activebackground=BG, font=FONT_LABEL).pack(side="left", padx=4)
        button(top, "WERTE LESEN (live)", self.read_live).pack(side="left", padx=(8, 2))
        self.lbl_info = label(self, "", justify="left", anchor="w")
        self.lbl_info.configure(textvariable=self.v_info)
        self.lbl_info.pack(fill="x", padx=12, pady=2)

        self.vpan = tk.PanedWindow(self, orient="vertical", sashwidth=8, sashrelief="raised", bg=BORDER_HVR, bd=0,
                                   opaqueresize=True)
        self.vpan.pack(fill="both", expand=True, padx=8, pady=4)
        upper = tk.Frame(self.vpan, bg=BG)
        self.vpan.add(upper, minsize=200, stretch="always")
        lower = tk.Frame(self.vpan, bg=BG)
        self.vpan.add(lower, minsize=120, stretch="never")

        # ---- oben: Liste + Aktion ----
        lf = tk.Frame(upper, bg=BG)
        lf.pack(side="left", fill="both", expand=True)
        self.v_count = tk.StringVar(value="")
        tk.Label(lf, textvariable=self.v_count, bg=BG, fg=TEXT_DIM, font=FONT_LABEL, anchor="w").pack(fill="x")
        tf = tk.Frame(lf, bg=BG)
        tf.pack(fill="both", expand=True)
        self.tl = tree(tf, [("score", "PKT"), ("cat", "KATEGORIE"), ("kind", "ART"), ("label", "KLASSE.NAME"),
                            ("live", "WERT LIVE"), ("sig", "TYP / SIGNATUR")], [40, 100, 70, 260, 100, 300], height=10)
        self.tl.column("label", stretch=True)
        with_scroll(tf, self.tl)
        self.tl.bind("<<TreeviewSelect>>", lambda _e: self._selected())

        rf = tk.Frame(upper, bg=BG)
        rf.pack(side="left", fill="y", padx=(8, 0))
        self.v_sel = tk.StringVar(value="Nichts gewählt")
        tk.Label(rf, textvariable=self.v_sel, bg=BG, fg=ACCENT, font=FONT_LABEL, wraplength=420, justify="left",
                 anchor="w").pack(fill="x")
        label(rf, "WAS SOLL PASSIEREN?").pack(anchor="w", pady=(4, 0))
        self.v_act = tk.StringVar()
        self.cb_act = ttk.Combobox(rf, textvariable=self.v_act, state="readonly", values=[], width=58)
        self.cb_act.pack(fill="x")
        self.cb_act.bind("<<ComboboxSelected>>", lambda _e: self._act_changed())
        self.v_note = tk.StringVar(value="")
        tk.Label(rf, textvariable=self.v_note, bg=BG, fg=WARN, font=FONT_LABEL, wraplength=420, justify="left",
                 anchor="w").pack(fill="x")
        vr = tk.Frame(rf, bg=BG)
        vr.pack(fill="x", pady=4)
        label(vr, "MODUS").pack(side="left")
        self.v_mode = tk.StringVar()
        self.cb_mode = ttk.Combobox(vr, textvariable=self.v_mode, state="readonly", values=[], width=18)
        self.cb_mode.pack(side="left", padx=(4, 8))
        label(vr, "MENGE / WERT").pack(side="left")
        self.v_val = tk.StringVar(value="99")
        entry(vr, self.v_val, 12).pack(side="left", padx=4)
        self.v_flag = tk.BooleanVar(value=True)
        tk.Checkbutton(vr, text="Flag AN (true)", variable=self.v_flag, bg=BG, fg=TEXT_DIM, selectcolor=BG,
                       activebackground=BG, font=FONT_LABEL).pack(side="left", padx=4)
        self.fr_hook = tk.Frame(rf, bg=BG)
        self.fr_hook.pack(fill="x")
        label(self.fr_hook, "HAKEN-METHODE (läuft oft, z. B. Update)").pack(anchor="w")
        self.v_hook = tk.StringVar()
        self.cb_hook = ttk.Combobox(self.fr_hook, textvariable=self.v_hook, state="readonly", values=[], width=58)
        self.cb_hook.pack(fill="x")
        nr = tk.Frame(rf, bg=BG)
        nr.pack(fill="x", pady=4)
        label(nr, "NAME").pack(side="left")
        self.v_name = tk.StringVar()
        entry(nr, self.v_name, 40).pack(side="left", padx=4, fill="x", expand=True)
        br = tk.Frame(rf, bg=BG)
        br.pack(fill="x", pady=2)
        button(br, "VORSCHAU", lambda: self.generate(False)).pack(side="left", padx=2)
        button(br, "HINZUFÜGEN", lambda: self.generate(True), accent=True).pack(side="left", padx=2)
        button(br, "JETZT SCHREIBEN", self.write_now).pack(side="left", padx=(8, 2))
        br2 = tk.Frame(rf, bg=BG)
        br2.pack(fill="x", pady=2)
        button(br2, "HAKEN AUTOMATISCH FINDEN + HINZUFÜGEN", self.auto_hook, accent=True).pack(side="left", padx=2)
        label(br2, "(statische Felder; im laufenden Spiel bleiben)", dim=True).pack(side="left", padx=4)
        self.txt = tk.Text(rf, height=9, width=60, bg=BG_CARD, fg=TEXT_DIM, font=FONT_LABEL, relief="flat", wrap="none")
        self.txt.pack(fill="both", expand=True, pady=4)

        # ---- unten: Sammlung (gemeinsam mit Unreal: tools_cave_common) ----
        self._build_collection(lower)
        button(self.coll_bar, "ANDEREN HAKEN SUCHEN", self.rehook).pack(side="left", padx=2)
        self.after(250, lambda: self._place_sash())

    # ------------------------------------------------------------------ Zugriff auf UNITY / Konsole
    def _unity(self):
        for t in getattr(self.win, "extra_tabs", []):
            if t.__class__.__name__ == "UnityTab":
                return t
        return None

    def _place_sash(self):
        try:
            self.vpan.sash_place(0, 0, int(self.vpan.winfo_height() * 0.62))
        except Exception:  # noqa: BLE001
            pass

    def _ctx_job(self):
        """Im Job-Thread: Modul-Basis (wie im Tab MANUELL) + Image-Basis des Hauptfensters -> Ctx."""
        un, be = self._unity(), self._backend()
        if un is None or un.game is None:
            raise ValueError("Erst im Tab MANUELL den Spiel-Ordner laden.")
        live = un._ensure_base(be.client)
        if live.base != self.base:
            self.win.ui(lambda: self.log(
                f"CAVEMAKER: Das IL2CPP-Modul liegt bei {live.base:#x}, die Image-Basis im Hauptfenster ist {self.base:#x}. "
                f"Die Offsets der Patches sind relativ zur Image-Basis; die Signatur findet den Hook auch nach einem "
                f"Neustart wieder.", "warn"))
        return CM.Ctx(be, live.base, self.base)

    # ------------------------------------------------------------------ Liste
    def load_list(self):
        un = self._unity()
        game = getattr(un, "game", None)
        if game is None:
            return self.log("CAVEMAKER: erst im Tab MANUELL den SPIEL-ORDNER laden", "warn")
        if self.model is None or self.model_of is not game:
            typeinfo = getattr(game, "typeinfo_rva", None) or {}
            self.model, self.model_of = CM.Model(game.classes, typeinfo, lambda m: self.log(f"CAVEMAKER: {m}", "info")), game
            self.live = {}
        self._refilter()
        n = len(self.model.candidates(self.v_libs.get()))
        self.v_info.set(f"{len(self.model.classes)} Klassen, {n} Kandidaten im Spiel-Code"
                        + (f", {len(self.model.typeinfo)} TypeInfo-Zeiger (statische Felder möglich)" if self.model.typeinfo
                           else ", ohne script.json (statische Felder nicht möglich)"))

    def _refilter_later(self):
        if self._after:
            try:
                self.after_cancel(self._after)
            except Exception:  # noqa: BLE001
                pass
        self._after = self.after(250, self._refilter)

    def _refilter(self):
        if self.model is None:
            return
        cands = self.model.candidates(self.v_libs.get())
        self.shown, total = CM.filter_cands(cands, self.v_search.get(), self.v_cat.get(), self.v_kind.get(),
                                            self.v_scored.get(), limit=MAX_ROWS)
        self.tl.delete(*self.tl.get_children())
        for i, c in enumerate(self.shown):
            self.tl.insert("", "end", iid=str(i), values=(
                c.score, c.cat, CM.KIND_NAMES[c.kind], c.label,
                self.live.get(CM.live_key(c), "") if CM.is_static_field(c) else "", c.sig))
        more = f" (zeige die ersten {len(self.shown)})" if total > len(self.shown) else ""
        self.v_count.set(f"{total} Treffer{more}")

    def read_live(self):
        if self.model is None:
            return self.log("CAVEMAKER: erst LISTE LADEN", "warn")
        cs = [c for c in self.shown if CM.is_static_field(c)][:600]
        if not cs:
            return self.log("CAVEMAKER: keine statischen Felder in der Liste - Filter 'Statisch (live)' wählen "
                            "(braucht script.json)", "warn")
        model = self.model

        def job():
            return CM.read_static_values(model, self._ctx_job(), cs)

        def ok(res):
            self.live.update(res)
            self._refilter()
            self.log(f"CAVEMAKER: {len(res)} Werte gelesen", "ok")

        self.bg(job, ok, lambda e: self.log(f"CAVEMAKER: Lesen: {e}", "err"))

    # ------------------------------------------------------------------ Auswahl
    def _selected(self):
        sel = self.tl.selection()
        if not sel:
            return
        self.select(self.shown[int(sel[0])])

    def select(self, c):
        self.cur = c
        self.v_sel.set(f"{c.cls.full}.{CM.clean_name(c.mem.name)}   [{c.sig}]")
        if c.kind == "method":
            acts, why = CM.actions_for_method(self.model, c.mem)
        else:
            acts, why = CM.actions_for_field(self.model, c.cls, c.mem)
        self.actions = acts
        self.cb_act.configure(values=[a.label for a in acts])
        if acts:
            self.v_act.set(acts[0].label)
            self.v_note.set("")
            self._act_changed()
        else:
            self.v_act.set("")
            self.cb_mode.configure(values=[])
            self.v_note.set(f"Nicht möglich: {why}")

    def _cur_action(self):
        lab = self.v_act.get()
        return next((a for a in self.actions if a.label == lab), None)

    def _cur_mode(self, a):
        text = self.v_mode.get()
        for m in a.modes:
            if CM.MODE_NAMES[m] == text:
                return m
        return a.modes[0]

    def _act_changed(self):
        a = self._cur_action()
        if a is None:
            return
        self.cb_mode.configure(values=[CM.MODE_NAMES[m] for m in a.modes])
        self.v_mode.set(CM.MODE_NAMES[a.modes[0]])
        self.v_note.set(a.note)
        self.hooks = CM.hook_choices(self.model, a) if a.need_hook else []
        self.cb_hook.configure(values=[t for t, _m in self.hooks])
        self.v_hook.set(self.hooks[0][0] if self.hooks else "")
        self.v_name.set("")

    def _value(self, a):
        return self.v_flag.get() if (a.ti is not None and a.ti.name == "bool") else self.v_val.get()

    def _cur_hook(self, a):
        if not a.need_hook:
            return None
        text = self.v_hook.get()
        for t, m in self.hooks:
            if t == text:
                return m
        raise ValueError("Haken-Methode wählen")

    # ------------------------------------------------------------------ Erzeugen
    def generate(self, add, a=None, mode=None, value=None, hook=None, name=None):
        """VORSCHAU / HINZUFÜGEN.  Die Parameter (a, mode, ...) dienen nur dem Aufruf aus Tests."""
        a = a or self._cur_action()
        if a is None:
            return self.log("CAVEMAKER: erst links etwas auswählen", "warn")
        try:
            mode = mode or self._cur_mode(a)
            value = self._value(a) if value is None else value
            hook = hook or self._cur_hook(a)
            name = name if name is not None else (self.v_name.get().strip() or None)
            if a.ti is not None and a.key != "void":
                CM.norm_value(a.ti, value, mode)
        except ValueError as e:
            return messagebox.showerror("CaveMaker", str(e))
        model = self.model

        def job():
            ctx = self._ctx_job()
            hm = a.method if a.method is not None else hook
            if add and hm is not None:
                other = self._used_hooks().get(ctx.module_base + hm.rva)
                if other:
                    raise ValueError(f"Dieser Haken ({hm.cls.name}.{hm.name}) wird schon von '{other}' benutzt. Zwei "
                                     f"Cheats am selben Haken gehen nicht gleichzeitig - bitte eine andere "
                                     f"Haken-Methode wählen oder HAKEN AUTOMATISCH FINDEN benutzen.")
            pd = CM.build_patch(model, ctx, a, mode, value, hook, name)
            if add:
                try:
                    pd.aob, _hits = CM.AOB.make_signature(ctx.backend.client, ctx.backend.get_maps(), pd.hook_addr,
                                                          pd.hook_len)
                except Exception as e:  # noqa: BLE001
                    pd.warnings.append(f"Keine eindeutige Signatur ({e}) - der Patch gilt nur für diese Basis")
            probs = CC.doc_problems(pd.to_json(self._author()), ctx.backend, pd.hook_addr)
            if probs:
                raise ValueError("ReaperPy würde diesen Hook nicht richtig verstehen: " + "; ".join(probs))
            return pd

        def ok(pd):
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", pd.preview())
            for w in pd.warnings:
                self.log(f"CAVEMAKER: Hinweis: {w}", "warn")
            if add:
                self._add_item(Item(pd, (a, mode, value)))
                hm = a.method if a.method is not None else hook
                if hm is not None and a.key != "void":
                    self.log(f"CAVEMAKER: Achtung: Dieser Cheat wirkt nur, wenn '{hm.cls.name}.{hm.name}' im Spiel läuft. "
                             f"Passiert nichts, ist die Methode die falsche - dann HAKEN AUTOMATISCH FINDEN oder "
                             f"JETZT SCHREIBEN nehmen.", "warn")
            else:
                self.log(f"CAVEMAKER: Vorschau: {pd.summary}", "ok")

        self.bg(job, ok, lambda e: self.log(f"CAVEMAKER: Erzeugen: {e}", "err"))

    # ------------------------------------------------------------------ Haken automatisch finden
    def _write_args(self):
        a = self._cur_action()
        if a is None or a.key != "static":
            self.log("CAVEMAKER: Das geht nur bei statischen Feldern: links ein Feld mit Wert in der Spalte WERT LIVE "
                     "wählen, rechts 'Statisches Feld festhalten'.", "warn")
            return None
        mode = self._cur_mode(a)
        try:
            CM.norm_value(a.ti, self._value(a), mode)
        except ValueError as e:
            messagebox.showerror("CaveMaker", str(e))
            return None
        return a, mode, self._value(a)

    def auto_hook(self):
        args = self._write_args()
        if args is not None:
            self._run_search(*args)

    def rehook(self):
        i, it = self._item()
        if it is None:
            return
        if not it.meta or it.meta[0].key != "static":
            return self.log("CAVEMAKER: Das geht nur bei Einträgen, die in dieser Sitzung aus einem statischen Feld "
                            "gebaut wurden. Sonst: ENTFERNEN und neu mit HAKEN AUTOMATISCH FINDEN anlegen.", "warn")
        self._run_search(*it.meta, replace=i)

    def _run_search(self, a, mode, value, replace=None):
        if mode not in ("set", "min"):
            return self.log("CAVEMAKER: Die Haken-Suche geht nur mit 'festlegen (=)' oder 'mindestens (>=)'.", "warn")
        if self._busy:
            return self.log("CAVEMAKER: Die Suche läuft schon.", "warn")
        used = self._used_hooks(skip=replace)
        old = self.items[replace] if replace is not None else None
        name = (old.pd.name if old is not None else self.v_name.get().strip()) or None
        model, author = self.model, self._author()
        allm = [m for _t, m in CM.hook_choices(model, a)]
        self._busy = True
        self.log(f"CAVEMAKER: Haken-Suche für {CM.clean_name(a.field.name)}: ich probiere bis zu 60 Methoden, je etwa "
                 f"3-4 s. Bitte im Spiel bleiben und NICHT im Menü stehen - am besten im laufenden Spiel herumlaufen …",
                 "warn")

        def job():
            ctx = self._ctx_job()
            cands = [m for m in allm if ctx.module_base + m.rva not in used][:60]
            if not cands:
                raise ValueError("Keine freie Haken-Methode zur Auswahl.")
            if old is not None and old.state:                      # alten Haken erst freigeben
                CM.PE.deactivate_patch(ctx.backend, self._reapatch(old), old.state)
                old.state = None
            res = CM.find_working_hook(model, ctx, a, mode, value, cands, name,
                                       lambda m: self.win.ui(lambda: self.log(f"CAVEMAKER: {m}", "info")), author)
            if res is not None:
                probs = CC.doc_problems(res[0].to_json(author), ctx.backend, res[0].hook_addr)
                if probs:
                    CM.PE.deactivate_patch(ctx.backend, res[1], res[2])
                    raise ValueError("ReaperPy würde diesen Hook nicht richtig verstehen: " + "; ".join(probs))
            return res

        def ok(res):
            self._busy = False
            if replace is not None and self.coll.get_children():
                self.coll.set(str(replace), "state", "aus")
            if res is None:
                return self.log("CAVEMAKER: Kein Haken gefunden, der den Wert setzt. Spiel an eine andere Stelle bringen "
                                "(z. B. im Laden) und nochmal versuchen - oder JETZT SCHREIBEN nehmen.", "err")
            pd, rp, st, hm, regular = res
            it = Item(pd, (a, mode, value))
            it.rp, it.state = rp, st
            self._add_item(it, replace)
            for w in pd.warnings:
                self.log(f"CAVEMAKER: Hinweis: {w}", "warn")
            if regular:
                self.log(f"CAVEMAKER: GEFUNDEN: {hm.cls.name}.{hm.name} - läuft regelmäßig, der Cheat wirkt dauerhaft "
                         f"(Status AN).", "ok")
            else:
                self.log(f"CAVEMAKER: NUR NOTLÖSUNG: {hm.cls.name}.{hm.name} läuft nur bei einem Ereignis. Der Cheat wirkt "
                         f"nur in diesen Momenten. Besser: im Spiel an eine andere Stelle gehen und die Suche wiederholen.",
                         "warn")

        def fail(e):
            self._busy = False
            self.log(f"CAVEMAKER: Haken-Suche: {e}", "err")

        self.bg(job, ok, fail)

    # ------------------------------------------------------------------ Direkt schreiben
    def write_now(self):
        args = self._write_args()
        if args is None:
            return
        a, mode, value = args
        model = self.model

        def job():
            return CM.write_static_value(model, self._ctx_job(), a.owner, a.field, a.ti, mode, value)

        def ok(r):
            cur, new, good = r
            nm = CM.clean_name(a.field.name)
            if good:
                self.log(f"CAVEMAKER: Geschrieben: {nm}  {cur:g} -> {new:g}  (nachgelesen: stimmt)", "ok")
            else:
                self.log(f"CAVEMAKER: {nm}: geschrieben, aber der Wert ist danach nicht {new:g} - das Spiel überschreibt "
                         f"ihn wohl sofort. Dann HAKEN AUTOMATISCH FINDEN benutzen.", "warn")

        self.bg(job, ok, lambda e: self.log(f"CAVEMAKER: Schreiben: {e}", "err"))

    # ------------------------------------------------------------------ Sammlung (Mixin) + Wirkungsprüfung
    def _after_test_on(self, it):
        if it.meta and it.meta[0].key == "static":
            self._verify_static(it)

    def _verify_static(self, it):
        """Nach TEST AN: Wird das statische Feld wirklich gesetzt (und immer wieder neu)?"""
        a, mode, value = it.meta
        model = self.model

        def job():
            import time
            ctx = self._ctx_job()
            ti = a.ti
            target = CM.norm_value(ti, value, mode)
            addr = CM.static_addr(model, ctx, a.owner, a.field)
            cur = None
            for _ in range(12):
                time.sleep(0.5)
                cur = CM.decode_value(ti, ctx.read(addr, ti.size))
                if CM.value_reached(ti, mode, cur, target):
                    CM.write_mem(ctx.backend, addr, CM.encode_value(ti, CM.different_value(ti, target)))
                    for _ in range(8):
                        time.sleep(0.25)
                        if CM.value_reached(ti, mode, CM.decode_value(ti, ctx.read(addr, ti.size)), target):
                            return True, cur, True
                    return True, cur, False
            return False, cur, False

        def ok(r):
            good, cur, regular = r
            nm = CM.clean_name(a.field.name)
            if good and regular:
                self.log(f"CAVEMAKER: Test OK: {nm} steht auf {cur:g} und wird immer wieder neu gesetzt - der Cheat wirkt "
                         f"dauerhaft.", "ok")
            elif good:
                self.log(f"CAVEMAKER: Test nur TEILWEISE OK: {nm} wurde einmal auf {cur:g} gesetzt, aber der Haken läuft nur "
                         f"ab und zu. Besser: HAKEN AUTOMATISCH FINDEN.", "warn")
            else:
                self.log(f"CAVEMAKER: Test FEHLGESCHLAGEN: {nm} ist noch {cur:g}. Die Haken-Methode läuft im Spiel nicht "
                         f"(oder zu selten). TEST AUS, ENTFERNEN und HAKEN AUTOMATISCH FINDEN.", "err")

        self.log("CAVEMAKER: Prüfe 6 s lang, ob der Wert wirklich gesetzt wird - bitte im Spiel weiterspielen …", "info")
        self.bg(job, ok, lambda e: self.log(f"CAVEMAKER: Prüfung: {e}", "err"))

    # ------------------------------------------------------------------ Ablage
    def _out_dir(self):
        un = self._unity()
        return out_dir_for(getattr(getattr(un, "game", None), "title", ""), "Unity-Cavemaker")

    def _save_cfg(self):
        _save_cfg(self._cfg)
