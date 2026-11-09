"""RIP-Operanden hinter einem Vorwaerts-Label (Sprung auf eine spaetere Marke) werden richtig ausgerechnet.
Assembler: GNU as, Zurueck-Lesen: objdump (nur wenn vorhanden)."""
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asm_tools  # noqa: E402
import patch_engine as pe  # noqa: E402

CAVE, HOOK = 0x30000000, 0x20001000


class Backend:
    """assemble() ueber GNU as (Intel-Syntax) - Marken und Sprungweiten wie im echten Assembler."""

    def assemble(self, text, addr=0):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "a.s"), "w", encoding="utf-8") as f:
            f.write(".intel_syntax noprefix\n.text\n" + text)
        subprocess.run(["as", "--64", "-o", os.path.join(d, "a.o"), os.path.join(d, "a.s")], check=True, capture_output=True)
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text", os.path.join(d, "a.o"), os.path.join(d, "a.bin")],
                       check=True, capture_output=True)
        with open(os.path.join(d, "a.bin"), "rb") as f:
            return f.read()


def objdump_disassemble(data, addr, detail=False):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.bin")
    with open(p, "wb") as f:
        f.write(data)
    out = subprocess.run(["objdump", "-D", "-b", "binary", "-mi386:x86-64", "-M", "intel", f"--adjust-vma={addr:#x}", p],
                         check=True, capture_output=True, text=True, encoding="utf-8").stdout
    ins = []
    for ln in out.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\t((?:[0-9a-f]{2} )+)\s*(.*)", ln)
        if m:
            raw = bytes.fromhex(m.group(2).replace(" ", ""))
            if ins and not m.group(3).strip():                      # Fortsetzungszeile langer Befehle
                ins[-1]["size"] += len(raw)
                continue
            ins.append({"addr": int(m.group(1), 16), "size": len(raw), "bytes": raw, "mnemonic": "", "op_str": ""})
    return ins, len(data)


@unittest.skipUnless(platform.system() == "Linux" and platform.machine() in ("x86_64", "AMD64")
                     and shutil.which("as") and shutil.which("objcopy") and shutil.which("objdump"), "keine Toolchain")
class T(unittest.TestCase):
    def test_token_after_a_forward_jump_is_resolved(self):
        lines = ["lea rsp, [rsp - 0x80]", "pushfq", "je Later", "mov eax, [rip + @hook+0x100]", "nop", "Later:",
                 "mov ecx, [rip + @hook-0x20]", "ret"]
        with mock.patch.object(asm_tools, "disassemble", objdump_disassemble):
            out = pe._resolve_rip_tokens(Backend(), lines, CAVE, HOOK)
        code = Backend().assemble("\n".join(out) + "\n", CAVE)
        # 'mov eax,[rip+d]' = 8B 05 d32 ; 'mov ecx,[rip+d]' = 8B 0D d32 (Position per Suche)
        i = code.index(b"\x8b\x05")
        d1 = struct.unpack_from("<i", code, i + 2)[0]
        self.assertEqual(CAVE + i + 6 + d1, HOOK + 0x100)
        j = code.index(b"\x8b\x0d")
        d2 = struct.unpack_from("<i", code, j + 2)[0]
        self.assertEqual(CAVE + j + 6 + d2, HOOK - 0x20)

    def test_without_forward_label_the_old_way_still_works(self):
        lines = ["pushfq", "mov eax, [rip + @hook+0x44]", "ret"]
        out = pe._resolve_rip_tokens(Backend(), lines, CAVE, HOOK)
        code = Backend().assemble("\n".join(out) + "\n", CAVE)
        i = code.index(b"\x8b\x05")
        self.assertEqual(CAVE + i + 6 + struct.unpack_from("<i", code, i + 2)[0], HOOK + 0x44)


if __name__ == "__main__":
    unittest.main()
