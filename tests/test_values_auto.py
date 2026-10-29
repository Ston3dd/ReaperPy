"""values_auto: wichtige Werte (Leben, Gold, XP ...) als Patches - Unity-Namenserkennung und Unreal-Caves."""
import json, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import il2cpp_dump as D
import test_cheatmenu_cave as TC
import values_auto as VA
from pathlib import Path


def game(spec):
    """spec: [(Klasse, image, [(Name, Rueckgabe, Parameter, rva, static)])] -> Objekt mit all_methods()."""
    classes = []
    for name, image, methods in spec:
        c = D.Class("", name, "class", image=image)
        c.methods = [D.Method(n, ret, par, rva, st, c) for n, ret, par, rva, st in methods]
        classes.append(c)

    class G:
        def all_methods(self): return [m for c in classes for m in c.methods]
    return G()


A = "Assembly-CSharp.dll"
SPEC = [
    ("PlayerHealth", A, [("TakeDamage", "void", "int amount", 0x1000, False), (".ctor", "void", "", 0x1010, False),
                         ("get_IsDead", "bool", "", 0x1020, False), ("get_Damage", "int", "", 0x1030, False)]),
    ("EnemyHealth", A, [("TakeDamage", "void", "int amount", 0x2000, False)]),
    ("PlayerWallet", A, [("SpendMoney", "void", "int amount", 0x3000, False), ("CanAfford", "bool", "int price", 0x3010, False),
                         ("RemoveGold", "bool", "int amount", 0x3020, False)]),
    ("PlayerStamina", A, [("UseStamina", "void", "float amount", 0x4000, False)]),
    ("Weapon", A, [("UseAmmo", "void", "", 0x5000, False), ("HasAmmo", "bool", "", 0x5010, False)]),
    ("PlayerLevel", A, [("get_ExpToNextLevel", "int", "", 0x6000, False), ("ExpToNextLevel", "float", "", 0x6010, False)]),
    ("<>c__DisplayClass1", A, [("TakeDamage", "void", "", 0x7000, False)]),
    ("PlayerNoCode", A, [("TakeDamage", "void", "", 0, False)]),
]


class Unity(unittest.TestCase):
    def setUp(self):
        self.c = VA.find_unity_candidates(game(SPEC))
        self.by = {x.label: x for x in self.c}

    def test_recognises_the_important_methods_with_the_right_action(self):
        want = {"PlayerHealth.TakeDamage": ("Leben", "noop"), "PlayerHealth.get_IsDead": ("Leben", "false"),
                "PlayerWallet.SpendMoney": ("Geld", "noop"), "PlayerWallet.CanAfford": ("Geld", "true"),
                "PlayerWallet.RemoveGold": ("Geld", "true"),            # bool-Rueckgabe: nicht leer machen, 'ja' liefern
                "PlayerStamina.UseStamina": ("Ausdauer", "noop"), "Weapon.UseAmmo": ("Munition", "noop"),
                "Weapon.HasAmmo": ("Munition", "true"), "PlayerLevel.get_ExpToNextLevel": (VA.XP_CATEGORY, "value")}
        for label, (cat, mode) in want.items():
            self.assertEqual((self.by[label].cat, self.by[label].mode), (cat, mode), label)
        self.assertEqual(self.by["PlayerLevel.get_ExpToNextLevel"].value, 1)

    def test_skips_constructors_generated_classes_no_code_and_wrong_types(self):
        self.assertNotIn("PlayerHealth..ctor", self.by)
        self.assertNotIn("PlayerHealth.get_Damage", self.by)                 # int-Getter: kein sinnvoller Patch
        self.assertNotIn("PlayerLevel.ExpToNextLevel", self.by)             # float: XP-Regel nur fuer Ganzzahlen
        self.assertFalse([k for k in self.by if "DisplayClass" in k or "NoCode" in k])

    def test_enemy_class_is_ranked_lower_warned_and_not_default(self):
        enemy, player = self.by["EnemyHealth.TakeDamage"], self.by["PlayerHealth.TakeDamage"]
        self.assertLess(enemy.score, player.score)
        self.assertIn("Gegner", enemy.warn)
        self.assertFalse(enemy.default_on)
        self.assertTrue(player.default_on)

    def test_every_candidate_is_buildable_and_described(self):
        for x in self.c:
            D.make_patch(x.method, x.mode, x.value)
            self.assertTrue(x.effect)

    def test_per_category_limit(self):
        many = [("PlayerHealth%d" % i, A, [("TakeDamage", "void", "", 0x1000 + i, False)]) for i in range(20)]
        got = [c for c in VA.find_unity_candidates(game(many), per_cat=4) if c.cat == "Leben"]
        self.assertEqual(len(got), 4)

    def test_patch_doc_reads_original_and_protects_against_other_versions(self):
        x = self.by["PlayerHealth.TakeDamage"]
        orig = bytes([0x55, 0x48, 0x89, 0xE5, 0x41])
        doc = VA.unity_patch_doc(x, 0x400000, lambda a, n: orig[:n] if a == 0x401000 else b"")
        self.assertTrue(doc["Verify"])
        v = doc["Variables"][0]
        self.assertEqual((v["offset"], v["defaultValue"], v["newValue"]), ("0x1000", "55", "C3"))
        self.assertIn("Leben", doc["name"])
        with self.assertRaises(ValueError) as c:
            VA.unity_patch_doc(x, 0x400000, lambda a, n: b"\xc3\x90\x90\x90\x90"[:n])    # schon leer/gepatcht
        self.assertIn("schon gepatcht", str(c.exception))


