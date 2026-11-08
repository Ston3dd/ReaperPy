"""Tests: Anleitungen (docs/howto) - beide Sprachen gleich aufgebaut, Verweise und Knopf-Namen stimmen, Parser und Suche."""
import ast
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import howto
import tools_i18n as T
from tools_i18n_en import EN

ROOT = os.path.join(os.path.dirname(__file__), "..")


def md(lang, slug):
    return howto.load(slug, lang)


def slugs(lang):
    return [a["slug"] for a in howto.articles(lang)]


class Content(unittest.TestCase):
    def test_both_languages_have_the_same_articles_in_the_same_order(self):
        self.assertEqual(slugs("de"), slugs("en"))
        self.assertGreaterEqual(len(slugs("de")), 12)

    def test_every_article_has_a_title_and_text(self):
        for lang in howto.LANGS:
            for a in howto.articles(lang):
                self.assertTrue(a["title"] and a["title"] != a["slug"], (lang, a["slug"]))
                text = md(lang, a["slug"])
                self.assertGreater(len(text), 600, (lang, a["slug"]))
                self.assertTrue(text.startswith("# "), (lang, a["slug"]))
                self.assertEqual(text.count("```") % 2, 0, (lang, a["slug"]))      # Codebloecke sind geschlossen

    def test_german_and_english_have_the_same_structure(self):
        for slug in slugs("de"):
            de, en = md("de", slug), md("en", slug)
            self.assertEqual(len(re.findall(r"(?m)^## ", de)), len(re.findall(r"(?m)^## ", en)), slug)
            self.assertEqual(de.count("```"), en.count("```"), slug)
            self.assertEqual(re.findall(r"\(howto:([a-z0-9-]+)\)", de), re.findall(r"\(howto:([a-z0-9-]+)\)", en), slug)
            self.assertEqual(len(re.findall(r"(?m)^> ", de)), len(re.findall(r"(?m)^> ", en)), slug)

    def test_all_links_point_to_existing_articles(self):
        for lang in howto.LANGS:
            known = set(slugs(lang))
            for slug in known:
                for target in re.findall(r"\(howto:([a-z0-9-]+)\)", md(lang, slug)):
                    self.assertIn(target, known, (lang, slug, target))

    def test_every_tab_topic_exists(self):
        known = set(slugs("de"))
        for tab, slug in howto.TAB_TOPICS.items():
            self.assertIn(slug, known, tab)

    def test_tab_topics_use_real_tab_names(self):
        with open(os.path.join(ROOT, "tools_gui.py"), encoding="utf-8") as f:
            names = {c.value for c in ast.walk(ast.parse(f.read())) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        for tab in howto.TAB_TOPICS:
            self.assertIn(tab, names, f"Tab '{tab}' kommt in tools_gui.py nicht vor")

    def test_no_emoji_or_symbol_characters(self):
        bad = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2900-\u297F\u25A0-\u25FF\u2460-\u24FF\u2B00-\u2BFF]")
        for lang in howto.LANGS:
            for slug in slugs(lang):
                self.assertIsNone(bad.search(md(lang, slug)), (lang, slug))

    def test_no_game_specific_names(self):
        for lang in howto.LANGS:
            for slug in slugs(lang):
                text = md(lang, slug).lower()
                for bad in ("palworld", "stellar", "deadcraft", "ppsa06929", "silent hill"):
                    self.assertNotIn(bad, text, (lang, slug))


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^0-9A-Za-zÄÖÜäöüß/?]+", " ", s)).strip().upper()


