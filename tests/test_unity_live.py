"""unity_live + Unity-ITEMS-Tab: Items live geben/testen (ps5_more.call und Spielobjekte nachgebaut)."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import ps5_more
import test_unity_items as TU
import unity_items as U
import unity_live as UL
from test_gui_smoke import FakeWin

BASE = 0x400000
THIS = 0x7000_0000


class FakeLive:
    base = BASE

    def __init__(self, objs=(THIS,)):
        self.objs = list(objs)

    def instances(self, cls, limit=400, **_k):
        return self.objs[:limit]

    def set_maps(self, _m):
        pass


class Calls:
    """ersetzt ps5_more.call und merkt sich die Aufrufe"""

    def __init__(self, fail_at=None):
        self.log, self.fail_at = [], fail_at

    def __call__(self, client, rip, rdi=0, rsi=0, rdx=0, rcx=0, r8=0, r9=0, **_k):
        self.log.append((rip, rdi, rsi, rdx, rcx))
        if self.fail_at is not None and len(self.log) == self.fail_at:
            raise ps5_more.MoreError("call: Status 0x80000001")
        return 1


class Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.g = TU.make_dump(cls.tmp)
        cls.en = cls.g.find_class("ItemID")
        ok, _bad = U.give_candidates(cls.g, cls.en)
        cls.gives = {g.method.name + str(g.method.static): g for g in ok}
        cls.inst = cls.gives["AddItemFalse"]
        cls.stat = cls.gives["GiveItemTrue"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.calls = Calls()
        self.old = ps5_more.call
        ps5_more.call = self.calls
        self.addCleanup(setattr, ps5_more, "call", self.old)

    def test_register_args_instance_and_static(self):
        r = UL.register_args(self.inst, THIS, 6, 99)
        self.assertEqual((r["rdi"], r["rsi"], r["rdx"], r["rcx"]), (THIS, 6, 99, 0))     # this, id, count, MethodInfo*
        r = UL.register_args(self.stat, 0, 6, 99)
        self.assertEqual((r["rdi"], r["rsi"], r["rdx"]), (6, 99, 0))

    def test_give_one_calls_base_plus_rva(self):
        UL.give_one(None, FakeLive(), self.inst, 6, 50)
        self.assertEqual(self.calls.log[0][0], BASE + self.inst.method.rva)
        self.assertEqual(self.calls.log[0][1:4], (THIS, 6, 50))

    def test_no_object_is_a_clear_error(self):
        with self.assertRaises(UL.LiveError) as c:
            UL.give_one(None, FakeLive(objs=()), self.inst, 1, 1)
        self.assertIn("Inventory", str(c.exception))
        self.assertEqual(self.calls.log, [])

    def test_static_needs_no_object(self):
        UL.give_one(None, FakeLive(objs=()), self.stat, 1, 1)
        self.assertEqual(len(self.calls.log), 1)

    def test_give_many_stops_at_first_error(self):
        self.calls.fail_at = 3
        items = [{"name": f"I{i}", "id": i} for i in range(1, 6)]
        done, errors = UL.give_many(None, FakeLive(), self.inst, items, 9)
        self.assertEqual(done, 2)
        self.assertEqual(errors[0][0]["name"], "I3")
        self.assertEqual(len(self.calls.log), 3)                  # nie wiederholt, nicht weitergemacht

    def test_float_param_refused(self):
        g = U.Give(self.inst.method, [dict(self.inst.params[0], kind="float")] + self.inst.params[1:], 0, 1, 0)
        with self.assertRaises(UL.LiveError):
            UL.register_args(g, THIS, 1, 1)

    def test_rank_uses_verified(self):
        gs = [self.inst, self.stat]
        first = UL.rank_gives(gs, {})[0]
        bad = UL.rank_gives(gs, {UL.give_key(first): UL.VERIFIED_BAD})
        self.assertIsNot(bad[0], first)
        ok = UL.rank_gives(gs, {UL.give_key(gs[1]): UL.VERIFIED_OK, UL.give_key(gs[0]): UL.VERIFIED_BAD})
        self.assertIs(ok[0], gs[1])


class Levels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.g = TU.make_dump(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_levels_only_widen(self):
        en = self.g.find_class("ItemID")
        n = [len(U.give_candidates(self.g, en, level=lv)[0]) for lv in U.LEVELS]
        self.assertLessEqual(n[0], n[1])
        self.assertLessEqual(n[1], n[2])

    def test_unknown_level_is_strict(self):
        en = self.g.find_class("ItemID")
        a = [g.method.key for g in U.give_candidates(self.g, en, level="zzz")[0]]
        b = [g.method.key for g in U.give_candidates(self.g, en)[0]]
        self.assertEqual(a, b)

    def test_off_never_offers_removers_or_getters(self):
        en = self.g.find_class("ItemID")
        names = [g.method.name for g in U.give_candidates(self.g, en, level="off")[0]]
        self.assertNotIn("RemoveItem", names)


class FakeUnity:
    def __init__(self, game):
        self.game, self.live = game, FakeLive()

    def _ensure_base(self, _client):
        return self.live

    @staticmethod
    def _maps(_client):
        return []


FakeUnity.__name__ = "UnityTab"


class Gui(unittest.TestCase):
    def setUp(self):
        import tools_unity_items_gui as G
        import tkinter.messagebox as mb
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.game = TU.make_dump(self.tmp)
        self.game.title = "Testspiel"
        self.w = FakeWin()
        self.w.client = object()
        self.w.extra_tabs = [FakeUnity(self.game)]
        self.t = G.UnityItemsTab(None, self.w)
        self.calls = Calls()
        self.old = ps5_more.call
        ps5_more.call = self.calls
        self.addCleanup(setattr, ps5_more, "call", self.old)
        self.answers = []
        self.oldq = mb.askyesno
        mb.askyesno = lambda *a, **k: self.answers.pop(0) if self.answers else True
        self.addCleanup(setattr, mb, "askyesno", self.oldq)

    def test_give_live_calls_every_checked_item(self):
        self.t.find_items()
        n = len(self.t._chosen())
        self.t.v_amount.set("7")
        self.t.give_live()
        self.assertEqual(len(self.calls.log), n)
        self.assertEqual({c[3] for c in self.calls.log}, {7})
        self.assertIn("gegeben", self.t.lbl_found._text)

    def test_give_live_needs_find_first(self):
        self.t.give_live()
        self.assertEqual(self.calls.log, [])
        self.assertIn("ITEMS FINDEN", self.t.lbl_found._text)

    def test_give_live_without_client(self):
        self.t.find_items()
        self.w.client = None
        self.t.give_live()
        self.assertEqual(self.calls.log, [])
        self.assertIn("verbinden", self.t.lbl_found._text)

    def test_test_one_marks_verified_and_switches_on_failure(self):
        self.t.find_items()
        first = self.t.give
        self.t.on = [False] * len(self.t.items)
        self.t.on[0] = True
        self.answers = [True, False]                  # Testen? ja / angekommen? nein
        self.t.test_one()
        self.assertEqual(len(self.calls.log), 1)
        self.assertEqual(self.t.verified[UL.give_key(first)], UL.VERIFIED_BAD)
        self.assertIsNot(self.t.give, first)

    def test_test_one_ok_is_remembered(self):
        self.t.find_items()
        self.t.on = [False] * len(self.t.items)
        self.t.on[0] = True
        first = self.t.give
        self.answers = [True, True]
        self.t.test_one()
        self.assertEqual(self.t.verified[UL.give_key(first)], UL.VERIFIED_OK)
        self.assertIs(self.t.give, first)

    def test_test_checked_reports_abort(self):
        self.t.find_items()
        self.calls.fail_at = 2
        self.t.test_checked()
        self.assertEqual(len(self.calls.log), 2)
        self.assertIn("Abbruch", self.t.lbl_found._text)

    def test_level_switch_reanalyses(self):
        self.t.find_items()
        self.t.v_level.set("streng")
        self.t.pick_level()
        self.assertEqual(self.t.level, "strict")
        self.assertIsNotNone(self.t.give)


if __name__ == "__main__":
    unittest.main()
