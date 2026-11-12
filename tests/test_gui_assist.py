"""Tab ASSISTENT mit Attrappen (ghost_tk): Scanner-Schritte, Watchpoint-Treffer -> schreibender Befehl, PRESET-Weitergabe."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk  # noqa: E402

ghost_tk.install()
import asm_tools as AT  # noqa: E402
import ps5_ext as X  # noqa: E402
import test_assist as TA  # noqa: E402
import tools_assist_gui as G  # noqa: E402


class FakeSc:
    def __init__(self):
        self.first_scan_done, self.count, self.vname = False, 0, "Int32"

    def results(self, start, n):
        return [{"addr": 0x5010 + 0x100 * i, "cur": (100 - i).to_bytes(4, "little"), "prev": b"", "first": b""}
                for i in range(min(self.count, n))]


class FakeScan:
    def __init__(self):
        self.vt, self.ct, self.v1, self.v2 = (ghost_tk.Var(value=x) for x in ("Int32", "Genau", "", ""))
        self.running = False
        self.sc = None
        self.calls = []
        self.n_first, self.n_next = 40, 3

    def _ct_values(self, first): pass
    def _ct_changed(self): pass

    def scan_first(self):
        self.calls.append(("first", self.vt.get(), self.ct.get(), self.v1.get()) + ((self.v2.get(),) if self.v2.get() else ()))
        self.sc = FakeSc()
        self.sc.first_scan_done, self.sc.count, self.sc.vname = True, self.n_first, self.vt.get()
        self.running = True                                  # wie das echte ScanTab: laeuft bis zum Ende des Jobs

    def scan_next(self):
        self.calls.append(("next", self.ct.get(), self.v1.get()) + ((self.v2.get(),) if self.v2.get() else ()))
        self.sc.count = self.n_next
        self.running = True

    def new_scan(self): self.calls.append(("new",))


class FakeSess:
    attached = True

    def __init__(self):
        self.set, self.cleared, self.resumed = [], [], 0

    def free_wp_index(self): return 0
    def set_watchpoint(self, idx, addr, size, typ): self.set.append((idx, addr, size, typ))
    def clear_watchpoint(self, idx): self.cleared.append(idx)
    def resume(self): self.resumed += 1


class FakeDbg:
    def __init__(self):
        self.sess, self.hit_items = FakeSess(), {}

    def _fill_wps(self): pass
    def attach(self): pass


class FakeClient:
    def __init__(self, mem): self.mem = mem
    def read_memory(self, a, n): return self.mem[a][:n] if a in self.mem else b"\x90" * n


class FakeDis:
    def __init__(self): self.asked = []
    def recipe_at(self, a, t): self.asked.append((a, t))


class FakeWin:
    def __init__(self, mem=None):
        self.scan_tab, self.dbg_tab, self.t_dis = FakeScan(), FakeDbg(), FakeDis()
        self.client, self.logs, self.went = FakeClient(mem or {}), [], []
        self.app = type("A", (), {"IMAGE_BASE": 0x400000})()

    def bg(self, fn, ok=None, err=None, lock=True):
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            return (err or (lambda e: self.logs.append(("err", str(e)))))(e)
        if ok:
            ok(r)

    def ui(self, fn): fn()
    def log(self, m, k="info"): self.logs.append((k, m))
    def goto_disasm(self, a): self.went.append(("dis", a))


class T(unittest.TestCase):
    def setUp(self):
        self.w = FakeWin()
        self.t = G.AssistTab(None, self.w)
        self.st = self.w.scan_tab

    def finish(self, first):
        """Scan-Job fertig (im echten Fenster pollt der Tab per after())."""
        self.st.running = False
        self.t._after_scan(first)

    def test_search_known_number(self):
        self.st.n_first = 6000
        self.t.v_num.set("100")
        self.t.start_search()
        self.assertEqual(self.st.calls[0], ("first", "Int32", "Genau", "100"))
        self.finish(True)
        self.assertIn("Treffer", self.t.lbl_count._text)               # 6000 Treffer -> "viel zu viele"
        self.assertEqual(len(self.t.tv_c.get_children()), 0)             # zu viele fuer die Liste

    def test_search_float_and_unknown_and_bad_input(self):
        self.t.v_num.set("9,5")
        self.t.start_search()
        self.assertEqual(self.st.calls[-1][1:], ("Float", "Ungefähr (Float)", "9.5"))
        self.st.running = False
        self.t.v_unknown.set(True)
        self.t.start_search()
        self.assertEqual(self.st.calls[-1][2], "Unbekannter Startwert")
        n = len(self.st.calls)
        self.t.v_unknown.set(False)
        self.t.v_num.set("abc")
        self.t.start_search()
        self.assertEqual(len(self.st.calls), n)
        self.assertEqual(self.w.logs[-1][0], "warn")

    def test_narrow_down_fills_candidates(self):
        self.t.v_num.set("100")
        self.t.start_search()
        self.t.v_new.set("90")
        self.finish(True)
        self.t.narrow("exact")
        self.assertEqual(self.st.calls[-1], ("next", "Genau", "90"))
        self.finish(False)
        self.assertEqual(len(self.t.tv_c.get_children()), 3)
        self.assertEqual(self.t.tv_c.item("20752", "values")[0], "0x5110")
        self.st.running = False
        self.t.narrow("down")
        self.assertEqual(self.st.calls[-1], ("next", "Kleiner geworden", ""))

    def test_fuzzy_search_by_typing_a_range(self):
        self.t.v_num.set("75~5")
        self.t.start_search()
        self.assertEqual(self.st.calls[-1], ("first", "Int32", "Fuzzy (± Toleranz)", "75", "5"))

    def test_fuzzy_search_by_checkbox_and_tolerance_field(self):
        self.t.v_approx.set(True)
        self.t.v_tol.set("10%")
        self.t.v_num.set("0.7")
        self.t.start_search()
        self.assertEqual(self.st.calls[-1], ("first", "Float", "Fuzzy (± Toleranz)", "0.7", "10%"))

    def test_fuzzy_unknown_float_and_changed_button(self):
        self.t.v_unknown.set(True)
        self.t.v_float.set(True)
        self.t.start_search()
        self.assertEqual(self.st.calls[-1][1:3], ("Float", "Unbekannter Startwert"))
        self.finish(True)
        self.t.narrow("changed")
        self.assertEqual(self.st.calls[-1], ("next", "Verändert", ""))

    def test_fuzzy_narrowing_uses_type_of_running_search(self):
        self.t.v_num.set("100")
        self.t.start_search()
        self.finish(True)
        self.t.v_new.set("90~5")
        self.t.narrow("exact")
        self.assertEqual(self.st.calls[-1], ("next", "Fuzzy (± Toleranz)", "90", "5"))

    def test_fuzzy_bad_input_is_reported_not_scanned(self):
        n = len(self.st.calls)
        self.t.v_num.set("abc~5")
        self.t.start_search()
        self.assertEqual(len(self.st.calls), n)
        self.assertEqual(self.w.logs[-1][0], "warn")

    def test_narrow_needs_first_scan(self):
        self.t.narrow("down")
        self.assertEqual(self.w.logs[-1], ("warn", "Erst in Schritt 1 SUCHEN"))

    @unittest.skipUnless(TA.TOOLS, "GNU as/objdump fehlen")
    def test_watch_hit_finds_writer_resumes_and_presets(self):
        rip = 0x7000100
        code = TA.assemble("mov eax, 5\nsub dword ptr [rbx+0x10], eax")
        before = b"\x90" * (16 - len(code)) + code
        self.w.client.mem[rip - 16] = before
        old = AT.disassemble_lines
        AT.disassemble_lines = TA.disasm
        self.addCleanup(setattr, AT, "disassemble_lines", old)
        # Treffer auswaehlen
        self.t.cands["20752"] = (0x5010, "Int32")
        self.t.tv_c.insert("", "end", iid="20752", values=("0x5010", "90"))
        self.t.tv_c.selection_set(["20752"])
        self.t.start_watch()
        sess = self.w.dbg_tab.sess
        self.assertEqual(sess.set, [(0, 0x5010, 4, X.WP_WRITE)])
        self.assertTrue(self.t.watching)
        hit = {"kind": "WP", "addr": 0x5010, "regs": {"rip": rip, "rbx": 0x5000, "rax": 5}}
        self.w.dbg_tab.hit_items["h1"] = hit
        self.t._poll_hits(self.w.dbg_tab, 0x5010, 4)
        self.assertEqual(sess.resumed, 1)
        rows = self.t.tv_w.get_children()
        self.assertEqual(len(rows), 1)
        vals = self.t.tv_w.item(rows[0], "values")
        self.assertIn("sub", vals[1].lower())
        self.assertEqual(vals[3], 1)
        # Schritt 4
        self.t.tv_w.selection_set(rows)
        self.t.to_preset()
        self.assertEqual(self.w.t_dis.asked[0][0], int(rows[0]))
        self.assertFalse(self.t.watching)
        self.assertEqual(sess.cleared, [0])

    def test_watch_needs_selection_and_alignment(self):
        self.t.start_watch()
        self.assertEqual(self.w.logs[-1][0], "warn")
        self.t.cands["1"] = (0x5011, "Int32")
        self.t.tv_c.insert("", "end", iid="1", values=("0x5011", "1"))
        self.t.tv_c.selection_set(["1"])
        self.t.start_watch()
        self.assertEqual(self.w.logs[-1][0], "err")

    def test_step4_needs_a_selected_instruction(self):
        self.t.to_preset()
        self.assertEqual(self.w.went, [])
        self.assertEqual(self.w.logs[-1], ("warn", "Erst in Schritt 3 einen Befehl markieren"))


if __name__ == "__main__":
    unittest.main()
