"""GAS-Attribute (FGameplayAttributeData) werden als CurrentValue/BaseValue anklickbar."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ue_quick as Q
import uecheat
import uesdk

HDR = """// ScriptStruct /Script/GameplayAbilities.GameplayAttributeData
// 0x0010 (0x0000 - 0x0010)
struct FGameplayAttributeData
{
\tuint8_t                                            Pad_0000[0x8];                // 0x0000 (0x0008) MISSED OFFSET
\tfloat                                              BaseValue;                     // 0x0008 (0x0004) [0x0028081040000214] FloatProperty
\tfloat                                              CurrentValue;                  // 0x000c (0x0004) [0x0028081040000214] FloatProperty
};

// Class /Script/Game.CoreAttributeSet
// 0x0040 (0x0030 - 0x0070) CastFlags 0x0
class UCoreAttributeSet : public UAttributeSet
{
public:
\tstruct FGameplayAttributeData                      Health;                        // 0x0050 (0x0010) [0x0020080100002034] StructProperty
\tstruct FGameplayAttributeData                      MaxHealth;                     // 0x0060 (0x0010) [0x0020080100002034] StructProperty
\tfloat                                              Plain;                         // 0x0070 (0x0004) [0x0018001040022a01] FloatProperty
};
"""


class Gas(unittest.TestCase):
    def setUp(self):
        self.sdk = uesdk.parse_header_text(HDR)

    def test_struct_wird_zu_zwei_zielen(self):
        got = Q.expand_member(self.sdk, "UCoreAttributeSet", "Health", "struct FGameplayAttributeData", 0x50)
        keys = {t.member: (t.offset, t.type, t.parent, t.sub) for t in got}
        self.assertEqual(keys["Health.CurrentValue"], (0x5C, "float", "Health", 0xC))
        self.assertEqual(keys["Health.BaseValue"], (0x58, "float", "Health", 0x8))
        self.assertTrue(all(t.writable for t in got))

    def test_alle_member_enthalten_gas(self):
        keys = {t.key for t in Q.targets_from_all_members(self.sdk)}
        self.assertIn("UCoreAttributeSet.Health.CurrentValue", keys)
        self.assertIn("UCoreAttributeSet.Plain", keys)

    def test_cheat_kandidaten_finden_health(self):
        cands = uecheat.find_candidates(self.sdk, 4.0)
        health = [c for c in cands if c.member == "Health"]
        self.assertTrue(health and "GAS" in " ".join(health[0].reasons))
        targets = Q.targets_from_candidates(self.sdk, cands)
        cur = [t for t in targets if t.key == "UCoreAttributeSet.Health.CurrentValue"]
        self.assertEqual(len(cur), 1)  # nur CurrentValue, BaseValue nicht doppelt
        self.assertFalse([t for t in targets if t.key.endswith("Health.BaseValue")])


if __name__ == "__main__":
    unittest.main()


STAT_HDR = """// ScriptStruct /Script/Game.StatValue
// 0x0008 (0x0000 - 0x0008)
struct FStatValue
{
\tfloat                                              Current;                       // 0x0000 (0x0004) [0x0018001040022a01] FloatProperty
\tfloat                                              Max;                           // 0x0004 (0x0004) [0x0018001040022a01] FloatProperty
};

// ScriptStruct /Script/Engine.Vector
// 0x000c (0x0000 - 0x000c)
struct FVector
{
\tfloat                                              X;                             // 0x0000 (0x0004) [0x0018001040022a01] FloatProperty
\tfloat                                              Y;                             // 0x0004 (0x0004) [0x0018001040022a01] FloatProperty
\tfloat                                              Z;                             // 0x0008 (0x0004) [0x0018001040022a01] FloatProperty
};

// ScriptStruct /Script/Game.AnimBlendValue
// 0x0004 (0x0000 - 0x0004)
struct FAnimBlendValue
{
\tfloat                                              Value;                         // 0x0000 (0x0004) [0x0018001040022a01] FloatProperty
};

// Class /Script/Game.StatComponent
// 0x0040 (0x0030 - 0x0070) CastFlags 0x0
class UStatComponent : public UActorComponent
{
public:
\tstruct FStatValue                                  Health;                        // 0x0040 (0x0008) [0x0018001040022a01] StructProperty
\tstruct FVector                                     Location;                      // 0x0048 (0x000c) [0x0018001040022a01] StructProperty
\tstruct FAnimBlendValue                             HealthBlend;                   // 0x0054 (0x0004) [0x0018001040022a01] StructProperty
};
"""


class AutoWrapper(unittest.TestCase):
    """Beliebige Wrapper-Structs werden ohne Eintrag von Hand erkannt, Engine-Mathe/Animation nicht."""

    def setUp(self):
        self.sdk = uesdk.parse_header_text(STAT_HDR)

    def test_eigener_stat_struct(self):
        got = Q.expand_member(self.sdk, "UStatComponent", "Health", "struct FStatValue", 0x40)
        self.assertEqual([(t.member, t.offset) for t in got], [("Health.Current", 0x40), ("Health.Max", 0x44)])

    def test_engine_mathe_und_animation_bleiben_aussen(self):
        self.assertEqual(Q.expand_member(self.sdk, "UStatComponent", "Location", "struct FVector", 0x48), [])
        self.assertEqual(Q.expand_member(self.sdk, "UStatComponent", "HealthBlend", "struct FAnimBlendValue", 0x54), [])

    def test_kandidat_mit_wrapper(self):
        cands = [c for c in uecheat.find_candidates(self.sdk, 4.0) if c.cls == "UStatComponent"]
        self.assertEqual({c.member for c in cands}, {"Health"})  # nur der echte Wert, nicht Location/HealthBlend
        targets = Q.targets_from_candidates(self.sdk, cands)
        self.assertEqual([t.key for t in targets], ["UStatComponent.Health.Current"])
