"""item_finder.py: Item-Listen am Inhalt erkennen, nach einem Item-Namen suchen, Klartext-Meldungen (ohne Konsole)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import item_finder as F  # noqa: E402

ITEMS = ["Sword_Iron", "Sword_Steel", "Sword_Gold", "Potion_Small", "Potion_Big", "Potion_Mega", "Shield_Wood", "Fish_Trout",
         "Fish_Salmon", "Gold", "Wood", "Stone"]


class Words(unittest.TestCase):
    def test_words_and_norm(self):
        self.assertEqual(F.words("Potion_Small"), ["potion", "small"])
        self.assertEqual(F.words("PotionSmall02"), ["potion", "small", "02"])
        self.assertEqual(F.words("DT_ITEMPARAM"), ["dt", "itemparam"])
        self.assertEqual(F.norm("Health Potion_S"), "healthpotions")
        self.assertEqual(F.words(None), [])


class ContentScore(unittest.TestCase):
    def test_a_normal_item_list_is_recognised(self):
        score, reasons = F.content_score(ITEMS)
        self.assertGreaterEqual(score, F.CONTENT_OK)
        self.assertTrue(any("Item-Wörtern" in r for r in reasons))

    def test_a_big_mixed_list_scores_high(self):
        names = [f"{w}_{i:02d}" for w in ("Sword", "Potion", "Armor", "Bow") for i in range(40)]
        self.assertGreaterEqual(F.content_score(names)[0], 8)

    def test_effect_and_animation_lists_are_not_items(self):
        self.assertLess(F.content_score([f"Anim_Run_{i}" for i in range(50)])[0], 2)
        self.assertLess(F.content_score([f"Sound_Step_{i}" for i in range(60)] + [f"Fx_Hit_{i}" for i in range(60)])[0], F.CONTENT_MAYBE)

    def test_tiny_lists_are_ignored(self):
        self.assertEqual(F.content_score(["A", "B", "C"])[0], 0.0)
        self.assertEqual(F.content_score([])[0], 0.0)

    def test_one_uniform_prefix_alone_is_not_enough(self):
        """Hundert Zeilen 'Foo_0001' ... sagen nichts darueber, was drin ist: nur Kandidat, nie automatisch."""
        score = F.content_score([f"Mst_Buki_{i:04d}" for i in range(200)])[0]
        self.assertLess(score, F.CONTENT_OK)

    def test_unusual_names_with_several_groups_are_candidates(self):
        names = ["kusuri_a", "kusuri_b", "kusuri_c", "buki_a", "buki_b", "buki_c", "tate_a", "tate_b", "tate_c",
                 "yoroi_a", "yoroi_b", "yoroi_c"]
        self.assertGreaterEqual(F.content_score(names)[0], F.CONTENT_MAYBE)        # Namen ohne bekannte Woerter, aber mit Ordnung

    def test_preview_shows_variety(self):
        p = F.preview(ITEMS, 4)
        self.assertIn("Sword_Iron", p)
        self.assertIn("Potion_Small", p)                                           # nicht nur die ersten vier Schwerter
        self.assertTrue(p.endswith("…"))
        self.assertEqual(F.preview(["a", "b"], 4), "a, b")


class Probing(unittest.TestCase):
    def tables(self):
        data = {
            ("a1", "DT_Weird"): ITEMS,
            ("a2", "DT_Fx"): [f"Fx_Hit_{i}" for i in range(40)],
            ("a3", "DT_Quests"): [f"Quest_{i:03d}" for i in range(20)],
        }
        return data

    def test_probe_ranks_by_content(self):
        data = self.tables()
        res = F.probe_tables([(k[0], k[1]) for k in data], lambda key: next(v for k, v in data.items() if k[0] == key))
        self.assertEqual((res.total, res.checked, res.timed_out), (3, 3, False))
        self.assertEqual(res.best().name, "DT_Weird")
        self.assertEqual([p.name for p in res.ranked(F.CONTENT_OK)], ["DT_Weird"])

    def test_broken_table_does_not_stop_the_rest(self):
        def rd(key):
            if key == "bad":
                raise RuntimeError("Speicher nicht lesbar")
            return ITEMS
        res = F.probe_tables([("bad", "Kaputt"), ("ok", "Gut")], rd)
        self.assertEqual(res.checked, 2)
        self.assertEqual(res.best().name, "Gut")

    def test_time_budget_stops_and_says_so(self):
        t = [0.0]

        def clock():
            return t[0]

        def rd(key):
            t[0] += 10
            return ITEMS
        res = F.probe_tables([(i, f"T{i}") for i in range(10)], rd, budget_s=25, clock=clock)
        self.assertTrue(res.timed_out)
        self.assertEqual(res.checked, 3)                  # nach 30 s "Zeit" ist Schluss
        self.assertEqual(res.total, 10)

    def test_cache_avoids_reading_twice(self):
        cache, reads = {}, []

        def rd(key):
            reads.append(key)
            return ITEMS
        F.probe_tables([("a", "A"), ("b", "B")], rd, cache=cache)
        F.probe_tables([("a", "A"), ("b", "B"), ("c", "C")], rd, cache=cache)
        self.assertEqual(reads, ["a", "b", "c"])

    def test_progress_is_reported(self):
        seen = []
        F.probe_tables([(i, f"T{i}") for i in range(60)], lambda k: ITEMS, progress=lambda a, b: seen.append((a, b)))
        self.assertEqual(seen, [(25, 60), (50, 60)])


class Search(unittest.TestCase):
    def probes(self):
        mk = lambda name, names: F.Probe(name, name, names, *F.content_score(names)[:1], reasons=[])  # noqa: E731
        return [mk("DT_Weird", ITEMS), mk("DT_Fx", [f"Fx_Potion_Splash_{i}" for i in range(40)]),
                mk("DT_Other", ["Rock", "Tree", "Bush", "Grass", "Flower"])]

    def test_finds_the_item_table_for_an_item_name(self):
        res = F.search("Potion", self.probes())
        self.assertEqual(res[0].probe.name, "DT_Weird")                      # die Item-Liste vor dem Effekt-Treffer
        self.assertIn("Potion_Small", res[0].hits)
        self.assertEqual({r.probe.name for r in res}, {"DT_Weird", "DT_Fx"})

    def test_case_spaces_and_underscores_do_not_matter(self):
        self.assertEqual(F.search("potion small", self.probes())[0].hits[0], "Potion_Small")
        self.assertEqual(F.search("SWORD-IRON", self.probes())[0].hits[0], "Sword_Iron")

    def test_exact_name_ranks_first_inside_a_table(self):
        probes = [F.Probe("T", "T", ["Gold_Coin", "Gold", "GoldBar", "Old_Gold_Key"], 5.0)]
        self.assertEqual(F.search("gold", probes)[0].hits[0], "Gold")

    def test_multi_word_needs_all_words(self):
        self.assertEqual(F.search("potion mega", self.probes())[0].hits, ["Potion_Mega"])
        self.assertEqual(F.search("potion unicorn", self.probes()), [])

    def test_no_hit_and_too_short_queries(self):
        self.assertEqual(F.search("Unicorn", self.probes()), [])
        self.assertEqual(F.search("a", self.probes()), [])
        self.assertEqual(F.search("", self.probes()), [])
        self.assertEqual(F.search("12", [F.Probe("T", "T", ["Item_12", "Item_21"], 1.0)])[0].hits, ["Item_12"])


class Messages(unittest.TestCase):
    def test_nothing_found(self):
        self.assertIn("143 Tabellen", F.msg_nothing(143, 0, False))
        self.assertIn("120 von 143", F.msg_nothing(143, 120, True))
        self.assertIn("Zeitlimit", F.msg_nothing(143, 120, True))
        self.assertIn("lists", F.msg_nothing(30, 30, False, kind="enum", lang="en"))

    def test_next_step_names_the_buttons(self):
        self.assertIn("ALLE LISTEN PRÜFEN", F.msg_next_step())
        self.assertIn("CHECK ALL LISTS", F.msg_next_step("en"))

    def test_search_messages(self):
        found = F.search("Potion", [F.Probe("DT_Weird", "DT_Weird", ITEMS, 5.5)])[0]
        m = F.msg_search_found("Potion", found, others=2)
        self.assertIn("DT_Weird", m)
        self.assertIn("Weitere Listen mit Treffern: 2", m)
        self.assertIn("English name", F.msg_search_none("X", 10, 10, False, "en").replace("the English name", "English name"))
        self.assertIn("Zeitlimit", F.msg_search_none("X", 5, 10, True))

    def test_content_pick_message(self):
        m = F.msg_content_pick("DT_Weird", 12, ITEMS)
        self.assertIn("erkannt am Inhalt", m)
        self.assertIn("12 Einträge", m)
        self.assertIn("recognised by content", F.msg_content_pick("T", 3, ["a", "b", "c"], "en"))


if __name__ == "__main__":
    unittest.main()
