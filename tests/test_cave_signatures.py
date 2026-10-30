"""Tests fuer Signatur-Anker, verschobene Funktionen und die Vorschau (cave_trainer).

Eigene Datei, damit tests/test_cave_trainer.py unveraendert bleibt; die Helfer (FakeImage, make_options) kommen von dort.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import cave_trainer as T
from test_cave_trainer import FakeImage, make_options


class SignatureAnchorTests(unittest.TestCase):
    """plan(client=...) erzeugt Signaturen mit Wildcards; Verschiebungen werden erkannt und lassen sich korrigieren."""

    class _Client:
        def __init__(self, img): self.img = img
        def read_memory(self, a, n): return self.img.read(a, n)
        def get_maps(self): return self.img.maps

    def _image(self):
        import random
        rnd = random.Random(7)
        img = FakeImage()
        for a in (img.impl, img.pe, img.BASE + 0x3000):
            img.write(a, bytes(rnd.randrange(1, 255) for _ in range(160)))       # eindeutiger Code
        return img

    def _plan(self, img, **kw):
        opts = make_options()
        return T.plan(img.read, img.maps, img.BASE, opts, img.impl, img.pe, [img.slot], log=lambda _m: None, settle=0,
                      client=self._Client(img), **kw)

    def test_plan_with_client_writes_named_signatures(self):
        import aob
        img = self._image()
        p = self._plan(img)
        self.assertIsInstance(p.anchors, dict)
        self.assertEqual(sorted(p.anchors), ["item_function", "process_event"])
        rva, sig = p.anchors["item_function"]
        self.assertEqual(rva, img.impl - img.BASE)
        pat, mask = aob.parse_pattern(sig)
        self.assertGreaterEqual(len(pat), T.ANCHOR_LEN)
        doc = T.spec_document(p)
        self.assertEqual(doc["anchors"]["process_event"]["rva"], hex(img.pe - img.BASE))
        res = T.check_anchors(self._Client(img), img.maps, img.BASE, doc)
        self.assertEqual({r[1] for r in res}, {"ok"})
        self.assertIsNone(T.anchor_problem(res, img.BASE))

    def test_plan_without_client_keeps_fixed_bytes(self):
        img = self._image()
        p = T.plan(img.read, img.maps, img.BASE, make_options(), img.impl, img.pe, [img.slot], log=lambda _m: None, settle=0)
        self.assertIsInstance(p.anchors, list)

    def test_non_unique_code_falls_back_to_fixed_bytes(self):
        img = FakeImage()                                           # impl und pe bestehen aus gleichen Wiederholungen
        logs = []
        p = T.plan(img.read, img.maps, img.BASE, make_options(), img.impl, img.pe, [img.slot], log=logs.append, settle=0,
                   client=self._Client(img))
        self.assertEqual(sorted(p.anchors), ["item_function", "process_event"])
        self.assertTrue(any("feste Bytes" in m for m in logs))
        self.assertEqual(p.anchors["item_function"][1].split()[:4], ["55", "48", "89", "E5"])

    def test_check_project_reads_signature_anchors(self):
        import tempfile
        img = self._image()
        p = self._plan(img)
        with tempfile.TemporaryDirectory() as d:
            T.write_project(d, p, game="t")
            r = T.check_project(d, img.read, img.BASE)
            self.assertTrue(r["ok_version"], r["problems"])
            self.assertEqual(r["anchors_checked"], 2)
            img.write(img.impl, bytes(range(1, 100)))              # Funktion wurde ueberschrieben/aendert sich
            r = T.check_project(d, img.read, img.BASE)
            self.assertFalse(r["ok_version"])
            self.assertIn("item_function", r["problems"][0])

    def test_moved_function_is_found_and_trainer_rows_are_remapped(self):
        import ue_cavegen
        img = self._image()
        p = self._plan(img)
        doc = T.spec_document(p)
        old_rva = img.impl - img.BASE
        new_addr = img.BASE + 0x4000                                # Update: Funktion liegt jetzt woanders
        img.write(new_addr, img.read(img.impl, 160))
        img.write(img.impl, bytes(160))
        res = T.check_anchors(self._Client(img), img.maps, img.BASE, doc)
        by = {n: (s, a) for n, s, a in res}
        self.assertEqual(by["item_function"], ("moved", new_addr))
        self.assertEqual(by["process_event"][0], "ok")
        moved, rest = T.moved_rvas(doc, res, img.BASE)
        self.assertEqual(moved, {old_rva: new_addr - img.BASE})
        self.assertEqual(rest, [])
        row = ue_cavegen.CallRow("Apfel", ue_cavegen.CallSpec(old_rva, []), fname=bytes(8))
        other = ue_cavegen.CallRow("Birne", ue_cavegen.CallSpec(0x7777, []), fname=bytes(8))
        new, n = T.remap_options([T.Option("Obst", [row, other])], moved)
        self.assertEqual(n, 1)
        self.assertEqual([r.call_impl_rva for r in new[0].rows], [new_addr - img.BASE, 0x7777])
        self.assertEqual(new[0].rows[0].alias, "Apfel")

    def test_missing_or_ambiguous_is_not_auto_fixable(self):
        doc = {"anchors": {"a": {"rva": "0x10", "aob": "AA"}, "b": {"rva": "0x20", "aob": "BB"}}}
        res = [("a", "missing", 0), ("b", "ambiguous", 0x500)]
        moved, rest = T.moved_rvas(doc, res, 0x400000)
        self.assertEqual(moved, {})
        self.assertEqual(rest, [("a", "missing"), ("b", "ambiguous")])


class PreviewTests(unittest.TestCase):
    def test_prot_text_and_region(self):
        self.assertEqual([T.prot_text(x) for x in (5, 3, 7, 1, 0)], ["r-x", "rw-", "rwx", "r--", "---"])
        maps = [(0x400000, 0x410000, 5), (0x410000, 0x420000, 3)]
        self.assertEqual(T.region_info(maps, 0x400010), (0x400000, 0x410000, "r-x"))
        self.assertEqual(T.region_info(maps, 0x41ffff), (0x410000, 0x420000, "rw-"))
        self.assertIsNone(T.region_info(maps, 0x500000))

    def test_preview_describes_cave_and_flag_without_writing(self):
        img = FakeImage()
        p = T.plan(img.read, img.maps, img.BASE, make_options(), img.impl, img.pe, [img.slot], log=lambda _m: None, settle=0)
        before = {k: bytes(v) for k, v in img.mem.items()}
        pv = T.preview(p, img.maps)
        self.assertEqual(pv["cave"], p.cave)
        self.assertEqual(pv["cave_region"][2], "r-x")
        self.assertFalse(pv["cave_writable"])
        self.assertEqual(pv["flag_region"][2], "rw-")
        text = "\n".join(T.preview_lines(pv))
        self.assertIn("Region 0x400000-0x410000 (r-x)", text)
        self.assertNotIn("WARNUNG", text)
        self.assertEqual({k: bytes(v) for k, v in img.mem.items()}, before)           # Vorschau veraendert nichts

    def test_preview_warns_about_writable_cave(self):
        img = FakeImage()
        p = T.plan(img.read, img.maps, img.BASE, make_options(), img.impl, img.pe, [img.slot], log=lambda _m: None, settle=0)
        text = "\n".join(T.preview_lines(T.preview(p, [(img.BASE, img.BASE + 0x20000, 7)])))
        self.assertIn("WARNUNG", text)
        self.assertIn("(rwx)", text)


if __name__ == "__main__":
    unittest.main()
