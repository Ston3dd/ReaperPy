"""unity_items: Item-Enum + Geben-Methode finden, Haken waehlen, Funktionsanfang verschieben, Cave bauen UND ausfuehren.

Die Cave wird hier WIRKLICH ausgefuehrt (Linux x86-64, mmap + ctypes) - wie bei tests/test_cave_trainer.py: Ein Treiber
ruft eine Update-Funktion (mit gehakten Anfangsbefehlen inkl. rip-relativer Adresse und bedingtem Sprung), eine Hilfsfunktion
(Geben-Methode) schreibt ihre Register in einen Puffer.  Ohne Linux/x86-64/gcc-Binutils werden diese Tests uebersprungen.
"""
import ctypes
import mmap
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cave_trainer as TR
import il2cpp_dump as D
import ue_instr
import unity_items as U

NATIVE = (platform.system() == "Linux" and platform.machine() in ("x86_64", "AMD64")
          and all(shutil.which(x) for x in ("as", "ld", "objcopy", "objdump")))

ITEMS = ["None", "Potion_Small", "Potion_Big", "Potion_Mega", "Sword_Iron", "Sword_Steel", "Sword_Gold", "Shield_Wood",
         "Shield_Iron", "Fish_Trout", "Fish_Salmon", "Fish_Carp", "Gold", "Wood", "Stone", "Herb_Red", "Herb_Blue", "Count"]


def enum_text(name, values, td, ns="Game", img_underlying="int"):
    lines = [f"// Namespace: {ns}", f"public enum {name} // TypeDefIndex: {td}", "{", f"\tpublic {img_underlying} value__; // 0x0"]
    lines += [f"\tpublic const {name} {n} = {v};" for n, v in values]
    lines.append("}\n")
    return "\n".join(lines)


def cls_text(name, td, body, base="MonoBehaviour", ns="Game", kind="class"):
    return f"// Namespace: {ns}\npublic {kind} {name} : {base} // TypeDefIndex: {td}\n{{\n{body}\n}}\n"


def meth(rva, sig):
    return f"\t// RVA: {rva:#x} Offset: {rva:#x} VA: {rva:#x}\n\t{sig} {{ }}\n"


def make_dump(tmp):
    parts = ["// Image 0: Assembly-CSharp.dll - 0\n// Image 1: UnityEngine.CoreModule.dll - 50\n"]
    parts.append(enum_text("ItemID", list(enumerate(ITEMS)) and [(n, i) for i, n in enumerate(ITEMS)], 0))
    parts.append(enum_text("ItemType", [("None", 0), ("Weapon", 1), ("Potion", 2), ("Food", 3)], 1))
    parts.append(enum_text("UIButtonKind", [(f"B{i}", i) for i in range(30)], 2))
    inv = (meth(0x1100, "public void AddItem(ItemID id, int count)") + meth(0x1110, 'public void AddItem(string name, int count)')
           + meth(0x1120, "public void RemoveItem(ItemID id, int count)") + meth(0x1200, "public void Update()")
           + meth(0x1210, "public bool HasItem(ItemID id)"))
    parts.append(cls_text("Inventory", 3, inv))
    parts.append(cls_text("Player", 4, "\tpublic Inventory inventory; // 0x40\n" + meth(0x1300, "public void Update()")))
    parts.append(cls_text("Enemy", 5, "\tpublic Inventory loot; // 0x30\n" + meth(0x1400, "public void Update()")))
    parts.append(cls_text("ItemDB", 6, meth(0x1500, "public static void GiveItem(ItemID id, int amount)")
                          + meth(0x1510, "public static void AddGold(int amount)"), base="Object"))
    parts.append(cls_text("Menu", 7, meth(0x1600, "public void AddButton(UIButtonKind kind, int count)")))
    parts.append("// Namespace: UnityEngine\npublic class MonoBehaviour // TypeDefIndex: 50\n{\n}\n")
    parts.append("// Namespace: System\npublic class Object // TypeDefIndex: 51\n{\n}\n")
    path = os.path.join(tmp, "dump.cs")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    g = D.GameDump({"dump_cs": path}, log=lambda *_a: None)
    g.load()
    return g


def cls(g, name):
    return g.find_class(name)


