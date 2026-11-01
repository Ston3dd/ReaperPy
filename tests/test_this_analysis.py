"""Erkennung 'liest die native Funktion this (rdi)?' - ohne Capstone (fertige Befehlslisten) und ohne Konsole."""
import unittest

import ue_cavegen as CG


def ins(*lines):
    out = []
    for ln in lines:
        mn, _, ops = ln.partition(" ")
        out.append({"mnemonic": mn, "op_str": ops})
    return out


class AnalyzeThisUse(unittest.TestCase):
    def test_real_function_that_overwrites_rdi_before_use(self):
        # Anfang von SBPlayerItemBucketItemAdd (aus der PS5-eboot): rdi wird aus einer globalen Tabelle neu geladen
        code = ins("push rbp", "mov rbp,rsp", "push r15", "push r14", "push r13", "push r12", "push rbx", "sub rsp,0x18",
                   "mov r13,[rip+0x73e3168]", "mov r15d,r8d", "mov ebx,ecx", "mov r14d,edx", "mov rax,[r13+0x0]",
                   "mov r12,[rip+0x7607925]", "test r12,r12", "je 0xb51c90", "mov rax,[r12+0xc8]",
                   "mov rdi,[rax+rcx*8]", "test rdi,rdi", "je 0xb51c70", "ret")
        self.assertIs(CG.analyze_this_use(code), True)

    def test_dereference_of_rdi(self):
        self.assertIs(CG.analyze_this_use(ins("mov rax,[rdi+0x10]", "ret")), False)

    def test_copy_then_dereference(self):
        self.assertIs(CG.analyze_this_use(ins("push rbp", "mov rbp,rsp", "mov rbx,rdi", "mov rax,[rbx+8]", "ret")), False)

    def test_null_check_means_used(self):
        self.assertIs(CG.analyze_this_use(ins("test rdi,rdi", "je 0x10", "ret")), False)

    def test_passed_on_to_call(self):
        self.assertIs(CG.analyze_this_use(ins("push rbp", "mov rbp,rsp", "call 0x1234", "ret")), False)

    def test_overwritten_before_call_is_fine(self):
        self.assertIs(CG.analyze_this_use(ins("push rbp", "mov rbp,rsp", "xor edi,edi", "call 0x1234", "ret")), True)

    def test_copy_in_callee_saved_never_used(self):
        self.assertIs(CG.analyze_this_use(ins("push rbp", "mov rbp,rsp", "mov rbx,rdi", "call 0x1234", "ret")), False)  # rdi beim Aufruf noch this

    def test_copy_survives_call_but_unused(self):
        code = ins("push rbp", "mov rbp,rsp", "mov rbx,rdi", "mov edi,5", "call 0x1234", "mov eax,1", "ret")
        self.assertIs(CG.analyze_this_use(code), True)

    def test_copy_used_after_call(self):
        code = ins("mov rbx,rdi", "mov edi,5", "call 0x1234", "mov rax,[rbx+0x20]", "ret")
        self.assertIs(CG.analyze_this_use(code), False)

    def test_stored_to_memory(self):
        self.assertIs(CG.analyze_this_use(ins("mov [rsp+8],rdi", "ret")), False)

    def test_push_is_unknown(self):
        self.assertIsNone(CG.analyze_this_use(ins("push rdi", "ret")))

    def test_jump_with_this_alive_is_unknown(self):
        self.assertIsNone(CG.analyze_this_use(ins("jmp 0x100")))

    def test_ends_without_ret_with_copy_alive_is_unknown(self):
        self.assertIsNone(CG.analyze_this_use(ins("mov rbx,rdi", "mov eax,1")))

    def test_register_names_are_normalised(self):
        self.assertIs(CG.analyze_this_use(ins("mov rax,[edi+4]", "ret")), False)
        self.assertIs(CG.analyze_this_use(ins("mov edi,3", "mov rax,[rdi+4]", "ret")), True)


class ChooseThis(unittest.TestCase):
    class Sdk:
        classes = {}

        def all_members(self, _c):
            return []

    def test_unused_this_means_always_call(self):
        mode, off, note = CG.choose_this(self.Sdk(), "USBCheatManager", this_unused=True)
        self.assertEqual((mode, off), ("zero", 0))
        self.assertIn("liest this nicht", note)

    def test_unknown_keeps_old_behaviour(self):
        mode, _o, _n = CG.choose_this(self.Sdk(), "USBCheatManager", this_unused=None)
        self.assertEqual(mode, "zero")                       # ohne Pfad wie bisher (mit Warnung im Text)
        self.assertIn("Absturz", CG.choose_this(self.Sdk(), "USBCheatManager")[2])

    def test_impl_ignores_this_without_capstone_is_unknown(self):
        self.assertIsNone(CG.impl_ignores_this(lambda a, n: b"\xc3" * n, 0x1000) if not _have_capstone() else None)


def _have_capstone():
    try:
        import capstone  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    unittest.main()
