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
        TS.build_helpers(self.tmp, CAVE_OFF)
        # eigene Hilfsdatei mit 80-Byte-Log
        src = os.path.join(self.tmp, "h2.s")
        with open(src, "w", encoding="utf-8") as f:
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

    def test_this_abs_calls_only_while_the_object_is_still_there(self):
        """Feste Objektadresse (Subsystem): Aufruf nur, wenn dort noch die erwartete vtable steht - sonst uebersprungen."""
        tgt = self.base + OBJ2_OFF
        struct.pack_into("<Q", self.mm, OBJ2_OFF, 0xBEEF0001)                    # 'vtable' des Objekts
        sp = C.CallSpec(0, [arg("n", "int", 7)], "abs", 0, "", None, tgt, 0xBEEF0001)
        self.install([self.opt("A", sp), self.opt("B", spec([arg("n", "int", 4)]))])
        self.assertEqual(self.fire(0, rdi=0x1234), 77)
        self.assertEqual([(c[0], c[1]) for c in self.calls()], [(tgt, 7)])           # this = die feste Adresse
        struct.pack_into("<Q", self.mm, OBJ2_OFF, 0x1111)                           # Spiel neu gestartet: anderes Objekt dort
        ctypes.memset(self.base + LOG_OFF, 0, 8)
        self.assertEqual(self.fire(0, rdi=0x1234), 77)                              # ProcessEvent laeuft trotzdem weiter
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.mm[FLAG_OFF], 0)
        self.fire(1)                                                                # naechster Eintrag funktioniert weiter
        self.assertEqual([c[1] for c in self.calls()], [4])

    def test_many_rows_of_one_entry_all_run_in_the_real_item_call_shape(self):
        """Wie ein Trainer-Eintrag fuer AddItemToWarehouse(FName ItemId, int32 Add, FName WorkId): 14 Zeilen, jede mit anderem Item,
        feste Objektadresse - JEDE Zeile muss laufen, mit ihrem Item und ihrer Menge."""
        tgt = self.base + OBJ2_OFF
        struct.pack_into("<Q", self.mm, OBJ2_OFF, 0xBEEF0001)
        specs = []
        for k in range(14):
            fn = struct.pack("<II", 0x100 + k, 0)
            specs.append(C.CallSpec(0, [arg("ItemId", "fname", fn, 8), arg("Add", "int", 99, 4, True),
                                        arg("WorkId", "fname", bytes(8), 8)], "abs", 0, "", None, tgt, 0xBEEF0001))
        self.install([self.opt("A", *specs)])
        self.fire(0)
        got = self.calls()
        self.assertEqual(len(got), 14)
        self.assertEqual([c[0] for c in got], [tgt] * 14)                                  # this
        self.assertEqual([c[1] & 0xFFFFFFFF for c in got], [0x100 + k for k in range(14)])   # jedes Item
        self.assertEqual({c[2] for c in got}, {99})                                          # Menge
        self.assertEqual({c[3] for c in got}, {0})                                           # WorkId leer
        self.assertEqual(self.mm[FLAG_OFF], 0)

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

    def test_abs_this_json_roundtrip_and_validation(self):
        r = C.build_row("A", 0x10, [("class FName", "N"), ("int32", "Count")], "void", Sdk(), ("abs", 0x105F9E6D00, 0x7123456),
                        id_value=bytes(range(1, 9)), count_value=3)
        self.assertEqual((r.spec.this_mode, r.spec.this_abs, r.spec.this_vt), ("abs", 0x105F9E6D00, 0x7123456))
        back = C.CallSpec.from_json(r.spec.to_json())
        self.assertEqual((back.this_mode, back.this_abs, back.this_vt), ("abs", 0x105F9E6D00, 0x7123456))
        with self.assertRaises(T.TrainerError):
            C.CallSpec(0, [], "abs", 0, "", None, 0x1000, 0)                          # ohne vtable keine Pruefung moeglich

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


