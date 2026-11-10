"""EDIT CHEATS: Einfach-/Erweitert-Modus und automatische Signatur beim Speichern (ohne Display, ohne Konsole)."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk  # noqa: E402

ghost_tk.install()
import tools_gui as G  # noqa: E402
import tools_i18n as T  # noqa: E402


class FakeText:
    def __init__(self, s=""):
        self.s = s

    def get(self, a, b=None):
        return self.s

    def insert(self, idx, s):
        self.s += s

    def delete(self, a, b=None):
        self.s = ""

    def configure(self, **k):
        pass


class Part:
    """Ersatz fuer einen Rahmen: merkt sich pack / pack_forget in einer gemeinsamen Liste."""
    def __init__(self, name, calls):
        self.name, self.calls = name, calls

    def pack(self, **kw):
        self.calls.append(("pack", self.name, kw.get("before")))

    def pack_forget(self):
        self.calls.append(("forget", self.name))


class Win:
    def __init__(self, client=True, cfg=None):
        self.client = types.SimpleNamespace(get_maps=lambda: []) if client else None
        self.logs = []
        self.app = types.SimpleNamespace(IMAGE_BASE=0x400000, PATCH_DIR="", cfg=cfg if cfg is not None else {},
                                         load_patches=lambda: None)

    def bg(self, fn, ok=None, err=None, lock=True):
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            return (err or (lambda e: self.logs.append(("err", str(e)))))(e)
        if ok:
            ok(r)

    def log(self, m, k="info"):
        self.logs.append((k, m))


class Base(unittest.TestCase):
    def setUp(self):
        self.win = Win()
        self.tab = self.make()
        self.saved = []
        self.tab._save_now = lambda: self.saved.append(dict(self.tab.v_snapshot()))
        self.tab.v_snapshot = lambda: {k: v.get() for k, v in self.tab.v.items()}
        self._sig = G.AOB.make_signature
        self._cfgsave = G.projects.save_config
        self.cfg_writes = []
        G.projects.save_config = lambda cfg: self.cfg_writes.append(dict(cfg))

    def tearDown(self):
        G.AOB.make_signature = self._sig
        G.projects.save_config = self._cfgsave

    def make(self, cfg=None):
        tab = G.CheatTab(None, self.win if cfg is None else Win(cfg=cfg))
        tab.t_def, tab.t_new, tab.t_cave = FakeText("48 8B 05 00 00 00 00"), FakeText("90 90 90 90 90 90 90"), FakeText()
        tab.v["name"].set("Unendlich Leben")
        tab.v["offset"].set("0x1234")
        return tab

    def fill_ok(self):
        self.tab.v["name"].set("Unendlich Leben")
        self.tab.v["offset"].set("0x1234")


class Modes(Base):
    def test_starts_simple_by_default(self):
        self.assertFalse(self.tab.v_adv.get())

    def test_saved_choice_is_read_from_config(self):
        self.assertTrue(self.make(cfg={"cheat_editor_advanced": True}).v_adv.get())
        self.assertFalse(self.make(cfg={}).v_adv.get())

    def test_apply_mode_hides_and_shows_in_fixed_order(self):
        calls = []
        anchors = [object(), object(), object()]
        self.tab._adv_parts = [(Part(n, calls), {}, a) for n, a in zip(("type", "cave", "sig"), anchors)]
        self.tab.v_adv.set(False)
        self.tab._apply_mode()
        self.assertEqual(calls, [("forget", "type"), ("forget", "cave"), ("forget", "sig")])
        calls.clear()
        self.tab.v_adv.set(True)
        self.tab._apply_mode()
        self.assertEqual([c[:2] for c in calls],           # erst alle weg, dann in der alten Reihenfolge zurueck
                         [("forget", "type"), ("forget", "cave"), ("forget", "sig"),
                          ("pack", "type"), ("pack", "cave"), ("pack", "sig")])
        self.assertEqual([c[2] for c in calls[3:]], anchors)

    def test_toggle_remembers_the_choice(self):
        tab = self.make(cfg={})
        tab.v_adv.set(True)
        tab._toggle_mode()
        self.assertEqual(self.cfg_writes[-1]["cheat_editor_advanced"], True)
        tab.v_adv.set(False)
        tab._toggle_mode()
        self.assertEqual(self.cfg_writes[-1]["cheat_editor_advanced"], False)

    def test_hint_text_follows_the_mode_and_the_language(self):
        tab = self.tab
        shown = []
        tab.lbl_mode = types.SimpleNamespace(configure=lambda **k: shown.append(k["text"]))
        tab.v_adv.set(False)
        tab._update_hint()
        self.assertIn("Einfach:", shown[-1])
        tab.v_adv.set(True)
        tab._update_hint()
        self.assertIn("Erweitert:", shown[-1])
        old = T.lang()
        T.set_lang("en")
        try:
            tab.v_adv.set(False)
            tab._update_hint()
            self.assertIn("Simple:", shown[-1])
            tab.v_adv.set(True)
            tab._update_hint()
            self.assertIn("Advanced:", shown[-1])
        finally:
            T.set_lang(old)

    def test_simple_mode_says_when_a_cave_is_used(self):
        tab = self.tab
        shown = []
        tab.lbl_mode = types.SimpleNamespace(configure=lambda **k: shown.append(k["text"]))
        tab.v_type.set("cave")
        tab.t_cave = FakeText("  mov eax, 1\n  jmp OriginReturn\n")
        tab.v_adv.set(False)
        tab._update_hint()
        self.assertIn("Code-Cave (2 Zeilen)", shown[-1])
        tab.v_adv.set(True)
        tab._update_hint()
        self.assertNotIn("Code-Cave", shown[-1])


class ReturnLen(Base):
    """OriginReturn: leer = automatisch aus ORIGINAL (ganze Befehle), eingetragen = gilt, aber mindestens 8 (Hook-Laenge)."""
    HEX9 = "48 8B 05 00 00 00 00 90 90"                 # 9 Byte

    def setUp(self):
        super().setUp()
        self._bch = G.AT.build_cave_hook
        self.tab.v_type.set("cave")
        self.tab.t_cave = FakeText("  jmp OriginReturn\n")

    def tearDown(self):
        G.AT.build_cave_hook = self._bch
        super().tearDown()

    def fake_hook(self, size, calls=None):
        def f(data, addr, min_len=8):
            if calls is not None:
                calls.append((bytes(data), addr))
            return {"size": size}
        G.AT.build_cave_hook = f

    def test_default_field_is_empty(self):
        self.assertEqual(self.tab.v["ret"].get(), "")
        self.tab.v["ret"].set("12")
        self.tab.clear()
        self.assertEqual(self.tab.v["ret"].get(), "")

    def test_manual_value_counts(self):
        self.tab.v["ret"].set("9")
        self.assertEqual(self.tab._return_len(), (9, "manual"))
        self.tab.v["ret"].set("0x0A")
        self.assertEqual(self.tab._return_len(), (10, "manual"))

    def test_manual_value_below_hook_length_is_rejected(self):
        self.tab.v["ret"].set("5")
        with self.assertRaises(ValueError) as cm:
            self.tab._return_len()
        self.assertIn("zu klein", str(cm.exception))
        self.assertIn("8", str(cm.exception))

    def test_manual_value_must_be_a_number(self):
        self.tab.v["ret"].set("abc")
        with self.assertRaises(ValueError) as cm:
            self.tab._return_len()
        self.assertIn("Zahl", str(cm.exception))

    def test_auto_uses_whole_instructions_from_original(self):
        calls = []
        self.fake_hook(9, calls)
        self.tab.t_def = FakeText("48 8B 05 00 00 00 00 90 90 90 90")    # 11 Byte, Befehlsgrenze bei 9
        self.assertEqual(self.tab._return_len(), (9, "auto"))
        self.assertEqual(calls, [(bytes.fromhex("488B05000000009090 9090".replace(" ", "")), 0)])

    def test_auto_falls_back_to_the_byte_count_without_disassembler(self):
        def boom(*a, **k):
            raise RuntimeError("capstone fehlt")
        G.AT.build_cave_hook = boom
        self.tab.t_def = FakeText(self.HEX9)
        self.assertEqual(self.tab._return_len(), (9, "auto"))

    def test_too_few_original_bytes_use_the_default(self):
        self.tab.t_def = FakeText("48 8B 05 00 00 00 00")                  # 7 Byte
        self.assertEqual(self.tab._return_len(), (8, "default"))
        self.tab.t_def = FakeText("")
        self.assertEqual(self.tab._return_len(), (8, "default"))
        self.tab.t_def = FakeText("kein hex")
        self.assertEqual(self.tab._return_len(), (8, "default"))

    def test_build_json_writes_the_derived_value_for_caves_only(self):
        self.fake_hook(9)
        self.tab.t_def = FakeText(self.HEX9)
        ret = [v for v in self.tab.build_json()["Variables"] if v["label"] == "OriginReturn"]
        self.assertEqual([r["offset"] for r in ret], [9])
        self.tab.v_type.set("patch")
        self.assertFalse([v for v in self.tab.build_json()["Variables"] if v["label"] == "OriginReturn"])

    def test_build_json_rejects_a_too_small_value(self):
        self.tab.v["ret"].set("4")
        with self.assertRaises(ValueError):
            self.tab.build_json()

    def test_log_says_where_the_value_comes_from(self):
        self.fake_hook(9)
        self.tab.t_def = FakeText(self.HEX9)
        self.tab._note_return_len()
        self.assertEqual(self.win.logs[-1][0], "info")
        self.assertIn("automatisch: 9 Bytes", self.win.logs[-1][1])
        self.tab.t_def = FakeText("90")
        self.tab._note_return_len()
        self.assertEqual(self.win.logs[-1][0], "warn")
        n = len(self.win.logs)
        self.tab.v["ret"].set("9")                                          # von Hand: nichts zu melden
        self.tab._note_return_len()
        self.tab.v["ret"].set("")
        self.tab.v_type.set("patch")                                        # kein Cave: nichts zu melden
        self.tab._note_return_len()
        self.assertEqual(len(self.win.logs), n)

    def test_saving_reports_a_bad_value_and_does_not_save(self):
        errors = []
        old = G.messagebox.showerror
        G.messagebox.showerror = lambda *a, **k: errors.append(a)
        try:
            self.tab.v_adv.set(True)
            self.tab.v["ret"].set("3")
            self.tab.save()
        finally:
            G.messagebox.showerror = old
        self.assertEqual(self.saved, [])
        self.assertIn("zu klein", errors[0][1])

    def test_disassembler_template_sets_an_explicit_value(self):
        self.tab.fill_hook({"addr": 0x401234, "size": 10, "default": "48 8B 05 00 00 00 00 90 90 90",
                            "new": "jmp OriginTarget", "cave": "mov eax, 1\njmp OriginReturn"})
        self.assertEqual(self.tab._return_len(), (10, "manual"))

    def test_english(self):
        self.tab.v["ret"].set("3")
        old = T.lang()
        T.set_lang("en")
        try:
            with self.assertRaises(ValueError) as cm:
                self.tab._return_len()
        finally:
            T.set_lang(old)
        self.assertIn("too small", str(cm.exception))


class AutoSignature(Base):
    def test_simple_mode_creates_the_signature_then_saves(self):
        seen = {}

        def fake(client, maps, addr, hl):
            seen.update(addr=addr, hl=hl)
            return ("48 8B 05 ?? ?? ?? ??", 0)
        G.AOB.make_signature = fake
        self.tab.v_adv.set(False)
        self.tab.save()
        self.assertEqual(seen, {"addr": 0x400000 + 0x1234, "hl": 7})        # Hook-Laenge = Laenge der Originalbytes
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["aob"], "48 8B 05 ?? ?? ?? ??")
        self.assertEqual(self.saved[0]["aoboff"], "0")
        self.assertTrue(any("automatisch" in m for _k, m in self.win.logs))

    def test_cave_uses_the_cave_hook_length(self):
        seen = {}
        G.AOB.make_signature = lambda c, m, a, hl: (seen.update(hl=hl), ("AA BB", 0))[1]
        self.tab.v_type.set("cave")
        self.tab.t_cave = FakeText("  mov eax, 1\n  jmp OriginReturn\n")
        self.tab.save()
        self.assertEqual(seen["hl"], 8)

    def test_failed_signature_still_saves_and_warns(self):
        def boom(*a):
            raise RuntimeError("nicht eindeutig")
        G.AOB.make_signature = boom
        self.tab.save()
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["aob"], "")
        warn = [m for k, m in self.win.logs if k == "warn"]
        self.assertTrue(warn and "nicht eindeutig" in warn[-1])

    def test_offline_saves_without_signature_and_says_so(self):
        self.win.client = None
        G.AOB.make_signature = lambda *a: self.fail("darf nicht aufgerufen werden")
        self.tab.save()
        self.assertEqual(len(self.saved), 1)
        self.assertTrue(any(k == "warn" and "Nicht verbunden" in m for k, m in self.win.logs))

    def test_existing_signature_is_kept(self):
        G.AOB.make_signature = lambda *a: self.fail("darf nicht aufgerufen werden")
        self.tab.v["aob"].set("11 22 33")
        self.tab.save()
        self.assertEqual(self.saved[0]["aob"], "11 22 33")

    def test_advanced_mode_does_not_touch_the_signature(self):
        G.AOB.make_signature = lambda *a: self.fail("darf nicht aufgerufen werden")
        self.tab.v_adv.set(True)
        self.tab.save()
        self.assertEqual(self.saved[0]["aob"], "")

    def test_invalid_input_is_reported_before_anything_else(self):
        errors = []
        old = G.messagebox.showerror
        G.messagebox.showerror = lambda *a, **k: errors.append(a)
        try:
            G.AOB.make_signature = lambda *a: self.fail("darf nicht aufgerufen werden")
            self.tab.v["name"].set("")
            self.tab.save()
        finally:
            G.messagebox.showerror = old
        self.assertEqual(self.saved, [])
        self.assertIn("Name fehlt", errors[0][1])

    def test_english_messages(self):
        self.win.client = None
        old = T.lang()
        T.set_lang("en")
        try:
            self.tab.save()
        finally:
            T.set_lang(old)
        self.assertTrue(any("Not connected" in m for _k, m in self.win.logs))


if __name__ == "__main__":
    unittest.main()
