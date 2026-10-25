import os, struct, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()
import ue_quick as Q, uesdk, uecheat
import test_ue_live as TL
from ue_world import HDR, tgt, Client, Proj, world


class Logic(unittest.TestCase):
    def setUp(self): self.im, self.ref, self.sdk, self.c = world()

    def test_decode_all_types(self):
        p = self.ref["p1"]
        for name, shown in (("Health", "75.5"), ("Gold", "1234"), ("Stamina", "55"), ("bIsEnableMuteki", "AUS"),
                            ("Level", "0")):
            t = tgt(self.sdk, name)
            self.assertEqual(Q.read_value(self.c.read_memory, p + t.offset, t)[1], shown, name)
        self.assertTrue(tgt(self.sdk, "bIsEnableMuteki").is_bool)
        self.assertEqual(tgt(self.sdk, "bIsEnableMuteki").bit, 2)

    def test_parse_input(self):
        f, i, fx, b, u8 = (tgt(self.sdk, n) for n in ("Health", "Gold", "Stamina", "bIsEnableMuteki", "Level"))
        self.assertEqual(Q.parse_input(f, "99,5"), 99.5)
        self.assertEqual(Q.parse_input(i, "0x10"), 16)
        self.assertEqual(Q.parse_input(i, "+100", 1234), 1334)
        self.assertEqual(Q.parse_input(i, "*2", 1234), 2468)
        self.assertEqual(Q.parse_input(f, "+0.5", 75.5), 76.0)
        self.assertEqual(Q.parse_input(i, "-5"), -5)                          # negative Zahl, nicht relativ
        self.assertEqual(Q.parse_input(fx, "100"), 100000)                    # Anzeige x1000
        self.assertEqual(Q.parse_input(fx, "*2", 55000), 110000)
        self.assertIs(Q.parse_input(b, "an"), True); self.assertIs(Q.parse_input(b, "AUS"), False)
        for bad in ("", "abc"):
            with self.assertRaises(ValueError): Q.parse_input(i, bad)
        with self.assertRaises(ValueError): Q.parse_input(b, "vielleicht")
        with self.assertRaises(ValueError): Q.parse_input(i, "+5")            # relativ ohne aktuellen Wert
        with self.assertRaises(ValueError): Q.encode(u8, 300)                 # ausserhalb uint8
        with self.assertRaises(ValueError): Q.encode(i, 2 ** 40)

    def test_write_value_and_bit_rmw(self):
        p = self.ref["p1"]
        t = tgt(self.sdk, "Health")
        Q.write_value(self.c.read_memory, self.c.write_memory, p + t.offset, t, 1.0)
        self.assertEqual(struct.unpack("<f", self.im.read(p + 0x80, 4))[0], 1.0)
        b = tgt(self.sdk, "bIsEnableMuteki")
        Q.write_value(self.c.read_memory, self.c.write_memory, p + 0x98, b, True)
        self.assertEqual(self.im.read(p + 0x98, 1)[0], 0b10000101)             # nur Bit 2 gesetzt, Rest erhalten
        Q.write_value(self.c.read_memory, self.c.write_memory, p + 0x98, b, False)
        self.assertEqual(self.im.read(p + 0x98, 1)[0], 0b10000001)
        fx = tgt(self.sdk, "Stamina")
        Q.write_value(self.c.read_memory, self.c.write_memory, p + 0x90, fx, Q.parse_input(fx, "9999"))
        self.assertEqual(struct.unpack("<q", self.im.read(p + 0x90, 8))[0], 9999000)

    def test_freezer_holds_value_and_bit(self):
        p = self.ref["p1"]; fz = Q.Freezer()
        h, b = tgt(self.sdk, "Health"), tgt(self.sdk, "bIsEnableMuteki")
        fz.add(p + 0x80, h, 100.0); fz.add(p + 0x98, b, True)
        self.im.w(p + 0x80, struct.pack("<f", 3.0))                            # Spiel senkt den Wert
        self.assertEqual(fz.tick(self.c), 2)
        self.assertEqual(struct.unpack("<f", self.im.read(p + 0x80, 4))[0], 100.0)
        self.assertEqual(self.im.read(p + 0x98, 1)[0], 0b10000101)
        self.assertEqual(fz.tick(self.c), 1)                                   # Bit schon gesetzt -> nur Health
        fz.remove(p + 0x80); self.im.w(p + 0x80, struct.pack("<f", 3.0)); fz.tick(self.c)
        self.assertEqual(struct.unpack("<f", self.im.read(p + 0x80, 4))[0], 3.0)
        fz.clear(); self.assertEqual(len(fz), 0)

    def test_connect_and_find_instances(self):
        lv = Q.connect_live(self.c, Proj(self.sdk), log=lambda m: None)
        self.assertIs(Q.connect_live(self.c, Proj(self.sdk), cached=lv), lv)   # Cache
        t = tgt(self.sdk, "Health")
        rows = Q.find_instances(lv, t)
        self.assertEqual({r["addr"] for r in rows}, {self.ref["p1"], self.ref["p2"]})
        r1 = next(r for r in rows if r["addr"] == self.ref["p1"])
        self.assertEqual(r1["vaddr"], self.ref["p1"] + 0x80)
        self.assertEqual(Q.read_value(self.c.read_memory, r1["vaddr"], t)[1], "75.5")

    def test_target_lists(self):
        cands = uecheat.find_candidates(self.sdk, 4)
        ts = Q.targets_from_candidates(self.sdk, cands)
        keys = {t.key: t for t in ts}
        self.assertIn("UHealthComponent.Health", keys)
        self.assertEqual(keys["UHealthComponent.bIsEnableMuteki"].bit, 2)
        allm = {t.key for t in Q.targets_from_all_members(self.sdk)}
        self.assertTrue({"UHealthComponent.Gold", "UHealthComponent.Level", "UHealthComponent.Big"} <= allm)