# ======================================================================================================
# this-Modus 'scan': das Objekt wird bei JEDEM Spielstart selbst in GObjects gefunden (kein feste Adresse)
# ======================================================================================================
GOBJ_OFF, CHUNKTAB_OFF, ITEMS_OFF = 0x3800, 0x3900, 0x3A00      # nachgebaute FChunkedFixedUObjectArray / Chunk-Tabelle / Items
VT, ITEM = 0xBEEF1000, 0x18
SCAN = {"gobjects_rva": GOBJ_OFF, "objs_off": 0, "num_off": 20, "item_size": ITEM, "flags_off": 8}


@unittest.skipUnless(NATIVE, "braucht Linux x86-64, as, ld, objcopy")
class NativeScan(NativeCalls):
    def objects(self, entries):
        """entries: Liste (Objektadresse oder 0, ...) -> GObjects mit einem Chunk; Objekt-Offsets liegen im mmap."""
        struct.pack_into("<Q", self.mm, GOBJ_OFF + 0, self.base + CHUNKTAB_OFF)          # Objects
        struct.pack_into("<i", self.mm, GOBJ_OFF + 20, len(entries))                      # NumElements
        struct.pack_into("<Q", self.mm, CHUNKTAB_OFF, self.base + ITEMS_OFF)              # Chunk 0
        for i, o in enumerate(entries):
            struct.pack_into("<Q", self.mm, ITEMS_OFF + i * ITEM, o)

    def obj(self, off, vt=VT, flags=0):
        struct.pack_into("<Q", self.mm, off, vt)
        struct.pack_into("<i", self.mm, off + 8, flags)
        return self.base + off

    def scan_spec(self, n=7):
        return C.CallSpec(0, [arg("n", "int", n)], "scan", 0, "", None, 0, VT, SCAN)

    def cell(self):
        return struct.unpack("<Q", self.mm[FLAG_OFF + 8:FLAG_OFF + 16])[0]

    def test_scan_finds_the_object_skips_default_and_foreign_objects(self):
        cdo = self.obj(0x4000, flags=0x10)                     # Class Default Object: gleiche vtable, aber nicht das echte
        other = self.obj(0x4040, vt=0x1234)                    # anderes Objekt
        real = self.obj(0x4080)
        self.objects([0, other, cdo, 0, real])
        self.install([self.opt("A", self.scan_spec())])
        self.assertEqual(self.fire(0), 77)
        self.assertEqual([(c[0], c[1]) for c in self.calls()], [(real, 7)])         # this = das echte Objekt
        self.assertEqual(self.cell(), real)                                          # gemerkt
        self.assertEqual(self.mm[FLAG_OFF], 0)
        pe = struct.unpack("<4Q", self.mm[PE_BUF:PE_BUF + 32])
        self.assertEqual(pe[:3], (0x1111, 0x2222, 0x3333))                           # ProcessEvent bekommt die Originalargumente

    def test_scan_survives_a_game_restart_object_lives_elsewhere(self):
        """Der Kern: nach einem Neustart steht das Objekt an einer ANDEREN Adresse (und die Zelle ist wieder 0)."""
        first = self.obj(0x4000)
        self.objects([first])
        self.install([self.opt("A", self.scan_spec())])
        self.fire(0)
        self.assertEqual(self.calls()[0][0], first)
        # 'Neustart': Zelle leer, Objekt an neuer Adresse, alte Stelle zeigt etwas anderes
        struct.pack_into("<Q", self.mm, FLAG_OFF + 8, 0)
        struct.pack_into("<Q", self.mm, 0x4000, 0x7777)
        second = self.obj(0x4100)
        self.objects([0, second])
        ctypes.memset(self.base + LOG_OFF, 0, 8)
        self.fire(0)
        self.assertEqual([(c[0], c[1]) for c in self.calls()], [(second, 7)])

    def test_scan_cell_is_used_then_refreshed_when_the_object_changes(self):
        a = self.obj(0x4000)
        self.objects([a])
        self.install([self.opt("A", self.scan_spec())])
        self.fire(0)
        self.objects([])                                        # Liste leer: nur die Zelle kann noch helfen
        ctypes.memset(self.base + LOG_OFF, 0, 8)
        self.fire(0)
        self.assertEqual([c[0] for c in self.calls()], [a])
        struct.pack_into("<Q", self.mm, 0x4000, 0x9999)         # Objekt zerstoert, Zelle veraltet
        b = self.obj(0x4100)
        self.objects([b])
        ctypes.memset(self.base + LOG_OFF, 0, 8)
        self.fire(0)
        self.assertEqual([c[0] for c in self.calls()], [b])
        self.assertEqual(self.cell(), b)

    def test_scan_not_found_skips_the_call_but_everything_else_runs(self):
        self.objects([self.obj(0x4000, vt=0x1111)])             # kein Objekt mit der gesuchten vtable (z. B. Hauptmenue)
        self.install([self.opt("A", self.scan_spec(), spec([arg("n", "int", 5)])), self.opt("B", spec([arg("n", "int", 4)]))])
        self.assertEqual(self.fire(0), 77)                      # ProcessEvent laeuft weiter
        self.assertEqual([c[1] for c in self.calls()], [5])     # die zweite Zeile (this = 0) laeuft, die Suche-Zeile nicht
        self.assertEqual(self.mm[FLAG_OFF], 0)                  # Schalter zurueckgesetzt
        self.fire(1)
        self.assertEqual([c[1] for c in self.calls()], [5, 4])

    def test_scan_no_objects_array_is_harmless(self):
        struct.pack_into("<Q", self.mm, GOBJ_OFF, 0)            # Chunk-Tabelle noch nicht da
        self.install([self.opt("A", self.scan_spec())])
        self.assertEqual(self.fire(0), 77)
        self.assertEqual(self.calls(), [])

    def test_scan_skips_empty_chunks_and_null_items_and_finds_late_object(self):
        struct.pack_into("<Q", self.mm, GOBJ_OFF, self.base + CHUNKTAB_OFF)
        struct.pack_into("<i", self.mm, GOBJ_OFF + 20, 3 * 65536)                # drei Chunks, Chunk 0 und 1 leer (Zeiger 0)
        struct.pack_into("<Q", self.mm, CHUNKTAB_OFF, 0)
        struct.pack_into("<Q", self.mm, CHUNKTAB_OFF + 8, 0)
        struct.pack_into("<Q", self.mm, CHUNKTAB_OFF + 16, self.base + ITEMS_OFF)
        real = self.obj(0x4000)
        for i in range(10):
            struct.pack_into("<Q", self.mm, ITEMS_OFF + i * ITEM, 0)
        struct.pack_into("<Q", self.mm, ITEMS_OFF + 9 * ITEM, real)
        self.install([self.opt("A", self.scan_spec())])
        self.fire(0)
        self.assertEqual([c[0] for c in self.calls()], [real])

    def test_many_rows_share_one_search_and_one_cell(self):
        real = self.obj(0x4000)
        self.objects([real])
        rows = [self.scan_spec(n) for n in range(1, 15)]
        one_row = len(self.install([self.opt("A", rows[0])]))
        code = self.install([self.opt("A", *rows)])
        self.assertLess(len(code) - one_row, 13 * 30)           # je weitere Zeile nur call/test/jz + Aufruf (~24 Byte), keine eigene Suche
        self.assertEqual(T.scan_keys([self.opt("A", *rows)]), [self.scan_spec().scan_key()])
        self.fire(0)
        self.assertEqual([(c[0], c[1]) for c in self.calls()], [(real, n) for n in range(1, 15)])

    def test_two_different_objects_get_two_cells(self):
        vt2 = 0xBEEF2000
        a, b = self.obj(0x4000), self.obj(0x4040, vt=vt2)
        self.objects([a, b])
        sp2 = C.CallSpec(0, [arg("n", "int", 2)], "scan", 0, "", None, 0, vt2, SCAN)
        self.install([self.opt("A", self.scan_spec(1), sp2)])
        self.fire(0)
        self.assertEqual([(c[0], c[1]) for c in self.calls()], [(a, 1), (b, 2)])
        self.assertEqual(struct.unpack("<2Q", self.mm[FLAG_OFF + 8:FLAG_OFF + 24]), (a, b))
        self.assertEqual(T.flag_bytes_needed(1, 2), 8 + 16)

    def test_scan_spec_json_roundtrip_and_validation(self):
        sp = self.scan_spec()
        back = C.CallSpec.from_json(__import__("json").loads(__import__("json").dumps(sp.to_json())))
        self.assertEqual((back.this_mode, back.scan_key()), ("scan", sp.scan_key()))
        self.assertEqual(sp.to_json()["this"], "scan")
        with self.assertRaises(T.TrainerError):
            C.CallSpec(0, [], "scan", 0, "", None, 0, 0, SCAN)                       # ohne vtable
        with self.assertRaises(T.TrainerError):
            C.CallSpec(0, [], "scan", 0, "", None, 0, VT, {"gobjects_rva": 1})       # unvollstaendig
        self.assertIsNone(spec([arg("n", "int", 1)]).scan_key())

    def test_build_row_accepts_scan_this(self):
        class S:
            enums = {}
        row = C.build_row("x", 0, [], None, S(), ("scan", VT, SCAN))
        self.assertEqual((row.spec.this_mode, row.spec.scan_key()), ("scan", self.scan_spec().scan_key()))


