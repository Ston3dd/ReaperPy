"""Tests fuer ue_cavegen: allgemeine Funktionsaufruf-Caves.  Die Cave wird auf einem echten x86-64-Prozessor ausgefuehrt
(mmap + ctypes, wie tests/test_cave_trainer.py); ohne Linux/x86-64/binutils werden diese Tests uebersprungen."""
import ctypes
import mmap
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import cave_trainer as T
import test_cave_trainer as TS
import ue_cavegen as C
import uesdk

NATIVE = TS.NATIVE
CAVE_OFF, FLAG_OFF, SIZE = 0x1000, 0x3000, 0x5000
LOG_OFF, PE_BUF, DRV_BUF = 0x0800, 0x0F00, 0x0F80
OBJ_OFF, OBJ2_OFF = 0x4000, 0x4100            # gehooktes Objekt / sein Member-Ziel

HELPERS = TS.HELPERS.replace(
    """rec_fn:
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
""", """rec_fn:
  mov rax, [rip+logcnt]
  lea r10, [rip+logbuf]
  imul r11, rax, 80
  add r10, r11
  mov [r10], rdi
  mov [r10+8], rsi
  mov [r10+16], rdx
  mov [r10+24], rcx
  mov [r10+32], r8
  mov [r10+40], rsp
  mov [r10+48], r9
  movq QWORD PTR [r10+56], xmm0
  movq QWORD PTR [r10+64], xmm1
""")
assert HELPERS != TS.HELPERS


class Sdk:
    enums = {}


def spec(args, this="zero", off=0, impl_rva=0):
    return C.CallSpec(impl_rva, args, this, off)


def arg(name, kind, value, size=4, signed=False, mode="val"):
    return {"name": name, "kind": kind, "size": size, "signed": signed, "value": value, "mode": mode}


