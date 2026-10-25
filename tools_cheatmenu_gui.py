"""tools_cheatmenu_gui.py - Tab "CHEAT-MENUE": Schalter und Werte fuer die Spielfigur, aus dem SDK erzeugt.

Funktioniert auch in Shipping-Builds ohne CheatManager: es werden nur gewoehnliche Speicherwerte der Figur
geschrieben (Engine-Werte wie bCanBeDamaged / MovementMode / MaxWalkSpeed sowie Leben/Ausdauer/Geld aus dem SDK).
  1) Im Tab UE-LIVE den SPIEL-ORDNER laden und verbinden, Spielstand laden (nicht Hauptmenue)
  2) MENUE AUFBAUEN - jeder Eintrag zeigt, ob er an deiner Figur erreichbar ist (✔) oder warum nicht (✗)
  3) Eintrag anklicken -> AN / AUS (Doppelklick geht auch); bei Werten vorher die Zahl eintippen
Logik: cheatmenu.py (testbar ohne Oberflaeche und Konsole).
"""
import tkinter as tk

import cheatmenu as M
from tools_common import BG, TEXT_DIM, BaseTab, button, entry, label, tree, with_scroll

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
        self.tv = tree(mid, [("on", "AN"), ("cat", "KATEGORIE"), ("label", "EINTRAG"), ("val", "WERT / STATUS")],
                       [50, 120, 380, 360], height=16, anchors={"on": "center"})
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
