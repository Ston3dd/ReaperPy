"""GUI-Tests: Rechtsklick im Tab CHEAT-MENUE -> passende Code Cave bauen (Fake-Tk, echter Maschinencode, keine Konsole)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E402,E702
import cheatmenu as M
import cheatmenu_cave as CV
import test_cheatmenu_cave as TC
import ue_instr as U
from test_gui_smoke import FakeWin

import tkinter.messagebox as mb  # das Fake-Modul


class Proj:
    """Stand-in fuer GameProject mit Dump: code() liefert die Test-Code-Sicht."""
    def __init__(self, code, dis):
        self.dm, self.dis, self._code = object(), dis, code
        self.sdk = None
        self.name = "Testspiel"

    def code(self):
        return self._code


class UeLive:
    def __init__(self, proj):
        self.proj, self.live = proj, None


UeLive.__name__ = "UeLiveTab"


class FakeMenu:
    sdk = None
    freezer = ()

    def __init__(self, entries):
        self.entries = entries

    def _off(self, cls, member):
        return None


@unittest.skipUnless(TC.HAVE, "Toolchain fehlt")
class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TC.Real.setUpClass()
        cls.code, cls.dis = TC.Real.code, TC.Real.dis

    def setUp(self):
        import tools_cheatmenu_gui as G
        self.G = G
        self.dir = tempfile.mkdtemp()
        self.w = FakeWin()
        self.w.app.PATCH_DIR = self.dir
        self.w.app.reloaded = 0
        self.w.app.load_patches = lambda: setattr(self.w.app, "reloaded", self.w.app.reloaded + 1)
        self.w.extra_tabs = [UeLive(Proj(self.code, self.dis))]
        self.t = G.CheatMenuTab(None, self.w)
        self.hp = TC.entry("UHealthComponent.Health", "value", "UHealthComponent", "Health", "float", 0x348, default="auto")
        self.flag = TC.entry("ACharacter.bFlag", "toggle", "ACharacter", "bFlag", "bool", 0x150, on=False, off=True)
        self.t.menu = FakeMenu([self.hp, self.flag])
        self.t._fill()
        self.asked = []
        self._ask = mb.askyesno
        mb.askyesno = lambda *a, **k: (self.asked.append(a), True)[1]
        self.addCleanup(setattr, mb, "askyesno", self._ask)

    def pick(self, e):
        iid = self.t.view.index(e)
        self.t.tv.sel = (str(iid),)
        self.t._on_select()

    def logs(self, kind):
        return [m for k, m in self.w.logs if k == kind]

    def files(self):
        return sorted(f for f in os.listdir(self.dir) if f.endswith(".reapproj"))

    def test_right_click_menu_is_registered(self):
        self.assertTrue(hasattr(self.t, "cave_auto") and hasattr(self.t, "cave_pick"))

    def test_auto_builds_keep_cave_for_health(self):
        self.pick(self.hp)
        self.t.cave_auto()
        self.assertEqual(self.files(), ["UHealthComponent.Health - Wert kann nicht sinken.reapproj"])
        p = json.load(open(os.path.join(self.dir, self.files()[0]), encoding="utf-8"))
        self.assertEqual(p["Variables"][0]["newValue"], "jmp OriginTarget")
        self.assertEqual(self.w.app.reloaded, 1)
        self.assertTrue(any("Cave gespeichert" in m for m in self.logs("ok")))
        self.assertIn("Gegner", self.asked[0][1])                 # Warnung: gilt fuer alle Objekte
        self.assertFalse(self.t._busy)

    def test_auto_builds_force_cave_for_toggle(self):
        self.pick(self.flag)
        self.t.cave_auto()
        self.assertEqual(self.files(), ["ACharacter.bFlag _ 0 (Cave).reapproj"])

    def test_auto_declined_writes_nothing(self):
        mb.askyesno = lambda *a, **k: False
        self.pick(self.hp)
        self.t.cave_auto()
        self.assertEqual(self.files(), [])
        self.assertEqual(self.w.app.reloaded, 0)
        self.assertFalse(self.t._busy)

    def test_auto_on_a_decrement_falls_back_to_force_and_asks_for_a_number(self):
        import tkinter.simpledialog as sd
        old = sd.askstring
        self.addCleanup(setattr, sd, "askstring", old)
        ammo = TC.entry("UWeaponComponent.CurrentAmmo", "value", "UWeaponComponent", "CurrentAmmo", "int32", 0x200,
                        default="auto")
        self.t.menu.entries.append(ammo)
        self.t._fill()
        opt, mode = CV.pick_best(ammo, CV.find_options(self.t.menu, ammo, self.code, self.dis))
        self.assertEqual((opt.hit.ins.mnem, mode), ("sub", "force"))      # 'sub [..], reg': 'nicht sinken' nicht baubar
        self.assertFalse(opt.modes["keep"][0])
        self.pick(ammo)
        asked = []
        sd.askstring = lambda *a, **k: (asked.append(a), None)[1]          # Abbruch im Zahlen-Dialog
        self.t.cave_auto()
        self.assertEqual((len(asked), self.files()), (1, []))
        self.assertTrue(any("abgebrochen" in m for k, m in self.w.logs))
        self.assertFalse(self.t._busy)
        sd.askstring = lambda *a, **k: "42"
        self.t.cave_auto()
        self.assertEqual(self.files(), ["UWeaponComponent.CurrentAmmo _ 42 (Cave).reapproj"])
        # steht im Wert-Feld schon eine Zahl, wird nicht gefragt
        sd.askstring = lambda *a, **k: self.fail("darf nicht fragen")
        self.t.v_val.set("17")
        self.assertEqual(self.t._value_text(ammo, "force"), "17")
        self.assertEqual(self.t._value_text(ammo, "keep"), "")

    def test_no_hit_explains(self):
        e = TC.entry("UX.Nothing", "value", "UX", "Nothing", "float", 0x999, default="auto")
        self.t.menu.entries.append(e)
        self.t._fill()
        self.pick(e)
        self.t.cave_auto()
        self.assertEqual(self.files(), [])
        self.assertTrue(any("Keine Instruktion schreibt diesen Wert" in m and m.endswith("UX.Nothing") for m in self.logs("warn")))

    def test_small_offset_is_a_clear_error(self):
        e = TC.entry("AActor.CustomTimeDilation", "value", "AActor", "CustomTimeDilation", "float", 0x60, default="1.5")
        self.t.menu.entries.append(e)
        self.t._fill()
        self.pick(e)
        self.t.cave_auto()
        self.assertTrue(any("+0x60" in m for m in self.logs("err")))
        self.assertFalse(self.t._busy)

    def test_without_project_folder_says_what_to_do(self):
        self.w.app.PATCH_DIR = None
        self.pick(self.hp)
        self.t.cave_auto()
        self.assertTrue(any("Projekt" in m for m in self.logs("err")))
        self.assertEqual(self.files(), [])

    def test_without_selection_and_menu(self):
        self.t.cave_auto()
        self.assertTrue(any("erst einen Eintrag" in m for m in self.logs("err")))
        self.t.menu = None
        self.t.cave_auto()
        self.assertTrue(any("erst" in m for m in self.logs("err")))

    def test_busy_blocks_double_start(self):
        self.pick(self.hp)
        self.t._busy = True
        self.t.cave_auto()
        self.assertEqual(self.files(), [])
        self.assertTrue(any("warten" in m for m in self.logs("warn")))

    def test_pick_dialog_builds_chosen_mode(self):
        self.pick(self.hp)
        self.t.cave_pick()                                        # Dialog (Fake) wird erzeugt, ohne Fehler
        opts = CV.find_options(self.t.menu, self.hp, self.code, self.dis)
        d = self.G.CavePickDialog(self.t, self.hp, opts, self.code, self.dis)
        d.tv.sel = ("0",)
        d._on_pick()
        self.assertEqual(d.v_mode.get(), CV.MODE_TEXT["keep"])
        d.v_mode.set(CV.MODE_TEXT["nop"])
        d.build()
        self.assertEqual(self.files(), ["UHealthComponent.Health - Schreibzugriff abschalten (NOP).reapproj"])
        d.v_mode.set(CV.MODE_TEXT["force"])
        d.v_value.set("")
        d.build()
        self.assertTrue(any("Zahl eintragen" in m for m in self.logs("err")))
        d.v_value.set("500")
        d.build()
        self.assertIn("UHealthComponent.Health _ 500 (Cave).reapproj", self.files())

    def test_pick_dialog_refuses_impossible_mode_with_reason(self):
        self.pick(self.flag)
        opts = CV.find_options(self.t.menu, self.flag, self.code, self.dis)
        d = self.G.CavePickDialog(self.t, self.flag, opts, self.code, self.dis)
        d.tv.sel = ("0",)
        d.v_mode.set(CV.MODE_TEXT["keep"])
        d.build()
        self.assertTrue(any("Schalter" in m for m in self.logs("err")))
        self.assertEqual(self.files(), [])

    def test_code_is_read_only_once(self):
        calls = []
        orig = CV.code_from_project
        CV.code_from_project = lambda p: (calls.append(1), orig(p))[1]
        self.addCleanup(setattr, CV, "code_from_project", orig)
        self.pick(self.hp)
        self.t.cave_auto()
        self.t.cave_auto()
        self.assertEqual(len(calls), 1)

    def test_live_fallback_without_dump(self):
        self.w.extra_tabs = [UeLive(type("P", (), {"dm": None, "dis": self.dis, "sdk": None})())]
        self.w.client = None
        self.pick(self.hp)
        self.t.cave_auto()
        self.assertTrue(any("VERBINDEN" in m for m in self.logs("err")))
        mem = bytes(self.code["buf"])
        self.w.app.IMAGE_BASE = 0x400000
        self.w.client = TC.FakeClient([(0x400000, 0x400000 + len(mem), 5)], mem)
        self.t._code = None
        self.t.cave_auto()
        self.assertEqual(self.files(), ["UHealthComponent.Health - Wert kann nicht sinken.reapproj"])


if __name__ == "__main__":
    unittest.main()
