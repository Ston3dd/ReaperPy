"""Trainer-Ordner: Namen so, wie der Nutzer die Dateien benannt hat; Neu-Laden/Speichern aktualisiert die Dateien
(statt die alten Namen und Eintraege aus der _trainer_spec.json zu benutzen)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cave_trainer as T  # noqa: E402
import ue_items as IT  # noqa: E402
from test_cave_trainer import FakeImage, make_options  # noqa: E402


class R:
    def __init__(self, alias, amount=1):
        self.alias, self.amount = alias, amount


def make_plan(options):
    img = FakeImage()
    return T.plan(img.read, img.maps, img.BASE, options, img.impl, img.pe, [img.slot], log=lambda _m: None, settle=0)


class TrainerNames(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.p = make_plan(make_options())                        # Gold, Traenke, Material
        T.write_project(self.dir, self.p, "Test", game="Spiel")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def names(self):
        return sorted(f for f in os.listdir(self.dir) if f.endswith(".reapproj"))

    def rename(self, old, new):
        os.rename(os.path.join(self.dir, old), os.path.join(self.dir, new))

    def test_untouched_project_keeps_generated_names(self):
        opts = T.load_options(self.dir)
        self.assertEqual([o.name for o in opts], ["Gold", "Traenke", "Material"])
        self.assertTrue(all(o.file is None for o in opts))

    def test_names_come_from_the_files_the_user_named(self):
        self.rename("01_Gold.reapproj", "Geld Klein.reapproj")
        self.rename("03_Material.reapproj", "Zeug.reapproj")
        opts, notes = T.sync_options(self.dir)
        self.assertEqual([(o.name, o.file) for o in opts],
                         [("Geld Klein", "Geld Klein.reapproj"), ("Traenke", None), ("Zeug", "Zeug.reapproj")])
        self.assertTrue(any("Gold" in n and "Geld Klein" in n for n in notes))

    def test_new_items_of_the_same_category_land_in_the_renamed_entry(self):
        self.rename("01_Gold.reapproj", "Geld Klein.reapproj")
        opts = T.load_options(self.dir)
        self.assertEqual(opts[0].origin, "Gold")
        out = IT.merge_into_existing(opts, [T.Option("Gold", [T.Row("neues_item", b"\x05" * 8, 5)])])
        self.assertEqual([o.name for o in out], ["Geld Klein", "Traenke", "Material"])
        self.assertIn("neues_item", [r.alias for r in out[0].rows])
        T.write_project(self.dir, make_plan(out), "Test", game="Spiel")           # und der Name ueberlebt das Speichern
        again = T.load_options(self.dir)
        self.assertEqual((again[0].name, again[0].file, again[0].origin), ("Geld Klein", "Geld Klein.reapproj", "Gold"))

    def test_deleted_file_is_no_longer_an_entry(self):
        os.remove(os.path.join(self.dir, "02_Traenke.reapproj"))
        opts, notes = T.sync_options(self.dir)
        self.assertEqual([o.name for o in opts], ["Gold", "Material"])
        self.assertTrue(any("Traenke" in n for n in notes))

    def test_only_json_left_falls_back_to_the_saved_list(self):
        for f in self.names():
            os.remove(os.path.join(self.dir, f))
        self.assertEqual([o.name for o in T.load_options(self.dir)], ["Gold", "Traenke", "Material"])

    def test_resave_updates_the_renamed_files_in_place_and_leaves_no_stale_copies(self):
        self.rename("01_Gold.reapproj", "Geld Klein.reapproj")
        self.rename(T.BASE_FILE, "Hauptschalter.reapproj")
        stale = json.load(open(os.path.join(self.dir, "Geld Klein.reapproj"), encoding="utf-8"))
        stale["Info"] = "ALT"
        with open(os.path.join(self.dir, "Geld Klein.reapproj"), "w", encoding="utf-8") as f:
            json.dump(stale, f)
        T.write_project(self.dir, make_plan(T.load_options(self.dir)), "Test", game="Spiel")
        self.assertEqual(self.names(), sorted(["02_Traenke.reapproj", "03_Material.reapproj", "Geld Klein.reapproj",
                                               "Hauptschalter.reapproj"]))           # keine 01_Gold / 00_BASIS Kopien
        fresh = json.load(open(os.path.join(self.dir, "Geld Klein.reapproj"), encoding="utf-8"))
        self.assertNotEqual(fresh.get("Info"), "ALT")                                 # Datei wurde neu geschrieben
        self.assertEqual(fresh["name"], "Geld Klein")                                 # im Patch steht der Nutzername
        base = json.load(open(os.path.join(self.dir, "Hauptschalter.reapproj"), encoding="utf-8"))
        self.assertEqual(base["name"], "Hauptschalter")

    def test_resave_follows_the_new_plan_not_the_old_json(self):
        """Nach dem Loeschen einer Datei stimmen Schalter-Nummern und Spec mit den Dateien im Ordner ueberein."""
        os.remove(os.path.join(self.dir, "02_Traenke.reapproj"))
        T.write_project(self.dir, make_plan(T.load_options(self.dir)), "Test", game="Spiel")
        spec = json.load(open(os.path.join(self.dir, T.SPEC_FILE), encoding="utf-8"))
        self.assertEqual([o["name"] for o in spec["options"]], ["Gold", "Material"])
        self.assertEqual(self.names(), sorted([T.BASE_FILE, "01_Gold.reapproj", "02_Material.reapproj"]))
        mat = json.load(open(os.path.join(self.dir, "02_Material.reapproj"), encoding="utf-8"))
        self.assertEqual(int(mat["Variables"][0]["offset"], 16), int(spec["flag_rva"], 16) + 1)

    def test_users_own_files_in_the_folder_are_not_touched(self):
        mine = os.path.join(self.dir, "Max Money.ReapPatch")
        with open(mine, "w", encoding="utf-8") as f:
            f.write("{}")
        T.write_project(self.dir, make_plan(T.load_options(self.dir)), "Test", game="Spiel")
        self.assertTrue(os.path.isfile(mine))

    def test_display_name_prefers_the_users_file_name(self):
        self.rename("01_Gold.reapproj", "Geld Klein.reapproj")
        p = os.path.join(self.dir, "Geld Klein.reapproj")
        self.assertEqual(T.display_name(p, "01 Gold"), "Geld Klein")
        q = os.path.join(self.dir, "02_Traenke.reapproj")
        self.assertEqual(T.display_name(q, "02 Traenke"), "02 Traenke")                # unveraendert -> Name aus der Datei
        self.assertEqual(T.display_name(os.path.join(self.dir, T.BASE_FILE), "00 BASIS - Item-Cave (zuerst aktivieren)"),
                         "00 BASIS - Item-Cave (zuerst aktivieren)")
        outside = tempfile.mkdtemp()
        try:                                                                          # ausserhalb eines Trainer-Ordners nie aendern
            self.assertEqual(T.display_name(os.path.join(outside, "x.reapproj"), "Name"), "Name")
        finally:
            shutil.rmtree(outside)

    def test_base_file_is_recognised_after_rename(self):
        self.rename(T.BASE_FILE, "1 Mastercode.reapproj")
        self.assertTrue(T.is_base_file(os.path.join(self.dir, "1 Mastercode.reapproj")))
        self.assertFalse(T.is_base_file(os.path.join(self.dir, "01_Gold.reapproj")))
        self.assertEqual(T.scan_files(self.dir)[0], "1 Mastercode.reapproj")

    def test_renamed_name_collision_gets_a_free_file_name(self):
        self.rename("03_Material.reapproj", "02_Traenke (Kopie).reapproj")
        opts = T.load_options(self.dir)
        names = T._unique_names(opts)
        self.assertEqual(len({n.lower() for n in names}), len(names))


class MergeKeepsUserNames(unittest.TestCase):
    def test_new_items_go_into_the_entry_with_room_names_and_files_stay(self):
        old = [T.Option("Food Item 2", [R(f"a{i}") for i in range(14)], "Food Item 2.reapproj", "Food 1"),
               T.Option("Food Item 1", [R("b0"), R("b1")], "Food Item 1.reapproj", "Food 4")]
        out = IT.merge_into_existing(old, [T.Option("Food", [R("b1", 99), R("neu", 99)])])
        self.assertEqual([(o.name, o.file, len(o.rows)) for o in out],
                         [("Food Item 2", "Food Item 2.reapproj", 14), ("Food Item 1", "Food Item 1.reapproj", 3)])
        self.assertEqual({r.alias: r.amount for r in out[1].rows}, {"b0": 1, "b1": 99, "neu": 99})

    def test_overflow_creates_the_next_numbered_entry(self):
        old = [T.Option("Food Item 3", [R(f"a{i}") for i in range(14)], "x.reapproj", "Food 2")]
        out = IT.merge_into_existing(old, [T.Option("Food", [R("neu")])])
        self.assertEqual([o.name for o in out], ["Food Item 3", "Food Item 4"])
        self.assertIsNone(out[1].file)
        self.assertEqual(out[1].origin, "Food")               # gehoert weiter zur Kategorie 

    def test_option_file_survives_json_roundtrip_and_refresh(self):
        o = T.Option("Zeug", [T.Row("a", b"\x01" * 8, 1)], "Zeug.reapproj", "MTL 3")
        back = T.Option.from_json(json.loads(json.dumps(o.to_json())))
        self.assertEqual((back.file, back.origin), ("Zeug.reapproj", "MTL 3"))
        new, _c, _m = T.refresh_fnames([o], {"a": b"\x02" * 8})
        self.assertEqual((new[0].file, new[0].origin), ("Zeug.reapproj", "MTL 3"))
        new, _n = T.remap_options([o], {})
        self.assertEqual((new[0].file, new[0].origin), ("Zeug.reapproj", "MTL 3"))


if __name__ == "__main__":
    unittest.main()
