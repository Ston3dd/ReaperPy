"""Tests fuer cheatmenu_cave.py: Cheat-Menue-Eintrag -> Treffer -> passende Code Cave (nativ ausgefuehrt)."""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cheatmenu as M
import cheatmenu_cave as C
import ue_instr as U
from pathlib import Path

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
set_flag:
  mov byte ptr [rdi+0x150], 1
  mov eax, 1
  mov edx, 2
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
"""
HAVE = shutil.which("as") and shutil.which("objdump") and shutil.which("gcc") and shutil.which("objcopy")


def entry(label, kind, cls, member, typ, offset, **kw):
    return M.Entry(key=f"g:{cls}.{member}", cat="Test", label=label, kind=kind, cls=cls, member=member, type=typ,
                   offset=offset, source="spiel", **kw)


class FakeMenu:
    sdk = None

    def _off(self, cls, member):
        return None


class FakeClient:
    def __init__(self, maps, mem):
        self.maps, self.mem, self.reads = maps, mem, []

    def get_maps(self):
        return self.maps

    def read_memory(self, addr, n):
        self.reads.append((addr, n))
        if addr < 0x400000 or addr + n > 0x400000 + len(self.mem):
            raise OSError("unlesbar")
        return self.mem[addr - 0x400000: addr - 0x400000 + n]


class Pure(unittest.TestCase):
    def test_value_bits(self):
        self.assertEqual(C.value_bits("float", "100", 4), struct.unpack("<I", struct.pack("<f", 100.0))[0])
        self.assertEqual(C.value_bits("int32", "99", 4), 99)
        self.assertEqual(C.value_bits("int32", "-1", 4), 0xFFFFFFFF)
        self.assertEqual(C.value_bits("bool", "an", 1), 1)
        self.assertEqual(C.value_bits("uint8", "aus", 1), 0)
        self.assertEqual(C.value_bits("double", "0", 8), 0)
        for typ, text, size in (("float", "1", 8), ("double", "1.5", 8), ("int32", "abc", 4), ("float", "auto", 4)):
            with self.assertRaises(C.CaveError, msg=(typ, text, size)):
                C.value_bits(typ, text, size)

    def test_entry_value_defaults(self):
        t = entry("Schalter", "toggle", "A", "bX", "bool", 0x150, on=True, off=False)
        self.assertEqual(C.entry_value(t), "1")
        t2 = entry("Modus", "toggle", "A", "Mode", "uint8", 0x150, on=5, off=3)
        self.assertEqual(C.entry_value(t2), "5")
        t3 = entry("Gott", "toggle", "A", "bCan", "bool", 0x150, on=False, off=True)
        self.assertEqual(C.entry_value(t3), "0")
        v = entry("Leben", "value", "A", "Health", "float", 0x348, default="auto")
        self.assertEqual(C.entry_value(v, "250"), "250")

    def test_small_offset_is_explained(self):
        e = entry("Zeit", "value", "AActor", "CustomTimeDilation", "float", 0x60)
        with self.assertRaises(C.CaveError) as cm:
            C.entry_offset(FakeMenu(), e)
        self.assertIn("+0x60", str(cm.exception))

    def test_live_offset_wins_for_engine_entries(self):
        class Live(FakeMenu):
            def _off(self, cls, member):
                return 0x1A0
        e = M.Entry(key="x", cat="c", label="l", kind="value", cls="A", member="B", type="float", offset=0x150)
        self.assertEqual(C.entry_offset(Live(), e), 0x1A0)
        self.assertEqual(C.entry_offset(FakeMenu(), e), 0x150)          # nicht lesbar -> SDK-Offset

    def test_save_patch_never_overwrites(self):
        d = tempfile.mkdtemp()
        p = {"name": "Leben: <test>", "author": "", "Variables": []}
        a, b = C.save_patch(d, p), C.save_patch(d, p)
        self.assertNotEqual(a, b)
        self.assertTrue(a.endswith(".reapproj") and os.path.exists(os.path.join(d, a)))
        self.assertEqual(json.loads(Path(os.path.join(d, b)).read_text(encoding="utf-8"))["name"], p["name"])

    def test_code_from_console_reads_the_main_exec_region(self):
        mem = bytes(range(256)) * 64
        maps = [(0x200000, 0x300000, 3), (0x400000, 0x400000 + len(mem) // 2, 5),
                (0x400000 + len(mem) // 2, 0x400000 + len(mem), 5), (0x9000000, 0x9100000, 5)]
        cl = FakeClient(maps, mem)
        seen = []
        code = C.code_from_console(cl, 0x400000, progress=lambda a, b: seen.append((a, b)), chunk=0x1000)
        self.assertEqual(code["buf"], mem)                              # beide zusammenhaengende Teile
        self.assertEqual((code["base_va"], code["dump_rva"], code["range"]), (0x400000, 0, (0, len(mem))))
        self.assertEqual(seen[-1][0], len(mem))

    def test_code_from_console_fills_unreadable_chunks(self):
        mem = b"\x90" * 0x2000
        cl = FakeClient([(0x400000, 0x400000 + 0x4000, 5)], mem)        # zweite Haelfte nicht lesbar
        code = C.code_from_console(cl, 0x400000, chunk=0x2000)
        self.assertEqual(len(code["buf"]), 0x4000)
        self.assertEqual(code["buf"][:0x2000], mem)
        self.assertEqual(code["buf"][0x2000:], b"\x00" * 0x2000)

    def test_code_from_console_errors(self):
        with self.assertRaises(C.CaveError):
            C.code_from_console(FakeClient([(0x200000, 0x300000, 3)], b""), 0x400000)
        with self.assertRaises(C.CaveError):
            C.code_from_console(FakeClient([(0x900000, 0x901000, 5)], b""), 0x400000)       # nichts lesbar

    def test_code_from_project_needs_a_dump(self):
        with self.assertRaises(C.CaveError):
            C.code_from_project(type("P", (), {"dm": None})())


@unittest.skipUnless(HAVE, "Toolchain fehlt")
class Real(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp()
        Path(os.path.join(d, "t.s")).write_text(ASM, encoding="utf-8")
        subprocess.run(["as", "--64", "-o", os.path.join(d, "t.o"), os.path.join(d, "t.s")], check=True)
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text", os.path.join(d, "t.o"), os.path.join(d, "t.bin")],
                       check=True)
        dump = b"\xCC" * 16 + Path(os.path.join(d, "t.bin")).read_bytes()
        cls.code = {"buf": dump, "lo": 0, "hi": len(dump), "base_va": 0x400000, "dump_rva": 0, "range": (0, len(dump))}
        cls.dis = U.ObjdumpDisasm()

    def opts(self, e):
        return C.find_options(FakeMenu(), e, self.code, self.dis)

    def run_cave(self, patch, setup, check, arg_kind="int"):
        """Cave-Text (Haken-Rueckkehr -> Ziel-Label) in eine Testfunktion setzen und nativ ausfuehren."""
        lines = [l.replace("OriginReturn", "done_cave") for l in patch["Variables"][2]["defaultValue"].splitlines()]
        if arg_kind == "float":
            pre = ["push rbx", "mov rbx, rdi", "movaps xmm1, xmm0", "xor ecx, ecx"]
            post = ["done_cave:", "mov eax, ecx", "pop rbx", "ret"]
            proto = "extern int run(char *base, float f);"
        else:
            pre = ["xor ecx, ecx"]
            post = ["done_cave:", "mov eax, ecx", "ret"]
            proto = "extern int run(char *base, int v);"
        asm = ".intel_syntax noprefix\n.text\n.globl run\n" + "\n".join(["run:"] + pre + lines + post) + "\n"
        c = ("#include <stdio.h>\n" + proto + "\nint main(void){ static char buf[0x1000];\n" + setup +
             "\n  return 0; }\n")
        d = tempfile.mkdtemp()
        Path(os.path.join(d, "c.s")).write_text(asm, encoding="utf-8")
        Path(os.path.join(d, "m.c")).write_text(c, encoding="utf-8")
        subprocess.run(["gcc", "-o", os.path.join(d, "m"), os.path.join(d, "m.c"), os.path.join(d, "c.s")],
                       check=True, capture_output=True)
        out = subprocess.run([os.path.join(d, "m")], capture_output=True, text=True, encoding="utf-8").stdout.split()
        self.assertEqual(out, check)

    # ------------------------------------------------------------------ Treffer
    def test_health_prefers_keep_cave(self):
        e = entry("UHealthComponent.Health", "value", "UHealthComponent", "Health", "float", 0x348, default="auto")
        opts = self.opts(e)
        opt, mode = C.pick_best(e, opts)
        self.assertEqual(mode, "keep")
        self.assertEqual(opt.hit.ins.mnem, "movss")
        self.assertTrue(opt.modes["force"][0] and opt.modes["nop"][0])
        self.assertIn("movss", C.describe(opt)[0])

    def test_toggle_gets_force_not_keep(self):
        e = entry("ACharacter.bFlag", "toggle", "ACharacter", "bFlag", "bool", 0x150, on=False, off=True)
        opt, mode = C.pick_best(e, self.opts(e))
        self.assertEqual(mode, "force")
        self.assertFalse(opt.modes["keep"][0])
        self.assertIn("Schalter", opt.modes["keep"][1])

    def test_bitfield_toggle_refuses_byte_store(self):
        e = entry("AActor.bBit", "toggle", "AActor", "bBit", "uint8", 0x150, on=True, off=False, bit=3)
        opt = self.opts(e)[0]
        self.assertFalse(opt.modes["force"][0])
        self.assertIn("Bit", opt.modes["force"][1])
        self.assertEqual(C.pick_best(e, [opt]), (None, None))

    def test_wrapped_struct_refuses_force(self):
        import ue_quick as Q
        t = Q.Target("UAttr", "Health.CurrentValue", "float", 0x348, parent="Health", sub=0xC)
        e = entry("UAttr.Health.CurrentValue", "value", "UAttr", "Health.CurrentValue", "float", 0x348, target=t)
        opt = self.opts(e)[0]
        self.assertFalse(opt.modes["force"][0])
        self.assertTrue(opt.modes["keep"][0])

    # ------------------------------------------------------------------ Caves nativ
    def test_keep_cave_float_runs(self):
        e = entry("UHealthComponent.Health", "value", "UHealthComponent", "Health", "float", 0x348, default="auto")
        opt, mode = C.pick_best(e, self.opts(e))
        patch = C.build_patch(e, opt, mode, self.code, self.dis, log=lambda m: None)
        self.assertEqual(patch["name"], "UHealthComponent.Health - Wert kann nicht sinken")
        self.run_cave(patch, "float *hp=(float*)(buf+0x348); *hp=100.f; run(buf,40.f); float a=*hp; run(buf,150.f);"
                             " printf(\"%.1f %.1f\\n\", a, *hp);", ["100.0", "150.0"], "float")

    def test_force_cave_int_sets_the_value_after_the_original_store(self):
        e = entry("UWeaponComponent.CurrentAmmo", "value", "UWeaponComponent", "CurrentAmmo", "int32", 0x200,
                  default="auto")
        opt = next(o for o in self.opts(e) if o.hit.ins.mnem == "sub")
        patch = C.build_patch(e, opt, "force", self.code, self.dis, value="99", log=lambda m: None)
        self.assertEqual(patch["name"], "UWeaponComponent.CurrentAmmo = 99 (Cave)")
        lines = patch["Variables"][2]["defaultValue"].splitlines()
        self.assertEqual(lines[0].lower().split()[0], "sub")
        self.assertIn("mov dword ptr [rdi+0x200], 0x63", lines[1].lower().replace(" + ", "+"))
        self.assertEqual(int(patch["Variables"][1]["offset"], 16), opt.hit.ins.size + sum(j.size for j in opt.hit.stolen))
        # Munition 500 -> Spiel zieht 30 ab -> Cave schreibt 99; das mov eax,[rdi+0x204] (gestohlen) laeuft weiter
        self.run_cave(patch, "int *a=(int*)(buf+0x200); int *b=(int*)(buf+0x204); *a=500; *b=7; int r=run(buf,30);"
                             " printf(\"%d %d %d\\n\", *a, *b, r);", ["99", "7", "0"], "int")

    def test_force_cave_toggle_byte(self):
        e = entry("ACharacter.bFlag", "toggle", "ACharacter", "bFlag", "bool", 0x150, on=False, off=True)
        opt, mode = C.pick_best(e, self.opts(e))
        patch = C.build_patch(e, opt, mode, self.code, self.dis, log=lambda m: None)
        self.assertEqual(patch["name"], "ACharacter.bFlag = 0 (Cave)")
        self.run_cave(patch, "buf[0x150]=5; run(buf,0); printf(\"%d\\n\", buf[0x150]);", ["0"], "int")

    def test_force_cave_float_bits(self):
        e = entry("UHealthComponent.Health", "value", "UHealthComponent", "Health", "float", 0x348, default="auto")
        opt = next(o for o in self.opts(e) if o.hit.ins.mnem == "movss")
        patch = C.build_patch(e, opt, "force", self.code, self.dis, value="777.5", log=lambda m: None)
        self.run_cave(patch, "float *hp=(float*)(buf+0x348); *hp=1.f; run(buf,40.f); printf(\"%.1f\\n\", *hp);",
                      ["777.5"], "float")

    def test_nop_patch(self):
        e = entry("UWalletComponent.Gold", "value", "UWalletComponent", "Gold", "int32", 0x100, default="auto")
        opt = self.opts(e)[0]
        patch = C.build_patch(e, opt, "nop", self.code, self.dis, log=lambda m: None)
        v = patch["Variables"][0]
        self.assertEqual(len(v["newValue"].split()), opt.hit.ins.size)
        self.assertEqual(set(v["newValue"].split()), {"90"})
        self.assertEqual(int(v["offset"], 16), opt.hit.rva)

    def test_force_needs_a_number(self):
        e = entry("UWeaponComponent.CurrentAmmo", "value", "UWeaponComponent", "CurrentAmmo", "int32", 0x200,
                  default="auto")
        opt = next(o for o in self.opts(e) if o.hit.ins.mnem == "sub")
        with self.assertRaises(C.CaveError) as cm:
            C.build_patch(e, opt, "force", self.code, self.dis, log=lambda m: None)         # Vorgabe 'auto'
        self.assertIn("auto", str(cm.exception))

    def test_unavailable_mode_is_reported_with_reason(self):
        e = entry("ACharacter.bFlag", "toggle", "ACharacter", "bFlag", "bool", 0x150, on=True, off=False)
        opt = self.opts(e)[0]
        with self.assertRaises(C.CaveError) as cm:
            C.build_patch(e, opt, "keep", self.code, self.dis, log=lambda m: None)
        self.assertIn("Schalter", str(cm.exception))
        with self.assertRaises(C.CaveError):
            C.build_patch(e, opt, "bogus", self.code, self.dis)

    def test_no_hit_gives_empty_list(self):
        e = entry("UX.Nothing", "value", "UX", "Nothing", "float", 0x999, default="auto")
        self.assertEqual(self.opts(e), [])
        self.assertEqual(C.pick_best(e, []), (None, None))


if __name__ == "__main__":
    unittest.main()
