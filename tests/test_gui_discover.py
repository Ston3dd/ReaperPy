"""GUI-Tests fuer den Tab UE-ENTDECKER (Fake-Tk, kein Display)."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import test_ue_profile as TP
from test_gui_smoke import FakeWin


def _rd(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Rec:
    def __init__(self): self.t = ""
    def delete(self, *a): self.t = ""
    def insert(self, _i, text): self.t += text
    def __getattr__(self, n): return lambda *a, **k: None


class FakeLive:
    index = {}
    def __init__(self, lt):
        self.lt = lt
        self.index = {0x7000_0000_8000: (1, 0x1111, "DT_Items"), 0x7000_0000_9000: (2, 0x1111, "DT_Enemies"),
                      0x7000_0000_A000: (3, 0x1111, "Default__DataTable")}
        self.rd, self.fname_str = lt.m.read, lt.fname
    def name(self, cl): return "DataTable"
    def is_template(self, ptr): return False


class FakeUeLive:
    def __init__(self, sdk, live=None):
        self.proj = type("P", (), {"sdk": sdk, "name": "Testspiel"})()
        self.live = live
        self.v_q = type("V", (), {"v": "", "set": lambda s, x: setattr(s, "v", x), "get": lambda s: s.v})()
        self.filled = 0
    def _fill_targets(self): self.filled += 1


FakeUeLive.__name__ = "UeLiveTab"


class T(unittest.TestCase):
    def setUp(self):
        import tools_discover_gui as G
        import tkinter.filedialog as fd
        self.fd = fd
        self.w = FakeWin()
        self.w.nb = type("NB", (), {"selected": [], "select": lambda s, t: s.selected.append(t)})()
        self.w.show_tab = lambda t: self.w.nb.selected.append(t)
        self.lt = TP.LiveTable(); self.lt.setUp()
        sdk = TP.sdk_from(TP.GAME_A, [(1, 0x7000_1000, "DataTable", "DataTable /Game/Data/DT_Items.DT_Items")])
        self.ue = FakeUeLive(sdk, FakeLive(self.lt))
        self.w.extra_tabs = [self.ue]
        self.t = G.DiscoverTab(None, self.w)
        self.t.txt = Rec()
        self.tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.tmp, True)

    def errs(self): return [m for k, m in self.w.logs if k == "err"]

    def pick(self, kind, title):
        self.t.v_kind.set(kind); self.t.fill()
        iid = next(i for i, s in enumerate(self.t.view) if s.title == title)
        self.t.tv.sel = (str(iid),)
        self.t.on_select()
        return self.t.view[iid]

    def test_analyze_needs_sdk(self):
        self.ue.proj = type("P", (), {"sdk": None})()
        self.t.analyze()
        self.assertTrue(any("SPIEL-ORDNER" in m for m in self.errs()))

    def test_analyze_fill_filter_and_detail(self):
        self.t.analyze()
        self.assertEqual(self.errs(), [])
        self.assertGreater(len(self.t.tv.rows), 10)
        self.assertTrue(any("UE-Entdecker" in m for k, m in self.w.logs if k == "ok"))
        self.t.v_kind.set("Item-Struct"); self.t.fill()
        self.assertEqual([s.kind for s in self.t.view], ["item_struct"] * len(self.t.view))
        self.assertEqual(self.t.view[0].title, "FInvEntry")
        self.t.v_kind.set("alle"); self.t.v_q.set("godmode"); self.t.fill()
        self.assertEqual([s.title for s in self.t.view], ["UMyCheatManager"])
        self.pick("alle", "UMyCheatManager")
        self.assertIn("Cheat-Manager", self.t.txt.t); self.assertIn("So benutzt du es", self.t.txt.t)

    def test_row_search_filters_by_name_and_keeps_indexes(self):
        self.t.analyze()
        self.pick("Tabelle", "FItemRow")
        self.t.read_table()
        self.assertEqual(len(self.t.tv_rows.rows), 3)
        self.t.v_rowq.set("poti")
        self.t._fill_rows()
        self.assertEqual([v[0] for v in self.t.tv_rows.rows.values()], ["Item_Potion"])
        self.t.tv_rows.sel = tuple(self.t.tv_rows.rows)               # iid = Index in der vollen Liste (1)
        self.assertEqual([r["name"] for r in self.t._selected_rows()], ["Item_Potion"])

    def test_id_number_is_taken_from_the_selected_row(self):
        self.t.cur = ("T", [{"name": "Item_A", "fname_hex": "00", "row_ptr": 0, "values": {"ItemID": 4711, "Price": 5}}], [])
        self.t.rows_mode = "rows"
        self.t.tv_rows.insert("", "end", iid="0", values=("Item_A", "00", ""))
        self.t.tv_rows.sel = ("0",)
        self.t._auto_id()
        self.assertEqual(self.t.v_idnum.get(), "4711")

    def test_unsupported_give_function_is_marked_and_explained(self):
        self.t.analyze()
        gives = [s for s in self.t.prof.suggestions if s.kind == "give_function"]
        if not gives:
            self.skipTest("Fixture ohne Geben-Funktion")
        for s in gives:
            s.data["params"] = list(s.data["params"]) + [("FString", "Reason")]      # nicht unterstuetzter Parametertyp
        self.t._support.clear()
        self.t.v_kind.set("alle"); self.t.v_q.set(""); self.t.fill()
        rows = [v for v in self.t.tv.rows.values() if "GEHT NICHT" in str(v[3])]
        self.assertTrue(rows)
        self.assertTrue(all(str(v[1]).startswith("✗ ") for v in rows))

    def test_next_step_hint_after_analysis(self):
        self.t.analyze()
        self.assertIn("Naechster Schritt", self.t.v_info.get())

    def test_read_table_for_suggestion_export_and_errors(self):
        self.t.analyze()
        self.pick("Tabelle", "FItemRow")
        self.t.read_table()
        self.assertEqual(self.errs(), [])
        name, rows, cols = self.t.cur
        self.assertEqual(name, "DT_Items")
        self.assertEqual([r["name"] for r in rows], ["Item_Gold", "Item_Potion", "Item_Sword"])
        first = next(iter(self.t.tv_rows.rows.values()))
        self.assertEqual(first[:2], ("Item_Gold", "0a00000000000000"))
        self.assertIn("Price=500", first[2])
        out = os.path.join(self.tmp, "t.csv")
        self.fd.asksaveasfilename = lambda *a, **k: out
        self.t.export_table()
        self.assertIn("Item_Sword,0c00000000000000", _rd(out))
        out2 = os.path.join(self.tmp, "t.json")
        self.fd.asksaveasfilename = lambda *a, **k: out2
        self.t.export_table()
        self.assertIn('"Price": 1200', _rd(out2))

    def test_read_table_errors_are_friendly(self):
        self.t.analyze()
        self.t.tv.sel = (); self.t.read_table()
        self.assertTrue(any("anklicken" in m for m in self.errs()))
        self.w.logs.clear()
        self.pick("Geben-Funktion", "UMyCheatManager.GiveItem"); self.t.read_table()
        self.assertTrue(any("keine Tabelle" in m for m in self.errs()))
        self.w.logs.clear()
        self.pick("Tabelle", "FShopRow"); self.t.read_table()          # keine passende Live-Tabelle -> Auswahlliste, kein Fehler
        self.assertEqual(self.errs(), [])
        self.assertEqual(self.t.rows_mode, "tables")
        self.assertEqual([n for _a, n in self.t.tab_list], ["DT_Enemies", "DT_Items"])
        self.w.logs.clear()
        self.t.v_table.set("enem"); self.t.read_table()                # getippter Name: DT_Enemies -> Speicher dort leer
        self.assertFalse(any("Keine" in m for m in self.errs()))

    def test_list_tables_skips_templates_and_default_objects(self):
        self.t.list_tables()
        self.assertEqual([n for _a, n in self.t.tables], ["DT_Enemies", "DT_Items"])
        self.assertTrue(any("2 DataTables" in m for k, m in self.w.logs if k == "ok"))
        self.assertEqual(self.t.rows_mode, "tables")
        self.assertEqual([v[0] for v in self.t.tv_rows.rows.values()], ["DT_Enemies", "DT_Items"])

    def test_no_live_gives_clear_message(self):
        self.ue.live = None
        self.t.list_tables()
        self.assertTrue(any("Kein Live-Zugriff" in m for m in self.errs()))

    def test_report_and_open_in_live(self):
        self.t.analyze()
        out = os.path.join(self.tmp, "r.md")
        self.fd.asksaveasfilename = lambda *a, **k: out
        self.t.save_report()
        self.assertIn("FInvEntry", _rd(out))
        self.pick("Waehrung", "UInventoryComponent.Gold")
        self.t.open_in_live()
        self.assertEqual(self.ue.v_q.v, "UInventoryComponent.Gold")
        self.assertEqual((self.ue.filled, len(self.w.nb.selected)), (1, 1))
        self.pick("Cheat-Manager", "UMyCheatManager")
        self.w.logs.clear(); self.t.open_in_live()
        self.assertTrue(self.errs())

    def _client_with_entries(self):
        import struct
        m = TP.WMem()
        base = 0x7000_0300_0000
        heap = bytearray(0x2000)
        for off, ix, cnt in ((0x100, 10, 500), (0x140, 11, 7)):
            struct.pack_into("<II", heap, off, ix, 0)
            struct.pack_into("<i", heap, off + 8, cnt)
        m.put(base, heap)
        self.mem = m
        self.w.client = type("C", (), {"read_memory": lambda s, a, n: m.read(a, n), "write_memory": lambda s, a, d: m.write(a, bytes(d)),
                                       "get_maps": lambda s: [(base, base + 0x2000, 3), (0x10000, 0x20000, 5)]})()
        return base

    def test_find_entries_and_set_count(self):
        import struct
        import tkinter.simpledialog as sd
        base = self._client_with_entries()
        self.t.analyze()
        self.pick("Tabelle", "FItemRow"); self.t.read_table()                 # Zeilen + FNames
        self.pick("Item-Struct", "FInvEntry")
        self.t.tv_rows.sel = ()
        self.t.find_entries()                                                  # ohne Item-Auswahl -> freundliche Meldung
        self.assertTrue(any("Items in der Tabelle" in m for m in self.errs()))
        self.w.logs.clear()
        self.t.tv_rows.sel = ("0",)                                            # Item_Gold
        self.t.find_entries()
        self.assertEqual(self.errs(), [])
        self.assertEqual([(h.name, h.count) for h in self.t.hits], [("Item_Gold", 500)])
        self.assertEqual(self.t.hits[0].base, base + 0x100)
        self.t.v_cnt.set("500"); self.t.find_entries()
        self.assertEqual(len(self.t.hits), 1)
        self.t.tv_hits.sel = ("0",)
        sd.askstring = lambda *a, **k: "99999"
        self.t.set_entry_count()
        self.assertEqual(struct.unpack("<i", self.mem.read(base + 0x108, 4))[0], 99999)
        self.t.tv_hits.sel = (); self.w.logs.clear(); self.t.set_entry_count()
        self.assertTrue(self.errs())
        self.t.tv_hits.sel = ("0",); self.t._goto_hit()
        self.assertEqual(self.w.went[-1], ("mem", base + 0x108))

    def test_find_entries_needs_item_struct_and_int_id_number(self):
        self._client_with_entries()
        self.t.analyze()
        self.pick("Geben-Funktion", "UMyCheatManager.GiveItem"); self.t.find_entries()
        self.assertTrue(any("Item-Struct" in m for m in self.errs()))
        self.w.logs.clear()
        t2 = TP.sdk_from(TP.GAME_B)
        self.ue.proj = type("P", (), {"sdk": t2})()
        self.t.analyze()
        self.pick("Item-Struct", "FBagSlot"); self.t.find_entries()
        self.assertTrue(any("ID-Zahl" in m for m in self.errs()))
        self.w.logs.clear()
        self.t.v_idnum.set("4711"); self.t.find_entries()
        self.assertEqual(self.errs(), ["0 Inventar-Eintraege von FBagSlot gefunden (ohne Mengen-Angabe: nur plausible Mengen - "
                                       "ggf. 'Menge im Spiel' eintragen)"])      # nichts gefunden = Hinweis, kein Absturz
        self.assertEqual(self.t.hits, [])

    # ---- Cave-Trainer ----------------------------------------------------------------------------
    def _cave_world(self, answer=False, name="Paket"):
        import tkinter.messagebox as mb
        import tkinter.simpledialog as sd
        import tools_discover_gui as G
        import test_cave_trainer as TS
        img = TS.FakeImage()
        out = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, out, True)
        self.w.client = type("C", (), {"read_memory": lambda s, a, n: img.read(a, n), "get_maps": lambda s: img.maps})()
        self.ue.live.function_entry = lambda owner, nm: (img.BASE + 0x1000,)
        self.t._hook_targets = lambda live: (img.pe, [img.slot], [])
        saved = [(G, "_find_impl", G._find_impl), (mb, "askyesnocancel", getattr(mb, "askyesnocancel", None)),
                 (self.fd, "askdirectory", getattr(self.fd, "askdirectory", None)), (sd, "askstring", getattr(sd, "askstring", None))]
        for o, a, v in saved:
            self.addCleanup(setattr, o, a, v)
        G._find_impl = lambda read, base, thunk: img.impl
        mb.askyesnocancel = lambda *a, **k: answer
        self.fd.askdirectory = lambda *a, **k: out
        sd.askstring = lambda *a, **k: name
        self.t.analyze()
        self.pick("Tabelle", "FItemRow"); self.t.read_table()
        return img, out

    def test_cave_trainer_for_fname_function(self):
        import cave_trainer as TR
        import ue_cavegen as CG
        img, out = self._cave_world()
        self.pick("Geben-Funktion", "UMyCheatManager.GiveItem")
        self.t.tv_rows.sel = ("0", "1"); self.t.v_amount.set("250")
        self.t.export_cave_trainer()
        self.assertEqual(self.errs(), [])
        opts = TR.load_options(out)
        self.assertEqual([o.name for o in opts], ["Item_Gold x250", "Item_Potion x250"])
        sp = opts[0].rows[0].spec
        self.assertEqual((sp.this_mode, sp.this_off, sp.impl_rva), ("zero", 0, img.impl - img.BASE))   # kein Cheat-Manager-Zeiger im Test-SDK
        self.assertEqual([(a["name"], a["value"]) for a in sp.args],
                         [("ItemName", bytes.fromhex("0a00000000000000")), ("Count", 250)])
        self.assertTrue(os.path.exists(os.path.join(out, TR.BASE_FILE)))
        self.assertTrue(any("this:" in m for k, m in self.w.logs))
        self.assertTrue(any("Cave-Trainer geschrieben" in m for k, m in self.w.logs if k == "ok"))
        self.assertEqual(int.from_bytes(img.read(img.slot, 8), "little"), img.pe)         # nur gelesen

    def test_cave_trainer_package_split_byref_and_extra(self):
        import cave_trainer as TR
        img, out = self._cave_world(answer=True, name="Items")
        self.pick("Geben-Funktion", "UMyCheatManager.GiveItem")
        self.t.tv_rows.sel = ("0", "1", "2"); self.t.v_byref.set(True); self.t.v_this.set("hooked")
        self.t.export_cave_trainer()
        self.assertEqual(self.errs(), [])
        opts = TR.load_options(out)
        self.assertEqual([(o.name, len(o.rows)) for o in opts], [("Items", 3)])
        a = opts[0].rows[0].spec.args[0]
        self.assertEqual((a["mode"], opts[0].rows[0].spec.this_mode), ("ref", "hooked"))

    def test_cave_trainer_amount_only_function_and_validation(self):
        import cave_trainer as TR
        img, out = self._cave_world()
        self.pick("Geben-Funktion", "UMyCheatManager.AddGold")
        self.t.v_amount.set("5000")
        self.t.export_cave_trainer()
        self.assertEqual(self.errs(), [])
        opts = TR.load_options(out)
        self.assertEqual([o.name for o in opts], ["AddGold x5000"])
        self.assertIsNone(opts[0].rows[0].fname)
        self.w.logs.clear()
        self.t.v_extra.set("kaputt"); self.t.export_cave_trainer()
        self.assertTrue(any("Name=Wert" in m for m in self.errs()))
        self.w.logs.clear()
        self.t.v_extra.set(""); self.pick("Item-Struct", "FInvEntry"); self.t.export_cave_trainer()
        self.assertTrue(any("Geben-Funktion" in m for m in self.errs()))
        self.w.logs.clear()
        self.pick("Geben-Funktion", "UMyCheatManager.GiveItem"); self.t.tv_rows.sel = (); self.t.export_cave_trainer()
        self.assertTrue(any("Item-Namen" in m for m in self.errs()))

    def test_cave_trainer_errors_write_nothing(self):
        import tools_discover_gui as G
        img, out = self._cave_world()
        G._find_impl = lambda *a: None
        self.pick("Geben-Funktion", "UMyCheatManager.AddGold"); self.t.export_cave_trainer()
        self.assertTrue(any("nicht erkannt" in m for m in self.errs()))
        self.assertEqual(os.listdir(out), [])
        self.assertFalse(self.t._busy)
        self.w.logs.clear()
        G._find_impl = lambda read, base, thunk: img.impl
        self.t._hook_targets = lambda live: (img.pe, [0x7000000100], [])
        self.t.export_cave_trainer()
        self.assertTrue(any("nicht im Spiel-Image" in m for m in self.errs()))
        self.assertEqual(os.listdir(out), [])

    # ---- Doppelklick-Bedienung ---------------------------------------------------------------------
    def test_selecting_table_fills_name_and_double_click_reads_it(self):
        self.t.analyze()
        self.pick("Tabelle", "FItemRow")
        self.assertEqual(self.t.v_table.get(), "DT_Items")                  # Name steht ohne Tippen im Feld
        self.t.on_double()
        self.assertEqual(self.errs(), [])
        self.assertEqual(self.t.rows_mode, "rows")
        self.assertEqual([r["name"] for r in self.t.cur[1]], ["Item_Gold", "Item_Potion", "Item_Sword"])
        self.pick("Tabelle", "FShopRow")
        self.assertEqual(self.t.v_table.get(), "")                          # kein veralteter Name bleibt stehen

    def test_double_click_without_match_offers_list_then_reads_chosen_table(self):
        self.t.analyze()
        self.pick("Tabelle", "FShopRow")
        self.t.on_double()                                                  # keine passende Live-Tabelle -> Auswahlliste
        self.assertEqual(self.t.rows_mode, "tables")
        self.t.tv_rows.sel = ("1",)                                         # DT_Items
        self.t.on_rows_double()
        self.assertEqual(self.errs(), [])
        self.assertEqual((self.t.rows_mode, self.t.cur[0]), ("rows", "DT_Items"))
        self.t.on_rows_double()                                             # in der Zeilen-Ansicht: nichts passiert
        self.assertEqual(self.t.cur[0], "DT_Items")

    def test_table_list_selection_is_never_taken_for_item_rows(self):
        self.t.analyze()
        self.pick("Tabelle", "FItemRow"); self.t.on_double()
        self.t.list_tables()                                                # unten jetzt Tabellen statt Zeilen
        self.t.tv_rows.sel = ("0",)
        self.assertEqual(self.t._selected_rows(), [])

    def test_double_click_on_member_suggestions_opens_live(self):
        self.t.analyze()
        self.pick("Waehrung", "UInventoryComponent.Gold"); self.t.on_double()
        self.assertEqual(self.ue.v_q.v, "UInventoryComponent.Gold")
        self.pick("Geben-Funktion", "UMyCheatManager.GiveItem"); self.w.logs.clear(); self.t.on_double()
        self.assertEqual(self.w.logs, [])                                   # keine Meldung, nichts passiert

    def test_registered_in_main_window(self):
        src = _rd(os.path.join(os.path.dirname(__file__), "..", "tools_gui.py"))
        self.assertIn('("tools_discover_gui", "DiscoverTab", "★ UE-ENTDECKER")', src)


if __name__ == "__main__":
    unittest.main()
