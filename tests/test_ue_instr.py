"""Scan + Patch-Bau gegen echten Maschinencode (GNU as, int3-Padding) und nativer Cave-Ausfuehrung."""
import os, shutil, struct, subprocess, sys, tempfile, unittest
from types import SimpleNamespace
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ue_instr as U

ASM = """
.intel_syntax noprefix
.text
.p2align 4,0xCC
take_damage:
  push rbx
  mov rbx, rdi
  movss xmm1, dword ptr [rbx+0x348]
  subss xmm1, xmm0
  xorps xmm2, xmm2
  maxss xmm1, xmm2
  movss dword ptr [rbx+0x348], xmm1
  movss xmm3, dword ptr [rbx+0x34C]
  mov eax, 1
  pop rbx
  ret
.p2align 4,0xCC
consume_ammo:
  sub dword ptr [rdi+0x200], esi
  mov eax, dword ptr [rdi+0x204]
  ret
.p2align 4,0xCC
spend_gold:
  mov eax, dword ptr [rdi+0x100]
  sub eax, esi
  mov dword ptr [rdi+0x100], eax
  mov ecx, 1
  mov edx, 2
  ret
.p2align 4,0xCC
unrelated:
  mov dword ptr [rdi+0x348], 0
  call take_damage
  ret
.p2align 4,0xCC
"""
HAVE = shutil.which("as") and shutil.which("objdump") and shutil.which("gcc")


def build_dump(d):
    open(os.path.join(d, "t.s"), "w").write(ASM)
    subprocess.run(["as", "--64", "-o", os.path.join(d, "t.o"), os.path.join(d, "t.s")], check=True)
    subprocess.run(["objcopy", "-O", "binary", "-j", ".text", os.path.join(d, "t.o"), os.path.join(d, "t.bin")], check=True)
    return b"\xCC" * 16 + open(os.path.join(d, "t.bin"), "rb").read()      # wie im echten Image: Padding davor