class Parsing(unittest.TestCase):
    def test_split_params_and_parse(self):
        self.assertEqual(U.split_params("ItemID id, int count = 1"), ["ItemID id", "int count = 1"])
        self.assertEqual(U.split_params("Dictionary<int, string> d, float f"), ["Dictionary<int, string> d", "float f"])
        self.assertEqual(U.split_params(""), [])
        with tempfile.TemporaryDirectory() as tmp:
            en = U.enum_map(make_dump(tmp))
        p = U.parse_param("ItemID id", en)
        self.assertEqual((p["kind"], p["size"], p["name"]), ("enum", 4, "id"))
        self.assertEqual(U.parse_param("int count = 1", en)["kind"], "int")
        self.assertEqual(U.parse_param("bool b", en)["kind"], "bool")
        self.assertEqual(U.parse_param("double d", en)["size"], 8)
        self.assertEqual(U.parse_param("string name", en)["kind"], "other")
        self.assertTrue(U.parse_param("ref int x", en)["ref"])


class Finding(unittest.TestCase):
    @classmethod
    def setUpClass(cls_):
        cls_.tmp = tempfile.mkdtemp()
        cls_.g = make_dump(cls_.tmp)

    @classmethod
    def tearDownClass(cls_):
        shutil.rmtree(cls_.tmp, ignore_errors=True)

    def test_item_enum_ranking(self):
        ranked = U.item_enums(self.g)
        self.assertEqual(ranked[0][0].name, "ItemID")
        names = [c.name for c, _s in ranked]
        self.assertNotIn("UIButtonKind", names)
        if "ItemType" in names:                     # Kategorien-Enum darf nie vor der Item-Liste stehen
            self.assertGreater(names.index("ItemType"), 0)

    def test_items_and_categories(self):
        items = U.build_items(cls(self.g, "ItemID"))
        by = {i["name"]: i for i in items}
        self.assertNotIn("None", by)
        self.assertNotIn("Count", by)
        self.assertEqual(by["Sword_Gold"]["id"], 6)
        groups = U.group_items(items)
        self.assertIn("Potion", groups)
        self.assertEqual(len(groups["Sword"]), 3)
        self.assertEqual(by["Gold"]["fname"], b"")

    def test_give_candidates(self):
        en = cls(self.g, "ItemID")
        ok, bad = U.give_candidates(self.g, en)
        titles = [g.method.key for g in ok]
        self.assertEqual(titles[0], "Game.Inventory.AddItem")
        self.assertEqual(ok[0].params[ok[0].id_i]["type"], "ItemID")
        self.assertEqual(ok[0].params[ok[0].count_i]["name"], "count")
        self.assertIn("Game.ItemDB.GiveItem", titles)                 # statische Methode ist auch erlaubt
        self.assertNotIn("Game.Inventory.RemoveItem", titles)
        self.assertNotIn("Game.Menu.AddButton", titles)
        self.assertNotIn("Game.ItemDB.AddGold", titles)               # keine Item-ID
        # die String-Variante wird abgelehnt (mit Grund), die Enum-Variante nicht
        self.assertTrue(all(g.method.rva != 0x1110 for g in ok))

    def test_rejected_with_reason(self):
        enums = U.enum_map(self.g)
        m = next(m for m in cls(self.g, "Inventory").methods if m.rva == 0x1110)
        with self.assertRaises(U.UnityTrainerError) as cm:
            U.classify_give(m, enums, cls(self.g, "ItemID"))
        self.assertIn("string", str(cm.exception))

    def test_hooks_instance(self):
        en = cls(self.g, "ItemID")
        give = next(g for g in U.give_candidates(self.g, en)[0] if g.method.key == "Game.Inventory.AddItem")
        hooks = U.hook_candidates(self.g, give)
        self.assertEqual((hooks[0].method.key, hooks[0].this_mode), ("Game.Inventory.Update", "hooked"))
        member = [h for h in hooks if h.this_mode == "member"]
        self.assertEqual([h.method.cls.name for h in member][:2], ["Player", "Enemy"])          # Spieler vor Gegner
        self.assertEqual(member[0].this_off, 0x40)

    def test_hooks_static(self):
        en = cls(self.g, "ItemID")
        give = next(g for g in U.give_candidates(self.g, en)[0] if g.method.key == "Game.ItemDB.GiveItem")
        hooks = U.hook_candidates(self.g, give)
        self.assertTrue(hooks and all(h.this_mode == "zero" for h in hooks))
        self.assertEqual(hooks[0].method.cls.name, "Player")


