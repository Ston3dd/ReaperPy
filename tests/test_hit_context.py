"""hit_context.py: Befehle rund um einen Debugger-Treffer, Schreiber und RIP markiert (Capstone noetig)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asm_tools as AT  # noqa: E402
import hit_context as HC  # noqa: E402

BASE = 0x1000
PAD = 0x90                                    # 64 Byte NOP davor: so weit wie hit_context zurueck liest
CODE = bytes.fromhex(
    "55"                # push rbp
    "4889E5"            # mov rbp, rsp
    "8B4708"            # mov eax, [rdi+8]
    "83C005"            # add eax, 5
    "89471C"            # mov [rdi+0x1c], eax      <- schreibt 0x701c
    "B901000000"        # mov ecx, 1               <- hier steht RIP nach dem Schreiben
    "31D2"              # xor edx, edx
    "5D"                # pop rbp
    "C3")               # ret
WRITER = BASE + 1 + 3 + 3 + 3
RIP_AFTER = WRITER + 3
REGS = {r: 0 for r in ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp", "r8", "r9", "r10", "r11", "r12",
                       "r13", "r14", "r15")}
REGS["rdi"] = 0x7000
MEM_START = BASE - HC.BEFORE_BYTES
MEM = bytes([PAD]) * HC.BEFORE_BYTES + CODE + bytes([0xCC]) * 64


def read(addr, n):
    off = addr - MEM_START
    if off < 0 or off + n > len(MEM):
        raise OSError(f"nicht lesbar {addr:#x}")
    return MEM[off:off + n]


def hit(kind, rip, index=None):
    return {"kind": kind, "index": index, "addr": rip, "lwpid": 1, "regs": dict(REGS, rip=rip)}


@unittest.skipUnless(AT.HAVE_CAPSTONE, "Capstone fehlt")
class Context(unittest.TestCase):
    def test_write_watchpoint_marks_writer_before_rip(self):
        wp = {"addr": 0x701C, "size": 4, "access": "write"}
        ctx = HC.build_context(read, hit("WP", RIP_AFTER, 0), wp)
        self.assertEqual(ctx["marks"], {RIP_AFTER: "rip", WRITER: "writer"})
        self.assertEqual(ctx["focus"], WRITER)
        self.assertEqual(ctx["writer"]["op_str"], "dword ptr [rdi + 0x1c], eax")
        self.assertEqual(ctx["how"], "address")
        self.assertIn("Schreibzugriff", ctx["headline"])
        self.assertIn("dahinter", ctx["headline"])

    def test_lines_are_contiguous_and_end_exactly_at_rip(self):
        ctx = HC.build_context(read, hit("WP", RIP_AFTER, 0), {"addr": 0x701C, "size": 4, "access": "write"})
        lines = ctx["lines"]
        for a, b in zip(lines, lines[1:]):
            self.assertEqual(a["addr"] + a["size"], b["addr"])
        idx = [ln["addr"] for ln in lines].index(RIP_AFTER)
        self.assertGreaterEqual(idx, 4)                         # ein paar Befehle davor
        self.assertGreaterEqual(len(lines) - idx, 5)            # und danach
        self.assertNotIn("db", {ln["mnemonic"] for ln in lines})

    def test_every_start_offset_gives_an_aligned_chain(self):
        """RIP auf jedem Befehl des Programms: die Befehle davor enden immer genau dort."""
        for rip in (BASE + 1, BASE + 4, BASE + 7, WRITER, RIP_AFTER, RIP_AFTER + 5):
            ctx = HC.build_context(read, hit("BP", rip))
            lines = ctx["lines"]
            pos = [i for i, ln in enumerate(lines) if ln["addr"] == rip]
            self.assertEqual(len(pos), 1, hex(rip))
            if pos[0]:
                prev = lines[pos[0] - 1]
                self.assertEqual(prev["addr"] + prev["size"], rip, hex(rip))

    def test_breakpoint_marks_only_rip(self):
        ctx = HC.build_context(read, hit("BP", WRITER))
        self.assertEqual(ctx["marks"], {WRITER: "rip"})
        self.assertIsNone(ctx["writer"])
        self.assertEqual(ctx["focus"], WRITER)
        self.assertIn("noch nicht ausgeführt", ctx["headline"])

    def test_exec_watchpoint_is_not_a_data_trap(self):
        ctx = HC.build_context(read, hit("WP", WRITER, 1), {"addr": WRITER, "size": 1, "access": "exec"})
        self.assertEqual(ctx["marks"], {WRITER: "rip"})
        self.assertIn("Ausführung", ctx["headline"])

    def test_step_headline(self):
        self.assertIn("Einzelschritt", HC.build_context(read, hit("STEP", RIP_AFTER))["headline"])

    def test_unreadable_before_still_shows_rip_and_after(self):
        def read_no_back(addr, n):
            if addr < BASE:
                raise OSError("nicht lesbar")
            return read(addr, n)
        ctx = HC.build_context(read_no_back, hit("WP", BASE, 0), {"addr": 0x701C, "size": 4, "access": "write"})
        self.assertEqual(ctx["lines"][0]["addr"], BASE)
        self.assertIsNone(ctx["writer"])
        self.assertEqual(ctx["marks"], {BASE: "rip"})

    def test_unreadable_rip_raises(self):
        with self.assertRaises(RuntimeError):
            HC.build_context(lambda a, n: (_ for _ in ()).throw(OSError("weg")), hit("BP", BASE))

    def test_unknown_writer_falls_back_to_the_instruction_before_rip(self):
        # Watch-Adresse passt zu keinem Befehl davor -> "guess": der letzte Befehl vor RIP
        ctx = HC.build_context(read, hit("WP", RIP_AFTER, 0), {"addr": 0x9999, "size": 4, "access": "write"})
        self.assertIsNotNone(ctx["writer"])
        self.assertIn(ctx["how"], ("writes", "guess"))


if __name__ == "__main__":
    unittest.main()
