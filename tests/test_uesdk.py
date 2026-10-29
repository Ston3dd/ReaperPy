import os, sys, json, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import uesdk, uecheat
from pathlib import Path

HDR = Path(os.path.join(os.path.dirname(__file__), "sample_sdk.hpp")).read_text(encoding="utf-8") if os.path.exists(
    os.path.join(os.path.dirname(__file__), "sample_sdk.hpp")) else ""


class T(unittest.TestCase):
    def sdk(self):
        return uesdk.parse_header_text(HDR)

    def test_parse(self):
        s = self.sdk()
        self.assertIn("UHealthComponent", s.classes)
        hc = s.classes["UHealthComponent"]
        self.assertEqual(hc.parent, "UActorComponent")
        self.assertEqual(s.find_member("UHealthComponent", "Health").offset, 0x348)
        self.assertEqual(s.find_member("AMyCharacter", "bIsDead").bit, 0)
        self.assertTrue(any(f[0] == "TakeDamage" for f in hc.functions))
        self.assertEqual(s.find_member("AMyCharacter", "CustomTimeDilation").owner, "AActor")   # geerbt
        self.assertNotIn("StaticClass", [f[0] for f in hc.functions])
        self.assertFalse([m for m in hc.members if m.name.startswith("Pad_")])

    def test_ue4ss_style(self):
        s = uesdk.parse_header_text("class UFoo : public UObject\n{\npublic:\n    int32 Gold; // 0x0100 (size: 0x4)\n};\n")
        self.assertEqual(s.classes["UFoo"].members[0].offset, 0x100)

    def test_offsets_json_and_hpp(self):
        s = uesdk.parse_offsets_json(json.dumps({"OFFSET_GOBJECTS": "0x5B2C8A0", "OFFSET_GNAMES": 12345,
                                                 "Nested": {"ProcessEvent": "0x1A2B3C"}}))
        self.assertEqual(s.offset("GObjects"), 0x5B2C8A0)
        self.assertEqual(s.offset("gnames"), 12345)
        self.assertEqual(s.offset("ProcessEvent"), 0x1A2B3C)
        s2 = uesdk.parse_header_text("namespace Offsets\n{\n\tconstexpr int32 GObjects = 0x1234;\n\tconstexpr int32 GWorld = 0x99;\n}\n")
        self.assertEqual(s2.offset("gworld"), 0x99)

    def test_gobjects_dump(self):
        s = uesdk.parse_gobjects_dump("[00001234] {0x000001A2B3C4D5E6} Class Engine.Actor\n[00001235] {0x1A2B3C4D5F00} Function Game.HealthComponent.TakeDamage\n")
        self.assertEqual(len(s.gobjects), 2)
        self.assertEqual(s.gobjects[1][2], "Function")

    def test_candidates(self):
        s = self.sdk(); c = uecheat.find_candidates(s)
        keys = [x.key for x in c]
        self.assertIn("UHealthComponent.Health", keys[:3])
        by = {x.key: x for x in c}
        self.assertEqual(by["UHealthComponent.Health"].category, "Leben")
        self.assertEqual(by["UWeaponComponent.CurrentAmmo"].category, "Munition")
        self.assertEqual(by["UWalletComponent.Gold"].category, "Währung")
        self.assertTrue(by["UHealthComponent.MaxHealth"].is_max)
        self.assertGreater(by["UHealthComponent.Health"].score, by["UHealthComponent.MaxHealth"].score)
        self.assertLess(by["UHealthBarWidget.Health"].score, by["UHealthComponent.Health"].score - 5)  # UI abgewertet
        self.assertTrue(by["UWeaponComponent.ClipSize"].is_max)
        self.assertNotIn("AActor.CustomTimeDilation", keys)
        comp = uecheat.companions(s, by["UHealthComponent.Health"])
        self.assertEqual(comp[0].name, "MaxHealth")
        fn = uecheat.find_functions(s)
        names = [(a, b) for a, b, _c, _d in fn]
        self.assertIn(("UHealthComponent", "TakeDamage"), names)
        self.assertIn(("UWalletComponent", "SpendCurrency"), names)

    def test_words(self):
        self.assertEqual(uecheat.words("CurrentHealthPercent"), ["current", "health", "percent"])
        self.assertEqual(uecheat.words("bIsDead"), ["is", "dead"])
        self.assertEqual(uecheat.words("HP"), ["hp"])

if __name__ == "__main__":
    unittest.main()
