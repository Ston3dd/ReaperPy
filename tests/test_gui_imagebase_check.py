"""Regression: _check_image_base nutzt imagebase.check_image_base (frueher AttributeError 'check_base' beim Verbinden)."""
import os
import queue
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702

MAPS = [(0x400000, 0x51D0000, 5, "eboot.bin"), (0x10000000, 0x10100000, 5, "libc.prx")]


class T(unittest.TestCase):
    def run_check(self, maps, base):
        import gui
        q = queue.Queue()
        me = types.SimpleNamespace(q=q, IMAGE_BASE=base,
                                   backend=types.SimpleNamespace(client=types.SimpleNamespace(get_maps_named=lambda: maps)))
        gui.App._check_image_base(me)
        out = []
        while not q.empty():
            out.append(q.get())
        return out

    def test_matching_base_logs_info_only(self):
        out = self.run_check(MAPS, 0x400000)
        self.assertEqual([m[0] for m in out], ["log"])
        self.assertEqual(out[0][1][1], "info")

    def test_shifted_base_is_corrected_via_queue(self):
        out = self.run_check(MAPS, 0x500000)
        self.assertEqual(out[-1], ("imgbase", 0x400000))

    def test_unknown_names_only_warn(self):
        out = self.run_check([(s, e, p) for s, e, p, _n in MAPS], 0x400000)
        self.assertEqual([m[0] for m in out], ["log"])
        self.assertEqual(out[0][1][1], "warn")


if __name__ == "__main__":
    unittest.main()
