"""Tab ITEMS (Fake-Tk, kein Display): ITEMS FINDEN -> Haken -> TRAINER SPEICHERN."""
import os, shutil, struct, sys, tempfile, unittest
from pathlib import Path

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
    moved = 0
    def __init__(self, img): self.img = img
    def get_maps_named(self):
        return [(s + self.moved, e + self.moved, p, "eboot.bin") for s, e, p in self.img.maps[:1]] + \
               [(s, e, p, "anon:x") for s, e, p in self.img.maps[1:]]
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


class BaseCheck(T):
    def test_matching_base_is_fine(self):
        self.t.find_items()
        self.assertEqual(self.t.basecheck.status, "ok")

    def test_wrong_base_is_reported_blocks_saving_and_can_be_adopted(self):
        self.w.client.moved = 0x10000
        applied = []
        app = self.w.app
        app.imgbase_var = type("V", (), {"set": lambda s, v: applied.append(v)})()
        app.apply_imgbase = lambda: applied.append("apply")
        self.t.find_items()
        self.assertEqual(self.t.basecheck.status, "shifted")
        self.assertIn("0x410000", self.t.lbl_found._text)
        self.t.save()
        self.assertIn("BASIS ÜBERNEHMEN", self.t.lbl_done._text)
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "Spiel", "Items")))
        self.t.adopt_base()
        self.assertEqual(applied, ["0x410000", "apply"])
        self.assertEqual(self.t.basecheck.status, "ok")


    def test_save_shows_preview_and_writes_only_after_yes(self):
        self.t.find_items()
        seen = []
        self.t._ask_preview = lambda text: seen.append(text) or False
        self.t.save()
        self.assertEqual(len(seen), 1)
        self.assertIn("Region 0x400000-0x410000 (r-x)", seen[0])
        self.assertIn("Cave:", seen[0])
        self.assertIn("nichts geschrieben", self.t.lbl_done._text)
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "Spiel", "Items")))
        self.assertFalse(self.t._busy)
        self.t._ask_preview = lambda text: True
        self.t.save()
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "Spiel", "Items", "_trainer_spec.json")))
        self.assertIn("Fertig", self.t.lbl_done._text)


class Portability(T):
    """Fremder / alter Trainer: pruefen und an die Item-Nummern des eigenen Spiels anpassen."""

    def build(self):
        self.t.find_items()
        self.t.save()
        return os.path.join(self.tmp, "Spiel", "Items")

    def test_check_passes_for_own_trainer(self):
        d = self.build()
        self.t._check_dir(d)
        txt = self.t.lbl_done._text
        self.assertIn("Passt zur Spielversion", txt)
        self.assertIn("Alle 3 Item-Nummern stimmen", txt)

    def test_other_console_other_item_numbers_are_detected_and_adapted(self):
        d = self.build()
        for it in self.t.items:                                   # andere Konsole: andere FName-Nummern
            it["fname"] = bytes([x ^ 0x5A for x in it["fname"]])
        asked = []
        self.t._ask_adapt = lambda text: asked.append(text) or True
        self.t._check_dir(d)
        self.assertEqual(len(asked), 1)
        self.assertIn("Angepasst: 3 Item-Nummern", self.t.lbl_done._text)
        ok, changed, missing = TR.compare_fnames(d, self.t._live_names())       # jetzt stimmen sie
        self.assertEqual((len(ok), changed, missing), (3, [], []))
        opts = TR.load_options(d)
        want = self.t.items[0]["fname"]
        self.assertEqual(opts[0].rows[0].fname, want)
        self.assertEqual(opts[0].rows[0].spec.args[0]["value"], want)           # der echte Aufruf-Wert

    def test_other_game_version_is_reported_and_not_adapted(self):
        d = self.build()
        self.img.write(self.img.impl, b"\x90" * 32)
        self.t._ask_adapt = lambda text: self.fail("darf nicht anbieten, anzupassen")
        self.t._check_dir(d)
        self.assertIn("ANDERE Spielversion", self.t.lbl_done._text)

    def test_adapt_while_base_active_gives_plain_hint(self):
        d = self.build()
        for it in self.t.items:
            it["fname"] = bytes([x ^ 0x5A for x in it["fname"]])
        self.img.write(self.img.slot, struct.pack("<Q", self.img.pe + 0x40))   # Haken schon gesetzt
        self.t._ask_adapt = lambda text: True
        self.t._check_dir(d)
        self.assertIn("BASIS dieses Trainers ist noch aktiv", self.t.lbl_done._text)

    def test_moved_function_is_found_and_trainer_is_adapted_automatically(self):
        import random
        rnd = random.Random(3)
        for a in (self.img.impl, self.img.pe):                       # eindeutiger Code -> echte Signaturen
            self.img.write(a, bytes(rnd.randrange(1, 255) for _ in range(160)))
        d = self.build()
        spec = TR._load_spec_raw(d)
        self.assertEqual(sorted(spec["anchors"]), ["item_function", "process_event"])
        old_rva = self.img.impl - self.img.BASE
        new_addr = self.img.impl + 0x100                              # Spiel-Update: Funktion liegt weiter hinten
        self.img.write(new_addr, self.img.read(self.img.impl, 160))
        self.img.write(self.img.impl, bytes(160))
        asked = []
        self.t._ask_adapt = lambda text: asked.append(text) or True
        self.t._check_dir(d)
        self.assertEqual(len(asked), 1)
        self.assertIn("anderer Stelle", asked[0])
        txt = self.t.lbl_done._text
        self.assertIn("Angepasst", txt)
        self.assertIn("verschobene Funktion", txt)
        opts = TR.load_options(d)
        self.assertEqual({r.call_impl_rva for o in opts for r in o.rows}, {new_addr - self.img.BASE})
        spec = TR._load_spec_raw(d)
        self.assertEqual(spec["anchors"]["item_function"]["rva"], hex(new_addr - self.img.BASE))
        self.assertNotEqual(old_rva, new_addr - self.img.BASE)
        res = TR.check_anchors(self.w.client, self.img.maps, self.img.BASE, spec)
        self.assertEqual({r[1] for r in res}, {"ok"})

    def test_moved_function_is_not_adapted_when_user_says_no(self):
        import random
        rnd = random.Random(4)
        for a in (self.img.impl, self.img.pe):
            self.img.write(a, bytes(rnd.randrange(1, 255) for _ in range(160)))
        d = self.build()
        before = Path(os.path.join(d, "_trainer_spec.json")).read_bytes()
        self.img.write(self.img.impl + 0x100, self.img.read(self.img.impl, 160))
        self.img.write(self.img.impl, bytes(160))
        self.t._ask_adapt = lambda text: False
        self.t._check_dir(d)
        self.assertIn("anderer Stelle", self.t.lbl_done._text)
        self.assertEqual(Path(os.path.join(d, "_trainer_spec.json")).read_bytes(), before)



if __name__ == "__main__":
    unittest.main()
