"""Fuehrt den Logger-Stub NATIV aus (gcc/as/ld noetig, sonst uebersprungen): Hook in einer
Testfunktion, mehrere Aufrufe inkl. Ringpuffer-Ueberlauf, Register-/Flag-Erhaltung."""
import os, shutil, struct, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import logger as L
from pathlib import Path

BASE, RING = 0x20000000, 16
FN, STUB = BASE + 0x1000, BASE + 0x2000
HOOK = FN + 2                       # direkt hinter 'cmp edi, esi' -> Flags muessen erhalten bleiben
FN_ASM = """
.intel_syntax noprefix
.text
  cmp edi, esi
  mov eax, 1
  nop
  nop
  nop
  je 1f
  add eax, edx
  ret
1: mov eax, 100
  ret
"""
C_SRC = r"""
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
typedef long (*F)(long,long,long,long,long,long,long,long,double,double);
static void load(const char *p, void *dst){FILE*f=fopen(p,"rb");if(!f)exit(2);char b[4096];size_t n=fread(b,1,4096,f);memcpy(dst,b,n);fclose(f);}
int main(void){
  char *m = mmap((void*)0x20000000, 0x10000, PROT_READ|PROT_WRITE|PROT_EXEC, MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE, -1, 0);
  if(m != (char*)0x20000000) return 3;
  load("fn.bin", m+0x1000); load("stub.bin", m+0x2000); load("hook.bin", m+0x1002);
  F f = (F)(m+0x1000);
  for(int i=0;i<40;i++){
    long a = (i%3==0)? 5 : i;                       /* i%3==0 -> rdi==rsi -> je genommen */
    long r = f(a, (i%3==0)?5:i+1, 7+i, 1000+i, 2000+i, 3000+i, 4000+i, 5000+i, 1.5+i, 2.5+i);
    printf("%d %ld\n", i, r);
  }
  FILE*o=fopen("ring.bin","wb"); fwrite(m, 1, 0x40+16*128, o); fclose(o);
  return 0; }
"""

@unittest.skipUnless(shutil.which("gcc") and shutil.which("as") and shutil.which("ld"), "keine Toolchain")
class T(unittest.TestCase):
    def sh(self, *cmd):
        subprocess.run(cmd, check=True, capture_output=True, cwd=self.d)

    def test_native(self):
        self.d = tempfile.mkdtemp()
        w = lambda n, t: Path(os.path.join(self.d, n)).write_text(t, encoding="utf-8")
        r = lambda n: Path(os.path.join(self.d, n)).read_bytes()
        w("fn.s", FN_ASM); self.sh("as", "--64", "-o", "fn.o", "fn.s")
        self.sh("objcopy", "-O", "binary", "-j", ".text", "fn.o", "fn.bin")
        stolen = r("fn.bin")[2:10]
        self.assertEqual(stolen[:1], b"\xB8")
        body = "\n".join([".intel_syntax noprefix", ".text"] + L.stub_asm(BASE, RING, thread=True)
                         + ["  .byte " + ",".join(str(b) for b in stolen), f"  jmp {FN + 10:#x}"])
        w("stub.s", body); self.sh("as", "--64", "-o", "stub.o", "stub.s")
        self.sh("ld", f"-Ttext={STUB:#x}", "--oformat", "binary", "-o", "stub.bin", "stub.o")
        rel = STUB - (HOOK + 5)
        Path(os.path.join(self.d, "hook.bin")).write_bytes(b"\xE9" + struct.pack("<i", rel) + b"\x90\x90\x90")
        w("h.c", C_SRC); self.sh("gcc", "-O0", "-o", "h", "h.c")
        res = subprocess.run(["./h"], cwd=self.d, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, res.stderr)
        rets = {int(a): int(b) for a, b in (l.split() for l in res.stdout.splitlines())}
        for i in range(40):                                  # Flags + rdx bleiben unberuehrt
            self.assertEqual(rets[i], 100 if i % 3 == 0 else 1 + 7 + i, i)
        ring = r("ring.bin")
        read = lambda a, n: ring[a - BASE:a - BASE + n]
        recs, idx, lost = L.collect(read, BASE, RING, 0)     # 40 Aufrufe, Ring 16 -> 24 verloren
        self.assertEqual((idx, lost, len(recs)), (40, 24, 16))
        for rec in recs:
            i = rec["index"]
            a = 5 if i % 3 == 0 else i
            self.assertEqual((rec["rdi"], rec["rsi"], rec["rdx"], rec["rcx"], rec["r8"], rec["r9"]),
                             (a, 5 if i % 3 == 0 else i + 1, 7 + i, 1000 + i, 2000 + i, 3000 + i))
            self.assertEqual((rec["s7"], rec["s8"]), (4000 + i, 5000 + i))
            self.assertEqual(struct.unpack("<d", struct.pack("<Q", rec["xmm0"]))[0], 1.5 + i)
            self.assertEqual(struct.unpack("<d", struct.pack("<Q", rec["xmm1"]))[0], 2.5 + i)
            self.assertTrue(rec["ret"] > 0 and rec["thread"] > 0 and rec["rsp"] % 8 == 0)
        # Teil-Lesen: ab Index 30 nur 10 Eintraege, keine Verluste
        recs2, idx2, lost2 = L.collect(read, BASE, RING, 30)
        self.assertEqual((idx2, lost2, len(recs2)), (40, 0, 10))
        # unvollstaendiger Eintrag (seq falsch) stoppt das Lesen
        broken = bytearray(ring); off = L.HEADER + (35 & 15) * L.REC; broken[off:off + 8] = bytes(8)
        recs3, idx3, _ = L.collect(lambda a, n: bytes(broken)[a - BASE:a - BASE + n], BASE, RING, 30)
        self.assertEqual((len(recs3), idx3), (5, 35))

if __name__ == "__main__":
    unittest.main()
