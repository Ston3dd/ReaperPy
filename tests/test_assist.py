"""assist.py: Suchart aus der Zahl, Hinweise, effektive Adresse, schreibenden Befehl aus einem Watchpoint-Treffer bestimmen
(Befehle werden mit GNU as assembliert und mit objdump zerlegt - Capstone ist nicht noetig)."""
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import assist as A  # noqa: E402

NATIVE = platform.system() == "Linux" and platform.machine() in ("x86_64", "AMD64")
# Nur Linux: unter Windows liefert objcopy fuer .o-Dateien (COFF) keine Bytes
TOOLS = NATIVE and shutil.which("as") and shutil.which("objdump") and shutil.which("ld") and shutil.which("objcopy")


def assemble(src):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "a.s"), "w", encoding="utf-8") as f:
        f.write(".intel_syntax noprefix\n.text\n" + src + "\n")
    subprocess.run(["as", "--64", "-o", os.path.join(d, "a.o"), os.path.join(d, "a.s")], check=True, cwd=d)
    subprocess.run(["objcopy", "-O", "binary", "-j", ".text", "a.o", "a.bin"], check=True, cwd=d)
    with open(os.path.join(d, "a.bin"), "rb") as f:
        return f.read()


def disasm(data, addr):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.bin")
    with open(p, "wb") as f:
        f.write(data)
    out = subprocess.run(["objdump", "-D", "-b", "binary", "-mi386:x86-64", "-M", "intel", f"--adjust-vma={addr:#x}", p],
                         check=True, capture_output=True, text=True, encoding="utf-8").stdout
    lines = []
    for ln in out.splitlines():
        m2 = re.match(r"\s*[0-9a-f]+:\t((?:[0-9a-f]{2} ?)+)\s*$", ln)             # Fortsetzungszeile langer Befehle
        if m2 and lines:
            lines[-1]["size"] += len(m2.group(1).split())
            continue
        m = re.match(r"\s*([0-9a-f]+):\t((?:[0-9a-f]{2} )+)\s*(\S+)\s*(.*)", ln)
        if m:
            lines.append({"addr": int(m.group(1), 16), "size": len(m.group(2).split()), "mnemonic": m.group(3),
                          "op_str": m.group(4).strip()})
    return lines


class Plan(unittest.TestCase):
    def test_value_plan(self):
        self.assertEqual(A.value_plan("100"), {"vname": "Int32", "ctype": "Genau", "text": "100"})
        self.assertEqual(A.value_plan("0x10")["text"], "16")
        self.assertEqual(A.value_plan("-5")["vname"], "Int32")
        self.assertEqual(A.value_plan("3000000000")["vname"], "UInt32")
        self.assertEqual(A.value_plan("99999999999")["vname"], "Int64")
        self.assertEqual(A.value_plan("9,5"), {"vname": "Float", "ctype": "Ungefähr (Float)", "text": "9.5"})
        self.assertEqual(A.value_plan("", unknown=True)["ctype"], "Unbekannter Startwert")
        for bad in ("", "abc"):
            with self.assertRaises(ValueError):
                A.value_plan(bad)

    def test_advice_levels_and_languages(self):
        self.assertEqual([A.advice(n)[0] for n in (0, 10, 31, 6000)], ["none", "good", "some", "many"])
        self.assertIn("Treffer", A.advice(50, "de")[1])
        self.assertIn("hits", A.advice(50, "en")[1])
        self.assertEqual(A.advice(5, first=True)[0], "good")

    def test_watch_size(self):
        self.assertEqual([A.watch_size(v) for v in ("Int32", "Float", "UInt8", "Int16", "Double", "Int64")], [4, 4, 1, 2, 8, 8])