# ----------------------------------------------------------------------------------------------------------------
# Verschieben des Funktionsanfangs
# ----------------------------------------------------------------------------------------------------------------
def asm_bytes(text, tmp, org_lines=""):
    src = os.path.join(tmp, "a.s")
    with open(src, "w", encoding="utf-8") as f:
        f.write(".intel_syntax noprefix\n.text\n" + text + "\n" + org_lines)
    obj, elf, binf = (os.path.join(tmp, n) for n in ("a.o", "a.elf", "a.bin"))
    subprocess.run(["as", "--64", "-o", obj, src], check=True)
    subprocess.run(["ld", "-Ttext=0", "-e", "0", "-o", elf, obj], check=True)
    subprocess.run(["objcopy", "-O", "binary", "-j", ".text", elf, binf], check=True)
    with open(binf, "rb") as f:
        return f.read()


@unittest.skipUnless(NATIVE, "braucht Linux x86-64 und binutils")
class Relocate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dis = ue_instr.get_disasm(prefer="objdump")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def reloc(self, text, old=0x0, new=0x9000):
        code = asm_bytes(text + "\n.fill 64, 1, 0x90", self.tmp)
        return code, U.relocate(code, old, new, self.dis)

    def test_plain_prologue_copied_unchanged(self):
        code, (n, out) = self.reloc("push rbp\nmov rbp, rsp\npush r15\npush r14")
        self.assertGreaterEqual(n, 5)
        self.assertEqual(out, code[:n])

    def test_rip_relative_is_adjusted(self):
        code, (n, out) = self.reloc("push rbp\nmov rbp, rsp\ncmp byte ptr [rip+0x200], 0")
        self.assertEqual(n, 1 + 3 + 7)
        old_tgt = 0 + n + struct.unpack_from("<i", code, n - 5)[0]                  # disp32 liegt vor dem Immediate
        new_tgt = 0x9000 + n + struct.unpack_from("<i", out, n - 5)[0]
        self.assertEqual(new_tgt, old_tgt)
        self.assertNotEqual(out, code[:n])

    def test_short_jcc_becomes_near_and_keeps_target(self):
        code, (n, out) = self.reloc("mov rbp, rsp\nje 1f\nnop\nnop\n1: nop")
        self.assertEqual(n, 3 + 2)
        self.assertEqual(out[3:5], bytes([0x0F, 0x84]))
        tgt = 5 + 2                                                                 # je +2 (Quelle liegt bei Adresse 0)
        self.assertEqual(0x9000 + 3 + 6 + struct.unpack_from("<i", out, 5)[0], tgt)
        self.assertEqual(len(out), 3 + 6)

    def test_call_rel32_retargeted(self):
        code, (n, out) = self.reloc("call 0x5000\npush rbp")
        self.assertEqual(out[0], 0xE8)
        self.assertEqual(0x9000 + 5 + struct.unpack_from("<i", out, 1)[0], 0x5000)

    def test_refuses_ret_in_the_middle_and_jump_into_stolen(self):
        with self.assertRaises(U.RelocError):
            self.reloc("ret\nnop\nnop\nnop\nnop\nnop")
        with self.assertRaises(U.RelocError):
            self.reloc("xor eax, eax\njmp 1f\n1: nop\nnop\nnop")

    def test_target_inside_stolen_region_refused(self):
        with self.assertRaises(U.RelocError):
            self.reloc("nop\nje 1f\n1: nop\nnop\nnop\nnop")


# ----------------------------------------------------------------------------------------------------------------
# Aufruf-Bytes gegen den GNU-Assembler pruefen
# ----------------------------------------------------------------------------------------------------------------
def make_call(kinds, static=False, this_mode="hooked", this_off=0, id_i=0, count_i=1, impl=0x100):
    params = [{"name": f"p{i}", "type": k, "kind": ("enum" if k == "E" else k), "size": {"E": 4, "int": 4, "int64": 8,
                                                                                             "bool": 1, "float": 4,
                                                                                             "double": 8}[k],
               "ref": False, "signed": True} for i, k in enumerate(kinds)]
    return U.Call(impl, static, "zero" if static else this_mode, this_off, params, id_i, count_i, "T.F")


