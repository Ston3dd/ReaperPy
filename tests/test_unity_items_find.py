"""UNITY -> ITEMS: Item-Liste auch finden, wenn der Enum-Name nichts sagt (Geben-Methode / Inhalt / Item-Name aus dem Spiel)."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk  # noqa: E402

ghost_tk.install()
import il2cpp_dump as D  # noqa: E402
import test_gui_unity_items as GU  # noqa: E402
import test_unity_items as TU  # noqa: E402
import tools_i18n  # noqa: E402
import unity_items as U  # noqa: E402
from test_gui_smoke import FakeWin  # noqa: E402

ITEM_NAMES = ["Sword_Iron", "Sword_Steel", "Sword_Gold", "Potion_Small", "Potion_Big", "Potion_Mega", "Shield_Wood", "Fish_Trout",
              "Fish_Salmon", "Gold", "Wood", "Stone"]
ODD = ["kusuri_a", "kusuri_b", "kusuri_c", "buki_a", "buki_b", "buki_c", "tate_a", "tate_b", "tate_c", "yoroi_a", "yoroi_b", "yoroi_c"]


def make_game(tmp, enums, classes=()):
    parts = ["// Image 0: Assembly-CSharp.dll - 0\n// Image 1: UnityEngine.CoreModule.dll - 50\n"]
    td = 0
    for name, values in enums:
        parts.append(TU.enum_text(name, [(n, i) for i, n in enumerate(values)], td))
        td += 1
    for name, body in classes:
        parts.append(TU.cls_text(name, td, body))
        td += 1
    parts.append("// Namespace: UnityEngine\npublic class MonoBehaviour // TypeDefIndex: 50\n{\n}\n")
    parts.append("// Namespace: System\npublic class Object // TypeDefIndex: 51\n{\n}\n")
    path = os.path.join(tmp, "dump.cs")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    g = D.GameDump({"dump_cs": path}, log=lambda *_a: None)
    g.load()
    g.title = "Testspiel"
    return g


def put(rva, sig):
    return TU.meth(rva, sig)


class Scoring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def game(self):
        return make_game(self.tmp, [
            ("E_Obj", ["Obj%02d" % i for i in range(24)]),                 # Name sagt nichts, Werte auch nicht
            ("Buki", ITEM_NAMES),                                         # Name sagt nichts, Werte sind Items
            ("ItemID", ITEM_NAMES + ["Herb_Red", "Herb_Blue"]),           # Name sagt Item
            ("Color", ["Red", "Green", "Blue", "Yellow", "Black", "White"]),
            ("UIButtonKind", ["B%d" % i for i in range(30)]),
        ], [("Bag", put(0x1100, "public void Put(E_Obj id, int n)") + put(0x1200, "public void Update()"))])

    def test_enum_taken_by_a_give_method_counts_even_with_an_unhelpful_name(self):
        g = self.game()
        c = g.find_class("E_Obj")
        self.assertEqual(U.enum_score(c), 0)                              # ohne Geben-Methode: nichts
        self.assertGreater(U.enum_score(c, {"E_Obj"}), 6)                 # mit: eine der besten Listen
        self.assertEqual(U.enum_how(c, {"E_Obj"}), "give")

    def test_give_enum_types_come_from_method_names_not_enum_names(self):
        g = self.game()
        self.assertEqual(U.give_enum_types(g), {"E_Obj"})                 # Put(E_Obj id, int n)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        g2 = make_game(tmp, [("Direction", ["N", "S", "E", "W"] * 3 and ["North", "South", "East", "West", "Up", "Down", "Left", "Right"]),
                             ("Mode", ["A", "B", "C", "D"])],
                       [("Mover", put(0x1100, "public void AddForce(Direction d, float f)")        # keine Zahl: kein Geben
                         + put(0x1110, "public void RemoveItem(Mode m, int n)")                    # Entfernen: kein Geben
                         + put(0x1120, "public void AddStuff(Mode m, int count)"))])
        self.assertEqual(U.give_enum_types(g2), {"Mode"})

    def test_content_alone_finds_a_list_but_ranks_below_name_matches(self):
        g = self.game()
        buki, real = g.find_class("Buki"), g.find_class("ItemID")
        self.assertGreater(U.enum_score(buki), 0)
        self.assertEqual(U.enum_how(buki), "content")
        self.assertLess(U.enum_score(buki), U.enum_score(real))
        self.assertEqual(U.enum_how(real), "name")

    def test_noise_enums_stay_out(self):
        g = self.game()
        self.assertEqual(U.enum_score(g.find_class("Color")), 0)
        self.assertEqual(U.enum_score(g.find_class("UIButtonKind")), 0)
        names = [c.name for c, _s in U.item_enums(g)]
        self.assertNotIn("Color", names)
        self.assertNotIn("UIButtonKind", names)
        self.assertEqual(names[0], "ItemID")                              # die Namens-Erkennung bleibt vorn

    def test_search_finds_the_enum_with_the_item_name(self):
        g = self.game()
        res = U.search_enums(g, "potion small")
        self.assertEqual({f.probe.name for f in res}, {"Buki", "ItemID"})
        self.assertEqual(res[0].hits[0], "Potion_Small")
        self.assertEqual(U.search_enums(g, "einhorn"), [])

    def test_probes_are_cached_on_the_game(self):
        g = self.game()
        self.assertIs(U.enum_probes(g), U.enum_probes(g))


class Base(unittest.TestCase):
    def build(self, enums, classes=()):
        import tools_unity_items_gui as G
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.game = make_game(tmp, enums, classes)
        self.w = FakeWin()
        self.w.client = None
        self.un = GU.FakeUnity(self.game)
        self.w.extra_tabs = [self.un]
        self.t = G.UnityItemsTab(None, self.w)
        self.t._base_dir = lambda: os.path.join(tmp, "out")
        return self.t

    def text(self):
        return self.t.lbl_found._text


class FindItems(Base):
    def test_enum_taken_by_a_give_method_is_chosen_automatically(self):
        self.build([("E_Obj", ["Obj%02d" % i for i in range(24)])],
                   [("Bag", put(0x1100, "public void Put(E_Obj id, int n)") + put(0x1200, "public void Update()"))])
        self.t.find_items()
        self.assertEqual(self.t.enum.name, "E_Obj")
        self.assertEqual(self.t.found_by, "give")
        self.assertEqual(len(self.t.items), 24)
        self.assertIn("24 Items aus der Liste E_Obj", self.text())
        self.assertNotIn("Keine Item-Liste", self.text())

    def test_content_only_list_is_used_but_flagged(self):
        self.build([("Buki", ITEM_NAMES)])
        self.t.find_items()
        self.assertEqual(self.t.enum.name, "Buki")
        self.assertEqual(self.t.found_by, "content")
        self.assertIn("erkannt am Inhalt", self.text())
        self.assertTrue(self.t._help_shown)                               # falls die Vermutung falsch ist: Suche bleibt sichtbar

    def test_name_match_needs_no_helper(self):
        self.build([("ItemID", ITEM_NAMES)])
        self.t.find_items()
        self.assertEqual(self.t.found_by, "name")
        self.assertFalse(self.t._help_shown)

    def test_nothing_recognised_explains_and_offers_the_search(self):
        self.build([("Mst", ODD), ("Color", ["Red", "Green", "Blue", "Yellow"])])
        self.t.find_items()
        self.assertIsNone(self.t.enum)
        self.assertIn("Keine Item-Liste am Namen erkannt", self.text())
        self.assertIn("2 Listen", self.text())
        self.assertIn("ALLE LISTEN PRÜFEN", self.text())
        self.assertTrue(self.t._help_shown)

    def test_strict_filter_finds_no_method_then_a_loosened_one_is_used_and_flagged(self):
        self.build([("ItemID", ITEM_NAMES)], [("Bag", put(0x1100, "public void Handle(ItemID id, int n)")
                                              + put(0x1200, "public void Update()"))])
        self.t.find_items()
        self.assertTrue(self.t.loosened)
        self.assertIsNotNone(self.t.give)
        self.assertIn("Notlösung", self.text())
        self.assertIn("1 ITEM TESTEN", self.text())

    def test_english(self):
        self.build([("Buki", ITEM_NAMES)])
        old = tools_i18n.lang()
        tools_i18n.set_lang("en")
        try:
            self.t.find_items()
        finally:
            tools_i18n.set_lang(old)
        self.assertIn("recognised by content", self.text())


class SearchByName(Base):
    def setUp(self):
        self.build([("Mst", ODD), ("Color", ["Red", "Green", "Blue", "Yellow"]),
                    ("Shop", ["buki_a", "buki_b", "buki_c", "x", "y", "z"])])
        self.t.find_items()
        self.assertTrue(self.t._help_shown)

    def test_item_name_selects_the_enum_it_lives_in(self):
        self.t.v_known.set("yoroi b")
        self.t.search_known()
        self.assertEqual(self.t.enum.name, "Mst")
        self.assertEqual(self.t.found_by, "search")
        self.assertEqual(len(self.t.items), 12)
        self.assertIn("yoroi_b", self.text())
        self.assertIn("ausgewählt", self.text())

    def test_hits_in_several_lists_are_offered_as_candidates(self):
        self.t.v_known.set("buki")
        self.t.search_known()
        self.assertEqual({p.name for p in self.t.cand_probes}, {"Mst", "Shop"})
        other = next(i for i, p in enumerate(self.t.cand_probes) if p.name != self.t.enum.name)
        self.t.cb_cand.current = lambda: other
        self.t.pick_candidate()
        self.assertEqual(self.t.enum.name, self.t.cand_probes[other].name)

    def test_not_found(self):
        self.t.v_known.set("einhorn")
        self.t.search_known()
        self.assertIn("nicht gefunden", self.text())
        self.assertIsNone(self.t.enum)

    def test_too_short_name_asks_for_one(self):
        self.t.v_known.set("x")
        self.t.search_known()
        self.assertIn("Tippe den Namen", self.text())

    def test_check_all_lists_offers_candidates(self):
        self.t.check_all_lists()
        self.assertIn("Mst", [p.name for p in self.t.cand_probes])
        self.assertIsNone(self.t.enum)                                    # Mst ist nur "vielleicht" (unter der Schwelle)
        self.assertIn("mögliche Item-Listen", self.text())

    def test_check_all_lists_loads_a_clear_winner(self):
        self.build([("Buki", ITEM_NAMES + ["Herb_Red", "Herb_Blue"] * 0), ("Color", ["Red", "Green", "Blue", "Yellow"])])
        self.t.enum, self.t.items = None, []
        self.t.check_all_lists()
        self.assertEqual(self.t.enum.name, "Buki")
        self.assertEqual(self.t.found_by, "content")


class NoGame(Base):
    def test_search_without_a_game_asks_for_step_one(self):
        self.build([("ItemID", ITEM_NAMES)])
        self.un.game = None
        self.t.v_known.set("potion")
        self.t.search_known()
        self.assertIn("Schritt", self.text())


if __name__ == "__main__":
    unittest.main()
