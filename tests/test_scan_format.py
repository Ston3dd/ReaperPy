"""Scanner: Adressen ohne fuehrende Nullen anzeigen (0x7F12A4 statt 00000000007F12A4)."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import tools_scan_gui as S


class T(unittest.TestCase):
    def test_fmt_addr(self):
        self.assertEqual(S.fmt_addr(0x7F12A4), "0x7F12A4")
        self.assertEqual(S.fmt_addr(0x400000), "0x400000")
        self.assertEqual(S.fmt_addr(0x7000000100), "0x7000000100")
        self.assertEqual(S.fmt_addr(0), "0x0")

    def test_round_trips_through_int_base_16(self):
        for a in (0x1, 0xB2C491, 0x7FFFFFFF0000):
            self.assertEqual(int(S.fmt_addr(a), 16), a)

    def test_no_zero_padded_address_formatting_left_in_the_scanner(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "tools_scan_gui.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIsNone(re.search(r":0?\d*16X}|:016X|:08X}", src))
        self.assertGreaterEqual(src.count("fmt_addr("), 3)           # Ergebnisliste + Cheat-Liste (+ Definition)


if __name__ == "__main__":
    unittest.main()
