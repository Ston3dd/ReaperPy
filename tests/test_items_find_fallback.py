"""UNREAL -> ITEMS: Item-Liste am Inhalt erkennen, nach einem Item-Namen suchen, Funktions-Filter lockern (Fake-Tk, ohne Konsole)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk  # noqa: E402

ghost_tk.install()
import item_finder as F  # noqa: E402
import test_gui_items as GI  # noqa: E402
import tools_i18n  # noqa: E402
import ue_items as IT  # noqa: E402
import ue_profile as P  # noqa: E402

ITEM_ROWS = ["Sword_Iron", "Sword_Steel", "Sword_Gold", "Potion_Small", "Potion_Big", "Potion_Mega", "Shield_Wood",
             "Fish_Trout", "Fish_Salmon", "Gold", "Wood", "Stone"]
GAME = {  # Adresse -> (Tabellenname, Zeilennamen): kein Name sagt "Item"
    0x1000: ("DT_Param001", ITEM_ROWS),
    0x2000: ("DT_Fx", [f"Fx_Hit_{i}" for i in range(30)]),
    0x3000: ("DT_Quests", [f"Quest_{i:03d}" for i in range(15)]),
}


def rows_of(names):
    return [{"name": n, "fname_hex": n.encode().hex(), "row_ptr": 0x100 * (i + 1), "values": {}} for i, n in enumerate(names)]


class Base(unittest.TestCase):
    def setUp(self):
        self.h = GI.T("test_status_shows_missing_steps")        # nur wegen setUp / Hilfsfunktionen, der Test selbst laeuft nicht
        self.h.setUp()
        self.t = self.h.t
        self.reads = []
        self.game = dict(GAME)
        self._ft, self._rt = P.find_table_objects, P.read_table
        P.find_table_objects = lambda live: [(a, n) for a, (n, _r) in self.game.items()]

        def read_table(read, fname_str, addr, columns=None, limit=100000, max_columns=14):
            self.reads.append((addr, limit))
            return rows_of(self.game[addr][1][:limit]), []
        P.read_table = read_table

    def tearDown(self):
        P.find_table_objects, P.read_table = self._ft, self._rt
        self.h.doCleanups()

    def text(self):
        return self.t.lbl_found._text


class ContentFallback(Base):
    def test_table_with_unhelpful_name_is_found_by_content(self):
        self.t.find_items()
        self.assertEqual(self.t.table[1], "DT_Param001")
        self.assertEqual(self.t.found_by, "content")
        self.assertEqual([i["name"] for i in self.t.items][:2], ["Sword_Iron", "Sword_Steel"])
        self.assertIn("erkannt am Inhalt", self.text())
        self.assertIn("⚠", self.text())                                  # Warnfarbe: bitte kurz pruefen

    def test_helper_row_is_offered_after_a_content_guess(self):
        self.t.find_items()
        self.assertTrue(self.t._help_shown)
        self.assertEqual(self.t.cand_probes[0].name, "DT_Param001")
        self.assertIn("DT_Param001", self.t.cand_probes[0].label())      # so steht sie in der Auswahl: Name, Anzahl, Vorschau
        self.assertIn("Sword_Iron", self.t.cand_probes[0].label())

    def test_name_based_result_is_untouched_and_needs_no_helper(self):
        P.find_table_objects, P.read_table = self._ft, self._rt
        self.t.find_items()
        self.assertEqual(self.t.table[1], "DT_Items")
        self.assertEqual(self.t.found_by, "name")
        self.assertIsNone(self.t.probe_result)                           # Inhaltspruefung lief gar nicht
        self.assertFalse(self.t._help_shown)

    def test_nothing_item_like_says_so_in_plain_words_and_offers_the_search(self):
        self.game = {0x2000: GAME[0x2000], 0x3000: GAME[0x3000]}
        self.t.find_items()
        self.assertIsNone(self.t.table)
        self.assertIn("Keine Item-Liste erkannt", self.text())
        self.assertIn("2 von 2", self.text())
        self.assertIn("ALLE LISTEN PRÜFEN", self.text())                 # naechster Schritt steht dabei
        self.assertTrue(self.t._help_shown)

    def test_english(self):
        old = tools_i18n.lang()
        tools_i18n.set_lang("en")
        try:
            self.t.find_items()
        finally:
            tools_i18n.set_lang(old)
        self.assertIn("recognised by content", self.text())


class SearchByName(Base):
    def setUp(self):
        super().setUp()
        self.game = {0x2000: GAME[0x2000], 0x3000: GAME[0x3000],
                     0x5000: ("DT_Mst", ["kusuri_a", "kusuri_b", "kusuri_c", "Potion_Small", "Potion_Big", "buki_a", "buki_b"])}
        self.t.find_items()                                              # nichts erkannt -> Hilfe-Zeile ist da
        self.assertTrue(self.t._help_shown)

    def test_item_name_selects_the_table_it_lives_in(self):
        self.t.v_known.set("potion small")
        self.t.search_known()
        self.assertEqual(self.t.table[1], "DT_Mst")
        self.assertEqual(self.t.found_by, "search")
        self.assertIn("Potion_Small", self.text())
        self.assertIn("ausgewählt", self.text())
        self.assertEqual(len(self.t.items), 7)

    def test_item_name_not_found(self):
        self.t.v_known.set("Einhorn")
        self.t.search_known()
        self.assertIn("nicht gefunden", self.text())
        self.assertIsNone(self.t.table)

    def test_too_short_or_empty_name_asks_for_one(self):
        self.t.v_known.set(" a ")
        self.t.search_known()
        self.assertIn("Tippe den Namen", self.text())

    def test_search_needs_find_items_first(self):
        self.t.live_tables = []
        self.t.v_known.set("potion")
        self.t.search_known()
        self.assertIn("Erst ITEMS FINDEN", self.text())

    def test_hits_are_offered_as_candidates_and_can_be_switched(self):
        self.game[0x6000] = ("DT_Shop", ["Potion_Small", "Potion_Big", "Potion_Mega", "Elixir"])
        self.t.find_items()
        self.t.v_known.set("potion")
        self.t.search_known()
        names = [p.name for p in self.t.cand_probes]
        self.assertIn("DT_Mst", names)
        self.assertIn("DT_Shop", names)
        other = next(i for i, p in enumerate(self.t.cand_probes) if p.name != self.t.table[1])
        self.t.cb_cand.current = lambda: other                           # Auswahl in der Liste
        self.t.pick_candidate()
        self.assertEqual(self.t.table[1], self.t.cand_probes[other].name)

    def test_second_search_reuses_the_probe_cache(self):
        self.t.v_known.set("potion")
        self.t.search_known()
        n = len(self.reads)
        self.t.v_known.set("kusuri")
        self.t.search_known()
        probes = [r for r in self.reads[n:] if r[1] == F.PROBE_ROWS]
        self.assertEqual(probes, [])                                      # keine Liste wurde noch einmal zum Bewerten gelesen


class CheckAllLists(Base):
    def test_button_loads_the_best_list_when_nothing_is_chosen(self):
        self.t.find_items()
        self.t.table, self.t.items = None, []                            # Nutzer hat nichts gewaehlt
        self.t.check_all_lists()
        self.assertEqual(self.t.table[1], "DT_Param001")

    def test_button_keeps_the_current_list_and_only_offers_candidates(self):
        self.t.find_items()
        before = self.t.table
        self.t.check_all_lists()
        self.assertEqual(self.t.table, before)
        self.assertTrue(self.t.cand_probes)
        self.assertEqual(self.t.found_by, "content")                     # unveraendert: die schon gewaehlte Liste bleibt

    def test_button_needs_find_items_first(self):
        self.t.live_tables = []
        self.t.check_all_lists()
        self.assertIn("Erst ITEMS FINDEN", self.text())


class UnreadableTable(Base):
    def test_one_unreadable_table_does_not_abort_the_search(self):
        """Vorher brach ITEMS FINDEN mit einem Speicherfehler ab, sobald eine der Tabellen nicht lesbar war."""
        P.find_table_objects = self._ft
        real = self._rt
        calls = []

        def rt(read, fname_str, addr, columns=None, limit=100000, max_columns=14):
            calls.append(addr)
            if len(calls) == 1:
                raise OSError(hex(addr))
            return real(read, fname_str, addr, columns, limit, max_columns)
        P.read_table = rt
        self.t.v_level.set(IT.LEVEL_OFF)                             # 'aus': alle Tabellen sind Kandidaten
        self.t.find_items()
        self.assertGreater(len(calls), 1)                            # es ging weiter
        self.assertNotIn("nicht geklappt", self.text())


class LoosenedFunctionFilter(Base):
    def test_strict_filter_finds_no_function_then_a_loosened_one_is_used_and_flagged(self):
        P.find_table_objects, P.read_table = self._ft, self._rt
        real = IT.rate_functions
        seen = []

        def rate(prof, sdk, level, *a, **k):
            seen.append(level)
            return [] if level != IT.LEVEL_OFF else real(prof, sdk, level, *a, **k)
        old = IT.rate_functions
        IT.rate_functions = rate
        try:
            self.t.v_level.set("streng")
            self.t.find_items()
        finally:
            IT.rate_functions = old
        self.assertEqual(seen, ["streng", IT.LEVEL_OFF])
        self.assertTrue(self.t.func_loosened)
        self.assertIsNotNone(self.t.func)
        self.assertIn("Notlösung", self.text())
        self.assertIn("1 ITEM TESTEN", self.text())

    def test_no_second_try_when_the_filter_is_already_off(self):
        P.find_table_objects, P.read_table = self._ft, self._rt
        seen = []
        old = IT.rate_functions
        IT.rate_functions = lambda prof, sdk, level, *a, **k: seen.append(level) or []
        try:
            self.t.v_level.set(IT.LEVEL_OFF)
            self.t.find_items()
        finally:
            IT.rate_functions = old
        self.assertEqual(seen, [IT.LEVEL_OFF])
        self.assertFalse(self.t.func_loosened)


if __name__ == "__main__":
    unittest.main()
