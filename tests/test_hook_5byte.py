"""Cave-Hook ab 5 Byte (jmp rel32), vollstaendige Hook-Uebersicht, Einsteiger-Hilfe im Debugger."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import cave_world as W  # noqa: E402


class Overview(unittest.TestCase):
    def test_five_byte_instruction_is_enough(self):
        import asm_tools as AT
        with W.patch_disasm():
            info = AT.build_cave_hook(bytes.fromhex("b801000000c39090"), 0x1000)
            self.assertEqual(info["size"], 5)
            text = AT.hook_overview(info, 0x1000)
            self.assertIn("mindestens 5 Byte", text)
            self.assertIn("OriginReturn = 5", text)
            self.assertNotIn("NOP", text.split("Dort steht danach")[1].splitlines()[0])

    def test_overview_shows_everything(self):
        import asm_tools as AT
        with W.patch_disasm():
            info = AT.build_cave_hook(bytes.fromhex("554889e589f083c0015dc3"), 0x401000)
            self.assertEqual(info["size"], 6)
            t = AT.hook_overview(info, 0x401000)
            for part in ("push rbp", "mov rbp, rsp", "mov eax, esi", "0x401006", "E9", "90", "1x 90", "OriginReturn = 6"):
                self.assertIn(part, t)
            import tools_i18n
            try:
                tools_i18n.LANG = "en"
                self.assertIn("HOW THE HOOK WORKS", AT.hook_overview(info, 0x401000))
            finally:
                tools_i18n.LANG = "de"


class FiveByteEngine(unittest.TestCase):
    def test_hook_is_exactly_five_bytes_and_restores(self):
        import cave_check as CC
        import patch_engine as PE
        b = W.GasBackend()
        fn = b.base + 0x2000
        b.put(fn, W.assemble_at("mov eax, 1\nret\nnop\nnop\nnop\n", fn))
        before = b.read(fn, 16)
        doc = {"name": "t", "author": "", "Variables": [
            {"label": "OriginSource", "offset": 0x2000, "defaultValue": "B8 01 00 00 00", "newValue": "jmp OriginTarget"},
            {"label": "OriginReturn", "offset": 5},
            {"label": "OriginTarget", "defaultValue": "mov eax, 7\njmp OriginReturn"}]}
        self.assertEqual(CC.doc_problems(doc, b, fn), [])
        rp = CC.load_doc(doc)
        st = PE.apply_patch(b, rp, fn)
        now = b.read(fn, 16)
        self.assertEqual(now[0], 0xE9)
        self.assertEqual(now[5:], before[5:])                     # nur 5 Byte angefasst
        ok, val = W.run_isolated(lambda: b.call(fn))
        self.assertTrue(ok, val)
        self.assertEqual(val & 0xFFFFFFFF, 7)
        PE.deactivate_patch(b, rp, st)
        self.assertEqual(b.read(fn, 16), before)

    def test_return_below_five_is_a_problem(self):
        import cave_check as CC
        b = W.GasBackend()
        fn = b.base + 0x2000
        b.put(fn, W.assemble_at("mov eax, 1\nret\n", fn))
        doc = {"name": "t", "author": "", "Variables": [
            {"label": "OriginSource", "offset": 0x2000, "defaultValue": "B8 01 00 00 00", "newValue": "jmp OriginTarget"},
            {"label": "OriginReturn", "offset": 4},
            {"label": "OriginTarget", "defaultValue": "jmp OriginReturn"}]}
        self.assertTrue(any("OriginReturn" in p for p in CC.doc_problems(doc, b, fn)))


class Guide(unittest.TestCase):
    def test_steps_follow_the_state(self):
        import debug_guide as G
        self.assertIn("SCHRITT 1", G.next_step(False))
        self.assertIn("SCHRITT 2", G.next_step(True, 0, 0))
        self.assertIn("SCHRITT 3", G.next_step(True, 0, 1))
        self.assertIn("SCHRITT 4", G.next_step(True, 0, 1, 2))
        self.assertIn("DAS BIN ICH", G.next_step(True, 0, 1, 2, 3))
        self.assertNotIn("DAS BIN ICH", G.next_step(True, 0, 1, 2, 1))

    def test_explain_hit(self):
        import debug_guide as G
        ctx = {"writer": {"addr": 0x1000, "mnemonic": "sub", "op_str": "dword ptr [rbx + 0x40], eax"}}
        de = G.explain_hit(ctx, "de")
        self.assertIn("NOP", de)
        self.assertIn("CHEAT BAUEN", de)
        import tools_i18n
        try:
            tools_i18n.LANG = "en"
            self.assertIn("Cheat idea", G.explain_hit(ctx, "en"))
        finally:
            tools_i18n.LANG = "de"
        self.assertEqual(G.explain_hit({}, "de"), "")


if __name__ == "__main__":
    unittest.main()
