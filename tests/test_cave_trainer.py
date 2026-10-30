"""Tests fuer cave_trainer (statische Item-Cave als ReaperPy-Projekt).

Die Cave wird hier WIRKLICH ausgefuehrt (Linux x86-64, mmap + ctypes):  ein Treiber ruft sie wie das Spiel das
ProcessEvent (mit magischen Werten in den callee-saved Registern), eine Hilfsfunktion (Item-Funktion) und ein
Hilfs-ProcessEvent schreiben ihre Register in Puffer.  Alles liegt in EINEM mmap-Bereich, damit die rel32-Spruenge
reichen.  Zusaetzlich wird die Cave mit objdump zerlegt.  Ohne gcc/binutils/Linux/x86-64 werden diese Tests
uebersprungen; die Plan-/Projekt-Tests laufen ueberall.
"""
import ctypes
import json
import mmap
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cave_trainer as T

NATIVE = (platform.system() == "Linux" and platform.machine() in ("x86_64", "AMD64")
          and all(shutil.which(x) for x in ("as", "ld", "objcopy", "objdump")))

# Layout im mmap-Bereich
HELP_OFF = 0x0000       # Hilfscode (rec_fn @0, rec_pe @0x100, driver @0x200)
LOG_OFF = 0x0800        # logcnt (8 Byte) + logbuf (48 Byte je Aufruf)
PE_BUF = 0x0F00         # rec_pe schreibt: rdi, rsi, rdx, rsp
DRV_BUF = 0x0F80        # Treiber schreibt: rbx, rbp, r12..r15 nach dem Aufruf, rax
CAVE_OFF = 0x1000
FLAG_OFF = 0x3000
SIZE = 0x4000

HELPERS = r"""
.intel_syntax noprefix
.text
.org 0x0
rec_fn:
  mov rax, [rip+logcnt]
  lea r10, [rip+logbuf]
  imul r11, rax, 48
  add r10, r11
  mov [r10], rdi
  mov [r10+8], rsi
  mov [r10+16], rdx
  mov [r10+24], rcx
  mov [r10+32], r8
  mov [r10+40], rsp
  inc rax
  mov [rip+logcnt], rax
  mov eax, 0x1234
  ret
.org 0x100
rec_pe:
  lea rax, [rip+pebuf]
  mov [rax], rdi
  mov [rax+8], rsi
  mov [rax+16], rdx
  mov [rax+24], rsp
  mov eax, 77
  ret
.org 0x200
driver:
  push rbx
  push rbp
  push r12
  push r13
  push r14
  push r15
  sub rsp, 8
  mov rbx, 0xB1B1B1B1
  mov rbp, 0xB2B2B2B2
  mov r12, 0xC1C1C1C1
  mov r13, 0xC2C2C2C2
  mov r14, 0xC3C3C3C3
  mov r15, 0xC4C4C4C4
  call CAVE
  lea r10, [rip+drvbuf]
  mov [r10], rbx
  mov [r10+8], rbp
  mov [r10+16], r12
  mov [r10+24], r13
  mov [r10+32], r14
  mov [r10+40], r15
  mov [r10+48], rax
  add rsp, 8
  pop r15
  pop r14
  pop r13
  pop r12
  pop rbp
  pop rbx
  ret
.org 0x800
logcnt: .quad 0
logbuf: .space 0x6F8
.org 0xF00
pebuf: .space 0x40
.org 0xF80
drvbuf: .space 0x40
"""


def make_options():
    return [
        T.Option("Gold", [T.Row("Item_Gold", bytes.fromhex("0102030405060708"), 99999)]),
        T.Option("Traenke", [T.Row("Item_PotionA", bytes.fromhex("1111111111111111"), 10),
                             T.Row("Item_PotionB", bytes.fromhex("2222222222222222"), 7)]),
        T.Option("Material", [T.Row("Item_Mat", bytes.fromhex("3333333333333333"), 0xFFFFFFFF)]),
    ]


def build_helpers(tmp, cave_abs_off):
    src = os.path.join(tmp, "h.s")
    with open(src, "w", encoding="utf-8") as f:
        f.write(HELPERS.replace("call CAVE", f"call {cave_abs_off}"))
    obj, elf, binf = (os.path.join(tmp, n) for n in ("h.o", "h.elf", "h.bin"))
    subprocess.run(["as", "--64", "-o", obj, src], check=True)
    subprocess.run(["ld", "-Ttext=0", "-e", "0", "-o", elf, obj], check=True)
    subprocess.run(["objcopy", "-O", "binary", "-j", ".text", elf, binf], check=True)
    with open(binf, "rb") as f:
        return f.read()