class GuiFlow(unittest.TestCase):
    def setUp(self):
        import tools_uelive_gui as G
        G.CFG = os.path.join(os.path.dirname(__file__), "_no_cfg.json")
        self.im, self.ref, self.sdk, self.c = world()
        self.win = type("W", (), {})()
        self.win.client, self.win.logs, self.win.went = self.c, [], []
        self.win.bg = lambda fn, ok=None, err=None, lock=True: self._bg(fn, ok, err)
        self.win.log = lambda m, k="info": self.win.logs.append((k, m))
        self.win.ui = lambda fn: fn()
        self.win.goto_memory = lambda a: self.win.went.append(("mem", a))
        self.win.to_debug_watch = lambda a, n: self.win.went.append(("watch", a, n))
        self.win.app = type("A", (), {"IMAGE_BASE": TL.BASE})()
        self.t = G.UeLiveTab(None, self.win)
        self.t.proj = Proj(self.sdk); self.t.proj.title = "T"
        self.t.cands = uecheat.find_candidates(self.sdk, 4)
        self.t._rebuild_targets()

    def _bg(self, fn, ok, err):
        try: r = fn()
        except Exception as e:
            (err or (lambda e: self.win.logs.append(("err", str(e)))))(e); return
        if ok: ok(r)

    def pick(self, key):
        iid = next(k for k, v in self.t.tl.rows.items() if v[0] == key)
        self.t.tl.sel = (iid,); self.t._on_pick(); self.t.refind()

    def row_of(self, addr):
        return str(next(i for i, r in enumerate(self.t.rows) if r["addr"] == addr))

    def errs(self): return [m for k, m in self.win.logs if k == "err"]

    def test_click_shows_live_values_and_sets(self):
        t = self.t; self.pick("UHealthComponent.Health")
        self.assertEqual(len(t.rows), 2, self.win.logs)
        self.assertEqual(t.rows[0]["txt"], "75.5")                             # nichtnull zuerst
        t.tr.sel = ("0",); t.v_val.set("999"); t.set_value()
        self.assertEqual(struct.unpack("<f", self.im.read(self.ref["p1"] + 0x80, 4))[0], 999.0, self.win.logs)
        t.v_val.set("*2"); t.set_value()
        self.assertEqual(struct.unpack("<f", self.im.read(self.ref["p1"] + 0x80, 4))[0], 1998.0)
        self.assertEqual(t.tr.rows["0"][1], "1998")
        t.v_val.set("abc"); t.set_value(); self.assertTrue(self.errs())

    def test_freeze_and_live_tick(self):
        t = self.t; p = self.ref["p1"]; self.pick("UHealthComponent.Health")
        t.tr.sel = ("0",); t.v_val.set("500"); t.freeze_sel()
        self.assertEqual(len(t.freezer), 1); self.assertEqual(t.tr.rows["0"][0], "❄")
        self.im.w(p + 0x80, struct.pack("<f", 1.0))                            # Spiel zieht Leben ab
        t._tick()
        self.assertEqual(struct.unpack("<f", self.im.read(p + 0x80, 4))[0], 500.0)
        t.unfreeze_all(); self.assertEqual(len(t.freezer), 0)
        self.im.w(p + 0x80, struct.pack("<f", 7.0)); t._tick()                 # nur lesen, nichts erzwingen
        self.assertEqual(t.rows[0]["txt"], "7"); self.assertFalse(self.errs())

    def test_bool_buttons_and_dialog(self):
        t = self.t; p = self.ref["p1"]; self.pick("UHealthComponent.bIsEnableMuteki")
        t.tr.sel = (self.row_of(p),); t._quick("an")
        self.assertEqual(self.im.read(p + 0x98, 1)[0] & 4, 4)
        t.freeze_sel(); self.assertEqual(len(t.freezer), 1)
        import tkinter.simpledialog as sd
        sd.askstring = lambda *a, **k: "aus"
        t.unfreeze_all(); t.edit_dialog()
        self.assertEqual(self.im.read(p + 0x98, 1)[0] & 4, 0, self.win.logs)

    def test_set_to_max_and_scope_all(self):
        t = self.t; p = self.ref["p1"]; self.pick("UHealthComponent.Health")
        t.tr.sel = (self.row_of(p),); t.set_to_max()
        self.assertEqual(struct.unpack("<f", self.im.read(p + 0x80, 4))[0], 100.0, self.win.logs)
        t.v_scope.set("alle Instanzen"); t.v_val.set("42"); t.set_value()
        for obj in (self.ref["p1"], self.ref["p2"]):
            self.assertEqual(struct.unpack("<f", self.im.read(obj + 0x80, 4))[0], 42.0)

    def test_filters_navigation_and_no_selection(self):
        t = self.t; self.pick("UHealthComponent.Gold")
        t._render(); self.assertEqual(len(t.tr.rows), len(t.rows))             # keine Filter mehr: alle Instanzen sichtbar
        t.tr.sel = (); t.v_val.set("5"); t.set_value()
        self.assertTrue(any("Zeile" in m for k, m in self.win.logs))          # freundlicher Hinweis statt Absturz
        t.tr.sel = ("0",); t.to_memory(); t.to_watch()
        self.assertEqual(self.win.went[0], ("mem", self.ref["p1"] + 0x88)); self.assertEqual(self.win.went[1][0], "watch")

    def test_second_pick_keeps_index_new_button_rebuilds(self):
        t = self.t; self.pick("UHealthComponent.Health")
        idx = t.live.index
        self.pick("UHealthComponent.Gold")
        self.assertIs(t.live.index, idx)                       # kein teurer Neuaufbau beim Weiterklicken
        t.refind(force=True)
        self.assertIsNot(t.live.index, idx)                    # INSTANZEN NEU liest frisch

    def test_not_connected(self):
        t = self.t; self.pick("UHealthComponent.Health"); self.win.client = None
        t.tr.sel = ("0",); t.v_val.set("1"); t.set_value()
        self.assertTrue(any("nicht verbunden" in m for m in self.errs()))
        t._tick()                                                              # kein Absturz ohne Verbindung


if __name__ == "__main__":
    unittest.main()


class Robust(unittest.TestCase):
    def test_garbage_class_pointers_do_not_crash(self):
        """Regression (echter Log): 'Q' format requires 0 <= number <= 2**64-1 bei toten Objekten."""
        im, ref, sdk, c = world()
        lv = Q.connect_live(c, Proj(sdk), log=lambda m: None)
        lv.build_index()
        junk = 0xFFFFFFFFFFFFFFF0
        lv.index[0x10300000] = (999999, junk, "Totes")            # Klassenzeiger ausserhalb des Adressraums
        lv.index[0x10300100] = (999998, 0, "Null")
        lv.index[0x10300200] = (999997, 0x10, "Winzig")
        self.assertEqual(lv.ancestors(junk), frozenset())
        self.assertFalse(lv.is_a(junk, ref["health"]))
        rows = Q.find_instances(lv, tgt(sdk, "Health"))
        self.assertEqual({r["addr"] for r in rows}, {ref["p1"], ref["p2"]})
        with self.assertRaises(OSError):
            lv.rd(junk, 0x40)                                      # klarer Fehler statt struct.error

if __name__ == "__main__":
    unittest.main()
