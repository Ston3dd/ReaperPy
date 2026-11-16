"""disasm_view.py: Zeilenarten, Tags und Adressbreite der gemeinsamen Befehls-Tabellen (Kontext-Ansicht und Disassembler-Tab)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk  # noqa: E402

ghost_tk.install()
import disasm_view as DV  # noqa: E402


def ln(addr, mnemonic, op="", size=1):
    return {"addr": addr, "mnemonic": mnemonic, "op_str": op, "bytes": b"\x90" * size, "size": size}


class Rows(unittest.TestCase):
    def test_kind_of_separates_flow_quiet_and_plain(self):
        for m in ("call", "jmp", "je", "jne", "ret", "leave"):
            self.assertEqual(DV._kind_of(ln(0, m)), "flow", m)
        for m in ("nop", "int3", "db"):
            self.assertEqual(DV._kind_of(ln(0, m)), "quiet", m)
        for m in ("mov", "add", "xor", "push", "jrcxz_not_a_flow_name_is_long"):
            self.assertEqual(DV._kind_of(ln(0, m)), "plain", m)

    def test_prefixed_instructions_use_the_real_mnemonic(self):
        self.assertEqual(DV._kind_of(ln(0, "lock add")), "plain")
        self.assertEqual(DV._kind_of(ln(0, "bnd jmp")), "flow")

    def test_marks_win_over_zebra(self):
        self.assertEqual(DV.row_tag(ln(0, "mov"), 0, "writer"), "writer")
        self.assertEqual(DV.row_tag(ln(0, "mov"), 1, "rip"), "rip")
        self.assertEqual(DV.row_tag(ln(0, "mov"), 0), "plain_a")
        self.assertEqual(DV.row_tag(ln(0, "mov"), 1), "plain_b")
        self.assertEqual(DV.row_tag(ln(0, "call"), 3, "unbekannt"), "flow_b")             # unbekannte Marke wird ignoriert

    def test_addr_width_is_as_wide_as_needed_but_at_least_eight(self):
        self.assertEqual(DV.addr_width([]), 8)
        self.assertEqual(DV.addr_width([ln(0x1000, "nop")]), 8)
        self.assertEqual(DV.addr_width([ln(0x1000, "nop"), ln(0x20_0000_0000, "nop")]), 10)      # Heap: 0x2000000000
        self.assertEqual(DV.addr_width([ln(0x200_0000_0000, "nop")]), 11)
        self.assertEqual(DV.addr_width([ln(0x7FFF_FFFF_0000, "nop")]), 12)


if __name__ == "__main__":
    unittest.main()