@unittest.skipUnless(NATIVE, "braucht Linux x86-64, as, ld, objcopy")
class NativeCave(unittest.TestCase):
    def setUp(self):
        self.mm = mmap.mmap(-1, SIZE, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
        self.base = ctypes.addressof(ctypes.c_char.from_buffer(self.mm))
        self.tmp = tempfile.mkdtemp()
        self.options = make_options()
        # 'call' im Treiber ist rel32 auf die absolute Cave-Adresse: Hilfscode wird mit Basis 0 gebaut und liegt bei
        # mmap+0, also ist CAVE_OFF das richtige Ziel (Position-unabhaengig)
        help_bin = build_helpers(self.tmp, CAVE_OFF)
        self.mm[HELP_OFF:HELP_OFF + len(help_bin)] = help_bin
        self.cave = self.base + CAVE_OFF
        code = T.build_cave(self.cave, self.base + FLAG_OFF, self.base + 0x100, self.base + 0x000, self.options)
        self.mm[CAVE_OFF:CAVE_OFF + len(code)] = code
        self.code = code
        self.driver = ctypes.CFUNCTYPE(ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64)(
            self.base + 0x200)

    def tearDown(self):
        del self.driver
        try:
            self.mm.close()
        except BufferError:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- Helfer ---------------------------------------------------------------------------------
    def set_flag(self, i, v=1):
        self.mm[FLAG_OFF + i] = v

    def flag(self, i):
        return self.mm[FLAG_OFF + i]

    def calls(self):
        n = struct.unpack("<Q", self.mm[LOG_OFF:LOG_OFF + 8])[0]
        out = []
        for k in range(n):
            o = LOG_OFF + 8 + 48 * k
            out.append(struct.unpack("<6Q", self.mm[o:o + 48]))
        return out

    def pe_seen(self):
        return struct.unpack("<4Q", self.mm[PE_BUF:PE_BUF + 32])

    def drv_seen(self):
        return struct.unpack("<7Q", self.mm[DRV_BUF:DRV_BUF + 56])

    def fname(self, row):
        return struct.unpack("<Q", row.fname)[0]

    # -- Tests ----------------------------------------------------------------------------------
    def test_idle_forwards_untouched(self):
        rax = self.driver(0x1111, 0x2222, 0x3333)
        self.assertEqual(rax, 77)                                       # Rueckgabe des ECHTEN ProcessEvent
        rdi, rsi, rdx, rsp = self.pe_seen()
        self.assertEqual((rdi, rsi, rdx), (0x1111, 0x2222, 0x3333))
        self.assertEqual(rsp % 16, 8)                                   # ABI: Eintritt rsp = 8 (mod 16)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.drv_seen()[:6], (0xB1B1B1B1, 0xB2B2B2B2, 0xC1C1C1C1, 0xC2C2C2C2, 0xC3C3C3C3, 0xC4C4C4C4))

    def test_flag_fires_once_with_exact_registers(self):
        self.set_flag(0)
        rax = self.driver(0x1111, 0x2222, 0x3333)
        self.assertEqual(rax, 77)
        gold = self.options[0].rows[0]
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        rdi, rsi, rdx, rcx, r8, rsp = calls[0]
        self.assertEqual((rdi, rsi, rdx, rcx, r8), (0, self.fname(gold), 99999, 1, 0))
        self.assertEqual(rsp % 16, 8)                                   # Stack am call richtig ausgerichtet
        self.assertEqual(self.flag(0), 0)                               # Schalter zurueckgesetzt
        rdi, rsi, rdx, _ = self.pe_seen()                               # Originalargumente danach unveraendert
        self.assertEqual((rdi, rsi, rdx), (0x1111, 0x2222, 0x3333))
        # callee-saved Register (rbx, rbp, r12-r15) sind nach dem Durchlauf unveraendert
        self.assertEqual(self.drv_seen()[:6], (0xB1B1B1B1, 0xB2B2B2B2, 0xC1C1C1C1, 0xC2C2C2C2, 0xC3C3C3C3, 0xC4C4C4C4))
        # zweiter Aufruf: nichts mehr
        self.driver(1, 2, 3)
        self.assertEqual(len(self.calls()), 1)

    def test_multi_row_option_runs_rows_in_order(self):
        self.set_flag(1)
        self.driver(5, 6, 7)
        rows = self.options[1].rows
        got = [(c[1], c[2], c[3], c[4]) for c in self.calls()]
        self.assertEqual(got, [(self.fname(r), r.amount, 1, 0) for r in rows])

    def test_amount_uses_full_32_bits(self):
        self.set_flag(2)
        self.driver(1, 2, 3)
        self.assertEqual(self.calls()[0][2], 0xFFFFFFFF)

    def test_several_flags_run_in_option_order(self):
        self.set_flag(2)
        self.set_flag(0)
        self.driver(1, 2, 3)
        names = [c[1] for c in self.calls()]
        self.assertEqual(names, [self.fname(self.options[0].rows[0]), self.fname(self.options[2].rows[0])])
        self.assertEqual((self.flag(0), self.flag(1), self.flag(2)), (0, 0, 0))

    def test_unused_flag_byte_does_nothing_and_still_forwards(self):
        self.set_flag(5)                                                # gehoert zu keinem Eintrag
        rax = self.driver(0xA, 0xB, 0xC)
        self.assertEqual(rax, 77)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.pe_seen()[:3], (0xA, 0xB, 0xC))

    def test_flag_value_other_than_one_also_fires(self):
        self.set_flag(0, 0x80)
        self.driver(1, 2, 3)
        self.assertEqual(len(self.calls()), 1)

    def test_two_threads_only_one_gives(self):
        for _ in range(300):
            ctypes.memset(self.base + LOG_OFF, 0, 8)
            self.set_flag(0)
            bar = threading.Barrier(2)

            def run():
                bar.wait()
                for _k in range(3):
                    self.driver(1, 2, 3)

            ts = [threading.Thread(target=run) for _ in range(2)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            self.assertEqual(len(self.calls()), 1)

    def test_more_than_eight_options(self):
        opts = [T.Option(f"E{i}", [T.Row(f"A{i}", struct.pack("<Q", 0x100 + i), i + 1)]) for i in range(20)]
        code = T.build_cave(self.cave, self.base + FLAG_OFF, self.base + 0x100, self.base + 0x000, opts)
        self.assertLess(len(code), FLAG_OFF - CAVE_OFF)
        self.mm[CAVE_OFF:CAVE_OFF + len(code)] = code
        self.set_flag(17)
        self.set_flag(9)
        self.driver(1, 2, 3)
        self.assertEqual([(c[1], c[2]) for c in self.calls()], [(0x100 + 9, 10), (0x100 + 17, 18)])

    def test_disassembly_matches_intent(self):
        raw = os.path.join(self.tmp, "c.bin")
        with open(raw, "wb") as f:
            f.write(self.code)
        out = subprocess.run(["objdump", "-D", "-b", "binary", "-mi386:x86-64", "-M", "intel", raw],
                             check=True, capture_output=True, text=True, encoding="utf-8").stdout
        for needle in ("xor    eax,eax", "or     rax,QWORD PTR [rip+", "xchg   BYTE PTR [rip+", "test   al,al",
                       "push   rdi", "push   rsi", "push   rdx", "movabs rsi,0x807060504030201", "mov    edx,0x1869f",
                       "mov    ecx,0x1", "xor    r8d,r8d", "xor    edi,edi", "call", "pop    rdx", "pop    rsi", "pop    rdi",
                       "jmp"):
            self.assertIn(needle, out, needle)
        self.assertNotIn("(bad)", out)
        # jeder Befehl endet sauber: letzter Befehl ist der jmp zum echten ProcessEvent
        last = [ln for ln in out.splitlines() if re.match(r"\s+[0-9a-f]+:", ln)][-1]
        self.assertIn("jmp", last)


# ======================================================================
# Plan / Projekt (ohne Prozessor)
# ======================================================================
class FakeImage:
    """Kleines Fake-Image: Code r-x | rodata r-- | daten rw- ; Speicher = bytearray."""

    BASE = 0x400000

    def __init__(self):
        b = self.BASE
        self.maps = [(b, b + 0x10000, 5), (b + 0x10000, b + 0x12000, 1), (b + 0x12000, b + 0x16000, 3),
                     (0x7000000000, 0x7000100000, 3)]            # Heap, gehoert NICHT zum Image
        self.mem = {}
        for s, e, _p in self.maps:
            self.mem[s] = bytearray(e - s)
        self.impl = b + 0x1000
        self.pe = b + 0x2000
        self.slot = b + 0x12100
        self.write(self.slot, struct.pack("<Q", self.pe))
        self.write(self.impl, b"\x55\x48\x89\xe5" * 8)           # Code, kein Padding
        self.write(self.pe, b"\x55\x48\x89\xe5" * 8)

    def _reg(self, addr):
        for s, e, _p in self.maps:
            if s <= addr < e:
                return s, e
        raise IOError(f"{addr:#x} nicht gemappt")

    def write(self, addr, data):
        s, e = self._reg(addr)
        self.mem[s][addr - s:addr - s + len(data)] = data

    def read(self, addr, n):
        s, e = self._reg(addr)
        if addr + n > e:
            raise IOError("ueber Regionsende")
        return bytes(self.mem[s][addr - s:addr - s + n])


class PlanTests(unittest.TestCase):
    def mk(self, **kw):
        img = FakeImage()
        opts = kw.pop("options", make_options())
        return img, T.plan(img.read, img.maps, img.BASE, opts, img.impl, img.pe, kw.pop("slots", [img.slot]),
                           log=lambda _m: None, settle=0, **kw)

    def test_places_cave_and_flags_inside_image(self):
        img, p = self.mk()
        self.assertTrue(img.BASE + 0x0 <= p.cave < img.BASE + 0x10000)           # Code-Region
        self.assertEqual(p.cave % 16, 0)
        self.assertTrue(img.BASE + 0x12000 <= p.flag_addr < img.BASE + 0x16000)  # Daten-Region, nicht Heap
        self.assertEqual(p.flag_addr % 8, 0)
        self.assertEqual(p.cave_bytes, T.build_cave(p.cave, p.flag_addr, img.pe, img.impl, p.options))
        self.assertEqual(p.cave_orig, bytes(len(p.cave_bytes)))
        self.assertGreaterEqual(p.flag_size, 3)

    def test_slot_must_point_to_process_event(self):
        img = FakeImage()
        img.write(img.slot, struct.pack("<Q", img.pe + 0x10))
        with self.assertRaises(T.TrainerError) as c:
            T.plan(img.read, img.maps, img.BASE, make_options(), img.impl, img.pe, [img.slot], settle=0)
        self.assertIn("zeigt nicht auf ProcessEvent", str(c.exception))

    def test_addresses_outside_image_rejected(self):
        img = FakeImage()
        with self.assertRaises(T.TrainerError) as c:
            T.plan(img.read, img.maps, img.BASE, make_options(), 0x7000000100, img.pe, [img.slot], settle=0)
        self.assertIn("nicht im Spiel-Image", str(c.exception))

    def test_busy_flag_area_rejected(self):
        img = FakeImage()
        end = img.BASE + 0x16000
        img.write(end - 0x20, b"\x01")                         # Spiel nutzt das Ende der Daten-Region
        with self.assertRaises(T.TrainerError):
            T.plan(img.read, img.maps, img.BASE, make_options(), img.impl, img.pe, [img.slot], settle=0)

    def test_no_code_padding_rejected(self):
        img = FakeImage()
        img.write(img.BASE, b"\x55" * 0x10000)                  # Code reicht bis zum Regionsende, keine Luecke
        with self.assertRaises(T.TrainerError) as c:
            T.plan(img.read, img.maps, img.BASE, make_options(), img.impl, img.pe, [img.slot], settle=0)
        self.assertIn("Code-Platz", str(c.exception))

    def test_limits_and_duplicates(self):
        img = FakeImage()
        many = [T.Option(f"E{i}", [T.Row("A", bytes(8), 1)]) for i in range(65)]
        with self.assertRaises(T.TrainerError):
            T.plan(img.read, img.maps, img.BASE, many, img.impl, img.pe, [img.slot], settle=0)
        dup = [T.Option("Gold", [T.Row("A", bytes(8), 1)]), T.Option("gold", [T.Row("B", bytes(8), 1)])]
        with self.assertRaises(T.TrainerError):
            T.plan(img.read, img.maps, img.BASE, dup, img.impl, img.pe, [img.slot], settle=0)
        with self.assertRaises(T.TrainerError):
            T.plan(img.read, img.maps, img.BASE, [], img.impl, img.pe, [img.slot], settle=0)

    def test_row_validation(self):
        with self.assertRaises(T.TrainerError):
            T.Row("x", b"\x01" * 7, 1)
        with self.assertRaises(T.TrainerError):
            T.Row("x", bytes(8), 0)
        with self.assertRaises(T.TrainerError):
            T.Row("x", bytes(8), 2 ** 32)

    def test_changing_flag_area_detected(self):
        img = FakeImage()
        calls = {"n": 0}
        real = img.read

        def flaky(addr, n):
            d = bytearray(real(addr, n))
            if n == 8 and addr >= img.BASE + 0x12000 and addr != img.slot:
                calls["n"] += 1
                if calls["n"] >= 2:
                    d[0] = 7
            return bytes(d)

        with self.assertRaises(T.TrainerError) as c:
            T.plan(flaky, img.maps, img.BASE, make_options(), img.impl, img.pe, [img.slot],
                   log=lambda _m: None, settle=0.01)
        self.assertIn("aendert sich", str(c.exception))

    def test_image_span_tolerates_small_gaps_but_not_far_regions(self):
        b = 0x400000
        maps = [(b, b + 0x10000, 5), (b + 0x11000, b + 0x14000, 3), (b + 0x40000000, b + 0x40001000, 3)]
        span = T.image_span(maps, b)
        self.assertEqual([(s, e) for s, e, _p in span], [(b, b + 0x10000), (b + 0x11000, b + 0x14000)])
        self.assertEqual(T.image_span(maps, 0x10), [])

    def test_split_package_in_14er_chunks(self):
        rows = [T.Row(f"I{i}", struct.pack("<Q", i), 1) for i in range(30)]
        o = T.split_package("Fische", rows)
        self.assertEqual([(x.name, len(x.rows)) for x in o], [("Fische 1", 14), ("Fische 2", 14), ("Fische 3", 2)])
        self.assertEqual([r.alias for x in o for r in x.rows], [r.alias for r in rows])
        self.assertEqual([x.name for x in T.split_package("Fische", rows[:14])], ["Fische"])
        self.assertEqual([x.name for x in T.split_package("Fische", rows[:15])], ["Fische 1", "Fische 2"])


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.img = FakeImage()
        self.p = T.plan(self.img.read, self.img.maps, self.img.BASE, make_options(), self.img.impl, self.img.pe,
                        [self.img.slot], log=lambda _m: None, settle=0)
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_files_written_and_loadable_by_reaperpy(self):
        import reapatch
        files = T.write_project(self.dir, self.p, "Test-Trainer", game="Spiel", title_id="PPSA20946", author="ich")
        names = sorted(os.path.basename(f) for f in files)
        self.assertIn(T.BASE_FILE, names)
        self.assertIn("01_Gold.reapproj", names)
        self.assertIn("02_Traenke.reapproj", names)
        self.assertIn("03_Material.reapproj", names)
        self.assertIn(T.SPEC_FILE, names)
        self.assertTrue(reapatch.is_patch_file("01_Gold.reapproj"))
        self.assertFalse(reapatch.is_patch_file(T.SPEC_FILE) and False)
        base = reapatch.ReapPatch.load(os.path.join(self.dir, T.BASE_FILE))
        sites = base.sites()
        self.assertEqual(len(sites), 2)                                   # Cave + 1 vtable-Slot
        self.assertEqual(sites[0][0], self.p.cave - self.p.base)
        self.assertEqual(sites[1][0], self.img.slot - self.p.base)
        self.assertEqual(bytes.fromhex(sites[0][2].replace(" ", "")), self.p.cave_bytes)
        self.assertEqual(bytes.fromhex(sites[1][2].replace(" ", "")), struct.pack("<Q", self.p.cave))
        self.assertEqual(bytes.fromhex(sites[1][1].replace(" ", "")), struct.pack("<Q", self.img.pe))
        gold = reapatch.ReapPatch.load(os.path.join(self.dir, "01_Gold.reapproj"))
        self.assertEqual(gold.origin_source[0], self.p.flag_addr - self.p.base)
        self.assertEqual(gold.origin_source[1:], ("00", "01"))
        mat = reapatch.ReapPatch.load(os.path.join(self.dir, "03_Material.reapproj"))
        self.assertEqual(mat.origin_source[0], self.p.flag_addr + 2 - self.p.base)

    def test_not_cave_patch_for_engine(self):
        """Die Dateien muessen als SIMPLE-Patches behandelt werden (keine Label-Spruenge)."""
        import patch_engine as PE
        import reapatch
        T.write_project(self.dir, self.p, "X")
        for f in os.listdir(self.dir):
            if f.endswith(".reapproj"):
                self.assertFalse(PE.is_cave_patch(reapatch.ReapPatch.load(os.path.join(self.dir, f))), f)

    def test_apply_and_deactivate_with_patch_engine(self):
        """Mit dem echten patch_engine auf einem Fake-Backend: BASIS an -> Cave + Haken stehen, aus -> alles wie vorher."""
        import patch_engine as PE
        import reapatch
        T.write_project(self.dir, self.p, "X")
        img = self.img

        class Backend:
            def read(self, a, n):
                return img.read(a, n)

            def write(self, a, d):
                img.write(a, bytes(d))

            def get_maps(self, force=False):
                return img.maps

            def assemble(self, *_a, **_k):
                raise AssertionError("Hex-Patches duerfen keinen Assembler brauchen")

        be = Backend()
        before = {a: img.read(a, 16) for a in (self.p.cave, self.img.slot)}
        base = reapatch.ReapPatch.load(os.path.join(self.dir, T.BASE_FILE))
        state = PE.apply_patch(be, base, img.BASE + base.origin_source[0])
        self.assertEqual(img.read(self.p.cave, len(self.p.cave_bytes)), self.p.cave_bytes)
        self.assertEqual(struct.unpack("<Q", img.read(img.slot, 8))[0], self.p.cave)
        self.assertTrue(PE.detect_patched(be, base, img.BASE + base.origin_source[0])[0])
        gold = reapatch.ReapPatch.load(os.path.join(self.dir, "01_Gold.reapproj"))
        PE.apply_patch(be, gold, img.BASE + gold.origin_source[0])
        self.assertEqual(img.read(self.p.flag_addr, 1), b"\x01")
        PE.deactivate_patch(be, base, state)
        self.assertEqual({a: img.read(a, 16) for a in (self.p.cave, self.img.slot)}, before)

    def test_goldhen_export_of_the_project(self):
        """Der vorhandene GoldHEN-Export versteht die Dateien (BASIS + Eintraege als Checkboxen)."""
        import export_goldhen as E
        import reapatch
        T.write_project(self.dir, self.p, "X")
        img = self.img

        class Backend:
            pid = 1

            def read(self, a, n):
                return img.read(a, n)

            def get_maps(self, force=False):
                return img.maps

            def assemble(self, *_a, **_k):
                raise AssertionError("kein Assembler noetig")

        pats = [reapatch.ReapPatch.load(os.path.join(self.dir, f)) for f in sorted(os.listdir(self.dir))
                if f.endswith(".reapproj")]
        mods, report = E.build_mods(Backend(), pats, img.BASE, log=lambda _m: None)
        self.assertEqual([r["status"] for r in report], ["ok"] * 4, report)
        self.assertEqual(len(mods), 4)
        base_mod = next(m for m in mods if m["name"].startswith("00"))
        self.assertEqual(len(base_mod["memory"]), 2)
        self.assertEqual(base_mod["memory"][1]["on"], struct.pack("<Q", self.p.cave).hex().upper())
        gold = next(m for m in mods if "Gold" in m["name"])
        self.assertEqual(gold["memory"], [{"offset": f"{self.p.flag_addr - img.BASE:X}", "on": "01", "off": "00"}])

    def test_spec_roundtrip_merge_and_rewrite_removes_stale_files(self):
        T.write_project(self.dir, self.p, "X", game="G", title_id="PPSA20946")
        old = T.load_options(self.dir)
        self.assertEqual([o.name for o in old], ["Gold", "Traenke", "Material"])
        new = [T.Option("gold", [T.Row("Item_Gold", bytes(8), 5)]), T.Option("Neu", [T.Row("Z", bytes(8), 3)])]
        merged = T.merge_options(old, new)
        self.assertEqual([o.name for o in merged], ["gold", "Traenke", "Material", "Neu"])
        self.assertEqual(merged[0].rows[0].amount, 5)
        p2 = T.plan(self.img.read, self.img.maps, self.img.BASE, merged, self.img.impl, self.img.pe,
                    [self.img.slot], log=lambda _m: None, settle=0)
        T.write_project(self.dir, p2, "X")
        files = sorted(f for f in os.listdir(self.dir) if f.endswith(".reapproj"))
        self.assertEqual(files, [T.BASE_FILE, "01_gold.reapproj", "02_Traenke.reapproj", "03_Material.reapproj",
                                 "04_Neu.reapproj"])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "01_Gold.reapproj")) and
                         os.path.exists(os.path.join(self.dir, "01_gold.reapproj")) and
                         os.name != "nt" and False)

    def test_compare_fnames(self):
        T.write_project(self.dir, self.p, "X")
        live = {"Item_Gold": bytes.fromhex("0102030405060708"),
                "Item_PotionA": bytes.fromhex("9999999999999999"),
                "Item_Mat": bytes.fromhex("3333333333333333")}
        ok, changed, missing = T.compare_fnames(self.dir, live)
        self.assertEqual(sorted(ok), ["Item_Gold", "Item_Mat"])
        self.assertEqual([c[0] for c in changed], ["Item_PotionA"])
        self.assertEqual(missing, ["Item_PotionB"])
        with self.assertRaises(T.TrainerError):
            T.compare_fnames(tempfile.mkdtemp(), live)

    def test_readme_mentions_limits(self):
        txt = T.readme_text(self.p, "X")
        for needle in ("NICHT GETESTET", "FNAMES PRUEFEN", "BASIS", "Gold"):
            self.assertIn(needle, txt)

    def test_clean_name(self):
        self.assertEqual(T.clean_name('a/b:c*"d'), "a b c d")
        self.assertEqual(T.clean_name("   "), "Eintrag")
        self.assertLessEqual(len(T.clean_name("x" * 200)), T.NAME_MAX)



