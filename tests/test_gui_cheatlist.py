"""GUI-Logik der Cheat-Liste im Hauptfenster (ohne Display): Filter, Favoriten, Gruppen, Hotkeys, Karten-Menue."""
import os
import sys
import time
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import gameprofile as GP
import gui
from i18n import Translator


class Var:
    def __init__(self, v=""): self.v = v
    def get(self): return self.v
    def set(self, v): self.v = v


class Card:
    def __init__(self, path, name, author=""):
        self.path, self.rp = path, types.SimpleNamespace(name=name, author=author)
        self.state, self.gridded, self.clicks, self.meta = gui.St.OFF, None, 0, 0
    def grid(self, **k): self.gridded = (k["row"], k["column"])
    def grid_remove(self): self.gridded = None
    def refresh_meta(self): self.meta += 1
    def _click(self): self.clicks += 1


def make_app():
    app = object.__new__(gui.App)
    app.tr = Translator("de")
    app.logs = []
    app.log_msg = lambda m, tag=None: app.logs.append((tag, m))
    app.gp = GP.GameProfile("PPSA00001", None)
    app.gp.save = lambda: True
    app.cards = {f"/p/{n}.reapproj": Card(f"/p/{n}.reapproj", n) for n in ("Inf Hp", "Inf Shield", "Gold", "Schnell")}
    app._cols = 2
    app._hotkeys, app._last_hot = {}, ("", 0.0)
    app.v_search, app.v_group, app.v_favonly = Var(), Var(app.tr.t("filter_all")), Var(False)
    app.group_combo = types.SimpleNamespace(configure=lambda **k: setattr(app, "combo_values", k.get("values")))
    app.cards_frame = types.SimpleNamespace(columnconfigure=lambda *a, **k: None)
    return app


