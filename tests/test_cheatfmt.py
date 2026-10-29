import os, sys, tempfile, unittest, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cheatfmt as C, gh_import
from pathlib import Path

DOC = C.new_doc("Test Game", "CUSA12345", "01.05", "eboot.bin", ["Alice", "Bob"], [
    {"name": "Infinite HP", "type": "checkbox", "memory": [
        {"offset": "751BF8", "section": 0, "on": "90909090", "off": "FF4B1C89"}]},
    {"name": "Cave & <Test>", "type": "checkbox", "memory": [
        {"offset": "10", "section": 0, "on": "E9 01 02 03 04 90 90 90", "off": "0000000000000000"},
        {"offset": "20", "section": 0, "on": "C3", "off": "55"}]},
])


class T(unittest.TestCase):
    def test_key_iv_lengths(self):
        self.assertEqual(len(C.MC4_KEY), 32)
        self.assertEqual(len(C.MC4_IV), 16)

    def test_shn_roundtrip(self):
        text = C.build_shn(DOC)
        self.assertIn("<ValueOn>90-90-90-90</ValueOn>", text)
        back = C.parse_shn(text)
        self.assertEqual(back["id"], "CUSA12345")
        self.assertEqual(back["credits"], ["Alice", "Bob"])
        self.assertEqual(back["mods"][0]["memory"][0]["off"], "FF4B1C89")
        self.assertEqual(back["mods"][1]["name"], "Cave & <Test>")      # Sonderzeichen ueberleben in SHN
        self.assertEqual(len(back["mods"][1]["memory"]), 2)

    def test_mc4_roundtrip_and_sanitize(self):
        raw = C.build_mc4(DOC)
        text = C.decrypt_mc4(raw)
        back = C.parse_shn(text)
        self.assertEqual(back["mods"][0]["name"], "Infinite HP")
        self.assertEqual(back["mods"][1]["name"], "Cave + (Test)")      # mc4: Sonderzeichen entschaerft
        self.assertEqual(back["mods"][1]["memory"][0]["on"], "E901020304909090")

    def test_json_roundtrip(self):
        back = C.parse_json(C.build_json(DOC))
        self.assertEqual(back["mods"][1]["memory"][1]["on"], "C3")
        self.assertEqual(back["version"], "01.05")

    def test_check(self):
        errs, _ = C.check(DOC, "shn")
        self.assertEqual(errs, [])
        bad = dict(DOC, id="XXXX1", version="1")
        errs, _ = C.check(bad, "mc4")
        self.assertEqual(len(errs), 2)
        sec = json.loads(json.dumps(DOC)); sec["mods"][0]["memory"][0]["section"] = 1
        self.assertTrue(C.check(sec, "json")[0])
        self.assertFalse(C.check(sec, "shn")[0])

    def test_files_and_detect(self):
        with tempfile.TemporaryDirectory() as d:
            for fmt in ("json", "shn", "mc4"):
                p = os.path.join(d, C.default_filename(DOC, fmt))
                C.save_file(DOC, p, fmt)
                self.assertEqual(C.detect(p), fmt)
                self.assertEqual(len(C.load_file(p)["mods"]), 2)
            self.assertEqual(C.default_filename(DOC, "mc4"), "CUSA12345_01.05.mc4")
            # mc4 ohne Endung wird am Inhalt erkannt
            raw = os.path.join(d, "noext")
            Path(raw).write_bytes(C.build_mc4(DOC))
            self.assertEqual(C.detect(raw), "mc4")
            self.assertEqual(len(C.load_file(raw)["mods"]), 2)

    def test_import_into_patches(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.mc4"); C.save_file(DOC, p, "mc4")
            notes = []
            w, sk = gh_import.import_into(d, p, 0x400000, 0x400000, notes=notes)
            self.assertEqual(len(w), 2)
            data = json.loads(Path(os.path.join(d, w[0])).read_text(encoding="utf-8"))
            self.assertIn("Variables", data)

    def test_other_section_skipped(self):
        doc = json.loads(json.dumps(DOC)); doc["mods"][0]["memory"][0]["section"] = 2
        notes = []
        out = gh_import.convert(doc, notes=notes)
        self.assertEqual(len(out), 1)
        self.assertTrue(notes and "Section" in notes[0])


if __name__ == "__main__":
    unittest.main()
