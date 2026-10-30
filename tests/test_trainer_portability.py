"""Trainer auf einer ANDEREN Konsole / Spielversion: nichts blind ueberschreiben, Platz nach Kapazitaet,
verstaendliche Meldungen, FName-Nummern des eigenen Spiels uebernehmen."""
import os, shutil, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import cave_trainer as T
import patch_engine as PE
import reapatch
import test_cave_trainer as TS
import ue_cavegen as CG
from pathlib import Path


class Backend:
    def __init__(self, img): self.img = img
    def read(self, a, n): return self.img.read(a, n)
    def write(self, a, d): self.img.write(a, bytes(d))
    def get_maps(self, force=False): return self.img.maps
    def assemble(self, *_a, **_k): raise AssertionError("kein Assembler noetig")


class Project(unittest.TestCase):
    def setUp(self):
        self.img = TS.FakeImage()
        self.p = T.plan(self.img.read, self.img.maps, self.img.BASE, TS.make_options(), self.img.impl, self.img.pe,
                        [self.img.slot], log=lambda _m: None, settle=0)
        self.dir = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.dir, True)
        T.write_project(self.dir, self.p, "X")

    def load(self, name):
        return reapatch.ReapPatch.load(os.path.join(self.dir, name))

    def other_console(self):
        """Gleiches Spiel, aber andere Version: an den Trainer-Adressen steht anderer Inhalt."""
        img = TS.FakeImage()
        img.write(self.p.cave, b"\x48\x8b\x05" * 10)
        img.write(self.p.flag_addr, b"\x07")
        img.write(img.slot, struct.pack("<Q", img.pe + 0x40))
        return img


class VersionGuard(Project):
    def test_projects_are_marked_for_verification(self):
        self.assertTrue(self.load(T.BASE_FILE).raw.get("Verify"))
        self.assertTrue(self.load("01_Gold.reapproj").raw.get("Verify"))

    def test_base_refuses_a_different_game_version_and_writes_nothing(self):
        img = self.other_console(); be = Backend(img)
        base = self.load(T.BASE_FILE)
        before = {a: img.read(a, 32) for a in (self.p.cave, img.slot)}
        with self.assertRaises(RuntimeError) as c:
            PE.apply_patch(be, base, img.BASE + base.origin_source[0])
        self.assertIn("Passt nicht zu diesem Spiel", str(c.exception))
        self.assertEqual({a: img.read(a, 32) for a in (self.p.cave, img.slot)}, before)    # nichts veraendert

    def test_flag_refuses_foreign_data_but_accepts_zero_and_already_set(self):
        img = self.other_console(); be = Backend(img)
        gold = self.load("01_Gold.reapproj"); hook = img.BASE + gold.origin_source[0]
        with self.assertRaises(RuntimeError):
            PE.apply_patch(be, gold, hook)                          # 0x07 steht dort: fremde Daten
        self.assertEqual(img.read(self.p.flag_addr, 1), b"\x07")
        img.write(self.p.flag_addr, b"\x00")
        PE.apply_patch(be, gold, hook)
        self.assertEqual(img.read(self.p.flag_addr, 1), b"\x01")
        PE.apply_patch(be, gold, hook)                              # schon 01: kein Fehler
        self.assertEqual(img.read(self.p.flag_addr, 1), b"\x01")

    def test_same_version_still_works(self):
        be = Backend(self.img); base = self.load(T.BASE_FILE)
        st = PE.apply_patch(be, base, self.img.BASE + base.origin_source[0])
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.p.cave)
        PE.deactivate_patch(be, base, st)
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe)

    def test_community_patches_without_verify_are_unchanged(self):
        img = self.other_console(); be = Backend(img)
        gold = self.load("01_Gold.reapproj"); gold.raw.pop("Verify")
        PE.apply_patch(be, gold, img.BASE + gold.origin_source[0])            # altes Verhalten: schreibt
        self.assertEqual(img.read(self.p.flag_addr, 1), b"\x01")


