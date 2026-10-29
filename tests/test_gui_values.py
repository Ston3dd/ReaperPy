"""Tab WERTE (Fake-Tk, kein Display): Unity-Methoden und Unreal-Werte -> Haken -> Patches speichern."""
import json, os, shutil, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import cheatmenu as M
import cheatmenu_cave as CV
import il2cpp_dump as D
import test_cheatmenu_cave as TC
import test_values_auto as TV
import ue_instr as U
import ue_quick as Q
import values_auto as VA
from test_gui_smoke import FakeWin


class Client:
    def __init__(self, mem=None): self.mem = mem or {}
    def read_memory(self, a, n): return self.mem.get(a, b"\x55" * n)[:n]
    def get_maps(self): return [(0x400000, 0x500000, 5)]


class FakeUnityTab:
    __name__ = "UnityTab"
    def __init__(self, game): self.game = game; self.picked = 0
    def pick_game(self): self.picked += 1
    def _ensure_base(self, client): return type("L", (), {"base": 0x400000})()
FakeUnityTab.__name__ = "UnityTab"


class FakeUeTab:
    def __init__(self, proj=None): self.proj = proj; self.live = None; self.picked = 0
    def pick_game(self): self.picked += 1
FakeUeTab.__name__ = "UeLiveTab"


def make(unity=None, ue=None, client=None):
    import tools_values_gui as G
    w = FakeWin(); w.client = client
    w.extra_tabs = [t for t in (unity, ue) if t is not None]
    w.app.IMAGE_BASE = 0x400000
    t = G.ValuesTab(None, w)
    tmp = tempfile.mkdtemp()
    t._base_dir = lambda kind: os.path.join(tmp, "Spiel", "Unity-Werte" if kind == "unity" else "Werte")
    return t, w, tmp


class UnityFlow(unittest.TestCase):
    def setUp(self):
        self.game = TV.game(TV.SPEC); self.game.title = "Testspiel"
        self.unity = FakeUnityTab(self.game)
        self.t, self.w, self.tmp = make(unity=self.unity, client=Client())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_status_and_engine_auto(self):
        self.assertIn("Unity-Spiel geladen: Testspiel", self.t.lbl_unity._text)
        self.assertIn("Kein Unreal-Spiel", self.t.lbl_ue._text)
        self.assertEqual(self.t._engine(), "unity")

    def test_find_lists_candidates_with_defaults(self):
        self.t.find()
        labels = [r["label"] for r in self.t.rows]
        self.assertIn("PlayerHealth.TakeDamage", labels)
        on = {r["label"] for r, f in zip(self.t.rows, self.t.on) if f}
        self.assertIn("PlayerHealth.TakeDamage", on)
        self.assertNotIn("EnemyHealth.TakeDamage", on)                 # Gegner nicht vorangehakt
        self.assertTrue(any("Gegner" in r["effect"] for r in self.t.rows))

    def test_save_writes_verified_patch_files(self):
        self.t.find()
        self.t.save()
        self.assertIn("Fertig", self.t.lbl_done._text)
        d = os.path.join(self.tmp, "Spiel", "Unity-Werte")
        files = [f for f in os.listdir(d) if f.endswith(".reapproj")]
        self.assertEqual(len(files), sum(self.t.on))
        doc = json.load(open(os.path.join(d, files[0]), encoding="utf-8"))
        self.assertTrue(doc["Verify"])
        self.assertIn("0x400000", self.t.lbl_done._text)               # Modul-Basis wird genannt

    def test_save_twice_does_not_pile_up_copies_but_keeps_foreign_files(self):
        self.t.find()
        d = os.path.join(self.tmp, "Spiel", "Unity-Werte"); os.makedirs(d)
        json.dump({"name": "fremd", "author": "jemand", "Variables": []}, open(os.path.join(d, "fremd.reapproj"), "w"))
        self.t.save(); n1 = len(os.listdir(d))
        self.t.save(); n2 = len(os.listdir(d))
        self.assertEqual(n1, n2)
        self.assertIn("fremd.reapproj", os.listdir(d))

    def test_check_all_buttons_and_nothing_checked(self):
        self.t.find()
        self.t.set_all(False)
        self.t.save()
        self.assertIn("etwas anhaken", self.t.lbl_done._text)
        self.t.tv.sel = ("0",)
        self.t.only_category_of_selected()
        self.assertTrue(0 < sum(self.t.on) < len(self.t.rows))

    def test_already_patched_method_is_reported_not_crashed(self):
        self.w.client = Client({0x401000: b"\xc3\x90\x90\x90\x90"})
        self.t.find(); self.t.set_all(False)
        i = next(k for k, r in enumerate(self.t.rows) if r["label"] == "PlayerHealth.TakeDamage")
        self.t.on[i] = True
        self.t.save()
        self.assertIn("schon gepatcht", self.t.lbl_done._text)

    def test_not_connected_message(self):
        self.t.find(); self.w.client = None
        self.t.save()
        self.assertIn("Nicht verbunden", self.t.lbl_done._text)


