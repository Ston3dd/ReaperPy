"""Tests: der Tab ANLEITUNGEN baut sich auf, zeigt die Sprache des Programms, sucht und folgt Verweisen (mit einem kleinen tkinter-Ersatz)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import tkinter as tk

import howto
import tools_i18n as T


class FakeText(ghost_tk.W):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.buf, self.tags, self.state = [], set(), "normal"

    def configure(self, **k):
        self.state = k.get("state", self.state)
    config = configure

    def insert(self, index, text, tags=()):
        assert self.state == "normal", "Text ist gesperrt"
        self.buf.append((text, tuple(tags)))

    def delete(self, *a):
        self.buf = []

    def tag_configure(self, name, **k):
        self.tags.add(name)

    def tag_names(self, *a):
        return list(self.tags)

    def tag_bind(self, name, seq, fn):
        self.__dict__.setdefault("binds", {})[(name, seq)] = fn

    def search(self, *a, **k):
        return ""

    def text(self):
        return "".join(t for t, _ in self.buf)


class FakeList(ghost_tk.W):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.items, self.sel = [], ()

    def insert(self, _i, text):
        self.items.append(text)

    def delete(self, *a):
        self.items, self.sel = [], ()

    def curselection(self):
        return self.sel

    def selection_clear(self, *a):
        self.sel = ()

    def selection_set(self, i):
        self.sel = (i,)


class FakeVar(ghost_tk.Var):
    def __init__(self, master=None, value=None, **k):
        super().__init__(master, value, **k)
        self.cbs = []

    def set(self, v):
        self.v = v
        for cb in self.cbs:
            cb()

    def trace_add(self, _mode, cb):
        self.cbs.append(lambda: cb())


import tools_howto_gui as G  # noqa: E402


class Win:
    def __init__(self):
        self.logs = []

    def log(self, msg, kind="info"):
        self.logs.append((kind, msg))


class Lang:
    def __init__(self, lang):
        self.lang = lang

    def __enter__(self):
        self.old = T.lang()
        T.set_lang(self.lang)

    def __exit__(self, *a):
        T.set_lang(self.old)


class Tab(unittest.TestCase):
    def setUp(self):
        p = mock.patch.multiple(tk, Text=FakeText, Listbox=FakeList, StringVar=FakeVar)      # nur waehrend dieser Tests
        p.start()
        self.addCleanup(p.stop)

    def make(self):
        win = Win()
        tab = G.HowToTab(None, win)
        return tab, win

    def test_builds_and_shows_the_first_steps_in_german(self):
        with Lang("de"):
            tab, _ = self.make()
            self.assertEqual(len(tab.lb.items), len(howto.articles("de")))
            self.assertIn("Erste Schritte", tab.lb.items)
            self.assertIn("Erste Schritte", tab.txt.text())
            self.assertEqual(tab._slug, "first-steps")
            self.assertEqual(tab.lb.sel, (0,))

    def test_every_article_renders_in_both_languages(self):
        for lang in ("de", "en"):
            with Lang(lang):
                tab, win = self.make()
                for a in howto.articles(lang):
                    tab.show(a["slug"])
                    self.assertGreater(len(tab.txt.text()), 500, (lang, a["slug"]))
                    self.assertIn(a["title"], tab.txt.text())
                self.assertEqual(win.logs, [])
                self.assertEqual(tab.txt.state, "disabled")                     # nur lesen

    def test_language_switch_reloads_list_and_text(self):
        with Lang("de"):
            tab, _ = self.make()
            tab.show("find-value")
            self.assertIn("Einen Wert finden", tab.lb.items)
        with Lang("en"):
            tab._tick()
            self.assertIn("Find a value", tab.lb.items)
            self.assertIn("Find a value", tab.txt.text())
            self.assertEqual(tab._slug, "find-value")                            # derselbe Artikel, andere Sprache

    def test_search_filters_the_list_and_marks_words(self):
        with Lang("en"):
            tab, _ = self.make()
            tab.v_search.set("watchpoint")
            self.assertIn("The debugger", tab.lb.items)
            self.assertLess(len(tab.lb.items), len(howto.articles("en")))
            self.assertIn("hit", tab.txt.tags)
            tab.lb.sel = (tab._shown.index("debugger"),)
            tab._on_pick()
            self.assertEqual(tab._slug, "debugger")
            tab.v_search.set("zzzzqqqq")
            self.assertEqual(tab.lb.items, [])
            self.assertEqual(tab.v_found.get(), "Keine Treffer")
            tab.v_search.set("")
            self.assertEqual(len(tab.lb.items), len(howto.articles("en")))

    def test_links_open_the_other_article(self):
        with Lang("en"):
            tab, _ = self.make()
            self.assertIn("link:find-value", tab.txt.tags)
            tab.txt.binds[("link:find-value", "<Button-1>")](None)
            self.assertEqual(tab._slug, "find-value")

    def test_unknown_article_is_logged_not_raised(self):
        with Lang("de"):
            tab, win = self.make()
            tab.show("gibt-es-nicht")
            self.assertEqual(win.logs[-1][0], "err")
            self.assertEqual(tab._slug, "first-steps")

    def test_tick_survives_a_destroyed_tab(self):
        tab, _ = self.make()
        tab.winfo_exists = lambda: False
        tab._tick()


class App:
    def __init__(self):
        self.root = None
        self.logs = []

    def log_msg(self, msg, tag=None):
        self.logs.append((tag, msg))


class Window(unittest.TestCase):
    """Die Anleitungen haengen am Hauptfenster (eigenes Fenster), nicht mehr als Tab im Werkzeug-Fenster."""

    def setUp(self):
        p = mock.patch.multiple(tk, Text=FakeText, Listbox=FakeList, StringVar=FakeVar)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(G, "style_ttk", lambda _w: None)                       # ttk-Styles kann der tkinter-Ersatz nicht
        q.start()
        self.addCleanup(q.stop)

    def test_window_builds_opens_a_given_article_and_logs_to_the_main_window(self):
        with Lang("en"):
            app = App()
            w = G.HowToWindow(app, "debugger")
            self.assertEqual(w.tab._slug, "debugger")
            w.show("find-value")
            self.assertEqual(w.tab._slug, "find-value")
            w.tab.show("gibt-es-nicht")
            self.assertEqual(app.logs[-1][0], "err")

    def test_main_window_has_the_button_and_the_tools_window_has_no_how_to_tab(self):
        def src(name):
            with open(os.path.join(os.path.dirname(__file__), "..", name), encoding="utf-8") as f:
                return f.read()
        self.assertIn('"btn_howto"', src("gui.py"))
        self.assertIn("def open_howto", src("gui.py"))
        self.assertNotIn("HowToTab", src("tools_gui.py"))
        self.assertIn("self.app.open_howto(", src("tools_gui.py"))
        i18n = src("i18n.py")
        self.assertEqual(i18n.count('"btn_howto"'), 2)                               # DE und EN


if __name__ == "__main__":
    unittest.main()
