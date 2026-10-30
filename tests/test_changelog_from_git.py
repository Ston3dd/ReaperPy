import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import changelog_from_git as C  # noqa: E402

MSG = """Fix anchor checks and cave placement

Added
- check_anchors() compares signatures
  with the running game
- English texts

Changed
- Cave prefers r-x regions

Fixed
- AttributeError in preflight

Tests: 685 passed. Files: cave_trainer.py"""


class T(unittest.TestCase):
    def test_parse_sections_and_continuation(self):
        r = C.parse_commit(MSG)
        self.assertEqual(r["Added"], ["check_anchors() compares signatures with the running game", "English texts"])
        self.assertEqual(r["Changed"], ["Cave prefers r-x regions"])
        self.assertEqual(r["Fixed"], ["AttributeError in preflight"])

    def test_commit_without_sections_uses_subject(self):
        self.assertEqual(C.parse_commit("Tidy up logs\n\nsome prose")["Changed"], ["Tidy up logs"])

    def test_build_merges_and_dedupes(self):
        out = C.build([MSG, "Other\n\nFixed\n- AttributeError in preflight\n- Second"], "5.9.1 - 2026-11-01")
        self.assertTrue(out.startswith("## 5.9.1 - 2026-11-01\n\n### Added\n"))
        self.assertEqual(out.count("AttributeError in preflight"), 1)
        self.assertIn("- Second", out)
        self.assertNotIn("Tests:", out)
        self.assertLess(out.index("### Added"), out.index("### Changed"))

    def test_result_is_readable_by_release_notes(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        import release_notes as R
        self.assertIn("Cave prefers", R.extract("# Changelog\n\n" + C.build([MSG], "5.9.1 - 2026-11-01"), "5.9.1"))


if __name__ == "__main__":
    unittest.main()