class PlanWithScan(unittest.TestCase):
    """plan(): der Schalter-Bereich bekommt hinter den Schaltern je gesuchtem Objekt eine 8-Byte-Zelle."""

    def make(self, n_rows=3):
        img = TS.FakeImage()
        sc = {"gobjects_rva": 0x13000, "objs_off": 0, "num_off": 20, "item_size": 0x18, "flags_off": 8}
        rows = [C.CallRow(f"r{i}", C.CallSpec(img.impl - img.BASE, [arg("n", "int", i + 1)], "scan", 0, "", None, 0, VT, sc),
                          None, 1) for i in range(n_rows)]
        opts = [T.Option("A", rows), T.Option("B", rows[:1])]
        return img, opts, T.plan(img.read, img.maps, img.BASE, opts, img.impl, img.pe, [img.slot], log=lambda _m: None, settle=0)

    def test_flag_area_has_room_for_the_cell(self):
        img, opts, p = self.make()
        self.assertEqual(len(T.scan_keys(opts)), 1)
        self.assertGreaterEqual(p.flag_size, T.flag_bytes_needed(2, 1))
        self.assertGreaterEqual(p.flag_size, 16)
        self.assertEqual(p.flag_addr % 8, 0)

    def test_cave_reads_and_writes_the_cell_inside_the_flag_area(self):
        img, opts, p = self.make()
        cell = p.flag_addr + T.flag_bytes_needed(2)
        code = p.cave_bytes
        found = False
        for i in range(len(code) - 7):               # mov rdi,[rip+d] (488B3D) / mov [rip+d],rdi (48893D) zeigen auf die Zelle
            if code[i:i + 3] in (bytes.fromhex("488B3D"), bytes.fromhex("48893D")):
                d = struct.unpack_from("<i", code, i + 3)[0]
                if p.cave + i + 7 + d == cell:
                    found = True
        self.assertTrue(found)

    def test_project_json_keeps_scan_and_loads_back(self):
        img, opts, p = self.make()
        spec_json = T.spec_json(p) if hasattr(T, "spec_json") else None
        row_json = opts[0].rows[0].to_json()
        back = C.CallRow.from_json(__import__("json").loads(__import__("json").dumps(row_json)))
        self.assertEqual(back.spec.scan_key(), opts[0].rows[0].spec.scan_key())
        self.assertEqual(row_json["call"]["this"], "scan")
        del spec_json