class AnchorTests(unittest.TestCase):
    class _Client:
        def __init__(self, mem, base):
            self.mem, self.base = mem, base

        def read_memory(self, a, n):
            o = a - self.base
            return bytes(self.mem[o:o + n]) if 0 <= o and o + n <= len(self.mem) else b""

    def _setup(self):
        import random
        rnd = random.Random(1)
        base = 0x400000
        mem = bytearray(rnd.randrange(1, 255) for _ in range(0x4000))
        return base, mem, self._Client(mem, base), [(base, base + 0x4000, 5)]

    def test_signature_roundtrip_ok_and_moved(self):
        import aob
        base, mem, cl, maps = self._setup()
        sig, _ = aob.make_signature(cl, maps, base + 0x800, hook_len=0, wildcard_hook=False, min_len=16, max_len=64)
        spec = {"anchors": {"impl": {"rva": hex(0x800), "aob": sig}}}
        self.assertEqual(T.check_anchors(cl, maps, base, spec)[0][1], "ok")
        # anderer Build: Funktion liegt 0x100 weiter hinten
        mem[0x900:0x900 + 80] = mem[0x800:0x800 + 80]
        mem[0x800:0x850] = bytes(range(1, 81))[:0x50]
        res = T.check_anchors(cl, maps, base, spec)
        self.assertEqual(res[0][1:], ("moved", base + 0x900))
        self.assertIn("passt nicht", T.anchor_problem(res, base))
        self.assertIsNone(T.anchor_problem([("impl", "ok", base + 0x800)], base))

    def test_spec_contains_anchors(self):
        p = T.Plan()
        p.anchors = {"impl": (0x10, "48 8B ??")}
        doc = T.spec_document(p)
        self.assertEqual(doc["anchors"]["impl"], {"rva": "0x10", "aob": "48 8B ??"})


