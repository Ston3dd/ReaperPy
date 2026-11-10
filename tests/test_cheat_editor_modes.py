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
