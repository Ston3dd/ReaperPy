"""Tests: der Exporter legt Caves nur im Spiel-Image an (nicht unter der Basis, nicht in fremden Modulen)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import export_goldhen as E

BASE = 0x400000


class Backend:
    """Fake-PS5: Regionen (start, end, prot) + Speicher (Standard: Code-Bytes, Padding wo gewuenscht)."""

    def __init__(self, maps, padded):
        self.maps, self.padded = maps, set(padded)
        self.mem = {}

    def get_maps(self, force=False):
        return self.maps

    def read(self, addr, n):
        for s, e, _p in self.maps:
            if s <= addr and addr + n <= e:
                end = e
                out = bytearray(b"\x55" * n)
                if (s, e) in self.padded:                       # Padding am Region-Ende (letzte 0x800 Byte)
                    for i in range(n):
                        if addr + i >= end - 0x800:
                            out[i] = 0
                return bytes(out)
        return None


class T(unittest.TestCase):
    def maps(self):
        return [(0x0, 0x10000, 5),                              # niedrige Region UNTER der Basis (z. B. Stub/Loader)
                (BASE, BASE + 0x400000, 5),                     # Spiel-Image: Code
                (BASE + 0x400000, BASE + 0x500000, 1),          # rodata
                (BASE + 0x500000, BASE + 0x600000, 3),          # data
                (0x7000000000, 0x7000100000, 5)]                # fremdes Modul weit weg

    def alloc(self, padded, base=BASE, near=BASE + 0x1000):
        be = Backend(self.maps(), padded)
        a = E.CaveAllocator(be, log=lambda _m: None, image_base=base)
        return a, a.alloc(0x40, near)

    def test_cave_is_inside_the_image_not_below_the_base(self):
        low, img = (0x0, 0x10000), (BASE, BASE + 0x400000)
        a, (cave, size) = self.alloc([low, img])
        self.assertTrue(img[0] <= cave < img[1], hex(cave))
        self.assertFalse(a.used_outside)

    def test_the_old_behaviour_would_have_picked_the_low_region(self):
        """Regression: ohne Image-Basis (altes Verhalten) wird die groesste Luecke genommen - hier die niedrige Region."""
        be = Backend(self.maps(), [(0x0, 0x10000), (BASE, BASE + 0x400000)])
        a = E.CaveAllocator(be, log=lambda _m: None)               # image_base=None
        cave, _ = a.alloc(0x40, BASE + 0x1000)
        self.assertGreaterEqual(cave, 0)                           # funktioniert weiter (Rueckwaertskompatibel)

    def test_regions_below_base_are_never_used_even_if_only_they_have_padding(self):
        a = E.CaveAllocator(Backend(self.maps(), [(0x0, 0x10000)]), log=lambda _m: None, image_base=BASE)
        with self.assertRaises(E.ExportError) as c:
            a.alloc(0x40, BASE + 0x1000)
        self.assertIn("Spiel-Image", str(c.exception))
        self.assertIn("0x400000", str(c.exception))

    def test_foreign_module_far_away_is_not_used(self):
        a = E.CaveAllocator(Backend(self.maps(), [(0x7000000000, 0x7000100000)]), log=lambda _m: None, image_base=BASE)
        with self.assertRaises(E.ExportError):
            a.alloc(0x40, BASE + 0x1000)

    def test_fallback_above_base_outside_contiguous_image_warns(self):
        maps = [(BASE, BASE + 0x100000, 5), (BASE + 0x40000000, BASE + 0x40100000, 5)]    # 1 GiB Luecke -> nicht zusammenhaengend
        logs = []
        be = Backend(maps, [(BASE + 0x40000000, BASE + 0x40100000)])
        a = E.CaveAllocator(be, log=logs.append, image_base=BASE)
        cave, _ = a.alloc(0x40, BASE + 0x1000)
        self.assertGreaterEqual(cave, BASE + 0x40000000)
        self.assertTrue(a.used_outside)
        self.assertTrue(any("WARNUNG" in m for m in logs))

    def test_release_gives_space_back(self):
        a, (cave, size) = self.alloc([(BASE, BASE + 0x400000)])
        a.release(cave, size)
        cave2, _ = a.alloc(0x40, BASE + 0x1000)
        self.assertEqual(cave, cave2)

    def test_successive_allocations_do_not_overlap_and_stay_aligned(self):
        be = Backend(self.maps(), [(BASE, BASE + 0x400000)])
        a = E.CaveAllocator(be, log=lambda _m: None, image_base=BASE)
        c1, _ = a.alloc(0x25, BASE + 0x1000)
        c2, _ = a.alloc(0x25, BASE + 0x1000)
        self.assertEqual((c1 % 16, c2 % 16), (0, 0))
        self.assertLessEqual(c2 + 0x30, c1)

    def test_build_mods_passes_the_image_base_to_the_allocator(self):
        seen = {}
        orig = E.CaveAllocator

        class Spy(orig):
            def __init__(self, backend, log=print, image_base=None):
                seen["base"] = image_base
                super().__init__(backend, log, image_base)
        E.CaveAllocator = Spy
        try:
            E.build_mods(Backend(self.maps(), []), [], BASE, log=lambda _m: None)
        finally:
            E.CaveAllocator = orig
        self.assertEqual(seen["base"], BASE)


if __name__ == "__main__":
    unittest.main()
