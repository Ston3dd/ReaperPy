"""GoldHEN-Export: Eine zweite Cave darf nie auf der Cave der Item-Trainer-BASIS landen."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import export_goldhen as G


class Backend:
    pid = 1

    def get_maps(self, force=False):
        return [(0x400000, 0x68A8000, 5)]

    def read(self, a, n):
        zero_from = 0x68A8000 - 0x4000                       # letzte 16 KB der Region sind leer
        return bytes(0 if a + i >= zero_from else 0x55 for i in range(n))


class Reserved(unittest.TestCase):
    def test_second_cave_does_not_overlap_reserved_base(self):
        al = G.CaveAllocator(Backend(), log=lambda _m: None, image_base=0x400000)
        al.reserve(0x68A5D80, 8830)                          # BASIS-Cave: 0x68a5d80 .. 0x68a7ffe
        cave, need = al.alloc(52, 0x500000)
        self.assertTrue(cave + need <= 0x68A5D80 or cave >= 0x68A7FFE, hex(cave))
        again, need2 = al.alloc(64, 0x500000)
        self.assertTrue(again + need2 <= cave)

    def test_without_reservation_it_would_take_the_tail(self):
        al = G.CaveAllocator(Backend(), log=lambda _m: None, image_base=0x400000)
        cave, _n = al.alloc(52, 0x500000)
        self.assertEqual(cave, 0x68A7FC0)                    # genau der Platz aus dem fehlerhaften Export


if __name__ == "__main__":
    unittest.main()