@unittest.skipUnless(NATIVE, "braucht Linux x86-64 und binutils")
class Encoding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def emitted(self, row):
        e = TR._Emit(0)
        row.emit(e, 0)
        return e.finish()

    def disasm(self, data):
        binf = os.path.join(self.tmp, "d.bin")
        with open(binf, "wb") as f:
            f.write(data)
        r = subprocess.run(["objdump", "-D", "-b", "binary", "-mi386:x86-64", "-M", "intel", binf], capture_output=True,
                           text=True, encoding="utf-8")
        return [" ".join(l.split("\t")[-1].split()) for l in r.stdout.splitlines() if "\t" in l and ":" in l.split("\t")[0]]

    def check(self, row, body):
        got = self.emitted(row)
        want = asm_bytes(body + "\n.org 0x100\nf: ret", self.tmp)
        self.assertEqual(got, want[:len(got)], f"{got.hex()} != {want[:len(got)].hex()}")

    def test_instance_enum_int(self):
        row = U.UnityRow("x", make_call(["E", "int"]), 0x1234, 77)
        self.check(row, "mov rdi,[rsp+0x10]\nmov esi,0x1234\nmov edx,77\nxor ecx,ecx\ncall f")

    def test_member_mode(self):
        row = U.UnityRow("x", make_call(["E", "int"], this_mode="member", this_off=0x40), 5, 9)
        got = self.disasm(self.emitted(row))                       # as nimmt disp8/jz kurz, wir disp32/jz near: gleiche Wirkung
        self.assertEqual(got[0], "mov rdi,QWORD PTR [rsp+0x10]")
        self.assertEqual(got[1], "mov rdi,QWORD PTR [rdi+0x40]")
        self.assertEqual(got[2], "test rdi,rdi")
        self.assertTrue(got[3].startswith("je "))
        self.assertEqual(got[4:7], ["mov esi,0x5", "mov edx,0x9", "xor ecx,ecx"])
        self.assertTrue(got[7].startswith("call "))
        e = TR._Emit(0)                                              # das jz muss genau hinter den call springen
        row.emit(e, 0)
        data = e.finish()
        self.assertEqual(data[15:17], b"\x0f\x84")                  # mov(5) + mov(7) + test(3) = 15 Byte davor
        self.assertEqual(17 + 4 + struct.unpack_from("<i", data, 17)[0], len(data))

    def test_static_starts_at_rdi(self):
        row = U.UnityRow("x", make_call(["E", "int"], static=True), 3, 4)
        self.check(row, "mov edi,3\nmov esi,4\nxor edx,edx\ncall f")

    def test_all_six_registers_and_bool(self):
        row = U.UnityRow("x", make_call(["E", "int", "bool", "int"]), 1, 2)
        self.check(row, "mov rdi,[rsp+0x10]\nmov esi,1\nmov edx,2\nmov ecx,0\nmov r8d,0\nxor r9d,r9d\ncall f")

    def test_wide_and_float(self):
        row = U.UnityRow("x", make_call(["int64", "float", "int"], id_i=0, count_i=2), 0x1122334455, 6)
        self.check(row, "mov rdi,[rsp+0x10]\nmovabs rsi,0x1122334455\nmov eax,0\nmovd xmm0,eax\nmov edx,6\nxor ecx,ecx\ncall f")

    def test_too_many_int_params_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = make_dump(tmp)
            en = U.enum_map(g)
            m = D.Method("Add", "void", "ItemID a, int b, int c, int d, int e, int f", 0x10, False, cls(g, "Inventory"))
            with self.assertRaises(U.UnityTrainerError):
                U.classify_give(m, en, cls(g, "ItemID"))

    def test_value_too_big_for_parameter(self):
        with self.assertRaises(U.UnityTrainerError):
            U.UnityRow("x", make_call(["E", "int"]), 2 ** 40, 1)
        with self.assertRaises(U.UnityTrainerError):
            U.UnityRow("x", make_call(["E", "int"]), 1, 0)


# ----------------------------------------------------------------------------------------------------------------
# Cave WIRKLICH ausfuehren
# ----------------------------------------------------------------------------------------------------------------
CAVE_OFF, FLAG_OFF, UPD_OFF, SIZE = 0x1000, 0x3000, 0x300, 0x4000
LOG_OFF = 0x800                                        # logcnt (8) + 64 Byte je Aufruf
RES_OFF = 0xF00                                        # Update-Ergebnis: count, this, mi
OBJ_OFF = 0x3800                                       # Spiel-Objekt: +0x20 -> Inventory-Zeiger
INV_OFF = 0x3900                                       # "Inventar"
DRV_BUF = 0xF80

