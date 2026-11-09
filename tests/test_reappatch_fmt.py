"""ReapPatch-Export: bytegleich mit einer echten, von Reaper stammenden Datei."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import reappatch_fmt as R  # noqa: E402
from reapatch import ReapPatch  # noqa: E402

SAMPLE = (
    '{"info":"","name":"Inf SBA","index":0,"author":"Ston3d","isMasterCode":false,"isIgnored":false,"Variables":['
    '{"index":0,"defaultValue":0,"newValue":null,"type":6,"editor":null,"isAlwaysEnabled":false,"isStatic":false,'
    '"offsetFinder":null,"offsetFinderPtr":null,"option":null,"label":"OriginReturn","DisplayName":null,"comment":null,'
    '"baseId":"OriginSource","offset":9},'
    '{"index":0,"defaultValue":"vmovss dword ptr [r14+0x80],xmm0","newValue":"jmp OriginTarget\\r\\nnop\\r\\nnop\\r\\nnop\\r\\nnop",'
    '"type":11,"editor":null,"isAlwaysEnabled":false,"isStatic":true,"offsetFinder":null,"offsetFinderPtr":null,"option":null,'
    '"label":"OriginSource","DisplayName":null,"comment":null,"baseId":"0","offset":6194008},'
    '{"index":0,"defaultValue":"mov rax, 0x447A0000\\r\\nmovd xmm0, eax\\r\\nvmovss dword ptr [r14+0x80], xmm0\\r\\njmp OriginReturn\\r\\n",'
    '"newValue":null,"type":11,"editor":null,"isAlwaysEnabled":false,"isStatic":false,"offsetFinder":null,"offsetFinderPtr":null,'
    '"option":null,"label":"OriginTarget","DisplayName":null,"comment":null,"baseId":"","offset":0}]}')

DOC = {"name": "Inf SBA", "author": "Ston3d", "Variables": [
    {"label": "OriginSource", "offset": 6194008, "defaultValue": "vmovss dword ptr [r14+0x80],xmm0",
     "newValue": "jmp OriginTarget\nnop\nnop\nnop\nnop"},
    {"label": "OriginReturn", "offset": 9},
    {"label": "OriginTarget", "defaultValue": "mov rax, 0x447A0000\nmovd xmm0, eax\nvmovss dword ptr [r14+0x80], xmm0\njmp OriginReturn"}]}


class T(unittest.TestCase):
    def test_identical_to_reaper_file(self):
        self.assertEqual(R.dumps(DOC).decode("utf-8"), SAMPLE)

    def test_reads_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.ReapPatch")
            with open(p, "wb") as f:
                f.write(R.dumps(DOC))
            rp = ReapPatch.load(p)
        self.assertEqual(rp.origin_source[0], 6194008)
        self.assertEqual(rp.origin_return_offset, 9)
        self.assertEqual(rp.labels[0][0], "OriginTarget")
        self.assertIn("jmp OriginReturn", rp.labels[0][1])

    def test_hex_string_offset_and_extra_label_and_plain_patch(self):
        doc = {"name": "n", "author": "", "Variables": [
            {"label": "OriginSource", "offset": "0x10", "defaultValue": "90", "newValue": "jmp OriginTarget"},
            {"label": "OriginReturn", "offset": 8},
            {"label": "OriginTarget", "defaultValue": "nop\njmp Foo"}, {"label": "Foo", "defaultValue": "ret"}]}
        v = json.loads(R.dumps(doc))["Variables"]
        self.assertEqual([x["label"] for x in v], ["OriginReturn", "OriginSource", "OriginTarget", "Foo"])
        self.assertEqual(v[1]["offset"], 16)
        self.assertEqual(v[3]["defaultValue"], "ret\r\n")
        plain = R.convert({"name": "p", "Variables": [{"label": "OriginSource", "offset": 5, "defaultValue": "90", "newValue": "C3"}]})
        self.assertEqual([x["label"] for x in plain["Variables"]], ["OriginSource"])

    def test_errors(self):
        with self.assertRaises(ValueError):
            R.convert({"name": "x", "Variables": []})
        with self.assertRaises(ValueError):
            R.convert({"name": "x"})


if __name__ == "__main__":
    unittest.main()


class Folder(unittest.TestCase):
    def test_export_patches_from_loaded_files(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            src = os.path.join(d, "a.reapproj")
            with open(src, "w", encoding="utf-8") as f:
                json.dump(DOC, f)
            plain = os.path.join(d, "b.reapproj")
            with open(plain, "w", encoding="utf-8") as f:
                json.dump({"name": "Plain", "Variables": [{"label": "OriginSource", "offset": 16, "defaultValue": "74 05",
                                                           "newValue": "EB 05"}]}, f)
            ps = [ReapPatch.load(src), ReapPatch.load(plain), ReapPatch.load(src)]
            written, failed = R.export_patches(ps, out)
            self.assertEqual((len(written), failed), (3, []))
            self.assertEqual(len(set(written)), 3)                # gleiche Namen -> (2), nie ueberschreiben
            with open(os.path.join(out, "Inf SBA.ReapPatch"), "rb") as fh:
                first = fh.read().decode("utf-8")
            self.assertEqual(first, SAMPLE)                       # auch ueber den Umweg ReapPatch.load bytegleich
            rp = ReapPatch.load(os.path.join(out, "Plain.ReapPatch"))
            self.assertEqual(rp.origin_source, (16, "74 05", "EB 05"))
            self.assertEqual(rp.labels, [])

    def test_broken_patch_is_reported_not_fatal(self):
        class Bad:
            name = "Kaputt"
            origin_source = None
        with tempfile.TemporaryDirectory() as out:
            written, failed = R.export_patches([Bad()], out)
        self.assertEqual((written, failed[0][0]), ([], "Kaputt"))
