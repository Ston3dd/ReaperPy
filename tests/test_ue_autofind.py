"""Live-Suche von GObjects/GNames (ohne Offsets) und Member-Offsets aus der FProperty-Kette."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import test_ue_live as TL
import ue_live as L
import ue_quick as Q
import ue_world as W


class AutoFind(unittest.TestCase):
    def setUp(self):
        self.im, self.ref, self.sdk, self.c = W.world()
        self.sdk.offsets.clear()  # keine offsets.json: alles muss live gefunden werden
        self.maps = [(TL.BASE, TL.BASE + 0x2000, 3), (TL.HEAP, TL.HEAP + 0x200000, 3)]
        self.c.get_maps = lambda: self.maps

    def test_findet_gobjects_und_gnames(self):
        live = L.UELive(self.c.read_memory, TL.BASE, self.sdk, log=lambda m: None)
        live.setup([TL.BASE], maps=self.maps)
        self.assertEqual(live.live_found["gnames_rva"], 0x400)
        live.build_index()
        self.assertTrue(live.find_class("UHealthComponent"))

    def test_ohne_maps_weiter_fehler(self):
        live = L.UELive(self.c.read_memory, TL.BASE, self.sdk, log=lambda m: None)
        with self.assertRaises(L.UELiveError):
            live.setup([TL.BASE])

    def test_neustart_sucht_neu(self):
        class P(W.Proj):
            pass

        proj = P(self.sdk)
        a = Q.connect_live(self.c, proj, log=lambda m: None)
        self.assertIs(Q.connect_live(self.c, proj, log=lambda m: None, cached=a), a)
        self.c.pid = 99  # neues Spiel
        self.assertIsNot(Q.connect_live(self.c, proj, log=lambda m: None, cached=a), a)

    def test_member_offset_live(self):
        live = L.UELive(self.c.read_memory, TL.BASE, self.sdk, log=lambda m: None)
        live.setup([TL.BASE], maps=self.maps)
        live.build_index()
        cls = live.find_class("UHealthComponent")

        def name(s, at):
            raw = s.encode()
            self.im.w(TL.HEAP + at, struct.pack("<H", len(raw) << 6) + raw)
            return at // 2

        n_health, n_gold = name("Health", 0x1F000), name("Gold", 0x1F020)
        f0 = TL.HEAP + 0x1F800
        for i, (n, off) in enumerate([(n_health, 0x90), (n_gold, 0x88)]):
            a = f0 + i * 0x100
            self.im.w(a + 0x18, struct.pack("<Q", f0 + 0x100 if i == 0 else 0))
            self.im.w(a + 0x20, struct.pack("<II", n, 0))
            self.im.w(a + 0x44, struct.pack("<i", off))
        self.im.w(cls + 0x50, struct.pack("<Q", f0))
        live.drop_cache()
        live.setup([TL.BASE], maps=self.maps)
        live.build_index()
        self.assertEqual(live.member_offset("UHealthComponent", "Health"), 0x90)  # Header sagt 0x80
        self.assertIsNone(live.member_offset("UHealthComponent", "GibtEsNicht"))
        rows = Q.find_instances(live, W.tgt(self.sdk, "Health"))
        self.assertTrue(rows and rows[0]["off"] == 0x90 and rows[0]["off_live"])


if __name__ == "__main__":
    unittest.main()