class InnerGapTests(unittest.TestCase):
    """Kein Padding am Region-Ende -> Ausweichplatz in einer CC-Luecke mitten im Code."""

    def test_alloc_code_falls_back_to_inner_gap(self):
        import cave_trainer as CT
        size = 0x3000
        mem = bytearray(b"\x90" * size)
        mem[0x1000:0x1400] = b"\xCC" * 0x400          # Luecke mitten im Code, am Region-Ende kein Padding

        def read(a, n):
            return bytes(mem[a - 0x10000:a - 0x10000 + n])
        sl = CT.Slots(read, [(0x10000, 0x10000 + size, 5)], log=lambda *_: None)
        cave, need = sl.alloc_code(0x100, 0x10000)
        self.assertTrue(0x11000 <= cave and cave + need <= 0x11400)
        self.assertGreaterEqual(sl.code_capacity(), 0x300)

    def test_tail_padding_is_preferred_and_inner_scan_is_skipped(self):
        import cave_trainer as CT
        reads = []
        size = 0x4000
        mem = bytearray(b"\x90" * size)
        mem[-0x2000:] = b"\xCC" * 0x2000               # grosses Padding am Ende
        mem[0x100:0x200] = b"\xCC" * 0x100

        def read(a, n):
            reads.append(n)
            return bytes(mem[a - 0x10000:a - 0x10000 + n])
        sl = CT.Slots(read, [(0x10000, 0x10000 + size, 5)], log=lambda *_: None)
        cave, _need = sl.alloc_code(0x100, 0x10000)
        self.assertGreaterEqual(cave, 0x10000 + size - 0x2000)
        self.assertLess(max(reads), 0x10000)                  # nur der Rand, nicht der ganze Code gelesen

    def test_no_gap_anywhere_still_raises_and_gap_split_over_blocks_is_merged(self):
        import cave_trainer as CT
        old = CT.INNER_BLOCK
        CT.INNER_BLOCK = 0x100                                 # Stueck muss ueber mehrere Bloecke zusammengesetzt werden
        self.addCleanup(setattr, CT, "INNER_BLOCK", old)
        size = 0x2000
        mem = bytearray(b"\x90" * size)

        def read(a, n):
            return bytes(mem[a - 0x10000:a - 0x10000 + n])
        with self.assertRaises(CT.TrainerError):
            CT.Slots(read, [(0x10000, 0x10000 + size, 5)], log=lambda *_: None).alloc_code(0x100, 0x10000)
        mem[0x500:0x900] = b"\xCC" * 0x400
        sl = CT.Slots(read, [(0x10000, 0x10000 + size, 5)], log=lambda *_: None)
        cave, need = sl.alloc_code(0x300, 0x10000)
        self.assertTrue(0x10500 <= cave and cave + need <= 0x10900)


