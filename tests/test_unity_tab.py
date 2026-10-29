"""Test: Unity-Tab (tools_unity_gui) - kompletter Ablauf mit Mini-Spiel und simuliertem Speicher, ohne Konsole."""
import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E402,E702
import test_il2cpp as TI  # noqa: E402
import il2cpp_dump as D  # noqa: E402
from pathlib import Path


class Client(TI.FakeMem):
    def __init__(self, maps):
        super().__init__()
        self.maps = maps

    def read_memory(self, a, n):
        return self.read(a, n)

    def write_memory(self, a, d):
        self.put(a, d)

    def get_maps(self):
        return self.maps


class Win:
    def __init__(self, client):
        self.client = client
        self.logs = []

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


class UnityTabFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        Path(os.path.join(self.tmp.name, "dump.cs")).write_text(TI.DUMP, encoding="utf-8")
        Path(os.path.join(self.tmp.name, "script.json")).write_text(json.dumps(TI.SCRIPT), encoding="utf-8")
        mem_maps = [(TI.BASE, TI.BASE + 0x10000, 5), (0x5000000, 0x5001000, 1), (0x8000000, 0x8001000, 3),
                    (TI.KLASS, TI.KLASS + 0x1000, 3)]
        c = Client(mem_maps)
        name_str, ns_str = 0x5000100, 0x5000200
        c.put(name_str - 1, b"\0Wallet\0")
        c.put(ns_str, b"Game\0")
        c.put(TI.KLASS + 0x10, struct.pack("<Q", name_str))
        c.put(TI.KLASS + 0x18, struct.pack("<Q", ns_str))
        c.put(TI.KLASS + 0x40, struct.pack("<Q", TI.KLASS))
        c.put(TI.BASE + 0x2000, struct.pack("<Q", TI.KLASS))
        c.put(TI.KLASS + D.K_STATIC_FIELDS, struct.pack("<Q", 0xA000000))
        self.inst = 0x8000040
        c.put(self.inst, struct.pack("<Q", TI.KLASS))
        c.put(self.inst + 0x10, struct.pack("<i", 123))
        c.put(TI.BASE + 0x1000, b"\x55\x48\x89\xe5\x90\x90\x90\x90")        # CanBuy-Prolog
        self.c = c
        import tools_unity_gui as U
        import tools_common
        self.w = Win(c)
        self.t = U.UnityTab(None, self.w)
        self.t._cfg = {}
        self.t.v_game.set(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_flow(self):
        t, w, c = self.t, self.w, self.c
        t.load()
        self.assertIsNotNone(t.game, w.logs)
        self.assertTrue(any(x.key == "Game.Wallet.gold" for x in t.targets))
        t.detect_base()
        self.assertEqual(t.mod_base, TI.BASE, w.logs)
        # Wert: Wallet.gold finden, lesen, setzen
        t.shown = [x for x in t.targets if x.key == "Game.Wallet.gold"]
        t.tl.selection = lambda: ("0",)
        t.cur = t.shown[0]
        t.refind()
        self.assertEqual([r["addr"] for r in t.rows], [self.inst], w.logs)
        self.assertEqual(t.rows[0]["txt"], "123")
        t.tr.selection = lambda: ("0",)
        t.set_value("+100")
        self.assertEqual(struct.unpack("<i", c.read(self.inst + 0x10, 4))[0], 223)
        t.freeze_sel()
        self.assertIn(self.inst + 0x10, t.freezer)
        # Methode patchen und zurueck
        t.v_mq.set("CanBuy")
        t._fill_methods()
        t.ml.selection = lambda: ("0",)
        t.apply_patch("true")
        self.assertEqual(c.read(TI.BASE + 0x1000, 6), b"\xb8\x01\x00\x00\x00\xc3", w.logs)
        t.al.selection = lambda: ("0",)
        t.remove_patch()
        self.assertEqual(c.read(TI.BASE + 0x1000, 6), b"\x55\x48\x89\xe5\x90\x90")
        self.assertEqual(t.applied, [])

    def test_scan_filters_list(self):
        t = self.t
        t.load()
        all_n = len(t.targets)
        self.assertTrue(all_n >= 4)
        t.detect_base()
        t.scan_game()
        self.assertIsNotNone(t.counts, self.w.logs)
        self.assertEqual(t.counts.get("Game.Wallet"), 1)
        t._fill_targets()
        keys = {x.key for x in t.shown}
        self.assertIn("Game.Wallet.gold", keys)
        self.assertNotIn("Game.Hidden.hp", keys)          # Klasse ohne Objekt im Speicher
        t.v_live_only.set(False)
        t._fill_targets()
        self.assertIn("Game.Hidden.hp", {x.key for x in t.shown})

    def test_names_and_errors(self):
        t = self.t
        t.load()
        t.v_nq.set("item apple")
        t._fill_names()
        self.assertEqual(t.nshown[0][1:], ("Apple", 7))
        # void-Methode darf kein TRUE bekommen
        t.v_mq.set("Spend")
        t._fill_methods()
        t.ml.selection = lambda: ("0",)
        import tools_unity_gui as U
        U.messagebox.showwarning = lambda *a, **k: self.w.logs.append(("warn", a[1]))
        t.apply_patch("true")
        self.assertTrue(any(k == "warn" for k, _ in self.w.logs))


if __name__ == "__main__":
    unittest.main()
