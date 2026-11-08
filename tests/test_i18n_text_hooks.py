"""Tests: Texte werden schon beim Setzen uebersetzt (kein Aufblitzen von Deutsch nach einer Suche) - auch Rechtsklick-Menues."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import tools_i18n as T

CLASSES = {"label": "Label", "button": "Button", "labelframe": "Labelframe", "ttk::label": "TLabel", "menu": "Menu",
           "ttk::treeview": "Treeview", "ttk::notebook": "TNotebook"}


def make_tk():
    """Kleiner Ersatz mit den Signaturen von tkinter.Misc/BaseWidget/Menu und ttk.Treeview/Notebook (frische Klassen je Test,
    weil install_text_hooks die Klassen veraendert)."""
    class Misc:
        def __init__(self):
            self.opts, self.kids, self.cls = {}, [], "Frame"

        def configure(self, cnf=None, **kw):
            if cnf is None and not kw:
                return dict(self.opts)
            if isinstance(cnf, dict):
                self.opts.update(cnf)
            self.opts.update(kw)
        config = configure

        def __setitem__(self, k, v):
            self.configure({k: v})

        def cget(self, k):
            return self.opts.get(k, "")

        def winfo_class(self):
            return self.cls

        def winfo_children(self):
            return self.kids

    class BaseWidget(Misc):
        def __init__(self, master, widgetName, cnf={}, kw={}, extra=()):  # noqa: B006
            Misc.__init__(self)
            self.cls = CLASSES.get(widgetName, widgetName)
            self.opts.update(cnf)
            self.opts.update(kw)
            if master is not None:
                master.kids.append(self)

    class Label(BaseWidget):
        def __init__(self, master=None, cnf={}, **kw):  # noqa: B006
            BaseWidget.__init__(self, master, "label", cnf, kw)

    class Frame(BaseWidget):
        def __init__(self, master=None, **kw):
            BaseWidget.__init__(self, master, "frame", {}, kw)

    class TtkLabel(BaseWidget):
        def __init__(self, master=None, **kw):
            BaseWidget.__init__(self, master, "ttk::label", {}, kw)

    class Menu(BaseWidget):
        def __init__(self, master=None, **kw):
            BaseWidget.__init__(self, master, "menu", {}, kw)
            self.entries = []

        def add(self, itemType, cnf={}, **kw):  # noqa: B006
            d = {"type": itemType}
            d.update(cnf)
            d.update(kw)
            self.entries.append(d)

        def add_command(self, cnf={}, **kw):  # noqa: B006
            self.add("command", cnf or kw)

        def add_separator(self, cnf={}, **kw):  # noqa: B006
            self.add("separator", cnf or kw)

        def insert(self, index, itemType, cnf={}, **kw):  # noqa: B006
            d = {"type": itemType}
            d.update(cnf)
            d.update(kw)
            self.entries.insert(index, d)

        def index(self, i):
            if i == "end":
                return len(self.entries) - 1 if self.entries else None
            return int(i)

        def type(self, i):
            return self.entries[i]["type"]

        def entrycget(self, i, opt):
            return self.entries[i].get(opt, "")

        def entryconfigure(self, index, cnf=None, **kw):
            if cnf is None and not kw:
                return dict(self.entries[self.index(index)])
            if isinstance(cnf, dict):
                self.entries[self.index(index)].update(cnf)
            self.entries[self.index(index)].update(kw)
        entryconfig = entryconfigure

    class Treeview(BaseWidget):
        def __init__(self, master=None, columns=(), **kw):
            BaseWidget.__init__(self, master, "ttk::treeview", {}, dict(kw, columns=columns))
            self.heads = {c: {"text": c} for c in columns}

        def heading(self, column, option=None, **kw):
            if option is not None:
                return self.heads[column].get(option)
            self.heads[column].update(kw)

    class Notebook(BaseWidget):
        def __init__(self, master=None, **kw):
            BaseWidget.__init__(self, master, "ttk::notebook", {}, kw)
            self.tab_text = {}

        def add(self, child, **kw):
            self.tab_text[str(id(child))] = kw.get("text", "")
            self.kids.append(child)
            self._ids = getattr(self, "_ids", []) + [child]

        def tabs(self):
            return tuple(str(id(c)) for c in getattr(self, "_ids", []))

        def tab(self, tab_id, option=None, **kw):
            if option is not None:
                return self.tab_text[tab_id]
            self.tab_text[tab_id] = kw.get("text", self.tab_text[tab_id])

    tk = types.SimpleNamespace(Misc=Misc, BaseWidget=BaseWidget, Label=Label, Frame=Frame, Menu=Menu)
    ttk = types.SimpleNamespace(Treeview=Treeview, Notebook=Notebook, Label=TtkLabel)
    return tk, ttk


class Lang:
    def __init__(self, lang):
        self.lang = lang

    def __enter__(self):
        self.old = T.lang()
        T.set_lang(self.lang)

    def __exit__(self, *a):
        T.set_lang(self.old)


DE_TEXT = "Alle auftauen"                  # -> "Unfreeze all"
DE_TEXT2 = "Schreiber finden"              # -> "Find writers"


class TextHooks(unittest.TestCase):
    def setUp(self):
        self.tk, self.ttk = make_tk()
        T.install_text_hooks(self.tk, self.ttk)
        self.en, self.en2 = T.translate(DE_TEXT), T.translate(DE_TEXT2)       # nur zur Sicherheit: die Beispiele muessen uebersetzbar sein

    def test_examples_are_translatable(self):
        with Lang("en"):
            self.assertNotEqual(T.translate(DE_TEXT), DE_TEXT)

    def test_german_mode_changes_nothing(self):
        lab = self.tk.Label(None, text=DE_TEXT)
        lab.configure(text=DE_TEXT2)
        self.assertEqual(lab.opts["text"], DE_TEXT2)
        m = self.tk.Menu()
        m.add_command(label=DE_TEXT)
        self.assertEqual(m.entries[0]["label"], DE_TEXT)

    def test_new_widget_is_translated_at_once(self):
        with Lang("en"):
            lab = self.tk.Label(None, text=DE_TEXT)
            self.assertEqual(lab.opts["text"], T.translate(DE_TEXT))
            ttk_lab = self.ttk.Label(None, text=DE_TEXT)
            self.assertEqual(ttk_lab.opts["text"], T.translate(DE_TEXT))

    def test_configure_and_item_assignment_are_translated_at_once(self):
        with Lang("en"):
            lab = self.tk.Label(None, text="x")
            lab.configure(text=DE_TEXT2)
            self.assertEqual(lab.opts["text"], T.translate(DE_TEXT2))
            lab["text"] = DE_TEXT
            self.assertEqual(lab.opts["text"], T.translate(DE_TEXT))
            lab.config({"text": DE_TEXT2})
            self.assertEqual(lab.opts["text"], T.translate(DE_TEXT2))

    def test_widgets_without_text_and_other_options_are_untouched(self):
        with Lang("en"):
            fr = self.tk.Frame(None, text=DE_TEXT)                 # Frame hat keinen sichtbaren Text -> nicht anfassen
            self.assertEqual(fr.opts["text"], DE_TEXT)
            lab = self.tk.Label(None, text=DE_TEXT, width=7)
            self.assertEqual(lab.opts["width"], 7)
            self.assertEqual(lab.configure(), lab.opts)            # Abfrage ohne Argumente geht unveraendert durch

    def test_switching_back_to_german_restores_the_original(self):
        root = self.tk.Frame()
        with Lang("en"):
            lab = self.tk.Label(root, text=DE_TEXT)
            lab.configure(text=DE_TEXT2)
            T.apply_to(root)
            self.assertEqual(lab.opts["text"], T.translate(DE_TEXT2))
        T.apply_to(root)                                           # jetzt wieder DE
        self.assertEqual(lab.opts["text"], DE_TEXT2)

    def test_apply_to_does_not_take_its_own_english_text_as_the_original(self):
        root = self.tk.Frame()
        lab = self.tk.Label(root, text=DE_TEXT)                    # in DE erzeugt
        with Lang("en"):
            T.apply_to(root)
            self.assertEqual(lab.opts["text"], T.translate(DE_TEXT))
        T.apply_to(root)
        self.assertEqual(lab.opts["text"], DE_TEXT)

    def test_context_menu_entries_are_translated_when_built(self):
        with Lang("en"):
            m = self.tk.Menu()
            m.add_command(label=DE_TEXT)
            m.add_separator()
            m.add_command(label=DE_TEXT2, command=print)
            self.assertEqual(m.entries[0]["label"], T.translate(DE_TEXT))
            self.assertEqual(m.entries[2]["label"], T.translate(DE_TEXT2))
            self.assertEqual(m.entries[2]["command"], print)       # andere Optionen bleiben
            m.insert(0, "command", label=DE_TEXT2)
            self.assertEqual(m.entries[0]["label"], T.translate(DE_TEXT2))
            m.entryconfigure(1, label=DE_TEXT2)
            self.assertEqual(m.entries[1]["label"], T.translate(DE_TEXT2))

    def test_menu_entries_go_back_to_german(self):
        root = self.tk.Frame()
        with Lang("en"):
            m = self.tk.Menu(root)
            m.add_command(label=DE_TEXT)
            m.add_separator()
            m.add_command(label=DE_TEXT2)
            T.apply_to(root)
            self.assertEqual(m.entries[2]["label"], T.translate(DE_TEXT2))
        T.apply_to(root)
        self.assertEqual([e.get("label") for e in m.entries], [DE_TEXT, None, DE_TEXT2])

    def test_menu_made_before_the_hook_is_translated_by_the_pass(self):
        tk, ttk = make_tk()                                        # Menue entsteht, bevor irgendein Hook installiert ist
        root = tk.Frame()
        m = tk.Menu(root)
        m.add_command(label=DE_TEXT)
        T.install_text_hooks(tk, ttk)
        with Lang("en"):
            T.apply_to(root)
            self.assertEqual(m.entries[0]["label"], T.translate(DE_TEXT))
        T.apply_to(root)
        self.assertEqual(m.entries[0]["label"], DE_TEXT)

    def test_treeview_headings_and_notebook_tabs(self):
        with Lang("en"):
            tv = self.ttk.Treeview(None, columns=("a", "b"))
            tv.heading("a", text="ADRESSE")
            self.assertEqual(tv.heads["a"]["text"], T.translate("ADRESSE"))
            self.assertEqual(tv.heading("a", "text"), T.translate("ADRESSE"))     # Abfrage geht durch
            nb = self.ttk.Notebook()
            page = self.tk.Frame()
            nb.add(page, text=DE_TEXT)
            self.assertEqual(nb.tab_text[nb.tabs()[0]], T.translate(DE_TEXT))

    def test_short_or_non_text_values_pass_through(self):
        with Lang("en"):
            lab = self.tk.Label(None, text="OK")
            lab.configure(text=42)
            self.assertEqual(lab.opts["text"], 42)

    def test_install_is_idempotent_and_harmless_without_real_tk(self):
        T.install_text_hooks(self.tk, self.ttk)
        T.install_text_hooks(self.tk, self.ttk)
        with Lang("en"):
            lab = self.tk.Label(None, text=DE_TEXT)
            self.assertEqual(lab.opts["text"], T.translate(DE_TEXT))     # nicht doppelt uebersetzt / verschachtelt
        T.install_text_hooks(types.SimpleNamespace(), None)              # ghost tk: kein Misc/BaseWidget -> nichts passiert


if __name__ == "__main__":
    unittest.main()
