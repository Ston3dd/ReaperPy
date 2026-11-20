"""cheat_from_disasm.py + Disassembler-Knoepfe: markierte Zeilen -> NOP-/Cave-Cheat."""
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk  # noqa: E402

ghost_tk.install()
import asm_tools as AT  # noqa: E402
import cheat_from_disasm as CD  # noqa: E402
import patch_engine as PE  # noqa: E402
import reapatch as RP  # noqa: E402
import tools_gui as G  # noqa: E402

BASE = 0x400000


def ln(addr, data, mnemonic="mov", op="eax, ebx"):
    return {"addr": addr, "size": len(data), "bytes": bytes(data), "mnemonic": mnemonic, "op_str": op}


A = ln(BASE + 0x1000, b"\x48\x89\x5b\x1c")          # 4 Byte
B = ln(BASE + 0x1004, b"\x89\xc1")                  # 2 Byte, direkt dahinter
C = ln(BASE + 0x1010, b"\x83\xc0\x05")              # 3 Byte, mit Luecke


class Runs(unittest.TestCase):
    def test_adjacent_lines_form_one_run(self):
        rs = CD.runs([A, B])
        self.assertEqual([(r["addr"], r["size"], len(r["lines"])) for r in rs], [(A["addr"], 6, 2)])

    def test_gap_makes_separate_runs_and_input_order_does_not_matter(self):
        rs = CD.runs([C, B, A])
        self.assertEqual([(r["addr"], r["size"]) for r in rs], [(A["addr"], 6), (C["addr"], 3)])

    def test_empty_selection(self):
        self.assertEqual(CD.runs([]), [])

    def test_hex_text(self):
        rs = CD.runs([A, B])
        self.assertEqual(CD.run_hex(rs[0]), "48 89 5B 1C 89 C1")
        self.assertEqual(CD.nop_hex(3), "90 90 90")

    def test_summary(self):
        self.assertEqual(CD.summary(CD.runs([A, B, C])), (3, 2, 9))


class NopDraft(unittest.TestCase):
    def test_single_run_has_plain_hex_and_name_from_offset(self):
        d = CD.nop_draft(CD.runs([A, B]), BASE)
        self.assertEqual((d["addr"], d["type"], d["name"]), (A["addr"], "patch", "NOP_1000"))
        self.assertEqual(d["default"], "48 89 5B 1C 89 C1")
        self.assertEqual(d["new"], "90 90 90 90 90 90")

    def test_explicit_name_wins(self):
        self.assertEqual(CD.nop_draft(CD.runs([A]), BASE, "Unendlich HP")["name"], "Unendlich HP")

    def test_further_runs_become_offset_segments(self):
        d = CD.nop_draft(CD.runs([A, C]), BASE)
        self.assertEqual(d["default"], "48 89 5B 1C\n+0x1010: 83 C0 05")
        self.assertEqual(d["new"], "90 90 90 90\n+0x1010: 90 90 90")

    def test_run_below_image_base_uses_an_absolute_address(self):
        low = ln(0x1000, b"\x90\x90")
        d = CD.nop_draft(CD.runs([A, low]), BASE)
        self.assertEqual(d["addr"], 0x1000)                                  # die niedrigste Stelle ist die Haupt-Stelle
        self.assertIn(f"+0x{A['addr'] - BASE:X}: ", d["new"])

    def test_engine_reads_the_text_back_as_the_same_sites(self):
        """Rundlauf: ReapPatch + _plan_sites muessen genau die markierten Stellen mit Original und NOPs liefern."""
        d = CD.nop_draft(CD.runs([A, B, C]), BASE)
        data = {"name": d["name"], "author": "", "Variables": [
            {"label": "OriginSource", "offset": d["addr"] - BASE, "defaultValue": d["default"], "newValue": d["new"]}]}
        fd, path = tempfile.mkstemp(suffix=".reapproj")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        try:
            rp = RP.ReapPatch.load(path)
        finally:
            os.remove(path)
        plan = PE._plan_sites(None, rp, A["addr"])
        self.assertEqual([(p["addr"], p["new_asm"], p["default_asm"]) for p in plan],
                         [(A["addr"], "90 90 90 90 90 90", "48 89 5B 1C 89 C1"),
                          (C["addr"], "90 90 90", "83 C0 05")])


class CavePlan(unittest.TestCase):
    def test_hook_covers_the_whole_first_run_but_at_least_hook_min(self):
        self.assertEqual(CD.cave_plan(CD.runs([A]))["min_len"], CD.HOOK_MIN)                 # 4 Byte -> mindestens 8
        long_run = [ln(BASE + 0x2000 + 3 * i, b"\x48\x89\xe5") for i in range(10)]             # 30 Byte
        plan = CD.cave_plan(CD.runs(long_run))
        self.assertEqual((plan["start"], plan["min_len"], plan["ignored"]), (BASE + 0x2000, 30, 0))

    def test_other_runs_are_reported_as_ignored(self):
        self.assertEqual(CD.cave_plan(CD.runs([A, C]))["ignored"], 1)

    @unittest.skipUnless(AT.HAVE_CAPSTONE, "Capstone fehlt")
    def test_build_cave_hook_with_min_len_copies_every_selected_instruction(self):
        code = b"\x48\x89\xe5" * 12                                                           # 12 x mov rbp, rsp
        r = AT.build_cave_hook(code, BASE, min_len=30)
        self.assertEqual(r["size"], 30)
        self.assertEqual(r["cave"].count("mov rbp, rsp"), 10)
        self.assertEqual(r["default"].count("48 89 E5"), 10)

    @unittest.skipUnless(AT.HAVE_CAPSTONE, "Capstone fehlt")
    def test_default_min_len_is_unchanged(self):
        r = AT.build_cave_hook(b"\x48\x89\xe5" * 12, BASE)
        self.assertEqual(r["size"], 9)                                                       # 3 Befehle >= 8 Byte


