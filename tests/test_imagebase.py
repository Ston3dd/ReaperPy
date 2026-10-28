import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import imagebase as IB

MAPS = [(0x400000, 0x51D0000, 5, "eboot.bin"), (0x51F0000, 0x6470000, 1, "eboot.bin"), (0x72DC000, 0x72F0000, 3, "eboot.bin"),
        (0x10000000, 0x10100000, 5, "libc.prx"), (0x200000000, 0x200014000, 3, "anon:0008009af2a1")]


class T(unittest.TestCase):
    def test_ok(self):
        r = IB.check_image_base(MAPS, 0x400000)
        self.assertEqual((r.status, r.live_base), ("ok", 0x400000))

    def test_shifted_reports_the_map_value_not_a_guess(self):
        moved = [(s + 0x10000, e + 0x10000, p, n) if n == "eboot.bin" else (s, e, p, n) for s, e, p, n in MAPS]
        r = IB.check_image_base(moved, 0x400000)
        self.assertEqual((r.status, r.live_base), ("shifted", 0x410000))
        self.assertIn("0x410000", r.message)

    def test_unnamed_maps_are_unknown_not_guessed(self):
        r = IB.check_image_base([(s, e, p) for s, e, p, _n in MAPS], 0x400000)
        self.assertEqual((r.status, r.live_base), ("unknown", None))

    def test_libs_never_count_and_dicts_work(self):
        d = [{"start": s, "end": e, "prot": p, "name": n} for s, e, p, n in MAPS if n != "eboot.bin"]
        self.assertEqual(IB.check_image_base(d, 0x400000).status, "unknown")
        d.append({"start": 0x400000, "end": 0x500000, "prot": 5, "name": "EBOOT.BIN"})
        self.assertEqual(IB.check_image_base(d, 0x400000).status, "ok")


if __name__ == "__main__":
    unittest.main()
