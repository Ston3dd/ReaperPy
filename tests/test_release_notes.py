import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import release_notes as R  # noqa: E402

CL = "# Changelog\n\n## 5.10.0 - 2027-01-01\n\n### Added\n- B\n\n## 5.9.0 - 2026-10-29\n\n### Fixed\n- A\n\n## 5.8.0\n- old\n"


class T(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(R.extract(CL, "5.9.0"), "### Fixed\n- A")
        self.assertEqual(R.extract(CL, "v5.10.0"), "### Added\n- B")
        self.assertEqual(R.extract(CL, "5.8.0"), "- old")
        self.assertEqual(R.extract(CL, "5.1.0"), "")
        self.assertEqual(R.extract(CL, "5.9"), "")          # kein Teiltreffer auf 5.9.0

    def test_current_version_has_changelog_entry(self):
        import version
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertTrue(R.extract(text, version.__version__), "CHANGELOG.md braucht einen Abschnitt fuer die aktuelle Version")

    def test_workflows_exist_and_reference_real_files(self):
        for wf in ("ci.yml", "release.yml"):
            self.assertTrue((ROOT / ".github" / "workflows" / wf).is_file(), wf)
        rel = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        for f in ("buildtools.py", "ReaperPy.spec", "scripts/release_notes.py"):
            self.assertIn(f, rel)
            self.assertTrue(os.path.exists(ROOT / f), f)


if __name__ == "__main__":
    unittest.main()
