import os, shutil, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ue_instr as U
from pathlib import Path

HAVE = shutil.which("as") and shutil.which("objdump") and shutil.which("gcc") and shutil.which("nm")

THUNKS = """
.intel_syntax noprefix
.text
.p2align 4,0xCC
helper:
  ret
.p2align 4,0xCC
helper2:
  ret
""" + "".join(f"""
.p2align 4,0xCC
impl{i}:
  mov eax, {i + 100}
  ret
.p2align 4,0xCC
thunk{i}:
  push rbx
  call helper
  call helper2
  call impl{i}
  pop rbx
  ret
""" for i in range(12)) + """
.p2align 4,0xCC
tail_impl:
  mov eax, 7
  ret
.p2align 4,0xCC
tail_thunk:
  call helper
  jmp tail_impl
.p2align 4,0xCC
"""


def build(asm):
    d = tempfile.mkdtemp()
    Path(os.path.join(d, "t.s")).write_text(asm, encoding="utf-8")
    subprocess.run(["as", "--64", "-o", os.path.join(d, "t.o"), os.path.join(d, "t.s")], check=True)
    subprocess.run(["objcopy", "-O", "binary", "-j", ".text", os.path.join(d, "t.o"), os.path.join(d, "t.bin")], check=True)
    syms = {}
    for line in subprocess.run(["nm", os.path.join(d, "t.o")], capture_output=True, text=True, encoding="utf-8").stdout.splitlines():
        p = line.split()
        if len(p) == 3:
            syms[p[2]] = int(p[0], 16) + 16
    return b"\xCC" * 16 + Path(os.path.join(d, "t.bin")).read_bytes(), syms


@unittest.skipUnless(HAVE, "Toolchain fehlt")
class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dump, cls.sym = build(THUNKS)
        cls.dis = U.ObjdumpDisasm(); cls.base = 0x400000
        cls.lo, cls.hi = 0, len(cls.dump)

    def va(self, n): return self.base + self.sym[n]

    def test_common_and_impl(self):
        thunks = [self.va(f"thunk{i}") for i in range(12)]
        common = U.common_callees(self.dump, self.dis, thunks, self.base, self.lo, self.hi)
        self.assertEqual(common, {self.va("helper"), self.va("helper2")})
        for i in (0, 5, 11):
            r = U.resolve_impl(self.dump, self.dis, self.va(f"thunk{i}"), self.base, self.lo, self.hi, common)
            self.assertEqual(r[0], self.va(f"impl{i}"), i)
        # Tail-Jump: das Ziel ist die Implementierung
        r = U.resolve_impl(self.dump, self.dis, self.va("tail_thunk"), self.base, self.lo, self.hi, common)
        self.assertEqual(r[0], self.va("tail_impl"))
        # ausserhalb des Code-Bereichs -> leer
        self.assertEqual(U.resolve_impl(self.dump, self.dis, 0x9000000, self.base, self.lo, self.hi), [])

    def test_ret_patches_native(self):
        asm = ".intel_syntax noprefix\n.text\n.globl f\nf:\n  mov dword ptr [rdi], 5\n  mov eax, 7\n  ret\n"
        d = tempfile.mkdtemp()
        Path(os.path.join(d, "f.s")).write_text(asm, encoding="utf-8")
        C = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <sys/mman.h>
extern int f(int *p);
int main(int argc, char **argv){
  uint8_t *fp = (uint8_t*)f; mprotect((void*)((uintptr_t)fp & ~0xFFFUL), 0x2000, PROT_READ|PROT_WRITE|PROT_EXEC);
  uint8_t code[8]; int n = 0; for (int i = 1; i < argc; i++) code[n++] = (uint8_t)strtol(argv[i], 0, 16);
  memcpy(fp, code, n);
  int v = 0; int r = f(&v);
  printf("%d %d\n", v, r); return 0; }
'''
        Path(os.path.join(d, "m.c")).write_text(C.replace("#include <sys/mman.h>", "#include <sys/mman.h>\n#include <stdlib.h>"), encoding="utf-8")
        subprocess.run(["gcc", "-o", os.path.join(d, "m"), os.path.join(d, "m.c"), os.path.join(d, "f.s")], check=True, capture_output=True)
        for mode, expect_r in (("false", 0), ("one", 1), ("true", 1)):
            code = U.RET_MODES[mode][0]
            out = subprocess.run([os.path.join(d, "m")] + [f"{b:02x}" for b in code], capture_output=True, text=True, encoding="utf-8").stdout.split()
            self.assertEqual(out[0], "0", mode)                       # *p wurde NICHT geschrieben
            self.assertEqual(int(out[1]) & 0xFF, expect_r, mode)
        out = subprocess.run([os.path.join(d, "m"), "c3"], capture_output=True, text=True, encoding="utf-8").stdout.split()
        self.assertEqual(out[0], "0")
        p = U.func_ret_patch(self.dump, self.sym["thunk0"], 0x1234, "false", "UFoo.Bar", "AA BB ?? CC")
        v = p["Variables"][0]
        self.assertEqual(v["newValue"], "31 C0 C3"); self.assertEqual(v["offset"], "0x1234")
        self.assertEqual(v["aob"], "AA BB ?? CC")

    def test_bounded_scan(self):
        # derselbe Offset ausserhalb des Bereichs darf nicht gefunden werden
        code = b"\xCC" * 16 + b"\x53\x89\x83\x48\x03\x00\x00\xC3" + b"\xCC" * 8
        fake = b"\xCC" * 16 + code + b"\xCC" * 8
        hits_all = U.byte_hits(fake, {0x348})
        hits_none = U.byte_hits(fake, {0x348}, lo=0, hi=20)
        self.assertTrue(hits_all[0x348]); self.assertEqual(hits_none[0x348], [])

if __name__ == "__main__":
    unittest.main()