class CheckProject(Project):
    def test_same_game_passes(self):
        r = T.check_project(self.dir, self.img.read, self.img.BASE)
        self.assertTrue(r["ok_version"], r["problems"])
        self.assertGreaterEqual(r["anchors_checked"], 2)
        self.assertFalse(r["base_active"])

    def test_other_version_and_other_base_are_reported(self):
        img = TS.FakeImage()
        img.write(img.impl, b"\x90" * 32)
        r = T.check_project(self.dir, img.read, img.BASE)
        self.assertFalse(r["ok_version"])
        self.assertTrue(any("Trainer erwartet" in x for x in r["problems"]))
        r = T.check_project(self.dir, img.read, img.BASE + 0x1000)
        self.assertTrue(any("Image-Basis" in x for x in r["problems"]))

    def test_detects_an_active_cave(self):
        be = Backend(self.img); base = self.load(T.BASE_FILE)
        PE.apply_patch(be, base, self.img.BASE + base.origin_source[0])
        self.assertTrue(T.check_project(self.dir, self.img.read, self.img.BASE)["base_active"])

    def test_old_project_without_anchors_is_flagged(self):
        import json
        sp = os.path.join(self.dir, T.SPEC_FILE)
        d = json.loads(Path(sp).read_text(encoding="utf-8")); d.pop("anchors"); Path(sp).write_text(json.dumps(d), encoding="utf-8")
        r = T.check_project(self.dir, self.img.read, self.img.BASE)
        self.assertFalse(r["ok_version"])
        self.assertTrue(any("Fingerabdruck" in x for x in r["problems"]))


class Capacity(unittest.TestCase):
    def test_capacity_follows_the_padding_and_fit_splits(self):
        img = TS.FakeImage()
        img.write(img.BASE, b"\x55" * (0x10000 - 0x600 + 1))   # Code bis kurz vor dem Ende: nur 0x5FF Byte Luecke
        cap = T.capacity(img.read, img.maps, img.BASE)
        self.assertTrue(0x500 <= cap["code"] <= 0x600, cap)
        rows = [T.Row(f"I{k}", bytes([k + 1] * 8), 1) for k in range(60)]
        opts = [T.Option(f"E{k}", rows[k * 6:k * 6 + 6]) for k in range(10)]
        groups = T.fit_options(opts, cap["code"])
        self.assertGreater(len(groups), 1)
        for g in groups:
            self.assertLessEqual(T.cave_size(g), cap["code"])
        self.assertEqual([o.name for g in groups for o in g], [o.name for o in opts])

    def test_single_option_too_big(self):
        big = T.Option("Gross", [T.Row(f"I{k}", bytes([1] * 8), 1) for k in range(14)])
        with self.assertRaises(T.TrainerError) as c:
            T.fit_options([big], 100)
        self.assertIn("passt nicht", str(c.exception))

    def test_no_space_message_explains_why(self):
        img = TS.FakeImage()
        img.write(img.BASE, b"\x55" * 0x10000)   # Region voll belegt (z. B. andere Cave / Code)
        with self.assertRaises(T.TrainerError) as c:
            T.plan(img.read, img.maps, img.BASE, TS.make_options(), img.impl, img.pe, [img.slot],
                   log=lambda _m: None, settle=0)
        msg = str(c.exception)
        self.assertIn("Kein freier Code-Platz", msg)
        self.assertIn("NICHT leer", msg)
        self.assertIn("Gebraucht:", msg)


class FNames(unittest.TestCase):
    def test_refresh_row_and_callrow(self):
        r1 = T.Row("Item_Gold", bytes([1] * 8), 5)
        spec = CG.CallSpec(0x1000, [{"name": "ItemName", "kind": "fname", "size": 8, "signed": False,
                                    "value": bytes([2] * 8)},
                                   {"name": "Count", "kind": "int", "size": 4, "signed": True, "value": 7}])
        r2 = CG.CallRow("Item_Potion", spec, bytes([2] * 8), 7)
        r3 = T.Row("Item_Weg", bytes([3] * 8), 1)
        opts = [T.Option("A", [r1, r2, r3])]
        live = {"Item_Gold": bytes([9] * 8), "Item_Potion": bytes([8] * 8)}
        new, changed, missing = T.refresh_fnames(opts, live)
        rows = new[0].rows
        self.assertEqual(rows[0].fname, bytes([9] * 8))
        self.assertEqual(rows[1].fname, bytes([8] * 8))
        self.assertEqual(rows[1].spec.args[0]["value"], bytes([8] * 8))                # echter Aufruf-Wert
        self.assertEqual(rows[1].spec.args[1]["value"], 7)
        self.assertEqual((rows[2].fname, rows[0].amount), (bytes([3] * 8), 5))
        self.assertEqual((sorted(changed), missing), (["Item_Gold", "Item_Potion"], ["Item_Weg"]))
        self.assertEqual(opts[0].rows[0].fname, bytes([1] * 8))                          # Original unveraendert
        T.cave_size(new)                                                                   # baubar


if __name__ == "__main__":
    unittest.main()