@unittest.skipUnless(TC.HAVE, "Toolchain fehlt")
class Unreal(TC.Real):
    """Echter Maschinencode (as/objdump): Leben, Munition, Geld (nicht sinken) und Erfahrung (festschreiben)."""

    def setUp(self):
        self.out = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.out, True)

    def entries(self):
        e = TC.entry
        xp = e("UStats.XP", "value", "UStats", "XP", "int32", 0x100, default="auto")
        xp.cat = VA.XP_CATEGORY
        return [e("UHealthComponent.Health", "value", "UHealthComponent", "Health", "float", 0x348, default="auto"),
                e("UWeapon.Ammo", "value", "UWeapon", "Ammo", "int32", 0x200, default="auto"),
                xp, e("UStats.Missing", "value", "UStats", "Missing", "int32", 0x999, default="auto")]

    def test_builds_patch_files_and_reports_the_missing_one(self):
        done, failed = VA.build_ue_patches(TC.FakeMenu(), self.entries(), self.code, self.dis, self.out)
        self.assertEqual([d["entry"].member for d in done], ["Health", "Ammo", "XP"])
        self.assertEqual([d["mode"] for d in done], ["keep", "nop", "force"])        # Munition: sub wird abgeschaltet
        self.assertEqual([e.member for e, _why in failed], ["Missing"])
        self.assertIn("keine Schreibzugriffe", failed[0][1])
        files = sorted(os.listdir(self.out))
        self.assertEqual(len(files), 3)
        xp = json.loads(Path(os.path.join(self.out, done[2]["file"])).read_text(encoding="utf-8"))
        self.assertIn("99999", xp["name"])

    def test_force_fallback_uses_a_number_never_auto(self):
        e = self.entries()[1]
        e.cat = "Geld"                                           # Eintrag ohne sub: festschreiben mit fester Zahl
        o = [x for x in VA.CV.find_options(TC.FakeMenu(), e, self.code, self.dis)][0]
        o.modes["nop"] = (False, "")                              # NOP gesperrt -> force
        opt, mode, value = VA.ue_pick(e, [o])
        self.assertEqual((mode, value), ("force", VA.FORCE_DEFAULTS["Geld"]))

    def test_xp_value_is_configurable(self):
        done, _f = VA.build_ue_patches(TC.FakeMenu(), self.entries()[2:3], self.code, self.dis, self.out, xp_value="500")
        self.assertIn("500", done[0]["name"])


if __name__ == "__main__":
    unittest.main()