HELPERS = r"""
.intel_syntax noprefix
.text
.org 0x0
rec_fn:
  mov rax, [rip+logcnt]
  lea r10, [rip+logbuf]
  imul r11, rax, 64
  add r10, r11
  mov [r10], rdi
  mov [r10+8], rsi
  mov [r10+16], rdx
  mov [r10+24], rcx
  mov [r10+32], r8
  mov [r10+40], rsp
  movq [r10+48], xmm0
  inc rax
  mov [rip+logcnt], rax
  mov eax, 0x1234
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
  mov rdi, OBJ
  mov esi, 0x5151
  call UPD
  lea r10, [rip+drvbuf]
  mov [r10], rbx
  mov [r10+8], rbp
  mov [r10+16], r12
  mov [r10+24], r13
  mov [r10+32], r14
  mov [r10+40], r15
  add rsp, 8
  pop r15
  pop r14
  pop r13
  pop r12
  pop rbp
  pop rbx
  ret
.org 0x300
update:
  push rbp
  mov rbp, rsp
  cmp byte ptr [rip+skipflag], 0
  jne 1f
  inc qword ptr [rip+updcount]
  mov [rip+updthis], rdi
  mov [rip+updmi], rsi
1:
  pop rbp
  ret
.org 0x800
logcnt: .quad 0
logbuf: .space 0x6F8
.org 0xF00
updcount: .quad 0
updthis: .quad 0
updmi: .quad 0
skipflag: .quad 0
.org 0xF80
drvbuf: .space 0x40
"""


def build_helpers(tmp, obj_abs):
    text = HELPERS.replace("call UPD", f"call {UPD_OFF}").replace("mov rdi, OBJ", f"mov rdi, {obj_abs}")
    return asm_bytes(text, tmp)