@unittest.skipUnless(NATIVE, "braucht Linux x86-64, as, ld, objcopy")
class NativeCalls(unittest.TestCase):
    def setUp(self):
        self.mm = mmap.mmap(-1, SIZE, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
        self.base = ctypes.addressof(ctypes.c_char.from_buffer(self.mm))
        self.tmp = tempfile.mkdtemp()
        help_bin = TS.build_helpers(self.tmp, CAVE_OFF)
        # eigene Hilfsdatei mit 80-Byte-Log
        src = os.path.join(self.tmp, "h2.s")
        with open(src, "w") as f:
            f.write(HELPERS.replace("call CAVE", f"call {CAVE_OFF}"))
        obj, elf, binf = (os.path.join(self.tmp, n) for n in ("h2.o", "h2.elf", "h2.bin"))
        subprocess.run(["as", "--64", "-o", obj, src], check=True)
        subprocess.run(["ld", "-Ttext=0", "-e", "0", "-o", elf, obj], check=True)
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text", elf, binf], check=True)
        with open(binf, "rb") as f:
            hb = f.read()
        self.mm[0:len(hb)] = hb
        self.driver = ctypes.CFUNCTYPE(ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64)(self.base + 0x200)

    def tearDown(self):
        del self.driver
        try:
            self.mm.close()
        except BufferError:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self, options):
        # impl = rec_fn bei mmap+0 (RVA relativ zu 'base' = mmap-Adresse)
        code = T.build_cave(self.base + CAVE_OFF, self.base + FLAG_OFF, self.base + 0x100, self.base, options, self.base)
        self.mm[CAVE_OFF:CAVE_OFF + len(code)] = code
        return code

    def calls(self):
        n = struct.unpack("<Q", self.mm[LOG_OFF:LOG_OFF + 8])[0]
        return [struct.unpack("<10Q", self.mm[LOG_OFF + 8 + 80 * k:LOG_OFF + 88 + 80 * k]) for k in range(n)]

    def fire(self, idx=0, rdi=0x1111, rsi=0x2222, rdx=0x3333):
        self.mm[FLAG_OFF + idx] = 1
        return self.driver(rdi, rsi, rdx)

    def opt(self, name, *specs):
        return T.Option(name, [C.CallRow(f"{name}{i}", s, None, 1) for i, s in enumerate(specs)])

    # ---- Register ------------------------------------------------------------------------------
    def test_item_call_registers(self):
        fn = bytes.fromhex("0a0b0c0d01000000")
        sp = spec([arg("ItemName", "fname", fn, 8), arg("Count", "int", 999, 4, True), arg("Level", "int", 1, 4),
                   arg("bNotify", "int", 0, 1)])
        self.install([self.opt("A", sp)])
        self.assertEqual(self.fire(), 77)
        (rdi, rsi, rdx, rcx, r8, rsp, r9, _x0, _x1, _p), = self.calls()
        self.assertEqual((rdi, rsi, rdx, rcx, r8), (0, struct.unpack("<Q", fn)[0], 999, 1, 0))
        self.assertEqual(rsp % 16, 8)
        self.assertEqual(self.mm[FLAG_OFF], 0)
        pe = struct.unpack("<4Q", self.mm[PE_BUF:PE_BUF + 32])
        self.assertEqual(pe[:3], (0x1111, 0x2222, 0x3333))

    def test_negative_and_64bit_and_five_int_args(self):
        sp = spec([arg("a", "int", -5, 4, True), arg("b", "int", 0x1122334455667788, 8), arg("c", "int", 7, 2),
                   arg("d", "ptr", 0xDEAD0000BEEF, 8), arg("e", "enum", 3, 1)])
        self.install([self.opt("A", sp)])
        self.fire()
        (rdi, rsi, rdx, rcx, r8, _rsp, r9, *_), = self.calls()
        self.assertEqual((rsi, rdx, rcx, r8, r9), (0xFFFFFFFB, 0x1122334455667788, 7, 0xDEAD0000BEEF, 3))

    def test_floats_and_doubles_go_to_xmm_in_order(self):
        sp = spec([arg("n", "int", 5, 4), arg("f", "float", 1.5, 4, True), arg("d", "double", -2.25, 8, True)])
        self.install([self.opt("A", sp)])
        self.fire()
        (rdi, rsi, *_rest), = self.calls()
        c = self.calls()[0]
        self.assertEqual(c[1], 5)
        self.assertEqual(struct.unpack("<f", struct.pack("<Q", c[7])[:4])[0], 1.5)       # xmm0 (float)
        self.assertEqual(struct.unpack("<d", struct.pack("<Q", c[8]))[0], -2.25)        # xmm1 (double)

    def test_byref_fname_points_into_cave_pool(self):
        fn = bytes.fromhex("1122334455667788")
        sp = spec([arg("ItemName", "fname", fn, 8, mode="ref"), arg("Count", "int", 3, 4)])
        code = self.install([self.opt("A", sp)])
        self.fire()
        c = self.calls()[0]
        ptr = c[1]
        self.assertTrue(self.base + CAVE_OFF <= ptr < self.base + CAVE_OFF + len(code))
        self.assertEqual(ptr % 8, 0)
        self.assertEqual(self.mm[ptr - self.base:ptr - self.base + 8], fn)
        self.assertEqual(c[2], 3)

    # ---- this -------------------------------------------------------------------------------------
    def test_this_hooked_survives_several_calls(self):
        a, b = spec([arg("n", "int", 1)], "hooked"), spec([arg("n", "int", 2)], "hooked")
        self.install([self.opt("A", a, b)])
        self.fire(rdi=0xABCDEF)
        cs = self.calls()
        self.assertEqual([(c[0], c[1]) for c in cs], [(0xABCDEF, 1), (0xABCDEF, 2)])     # rdi wird je Aufruf neu geladen

    def test_this_member_and_null_member_skips(self):
        obj, tgt = self.base + OBJ_OFF, self.base + OBJ2_OFF
        struct.pack_into("<Q", self.mm, OBJ_OFF + 0x20, tgt)
        sp = spec([arg("n", "int", 9)], "member", 0x20)
        self.install([self.opt("A", sp), self.opt("B", spec([arg("n", "int", 4)]))])
        self.fire(0, rdi=obj)
        self.assertEqual([(c[0], c[1]) for c in self.calls()], [(tgt, 9)])
        struct.pack_into("<Q", self.mm, OBJ_OFF + 0x20, 0)
        ctypes.memset(self.base + LOG_OFF, 0, 8)
        self.assertEqual(self.fire(0, rdi=obj), 77)                        # Member 0 -> kein Aufruf, ProcessEvent laeuft weiter
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.mm[FLAG_OFF], 0)
        self.fire(1, rdi=obj)                                              # naechster Eintrag funktioniert weiter
        self.assertEqual([c[1] for c in self.calls()], [4])

    def test_mixed_stellar_blade_row_and_call_row(self):
        sb = T.Row("Item_Gold", bytes.fromhex("0a00000000000000"), 77)
        cr = C.CallRow("x", spec([arg("n", "int", 5)]), None, 1)
        self.install([T.Option("Mix", [sb, cr])])
        self.fire()
        cs = self.calls()
        self.assertEqual((cs[0][1], cs[0][2], cs[0][3]), (0x0a, 77, 1))     # SB-Form (rsi=FName, edx=Menge, ecx=1)
        self.assertEqual((cs[1][1]), 5)

    def test_idle_still_forwards(self):
        self.install([self.opt("A", spec([arg("n", "int", 1)]))])
        self.assertEqual(self.driver(0x9, 0x8, 0x7), 77)
        self.assertEqual(self.calls(), [])


