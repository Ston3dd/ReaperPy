"""Tab ITEMS: Filterstufen, mehrere Item-Listen, TEST-Button (Vorab-Test + Live-Test) - Fake-Tk, ohne Konsole."""
import os, struct, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import item_check as IC
import test_gui_items as GI
import ue_items as IT
import ue_profile as P


class Setup(unittest.TestCase):
    def setUp(self):
        GI.T.setUp(self)
        import tkinter.messagebox as mb
        self.mb = mb
        self.asked = []
        self.answers = {"askyesno": True, "askyesnocancel": True}
        for name in ("askyesno", "askyesnocancel"):
            old = getattr(mb, name, None)
            setattr(mb, name, (lambda n: lambda title, msg, **kw: self.asked.append((n, title, msg)) or self.answers[n])(name))
            self.addCleanup(setattr, mb, name, old)
        self.w.client.write_memory = self.img.write
        real = IC.live_probe

        def fast(*a, **k):                                           # Spiel-Thread simulieren, kurz warten
            return real(*a, **{**k, "tick": self.game, "wait": 0.3})
        self.patch(IC, "live_probe", fast)

    patch = GI.T.patch

    def game(self):
        end = self.img.BASE + 0x16000
        buf = bytearray(self.img.read(end - 0x100, 0x100))
        if 1 in buf:
            self.img.write(end - 0x100, bytes(0 if b == 1 else b for b in buf))

    def errs(self):
        return [m for k, m in self.w.logs if k == "err"]


class Levels(Setup):
    def test_default_is_the_soft_level(self):
        self.assertEqual(self.t.v_level.get(), "normal")
        self.assertTrue(self.t.v_merge.get())

    def test_table_named_item_skill_survives_normal_but_not_strict(self):
        tabs = [(0x10, "DT_ItemSkill"), (0x20, "DT_FxParam")]
        cands = IT.table_candidates(self.t.prof) if self.t.prof else []
        strict = [r["name"] for r in IT.rate_tables(cands, tabs, "streng") if r["relevant"]]
        normal = [r["name"] for r in IT.rate_tables(cands, tabs, "normal") if r["relevant"]]
        off = [r["name"] for r in IT.rate_tables(cands, tabs, "aus") if r["relevant"]]
        self.assertEqual((strict, normal, sorted(off)), ([], ["DT_ItemSkill"], ["DT_FxParam", "DT_ItemSkill"]))

    def test_changing_the_filter_searches_again(self):
        self.t.find_items()
        calls = []
        real = self.t.find_items
        self.t.find_items = lambda: calls.append(1) or real()
        self.t.v_level.set("aus"); self.t._level_changed()
        self.assertEqual(calls, [1])
        self.assertEqual(len(self.t.items), 3)


class MultiTable(Setup):
    def test_all_item_tables_are_read_and_merged(self):
        rows_a = [{"name": f"Item_Potion_{i}", "fname_hex": f"{i + 1:02x}" + "00" * 7, "row_ptr": 0, "values": {}} for i in range(3)]
        rows_b = [{"name": f"Sword_{i}", "fname_hex": f"{i + 20:02x}" + "00" * 7, "row_ptr": 0, "values": {}} for i in range(4)]
        tabs = [(0x7000_0000_8000, "DT_Consumables"), (0x7000_0000_9000, "DT_Weapons"), (0x7000_0000_A000, "DT_Enemies")]
        self.patch(P, "find_table_objects", lambda live: tabs)
        self.patch(P, "read_table", lambda rd, fs, addr, cols: ({0x7000_0000_8000: rows_a, 0x7000_0000_9000: rows_b}.get(addr, []), []))
        sug = lambda: type("S", (), {"data": {"columns": []}})()  # noqa: E731
        self.patch(IT, "choose_tables", lambda cands, live_tables, level=IT.DEFAULT_LEVEL, limit=12:
                   [(sug(), tabs[0], None), (sug(), tabs[1], None)])
        self.t.find_items()
        self.assertEqual(len(self.t.items), 7)
        self.assertEqual(self.t.tables_used, ["DT_Consumables", "DT_Weapons"])
        self.assertEqual({i["category"] for i in self.t.items}, {"Consumables", "Weapons"})      # nach der Tabelle benannt
        self.assertIn("2 Tabellen", self.t.lbl_found._text)

    def test_single_table_mode_keeps_old_behaviour(self):
        self.t.v_merge.set(False)
        self.t.find_items()
        self.assertEqual(self.t.tables_used, ["DT_Items"])
        self.assertEqual(len(self.t.items), 3)

    def test_nothing_found_explains_where_it_got_lost(self):
        self.patch(P, "find_table_objects", lambda live: [(0x1, "DT_Zombie")])
        self.patch(P, "read_table", lambda *a, **k: ([], []))
        self.t.v_merge.set(True)
        self.t.find_items()
        self.assertEqual(self.t.items, [])
        self.assertIn("Filter 'normal'", self.t.diag)
        self.assertIn("auf 'aus' stellen", self.t.diag)
        self.assertTrue(any("Filter 'normal'" in m for k, m in self.w.logs))


