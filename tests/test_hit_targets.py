"""hit_targets.py / hit_context.py: Ziel-Adresse und Wert pro Treffer, Gruppierung nach Objekt (Spieler vs. Gegner)."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asm_tools as AT          # noqa: E402
import hit_context as HC        # noqa: E402
import hit_targets as TG        # noqa: E402


def line(addr, mnem, ops, size=4):
    return {"addr": addr, "size": size, "mnemonic": mnem, "op_str": ops}


class HitTargets(unittest.TestCase):
    def test_base_plus_disp(self):
        t = TG.target_of(line(0x1000, "mov", "dword ptr [rbx + 0x278], ecx"), {"rbx": 0x10000, "rip": 0x1004})
        assert t["ea"] == 0x10278 and t["width"] == 4 and t["base"] == 0x10000


    def test_index_scale_and_negative_disp(self):
        t = TG.target_of(line(0x1000, "movss", "dword ptr [rax + rcx*4 - 0x10], xmm0"), {"rax": 0x2000, "rcx": 3})
        assert t["ea"] == 0x2000 + 12 - 0x10 and t["width"] == 4 and t["base"] == 0x2000


    def test_rip_relative_uses_next_instruction(self):
        t = TG.target_of(line(0x1000, "mov", "dword ptr [rip + 0x100], eax", size=6), {"rip": 0x1000, "rax": 1})
        assert t["ea"] == 0x1000 + 6 + 0x100 and t["base"] is None


    def test_width_from_register_and_qword(self):
        assert TG.target_of(line(0, "mov", "[rax], cl"), {"rax": 8})["width"] == 1
        assert TG.target_of(line(0, "mov", "qword ptr [rax], rdx"), {"rax": 8})["width"] == 8
        assert TG.target_of(line(0, "movaps", "xmmword ptr [rax], xmm1"), {"rax": 8})["width"] == 8
        assert TG.target_of(line(0, "movsd", "[rax], xmm1"), {"rax": 8})["width"] == 8


    def test_32bit_register_in_address(self):
        t = TG.target_of(line(0, "mov", "dword ptr [ebx + 4], eax"), {"rbx": 0x1_0000_0010})
        assert t["ea"] == 0x14


    def test_no_memory_operand_or_not_computable(self):
        assert TG.target_of(line(0, "mov", "eax, ecx"), {"rax": 1}) is None
        assert TG.target_of(line(0, "lea", "rax, [rbx + 8]"), {"rbx": 1}) is None
        assert TG.target_of(line(0, "mov", "dword ptr fs:[0x28], eax"), {"rax": 1}) is None
        assert TG.target_of(line(0, "mov", "[rbx + 8], eax"), {}) is None           # Register fehlt
        assert TG.target_of(None, {"rax": 1}) is None
        assert TG.target_of(line(0, "jmp", "qword ptr [rax]"), {"rax": 1}) is None


    def test_memory_source_is_found_too(self):
        t = TG.target_of(line(0, "mov", "eax, dword ptr [rdi + 0x10]"), {"rdi": 0x5000})
        assert t["ea"] == 0x5010


    def test_format_and_delta(self):
        assert TG.format_value(None, 4) == "-"
        assert TG.format_value(100, 4) == "100"
        assert TG.format_value(0xFFFFFFFF, 4) == "-1"
        f = struct.unpack("<I", struct.pack("<f", 74.6))[0]
        assert "74.6" in TG.format_value(f, 4)
        assert TG.delta_text(None, 5, 4) == ""
        assert TG.delta_text(100, 90, 4) == "-10"
        assert TG.delta_text(5, 5, 4) == "0"
        a = struct.unpack("<I", struct.pack("<f", 100.0))[0]
        b = struct.unpack("<I", struct.pack("<f", 99.5))[0]
        assert TG.delta_text(a, b, 4) == "-0.5"


    def test_book_groups_labels_and_changes(self):
        book = TG.TargetBook()
        t1 = {"ea": 0x100, "width": 4, "base": 0xF00, "writer": "x", "value": 10}
        t2 = {"ea": 0x200, "width": 4, "base": 0x1F00, "writer": "x", "value": 20}
        g, new, ch = book.add(t1, 10, insn="w", when=1)
        assert new and not ch and g["label"] == "A" and g["hits"] == 1
        g, new, ch = book.add(t1, 9)
        assert not new and ch and g["prev"] == 10 and g["value"] == 9 and g["changes"] == 1 and g["hits"] == 2
        g, new, ch = book.add(t1, 9)
        assert not ch and g["prev"] == 10 and g["hits"] == 3
        g2, new, _ = book.add(t2, 20)
        assert new and g2["label"] == "B"
        assert [r["label"] for r in book.rows()] == ["A", "B"]
        book.skipped = 4
        book.reset()
        assert not book.groups and book.skipped == 0
        assert book.add(t2, 1)[0]["label"] == "A"


    def test_labels_run_past_z(self):
        assert [TG._label(n) for n in (0, 25, 26, 27, 701, 702)] == ["A", "Z", "AA", "AB", "ZZ", "AAA"]


    def test_toggle_me_is_exclusive(self):
        book = TG.TargetBook()
        book.add({"ea": 1, "width": 4}, 1)
        book.add({"ea": 2, "width": 4}, 1)
        book.toggle_me(1)
        book.toggle_me(2)
        assert [g["me"] for g in book.rows()] == [False, True]
        book.toggle_me(2)
        assert not any(g["me"] for g in book.rows())
        book.toggle_me(999)                                                         # unbekannt: nichts passiert


    def test_find_value_int_float_and_rounding(self):
        book = TG.TargetBook()
        hp = struct.unpack("<I", struct.pack("<f", 74.6))[0]
        book.add({"ea": 1, "width": 4}, hp)
        book.add({"ea": 2, "width": 4}, 75)
        book.add({"ea": 3, "width": 4}, 500)
        assert [g["ea"] for g in book.find_value("75")] == [1, 2]                   # 74.6 zaehlt als gerundete 75
        assert [g["ea"] for g in book.find_value("74.6")] == [1]
        assert [g["ea"] for g in book.find_value("0x1F4")] == [3]
        assert book.find_value("") == [] and book.find_value("abc") == []


    def test_build_context_delivers_insn_and_target(self):
        try:
            self._build_context()
        except RuntimeError as e:                              # kein Assembler (keystone) installiert
            self.skipTest(str(e))

    def _build_context(self):
        code = AT.assemble("mov dword ptr [rbx + 0x278], ecx\nnop\nnop\nnop\nnop\nnop") if hasattr(AT, "assemble") else None
        if code is None:
            return
        base = 0x401000
        mem = {base: bytes(code)}

        def read(addr, n):
            for a, d in mem.items():
                if a <= addr < a + len(d):
                    return d[addr - a:addr - a + n]               # wie die Konsole: so viel, wie da ist
            if addr == 0x10278:
                return struct.pack("<I", 77)
            raise OSError("unreadable")

        first = AT.disassemble_lines(bytes(code), base, 1)[0]
        hit = {"kind": "BP", "regs": {"rip": base, "rbx": 0x10000, "rcx": 5}}
        ctx = HC.build_context(read, hit, None)
        assert ctx["insn"]["addr"] == first["addr"]
        assert ctx["target"]["ea"] == 0x10278 and ctx["target"]["value"] == 77


    def test_target_follows_the_watchpoint_when_the_writer_changes_its_base(self):
        """Register stehen NACH dem Befehl: mov rax,[rax+8] aendert rax - dann gilt die Adresse des Watchpoints."""
        insn = line(0x1000, "mov", "rax, qword ptr [rax + 8]")
        wp = {"addr": 0x5008, "size": 8}
        t = HC._target(lambda a, n: b"\x2A" + b"\0" * 7, insn, {"rax": 0xDEAD, "rip": 0x1004}, wp)
        self.assertEqual((t["ea"], t["base"], t["width"], t["value"]), (0x5008, None, 8, 42))
        ok = HC._target(lambda a, n: b"\x01\0\0\0", line(0x1000, "mov", "dword ptr [rdi + 8], eax"),
                        {"rdi": 0x5000, "rip": 0x1004}, {"addr": 0x5008, "size": 4})
        self.assertEqual((ok["ea"], ok["base"]), (0x5008, 0x5000))


if __name__ == "__main__":
    unittest.main()