@unittest.skipUnless(NATIVE, "braucht Linux x86-64 und binutils")
class NativeCave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mm = mmap.mmap(-1, SIZE, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
        self.abs = ctypes.addressof(ctypes.c_char.from_buffer(self.mm))
        self.dis = ue_instr.get_disasm(prefer="objdump")
        code = build_helpers(self.tmp, self.abs + OBJ_OFF)
        self.mm[0:len(code)] = code
        self.driver = ctypes.CFUNCTYPE(None)(self.abs + 0x200)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        try:
            self.mm.close()
        except BufferError:
            pass

    def q(self, off, n=1):
        return [struct.unpack_from("<Q", self.mm, off + 8 * i)[0] for i in range(n)]

    def log(self):
        n = self.q(LOG_OFF)[0]
        out = []
        for i in range(n):
            f = struct.unpack_from("<6Qd", self.mm, LOG_OFF + 8 + 64 * i)
            out.append(f)
        return out

    def install(self, options, flags_for=()):
        head = bytes(self.mm[UPD_OFF:UPD_OFF + 48])
        n, _p = U.relocate(head, UPD_OFF, UPD_OFF, self.dis)
        cave = U.build_cave(CAVE_OFF, FLAG_OFF, UPD_OFF + n, lambda a: U.relocate(head, UPD_OFF, a, self.dis)[1], options, 0)
        self.assertLess(len(cave), FLAG_OFF - CAVE_OFF)
        self.mm[CAVE_OFF:CAVE_OFF + len(cave)] = cave
        hook = b"\xE9" + struct.pack("<i", CAVE_OFF - (UPD_OFF + 5)) + b"\x90" * (n - 5)
        self.mm[UPD_OFF:UPD_OFF + n] = hook
        for i in flags_for:
            self.mm[FLAG_OFF + i] = 1
        return cave, n

    def run_driver(self):
        self.driver()
        regs = struct.unpack_from("<6Q", self.mm, DRV_BUF)
        self.assertEqual(regs, (0xB1B1B1B1, 0xB2B2B2B2, 0xC1C1C1C1, 0xC2C2C2C2, 0xC3C3C3C3, 0xC4C4C4C4))   # callee-saved heil

    def rows(self, call, specs):
        return [U.UnityRow(f"i{k}", call, i, a) for k, (i, a) in enumerate(specs)]

    def test_no_flag_original_runs_untouched(self):
        call = make_call(["E", "int"], impl=0)
        self.install([U.Option("A", self.rows(call, [(11, 5)]))])
        self.run_driver()
        self.assertEqual(self.log(), [])
        cnt, this, mi = self.q(RES_OFF, 3)
        self.assertEqual((cnt, this, mi), (1, self.abs + OBJ_OFF, 0x5151))

    def test_flag_calls_game_function_once_per_row(self):
        call = make_call(["E", "int"], impl=0)                      # Geben-Methode = rec_fn @ 0
        opts = [U.Option("A", self.rows(call, [(11, 5), (12, 6)])), U.Option("B", self.rows(call, [(99, 1000)]))]
        self.install(opts, flags_for=[0])
        self.run_driver()
        log = self.log()
        self.assertEqual([(r[1], r[2]) for r in log], [(11, 5), (12, 6)])
        for r in log:
            self.assertEqual(r[0], self.abs + OBJ_OFF)               # this = gehooktes Objekt
            self.assertEqual(r[3], 0)                               # MethodInfo = 0
            self.assertEqual(r[5] & 0xF, 8)                         # Stack am Aufruf ausgerichtet (rsp = 8 mod 16)
        cnt, this, mi = self.q(RES_OFF, 3)                          # die Update-Methode lief danach ganz normal
        self.assertEqual((cnt, this, mi), (1, self.abs + OBJ_OFF, 0x5151))
        self.assertEqual(self.mm[FLAG_OFF], 0)                       # Schalter zurueckgesetzt
        self.run_driver()                                            # zweiter Durchlauf: nichts mehr
        self.assertEqual(len(self.log()), 2)
        self.assertEqual(self.q(RES_OFF)[0], 2)

    def test_two_flags_in_order(self):
        call = make_call(["E", "int"], impl=0)
        opts = [U.Option("A", self.rows(call, [(1, 1)])), U.Option("B", self.rows(call, [(2, 2)]))]
        self.install(opts, flags_for=[1, 0])
        self.run_driver()
        self.assertEqual([r[1] for r in self.log()], [1, 2])

    def test_member_mode_uses_field_and_skips_null(self):
        call = make_call(["E", "int"], this_mode="member", this_off=0x20, impl=0)
        self.install([U.Option("A", self.rows(call, [(7, 3)]))], flags_for=[0])
        struct.pack_into("<Q", self.mm, OBJ_OFF + 0x20, self.abs + INV_OFF)
        self.run_driver()
        self.assertEqual([(r[0], r[1], r[2]) for r in self.log()], [(self.abs + INV_OFF, 7, 3)])
        # Feld ist null -> nichts aufrufen, Schalter trotzdem zurueck, Update laeuft
        struct.pack_into("<Q", self.mm, OBJ_OFF + 0x20, 0)
        self.mm[FLAG_OFF] = 1
        self.run_driver()
        self.assertEqual(len(self.log()), 1)
        self.assertEqual(self.mm[FLAG_OFF], 0)
        self.assertEqual(self.q(RES_OFF)[0], 2)

    def test_static_call_args_from_rdi(self):
        call = make_call(["E", "int"], static=True, impl=0)
        self.install([U.Option("A", self.rows(call, [(41, 8)]))], flags_for=[0])
        self.run_driver()
        r = self.log()[0]
        self.assertEqual((r[0], r[1], r[2]), (41, 8, 0))             # rdi=id, rsi=Menge, rdx=MethodInfo

    def test_float_count(self):
        call = make_call(["E", "float"], impl=0)
        self.install([U.Option("A", self.rows(call, [(5, 250)]))], flags_for=[0])
        self.run_driver()
        r = self.log()[0]
        self.assertEqual(r[1], 5)
        self.assertEqual(struct.unpack("<f", struct.pack("<Q", struct.unpack("<Q", struct.pack("<d", r[6]))[0])[:4])[0], 250.0)

    def test_update_skip_branch_still_works_after_hook(self):
        """Der gehakte Anfang enthaelt cmp [rip+x],0 + jne: wird skipflag gesetzt, muss die Methode weiterhin ueberspringen."""
        call = make_call(["E", "int"], impl=0)
        self.install([U.Option("A", self.rows(call, [(1, 1)]))])
        struct.pack_into("<Q", self.mm, RES_OFF + 24, 1)             # skipflag = 1
        self.run_driver()
        self.assertEqual(self.q(RES_OFF)[0], 0)                      # Update-Rumpf wurde uebersprungen (wie im Original)


class Project(unittest.TestCase):
    def fake_game(self, head, size=0x30000):
        """Spiel-Speicher: Code-Region (r-x) mit Update-Funktion, Padding am Ende, Daten-Region (rw-) mit Null-Ende."""
        base = 0x400000
        code = bytearray(b"\xCC" * 0x20000)
        code[0x100:0x100 + len(head)] = head
        code[0x300:0x302] = b"\x90\xC3"
        data = bytearray(0x10000)
        mem = {base: code, base + 0x20000: data}
        maps = [(base, base + 0x20000, 5), (base + 0x20000, base + 0x30000, 3)]

        def read(addr, n):
            for s, buf in mem.items():
                if s <= addr and addr + n <= s + len(buf):
                    return bytes(buf[addr - s:addr - s + n])
            raise OSError(f"unlesbar {addr:#x}")
        return base, maps, read

    @unittest.skipUnless(NATIVE, "braucht Linux x86-64 und binutils")
    def test_plan_and_write_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            head = asm_bytes("push rbp\nmov rbp, rsp\ncmp byte ptr [rip+0x4000], 0\njne 1f\nnop\n1: pop rbp\nret", tmp)
            base, maps, read = self.fake_game(head)
            call = make_call(["E", "int"], impl=0x300)
            opts = [U.Option("Traenke", [U.UnityRow("Potion_Small", call, 1, 99), U.UnityRow("Potion_Big", call, 2, 99)]),
                    U.Option("Schwerter", [U.UnityRow("Sword_Iron", call, 4, 1)])]
            p = U.plan(read, maps, base, opts, call, 0x100, "Game.Inventory.Update", log=lambda *_a: None, settle=0,
                       dis=ue_instr.get_disasm(prefer="objdump"))
            self.assertEqual(p.hook_len, 11)
            self.assertEqual(p.hook_new[0], 0xE9)
            self.assertEqual(len(p.hook_new), p.hook_len)
            self.assertTrue(p.cave > base + 0x100 and p.flag_addr >= base + 0x20000)
            out = os.path.join(tmp, "Items")
            files = U.write_project(out, p, game="Testspiel", title_id="PPSA00000")
            names = sorted(os.path.basename(f) for f in files)
            self.assertIn(U.BASE_FILE, names)
            self.assertIn("01_Traenke.reapproj", names)
            self.assertIn("02_Schwerter.reapproj", names)
            import json
            with open(os.path.join(out, U.BASE_FILE), encoding="utf-8") as f:
                base_doc = json.load(f)
            self.assertEqual(base_doc["ImageBase"], hex(base))
            self.assertEqual([v["offset"] for v in base_doc["Variables"]], [hex(p.cave - base), hex(0x100)])
            self.assertEqual(base_doc["Variables"][1]["defaultValue"], TR._spaced(head[:11]))
            with open(os.path.join(out, "02_Schwerter.reapproj"), encoding="utf-8") as f:
                opt_doc = json.load(f)
            self.assertEqual(opt_doc["Variables"][0]["offset"], hex(p.flag_addr + 1 - base))
            back = U.load_options(out)
            self.assertEqual([o.name for o in back], ["Traenke", "Schwerter"])
            self.assertEqual([(r.alias, r.item_id, r.amount) for r in back[0].rows], [("Potion_Small", 1, 99), ("Potion_Big", 2, 99)])
            # erneutes Speichern entfernt veraltete Eintrag-Dateien
            p.options = p.options[:1]
            U.write_project(out, p)
            self.assertFalse(os.path.exists(os.path.join(out, "02_Schwerter.reapproj")))

    @unittest.skipUnless(NATIVE, "braucht Linux x86-64 und binutils")
    def test_leftover_unity_cave_is_reused_not_zero_capacity(self):
        """BASIS aus -> die Cave bleibt am Region-Ende stehen.  Ein zweiter Export darf daran nicht mit '0 Byte' scheitern
        (gleiche Lage wie beim Unreal-Trainer auf der zweiten Konsole), und der Trainer muss auch auf frischer Konsole laufen."""
        import json
        with tempfile.TemporaryDirectory() as tmp:
            head = asm_bytes("push rbp\nmov rbp, rsp\ncmp byte ptr [rip+0x4000], 0\njne 1f\nnop\n1: pop rbp\nret", tmp)
            base, maps, read = self.fake_game(head)
            dis = ue_instr.get_disasm(prefer="objdump")
            call = make_call(["E", "int"], impl=0x300)
            opts = [U.Option("A", [U.UnityRow("x", call, 1, 5)])]
            mem = {}
            orig_read = read

            def rd(a, n):
                b = bytearray(orig_read(a, n))
                for k in range(n):
                    if a + k in mem:
                        b[k] = mem[a + k]
                return bytes(b)
            free = TR.capacity(rd, maps, base)["code"]
            p1 = U.plan(rd, maps, base, opts, call, 0x100, dis=dis, log=lambda *_a: None, settle=0)
            for k, v in enumerate(p1.cave_bytes):                  # Cave steht, Haken ist aus
                mem[p1.cave + k] = v
            self.assertGreater(TR.capacity(rd, maps, base)["code"], 0)
            self.assertGreaterEqual(TR.capacity(rd, maps, base)["code"], free - 0x200)
            p2 = U.plan(rd, maps, base, [U.Option("B", [U.UnityRow("y", call, 2, 6), U.UnityRow("z", call, 3, 6)])], call,
                        0x100, dis=dis, log=lambda *_a: None, settle=0)
            self.assertEqual(p2.cave_orig, bytes([p2.cave_orig[0]]) * len(p2.cave_bytes))        # "Original" = Padding
            self.assertIn(rd(p2.cave, len(p2.cave_bytes)), p2.verify_also)
            self.assertTrue(any("frueheren" in w for w in p2.warnings))
            self.assertLessEqual(p2.flag_addr + p2.flag_size, p1.flag_addr + p1.flag_size)
            out = os.path.join(tmp, "o")
            U.write_project(out, p2)
            with open(os.path.join(out, U.BASE_FILE), encoding="utf-8") as f:
                self.assertTrue(json.load(f).get("VerifyAlso"))

    def test_fit_options_zero_capacity_is_explained(self):
        call = make_call(["E", "int"])
        with self.assertRaises(U.UnityTrainerError) as c:
            U.fit_options([U.Option("A", [U.UnityRow("x", call, 1, 1)])], 0)
        self.assertIn("KEIN freier Code-Platz", str(c.exception))

    @unittest.skipUnless(NATIVE, "braucht Linux x86-64 und binutils")
    def test_refuses_already_hooked_and_unhookable(self):
        with tempfile.TemporaryDirectory() as tmp:
            call = make_call(["E", "int"], impl=0x300)
            opts = [U.Option("A", [U.UnityRow("x", call, 1, 1)])]
            dis = ue_instr.get_disasm(prefer="objdump")
            base, maps, read = self.fake_game(b"\xE9\x00\x10\x00\x00" + b"\x90" * 20)
            with self.assertRaises(U.UnityTrainerError):
                U.plan(read, maps, base, opts, call, 0x100, dis=dis, log=lambda *_a: None, settle=0)
            base, maps, read = self.fake_game(b"\xC3" + b"\x90" * 20)
            with self.assertRaises(U.UnityTrainerError) as cm:
                U.plan(read, maps, base, opts, call, 0x100, dis=dis, log=lambda *_a: None, settle=0)
            self.assertIn("haken", str(cm.exception).lower())

    def test_fit_options_splits_by_capacity(self):
        call = make_call(["E", "int"])
        opts = [U.Option(f"P{i}", [U.UnityRow(f"i{i}_{k}", call, k + 1, 1) for k in range(14)]) for i in range(10)]
        cap = U.cave_size(opts[:3])
        groups = U.fit_options(opts, cap)
        self.assertTrue(all(U.cave_size(g) <= cap for g in groups))
        self.assertEqual(sum(len(g) for g in groups), 10)
        self.assertGreater(len(groups), 1)
        with self.assertRaises(U.UnityTrainerError):
            U.fit_options(opts, 40)


class Packages(unittest.TestCase):
    def test_make_options_14_per_package_and_names(self):
        call = make_call(["E", "int"])
        items = [{"name": f"Fish_{i}", "id": i + 1, "category": "Fish", "fname": b""} for i in range(30)]
        pk = U.packages(U.group_items(items))
        self.assertEqual([n for n, _ in pk], ["Fish 1", "Fish 2", "Fish 3"])
        options, skipped = U.make_options(pk, call, 99)
        self.assertEqual((len(options), skipped), (3, 0))
        self.assertEqual([len(o.rows) for o in options], [14, 14, 2])
        items.append({"name": "NoId", "id": None, "category": "Fish", "fname": b""})
        _o, skipped = U.make_options(U.packages(U.group_items(items)), call, 1)
        self.assertEqual(skipped, 1)


if __name__ == "__main__":
    unittest.main()
