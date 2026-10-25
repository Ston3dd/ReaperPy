"""ue_promising: nur Werte aus Klassen mit echten Instanzen, Rauschen raus, universelle Engine-Werte."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import test_ue_live as TL
import ue_live as L
import ue_promising as P
import ue_world as W
import uesdk

GHOST = """// Class /Script/Game.GhostComponent
// 0x0010 (0x0090 - 0x0080) CastFlags 0x0
class UGhostComponent : public UActorComponent
{
public:
\tfloat                                              Health;                        // 0x0080 (0x0004) [0x0018001040022a01] FloatProperty
\tint32                                              Money;                         // 0x0084 (0x0004) [0x0018001040022a01] IntProperty
};
// Class /Script/Engine.Canvas
// 0x0010 (0x0090 - 0x0080) CastFlags 0x0
class UCanvas : public UActorComponent
{
public:
\tfloat                                              ClipX;                         // 0x0080 (0x0004) [0x0018001040022a01] FloatProperty
};
"""


class Promising(unittest.TestCase):
    def setUp(self):
        self.im, self.ref, self.sdk, self.c = W.world()
        uesdk.parse_header_text(GHOST, self.sdk)
        self.live = L.UELive(self.c.read_memory, TL.BASE, self.sdk, gobjects_rva=0x100, gnames_rva=0x400, log=lambda m: None)
        self.live.setup([TL.BASE])
        self.live.build_index()

    def test_nur_klassen_mit_instanzen(self):
        res = P.find_promising(self.live, self.sdk, read=self.c.read_memory, min_score=4.0)
        keys = {p.key for p in res}
        self.assertIn("UHealthComponent.Health", keys)
        self.assertNotIn("UGhostComponent.Health", keys)  # Klasse existiert im SDK, aber kein Objekt im Spiel
        self.assertNotIn("UGhostComponent.Money", keys)

    def test_instanzzahl_und_stichprobe(self):
        res = {p.key: p for p in P.find_promising(self.live, self.sdk, read=self.c.read_memory, min_score=4.0)}
        p = res["UHealthComponent.Health"]
        self.assertEqual(p.count, 2)  # inkl. Blueprint-Unterklasse, ohne Default__
        self.assertTrue(p.sample)

    def test_rauschen_und_universal(self):
        self.assertTrue(P.is_noise(self.live, self.sdk, "UCanvas", "ClipX"))
        self.assertTrue(P.is_noise(self.live, self.sdk, "UFoo", "MipLevel"))
        self.assertFalse(P.is_noise(self.live, self.sdk, "UHealthComponent", "Health"))
        # universelle Werte ohne passende Klasse im Spiel werden still ausgelassen
        res = P.find_promising(self.live, self.sdk, read=None, min_score=4.0)
        self.assertFalse([p for p in res if p.universal])

    def test_ohne_read_funktioniert(self):
        res = P.find_promising(self.live, self.sdk, read=None, min_score=4.0)
        self.assertIn("UHealthComponent.Health", {p.key for p in res})


if __name__ == "__main__":
    unittest.main()
