"""Regression: CheatCard._on_resize darf cget('wraplength') nicht als Zahl lesen (Tcl_Obj -> TypeError im Tk-Callback)."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702


class TclObj:
    """Wie _tkinter.Tcl_Obj: weder int() noch Vergleich mit Zahlen funktioniert."""
    def __int__(self): raise TypeError("int() argument must be ... not '_tkinter.Tcl_Obj'")


class T(unittest.TestCase):
    def test_on_resize_never_reads_wraplength_back(self):
        import gui
        calls = []
        lbl = types.SimpleNamespace(cget=lambda k: TclObj(), configure=lambda **k: calls.append(k))
        card = types.SimpleNamespace(lbl_name=lbl)
        for width in (400, 400, 400, 520, 520, 100):
            gui.CheatCard._on_resize(card, types.SimpleNamespace(width=width))
        self.assertEqual(calls, [{"wraplength": 282}, {"wraplength": 402}, {"wraplength": 120}])    # nur bei Aenderung


if __name__ == "__main__":
    unittest.main()