class T(unittest.TestCase):
    def setUp(self):
        self.app = make_app()

    def shown(self):
        return {os.path.basename(p)[:-9]: c.gridded for p, c in self.app.cards.items()}

    def test_search_hides_and_shows_cards(self):
        a = self.app
        a._grid_cards(2)
        self.assertTrue(all(v is not None for v in self.shown().values()))
        a.v_search.set("inf")
        a._apply_filter()
        s = self.shown()
        self.assertIsNone(s["Gold"])
        self.assertIsNone(s["Schnell"])
        self.assertEqual({s["Inf Hp"], s["Inf Shield"]}, {(0, 0), (0, 1)})
        a.v_search.set("")
        a._apply_filter()
        self.assertTrue(all(v is not None for v in self.shown().values()))

    def test_favorite_group_and_filters(self):
        a = self.app
        card = a.cards["/p/Schnell.reapproj"]
        a.toggle_favorite(card)
        self.assertIn("Schnell.reapproj", a.gp.favorites)
        self.assertEqual(self.shown()["Schnell"], (0, 0))                       # Favoriten zuerst
        self.assertTrue(all(c.meta >= 1 for c in a.cards.values()))
        a.v_favonly.set(True)
        a._apply_filter()
        self.assertEqual([n for n, v in self.shown().items() if v is not None], ["Schnell"])
        self.assertEqual(a.gp.ui["only_fav"], True)
        a.v_favonly.set(False)
        a.gp.set_group("Inf Hp.reapproj", "Leben")
        a._refresh_group_values()
        self.assertEqual(a.combo_values, ["Alle", "(ohne Gruppe)", "Leben"])
        a.v_group.set("Leben")
        a._apply_filter()
        self.assertEqual([n for n, v in self.shown().items() if v is not None], ["Inf Hp"])
        a.v_group.set("(ohne Gruppe)")
        a._apply_filter()
        self.assertEqual(sorted(n for n, v in self.shown().items() if v is not None), ["Gold", "Inf Shield", "Schnell"])
        self.assertEqual(a.gp.ui["group"], "(ohne Gruppe)")

    def test_group_vanishing_resets_filter_to_all(self):
        a = self.app
        a.gp.set_group("Gold.reapproj", "Geld")
        a._refresh_group_values()
        a.v_group.set("Geld")
        a.gp.set_group("Gold.reapproj", "")
        a._refresh_group_values()
        self.assertEqual(a.v_group.get(), "Alle")

    def test_hotkey_choice_validation_conflict_and_apply(self):
        a = self.app
        c1, c2 = a.cards["/p/Gold.reapproj"], a.cards["/p/Schnell.reapproj"]
        self.assertEqual(a._hotkey_chosen(c1, None), "wait")                    # nur Modifier gedrueckt: weiter warten
        self.assertEqual(a._hotkey_chosen(c1, "A"), "bad")
        self.assertEqual(a.logs[-1][0], "warn")
        self.assertEqual(a._hotkey_chosen(c1, "F5"), "ok")
        self.assertEqual(a._hotkeys, {"F5": "/p/Gold.reapproj"})
        self.assertEqual(a._hotkey_chosen(c2, "F5"), "conflict:Gold.reapproj")
        self.assertNotIn("Schnell.reapproj", a.gp.hotkeys)
        a.clear_card_hotkey(c1)
        self.assertEqual(a._hotkeys, {})

    def key(self, keysym, state=0, cls="Frame"):
        return types.SimpleNamespace(keysym=keysym, state=state, widget=types.SimpleNamespace(winfo_class=lambda: cls))

    def test_hotkey_fires_toggles_once_and_ignores_text_fields_and_repeats(self):
        a = self.app
        a._hotkey_chosen(a.cards["/p/Gold.reapproj"], "F5")
        gold = a.cards["/p/Gold.reapproj"]
        self.assertEqual(a._on_key(self.key("F5")), "break")
        self.assertEqual(gold.clicks, 1)
        self.assertEqual(a._on_key(self.key("F5")), "break")                    # Tastenwiederholung (<0,4 s)
        self.assertEqual(gold.clicks, 1)
        a._last_hot = ("F5", time.time() - 1)
        a._on_key(self.key("F5"))
        self.assertEqual(gold.clicks, 2)
        self.assertIsNone(a._on_key(self.key("F5", cls="Entry")))               # beim Tippen nichts ausloesen
        self.assertIsNone(a._on_key(self.key("F6")))
        self.assertEqual(gold.clicks, 2)
        a._hotkeys = {}
        self.assertIsNone(a._on_key(self.key("F5")))

    def test_card_menu_items_follow_state_and_profile(self):
        a = self.app
        card = types.SimpleNamespace(app=a, path="/p/Gold.reapproj", state=gui.St.OFF, rp=types.SimpleNamespace(name="Gold", author=""),
                                     _click=None, _info=None, _copy_name=None, _show_file=None)
        labels = [i[0] for i in gui.CheatCard.menu_items(card) if i[0]]
        self.assertEqual(labels, ["Aktivieren", "Info anzeigen", "★ Als Favorit markieren", "Gruppe setzen…", "Hotkey setzen…",
                                  "Namen kopieren", "Patch-Datei im Ordner zeigen"])
        a.gp.favorites.add("Gold.reapproj")
        a.gp.hotkeys["Gold.reapproj"] = "F5"
        card.state = gui.St.ON
        labels = [i[0] for i in gui.CheatCard.menu_items(card) if i[0]]
        self.assertEqual(labels[0], "Deaktivieren")
        self.assertIn("Favorit entfernen", labels)
        self.assertIn("Hotkey entfernen", labels)
        a.tr.set_lang("en")
        self.assertEqual(gui.CheatCard.menu_items(card)[0][0], "Deactivate")

    def test_refresh_meta_shows_star_group_and_hotkey(self):
        a = self.app
        a.gp.favorites.add("Gold.reapproj")
        a.gp.groups["Gold.reapproj"] = "Geld"
        a.gp.hotkeys["Gold.reapproj"] = "Ctrl+F5"
        out = {}
        lbl = lambda k: types.SimpleNamespace(configure=lambda **kw: out.setdefault(k, kw))   # noqa: E731
        card = types.SimpleNamespace(app=a, path="/p/Gold.reapproj", rp=types.SimpleNamespace(name="Gold", author="Michi"),
                                     lbl_name=lbl("n"), lbl_sub=lbl("s"))
        gui.CheatCard.refresh_meta(card)
        self.assertEqual(out["n"]["text"], "★ Gold")
        self.assertEqual(out["s"]["text"], "by : Michi  ·  [Geld]  ·  ⌨ Ctrl+F5")
        out.clear()
        a.gp = None
        gui.CheatCard.refresh_meta(card)
        self.assertEqual((out["n"]["text"], out["s"]["text"]), ("Gold", "by : Michi"))

    def test_load_game_profile_uses_title_id_and_restores_view(self):
        import gameprofile
        import tempfile
        d = tempfile.mkdtemp()
        old = gameprofile.load
        gameprofile.load = lambda key, directory=None: old(key, d)
        try:
            a = self.app
            a.gp = None
            a.current_project, a.PATCH_DIR = "Super Game PPSA11111", "/x/y"
            pre = GP.GameProfile("PPSA11111", d)
            pre.ui = {"group": "Leben", "only_fav": True}
            pre.groups = {"A.reapproj": "Leben"}
            pre.save()
            a._load_game_profile()
            self.assertEqual(a.gp.key, "PPSA11111")
            self.assertEqual((a.v_group.get(), a.v_favonly.get()), ("Leben", True))
            a.current_project, a.PATCH_DIR = "Ohne ID", "/x/z"
            a._load_game_profile()
            self.assertEqual(a.gp.key, "Ohne ID")
        finally:
            gameprofile.load = old


if __name__ == "__main__":
    unittest.main()