class Hints(unittest.TestCase):
    def test_nop_warns_when_runs_are_far_apart(self):
        far = ln(BASE + 0x9000, b"\x90")
        self.assertEqual([k for k, _v in CD.warnings("nop", CD.runs([A, far]))], ["far"])
        self.assertEqual(CD.warnings("nop", CD.runs([A, C])), [])

    def test_cave_warns_about_ignored_runs_and_very_long_hooks(self):
        long_run = [ln(BASE + 3 * i, b"\x48\x89\xe5") for i in range(6)]
        keys = [k for k, _v in CD.warnings("cave", CD.runs(long_run + [ln(BASE + 0x500, b"\x90")]))]
        self.assertEqual(keys, ["ignored", "long"])
        self.assertEqual([k for k, _v in CD.warnings("cave", CD.runs([A]))], ["short"])                 # 4 Byte < HOOK_MIN
        eight = [ln(BASE + 0x3000, b"\x48\x89\xe5\x48\x89\xe5\x90\x90")]                                # genau 8 Byte
        self.assertEqual(CD.warnings("cave", CD.runs(eight)), [])

    def test_default_names(self):
        rs = CD.runs([A])
        self.assertEqual((CD.default_name("nop", rs, BASE), CD.default_name("cave", rs, BASE)), ("NOP_1000", "Hook_1000"))
        self.assertEqual(CD.default_name("nop", CD.runs([ln(0x10, b"\x90")]), BASE), "NOP_10")      # unter der Base: absolut


class DisasmTabNop(unittest.TestCase):
    def tab(self, lines):
        writes = []
        fake = types.SimpleNamespace(_selected=lambda: lines, log=lambda *a: None,
                                     _write_all=lambda patches, what: writes.append((patches, what)))
        return fake, writes

    def test_contiguous_selection_is_one_write_like_before(self):
        fake, writes = self.tab([A, B])
        with mock.patch.object(G.messagebox, "askyesno", return_value=True) as ask:
            G.DisasmTab.nop(fake)
        self.assertEqual(writes, [([(A["addr"], b"\x90" * 6)], "NOP")])
        self.assertIn("6 Byte(s) ab", ask.call_args[0][1])

    def test_separate_lines_are_not_joined_so_the_code_between_stays_untouched(self):
        fake, writes = self.tab([C, A])
        with mock.patch.object(G.messagebox, "askyesno", return_value=True) as ask:
            G.DisasmTab.nop(fake)
        self.assertEqual(writes, [([(A["addr"], b"\x90" * 4), (C["addr"], b"\x90" * 3)], "NOP")])
        self.assertIn("7 Byte(s) an 2 Stellen", ask.call_args[0][1])

    def test_declining_writes_nothing_and_empty_selection_is_ignored(self):
        fake, writes = self.tab([A])
        with mock.patch.object(G.messagebox, "askyesno", return_value=False):
            G.DisasmTab.nop(fake)
        self.assertEqual(writes, [])
        fake, writes = self.tab([])
        G.DisasmTab.nop(fake)
        self.assertEqual(writes, [])


class CheatTabFill(unittest.TestCase):
    class Var:
        def __init__(self):
            self.val = ""

        def set(self, v):
            self.val = v

        def get(self):
            return self.val

    class Box:
        def __init__(self):
            self.text = ""

        def delete(self, *a):
            self.text = ""

        def insert(self, _i, t):
            self.text = t

    def fake(self):
        f = types.SimpleNamespace(v={k: self.Var() for k in ("name", "offset", "aob", "aoboff")}, v_type=self.Var(),
                                  t_def=self.Box(), t_new=self.Box(), base=BASE, types=[])
        f._type = lambda: f.types.append(f.v_type.get())
        return f

    def test_fill_takes_name_type_offset_and_texts(self):
        f = self.fake()
        G.CheatTab.fill(f, CD.nop_draft(CD.runs([A, C]), BASE))
        self.assertEqual((f.v["name"].get(), f.v_type.get(), f.v["offset"].get()), ("NOP_1000", "patch", "0x1000"))
        self.assertEqual(f.t_def.text.splitlines()[1], "+0x1010: 83 C0 05")
        self.assertEqual(f.types, ["patch"])                                  # Typ-Umschaltung wurde ausgelöst

    def test_old_callers_without_name_or_type_still_work(self):
        f = self.fake()
        G.CheatTab.fill(f, {"addr": BASE + 0x20, "default": "90", "new": "C3"})
        self.assertEqual((f.v["name"].get(), f.v_type.get(), f.types), ("", "", []))
        self.assertEqual(f.t_new.text, "C3")


if __name__ == "__main__":
    unittest.main()
