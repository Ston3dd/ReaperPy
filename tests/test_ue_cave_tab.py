"""Test: Tab UNREAL > CAVEMAKER - Cheat-Menü-Eintrag -> beste Instruktion -> geprüfter Hook in der SAMMLUNG -> TEST AN/AUS am
(simulierten) Speicher mit echtem Maschinencode -> ins Projekt.  Ohne Display, ohne Konsole."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E402,E702
import cave_world as W  # noqa: E402
import test_cheatmenu_cave as TC  # noqa: E402
import test_gui_cheatmenu_cave as GC  # noqa: E402
from test_gui_smoke import FakeWin  # noqa: E402

import tkinter.messagebox as mb  # noqa: E402


@unittest.skipUnless(TC.HAVE and W.TOOLCHAIN, "Toolchain fehlt")
class UeCaveTabFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TC.Real.setUpClass()
        cls.code, cls.dis = TC.Real.code, TC.Real.dis

    def setUp(self):
        import tools_ue_cave_gui as G
        self.b = W.GasBackend()
        self.b.client = object()
        self.b.put(self.b.base, self.code["buf"])                       # der Spiel-Code liegt ausführbar bei Image-Basis
        self.w = FakeWin()
        self.w.app.IMAGE_BASE = self.b.base
        self.w.app.backend = self.b
        self.w.app.added = []
        self.w.app.add_patch_from_file = lambda p: (self.w.app.added.append(p), p)[1]
        self.w.extra_tabs = [GC.UeLive(GC.Proj(self.code, self.dis))]
        self.t = G.UeCaveTab(None, self.w)
        self.out = tempfile.TemporaryDirectory()
        self.t._out_dir = lambda: self.out.name
        self.t._cfg = {}
        self.hp = TC.entry("UHealthComponent.Health", "value", "UHealthComponent", "Health", "float", 0x348, default="auto")
        self.t.menu = GC.FakeMenu([self.hp])
        self.t._fill()
        self._ask = mb.askyesno
        mb.askyesno = lambda *a, **k: True
        self.addCleanup(setattr, mb, "askyesno", self._ask)
        self.addCleanup(self.out.cleanup)

    def take_damage(self):
        """take_damage(this, damage) aus dem Test-Code: Health 100 - 30."""
        import ctypes
        obj = self.b.base + 0x2000
        self.b.put(obj + 0x348, bytes(ctypes.c_float(100.0)))
        addr = self.b.base + self.code["buf"].index(b"\x53\x48\x89\xfb")             # push rbx; mov rbx, rdi
        ok, val = W.run_isolated(lambda: self.b.call(addr, obj, 30.0))
        self.assertTrue(ok, val)
        return ctypes.c_float.from_buffer_copy(self.b.read(obj + 0x348, 4)).value

    def pick(self):
        iid = self.t.view.index(self.hp)
        self.t.tv.sel = (str(iid),)
        self.t._on_select()

    def test_cave_goes_to_the_collection_not_to_disk(self):
        self.pick()
        self.t.cave_auto()
        self.assertEqual(len(self.t.items), 1, self.w.logs)
        self.assertEqual(os.listdir(self.out.name), [])
        self.assertIn("kann nicht sinken", self.t.items[0].pd.name)

    def test_test_on_off_changes_the_game_and_project_gets_a_checked_card(self):
        self.assertEqual(self.take_damage(), 70.0)
        self.pick()
        self.t.cave_auto()
        self.t.coll.selection_set(["0"])
        self.t.test_on()
        self.assertIsNotNone(self.t.items[0].state, self.w.logs)
        self.assertEqual(self.take_damage(), 100.0)                   # Health kann nicht sinken
        self.t.test_off()
        self.assertEqual(self.take_damage(), 70.0)
        self.t.to_project()
        self.assertEqual(len(self.w.app.added), 1, self.w.logs)
        from reapatch import ReapPatch
        import patch_engine as PE
        rp = ReapPatch.load(self.w.app.added[0])
        self.assertTrue(PE.is_cave_patch(rp))
        self.assertIn("✔ 1 Hook(s) im Projekt", self.t.lbl_done.cget("text"))
        st = PE.apply_patch(self.b, rp, self.b.base + rp.origin_source[0])    # die Datei aus dem Projekt wirkt genauso
        self.assertEqual(self.take_damage(), 100.0)
        PE.deactivate_patch(self.b, rp, st)

    def test_same_instruction_twice_is_refused(self):
        self.pick()
        self.t.cave_auto()
        self.t.cave_auto()
        self.assertEqual(len([i for i in self.t.items if i]), 1)
        self.assertTrue(any("schon von" in m for k, m in self.w.logs if k == "err"), self.w.logs)

    def test_not_connected_is_reported(self):
        self.w.app.backend = None
        self.pick()
        self.t.cave_auto()
        self.assertEqual(self.t.items, [])
        self.assertTrue(any("Nicht verbunden" in m for k, m in self.w.logs), self.w.logs)


if __name__ == "__main__":
    unittest.main()
