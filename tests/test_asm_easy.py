"""Assembler fuer Einsteiger: Erklaerungen, verstaendliche Fehler, Groessen-Vorschau, Presets."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asm_explain as AX  # noqa: E402
import asm_help as AH  # noqa: E402
import asm_recipes as AR  # noqa: E402
import asm_tools as AT  # noqa: E402


def fake_lines(*insns):
    """[(mnemonic, op_str, size)] -> disassemble_lines-Ersatz."""
    def f(data, addr, max_insn=None):
        out, a = [], addr
        for m, o, sz in insns:
            out.append({"addr": a, "size": sz, "bytes": bytes(sz), "mnemonic": m, "op_str": o, "insn": None})
            a += sz
        return out[:max_insn] if max_insn else out
    return f


class Explain(unittest.TestCase):
    def test_common_instructions_in_both_languages(self):
        t = AX.explain("sub", "dword ptr [rbx + 0x10], 1", "de")
        self.assertIn("Zieht 1 von", t)
        self.assertIn("Leben", t)
        self.assertIn("[rbx+0x10]", t)
        self.assertIn("4-Byte", t)
        e = AX.explain("sub", "dword ptr [rbx + 0x10], 1", "en")
        self.assertIn("Subtracts 1 from", e)
        self.assertIn("4-byte", e)
        self.assertEqual(AX.explain("xor", "eax, eax", "de"), "Setzt eax auf 0 (schnellster Weg dafuer).")
        self.assertIn("nicht gleich" if False else "verschieden", AX.explain("jne", "0x1234", "de"))
        self.assertIn("Kommazahl", AX.explain("subss", "xmm0, xmm1", "de"))

    def test_prefix_and_unknown(self):
        self.assertTrue(AX.explain("lock xadd", "dword ptr [rdx], eax", "de").startswith("Atomar"))
        self.assertTrue(AX.explain("lock", "xadd dword ptr [rdx], eax", "de").startswith("Atomar"))
        self.assertEqual(AX.explain("vfmadd231ps", "xmm0, xmm1, xmm2", "de"), "")

    def test_operand_split_ignores_commas_in_brackets(self):
        self.assertEqual(AX.split_ops("dword ptr [rax + rcx*4], 5"), ["dword ptr [rax + rcx*4]", "5"])
        self.assertEqual(AX.kind("[rbx]"), "mem")
        self.assertEqual(AX.kind("r12d"), "reg")
        self.assertEqual(AX.kind("-0x10"), "imm")

    def test_every_template_formats_without_error(self):
        for m in AX._T:
            for ops in ("", "eax", "eax, ebx", "dword ptr [rbx + 4], 1", "xmm0, dword ptr [rip + 0x10]"):
                for lang in ("de", "en"):
                    AX.explain(m, ops, lang)


class Help(unittest.TestCase):
    def test_friendly_errors(self):
        t = AH.friendly_error("Invalid mnemonic (KS_ERR_ASM_MNEMONICFAIL)", "movv eax, 1", "de")
        self.assertIn("kenne ich nicht", t)
        self.assertIn("movv eax, 1", t)
        self.assertIn("KS_ERR_ASM_MNEMONICFAIL", t)
        self.assertIn("Register und Groesse", AH.friendly_error("Invalid operand (KS_ERR_ASM_INVALIDOPERAND)", "", "de"))
        self.assertIn("pip install keystone-engine", AH.friendly_error("Kein Assembler verfügbar", "", "de"))
        self.assertIn("I do not know", AH.friendly_error("Invalid mnemonic", "x", "en"))
        self.assertIn("could not turn", AH.friendly_error("irgendwas", "nop\nnop", "en"))

    def test_fit_preview(self):
        asm = lambda text, addr=0: bytes(3 * len(text.splitlines()))
        self.assertEqual(AH.fit_preview("", 8, asm), ("empty", ""))
        self.assertEqual(AH.fit_preview("; nur Kommentar", 8, asm)[0], "empty")
        self.assertEqual(AH.fit_preview("nop\nnop", 8, asm)[0], "pad")
        self.assertEqual(AH.fit_preview("nop\nnop\nnop", 8, asm)[0], "big")
        self.assertIn("1 zu viel", AH.fit_preview("a\nb\nc", 8, asm)[1])
        self.assertEqual(AH.fit_preview("a\nb", 6, asm)[0], "ok")

        def boom(text, addr=0):
            raise RuntimeError("Invalid mnemonic")
        kind, msg = AH.fit_preview("xyz", 8, boom)
        self.assertEqual(kind, "err")
        self.assertIn("kenne ich nicht", msg)


class Recipes(unittest.TestCase):
    def plan(self, rid, insns, value=""):
        with mock.patch.object(AT, "disassemble_lines", fake_lines(*insns)):
            return AR.make_plan(rid, bytes(32), 0x1000, value)

    SUB = [("sub", "dword ptr [rbx + 0x10], 1", 4), ("mov", "eax, 7", 5)]

    def test_disable_is_a_nop_patch(self):
        p = self.plan("disable", self.SUB)
        self.assertEqual((p["kind"], p["size"], p["new"].split()), ("patch", 4, ["nop"] * 4))

    def test_set_value_writes_after_the_original_instruction(self):
        p = self.plan("set_value", self.SUB, "999")
        self.assertEqual(p["kind"], "cave")
        self.assertEqual(p["cheat"], ["sub dword ptr [rbx + 0x10], 1", "mov dword ptr [rbx + 0x10], 0x3e7", "mov eax, 7"])
        self.assertEqual(p["body"], ["sub dword ptr [rbx + 0x10], 1", "mov eax, 7"])
        text = AR.cave_text(p)
        self.assertTrue(text.rstrip().endswith("jmp OriginReturn"))
        self.assertIn("0x3e7", text)

    def test_set_value_for_floats_and_registers_and_rip(self):
        p = self.plan("set_value", [("movss", "dword ptr [rbx + 0x10], xmm0", 5), ("nop", "", 4)], "100.5")
        self.assertEqual(p["cheat"][1], "mov dword ptr [rbx + 0x10], 0x42c90000")
        p = self.plan("set_value", [("mov", "eax, dword ptr [rbx + 0x10]", 3), ("nop", "", 5)], "5")
        self.assertEqual(p["cheat"][1], "mov eax, 5")
        p = self.plan("set_value", [("sub", "dword ptr [rip + @hook+0x44], 1", 7), ("nop", "", 4)], "9")
        self.assertEqual(p["cheat"][1], "mov dword ptr [rip + @hook+0x44], 0x9")

    def test_set_value_refuses_what_it_cannot_do(self):
        for insns, val, word in (([("movsd", "qword ptr [rbx], xmm0", 5), ("nop", "", 4)], "1", "movsd"),
                                 ([("movss", "xmm0, xmm1", 4), ("nop", "", 5)], "1", "Kommazahl"),
                                 ([("sub", "dword ptr [rbx], 1", 3), ("nop", "", 5)], "abc", "Keine Zahl"),
                                 ([("sub", "dword ptr [rbx], 1", 3), ("nop", "", 5)], "1.5", "ganze Zahl"),
                                 ([("sub", "[rbx], 1", 3), ("nop", "", 5)], "1", "Groesse")):
            with self.assertRaises(ValueError) as cm:
                self.plan("set_value", insns, val)
            self.assertIn(word, str(cm.exception))

    def test_return_now(self):
        p = self.plan("return_now", [("push", "rbp", 1), ("mov", "rbp, rsp", 3), ("nop", "", 8)])
        self.assertEqual((p["kind"], p["new"]), ("patch", "ret"))
        self.assertTrue(p["warnings"])

    def test_catalog(self):
        self.assertEqual(set(AR.IDS), {"disable", "set_value", "return_now"})
        for rid in AR.IDS:
            self.assertTrue(AR.title(rid, "de") and AR.title(rid, "en") and AR.describe(rid, "de") and AR.describe(rid, "en"))
        self.assertTrue(AR.needs_value("set_value"))
        self.assertFalse(AR.needs_value("disable"))

    def test_parse_value(self):
        self.assertEqual(AR.parse_value("0x10"), 16)
        self.assertEqual(AR.parse_value("-5"), -5)
        self.assertEqual(AR.parse_value("9,5", True), 9.5)
        with self.assertRaises(ValueError):
            AR.parse_value("")


if __name__ == "__main__":
    unittest.main()
