import io
import unittest
from contextlib import redirect_stdout

import patch_engine
from patch_engine import fmt_bytes


class FmtBytesTests(unittest.TestCase):
    def test_short_is_unchanged(self):
        self.assertEqual(fmt_bytes(b"\x48\x89\xe5"), "48 89 e5")
        self.assertEqual(fmt_bytes(b""), "")
        self.assertEqual(fmt_bytes(bytes(32)), " ".join(["00"] * 32))

    def test_long_is_cut_with_remainder(self):
        out = fmt_bytes(bytes(400))
        self.assertTrue(out.startswith(" ".join(["00"] * 32)))
        self.assertTrue(out.endswith("... (+368 bytes)"))
        self.assertLess(len(out), 140)

    def test_accepts_bytearray_and_custom_limit(self):
        self.assertEqual(fmt_bytes(bytearray(b"\x01\x02\x03\x04"), limit=2), "01 02 ... (+2 bytes)")

    def test_verify_log_is_short_for_big_blocks(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = patch_engine._verify_write(type("B", (), {"read": lambda s, a, n: bytes(400)})(), 0x40ff30, bytes(399) + b"\x01", "t")
        self.assertFalse(ok)
        self.assertLess(len(buf.getvalue()), 600)
        self.assertIn("(+368 bytes)", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
