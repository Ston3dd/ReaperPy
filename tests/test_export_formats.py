import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import export_goldhen as E, cheatfmt as C

MODS = [{"name": "Unendlich HP", "type": "checkbox",
         "memory": [{"offset": "751BF8", "on": "9090", "off": "FF4B"}]}]

class T(unittest.TestCase):
    def setUp(self):
        self._orig = E.build_mods
        E.build_mods = lambda *a, **k: (MODS, [])
    def tearDown(self): E.build_mods = self._orig

    def run_fmt(self, fmt, tid="CUSA12345", ver="01.05"):
        d = tempfile.mkdtemp(); p = os.path.join(d, "x." + fmt)
        doc, rep, issues = E.export(None, [], 0x400000, p, "Spiel", tid, ver, "eboot.bin", ["Ich"], fmt=fmt)
        return p, doc, issues

    def test_all_formats_roundtrip(self):
        for fmt in ("json", "shn", "mc4"):
            p, doc, issues = self.run_fmt(fmt)
            self.assertTrue(os.path.exists(p), fmt)
            back = C.load_file(p)
            self.assertEqual(back["mods"][0]["memory"][0]["on"], "9090", fmt)
            self.assertEqual(back["id"], "CUSA12345")

    def test_bad_id_not_written(self):
        p, doc, issues = self.run_fmt("mc4", tid="FOO", ver="1")
        self.assertFalse(os.path.exists(p))
        self.assertEqual(doc["mods"], [])
        self.assertTrue(any("NICHT geschrieben" in i for i in issues))

if __name__ == "__main__":
    unittest.main()
