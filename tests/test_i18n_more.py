"""Tests: die zusaetzlichen Englisch-Eintraege (tools_i18n_en_more.py) gehoeren zu echten Texten im Code und sind sauber."""
import ast
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tools_i18n as T
from tools_i18n_en import EN
from tools_i18n_en_more import EN_MORE

ROOT = os.path.join(os.path.dirname(__file__), "..")


def code_strings():
    """Alle Textkonstanten der Programmdateien im Hauptordner (ohne Tests)."""
    found = set()
    for name in os.listdir(ROOT):
        if not name.endswith(".py") or name.startswith("tools_i18n_en"):
            continue
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                found.add(n.value)
    return found


class MoreEntries(unittest.TestCase):
    def test_every_key_is_a_text_in_the_code(self):
        known = code_strings()
        stale = sorted(k for k in EN_MORE if k not in known)
        self.assertEqual(stale, [], "Eintraege ohne passenden Text im Code (umbenannt oder entfernt?)")

    def test_values_have_no_umlauts_and_keep_placeholders(self):
        for k, v in EN_MORE.items():
            self.assertIsNone(re.search("[äöüßÄÖÜ]", v), v)
            self.assertEqual(k.count("{}"), v.count("{}"), k)
            self.assertEqual(k.count("%d"), v.count("%d"), k)

    def test_merged_into_the_main_dictionary(self):
        for k, v in EN_MORE.items():
            self.assertEqual(EN[k], v)

    def test_translation_is_used_in_english_mode_only(self):
        key = "keine Funktion zum Geben von Items im SDK"
        old = T.lang()
        try:
            T.set_lang("en")
            self.assertEqual(T.translate(key), "no function for giving items in the SDK")
            T.set_lang("de")
            self.assertEqual(T.translate(key), key)
        finally:
            T.set_lang(old)


if __name__ == "__main__":
    unittest.main()
