"""Mehr Wert-Begriffe (Hunger/Durst, weitere Waehrungen, EXP-Punkte, Ausdauer-Varianten) werden bei Unreal gefunden."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import uecheat
import uesdk

HDR = """// Class /Script/Game.SurvivalStats
// 0x0040 (0x0030 - 0x0070) CastFlags 0x0
class USurvivalStats : public UActorComponent
{
public:
\tfloat                                              Hunger;                        // 0x0100 (0x0004) [0x0018001040022a01] FloatProperty
\tfloat                                              Thirst;                        // 0x0104 (0x0004) [0x0018001040022a01] FloatProperty
\tint32_t                                            Diamonds;                      // 0x0108 (0x0004) [0x0018001040022a01] IntProperty
\tint32_t                                            SkillPoints;                   // 0x010c (0x0004) [0x0018001040022a01] IntProperty
\tint32_t                                            PerkPoints;                    // 0x0110 (0x0004) [0x0018001040022a01] IntProperty
\tfloat                                              Vigor;                         // 0x0114 (0x0004) [0x0018001040022a01] FloatProperty
\tfloat                                              Oxygen;                        // 0x0118 (0x0004) [0x0018001040022a01] FloatProperty
};
"""


class Words(unittest.TestCase):
    def test_new_words_are_candidates(self):
        sdk = uesdk.parse_header_text(HDR)
        got = {c.member: c.category for c in uecheat.find_candidates(sdk, 4.0)}
        self.assertEqual(got.get("Hunger"), "Hunger/Durst")
        self.assertEqual(got.get("Thirst"), "Hunger/Durst")
        self.assertEqual(got.get("Diamonds"), "Währung")
        self.assertEqual(got.get("SkillPoints"), "Erfahrung")
        self.assertEqual(got.get("PerkPoints"), "Erfahrung")
        self.assertEqual(got.get("Vigor"), "Ausdauer")
        self.assertEqual(got.get("Oxygen"), "Ausdauer")

    def test_cheat_menu_offers_hunger_category(self):
        import cheatmenu
        self.assertIn("Hunger/Durst", [c[0] for c in cheatmenu.GAME_CATS])


if __name__ == "__main__":
    unittest.main()
