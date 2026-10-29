"""Tests: Spiel-Profile (Speichern/Laden) und Cheat-Listen-Logik (Suche, Favoriten, Gruppen, Hotkeys)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cheatlist as CL
import gameprofile as GP
from pathlib import Path


class Profile(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_key_for(self):
        self.assertEqual(GP.key_for("ppsa01234", "x"), "PPSA01234")
        self.assertEqual(GP.key_for("CUSA12345"), "CUSA12345")
        self.assertEqual(GP.key_for("", "Super Game: Deluxe/Edition?"), "Super Game_ Deluxe_Edition")
        self.assertEqual(GP.key_for("", ""), "default")
        self.assertEqual(GP.key_for("PPSA1", "Name"), "Name")                 # ungueltige ID -> Projektname

    def test_roundtrip(self):
        gp = GP.GameProfile("PPSA01234", self.d)
        gp.title, gp.notes = "Super Game", "Boss 2: Phase 3\nSchwachstelle Ruecken"
        gp.toggle_favorite("Inf Hp.reapproj")
        gp.set_group("Inf Hp.reapproj", "Leben")
        gp.set_hotkey("Inf Hp.reapproj", "F5")
        gp.ui = {"group": "Leben", "only_fav": True}
        gp.discover = {"sig": "1/2/3", "json": "{}"}
        self.assertTrue(gp.save())
        b = GP.load("PPSA01234", self.d)
        self.assertEqual((b.title, b.notes), ("Super Game", "Boss 2: Phase 3\nSchwachstelle Ruecken"))
        self.assertEqual((b.favorites, b.groups, b.hotkeys), ({"Inf Hp.reapproj"}, {"Inf Hp.reapproj": "Leben"}, {"Inf Hp.reapproj": "F5"}))
        self.assertEqual((b.ui, b.discover), ({"group": "Leben", "only_fav": True}, {"sig": "1/2/3", "json": "{}"}))
        self.assertGreater(b.updated, 0)
        self.assertFalse(os.path.exists(gp.path() + ".tmp"))

    def test_missing_and_broken_files(self):
        gp = GP.load("PPSA99999", self.d)
        self.assertEqual((gp.notes, gp.favorites), ("", set()))
        p = os.path.join(self.d, "PPSA11111.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{kaputt")
        gp = GP.load("PPSA11111", self.d)
        self.assertEqual(gp.favorites, set())
        self.assertTrue(os.path.exists(p + ".bad"))                              # Original bleibt erhalten
        with open(p, "w", encoding="utf-8") as f:
            json.dump([1, 2], f)
        self.assertEqual(GP.load("PPSA11111", self.d).notes, "")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"favorites": ["a", 5], "groups": None, "discover": {"zu": "wenig"}}, f)
        gp = GP.load("PPSA11111", self.d)
        self.assertEqual((gp.favorites, gp.groups, gp.discover), ({"a"}, {}, None))

    def test_hotkey_conflicts_and_cleanup(self):
        gp = GP.GameProfile("k", self.d)
        self.assertIsNone(gp.set_hotkey("a", "F5"))
        self.assertEqual(gp.set_hotkey("b", "F5"), "a")                         # Konflikt: nichts gesetzt
        self.assertNotIn("b", gp.hotkeys)
        self.assertIsNone(gp.set_hotkey("a", "F5"))                             # gleicher Cheat darf neu setzen
        gp.clear_hotkey("a")
        self.assertIsNone(gp.set_hotkey("b", "F5"))
        gp.toggle_favorite("x"); gp.toggle_favorite("b"); gp.set_group("x", "G")
        gp.forget_missing(["b"])
        self.assertEqual((gp.favorites, gp.groups, gp.hotkeys), ({"b"}, {}, {"b": "F5"}))

    def test_group_names_and_unsetting(self):
        gp = GP.GameProfile("k", self.d)
        gp.set_group("a", "zeta"); gp.set_group("b", "Alpha"); gp.set_group("c", "Alpha")
        self.assertEqual(gp.group_names(), ["Alpha", "zeta"])
        gp.set_group("a", "  ")
        self.assertEqual(gp.group_names(), ["Alpha"])
        self.assertFalse(gp.toggle_favorite("a") is False)                      # erster Aufruf: an
        self.assertFalse(gp.toggle_favorite("a"))                               # zweiter: aus

    def test_save_failure_is_reported_not_raised(self):
        blocker = os.path.join(self.d, "datei")
        Path(blocker).write_text("", encoding="utf-8")
        self.assertFalse(GP.GameProfile("k", os.path.join(blocker, "x")).save())


ITEMS = [("/p/Inf Hp.reapproj", "Inf Hp"), ("/p/Inf Shield.reapproj", "Inf Shield"), ("/p/Gold x10.reapproj", "Gold x10"),
         ("/p/Alle Items.reapproj", "Alle Items"), ("/p/Schnell.reapproj", "Schnell")]


class ListLogic(unittest.TestCase):
    def gp(self):
        gp = GP.GameProfile("k", None)
        gp.set_group("Inf Hp.reapproj", "Leben")
        gp.set_group("Inf Shield.reapproj", "Leben")
        gp.set_group("Gold x10.reapproj", "Geld")
        gp.toggle_favorite("Schnell.reapproj")
        return gp

    def names(self, order):
        return [p.rsplit("/", 1)[-1][:-9] for p in order]

    def test_default_order_favorites_then_groups_then_ungrouped(self):
        order = CL.visible_order(ITEMS, self.gp())
        self.assertEqual(self.names(order), ["Schnell", "Gold x10", "Inf Hp", "Inf Shield", "Alle Items"])

    def test_search_matches_name_and_group_case_insensitive(self):
        gp = self.gp()
        self.assertEqual(self.names(CL.visible_order(ITEMS, gp, "inf")), ["Inf Hp", "Inf Shield"])
        self.assertEqual(self.names(CL.visible_order(ITEMS, gp, "GELD")), ["Gold x10"])               # Treffer ueber den Gruppennamen
        self.assertEqual(CL.visible_order(ITEMS, gp, "gibtsnicht"), [])
        self.assertEqual(len(CL.visible_order(ITEMS, gp, "   ")), 5)

    def test_group_and_favorite_filters(self):
        gp = self.gp()
        self.assertEqual(self.names(CL.visible_order(ITEMS, gp, group="Leben")), ["Inf Hp", "Inf Shield"])
        self.assertEqual(self.names(CL.visible_order(ITEMS, gp, group=CL.NO_GROUP)), ["Schnell", "Alle Items"])
        self.assertEqual(self.names(CL.visible_order(ITEMS, gp, only_fav=True)), ["Schnell"])
        self.assertEqual(CL.visible_order(ITEMS, gp, group="Leben", only_fav=True), [])
        self.assertEqual(self.names(CL.visible_order(ITEMS, None)), sorted(self.names(CL.visible_order(ITEMS, None)), key=str.lower))

    def test_windows_paths_use_the_file_name(self):
        gp = GP.GameProfile("k", None)
        gp.toggle_favorite("B.reapproj")
        order = CL.visible_order([("C:\\x\\A.reapproj", "A"), ("C:\\x\\B.reapproj", "B")], gp)
        self.assertEqual(order[0], "C:\\x\\B.reapproj")


class Hotkeys(unittest.TestCase):
    def spec(self, k, s, plat="win32"):
        return CL.spec_from_event(k, s, plat)

    def test_spec_from_event(self):
        self.assertEqual(self.spec("F5", 0), "F5")
        self.assertEqual(self.spec("F5", 0x4), "Ctrl+F5")
        self.assertEqual(self.spec("F5", 0x4 | 0x1), "Ctrl+Shift+F5")
        self.assertEqual(self.spec("a", 0x4), "Ctrl+A")
        self.assertEqual(self.spec("A", 0x1 | 0x4), "Ctrl+Shift+A")
        self.assertEqual(self.spec("a", 0x20000), "Alt+A")                      # Windows: Alt = 0x20000
        self.assertEqual(self.spec("a", 0x8, "win32"), "A")                     # Windows: 0x8 ist NumLock, kein Alt
        self.assertEqual(self.spec("a", 0x8, "linux"), "Alt+A")
        self.assertEqual(self.spec("1", 0x4), "Ctrl+1")
        self.assertEqual(self.spec("F5", 0x8, "win32"), "F5")                   # NumLock stoert F-Tasten nicht
        self.assertIsNone(self.spec("Control_L", 0x4))
        self.assertIsNone(self.spec("Shift_R", 0x1))
        self.assertIsNone(self.spec("", 0))

    def test_valid_spec_rules(self):
        for ok in ("F1", "F12", "F24", "Ctrl+F5", "Ctrl+1", "Alt+X", "Ctrl+Shift+A"):
            self.assertTrue(CL.valid_spec(ok), ok)
        for bad in ("", "A", "1", "Shift+A", "Escape", "Tab", "Return", "Ctrl+C", "Ctrl+V", "Alt+F4", "F25", "F0", "Ctrl+Tab"):
            self.assertFalse(CL.valid_spec(bad), bad)

    def test_typing_in_text_fields_blocks_hotkeys(self):
        for c in ("Entry", "TEntry", "TCombobox", "Text"):
            self.assertTrue(CL.typing_in_text(c))
        for c in ("Button", "Frame", "Canvas", "Tk"):
            self.assertFalse(CL.typing_in_text(c))


if __name__ == "__main__":
    unittest.main()
