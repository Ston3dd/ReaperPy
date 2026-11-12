"""Objekt-Finder (kein Voll-Scan pro Klick), MANUELL mit EINEM Scan, Items mit Mengen fuer viele, Cave mit fester Menge."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E402,E702
import il2cpp_dump as D  # noqa: E402
import test_il2cpp as TI  # noqa: E402
import test_unity_items as TU  # noqa: E402
import unity_cheatmenu as UM  # noqa: E402
import unity_items as U  # noqa: E402
import unity_live as UL  # noqa: E402
import unity_objects as UO  # noqa: E402
from test_unity_tab import UnityTabFlow  # noqa: E402


class FakeCls:
    full = "Game.Wallet"


class FakeLive:
    """zaehlt die teuren Aufrufe"""

    def __init__(self, cache=False, single=0):
        self.objects = {} if cache else None
        self.known = {"Game.Wallet"} if cache else set()
        self.single, self.censuses, self.inst_calls = single, 0, 0

    def census(self, progress=None, cancel=None):
        self.censuses += 1
        self.objects, self.known = {"Game.Wallet": [0x1000]}, {"Game.Wallet"}

    def instances(self, cls, limit=400, **_k):
        self.inst_calls += 1
        return [0x1000]


class FakeGame:
    def family(self, cls, cap=24):
        return [cls]


class Finder(unittest.TestCase):
    def test_cache_first(self):
        lv = FakeLive(cache=True)
        self.assertEqual(UO.find(lv, FakeGame(), FakeCls()), ([0x1000], "cache"))
        self.assertEqual(lv.censuses, 0)

    def test_one_census_serves_all_later_calls(self):
        lv = FakeLive()
        self.assertEqual(UO.find(lv, FakeGame(), FakeCls())[1], "census")
        self.assertEqual(UO.find(lv, FakeGame(), FakeCls())[1], "cache")
        self.assertEqual(lv.censuses, 1)

    def test_no_scan_when_forbidden(self):
        lv = FakeLive()
        self.assertEqual(UO.find(lv, FakeGame(), FakeCls(), census=False), ([], "none"))
        self.assertEqual(lv.censuses, 0)

    def test_cancelled_scan_returns_nothing(self):
        lv = FakeLive()
        self.assertEqual(UO.find(lv, FakeGame(), FakeCls(), cancel=lambda: True), ([], "none"))

    def test_substitute_live_without_census_is_asked_directly(self):
        class Simple:
            def instances(self, cls, limit=400, **_k):
                return [5]
        self.assertEqual(UO.find(Simple(), None, FakeCls()), ([5], "scan"))


class Singleton(UnityTabFlow):
    """Wallet hat 'public static Wallet Instance' -> ein Lesezugriff statt Scan (Geben, Cheat-Menue)."""

    def _live(self):
        self.t.load()
        self.t.detect_base()
        self.c.maps.append((0xA000000, 0xA001000, 3))
        return self.t._ensure_base(self.c)

    def test_singleton_field_is_found_in_dump(self):
        self.t.load()
        w = self.t.game.by_full["Game.Wallet"]
        self.assertEqual([f.name for f in UO.singleton_fields(self.t.game, w)], ["Instance"])
        self.assertEqual(UO.singleton_fields(self.t.game, self.t.game.by_full["Game.Hidden"]), [])

    def test_singleton_pointer_is_used_without_scan(self):
        live = self._live()
        self.c.put(0xA000000, struct.pack("<Q", self.inst))
        calls = []
        old = D.Il2CppLive.census
        D.Il2CppLive.census = lambda self, *a, **k: calls.append(1) or old(self, *a, **k)
        self.addCleanup(setattr, D.Il2CppLive, "census", old)
        w = self.t.game.by_full["Game.Wallet"]
        self.assertEqual(UO.find(live, self.t.game, w, mode="any"), ([self.inst], "singleton"))
        self.assertEqual(calls, [])

    def test_wrong_singleton_pointer_falls_back_to_scan(self):
        live = self._live()
        self.c.put(0xA000000, struct.pack("<Q", 0x8000800))       # zeigt auf Unsinn
        w = self.t.game.by_full["Game.Wallet"]
        addrs, how = UO.find(live, self.t.game, w, mode="any")
        self.assertEqual((addrs, how), ([self.inst], "census"))


class ManualTab(UnityTabFlow):
    def test_two_fields_cause_one_scan(self):
        t = self.t
        t.load()
        t.detect_base()
        calls = []
        old = D.Il2CppLive.census
        D.Il2CppLive.census = lambda self, *a, **k: calls.append(1) or old(self, *a, **k)
        self.addCleanup(setattr, D.Il2CppLive, "census", old)
        for key in ("Game.Wallet.gold", "Game.Wallet.luck", "Game.Wallet.gold"):
            t.cur = next(x for x in t.targets if x.key == key)
            t.refind()
            self.assertEqual([r["addr"] for r in t.rows], [self.inst], self.w.logs)
        self.assertEqual(len(calls), 1)

    def test_click_during_scan_waits_and_reruns(self):
        t = self.t
        t.load()
        t.detect_base()
        t.cur = next(x for x in t.targets if x.key == "Game.Wallet.gold")
        t._scan_busy = True
        t.refind()
        self.assertTrue(t._rerun)
        self.assertEqual(t.rows, [])
        t._scan_busy = False
        t.refind()
        self.assertEqual(len(t.rows), 1)
        self.assertFalse(t._rerun)

    def test_stop_scan_sets_flag(self):
        self.t.stop_scan()
        self.assertTrue(self.t._scan_stop)

    def test_cave_button_without_field_and_for_static(self):
        t = self.t
        t.load()
        t.detect_base()
        t.cur = None
        t.build_cave_for_selected()
        self.assertEqual(self.w.logs[-1][0], "warn")
        t.cur = next(x for x in t.targets if x.key == "Game.Wallet.gold")
        t.static_keys = {t.cur.key}
        t.build_cave_for_selected()
        self.assertIn("statisch", self.w.logs[-1][1])


class EntryFromTarget(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.g = TU_game(self.tmp)

    def test_builds_entry_with_amount(self):
        import ue_quick as Q
        t = Q.Target("Game.Player", "gold", "int32", 0x124)
        e = UM.entry_from_target(self.g, t, "999")
        self.assertEqual((e.kind, e.offset, e.type, e.default, e.cat), ("field", 0x124, "int32", "999", "Manuell"))
        self.assertEqual(UM.cave_entry(e).kind, "value")

    def test_bad_inputs(self):
        import ue_quick as Q
        for target, amount, word in ((Q.Target("Game.Player", "name", "string", 0x20), "1", "Zahlen"),
                                     (Q.Target("Game.Player", "gold", "int32", 0), "1", "Offset"),
                                     (Q.Target("Game.Nope", "gold", "int32", 8), "1", "nicht im Dump"),
                                     (Q.Target("Game.Player", "gold", "int32", 0x124), "viel", "keine passende Zahl"),
                                     (Q.Target("Game.Player", "f", "bool", 0x20, bit=2), "1", "Bitfeld")):
            with self.assertRaises(UM.MenuError, msg=word) as c:
                UM.entry_from_target(self.g, target, amount)
            self.assertIn(word, str(c.exception))


def TU_game(tmp):
    import test_unity_cheatmenu as TC
    g = TC.make_game(tmp)
    # Spielklasse unter dem Namen Game.Player fuer den Test bereitstellen
    c = g.find_class("Player")
    g.by_full["Game.Player"] = c
    return g


class Items(unittest.TestCase):
    def setUp(self):
        import tempfile, shutil
        import tools_unity_items_gui as G
        from test_gui_smoke import FakeWin
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.game = TU.make_dump(self.tmp)
        self.game.title = "Testspiel"
        self.w = FakeWin()
        self.w.client = object()
        import test_unity_live as TL
        self.w.extra_tabs = [TL.FakeUnity(self.game)]
        self.t = G.UnityItemsTab(None, self.w)
        self.t.find_items()
        self.n = len(self.t.items)

    def test_select_and_amount_for_visible(self):
        self.assertGreater(self.n, 2)
        self.t.on = [False] * self.n
        self.t.v_set.set("999")
        self.t.apply_amount("visible")
        self.assertTrue(all(self.t.on))
        self.assertTrue(all(it["amount"] == 999 for it in self.t.items))
        self.assertIn("999", self.t.lbl_found._text)

    def test_amount_for_selection_only(self):
        self.t.on = [False] * self.n
        self.t.tv.selection = lambda: ("0", "1")
        self.t.v_set.set("50")
        self.t.apply_amount("selected")
        self.assertEqual([it.get("amount") for it in self.t.items[:3]], [50, 50, None])
        self.assertEqual(self.t.on[:3], [True, True, False])

    def test_checked_scope_does_not_tick(self):
        self.t.on = [False] * self.n
        self.t.on[1] = True
        self.t.v_set.set("7")
        self.t.apply_amount("checked")
        self.assertEqual([it.get("amount") for it in self.t.items[:3]], [None, 7, None])
        self.assertEqual(self.t.on[:3], [False, True, False])

    def test_bad_and_empty_amounts(self):
        self.t.v_set.set("abc")
        self.t.apply_amount("all")
        self.assertTrue(all("amount" not in it for it in self.t.items))
        self.t.v_set.set("0")
        self.t.apply_amount("all")
        self.assertTrue(all("amount" not in it for it in self.t.items))
        self.t.v_set.set("5")
        self.t.apply_amount("all")
        self.t.v_set.set("")
        self.t.apply_amount("all")                         # leer = eigene Menge entfernen
        self.assertTrue(all("amount" not in it for it in self.t.items))

    def test_nothing_to_apply(self):
        self.t.on = [False] * self.n
        self.t.tv.selection = lambda: ()
        self.t.apply_amount("selected")
        self.assertTrue(all("amount" not in it for it in self.t.items))
        self.t.apply_amount("checked")
        self.assertIn("Keine Items", self.t.lbl_found._text)

    def test_invert_all_and_clear(self):
        self.t.on = [False] * self.n
        self.t.set_all(True)
        self.assertTrue(all(self.t.on))
        self.t.invert_visible()
        self.assertFalse(any(self.t.on))
        self.t.v_set.set("9")
        self.t.apply_amount("all")
        self.t.clear_amounts()
        self.assertTrue(all("amount" not in it for it in self.t.items))

    def test_row_shows_amount_column(self):
        self.assertEqual(self.t._row(0)[4], "–")
        self.t.items[0]["amount"] = 12
        self.assertEqual(self.t._row(0)[4], 12)

    def test_trainer_uses_item_amounts(self):
        prm = [{"name": n, "type": "int", "kind": "int", "size": 4, "ref": False, "signed": True} for n in ("id", "n")]
        call = U.Call(0x1000, True, "zero", 0, prm, 0, 1)
        pkgs = [("P", [{"name": "A", "id": 1, "amount": 500}, {"name": "B", "id": 2}])]
        opts, _ = U.make_options(pkgs, call, 99)
        self.assertEqual([r.amount for r in opts[0].rows], [500, 99])
        call.count_i = None                                         # ohne Mengen-Parameter immer 1
        opts, _ = U.make_options(pkgs, call, 99)
        self.assertEqual([r.amount for r in opts[0].rows], [1, 1])

    def test_live_give_uses_item_amounts(self):
        import ps5_more
        import test_unity_live as TL
        calls = TL.Calls()
        old = ps5_more.call
        ps5_more.call = calls
        self.addCleanup(setattr, ps5_more, "call", old)
        self.t.on = [False] * self.n
        self.t.on[0] = self.t.on[1] = True
        self.t.items[0]["amount"] = 777
        self.t.v_amount.set("5")
        import tkinter.messagebox as mb
        o = mb.askyesno
        mb.askyesno = lambda *a, **k: True
        self.addCleanup(setattr, mb, "askyesno", o)
        self.t.give_live()
        self.assertEqual([c[3] for c in calls.log], [777, 5])
        self.assertEqual(UL.item_amount({"amount": 3}, 9), 3)
        self.assertEqual(UL.item_amount({}, 9), 9)


if __name__ == "__main__":
    unittest.main()
