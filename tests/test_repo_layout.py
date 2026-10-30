"""Wächter für die Ordnerstruktur: Testdateien gehören nach tests/ (im Hauptordner führen sie zu
'module incorrectly imported from ...' beim Testlauf, weil tests/ gleichnamige Module enthält)."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Layout(unittest.TestCase):
    def test_no_test_files_in_repo_root(self):
        stray = sorted(p.name for p in ROOT.glob("test_*.py")) + sorted(p.name for p in ROOT.glob("*_test.py"))
        self.assertEqual(stray, [], "Testdateien gehören nach tests/: " + ", ".join(stray))

    def test_test_helpers_live_in_tests(self):
        for name in ("ue_world.py", "ghost_tk.py", "i18n_harvest.py"):
            self.assertFalse((ROOT / name).exists(), f"{name} gehört nach tests/")
            self.assertTrue((ROOT / "tests" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
