"""tools_unity_cheatmenu_gui.py - Tab "CHEAT-MENUE" im Reiter UNITY: Schalter und Werte aus dem dump.cs, wie bei Unreal.

  1) Im Tab UNITY MANUELL (oder ITEMS) den Spiel-Ordner laden, mit der Konsole verbinden, Spielstand laden
  2) MENUE AUFBAUEN - Methoden-Patches (Schaden, Geld ausgeben ...) und Felder (Health, Gold, Stamina, EXP ...)
  3) Eintrag anklicken -> AN / AUS (Doppelklick); bei Zahlen vorher den Wert eintippen
  4) CODE CAVE BAUEN (Felder): sucht im Spiel-Code die Instruktion, die das Feld schreibt, und legt die Cave als .reapproj ab;
     PATCH SPEICHERN (Methoden): fertiger .reapproj-Patch
Logik: unity_cheatmenu.py; Cave-Bau und Dialoge kommen aus tools_cheatmenu_gui.py (gleiche Bedienung wie bei Unreal).
"""

import cheatmenu_cave as CV
import unity_cheatmenu as UM
import values_auto as VA
from tools_cheatmenu_gui import TICK_MS, CheatMenuTab
from tools_common import button


class UnityCheatMenuTab(CheatMenuTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.v_info.set("Erst im Tab UNITY MANUELL den Spiel-Ordner laden und verbinden, Spielstand laden, dann MENUE AUFBAUEN.")
        self.v_hold.set(True)
        bar = self._bar
        button(bar, "PATCH SPEICHERN", self.save_patch).pack(side="left", padx=(8, 2))

    # -- Zugriff auf UNITY ---------------------------------------------------------------------------
    def _unity(self):
        for t in getattr(self.win, "extra_tabs", []):
            if t.__class__.__name__ == "UnityTab":
                return t
        return None

    def _game(self):
        return getattr(self._unity(), "game", None)

    # -- Cave fuer ein beliebiges Feld (aus dem Tab MANUELL) ------------------------------------------------
    def cave_for_field(self, target, amount_text):
        """MANUELL: ausgewaehltes Feld + feste Menge (z. B. 999) -> Eintrag 'Manuell' im Menue, dann die Cave bauen."""
        un = self._unity()
        game, client = self._game(), self.win.client
        if game is None or client is None or un is None:
            return self.log("Cheat-Menü: erst Spiel-Ordner laden und verbinden (Tab MANUELL)", "err")
        try:
            e = UM.entry_from_target(game, target, amount_text)
        except UM.MenuError as ex:
            return self.log(f"Cheat-Menü: {ex}", "err")
        if self.menu is None:
            self.menu = UM.UnityMenu(game, client, getattr(un, "live", None), entries=[], log=lambda m: self.log(m, "warn"))
        old = self.menu.by_key.get(e.key)
        if old is not None:
            self.menu.entries.remove(old)
        self.menu.entries.insert(0, e)
        self.menu.by_key[e.key] = e
        self._fill()
        self.tv.selection_set("0" if self.view and self.view[0] is e else str(self.view.index(e)))
        self.v_val.set(e.default)
        self.v_hold.set(True)
        self.log(f"Cheat-Menü: baue Cave für {e.label} = {e.default} ...", "info")
        self.cave_auto()

    # -- Aufbau --------------------------------------------------------------------------------------
    def build(self):
        if self._busy:
            return
        game, un, client = self._game(), self._unity(), self.win.client
        if game is None:
            self.log("Cheat-Menü: kein Spiel geladen - im Tab UNITY MANUELL den SPIEL-ORDNER wählen", "err")
            return
        if client is None:
            self.log("Cheat-Menü: nicht verbunden - im Hauptfenster VERBINDEN", "err")
            return
        self._busy = True
        self.v_info.set("Baue das Menü auf (Methoden und Felder aus dem Dump) …")

        def job():
            if self.menu is not None:
                self.menu.release_all()
            live = un._ensure_base(client)
            try:
                live.set_maps(un._maps(client))
            except Exception:  # noqa: BLE001
                pass
            return UM.UnityMenu(game, client, live, log=lambda m: self.win.ui(lambda: self.log(m, "warn")))

        def ok(menu):
            self._busy = False
            self.menu = menu
            self._fill()
            n_p = sum(1 for e in menu.entries if e.kind == "patch")
            self.v_info.set(f"{len(menu.entries)} Einträge ({n_p} Methoden, {len(menu.entries) - n_p} Felder). "
                            "Eintrag anklicken -> AN / AUS.")
            self.log(f"Unity Cheat-Menü: {len(menu.entries)} Einträge", "ok" if menu.entries else "err")

        def fail(e):
            self._busy = False
            msg = str(e) or e.__class__.__name__
            self.v_info.set("Fehler: " + msg)
            self.log("Cheat-Menü: " + msg, "err")

        self.bg(job, ok, fail)

    @staticmethod
    def _row(e):
        if not e.ok:
            return ("✗", e.cat, e.label, e.status)
        kind = "Methode" if e.kind == "patch" else "Feld"
        if e.active:
            return ("✔", e.cat, e.label, "AN" + ("  (festgehalten)" if e.held else ""))
        extra = f"  (Vorgabe {e.default})" if e.kind == "field" and not e.toggle else ""
        return ("☐", e.cat, e.label, f"bereit - {kind}{extra}" + (f"  ⚠ {e.warn}" if e.warn else ""))

    def _on_select(self):
        e = self._selected()
        if e is None:
            return
        if e.kind == "field" and not e.toggle:
            self.v_val.set(e.default)
        self.v_note.set(e.warn or "")

    # -- Schalten ------------------------------------------------------------------------------------
    def toggle(self):
        e = self._selected()
        if e is None:
            return self.log("Cheat-Menü: erst einen Eintrag anklicken", "err")
        if not e.ok:
            return self.log(f"Cheat-Menü: {e.label}: {e.status}", "err")
        menu, text = self.menu, self.v_val.get().strip() or e.default
        if e.active or e.kind == "patch" or e.toggle:
            self._run(lambda: (menu.toggle(e), 0)[1], lambda _n: f"{e.label}: {'AN' if e.active else 'AUS'}")
        else:
            self._run(lambda: menu.set_on(e, text), lambda _n: f"{e.label} = {text}")

    def set_value(self):
        e = self._selected()
        if e is None or e.kind != "field" or e.toggle:
            return self.log("Cheat-Menü: ein Zahlen-Feld anklicken (nicht Methode oder Schalter)", "err")
        menu, text = self.menu, self.v_val.get().strip() or e.default
        self._run(lambda: menu.write_field(e, text, self.v_hold.get()), lambda _n: f"{e.label} = {text}")

    def all_off(self):
        if self.menu is None:
            return
        menu = self.menu
        self._run(lambda: (menu.release_all(), 0)[1], lambda _n: "Cheat-Menü: alles aus, Originalwerte zurückgeschrieben")

    # -- Code Cave / Patch ------------------------------------------------------------------------------
    def _cave_target(self):
        e = self._selected()
        if e is None:
            self.log("Cheat-Menü: erst einen Eintrag anklicken", "err")
            return None
        if self.menu is None:
            self.log("Cheat-Menü: erst MENÜ AUFBAUEN", "err")
            return None
        if self._busy:
            self.log("Cheat-Menü: bitte kurz warten, es läuft noch etwas", "warn")
            return None
        try:
            ce = UM.cave_entry(e)
            self._patch_dir()
        except Exception as ex:                     # noqa: BLE001
            self.log(f"Cheat-Menü: {ex}", "err")
            return None
        return ce

    def _get_code(self, progress=None):
        import ue_instr as U
        un = self._unity()
        base = getattr(un, "mod_base", None) or getattr(self.menu.live, "base", None)
        if not base:
            raise CV.CaveError("Modul-Basis unbekannt - im Tab MANUELL einmal ein Feld anklicken (Instanzen laden), dann nochmal")
        key = (base, id(self.menu))
        if self._code is not None and self._code[0] == key:
            return self._code[1], self._code[2]
        if self.win.client is None:
            raise CV.CaveError("Nicht verbunden - im Hauptfenster VERBINDEN")
        self.win.ui(lambda: self.log("Cheat-Menü: lese den Spiel-Code von der Konsole (kann einen Moment dauern) ...", "info"))
        code = CV.code_from_console(self.win.client, base, progress=progress)
        dis = U.get_disasm()
        self._code = (key, code, dis)
        return code, dis

    def save_patch(self):
        e = self._selected()
        if e is None or self.menu is None:
            return self.log("Cheat-Menü: erst MENÜ AUFBAUEN und einen Methoden-Eintrag anklicken", "err")
        if e.kind != "patch":
            return self.log("Cheat-Menü: PATCH SPEICHERN gilt für Methoden - bei Feldern CODE CAVE BAUEN", "err")
        try:
            pdir = self._patch_dir()
        except Exception as ex:                     # noqa: BLE001
            return self.log(f"Cheat-Menü: {ex}", "err")
        menu = self.menu
        un = self._unity()

        def job():
            base = getattr(un, "mod_base", None) or menu.live.base
            doc = VA.unity_patch_doc(e.cand, base, menu.client.read_memory)
            return CV.save_patch(pdir, doc)

        def ok(fn):
            self._busy = False
            try:
                self.win.app.load_patches()
            except Exception as ex:                 # noqa: BLE001
                self.log(f"Patch-Liste nicht neu geladen: {ex}", "warn")
            self.log(f"Cheat-Menü: Patch gespeichert: {fn} - im Hauptfenster aktivieren", "ok")

        def fail(ex):
            self._busy = False
            self.log(f"Cheat-Menü: {ex}", "err")

        self._busy = True
        self.bg(job, ok, fail)

    # -- Festhalten -----------------------------------------------------------------------------------
    def _tick(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:  # noqa: BLE001
            return
        self.after(TICK_MS, self._tick)
        menu = self.menu
        if menu is None or self._busy or not any(e.held and e.active for e in menu.entries) or self.win.client is None:
            return
        self._busy = True

        def done(msgs):
            self._busy = False
            if msgs:
                self.log("Cheat-Menü: " + "; ".join(msgs), "err")
                self._refresh()

        def err(e):
            self._busy = False
            self.log(f"Cheat-Menü Festhalten: {e}", "err")

        self.bg(menu.tick, done, err)
