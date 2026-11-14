"""tools_ue_cave_gui.py - Tab "CAVEMAKER" im Reiter UNREAL: wie das CHEAT-MENÜ, aber die gebaute Code Cave wird nicht sofort
gespeichert, sondern kommt in eine SAMMLUNG: dort prüfen, TEST AN / TEST AUS auf der Konsole und erst dann IN PROJEKT
ÜBERNEHMEN.

  1) Im Tab UE-LIVE den Spiel-Ordner laden und verbinden, Spielstand laden, hier MENÜ AUFBAUEN
  2) Eintrag anklicken -> CODE CAVE BAUEN (beste Instruktion) oder CAVE: TREFFER WÄHLEN (alle Schreibzugriffe zur Auswahl)
  3) Der Hook wird mit ReaperPys eigenem Parser und Cave-Assembler geprüft (cave_check.py) und landet in der SAMMLUNG
  4) TEST AN / TEST AUS direkt im Spiel, dann IN PROJEKT ÜBERNEHMEN: der Hook kommt als normale Karte ins Hauptfenster

Suche, Treffer-Bewertung und Cave-Bau sind die vom CHEAT-MENÜ (cheatmenu_cave.py / ue_instr.py) - dasselbe Format, das
ReaperPy ohnehin liest.
"""
import tkinter as tk

import cave_check as CC
import cheatmenu_cave as CV
from tools_cave_common import CaveCollectionMixin, DocPatch, Item, out_dir_for
from tools_cheatmenu_gui import CheatMenuTab
from tools_common import BG
from tools_unity_gui import _load_cfg, _save_cfg

COLLECTION_TARGET = "die SAMMLUNG unten (dort testen, dann IN PROJEKT ÜBERNEHMEN)"


class UeCaveTab(CaveCollectionMixin, CheatMenuTab):
    def __init__(self, parent, win):
        self._cfg = _load_cfg()
        super().__init__(parent, win)
        self.v_info.set("Erst im Tab UE-LIVE den Spiel-Ordner laden und verbinden, Spielstand laden, dann MENÜ AUFBAUEN. "
                        "Danach Eintrag wählen und CODE CAVE BAUEN.")
        lower = tk.Frame(self, bg=BG)
        lower.pack(side="bottom", fill="both", padx=8, pady=4)
        self._build_collection(lower)

    # Die Cave wird nicht in den Patch-Ordner geschrieben, sondern in die Sammlung gelegt
    def _patch_dir(self):
        return COLLECTION_TARGET

    def build_cave(self, e, opt, mode, value, code, dis, done=None):
        """Cave bauen, mit ReaperPys Parser/Assembler prüfen und in die SAMMLUNG legen (nichts wird gespeichert)."""
        try:
            be = self._backend()
        except ValueError as ex:
            return self.log(f"CAVEMAKER: {ex}", "err")
        hook = self.base + opt.hit.rva
        taken = self._used_hooks().get(hook)
        if taken:
            return self.log(f"CAVEMAKER: Diese Instruktion ({hook:#x}) wird schon von '{taken}' benutzt - zwei Caves an "
                            f"derselben Stelle gehen nicht. Bitte 'Treffer selbst wählen' und eine andere nehmen.", "err")
        self._busy = True

        def job():
            doc = CV.build_patch(e, opt, mode, code, dis, value=value,
                                 log=lambda m: self.win.ui(lambda: self.log(f"CAVEMAKER: {m}", "warn")))
            probs = CC.doc_problems(doc, be, hook)
            if probs:
                raise ValueError("ReaperPy würde diesen Hook nicht richtig verstehen: " + "; ".join(probs))
            return DocPatch(doc, hook, summary=CV.describe(opt)[0])

        def ok(pd):
            self._busy = False
            self._add_item(Item(pd, (e, mode, value)))
            self.log("CAVEMAKER: Gilt für ALLE Objekte, die diesen Code benutzen (auch Gegner). Erst TEST AN, im Spiel "
                     "prüfen, dann IN PROJEKT ÜBERNEHMEN.", "warn")
            if done:
                done(pd.name, "")

        def fail(ex):
            self._busy = False
            self.log(f"CAVEMAKER: {ex}", "err")

        self.bg(job, ok, fail)

    def _out_dir(self):
        proj = getattr(self._uelive(), "proj", None)
        return out_dir_for(getattr(proj, "name", ""), "Unreal-Cavemaker")

    def _save_cfg(self):
        _save_cfg(self._cfg)
