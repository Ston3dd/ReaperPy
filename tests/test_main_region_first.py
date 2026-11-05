"""Die Cave gehoert in den Spielcode, nicht in kleine Zusatzregionen ('(aux)'), auch wenn dort mehr Platz scheint."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cave_trainer as T


class MainRegionFirst(unittest.TestCase):
    def setUp(self):
        self.mem = {(0x400000, 0x68A8000): bytearray(b"\x90" * (0x68A8000 - 0x400000)),
                    (0x918C000, 0x9190000): bytearray(0x4000)}            # (aux): komplett leer, groesser als der Schwanz
        self.mem[(0x400000, 0x68A8000)][-0x2600:] = bytes(0x2600)          # Spielcode: nur 9728 Byte frei
        self.span = [(0x400000, 0x68A8000, 5), (0x918C000, 0x9190000, 5)]

    def read(self, a, n):
        for (s, e), v in self.mem.items():
            if s <= a and a + n <= e:
                return bytes(v[a - s:a - s + n])
        raise OSError(hex(a))

    def test_main_preferred_although_aux_is_bigger(self):
        sl = T.Slots(self.read, self.span, lambda _m: None)
        self.assertEqual(sl.code_capacity(), 0x2600)
        cave, _n = sl.alloc_code(0x2000, 0x500000)
        self.assertTrue(0x400000 <= cave < 0x68A8000)

    def test_aux_only_when_main_is_full(self):
        self.mem[(0x400000, 0x68A8000)][-0x2600:] = b"\x90" * 0x2600
        sl = T.Slots(self.read, self.span, lambda _m: None)
        cave, _n = sl.alloc_code(0x1000, 0x500000)
        self.assertTrue(0x918C000 <= cave < 0x9190000)


if __name__ == "__main__":
    unittest.main()
