"""Tests gegen ECHTE Ausschnitte aus Palworld (PPSA23126) - Header, offsets.json, GObjects.txt."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import uesdk, uecheat

FX = os.path.join(os.path.dirname(__file__), "fixtures")
rd = lambda n: open(os.path.join(FX, n), encoding="utf-8").read()


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sdk = uesdk.parse_header_text(rd("pal_sample_classes.hpp"))
        uesdk.parse_offsets_json(rd("offsets.json"), cls.sdk)
        uesdk.parse_gobjects_dump(rd("gobjects_excerpt.txt"), cls.sdk)

    def test_members_flags_functions(self):
        c = self.sdk.classes["UPalCharacterParameterComponent"]
        self.assertEqual((c.parent, c.size), ("UActorComponent", 0x8b8))
        m = self.sdk.find_member("UPalCharacterParameterComponent", "bIsEnableMuteki")
        self.assertEqual((m.offset, m.ptype, m.type), (0xa2, "BoolProperty", "bool"))
        f = {x.name: x for x in c.funcs}
        self.assertEqual(f["AddHP"].native, 0x20d0950)
        self.assertEqual(f["AddHP"].ret, "void")
        self.assertIn("FFixedPoint64", f["AddHP"].args)
        self.assertTrue(f["AddHP"].flags & 0x400)                                     # FUNC_Native
        self.assertEqual(self.sdk.find_member("FPalIndividualCharacterSaveParameter", "Hp").type, "struct FFixedPoint64")
        self.assertFalse([k for k in self.sdk.classes if k.endswith("_Params")])

    def test_real_offsets_json(self):
        s = self.sdk
        self.assertEqual((s.offset("base"), s.offset("gobjects"), s.offset("gnames")), (0x400000, 0x8262c98, 0x8226f00))
        self.assertEqual((s.offset("UObject_Class"), s.offset("UObject_Name"), s.offset("UObject_Outer")), (0x10, 0x18, 0x20))
        self.assertEqual(s.offset("UFunction_ExecFunction"), 216)
        self.assertEqual(s.offset("fuobjectitem_size"), 24)
        self.assertEqual(s.offset("process_event"), 0x3086340)

    def test_gobjects_hex_index(self):
        g = self.sdk.gobjects
        self.assertEqual(g[0][:3], (0, 0x300b060000, "Package"))
        self.assertTrue(any(x[0] == 0x18F4 and x[3].endswith("Object.ExecuteUbergraph") for x in g))

    def test_candidates_find_builtin_cheat_switches(self):
        c = {x.key: x for x in uecheat.find_candidates(self.sdk, 8)}
        for k in ("UPalCharacterParameterComponent.bIsEnableMuteki", "UPalCharacterParameterComponent.bIsInfinitySP",
                  "UPalCharacterParameterComponent.bIsDebugMuteki"):
            self.assertIn(k, c, k)
            self.assertEqual(c[k].category, "Cheat-Schalter")
        hp = c["FPalIndividualCharacterSaveParameter.Hp"]
        self.assertEqual(hp.category, "Leben")
        self.assertTrue(any("FixedPoint" in r for r in hp.reasons))
        self.assertNotIn("FPalIndividualCharacterSaveParameter.PhysicalHealth", c)     # Enum, kein Zahlenwert

    def test_function_targets(self):
        t = {(d["cls"], d["name"]): d for d in uecheat.find_function_targets(self.sdk, min_score=-20)}
        d = t[("UPalCharacterParameterComponent", "AddHP")]
        self.assertEqual(d["native"], 0x20d0950); self.assertFalse(d["shared"])
        # Netzwerk-Huelle schlechter als die Funktion selbst
        self.assertGreater(d["score"], t[("UPalCharacterParameterComponent", "AddHP_ToServer")]["score"])

    def test_shared_stub_detection(self):
        sdk = uesdk.SDK(); c = uesdk.UClass("UPalFoo"); sdk.classes["UPalFoo"] = c
        for i in range(40):
            c.funcs.append(uesdk.Function(f"AddHP{i}", "void", "", 0x400, 0x30854e0, "UPalFoo"))
        c.funcs.append(uesdk.Function("AddHPReal", "void", "", 0x400, 0x20d0950, "UPalFoo"))
        res = {d["name"]: d for d in uecheat.find_function_targets(sdk, min_score=-20)}
        self.assertTrue(res["AddHP3"]["shared"]); self.assertFalse(res["AddHPReal"]["shared"])

if __name__ == "__main__":
    unittest.main()
