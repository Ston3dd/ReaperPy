"""Tests fuer autocodes: Spiel beim Verbinden erkennen und Codes automatisch anzeigen (oder leer lassen)."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import autocodes as A
from pathlib import Path


class T(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        for d, files in {"PPSA11111 - Super Game": ["Unendlich Leben.reapproj", "Gold.reapproj"],
                         "PPSA33333 - Leer": [],
                         "Mein Zeug": ["x.reapproj"]}.items():
            os.makedirs(os.path.join(self.root, d))
            for f in files:
                Path(os.path.join(self.root, d, f)).write_text("", encoding="utf-8")
        self.cfg = {"projects_root": self.root, "library_dir": os.path.join(self.root, "lib"), "projects": {}}

    def fg(self, pid=7, tid="PPSA11111", name="Super Game", ver="01.02"):
        return lambda client: (pid, tid, name, ver)

    def test_game_with_codes_is_found(self):
        d = A.detect(None, self.cfg, {}, foreground_fn=self.fg())
        self.assertEqual((d.title_id, d.name, d.version, d.error), ("PPSA11111", "Super Game", "01.02", ""))
        self.assertEqual(len(d.entry.patches), 2)
        self.assertEqual(A.decide(d, "")[0], "load")
        self.assertEqual(A.decide(d, "irgendwas PPSA99999")[0], "load")        # Codes des erkannten Spiels haben Vorrang

    def test_game_without_codes_leaves_list_empty_or_closes_foreign_project(self):
        d = A.detect(None, self.cfg, {}, foreground_fn=self.fg(tid="PPSA33333"))
        self.assertIsNone(d.entry)                                              # Ordner existiert, aber ohne Patches
        self.assertEqual(A.decide(d, ""), ("keep", None))                       # ist schon leer
        self.assertEqual(A.decide(d, "Super Game PPSA11111")[0], "clear")       # Projekt eines anderen Spiels -> zu
        self.assertEqual(A.decide(d, "PPSA33333 Leer")[0], "keep")              # gehoert zu diesem Spiel
        self.assertEqual(A.decide(d, "Mein Zeug")[0], "keep")                   # ohne Titel-ID: nichts zerstoeren

    def test_unknown_game_id(self):
        d = A.detect(None, self.cfg, {}, foreground_fn=self.fg(tid="PPSA55555"))
        self.assertIsNone(d.entry)
        self.assertEqual(A.decide(d, "PPSA11111")[0], "clear")

    def test_detection_problems_never_raise_and_change_nothing(self):
        def boom(_c):
            raise OSError("keine Antwort")
        d = A.detect(None, self.cfg, {}, foreground_fn=boom)
        self.assertIn("keine Antwort", d.error)
        self.assertEqual(A.decide(d, "PPSA11111")[0], "keep")
        d = A.detect(None, self.cfg, {}, foreground_fn=self.fg(pid=0, tid=""))
        self.assertEqual(d.error, "kein Spiel im Vordergrund")
        self.assertEqual(A.decide(d, "PPSA11111")[0], "keep")

    def test_library_failure_keeps_everything(self):
        class Bad:
            def __init__(self, *a): pass
            def scan(self): raise RuntimeError("Platte weg")
        d = A.detect(None, self.cfg, {}, foreground_fn=self.fg(), library_cls=Bad)
        self.assertEqual(d.title_id, "PPSA11111")
        self.assertIn("Platte weg", d.error)
        self.assertEqual(A.decide(d, "PPSA22222")[0], "keep")

    def test_titleid_is_uppercased(self):
        d = A.detect(None, self.cfg, {}, foreground_fn=self.fg(tid="ppsa11111"))
        self.assertEqual(d.title_id, "PPSA11111")
        self.assertIsNotNone(d.entry)


if __name__ == "__main__":
    unittest.main()
