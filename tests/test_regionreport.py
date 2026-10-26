import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import regionreport as R

MAPS = [{"name": "eboot.bin", "start": 0x400000, "end": 0x1400000, "prot": 5},
        {"name": "heap", "start": 0x10000000, "end": 0x50000000, "prot": 3},
        {"name": "heap", "start": 0x60000000, "end": 0x61000000, "prot": 3},
        {"name": "", "start": 0x70000000, "end": 0x70001000, "prot": 2}]


class T(unittest.TestCase):
    def test_summary_groups_and_sorts(self):
        rows = R.summarize(MAPS)
        self.assertEqual(rows[0][:3], ("heap", "rw-", 2))
        self.assertAlmostEqual(rows[0][3], 1040.0)
        self.assertEqual([r[0] for r in rows], ["heap", "eboot.bin"])      # nicht lesbare Region entfaellt

    def test_report_text(self):
        t = R.report(MAPS)
        self.assertIn("davon schreibbar: 1040 MB", t)
        self.assertIn("0x0000000010000000", t)
        self.assertLess(t.index("0x0000000010000000"), t.index("0x0000000060000000"))   # groesste zuerst

    def test_prot_text(self):
        self.assertEqual(R.prot_text(5), "r-x")


if __name__ == "__main__":
    unittest.main()
