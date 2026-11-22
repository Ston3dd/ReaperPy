"""Jeder Tab mit geteilter Anleitung springt zu SEINEM Abschnitt - in Deutsch und Englisch."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import howto  # noqa: E402


def headings(slug, lang):
    return re.findall(r"^## (.+)$", howto.load(slug, lang), re.M)


class Sections(unittest.TestCase):
    def test_every_hint_finds_a_heading(self):
        for tab, hints in howto.SECTION_HINTS.items():
            slug = howto.topic_for(tab)
            self.assertTrue(slug, tab)
            for lang in ("de", "en"):
                self.assertIsNotNone(howto.find_section(headings(slug, lang), hints), (tab, lang))

    def test_unity_and_unreal_do_not_mix(self):
        h = headings("values-and-live", "de")
        self.assertIn("CHEAT-MENÜ", h[howto.find_section(h, howto.section_for("★ CHEAT-MENÜ"))])
        self.assertTrue(h[howto.find_section(h, howto.section_for("★ UNITY CHEAT-MENÜ"))].startswith("Unity"))
        self.assertFalse(h[howto.find_section(h, howto.section_for("★ CHEAT-MENÜ"))].startswith("Unity"))

    def test_shared_topics_have_hints(self):
        shared = {}
        for tab, slug in howto.TAB_TOPICS.items():
            shared.setdefault(slug, []).append(tab)
        for slug, tabs in shared.items():
            if slug in ("values-and-live", "advanced-tools"):
                for tab in tabs:
                    if tab not in ("FORTGESCHRITTEN",):
                        self.assertTrue(howto.section_for(tab), tab)

    def test_no_match(self):
        self.assertIsNone(howto.find_section(["A", "B"], ("zzz",)))
        self.assertIsNone(howto.find_section([], ("a",)))


if __name__ == "__main__":
    unittest.main()
