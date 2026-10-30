"""tools_cheatmenu_gui.py - Tab "CHEAT-MENUE": Schalter und Werte fuer die Spielfigur, aus dem SDK erzeugt.

Funktioniert auch in Shipping-Builds ohne CheatManager: es werden nur gewoehnliche Speicherwerte der Figur
geschrieben (Engine-Werte wie bCanBeDamaged / MovementMode / MaxWalkSpeed sowie Leben/Ausdauer/Geld aus dem SDK).
  1) Im Tab UE-LIVE den SPIEL-ORDNER laden und verbinden, Spielstand laden (nicht Hauptmenue)
  2) MENUE AUFBAUEN - jeder Eintrag zeigt, ob er an deiner Figur erreichbar ist (✔) oder warum nicht (✗)
  3) Eintrag anklicken -> AN / AUS (Doppelklick geht auch); bei Werten vorher die Zahl eintippen
  4) Rechtsklick auf einen Eintrag -> "Passende Code Cave bauen": sucht im Spiel-Code die Instruktion, die den Wert schreibt,
     und legt die Cave als .reapproj im Projekt ab (Logik: cheatmenu_cave.py)
Logik: cheatmenu.py (testbar ohne Oberflaeche und Konsole).
"""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import cheatmenu as M
import cheatmenu_cave as CV
from tools_common import BG, TEXT_DIM, BaseTab, button, entry, label, tree, with_scroll

try:
    from tools_i18n import translate as _tr
except Exception:  # noqa: BLE001
    def _tr(text):
        return text

NO_HIT = "Cheat-Menü: Keine Instruktion schreibt diesen Wert (Offset im Spiel-Code nicht vorhanden?): "
TICK_MS = 250
GUARD_EVERY = 8          # alle 8 Ticks (~2 s) zusaetzlich die Objektliste neu pruefen


class CheatMenuTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.menu = None
        self.view = []                    # angezeigte Eintraege (iid = Index)
        self._busy = False
        self.v_info = tk.StringVar(value="Erst im Tab UE-LIVE den Spiel-Ordner laden und verbinden, Spielstand laden, "
                                         "dann MENUE AUFBAUEN.")
        self.v_val = tk.StringVar()
        self.v_hold = tk.BooleanVar(value=True)
        self.v_note = tk.StringVar()

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=8, pady=(8, 2))
        button(top, "🔄  MENÜ AUFBAUEN", self.build, accent=True).pack(side="left", padx=2)
        button(top, "ALLE AUS", self.all_off).pack(side="left", padx=2)
        label(self, "", dim=False)
        self.lbl_info = label(self, "", dim=False)
        self.lbl_info.configure(textvariable=self.v_info)
        self.lbl_info.pack(anchor="w", padx=10)

        mid = tk.Frame(self, bg=BG)
        mid.pack(fill="both", expand=True, padx=8, pady=4)
        self._code = None                 # (Schluessel, Code-Sicht, Disassembler) - der Spiel-Code wird nur einmal gelesen
        self.tv = tree(mid, [("on", "AN"), ("cat", "KATEGORIE"), ("label", "EINTRAG"), ("val", "WERT / STATUS")],
                       [50, 120, 380, 360], height=16, anchors={"on": "center"},
                       actions=[("⚙  Passende Code Cave bauen", self.cave_auto),
                                ("⚙  Code Cave bauen - Treffer selbst wählen ...", self.cave_pick)])
        with_scroll(mid, self.tv)
        self.tv.bind("<Double-1>", lambda _e: self.toggle())
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self._on_select())

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=8, pady=(2, 0))
        button(bar, "AN / AUS", self.toggle, accent=True).pack(side="left", padx=2)
        label(bar, "  Wert").pack(side="left")
        entry(bar, self.v_val, 12).pack(side="left", padx=4)
        button(bar, "WERT SETZEN", self.set_value).pack(side="left", padx=2)
        tk.Checkbutton(bar, text="festhalten", variable=self.v_hold, bg=BG, fg=TEXT_DIM, selectcolor=BG,
                       activebackground=BG).pack(side="left", padx=8)
        self.lbl_note = label(self, "", dim=True)
        self.lbl_note.configure(textvariable=self.v_note, justify="left", wraplength=900)
        self.lbl_note.pack(anchor="w", padx=10, pady=(4, 8))
        label(self, "Alles sind Speicherwerte der Figur - kein CheatManager, kein Code-Patch. Wechselt die Figur "
                    "(Tod/Ladebildschirm), werden alle Eintraege automatisch freigegeben.", dim=True).pack(anchor="w", padx=10)
        self._n = 0
        self.after(TICK_MS, self._tick)

    # -- Zugriff auf UE-LIVE ----------------------------------------------------------------------
    def _uelive(self):
        for t in getattr(self.win, "extra_tabs", []):
            if t.__class__.__name__ == "UeLiveTab":
                return t
        return None

    def _sdk(self):
        return getattr(getattr(self._uelive(), "proj", None), "sdk", None)

    def _live(self):
        live = getattr(self._uelive(), "live", None)
        if live is None:
            raise ValueError("Kein Live-Zugriff - im Tab UE-LIVE zuerst das Spiel laden und verbinden")
        if live.index is None:
            live.build_index()
        return live

    # -- Aufbau ---------------------------------------------------------------------------------
    def build(self):
        if self._busy:
            return
        sdk = self._sdk()
        if sdk is None:
            self.log("Cheat-Menü: kein SDK geladen - im Tab UE-LIVE den SPIEL-ORDNER wählen", "err")
            return
        self._busy = True
        self.v_info.set("Baue das Menü auf und prüfe die Spielfigur …")

        def job():
            live = self._live()
            if self.menu is not None:
                self.menu.release_all(restore=False)
            menu = M.CheatMenu(live, sdk, self.win.client, log=lambda m, k="info": self.win.ui(lambda: self.log(m, k)))
            menu.build()
            menu.check_live()
            return menu

        def ok(menu):
            self._busy = False
            self.menu = menu
            self._fill()
            n_ok = sum(1 for e in menu.entries if e.ok and not e.hidden)
            n = sum(1 for e in menu.entries if not e.hidden)
            self.v_info.set(f"{n_ok} von {n} Einträgen erreichbar (✔). Eintrag anklicken -> AN / AUS.")
            self.log(f"Cheat-Menü: {n_ok}/{n} Einträge an der Spielfigur erreichbar", "ok" if n_ok else "err")

        def fail(e):
            self._busy = False
            msg = str(e) or e.__class__.__name__
            self.v_info.set("Fehler: " + msg)
            self.log("Cheat-Menü: " + msg, "err")

        self.bg(job, ok, fail)

    def _fill(self, keep=None):
        self.tv.delete(*self.tv.get_children())
        self.view = []
        if self.menu is None:
            return
        order = {}
        for e in self.menu.entries:
            order.setdefault(e.cat, len(order))
        for e in sorted((x for x in self.menu.entries if not x.hidden), key=lambda x: (order[x.cat], not x.ok)):
            self.tv.insert("", "end", iid=str(len(self.view)), values=self._row(e))
            self.view.append(e)
        if keep is not None and keep < len(self.view):
            self.tv.selection_set(str(keep))

    @staticmethod
    def _row(e):
        if not e.ok:
            return ("✗", e.cat, e.label, e.status)
        if e.active:
            return ("✔", e.cat, e.label, "AN" + ("  (festgehalten)" if e.held else ""))
        return ("☐", e.cat, e.label, "bereit" + (f"  (Vorgabe {e.default})" if e.kind == "value" else ""))

    def _selected(self):
        sel = self.tv.selection()
        if not sel:
            return None
        try:
            return self.view[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def _on_select(self):
        e = self._selected()
        if e is None:
            return
        if e.kind == "value":
            self.v_val.set(e.default)
        self.v_note.set((e.note + "  " if e.note else "") + (f"✗ {e.status}" if not e.ok else ""))

    def _refresh(self):
        sel = self.tv.selection()
        self._fill(int(sel[0]) if sel else None)

    # -- Schalten -------------------------------------------------------------------------------
    def _run(self, fn, done_msg):
        if self.menu is None or self._busy:
            if self.menu is None:
                self.log("Cheat-Menü: erst MENÜ AUFBAUEN", "err")
            return
        self._busy = True

        def ok(n):
            self._busy = False
            self._refresh()
            self.log(done_msg(n), "ok")

        def fail(e):
            self._busy = False
            self._refresh()
            self.log(f"Cheat-Menü: {e}", "err")

        self.bg(fn, ok, fail)

    def toggle(self):
        e = self._selected()
        if e is None:
            self.log("Cheat-Menü: erst einen Eintrag anklicken", "err")
            return
        if not e.ok:
            self.log(f"Cheat-Menü: {e.label}: {e.status}", "err")
            return
        menu, hold, text = self.menu, self.v_hold.get(), self.v_val.get().strip() or e.default
        if e.kind == "toggle":
            on = not e.active
            self._run(lambda: menu.set_toggle(e.key, on), lambda n: f"{e.label}: {'AN' if on else 'AUS'}")
        elif e.active:
            self._run(lambda: (menu.release(e.key), 0)[1], lambda n: f"{e.label}: freigegeben (Originalwert zurück)")
        else:
            self._run(lambda: menu.set_value(e.key, text, hold), lambda n: f"{e.label} = {text}")

    def set_value(self):
        e = self._selected()
        if e is None or e.kind != "value":
            self.log("Cheat-Menü: einen Wert-Eintrag anklicken (nicht einen Schalter)", "err")
            return
        if not e.ok:
            self.log(f"Cheat-Menü: {e.label}: {e.status}", "err")
            return
        menu, hold, text = self.menu, self.v_hold.get(), self.v_val.get().strip() or e.default
        self._run(lambda: menu.set_value(e.key, text, hold), lambda n: f"{e.label} = {text}")

    def all_off(self):
        if self.menu is None:
            return
        menu = self.menu
        self._run(lambda: (menu.release_all(), 0)[1], lambda n: "Cheat-Menü: alles aus, Originalwerte zurückgeschrieben")

    # -- Code Cave per Rechtsklick ----------------------------------------------------------------
    def _cave_target(self):
        """Gewaehlter Eintrag, wenn eine Cave dafuer ueberhaupt gebaut werden darf - sonst Hinweis im Log und None."""
        e = self._selected()
        if e is None:
            self.log("Cheat-Menü: erst einen Eintrag anklicken (Rechtsklick wählt ihn aus)", "err")
            return None
        if self.menu is None:
            self.log("Cheat-Menü: erst MENÜ AUFBAUEN", "err")
            return None
        if self._busy:
            self.log("Cheat-Menü: bitte kurz warten, es läuft noch etwas", "warn")
            return None
        if not e.ok and e.offset < 0:               # Member gibt es nicht -> nichts, wonach man suchen koennte
            self.log(f"Cheat-Menü: {e.label}: {e.status}", "err")
            return None
        try:
            self._patch_dir()
        except Exception as ex:                     # noqa: BLE001
            self.log(f"Cheat-Menü: {ex}", "err")
            return None
        return e

    def _patch_dir(self):
        app = self.win.app
        if not getattr(app, "PATCH_DIR", None):
            raise RuntimeError("kein Projekt/Patch-Ordner aktiv - im Hauptfenster erst ein Projekt öffnen (ORDNER)")
        return app.PATCH_DIR

    def _get_code(self, progress=None):
        """Spiel-Code fuer die Instruktionssuche: dump.bin des Spielordners, sonst live von der Konsole (einmal, dann gemerkt)."""
        import ue_instr as U
        proj = getattr(self._uelive(), "proj", None)
        key = (id(proj), getattr(getattr(self.win.app, "backend", None), "pid", None))
        if self._code is not None and self._code[0] == key:
            return self._code[1], self._code[2]
        dis = getattr(proj, "dis", None) or U.get_disasm()
        if proj is not None and getattr(proj, "dm", None) is not None:
            code = CV.code_from_project(proj)
        else:
            if self.win.client is None:
                raise CV.CaveError("Nicht verbunden und kein dump.bin im Spielordner - im Hauptfenster VERBINDEN")
            self.win.ui(lambda: self.log("Cheat-Menü: kein dump.bin - lese den Spiel-Code von der Konsole (kann einen Moment dauern) ...", "info"))
            code = CV.code_from_console(self.win.client, self.win.app.IMAGE_BASE, progress=progress)
        self._code = (key, code, dis)
        return code, dis

    def _scan_progress(self, done, total):
        pct = int(100 * done / max(total, 1))
        self.win.ui(lambda: self.v_info.set(f"Suche im Spiel-Code ... {pct} %"))

    def _find(self, e, then):
        """Treffer zum Eintrag suchen (Hintergrund) und dann then(code, dis, opts) aufrufen."""
        self._busy = True
        self.v_info.set(f"Suche im Spiel-Code nach Schreibzugriffen auf: {e.label}")

        def job():
            code, dis = self._get_code(self._scan_progress)
            return code, dis, CV.find_options(self.menu, e, code, dis, progress=self._scan_progress)

        def ok(res):
            self._busy = False
            self.v_info.set("")
            then(*res)

        def fail(ex):
            self._busy = False
            msg = str(ex) or ex.__class__.__name__
            self.v_info.set("Fehler: " + msg)
            self.log("Cheat-Menü: " + msg, "err")

        self.bg(job, ok, fail)

    def _value_text(self, e, mode):
        """Wert fuer 'festschreiben': das Wert-Feld, sonst nachfragen (None = abgebrochen)."""
        text = self.v_val.get().strip()
        if mode != "force":
            return ""
        if e.kind == "toggle":
            return CV.entry_value(e)
        if not text or text.lower() in CV.AUTO_TEXT:
            text = simpledialog.askstring("Wert festschreiben", f"Welche Zahl soll {e.label} bekommen?", parent=self.win)
            if text is None or not text.strip():
                return None
        return text.strip()

    def cave_auto(self):
        """Rechtsklick: die beste Instruktion suchen und die passende Cave bauen."""
        e = self._cave_target()
        if e is None:
            return

        def then(code, dis, opts):
            if not opts:
                return self.log(NO_HIT + e.label, "warn")
            opt, mode = CV.pick_best(e, opts)
            if opt is None:
                return self.log(f"Cheat-Menü: {len(opts)} Treffer, aber keine passende Cave baubar - "
                                "'Treffer selbst wählen' zeigt die Gründe (NOP geht immer)", "warn")
            value = self._value_text(e, mode)
            if value is None:
                return self.log("Cheat-Menü: abgebrochen", "info")
            instr, _note = CV.describe(opt)
            if not messagebox.askyesno(
                    "Code Cave bauen",
                    f"{e.label}\n\nCave: {CV.MODE_TEXT[mode]}\nInstruktion: {instr}\nAdresse: +{opt.hit.rva:#x}\n\n"
                    "Achtung: gilt für ALLE Objekte, die diesen Code benutzen (auch Gegner).\n"
                    f"Speichern in:\n{self._patch_dir()}", parent=self.win):
                return
            self.build_cave(e, opt, mode, value, code, dis)

        self._find(e, then)

    def cave_pick(self):
        """Rechtsklick: alle Treffer zeigen; Treffer und Art der Cave selbst waehlen."""
        e = self._cave_target()
        if e is None:
            return

        def then(code, dis, opts):
            if not opts:
                return self.log(NO_HIT + e.label, "warn")
            CavePickDialog(self, e, opts, code, dis)

        self._find(e, then)

    def build_cave(self, e, opt, mode, value, code, dis, done=None):
        """Cave bauen und als .reapproj im Patch-Ordner ablegen (Hintergrund), dann Patch-Liste neu laden."""
        try:
            pdir = self._patch_dir()
        except Exception as ex:                     # noqa: BLE001
            return self.log(f"Cheat-Menü: {ex}", "err")
        self._busy = True

        def job():
            patch = CV.build_patch(e, opt, mode, code, dis, value=value,
                                   log=lambda m: self.win.ui(lambda: self.log(m, "warn")))
            return patch["name"], CV.save_patch(pdir, patch)

        def ok(res):
            self._busy = False
            name, fn = res
            try:
                self.win.app.load_patches()
            except Exception as ex:                 # noqa: BLE001
                self.log(f"Patch-Liste nicht neu geladen: {ex}", "warn")
            self.log(f"Cheat-Menü: Cave gespeichert: {fn} - im Hauptfenster aktivieren", "ok")
            if done:
                done(name, fn)

        def fail(ex):
            self._busy = False
            self.log(f"Cheat-Menü: {ex}", "err")

        self.bg(job, ok, fail)

    # -- Festhalten -----------------------------------------------------------------------------
    def _tick(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:  # noqa: BLE001
            return
        self.after(TICK_MS, self._tick)
        menu = self.menu
        if menu is None or self._busy or not len(menu.freezer) or self.win.client is None:
            return
        self._n += 1
        self._busy = True

        def job():
            return menu.tick()

        def done(msg):
            self._busy = False
            if msg:
                self.log("Cheat-Menü: " + msg, "err")
                self.v_info.set(msg)
                self._refresh()

        def err(e):
            self._busy = False
            self.log(f"Cheat-Menü Festhalten: {e}", "err")

        self.bg(job, done, err)


class CavePickDialog(tk.Toplevel):
    """Liste aller Treffer eines Eintrags; Treffer und Art der Cave waehlen und bauen."""

    def __init__(self, tab, e, opts, code, dis):
        super().__init__(tab.win)
        self.tab, self.e, self.opts, self.code, self.dis = tab, e, opts, code, dis
        self.title(f"Code Cave bauen - {e.label}")
        self.configure(bg=BG)
        self.geometry("920x560")
        self.transient(tab.win)
        self.v_mode = tk.StringVar()
        self.v_value = tk.StringVar(value=tab.v_val.get().strip() or CV.entry_value(e))
        self._rev = {text: key for key, text in CV.MODE_TEXT.items()}

        label(self, f"{len(opts)} Instruktion(en) im Spiel-Code schreiben diesen Wert: {e.label}", dim=False
              ).pack(anchor="w", padx=12, pady=(10, 2))
        label(self, "Treffer wählen, Art der Cave einstellen, CAVE BAUEN. Die oberste Zeile passt am wahrscheinlichsten. "
                    "Die Cave gilt für ALLE Objekte, die diesen Code benutzen (auch Gegner).", dim=True
              ).pack(anchor="w", padx=12)
        mid = tk.Frame(self, bg=BG)
        mid.pack(fill="both", expand=True, padx=12, pady=6)
        self.tv = tree(mid, [("score", "SCORE"), ("rva", "ADRESSE"), ("insn", "INSTRUKTION"), ("can", "CAVE MÖGLICH"),
                             ("note", "HINWEIS")], [60, 90, 330, 230, 170], height=14)
        with_scroll(mid, self.tv)
        for i, o in enumerate(opts):
            instr, note = CV.describe(o)
            can = ", ".join(_tr(CV.MODE_TEXT[m]) for m in o.possible if m != "nop") or _tr("nur NOP")
            self.tv.insert("", "end", iid=str(i), values=(f"{o.hit.score:.1f}", f"{o.hit.rva:#x}", instr, can, _tr(note)))
        if opts:
            self.tv.selection_set("0")
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self._on_pick())

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=4)
        label(bar, "Art").pack(side="left")
        self.cb = ttk.Combobox(bar, textvariable=self.v_mode, values=tuple(CV.MODE_TEXT.values()), width=34,
                               state="readonly")
        self.cb.pack(side="left", padx=6)
        label(bar, "Wert (nur bei 'festschreiben')").pack(side="left", padx=(10, 0))
        entry(bar, self.v_value, 10).pack(side="left", padx=6)
        self.lbl = label(self, "", dim=True)
        self.lbl.pack(anchor="w", padx=12)
        bar2 = tk.Frame(self, bg=BG)
        bar2.pack(fill="x", padx=12, pady=(4, 10))
        button(bar2, "CAVE BAUEN", self.build, accent=True).pack(side="left", padx=2)
        button(bar2, "IM DISASSEMBLER ZEIGEN", self.goto).pack(side="left", padx=2)
        button(bar2, "SCHLIESSEN", self.destroy).pack(side="right", padx=2)
        self._on_pick()

    def _sel(self):
        sel = self.tv.selection()
        if not sel:
            return None
        try:
            return self.opts[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def _on_pick(self):
        o = self._sel()
        if o is None:
            return
        mode = o.best(CV.default_modes(self.e)) or "nop"
        self.v_mode.set(CV.MODE_TEXT[mode])
        bad = [f"{_tr(CV.MODE_TEXT[m])}: {_tr(why)}" for m, (ok, why) in o.modes.items() if not ok and m != "nop"]
        self.lbl.configure(text=(_tr("Nicht möglich - ") + "  |  ".join(bad)) if bad else "")

    def goto(self):
        o = self._sel()
        if o is not None:
            self.tab.win.goto_disasm(self.tab.win.app.IMAGE_BASE + o.hit.rva)

    def build(self):
        o = self._sel()
        if o is None:
            return
        mode = self._rev.get(self.v_mode.get(), "nop")
        if mode == "force" and not self.v_value.get().strip():
            return self.tab.log("Cheat-Menü: bei 'Wert festschreiben' eine Zahl eintragen", "err")
        if not o.modes[mode][0]:
            return self.tab.log(f"Cheat-Menü: {CV.MODE_TEXT[mode]}: {o.modes[mode][1]}", "err")
        self.tab.build_cave(self.e, o, mode, self.v_value.get().strip(), self.code, self.dis)
