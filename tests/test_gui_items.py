"""Tab ITEMS (Fake-Tk, kein Display): ITEMS FINDEN -> Haken -> TRAINER SPEICHERN."""
import os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import cave_trainer as TR
import test_cave_trainer as TS
import test_gui_discover as GD
import test_ue_profile as TP
import ue_cavegen as CG
import ue_items as IT
import ue_quick as Q
from test_gui_smoke import FakeWin


class Client:
    def __init__(self, img): self.img = img
    def read_memory(self, a, n): return self.img.read(a, n)
    def get_maps(self): return self.img.maps


class T(unittest.TestCase):
    def setUp(self):
        import tools_items_gui as G
        self.lt = TP.LiveTable(); self.lt.setUp()
        sdk = TP.sdk_from(TP.GAME_A, [(1, 0x7000_1000, "DataTable", "DataTable /Game/Data/DT_Items.DT_Items")])
        self.live = GD.FakeLive(self.lt)
        self.ue = GD.FakeUeLive(sdk, None)
        self.img = TS.FakeImage()
        self.w = FakeWin(); self.w.client = Client(self.img); self.w.extra_tabs = [self.ue]
        self.w.app.IMAGE_BASE = self.img.BASE
        self.t = G.ItemsTab(None, self.w)
        self.tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.tmp, True)
        self.t._base_dir = lambda: os.path.join(self.tmp, "Spiel")
        self.patch(Q, "connect_live", lambda client, proj, log=print, cached=None: self.live)
        self.patch(CG, "find_impl", lambda read, base, thunk: self.img.impl)
        self.patch(IT, "hook_targets", lambda sdk, live, read, base: (self.img.pe, [self.img.slot], []))
        self.live.function_entry = lambda owner, name: (0x1234, None)
        self.live.build_index = lambda: None

    def patch(self, obj, name, val):
        old = getattr(obj, name); setattr(obj, name, val); self.addCleanup(setattr, obj, name, old)

    def last(self, widget): return widget.cget("text") if hasattr(widget, "cget") else widget._text

    def test_status_shows_missing_steps(self):
        self.ue.proj = type("P", (), {"sdk": None})(); self.w.client = None
        self.t.refresh_status()
        self.assertIn("Noch kein Spiel", self.t.lbl_game._text)
        self.assertIn("Nicht verbunden", self.t.lbl_conn._text)
        self.t.find_items()
        self.assertIn("Schritt", self.t.lbl_found._text)

    def test_find_items_picks_table_and_function(self):
        self.t.find_items()
        self.assertEqual(self.t.table[1], "DT_Items")
        self.assertIn(self.t.func.data["name"], ("GiveItem", "AddItem"))
        self.assertEqual([i["name"] for i in self.t.items], ["Item_Gold", "Item_Potion", "Item_Sword"])
        self.assertEqual(len(self.t.tv.rows), 3)
        self.assertIn("3 Items", self.t.lbl_found._text)
        self.assertIn("3 von 3", self.t.lbl_count._text)
        self.assertIn("3 Items in 1 Eintr", self.t.lbl_plan._text)

    def test_checks_search_and_category_buttons(self):
        self.t.find_items()
        self.t.set_visible(False)
        self.assertEqual(sum(self.t.on), 0)
        self.t.v_q.set("poti"); self.t.fill()
        self.assertEqual(len(self.t.tv.rows), 1)
        self.t.set_visible(True)
        self.assertEqual([i["name"] for i in self.t._chosen()], ["Item_Potion"])
        self.t.v_q.set(""); self.t.fill()
        self.t.tv.sel = ("0",); self.t.set_selected(True)
        self.assertEqual(len(self.t._chosen()), 2)

    def test_save_writes_a_project_with_all_checked_items(self):
        self.t.find_items()
        self.t.v_amount.set("500")
        self.t.save()
        self.assertEqual([m for k, m in self.w.logs if k == "err"], [])
        self.assertIn("Fertig", self.t.lbl_done._text)
        d = os.path.join(self.tmp, "Spiel", "Items")
        self.assertTrue(os.path.isdir(d))
        opts = TR.load_options(d)
        self.assertEqual(sum(len(o.rows) for o in opts), 3)
        self.assertEqual(opts[0].rows[0].amount, 500)

    def test_save_validation_messages(self):
        self.t.find_items()
        self.t.v_amount.set("viel"); self.t.save()
        self.assertIn("ganze Zahl", self.t.lbl_done._text)
        self.t.v_amount.set("5"); self.t.set_visible(False); self.t.save()
        self.assertIn("Items anhaken", self.t.lbl_done._text)
        self.t.set_visible(True); self.t.func = None; self.t.save()
        self.assertIn("Geben-Funktion", self.t.lbl_done._text)

    def test_many_items_make_several_projects(self):
        self.t.find_items()
        rows = [{"name": f"Item_Cat{k}_{i}", "fname_hex": f"{(k * 40 + i) % 250 + 1:02x}" + "00" * 7, "row_ptr": 0,
                 "values": {}} for k in range(12) for i in range(40)]
        self.t.set_items(rows, [])
        self.t.save()
        self.assertIn("mehrere Projekte", self.t.lbl_done._text)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "Spiel", "Items 1")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "Spiel", "Items 2")))


if __name__ == "__main__":
    unittest.main()
