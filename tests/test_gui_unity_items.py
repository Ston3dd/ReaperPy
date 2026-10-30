"""Tab UNITY > ITEMS: Spiel -> ITEMS FINDEN -> TRAINER SPEICHERN (GUI ohne Display, Spiel-Speicher nachgebaut)."""
import json, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import test_unity_items as TU
import unity_items as U
from test_gui_smoke import FakeWin

BASE = 0x400000


class Client:
    def __init__(self, head):
        self.code = bytearray(b"\xCC" * 0x20000)
        self.code[0x1200:0x1200 + len(head)] = head
        self.code[0x1100:0x1102] = b"\x90\xC3"
        self.data = bytearray(0x10000)

    def read_memory(self, addr, n):
        for s, buf in ((BASE, self.code), (BASE + 0x20000, self.data)):
            if s <= addr and addr + n <= s + len(buf):
                return bytes(buf[addr - s:addr - s + n])
        raise OSError("unlesbar")

    def get_maps(self):
        return [(BASE, BASE + 0x20000, 5), (BASE + 0x20000, BASE + 0x30000, 3)]


class FakeUnity:
    def __init__(self, game):
        self.game = game
        self.picked = 0

    def pick_game(self):
        self.picked += 1

    def _ensure_base(self, client):
        return type("L", (), {"base": BASE})()


FakeUnity.__name__ = "UnityTab"


class T(unittest.TestCase):
    def setUp(self):
        import tools_unity_items_gui as G
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.game = TU.make_dump(self.tmp)
        self.game.title = "Testspiel"
        head = TU.asm_bytes("push rbp\nmov rbp, rsp\ncmp byte ptr [rip+0x4000], 0\njne 1f\nnop\n1: pop rbp\nret", self.tmp)
        self.w = FakeWin()
        self.w.client = Client(head)
        self.un = FakeUnity(self.game)
        self.w.extra_tabs = [self.un]
        self.t = G.UnityItemsTab(None, self.w)
        self.t._base_dir = lambda: os.path.join(self.tmp, "out")
        import tkinter.messagebox as mb
        self.mb, self.old = mb, mb.askyesno
        mb.askyesno = lambda *a, **k: True
        self.addCleanup(setattr, mb, "askyesno", self.old)

    def test_status_without_game(self):
        self.un.game = None
        self.t.refresh_status()
        self.assertIn("Noch kein Spiel", self.t.lbl_game._text)
        self.t.find_items()
        self.assertIn("Schritt", self.t.lbl_found._text)

    def test_find_items_selects_everything_automatically(self):
        self.t.find_items()
        self.assertEqual(self.t.enum.name, "ItemID")
        self.assertEqual(self.t.give.method.key, "Game.Inventory.AddItem")
        self.assertEqual(self.t.hook.method.key, "Game.Inventory.Update")
        self.assertEqual(len(self.t.items), 16)
        self.assertTrue(all(self.t.on))
        self.assertIn("Items aus der Liste", self.t.lbl_found._text)
        self.assertIn("Einträgen", self.t.lbl_plan._text)

    def test_filter_and_toggle(self):
        self.t.find_items()
        self.t.v_q.set("sword")
        self.t.fill()
        self.assertEqual(len(self.t.view), 3)
        self.t.set_visible(False)
        self.assertEqual(sum(self.t.on), 13)

    @unittest.skipUnless(TU.NATIVE, "braucht objdump fuer die Zerlegung")
    def test_save_writes_project(self):
        import ue_instr
        old = ue_instr.get_disasm
        ue_instr.get_disasm = lambda *a, **k: old(prefer="objdump")
        self.addCleanup(setattr, ue_instr, "get_disasm", old)
        import cave_trainer as TR
        old_cap = TR.capacity
        TR.capacity = lambda read, maps, base, log=print: {"code": 4000}
        self.addCleanup(setattr, TR, "capacity", old_cap)
        self.t.find_items()
        self.t.v_amount.set("999")
        self.t.save()
        self.assertTrue(self.t.out_dirs, self.t.lbl_done._text)
        out = self.t.out_dirs[0]
        files = sorted(os.listdir(out))
        self.assertIn(U.BASE_FILE, files)
        self.assertTrue(any(f.endswith("Potion.reapproj") or "Potion" in f for f in files), files)
        with open(os.path.join(out, U.SPEC_FILE), encoding="utf-8") as f:
            spec = json.load(f)
        self.assertEqual(spec["call"]["function"], "Game.Inventory.AddItem")
        self.assertEqual(spec["options"][0]["rows"][0]["amount"], 999)
        self.assertIn("Fertig", self.t.lbl_done._text)

    def test_bad_amount_and_no_items(self):
        self.t.find_items()
        self.t.v_amount.set("abc")
        self.t.save()
        self.assertIn("ganze Zahl", self.t.lbl_done._text)
        self.t.v_amount.set("5")
        self.t.set_visible(False)
        self.t.save()
        self.assertIn("Items anhaken", self.t.lbl_done._text)


if __name__ == "__main__":
    unittest.main()