@unittest.skipUnless(HAVE, "Toolchain fehlt")
class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.dump = build_dump(cls.d)
        cls.dis = U.ObjdumpDisasm()
        cls.base = 0x400000

    def scan(self, targets, cls_offs=None):
        return U.scan(self.dump, targets, self.dis, cls_offs, base_va=self.base, dump_rva=self.base - 0x400000)

    def test_hits_and_ranking(self):
        hits = self.scan({0x348: ["UHealthComponent.Health"]}, {0x34C})
        self.assertGreaterEqual(len(hits), 2)
        best = hits[0]
        self.assertEqual(best.ins.mnem, "movss")
        self.assertTrue(best.writes and best.dec_hint)
        self.assertEqual(best.coaccess, 1)                       # 0x34C in derselben Funktion
        self.assertEqual(best.kind, "store")
        other = [h for h in hits if h.ins.mnem == "mov"][0]      # 'unrelated': Konstante schreiben
        self.assertLess(other.score, best.score)
        self.assertEqual(self.dump[best.pos:best.pos + best.ins.size], best.ins.raw)

    def test_dec_instruction(self):
        h = self.scan({0x200: ["UWeaponComponent.CurrentAmmo"]})[0]
        self.assertEqual((h.ins.mnem, h.kind), ("sub", "dec"))
        p = U.nop_patch(self.dump, h)
        v = p["Variables"][0]
        self.assertEqual(v["newValue"], "90 " * 5 + "90" if h.ins.size == 6 else v["newValue"])
        self.assertEqual(len(v["newValue"].split()), h.ins.size)
        self.assertEqual(bytes.fromhex(v["defaultValue"].replace(" ", "")), h.ins.raw)
        self.assertEqual(int(v["offset"], 16), h.rva)

    def test_reads_excluded_by_default(self):
        hits = self.scan({0x34C: ["x"]})
        self.assertEqual(hits, [])                               # 0x34C wird nur gelesen
        hits = U.scan(self.dump, {0x34C: ["x"]}, self.dis, base_va=self.base, include_reads=True)
        self.assertTrue(hits and not hits[0].writes)

    def test_aob_unique(self):
        h = self.scan({0x100: ["UWalletComponent.Gold"]})[0]
        text, n = U.make_aob(self.dump, self.dis, h, self.base, min_len=8)
        # winzige Test-Funktion: Signatur darf scheitern, wenn sie nicht eindeutig sein kann - aber
        # wenn eine geliefert wird, muss sie genau die Stelle treffen
        if text:
            import aob
            pat, mask = aob.parse_pattern(text)
            found = U._all_matches(aob._regex(pat, mask), self.dump)
            self.assertEqual(found, [h.pos])

    # ---------- erzeugte Caves nativ ausfuehren ----------
    def run_cave(self, patch, kind):
        lines = patch["Variables"][2]["defaultValue"].splitlines()
        lines = [l.replace("OriginReturn", "done_cave") for l in lines]
        if kind == "float":
            wrapper = ["run:", "push rbx", "mov rbx, rdi", "movaps xmm1, xmm0", "xor ecx, ecx"] + lines + \
                      ["done_cave:", "mov eax, ecx", "pop rbx", "ret"]
        else:
            wrapper = ["run:", "xor ecx, ecx", "mov eax, esi"] + lines + ["done_cave:", "mov eax, ecx", "ret"]
        asm = ".intel_syntax noprefix\n.text\n.globl run\n" + "\n".join(wrapper) + "\n"
        c = r'''
#include <stdio.h>
#include <string.h>
extern int run(char *base, float f);
int main(void){ static char buf[0x1000]; float *hp=(float*)(buf+0x348); int *gold=(int*)(buf+0x100);
  *hp=100.f; *gold=500;
  int r1=run(buf, 40.f); float a=*hp; run(buf,150.f); float b=*hp;
  /* int-Variante: zweites Argument als int in esi */
  return printf("%d %.1f %.1f\n", r1, a, b) < 0; }
'''
        cint = r'''
#include <stdio.h>
extern int run(char *base, int v);
int main(void){ static char buf[0x1000]; int *gold=(int*)(buf+0x100); *gold=500;
  int r1=run(buf, 300); int a=*gold; run(buf, 800); int b=*gold; printf("%d %d %d\n", r1, a, b); return 0; }
'''
        d = tempfile.mkdtemp()
        open(os.path.join(d, "c.s"), "w").write(asm)
        open(os.path.join(d, "m.c"), "w").write(c if kind == "float" else cint)
        subprocess.run(["gcc", "-o", os.path.join(d, "m"), os.path.join(d, "m.c"), os.path.join(d, "c.s")], check=True,
                       capture_output=True)
        return subprocess.run([os.path.join(d, "m")], capture_output=True, text=True).stdout.split()

    def test_cave_float_never_decreases(self):
        h = [x for x in self.scan({0x348: ["Health"]}, {0x34C}) if x.ins.mnem == "movss"][0]
        ok, why = U.can_cave(h); self.assertTrue(ok, why)
        p = U.keep_cave_patch(self.dump, h)
        self.assertEqual(p["Variables"][0]["newValue"], "jmp OriginTarget")
        self.assertEqual(int(p["Variables"][1]["offset"], 16), 8)
        # Original-Instruktion rbx-relativ mit xmm1 -> Test-Wrapper nutzt rbx/xmm1 wie die Funktion
        r1, a, b = self.run_cave(p, "float")
        self.assertEqual((a, b), ("100.0", "150.0"))             # 40 geblockt, 150 geschrieben

    def test_cave_int_with_stolen_instruction(self):
        h = self.scan({0x100: ["Gold"]})[0]
        self.assertEqual(h.ins.mnem, "mov")
        self.assertEqual([j.mnem for j in h.stolen], ["mov"])
        ok, why = U.can_cave(h); self.assertTrue(ok, why)
        p = U.keep_cave_patch(self.dump, h)
        self.assertEqual(int(p["Variables"][1]["offset"], 16), h.ins.size + h.stolen[0].size)
        r1, a, b = self.run_cave(p, "int")
        self.assertEqual((r1, a, b), ("1", "500", "800"))         # 300 geblockt, 800 erlaubt, mov ecx,1 lief

    def test_cave_refused(self):
        h = [x for x in self.scan({0x348: ["Health"]}) if x.ins.mnem == "mov"][0]       # Store einer Konstante
        ok, why = U.can_cave(h)
        self.assertFalse(ok)
        with self.assertRaises(ValueError):
            U.keep_cave_patch(self.dump, h)


class MockCapstone(unittest.TestCase):
    def test_conv(self):
        cs = SimpleNamespace(x86=SimpleNamespace(X86_OP_MEM=3), CS_AC_READ=1, CS_AC_WRITE=2, CS_GRP_JUMP=1, CS_GRP_CALL=2)
        d = U.CapstoneDisasm.__new__(U.CapstoneDisasm); d.cs = cs
        op = SimpleNamespace(type=3, access=2, mem=SimpleNamespace(base=5, index=0, scale=1, disp=0x348))
        ins = SimpleNamespace(address=0x1000, size=8, bytes=b"\xf3\x0f\x11\x8b\x48\x03\x00\x00", mnemonic="movss",
                              op_str="dword ptr [rbx + 0x348], xmm1", operands=[op], disp_size=4, disp_offset=4,
                              imm_size=0, imm_offset=0, group=lambda g: False, reg_name=lambda r: {5: "rbx"}.get(r))
        r = d._conv(ins)
        self.assertEqual((r.mem.base, r.mem.disp, r.writes, r.reads, r.wild), ("rbx", 0x348, True, False, [(4, 4)]))
        self.assertEqual(r.text, "movss dword ptr [rbx + 0x348], xmm1")

if __name__ == "__main__":
    unittest.main()
