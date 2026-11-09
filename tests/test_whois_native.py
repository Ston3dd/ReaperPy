"""Fuehrt den Logger-Stub und die 'nur Spieler / nur Gegner'-Pruefung NATIV aus (gcc/as/ld noetig, sonst uebersprungen):
Eine Funktion zieht 1 Leben ab; Spieler und Gegner rufen sie gleich auf, nur Objekt-Feld, Aufrufer oder Adresse
unterscheiden sich."""
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import whois as W  # noqa: E402

BASE = 0x20000000
FN, CALLERS, OBJ, DATA = BASE + 0x1000, BASE + 0x3000, BASE + 0x4000, BASE + 0x8000
STUB = BASE + 0x2000
P, E1, E2 = OBJ, OBJ + 0x100, OBJ + 0x200                 # Spieler, Gegner 1, Gegner 2 (Team-Feld +0x38)
RING = 32
FN_ASM = """
.intel_syntax noprefix
.text
  mov qword ptr [rsp-8], 0x1234abcd
  mov r11, rdi
  sub dword ptr [r11+0x10], 1
  mov eax, 7
  mov rax, qword ptr [rsp-8]
  ret
"""
CALLERS_ASM = f"""
.intel_syntax noprefix
.text
callerA:
  movabs rax, {FN:#x}
  call rax
  ret
.org 0x100
callerB:
  movabs rax, {FN:#x}
  call rax
  ret
"""
RET_A, RET_B = CALLERS + 12, CALLERS + 0x100 + 12
C_SRC = rf"""
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
typedef long (*F)(long);
static void load(const char *p, void *dst){{FILE*f=fopen(p,"rb");if(!f)exit(2);char b[8192];size_t n=fread(b,1,8192,f);memcpy(dst,b,n);fclose(f);}}
int main(void){{
  char *m = mmap((void*)0x20000000, 0x20000, PROT_READ|PROT_WRITE|PROT_EXEC, MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE, -1, 0);
  if(m != (char*)0x20000000) return 3;
  load("fn.bin", m+0x1000); load("callers.bin", m+0x3000); load("stub.bin", m+0x2000); load("hook.bin", m+HOOKOFF);
  long objs[3] = {{0x{P:x}, 0x{E1:x}, 0x{E2:x}}};
  for(int i=0;i<3;i++){{ *(int*)(objs[i]+0x10)=1000; *(int*)(objs[i]+0x38)=(i==0)?1:(i+1); }}
  F a = (F)(m+0x3000), b = (F)(m+0x3100);
  long rz = 0;
  for(int k=0;k<10;k++){{ rz = a(objs[0]); b(objs[1]); b(objs[2]); }}
  printf("%d %d %d %lx\n", *(int*)(objs[0]+0x10), *(int*)(objs[1]+0x10), *(int*)(objs[2]+0x10), rz);
  FILE*o=fopen("ring.bin","wb"); fwrite(m+0x8000, 1, 0x40+{RING}*512, o); fclose(o);
  return 0; }}
"""