# ----------------------------------------------------------------------------------------------
# Ohne Prozessor
# ----------------------------------------------------------------------------------------------
class Logic(unittest.TestCase):
    def test_classify_roles(self):
        got = C.classify_params([("class FName", "ItemName"), ("int32", "Count"), ("float", "Scale"), ("bool", "bNotify"),
                                 ("class UObject*", "Ctx"), ("int32", "ItemID")])
        self.assertEqual([(a["name"], a["kind"], a["role"]) for a in got],
                         [("ItemName", "fname", "id"), ("Count", "int", "count"), ("Scale", "float", "other"),
                          ("bNotify", "int", "other"), ("Ctx", "ptr", "other"), ("ItemID", "int", "id")])
        self.assertEqual([a["size"] for a in got], [8, 4, 4, 1, 8, 4])
        self.assertEqual(C.classify_params([("enum EKind", "Kind")])[0]["kind"], "enum")

    def test_unsupported_things_fail_loudly(self):
        with self.assertRaises(T.TrainerError) as c:
            C.classify_params([("int32&", "OutValue")])
        self.assertIn("Out-Parameter", str(c.exception))
        with self.assertRaises(T.TrainerError):
            C.classify_params([("struct FVector", "Pos")])
        with self.assertRaises(T.TrainerError):
            C.classify_params([("class FString", "Code")])
        with self.assertRaises(T.TrainerError) as c:
            C.classify_params([("int32", f"a{i}") for i in range(6)])
        self.assertIn("Stack", str(c.exception))
        with self.assertRaises(T.TrainerError):
            C.classify_params([("float", f"f{i}") for i in range(9)])
        with self.assertRaises(T.TrainerError):
            C.check_return("struct FItemResult")
        C.check_return("void"); C.check_return("bool"); C.check_return("")

    def test_const_ref_is_allowed(self):
        got = C.classify_params([("const class FName&", "ItemName")])
        self.assertTrue(got[0]["ref"])

    def test_choose_this(self):
        sdk = uesdk.parse_header_text(
            "class AController : public AActor\n{\npublic:\n};\n"
            "class APlayerController : public AController\n{\npublic:\n\tclass UCheatManager*  CheatManager;   // 0x03D8 (0x0008) [0x0] ObjectProperty\n};\n"
            "class UMyCheatManager : public UCheatManager\n{\npublic:\n};\n"
            "class UInventoryComponent : public UActorComponent\n{\npublic:\n};\n")
        self.assertEqual(C.choose_this(sdk, "AController")[:2], ("hooked", 0))
        self.assertEqual(C.choose_this(sdk, "APlayerController")[:2], ("hooked", 0))
        m = C.choose_this(sdk, "UCheatManager")
        self.assertEqual(m[:2], ("member", 0x3D8))
        z = C.choose_this(sdk, "UInventoryComponent")
        self.assertEqual(z[0], "zero")
        self.assertIn("Absturz", z[2])
        self.assertEqual(C.choose_this(sdk, "UInventoryComponent", static=True)[0], "zero")

    def test_build_row_fills_roles_extra_and_validates(self):
        params = [("class FName", "ItemName"), ("int32", "Count"), ("int32", "Level"), ("bool", "bNotify")]
        fn = bytes.fromhex("0102030405060708")
        row = C.build_row("Gold", 0x1234, params, "void", Sdk(), ("hooked", 0), id_value=fn, count_value=999,
                          extra={"Level": 2, "bNotify": 1}, function="UCheat.AddItem")
        self.assertEqual([(a["name"], a["value"]) for a in row.spec.args],
                         [("ItemName", fn), ("Count", 999), ("Level", 2), ("bNotify", 1)])
        self.assertEqual((row.fname, row.amount, row.call_impl_rva), (fn, 999, 0x1234))
        with self.assertRaises(T.TrainerError):
            C.build_row("x", 1, params, "void", Sdk(), ("zero", 0), id_value=None, count_value=1)       # FName fehlt
        with self.assertRaises(T.TrainerError):
            C.build_row("x", 1, [("uint8", "Small")], "void", Sdk(), ("zero", 0), extra={"Small": 300})
        with self.assertRaises(T.TrainerError):
            C.CallSpec(1, [], "sideways")
        with self.assertRaises(T.TrainerError):
            C.CallSpec(1, [{"name": "n", "kind": "fname", "size": 8, "value": b"123"}])

    def test_json_roundtrip_and_compare_fnames(self):
        fn = bytes.fromhex("0a0b0c0d0e0f1011")
        r1 = C.build_row("Gold", 0x10, [("class FName", "N"), ("int32", "Count")], "void", Sdk(), ("member", 0x3D8),
                         id_value=fn, count_value=50)
        r2 = C.build_row("XP", 0x20, [("int32", "Amount")], "void", Sdk(), ("hooked", 0), count_value=500)
        opts = [T.Option("Gold", [r1]), T.Option("XP", [r2])]
        doc = [o.to_json() for o in opts]
        back = [T.Option.from_json(d) for d in doc]
        self.assertIsInstance(back[0].rows[0], C.CallRow)
        self.assertEqual(back[0].rows[0].spec.this_mode, "member")
        self.assertEqual(back[0].rows[0].spec.this_off, 0x3D8)
        self.assertEqual(back[0].rows[0].spec.args[0]["value"], fn)
        self.assertIsNone(back[1].rows[0].fname)
        import json
        json.dumps(doc)
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        img = TS.FakeImage()
        p = T.plan(img.read, img.maps, img.BASE, back, None, img.pe, [img.slot], log=lambda _m: None, settle=0)
        T.write_project(d, p, "X")
        ok, changed, missing = T.compare_fnames(d, {"Gold": fn})
        self.assertEqual((ok, changed, missing), (["Gold"], [], []))                 # XP hat keinen FName -> wird uebersprungen

    def test_plan_with_only_call_rows_checks_function_in_image(self):
        img = TS.FakeImage()
        good = C.build_row("A", img.impl - img.BASE, [("int32", "Amount")], "void", Sdk(), ("zero", 0), count_value=5)
        bad = C.build_row("B", 0x7000000100 - img.BASE, [("int32", "Amount")], "void", Sdk(), ("zero", 0), count_value=5)
        p = T.plan(img.read, img.maps, img.BASE, [T.Option("A", [good])], None, img.pe, [img.slot], log=lambda _m: None, settle=0)
        self.assertEqual(p.impl, img.impl)
        with self.assertRaises(T.TrainerError) as c:
            T.plan(img.read, img.maps, img.BASE, [T.Option("B", [bad])], None, img.pe, [img.slot], log=lambda _m: None, settle=0)
        self.assertIn("nicht im Spiel-Image", str(c.exception))
        with self.assertRaises(T.TrainerError):
            T.plan(img.read, img.maps, img.BASE, TS.make_options(), None, img.pe, [img.slot], log=lambda _m: None, settle=0)

    def test_cave_size_matches_for_pools(self):
        row = C.build_row("A", 0x100, [("class FName", "N")], "void", Sdk(), ("zero", 0), id_value=bytes(range(1, 9)),
                          byref=["N"])
        o = [T.Option("A", [row])]
        self.assertEqual(T.cave_size(o), len(T.build_cave(0x1000, 0x2000, 0x3000, 0, o, 0x400000)))


if __name__ == "__main__":
    unittest.main()