class Nothing(unittest.TestCase):
    def test_no_game_loaded(self):
        t, w, tmp = make(client=Client())
        self.addCleanup(shutil.rmtree, tmp, True)
        t.find()
        self.assertIn("Schritt ①", t.lbl_found._text)

    def test_buttons_call_the_game_pickers(self):
        un, ue = FakeUnityTab(None), FakeUeTab()
        t, w, tmp = make(unity=un, ue=ue); self.addCleanup(shutil.rmtree, tmp, True)
        t.pick_unity(); t.pick_ue()
        self.assertEqual((un.picked, ue.picked), (1, 1))


@unittest.skipUnless(TC.HAVE, "Toolchain fehlt")
class UnrealFlow(TC.Real):
    def setUp(self):
        self.ent = [TC.entry("UHealthComponent.Health", "value", "UHealthComponent", "Health", "float", 0x348, default="auto"),
                    TC.entry("UWeapon.Ammo", "value", "UWeapon", "Ammo", "int32", 0x200, default="auto"),
                    TC.entry("UStats.XP", "value", "UStats", "XP", "int32", 0x100, default="auto")]
        self.ent[0].cat, self.ent[1].cat, self.ent[2].cat = "Leben", "Munition", VA.XP_CATEGORY
        fake = type("Live", (), {"index": 1, "build_index": lambda s: None})()
        proj = type("P", (), {"sdk": object(), "title": "UE-Spiel", "dm": None, "dis": self.dis})()
        self.ue = FakeUeTab(proj)
        self.t, self.w, self.tmp = make(ue=self.ue, client=Client())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        ents = self.ent

        class Menu:
            entries = ents
            def __init__(s, *a, **k): pass
            def build(s): return ents
            def check_live(s): pass
            def release_all(s, restore=True): pass
            sdk = None
            def _off(s, c, m): return None
        self.patch(M, "CheatMenu", Menu)
        self.patch(Q, "connect_live", lambda *a, **k: fake)
        self.patch(CV, "code_from_console", lambda client, base, progress=None, **k: self.code)

    def patch(self, obj, name, val):
        old = getattr(obj, name); setattr(obj, name, val); self.addCleanup(setattr, obj, name, old)

    def test_find_and_save_builds_caves(self):
        self.t.find()
        self.assertEqual([r["cat"] for r in self.t.rows], ["Leben", "Munition", VA.XP_CATEGORY])
        self.assertEqual(self.t.kind, "ue")
        self.t.v_xp.set("777")
        self.t.save()
        txt = self.t.lbl_done._text
        self.assertIn("Fertig: 3 Patches", txt)
        d = os.path.join(self.tmp, "Spiel", "Werte")
        names = [json.load(open(os.path.join(d, f), encoding="utf-8"))["name"] for f in os.listdir(d)]
        self.assertTrue(any("777" in n for n in names))
        self.assertIn("ALLE Objekte", txt)

    def test_bad_xp_value_is_rejected(self):
        self.t.find(); self.t.v_xp.set("viel"); self.t.save()
        self.assertIn("Zahl", self.t.lbl_done._text)


if __name__ == "__main__":
    unittest.main()