@unittest.skipUnless(platform.system() == "Linux" and platform.machine() in ("x86_64", "AMD64")
                     and shutil.which("gcc") and shutil.which("as") and shutil.which("ld") and shutil.which("objcopy"),
                     "keine Toolchain")
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.sh("as", "--64", "-o", "fn.o", cls.w("fn.s", FN_ASM))
        cls.sh("objcopy", "-O", "binary", "-j", ".text", "fn.o", "fn.bin")
        cls.fn = Path(cls.d, "fn.bin").read_bytes()
        cls.hookoff = 0x1000 + cls.fn.index(b"\x41\x83\x6b\x10\x01")
        cls.hook_addr = BASE + cls.hookoff
        cls.stolen = cls.fn[cls.hookoff - 0x1000:cls.hookoff - 0x1000 + 10]
        cls.w("callers.s", CALLERS_ASM)
        cls.sh("as", "--64", "-o", "callers.o", "callers.s")
        cls.sh("objcopy", "-O", "binary", "-j", ".text", "callers.o", "callers.bin")
        cls.w("h.c", C_SRC.replace("HOOKOFF", hex(cls.hookoff)))
        cls.sh("gcc", "-O0", "-o", "h", "h.c")

    @classmethod
    def w(cls, name, text):
        Path(cls.d, name).write_text(text, encoding="utf-8")
        return name

    @classmethod
    def sh(cls, *cmd):
        subprocess.run(cmd, check=True, capture_output=True, cwd=cls.d)

    def run_cave(self, lines):
        """Cave-Zeilen als Stub an den Hook haengen, laufen lassen -> (hp P, hp E1, hp E2, Red-Zone-Wert)."""
        src = []
        for ln in lines:
            ln = ln.strip()
            if not ln or ln.startswith(";"):
                continue
            ln = re.sub(r"\bOriginReturn\b", f"{self.hook_addr + 10:#x}", ln)
            m = re.match(r"lea (\w+), \[rip \+ @hook([+-])(0x[0-9a-f]+)\]", ln)
            if m:
                tgt = self.hook_addr + (1 if m.group(2) == "+" else -1) * int(m.group(3), 16)
                ln = f"movabs {m.group(1)}, {tgt:#x}"
            src.append(ln)
        self.w("stub.s", "\n".join([".intel_syntax noprefix", ".text"] + src) + "\n")
        self.sh("as", "--64", "-o", "stub.o", "stub.s")
        self.sh("ld", f"-Ttext={STUB:#x}", "--oformat", "binary", "-o", "stub.bin", "stub.o")
        rel = STUB - (self.hook_addr + 5)
        Path(self.d, "hook.bin").write_bytes(b"\xE9" + struct.pack("<i", rel) + b"\x90" * 5)
        res = subprocess.run(["./h"], cwd=self.d, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, res.stderr)
        a, b, c, rz = res.stdout.split()
        return int(a), int(b), int(c), int(rz, 16)

    BODY = ["sub dword ptr [r11 + 0x10], 1", "mov eax, 7"]
    SKIP = ["mov eax, 7"]                                         # Preset 'Befehl abschalten'

    def test_logger_stub_records_registers_and_caller_chain(self):
        lines = W.stub_asm(DATA, RING) + self.BODY + ["jmp OriginReturn"]
        hp = self.run_cave(lines)
        self.assertEqual(hp, (990, 990, 990, 0x1234abcd))        # Red Zone heil, Funktion lief normal
        ring = Path(self.d, "ring.bin").read_bytes()
        recs, idx, lost = W.collect(lambda a, n: ring[a - DATA:a - DATA + n], DATA, RING, 0)
        self.assertEqual((idx, lost, len(recs)), (30, 0, 30))
        first = recs[0]
        self.assertEqual(first["regs"]["r11"], P)
        self.assertEqual(first["stack"][0], RET_A)               # Rueckkehr in callerA = Spieler-Pfad
        self.assertEqual(recs[1]["stack"][0], RET_B)
        self.assertEqual((recs[1]["regs"]["r11"], recs[2]["regs"]["r11"]), (E1, E2))

    def check(self, c, apply_to, expect):
        text = W.guard_cave(c, self.hook_addr, self.SKIP, self.BODY, apply_to=apply_to)
        self.assertEqual(self.run_cave(text.splitlines()), expect, (c["kind"], apply_to))

    def test_field_guard_player_only_and_enemy_only(self):
        c = {"kind": "field", "reg": "r11", "off": 0x38, "player": [1], "enemy": [2, 3]}
        self.check(c, "player", (1000, 990, 990, 0x1234abcd))      # Spieler unsterblich, Gegner nicht
        self.check(c, "enemy", (990, 1000, 1000, 0x1234abcd))

    def test_caller_guard_uses_the_stack(self):
        c = {"kind": "caller", "slot": 0, "player": [RET_A], "enemy": [RET_B]}
        self.check(c, "player", (1000, 990, 990, 0x1234abcd))
        self.check(c, "enemy", (990, 1000, 1000, 0x1234abcd))

    def test_object_guard(self):
        c = {"kind": "object", "reg": "r11", "player": [P], "enemy": [E1, E2]}
        self.check(c, "player", (1000, 990, 990, 0x1234abcd))
        self.check({**c, "player": [E1, E2]}, "player", (990, 1000, 1000, 0x1234abcd))

    def test_analysis_finds_all_three_on_the_real_records(self):
        self.run_cave(W.stub_asm(DATA, RING) + self.BODY + ["jmp OriginReturn"])
        ring = Path(self.d, "ring.bin").read_bytes()
        recs, _i, _l = W.collect(lambda a, n: ring[a - DATA:a - DATA + n], DATA, RING, 0)
        a = [r for r in recs if r["regs"]["r11"] == P]
        b = [r for r in recs if r["regs"]["r11"] != P]
        mem = {}
        for o, team in ((P, 1), (E1, 2), (E2, 3)):
            blob = bytearray(0x200)
            struct.pack_into("<II", blob, 0x38, team, 0)
            mem[o] = bytes(blob)
        read = lambda addr, n: mem[addr][:n] if addr in mem else b""
        found = W.analyze(a, b, read=read, is_code=lambda v: BASE <= v < BASE + 0x10000)
        kinds = {(c["kind"], c.get("slot", c.get("off"))) for c in found}
        self.assertIn(("caller", 0), kinds)
        self.assertIn(("field", 0x38), kinds)
        self.assertEqual(found[0]["kind"], "caller")             # stabil und am sichersten -> zuerst
        self.assertEqual(found[0]["player"], [RET_A])


if __name__ == "__main__":
    unittest.main()
