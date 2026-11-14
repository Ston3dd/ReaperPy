"""Test: Tab UNITY > CAVEMAKER - Liste laden, Cheat bauen, TEST AN/AUS auf (simuliertem) Speicher mit echtem Maschinencode,
ins Projekt übernehmen.  Ohne Display (ghost_tk) und ohne Konsole."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import ghost_tk; ghost_tk.install()  # noqa: E402,E702
import cave_world as W  # noqa: E402
import test_cavemaker_core as TC  # noqa: E402


class Win:
    def __init__(self, backend, unity):
        self.logs, self.extra_tabs = [], [unity]
        self.client = backend.client or object()
        self.added = []
        win = self

        class App:
            IMAGE_BASE = backend.base
            PATCH_DIR = None

            def add_patch_from_file(self, path):
                from reapatch import ReapPatch
                ReapPatch.load(path)
                win.added.append(path)
                return path

        self.app = App()
        self.app.backend = backend

    def bg(self, fn, ok=None, err=None, lock=True):
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            (err or (lambda e: self.logs.append(("err", str(e)))))(e)
            return
        if ok:
            ok(r)

    def log(self, m, k="info"):
        self.logs.append((k, m))

    def ui(self, fn):
        fn()


class UnityStub:
    """Was der Cavemaker vom Tab MANUELL braucht: geladenes Spiel + Modul-Basis."""
    __name__ = "UnityTab"

    def __init__(self, game, base):
        self.game = game
        self._base = base

    def _ensure_base(self, client):
        class Live:
            pass
        lv = Live()
        lv.base = self._base
        return lv


UnityStub.__name__ = "UnityTab"


@unittest.skipUnless(W.TOOLCHAIN, "keine Toolchain (Linux x86-64 mit as/ld/objdump)")
class UnityCaveTabFlow(unittest.TestCase):
    def setUp(self):
        import il2cpp_dump as D
        self.core = TC.CaveMakerCore("test_instance_field_cave")
        self.core.setUp()                                   # Mini-Spiel + Speicher + Funktionen wie im Kerntest
        c = self.core
        files = D.find_game_files(c.tmp.name)
        game = D.GameDump(files, log=lambda m: None).load()
        c.b.client = object()                                # Verbindung vorhanden (Signatur-Suche scheitert -> Hinweis)
        stub = UnityStub(game, c.b.base)
        stub.__class__.__name__ = "UnityTab"
        self.win = Win(c.b, stub)
        import tools_unity_cave_gui as G
        self.G = G
        self.t = G.UnityCaveTab(None, self.win)
        self.out = tempfile.TemporaryDirectory()
        self.t._out_dir = lambda: self.out.name
        self.t._cfg = {}

    def tearDown(self):
        self.core.tearDown()
        self.out.cleanup()

    def pick(self, label):
        self.t.v_scored.set(False)
        self.t.v_search.set("")
        self.t.load_list()
        c = next(c for c in self.t.shown if c.label == label)
        self.t.select(c)
        return c

    def test_list_loads_and_offers_actions(self):
        c = self.pick("Player.AddMoney")
        self.assertEqual(c.kind, "method")
        self.assertIn("Parameter 'amount' (int) ändern", [a.label for a in self.t.actions])
        self.assertTrue(any(c.label == "Player.Gold" for c in self.t.shown))

    def test_add_test_on_off_and_save_to_project(self):
        t, b = self.t, self.core.b
        self.pick("Player.AddMoney")
        t.v_act.set("Parameter 'amount' (int) ändern")
        t._act_changed()
        t.v_val.set("100")
        t.generate(True)
        self.assertEqual(len(t.items), 1, self.win.logs)
        it = t.items[0]
        self.assertEqual(it.kind, "Cave")
        t.coll.selection_set(["0"])
        t.test_on()
        self.assertIsNotNone(it.state, self.win.logs)
        self.assertEqual(self.core.call_fn(b.base + 0x1000, 0, 5), 101)
        t.test_off()
        self.assertIsNone(it.state)
        self.assertEqual(self.core.call_fn(b.base + 0x1000, 0, 5), 6)
        t.to_project()
        self.assertEqual(len(self.win.added), 1, self.win.logs)
        from reapatch import ReapPatch
        import patch_engine as PE
        rp = ReapPatch.load(self.win.added[0])
        self.assertTrue(PE.is_cave_patch(rp))
        self.assertIn("✔ 1 Hook(s) im Projekt", t.lbl_done.cget("text"))
        # das gespeicherte Dokument aktiviert sich genauso
        st = PE.apply_patch(b, rp, b.base + rp.origin_source[0])
        self.assertEqual(self.core.call_fn(b.base + 0x1000, 0, 5), 101)
        PE.deactivate_patch(b, rp, st)

    def test_same_hook_twice_is_refused(self):
        t = self.t
        self.pick("Player.AddMoney")
        t.v_act.set("Parameter 'amount' (int) ändern")
        t._act_changed()
        t.generate(True)
        t.generate(True)
        self.assertEqual(len(t.items), 1)
        self.assertTrue(any("schon von" in m for k, m in self.win.logs if k == "err"), self.win.logs)

    def test_broken_hook_is_not_taken_over(self):
        t = self.t
        self.pick("Player.AddMoney")
        t.v_act.set("Parameter 'amount' (int) ändern")
        t._act_changed()
        t.generate(True)
        t.items[0].pd.blocks = []                             # Cave-Code geht verloren -> darf nicht ins Projekt
        t.to_project()
        self.assertEqual(self.win.added, [])
        self.assertEqual(os.listdir(self.out.name), [])
        self.assertIn("✗", t.lbl_done.cget("text"))

    def test_static_field_needs_script_json_hint(self):
        self.pick("Player.Gold")
        self.assertEqual([a.key for a in self.t.actions], ["static"])
        self.assertTrue(self.t.hooks, "Haken-Methoden für das statische Feld")


if __name__ == "__main__":
    unittest.main()