def _program_strings():
    out = set()
    for fn in os.listdir(ROOT):
        if fn.endswith(".py") and not fn.startswith("tools_i18n_en"):
            with open(os.path.join(ROOT, fn), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            out |= {c.value for c in ast.walk(tree) if isinstance(c, ast.Constant) and isinstance(c.value, str) and len(c.value) < 80}
    return out


TERMS = {"NOP", "AOB", "RIP", "DE / EN", "BASE", "BASIS", "PID", "FLOAT", "INT32"}          # Fachwoerter, keine Knoepfe


class ButtonNames(unittest.TestCase):
    """Fett gedruckte GROSSBUCHSTABEN-Namen in den Anleitungen sind Namen von Tabs und Knoepfen - es muss sie wirklich geben."""

    @classmethod
    def setUpClass(cls):
        de = _program_strings()
        old = T.lang()
        T.set_lang("en")
        try:
            en = {T.translate(s) for s in de}
        finally:
            T.set_lang(old)
        cls.known = {"de": {_norm(s) for s in de | set(EN)}, "en": {_norm(s) for s in en | set(EN.values())}}

    def names(self, lang):
        for slug in slugs(lang):
            if slug == "glossary":
                continue
            for tok in re.findall(r"\*\*([^*]+)\*\*", md(lang, slug)):
                whole = tok.strip()
                # 'TOP 10 → CHEAT LIST' ist EIN Knopf; 'UNREAL → ITEMS' ist ein Weg ueber zwei Tabs
                parts = [whole] if self.exists(lang, whole) else [p.strip() for p in tok.split("→")]
                for part in parts:
                    letters = re.sub(r"[^A-Za-zÄÖÜäöüß]", "", part)
                    if len(letters) >= 3 and letters == letters.upper() and part.upper() not in TERMS:
                        yield slug, part

    def exists(self, lang, name):
        """Der Name ist ein Text im Programm - oder der Anfang eines laengeren (z. B. die Kopfzeile 'SPEICHERBEREICHE  -  was ...')."""
        n = _norm(name)
        return any(k == n or k.startswith(n + " ") for k in self.known[lang])

    def check(self, lang):
        missing = sorted({(s, p) for s, p in self.names(lang) if not self.exists(lang, p)})
        self.assertEqual(missing, [], f"Namen in den Anleitungen ({lang}), die es im Programm nicht gibt")

    def test_german_names_exist(self):
        self.check("de")

    def test_english_names_exist(self):
        self.check("en")


class Parser(unittest.TestCase):
    MD = """# Titel *kursiv*

Ein **fetter** Absatz mit `code` und
Fortsetzung, [Link](howto:glossary).

## Liste
- eins **a**
  weiter
- zwei

1. erst
2. dann

> **Tipp:** Das hilft.
> Zweite Zeile.

> **Achtung:** Vorsicht!

> Nur ein Hinweis.

```
mov eax, 1
```
---
"""

    def test_blocks(self):
        kinds = [k for k, _ in howto.parse(self.MD)]
        self.assertEqual(kinds, ["h1", "p", "h2", "ul", "ol", "tip", "warn", "note", "code", "hr"])

    def test_spans(self):
        self.assertEqual(howto.spans("a **b** `c` [d](howto:x-y) *e*"),
                         [("a ", ""), ("b", "b"), (" ", ""), ("c", "code"), (" ", ""), ("d", "link:x-y"), (" ", ""), ("e", "i")])
        self.assertEqual(howto.spans("2*3*4"), [("2*3*4", "")])               # Sterne zwischen Zahlen sind keine Kursivschrift

    def test_list_items_and_continuation(self):
        blocks = dict((k, c) for k, c in howto.parse(self.MD))
        self.assertEqual(len(blocks["ul"]), 2)
        self.assertEqual("".join(t for t, _s in blocks["ul"][0]), "eins a weiter")

    def test_code_block_is_kept_verbatim(self):
        code = [c for k, c in howto.parse(self.MD) if k == "code"][0]
        self.assertEqual(code, "mov eax, 1")

    def test_all_real_articles_parse_to_something(self):
        for lang in howto.LANGS:
            for slug in slugs(lang):
                kinds = {k for k, _ in howto.parse(md(lang, slug))}
                self.assertIn("h1", kinds)
                self.assertIn("p", kinds)
                if slug != "glossary":                                          # das Glossar besteht nur aus Begriffen
                    self.assertIn("h2", kinds)


class Search(unittest.TestCase):
    def test_finds_by_title_and_content(self):
        hits = howto.search("pointer", "en")
        self.assertIn("pointers", [h["slug"] for h in hits])
        self.assertEqual(hits[0]["slug"], "pointers")                          # Titel-Treffer zuerst
        self.assertTrue(all(h["snippet"] for h in hits))

    def test_all_words_must_match_and_case_does_not_matter(self):
        self.assertTrue(howto.search("WATCHPOINT debugger", "en"))
        self.assertEqual(howto.search("zzzzqqqq", "en"), [])
        self.assertEqual(howto.search("   ", "en"), [])

    def test_german_search(self):
        self.assertIn("find-value", [h["slug"] for h in howto.search("erster scan", "de")])

    def test_unknown_language_and_missing_article(self):
        self.assertEqual(howto.articles("xx"), howto.articles("de"))
        with self.assertRaises(KeyError):
            howto.load("gibt-es-nicht", "de")


if __name__ == "__main__":
    unittest.main()
