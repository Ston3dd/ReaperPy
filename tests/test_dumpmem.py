import json, os, shutil, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import dumpmem as D

REGIONS = [
    {"name": "executable", "start": 0x400000, "end": 0x500000, "prot": 5, "offset": 0},
    {"name": "executable", "start": 0x500000, "end": 0x580000, "prot": 1, "offset": 0x100000},
    {"name": "executable", "start": 0x700000, "end": 0x710000, "prot": 3, "offset": 0x180000},
    {"name": "libc.prx", "start": 0x80000000, "end": 0x80010000, "prot": 5, "offset": 0x190000},
]
FX = os.path.join(os.path.dirname(__file__), "fixtures")


def make_dump(d, code=b""):
    total = 0x1A0000
    buf = bytearray(total)
    buf[0:len(code)] = code
    buf[0x100000:0x100008] = b"DATA1234"
    buf[0x180000:0x180008] = (0x1122334455667788).to_bytes(8, "little")
    p = os.path.join(d, "dump.bin"); open(p, "wb").write(buf)
    j = os.path.join(d, "dump.json"); json.dump({"name": "eboot.bin", "title_id": "PPSA00000", "regions": REGIONS}, open(j, "w"))
    return p, j


class T(unittest.TestCase):
    def test_read_and_map(self):
        d = tempfile.mkdtemp(); p, j = make_dump(d)
        dm = D.DumpMemory(p, j)
        self.assertEqual(dm.base, 0x400000); self.assertEqual(dm.module_name, "executable")
        self.assertEqual(dm.read(0x500000, 8), b"DATA1234")
        self.assertEqual(int.from_bytes(dm.read(0x700000, 8), "little"), 0x1122334455667788)
        self.assertIsNone(dm.va_to_off(0x600000))                       # Luecke
        with self.assertRaises(OSError): dm.read(0x600000, 4)
        with self.assertRaises(OSError): dm.read(0x57FFFC, 8)           # ragt hinter die Region in eine Luecke
        dm.close()

    def test_cross_region_contiguous(self):
        d = tempfile.mkdtemp(); p, j = make_dump(d)
        dm = D.DumpMemory(p, j)
        # 0x4FFFF8..0x500008: Code-Ende (offset 0xFFFF8) und Daten-Anfang (offset 0x100000) liegen luckenlos
        self.assertEqual(dm.read(0x4FFFF8, 16)[8:], b"DATA1234")
        buf, lo, hi, base_va = dm.code_view()
        self.assertEqual((lo, hi, base_va), (0, 0x100000, 0x400000))
        dm.close()

    def test_native_convention(self):
        if not (shutil.which("as") and shutil.which("objcopy")):
            self.skipTest("as fehlt")
        d = tempfile.mkdtemp()
        asm = ".intel_syntax noprefix\n.text\n" + "".join(
            f".p2align 4,0xCC\nf{i}:\n  push rbx\n  mov eax, {i}\n  pop rbx\n  ret\n" for i in range(40))
        open(os.path.join(d, "t.s"), "w").write(asm)
        subprocess.run(["as", "--64", "-o", os.path.join(d, "t.o"), os.path.join(d, "t.s")], check=True)
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text", os.path.join(d, "t.o"), os.path.join(d, "t.bin")], check=True)
        code = b"\xCC" * 16 + open(os.path.join(d, "t.bin"), "rb").read()
        p, j = make_dump(d, code)
        dm = D.DumpMemory(p, j)
        starts = [i for i in range(16, len(code), 16) if code[i - 1] in (0xCC, 0xC3) and code[i] != 0xCC][:30]
        rvas = starts                                                  # Position = RVA (Base 0x400000, Offset 0)
        conv, r, v = D.native_convention(dm, rvas, 0x400000)
        self.assertEqual(conv, "rva"); self.assertGreater(r, 0.9)
        conv, r, v = D.native_convention(dm, [a + 0x400000 for a in rvas], 0x400000)
        self.assertEqual(conv, "va")
        dm.close()

    def test_find_game_files_real_layout(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "SDK", "SDK_HEADERS")); os.makedirs(os.path.join(d, "Anderes Spiel"))
        for n in ("A_classes.hpp", "A_structs.hpp", "A_parameters.hpp"):
            open(os.path.join(d, "SDK", "SDK_HEADERS", n), "w").write("//")
        for n in ("offsets.json", "dump.json", "GObjects.txt", "dump.bin.engine.json"):
            open(os.path.join(d, n), "w").write("{}")
        open(os.path.join(d, "dump.bin"), "wb").write(b"0")
        f = D.find_game_files(d)
        self.assertTrue(f["sdk"].endswith("SDK_HEADERS")); self.assertTrue(f["dump_bin"].endswith("dump.bin"))
        for k in ("offsets", "dump_json", "gobjects", "engine"):
            self.assertTrue(f[k], k)

    def test_find_game_files_ps4_unreal_dumper_layout(self):
        """dumps/<TitleID>/{dump.bin,dump.json,dump.bin.engine.json} + SDK/{offsets.json,GObjects.txt,SDK_HEADERS}"""
        d = tempfile.mkdtemp(); g = os.path.join(d, "dumps", "CUSA31820")
        os.makedirs(os.path.join(g, "SDK", "SDK_HEADERS"))
        for n in ("Engine_classes.hpp", "Engine_structs.hpp", "Engine_parameters.hpp"):
            open(os.path.join(g, "SDK", "SDK_HEADERS", n), "w").write("//")
        for n in ("offsets.json", "GObjects.txt", "GameDefines.hpp"):
            open(os.path.join(g, "SDK", n), "w").write("{}")
        for n in ("dump.json", "dump.bin.engine.json", "rpc_stub.txt"):
            open(os.path.join(g, n), "w").write("{}")
        open(os.path.join(g, "dump.bin"), "wb").write(b"0")
        f = D.find_game_files(d)                                   # Eltern-Ordner reicht
        self.assertTrue(f["sdk"].endswith("SDK_HEADERS"))
        self.assertTrue(f["offsets"].endswith(os.path.join("SDK", "offsets.json")))
        self.assertTrue(f["dump_bin"].endswith("dump.bin") and f["dump_json"] and f["gobjects"] and f["engine"])

    def test_sdk_subfolder_finds_dump_in_parent(self):
        """Dein Fall: --game ...\\dumps\\PPSA33286\\SDK  (dump.bin liegt eine Ebene darueber)"""
        d = tempfile.mkdtemp(); g = os.path.join(d, "dumps", "PPSA33286")
        os.makedirs(os.path.join(g, "SDK", "SDK_HEADERS"))
        open(os.path.join(g, "SDK", "SDK_HEADERS", "A_classes.hpp"), "w").write("//")
        for n in ("offsets.json", "GObjects.txt"):
            open(os.path.join(g, "SDK", n), "w").write("{}")
        for n in ("dump.json", "dump.bin.engine.json"):
            open(os.path.join(g, n), "w").write("{}")
        open(os.path.join(g, "dump.bin"), "wb").write(b"0")
        f = D.find_game_files(os.path.join(g, "SDK"))
        self.assertTrue(f["dump_bin"].endswith("dump.bin") and f["dump_json"].endswith("dump.json") and f["engine"])
        self.assertTrue(f["offsets"].endswith("offsets.json") and f["sdk"].endswith("SDK_HEADERS"))

    def test_real_fixture_regions(self):
        regs = json.load(open(os.path.join(FX, "dump_excerpt.json")))["regions"]
        self.assertEqual(regs[0]["start"], 0x400000)
        self.assertEqual(regs[1]["offset"], 0x6178000)

if __name__ == "__main__":
    unittest.main()