class Ea(unittest.TestCase):
    REGS = {"rbx": 0x1000, "rax": 3, "r14": 0x2000, "rcx": 0xFFFFFFFF00000005}

    def test_forms(self):
        f = A.effective_address
        self.assertEqual(f("rbx + 0x10", self.REGS, 0), 0x1010)
        self.assertEqual(f("rbx + rax*4 + 8", self.REGS, 0), 0x1014)
        self.assertEqual(f("r14 - 0x20", self.REGS, 0), 0x1FE0)
        self.assertEqual(f("rip + 0x100", self.REGS, 0x500), 0x600)
        self.assertEqual(f("rbx + ecx*2", self.REGS, 0), 0x100A)           # 32-Bit-Register wird abgeschnitten
        self.assertIsNone(f("fs:0x28", self.REGS, 0))
        self.assertIsNone(f("rbx + rdx", self.REGS, 0))                      # rdx unbekannt

    def test_mem_operand(self):
        self.assertEqual(A.mem_operand("dword ptr [rbx + 0x10], eax"), ("rbx + 0x10", True))
        self.assertEqual(A.mem_operand("eax, dword ptr [rbx + 0x10]"), ("rbx + 0x10", False))
        self.assertIsNone(A.mem_operand("eax, 5"))


@unittest.skipUnless(TOOLS, "braucht Linux x86-64 mit GNU as/objdump/objcopy")
class Writer(unittest.TestCase):
    RIP = 0x7000100

    def hit(self, src, regs, watch, size=4):
        code = assemble(src)
        before = b"\x90" * max(0, 16 - len(code)) + code
        return A.find_writer(self.RIP, before[-16:], dict(regs, rip=self.RIP), watch, size, disasm)

    def test_finds_decrement_of_health(self):
        w = self.hit("mov eax, 5\nsub dword ptr [rbx+0x10], eax", {"rbx": 0x5000}, 0x5010)
        self.assertEqual((w["mnemonic"], w["how"]), ("sub", "address"))
        self.assertTrue(w["op_str"].startswith("DWORD PTR [rbx+0x10]") or "rbx" in w["op_str"])
        self.assertEqual(w["addr"] + w["size"], self.RIP)

    def test_long_instruction_with_prefixes_and_index(self):
        w = self.hit("mov dword ptr [r14+rax*4+0x1234], 0x7f", {"r14": 0x9000, "rax": 2}, 0x9000 + 8 + 0x1234)
        self.assertEqual((w["mnemonic"], w["how"]), ("mov", "address"))

    def test_picks_the_write_when_another_decode_also_fits(self):
        # 'add [rax],al' (00 00) kann auch aus den Bytes eines davor stehenden Befehls entstehen -> die Adresse entscheidet
        w = self.hit("mov ecx, 1\nmov dword ptr [rdi+8], ecx", {"rdi": 0x4000, "rcx": 1}, 0x4008)
        self.assertEqual(w["how"], "address")
        self.assertIn("rdi", w["op_str"])

    def test_falls_back_to_write_heuristic_when_registers_do_not_match(self):
        w = self.hit("mov dword ptr [rbx+0x10], eax", {"rbx": 0x1}, 0x5010)        # Adresse passt nicht
        self.assertEqual(w["how"], "writes")

    def test_none_when_nothing_decodes(self):
        self.assertIsNone(A.find_writer(0x100, b"", {}, 0, 4, disasm))


class Collect(unittest.TestCase):
    def test_writers_count_and_explain(self):
        W = A.Writers()
        w1 = {"addr": 0x10, "size": 3, "mnemonic": "sub", "op_str": "dword ptr [rbx + 0x10], 1", "how": "address"}
        w2 = {"addr": 0x20, "size": 3, "mnemonic": "mov", "op_str": "dword ptr [rbx + 0x10], eax", "how": "address"}
        for w in (w1, w1, w2):
            W.add(w)
        W.add(None)
        rows = W.rows("de")
        self.assertEqual([(r["addr"], r["count"]) for r in rows], [(0x10, 2), (0x20, 1)])
        self.assertEqual(W.unknown, 1)
        self.assertTrue(rows[0]["text"])
        self.assertTrue(W.rows("en")[0]["text"])


if __name__ == "__main__":
    unittest.main()
