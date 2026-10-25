"""GUI-Tests fuer den Tab CHEAT-MENUE (Fake-Tk, kein Display, keine Konsole)."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import test_cheatmenu as TM
import uesdk
from test_gui_smoke import FakeWin


class FakeUeLive:
    def __init__(self, sdk, live):
        self.proj = type("P", (), {"sdk": sdk, "name": "Testspiel"})()
        self.live = live


FakeUeLive.__name__ = "UeLiveTab"


class T(unittest.TestCase):
    def setUp(self):
        import tools_cheatmenu_gui as G
        self.mem = TM.Mem()
        _menu, self.mem = TM.make(self.mem)                           # Speicher der Fake-Welt fuellen
        self.w = FakeWin()
        self.w.client = self.mem
        self.live = TM.FakeLive()
        self.ue = FakeUeLive(uesdk.parse_header_text(TM.SDK_TEXT), self.live)
        self.w.extra_tabs = [self.ue]
        self.t = G.CheatMenuTab(None, self.w)

    def errs(self):
        return [m for k, m in self.w.logs if k == "err"]

    def pick(self, label_part):
        iid = next(i for i, e in enumerate(self.t.view) if label_part in e.label)
        self.t.tv.sel = (str(iid),)
        self.t._on_select()
        return self.t.view[iid]

    def test_build_without_sdk_explains(self):
        self.ue.proj.sdk = None
        self.t.build()
        self.assertTrue(any("kein SDK" in m for m in self.errs()))

    def test_build_lists_reachable_entries(self):
        self.t.build()
        rows = list(self.t.tv.rows.values())
        self.assertTrue(rows)
        self.assertIn("erreichbar", self.t.v_info.get())
        god = next(r for r in rows if "Unverwundbar" in r[2])
        self.assertEqual(god[0], "☐")
        self.assertEqual(god[3], "bereit")

    def test_toggle_switches_the_game_value_and_back(self):
        self.t.build()
        self.pick("Unverwundbar")
        self.t.toggle()
        self.assertEqual(self.mem.read_memory(TM.PAWN + 0x58, 1)[0] & 0b100, 0)
        self.assertEqual(next(r for r in self.t.tv.rows.values() if "Unverwundbar" in r[2])[0], "✔")
        self.t.toggle()
        self.assertTrue(self.mem.read_memory(TM.PAWN + 0x58, 1)[0] & 0b100)
        self.assertEqual(self.errs(), [])

    def test_value_entry_uses_typed_number(self):
        self.t.build()
        self.pick("Lauftempo")
        self.assertEqual(self.t.v_val.get(), "1200")                      # Vorgabe wird eingetragen
        self.t.v_val.set("900")
        self.t.set_value()
        self.assertEqual(TM.f32(self.mem, TM.COMP + 0x178), 900.0)

    def test_set_value_on_a_switch_is_refused_politely(self):
        self.t.build()
        self.pick("Unverwundbar")
        self.t.set_value()
        self.assertTrue(any("Wert-Eintrag" in m for m in self.errs()))

    def test_tick_holds_values_and_reports_a_character_change(self):
        self.t.build()
        self.pick("Lauftempo")
        self.t.v_val.set("900")
        self.t.set_value()
        self.mem.put(TM.COMP + 0x178, struct.pack("<f", 600.0))           # Spiel setzt zurueck
        self.t._tick()
        self.assertEqual(TM.f32(self.mem, TM.COMP + 0x178), 900.0)
        self.mem.put(TM.CTRL + 0x100, struct.pack("<Q", 0x3100_0000))     # Figur gewechselt
        self.t._tick()
        self.assertTrue(any("gewechselt" in m for m in self.errs()))
        self.assertEqual(next(r for r in self.t.tv.rows.values() if "Lauftempo" in r[2])[0], "☐")

    def test_all_off_restores_everything(self):
        self.t.build()
        self.pick("Unverwundbar"); self.t.toggle()
        self.pick("Lauftempo"); self.t.v_val.set("900"); self.t.set_value()
        self.t.all_off()
        self.assertTrue(self.mem.read_memory(TM.PAWN + 0x58, 1)[0] & 0b100)
        self.assertEqual(TM.f32(self.mem, TM.COMP + 0x178), 600.0)

    def test_without_menu_actions_say_what_to_do(self):
        self.t.toggle()
        self.assertTrue(any("erst einen Eintrag" in m for m in self.errs()))


if __name__ == "__main__":
    unittest.main()