class TestButton(Setup):
    def test_preflight_marks_every_checked_item(self):
        self.answers["askyesno"] = False                                   # Live-Test ablehnen
        self.t.find_items()
        self.t.run_test()
        self.assertEqual(self.errs(), [])
        self.assertEqual(sorted(self.t.results), [0, 1, 2])
        self.assertEqual([r.status for r in self.t.results.values()], ["ok"] * 3)
        self.assertEqual([self.t._vals(i)[3] for i in range(3)], ["✔ ok"] * 3)
        self.assertIn("3 von 3 Items in Ordnung", self.t.lbl_done._text)
        self.assertEqual(self.asked[0][0], "askyesno")

    def test_only_checked_items_of_the_chosen_category_are_tested(self):
        self.answers["askyesno"] = False
        self.t.find_items()
        self.t.on = [True, False, True]
        self.t.run_test()
        self.assertEqual(sorted(self.t.results), [0, 2])
        self.t.results = {}
        cat = self.t.items[0]["category"]
        self.t.on = [True] * 3
        self.t.v_cat.set(cat)
        self.assertEqual(self.t._scope(), [i for i, it in enumerate(self.t.items) if it["category"] == cat])

    def test_nothing_checked_gives_a_hint(self):
        self.t.find_items()
        self.t.set_visible(False)
        self.t.run_test()
        self.assertIn("Items anhaken", self.t.lbl_done._text)
        self.assertEqual(self.t.results, {})

    def test_broken_item_fails_and_is_unchecked_but_others_stay(self):
        self.answers["askyesno"] = False
        self.t.find_items()
        self.t.items[1]["fname"] = struct.pack("<II", 999, 0)               # gibt es nicht im Namenspool
        self.t.run_test()
        self.assertEqual([self.t.results[i].status for i in range(3)], ["ok", "fail", "ok"])
        self.assertEqual(self.t.on, [True, False, True])
        self.assertIn("1 nicht brauchbar (abgehakt)", self.t.lbl_done._text)
        self.assertEqual([i["name"] for i in self.t._chosen()], ["Item_Gold", "Item_Sword"])

    def test_keep_failed_checked_when_switched_off(self):
        self.answers["askyesno"] = False
        self.t.find_items()
        self.t.v_cleanup.set(False)
        self.t.items[1]["fname"] = struct.pack("<II", 999, 0)
        self.t.run_test()
        self.assertEqual(self.t.on, [True, True, True])

    def test_blocking_failure_is_explained(self):
        self.t.find_items()
        self.live.function_entry = lambda owner, name: None
        self.t.run_test()
        self.assertTrue(self.t.report.blocking)
        self.assertIn("NICHT funktionieren", self.t.lbl_done._text)
        self.assertEqual(self.asked, [])                                    # kein Live-Test-Angebot bei Totalausfall

    def test_live_test_runs_and_removes_the_hook(self):
        self.t.find_items()
        self.t.run_test()                                                   # askyesno -> True: Live-Test
        self.assertEqual(self.errs(), [])
        self.assertEqual([r.ran for r in self.t.results.values()], [True] * 3)
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe)
        self.assertEqual([a[0] for a in self.asked], ["askyesno", "askyesnocancel"])
        self.assertIn("Item_Gold", self.asked[1][2])
        self.assertIn("3 von 3 Items in Ordnung", self.t.lbl_done._text)

    def test_nothing_arrived_in_the_inventory_is_flagged(self):
        self.answers["askyesnocancel"] = False
        self.t.find_items()
        self.t.run_test()
        self.assertEqual([r.status for r in self.t.results.values()], ["warn"] * 3)
        self.assertIn("kam nichts an", self.t.lbl_done._text)

    def test_live_test_failure_changes_nothing_and_says_so(self):
        self.t.find_items()
        self.img.write(self.img.slot, struct.pack("<Q", self.img.pe + 0x10))      # schon fremder Haken
        self.t.run_test()
        self.assertIn("im Spiel wurde nichts verändert", self.t.lbl_done._text)
        self.assertFalse(self.t._busy)
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe + 0x10)


class SaveAfterFailedTest(Setup):
    def test_saving_after_a_failed_test_asks_first(self):
        self.t.find_items()
        self.live.function_entry = lambda owner, name: None
        self.answers["askyesno"] = False
        self.t.v_cleanup.set(False)                                         # Items bleiben angehakt, damit gespeichert werden kann
        self.t.run_test()
        self.asked.clear()
        self.t.save()
        self.assertEqual(self.asked[0][1], "Der Test ist gescheitert")
        self.assertIn("nichts geschrieben", self.t.lbl_done._text)
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "Spiel", "Spiel Items")))
        self.live.function_entry = lambda owner, name: (0x1234, None)
        self.answers["askyesno"] = True
        self.t._ask_preview = lambda text: True
        self.t.save()
        self.assertIn("Fertig", self.t.lbl_done._text)

    def test_new_search_or_other_function_forgets_the_old_test(self):
        self.t.find_items()
        self.answers["askyesno"] = False
        self.t.run_test()
        self.assertTrue(self.t.results)
        self.t.find_items()
        self.assertEqual((self.t.report, self.t.results), (None, {}))


if __name__ == "__main__":
    unittest.main()
