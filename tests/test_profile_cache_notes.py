"""Tests: Analyse-Zwischenspeicher (ue_profile.signature/from_json), Entdecker nutzt ihn, Notizen im Start-Tab."""
import json
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import gameprofile as GP
import test_ue_profile as TP
import ue_profile as P


class Cache(unittest.TestCase):
    def test_json_roundtrip_keeps_everything_the_gui_needs(self):
        prof = P.build(TP.sdk_from(TP.GAME_A, [(1, 0x7000_1000, "DataTable", "DataTable /Game/Data/DT_Items.DT_Items")]))
        back = P.from_json(P.to_json(prof))
        self.assertEqual([(s.kind, s.title, s.score) for s in back.suggestions], [(s.kind, s.title, s.score) for s in prof.suggestions])
        self.assertEqual(back.counts, prof.counts)
        self.assertEqual(back.summary, prof.summary)
        self.assertTrue(all(s.howto for s in back.suggestions if s.kind in P.HOWTO))
        table = next(s for s in back.suggestions if s.title == "FItemRow")
        self.assertEqual(table.data["table_name"], "DT_Items")
        self.assertEqual(len(table.data["columns"][0]), 4)                         # Spalten bleiben (Name, Typ, Offset, Groesse)
        give = next(s for s in back.suggestions if s.title == "UMyCheatManager.GiveItem")
        self.assertEqual([tuple(p) for p in give.data["params"]], [tuple(p) for p in next(
            x for x in prof.suggestions if x.title == "UMyCheatManager.GiveItem").data["params"]])

    def test_signature_changes_with_the_sdk(self):
        a = P.signature(TP.sdk_from(TP.GAME_A))
        b = P.signature(TP.sdk_from(TP.GAME_B))
        self.assertNotEqual(a, b)
        self.assertEqual(a, P.signature(TP.sdk_from(TP.GAME_A)))
        self.assertNotEqual(a, P.signature(TP.sdk_from(TP.GAME_A, [(1, 1, "DataTable", "x.y")])))

    def test_broken_cache_raises_value_error(self):
        for bad in ("{kaputt", "[]", json.dumps({"suggestions": [{"kind": "x"}]}), json.dumps({})):
            with self.assertRaises(ValueError):
                P.from_json(bad)


class DiscoverUsesCache(unittest.TestCase):
    def setUp(self):
        import tools_discover_gui as G
        from test_gui_smoke import FakeWin
        self.w = FakeWin()
        self.w.app = types.SimpleNamespace(gp=GP.GameProfile("PPSA00001", None))
        self.saved = []
        self.w.app.gp.save = lambda: self.saved.append(1) or True
        self.sdk = TP.sdk_from(TP.GAME_A)
        self.w.extra_tabs = [type("UeLiveTab", (), {"proj": types.SimpleNamespace(sdk=self.sdk), "live": None})()]
        self.t = G.DiscoverTab(None, self.w)
        self.builds = []
        real = P.build
        self.addCleanup(setattr, P, "build", real)
        P.build = lambda sdk, progress=None: (self.builds.append(1), real(sdk, progress))[1]

    def test_second_analysis_comes_from_cache_and_force_rebuilds(self):
        self.t.analyze()
        self.assertEqual(len(self.builds), 1)
        self.assertEqual(self.saved, [1])
        self.assertEqual(self.w.app.gp.discover["sig"], P.signature(self.sdk))
        n = len(self.t.view)
        self.t.prof, self.t.view = None, []
        self.t.analyze()
        self.assertEqual(len(self.builds), 1)                                    # kein neuer Build
        self.assertEqual(len(self.t.view), n)
        self.assertTrue(any("Zwischenspeicher" in m for k, m in self.w.logs if k == "ok"))
        self.t.reanalyze()
        self.assertEqual(len(self.builds), 2)

    def test_changed_sdk_or_broken_cache_rebuilds(self):
        self.t.analyze()
        self.w.app.gp.discover["sig"] = "0/0/0/0/0"
        self.t.analyze()
        self.assertEqual(len(self.builds), 2)
        self.w.app.gp.discover["json"] = "{kaputt"
        self.t.analyze()
        self.assertEqual(len(self.builds), 3)

    def test_works_without_profile(self):
        self.w.app.gp = None
        self.t.analyze()
        self.t.analyze()
        self.assertEqual(len(self.builds), 2)
        self.assertEqual([m for k, m in self.w.logs if k == "err"], [])


class Notes(unittest.TestCase):
    def make(self, gp):
        import tools_start_gui as S

        class Text:
            def __init__(self): self.t = ""
            def delete(self, *a): self.t = ""
            def insert(self, i, text): self.t += text
            def get(self, *a): return self.t
            def bind(self, *a): pass
        app = types.SimpleNamespace(backend=types.SimpleNamespace(client=None, pid=None), current_project=None, patches={}, gp=gp,
                                    root=None)
        logs = []
        win = types.SimpleNamespace(app=app, log=lambda m, k="info": logs.append((k, m)), ui=lambda fn: fn())
        t = S.StartTab(None, win)
        t.notes = Text()
        t._notes_key = object()
        t.v_prof = types.SimpleNamespace(set=lambda v: setattr(t, "prof_text", v))
        return t, app, logs

    def test_notes_load_save_and_follow_the_game(self):
        gp = GP.GameProfile("PPSA00001", None)
        gp.notes = "Boss 2: Ruecken"
        saved = []
        gp.save = lambda: saved.append(gp.notes) or True
        t, app, logs = self.make(gp)
        t.refresh()
        self.assertEqual((t.notes.t, t.prof_text), ("Boss 2: Ruecken", "(PPSA00001)"))
        t.notes.t = "Neu geschrieben"
        t.save_notes()
        self.assertEqual(saved, ["Neu geschrieben"])
        self.assertEqual(logs[-1], ("ok", "Notizen gespeichert"))
        t.save_notes()                                                           # unveraendert: nicht nochmal speichern
        self.assertEqual(len(saved), 1)
        gp2 = GP.GameProfile("PPSA00002", None)
        gp2.notes = "anderes Spiel"
        app.gp = gp2
        t.refresh()
        self.assertEqual((t.notes.t, t.prof_text), ("anderes Spiel", "(PPSA00002)"))

    def test_no_profile_gives_a_hint_but_quiet_autosave_stays_silent(self):
        t, app, logs = self.make(None)
        t.refresh()
        self.assertEqual(t.prof_text, "(kein Projekt offen)")
        t.save_notes(quiet=True)
        self.assertEqual(logs, [])
        t.save_notes()
        self.assertEqual(logs[-1][0], "err")


if __name__ == "__main__":
    unittest.main()