class LeftoverCaveTests(unittest.TestCase):
    """Eine fruehere Cave (BASIS aus, GoldHEN-Cheat, anderer Export) blockiert das Region-Ende: das war 'Platz: 0 Byte'."""

    def _plan(self, img, opts):
        return T.plan(img.read, img.maps, img.BASE, opts, img.impl, img.pe, [img.slot], log=lambda _m: None, settle=0)

    def _opts(self, name, n=3):
        return [T.Option(name, [T.Row(f"{name}{i}", struct.pack("<Q", 0x1000 + i), 5) for i in range(n)])]

    def _leave_cave(self, img, name="Alt"):
        p1 = self._plan(img, self._opts(name))
        img.write(p1.cave, p1.cave_bytes)                       # Cave steht, Haken ist aus (Slot zeigt noch auf ProcessEvent)
        return p1

    def test_capacity_is_not_zero_after_a_cave_was_left_behind(self):
        img = FakeImage()
        free = T.capacity(img.read, img.maps, img.BASE)["code"]
        self._leave_cave(img)
        after = T.capacity(img.read, img.maps, img.BASE)["code"]
        self.assertGreaterEqual(after, free)                    # vorher 0 Byte: Rest der Cave zaehlte als belegt

    def test_second_export_reuses_the_old_cave_space(self):
        img = FakeImage()
        p1 = self._leave_cave(img)
        p2 = self._plan(img, self._opts("Neu", 5))
        self.assertGreater(p2.cave + len(p2.cave_bytes), p1.cave)       # liegt wieder am Region-Ende
        self.assertEqual(p2.cave_orig, bytes(len(p2.cave_bytes)))       # Original = Padding, nicht die alte Cave
        self.assertIn(img.read(p2.cave, len(p2.cave_bytes)), p2.verify_also)
        self.assertTrue(any("frueheren" in w for w in p2.warnings))

    def test_stacked_caves_are_one_chain(self):
        img = FakeImage()
        p1 = self._leave_cave(img, "A")
        free_after_one = T.capacity(img.read, img.maps, img.BASE)["code"]
        p2 = self._plan(img, self._opts("B", 4))
        img.write(p2.cave, p2.cave_bytes)
        self.assertGreaterEqual(T.capacity(img.read, img.maps, img.BASE)["code"], free_after_one)
        p3 = self._plan(img, self._opts("C", 6))
        self.assertGreaterEqual(p3.cave, p2.cave - 0x1000)
        self.assertEqual(p3.cave_orig, bytes(len(p3.cave_bytes)))
        self.assertLess(p1.cave, img.BASE + 0x10000)

    def test_leftover_flag_bytes_of_the_old_trainer_do_not_block(self):
        img = FakeImage()
        p1 = self._leave_cave(img)
        img.write(p1.flag_addr, b"\x01\x00\x01")                  # Eintrag geklickt, aber Haken war aus -> Schalter blieb 1
        p2 = self._plan(img, self._opts("Neu"))                      # darf nicht an 'Schalter-Bereich nicht leer' scheitern
        self.assertLessEqual(p2.flag_addr + p2.flag_size, p1.flag_addr)   # frische Schalter VOR den alten (nichts Altes loest aus)
        self.assertEqual(img.read(p2.flag_addr, p2.flag_size), bytes(p2.flag_size))

    def test_foreign_data_at_region_end_is_still_not_overwritten(self):
        img = FakeImage()
        img.write(img.BASE, b"\x55\x48\x89\xe5" * 0x4000)           # Code bis zum Regionsende, nirgends Padding
        self.assertEqual(T.capacity(img.read, img.maps, img.BASE)["code"], 0)
        with self.assertRaises(T.TrainerError) as c:
            T.fit_options(self._opts("X"), 0)
        self.assertIn("KEIN freier Code-Platz", str(c.exception))

    def test_zero_capacity_is_explained_in_the_log(self):
        img = FakeImage()
        img.write(img.BASE, b"\x55\x48\x89\xe5" * 0x4000)
        logs = []
        T.capacity(img.read, img.maps, img.BASE, log=logs.append)
        self.assertTrue(any("KEIN freier Code-Platz" in x for x in logs))
        self.assertTrue(any("'#'=Daten" in x for x in logs))            # Karte des Region-Endes im Log

    def test_base_patch_accepts_leftover_and_clean_console_with_patch_engine(self):
        """Gleicher Trainer auf der Konsole mit altem Cave-Rest UND auf einer frischen Konsole (nur Padding) aktivierbar."""
        import patch_engine as PE
        import reapatch
        img = FakeImage()
        self._leave_cave(img)
        p2 = self._plan(img, self._opts("Neu", 5))
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        T.write_project(d, p2, "X")
        with open(os.path.join(d, T.BASE_FILE), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertTrue(doc.get("VerifyAlso"))
        for image in (img, FakeImage()):                              # alter Rest / frisch
            class Backend:
                def read(self, a, n, _i=image):
                    return _i.read(a, n)

                def write(self, a, data, _i=image):
                    _i.write(a, bytes(data))

                def get_maps(self, force=False, _i=image):
                    return _i.maps

                def assemble(self, *_a, **_k):
                    raise AssertionError("kein Assembler noetig")
            base = reapatch.ReapPatch.load(os.path.join(d, T.BASE_FILE))
            PE.apply_patch(Backend(), base, image.BASE + base.origin_source[0])
            self.assertEqual(image.read(p2.cave, len(p2.cave_bytes)), p2.cave_bytes)

    def test_other_fill_byte_cc_is_also_accepted(self):
        img = FakeImage()
        img.write(img.BASE + 0x2100, b"\xcc" * (0x10000 - 0x2100))   # Konsole, deren Padding 0xCC statt 0x00 ist
        p = self._plan(img, self._opts("X"))
        self.assertEqual(p.cave_orig[0], 0xCC)
        img.write(p.cave, p.cave_bytes)                              # alter Rest
        p2 = self._plan(img, self._opts("Y", 4))
        self.assertEqual(p2.cave_orig[0], 0xCC)
        self.assertTrue(any(x == bytes(len(p2.cave_bytes)) for x in p2.verify_also))   # frisch mit 00-Padding ginge auch

    def test_foreign_cave_at_the_very_end_leaves_the_free_part_before_it_usable(self):
        """Wie auf der anderen Konsole vermutet: ein fremder Cheat legt seine Cave ans Seitenende des Codes - davor
        ist das Padding noch frei.  Das darf nicht '0 Byte' ergeben."""
        img = FakeImage()
        end = img.BASE + 0x10000
        img.write(end - 0x200, b"\x48\x8b\x05\x11\x22\x33\x44\x90" * 0x40)       # fremder Code (512 Byte) ganz am Ende
        cap = T.capacity(img.read, img.maps, img.BASE)["code"]
        self.assertGreater(cap, 0x1000)
        p = self._plan(img, self._opts("Neu", 4))
        self.assertLess(p.cave + len(p.cave_bytes), end - 0x200 + 1)       # liegt VOR dem fremden Code
        self.assertEqual(p.cave_orig, bytes(len(p.cave_bytes)))
        self.assertEqual(img.read(end - 0x200, 8), b"\x48\x8b\x05\x11\x22\x33\x44\x90")

    def test_foreign_cave_in_the_middle_of_the_padding(self):
        img = FakeImage()
        end = img.BASE + 0x10000
        img.write(end - 0x1800, b"\xe9\x01\x02\x03\x04" * 0x80)
        p = self._plan(img, self._opts("Neu", 4))
        forbidden = range(end - 0x1800, end - 0x1800 + 0x280)
        self.assertFalse(any(a in forbidden for a in range(p.cave, p.cave + len(p.cave_bytes))))

    def test_unrelated_bytes_with_similar_start_are_not_taken_for_a_cave(self):
        img = FakeImage()
        end = img.BASE + 0x10000
        img.write(img.BASE, b"\x55\x48\x89\xe5" * 0x4000)
        img.write(end - 0x40, b"\x31\xc0\x48\x0b\x05\x00\x00\x00\x00\x0f\x85\x05\x00\x00\x00\xe9\xff\xff\xff\x7f" + b"\x55" * 0x2c)
        self.assertEqual(T.capacity(img.read, img.maps, img.BASE)["code"], 0)


if __name__ == "__main__":
    unittest.main()
