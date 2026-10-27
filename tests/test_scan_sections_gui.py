"""Cheat-Searcher: Bereichsliste (Panel) + Anbindung an den Scan - ohne Display (ghost_tk)."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import regionfilter as RF
import tools_i18n as T
from test_regionfilter import MAPS


class FakeClient:
    def get_maps_named(self): return MAPS


class FakeWin:
    def __init__(self):
        self.client = FakeClient(); self.logs = []; self.went = []
        self.app = type("A", (), {"IMAGE_BASE": 0x400000, "backend": object()})()
    def bg(self, fn, ok=None, err=None, lock=True):
        try: r = fn()
        except Exception as e:
            (err or (lambda e: self.logs.append(("err", str(e)))))(e); return
        if ok: ok(r)
    def ui(self, fn): fn()
    def log(self, m, k="info"): self.logs.append((k, m))
    def goto_memory(self, a): self.went.append(a)


def make():
    os.environ["REAPERPY_HOME"] = tempfile.mkdtemp()
    import tools_scan_gui as S
    w = FakeWin()
    return S.ScanTab(None, w), w


class Panel(unittest.TestCase):
    def test_refresh_fills_tree_and_summary(self):
        tab, w = make()
        tab.panel.refresh()
        rows = tab.panel.tv.rows
        self.assertIn("c:eboot", rows)
        self.assertEqual(len([k for k in rows if k.startswith("s:mod:eboot.bin")]), 3)   # eboot aufgesplittet
        self.assertIn("Ausgewählt:", tab.panel.lbl_sum._text)

    def test_default_hides_syslibs_in_tree_and_in_scan_pick(self):
        tab, w = make()
        tab.panel.set_maps(MAPS)
        info = tab.panel.tv.rows["s:lib:libc.prx"][3]
        self.assertIn("ausgeblendet", info)
        pick = tab.panel.make_pick("rw")
        got = pick(MAPS)
        self.assertNotIn(0x10000000, got)
        self.assertIn(0x200000000, got)

    def test_click_toggle_and_persistence(self):
        tab, w = make()
        p = tab.panel
        p.set_maps(MAPS)
        p.tv.sel = ("s:lib:Il2CppUserAssemblies.prx",)
        p._toggle("s:lib:Il2CppUserAssemblies.prx")
        self.assertNotIn(0x30000000, p.make_pick("rw")(MAPS))
        back = RF.load_state(p._path())
        self.assertIn("lib:Il2CppUserAssemblies.prx", back.off)

    def test_buttons(self):
        tab, w = make()
        p = tab.panel; p.set_maps(MAPS)
        p.sel_eboot(); self.assertEqual(p.make_pick("all")(MAPS), {0x400000, 0x6470000, 0x72DC000})
        p.sel_none(); self.assertEqual(p.make_pick("all")(MAPS), set())
        p.sel_all(); self.assertTrue(p.make_pick("all")(MAPS))
        p.sel_game(); got = p.make_pick("all")(MAPS)
        self.assertIn(0x200000000, got); self.assertNotIn(0x400000000, got)

    def test_hide_module_from_context_menu(self):
        tab, w = make()
        p = tab.panel; p.set_maps(MAPS)
        secs = [p.rows["s:lib:Il2CppUserAssemblies.prx"][1]]
        p._hide_modules(secs)
        self.assertIn("il2cppuserassemblies.prx", RF.split_patterns(p.state.custom))
        self.assertNotIn(0x30000000, p.make_pick("rw")(MAPS))

    def test_scope_change_updates_counts(self):
        tab, w = make()
        p = tab.panel; p.set_maps(MAPS)
        tab.scope.set("Alles Lesbare"); p.on_scope_changed()
        a = p.lbl_sum._text
        tab.scope.set("Daten (rw, ohne Code)"); p.on_scope_changed()
        self.assertNotEqual(a, p.lbl_sum._text)

    def test_english_labels_exist_for_regionfilter_texts(self):
        from tools_i18n_en import EN
        texts = list(RF.CATS.values()) + [v[0] for v in RF.PRESETS.values()] + [RF.SMALL_LABEL, RF.CUSTOM_LABEL,
                "Code-Bereich", "Daten-Bereich", "Nur-Lesen-Bereich"]
        self.assertEqual([t for t in texts if t not in EN], [])
        T.set_lang("en")
        try:
            tab, w = make(); tab.panel.set_maps(MAPS)
            self.assertIn("regions", tab.panel.tv.rows["c:heap"][3])
        finally:
            T.set_lang("de")


if __name__ == "__main__":
    unittest.main()
