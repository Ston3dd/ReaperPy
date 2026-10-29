"""GameProject Ende-zu-Ende auf einem synthetischen Spielordner im Layout des PS5-Dumpers."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import test_ue_funcs as TF, ue_project as P, ue_instr as U, ue_auto
from pathlib import Path

HAVE = shutil.which("as") and shutil.which("objdump") and shutil.which("nm")

DAMAGE = """
.p2align 4,0xCC
take_damage_impl:
  push rbx
  mov rbx, rdi
  movss xmm1, dword ptr [rbx+0x348]
  subss xmm1, xmm0
  movss dword ptr [rbx+0x348], xmm1
  movss xmm3, dword ptr [rbx+0x34C]
  pop rbx
  ret
.p2align 4,0xCC
"""


def make_game():
    code, sym = TF.build(TF.THUNKS + DAMAGE)
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "SDK", "SDK_HEADERS"))
    fn = "".join(f"\t// void AddHP{i}(float Amount);  // flags 0x04020401  native {sym[f'thunk{i}']:#x}\n" for i in range(12))
    hdr = ("// Class /Script/Game.HealthComponent\n// 0x0020 (0x0348 - 0x0368) CastFlags 0x0\n"
           "class UHealthComponent : public UActorComponent\n{\npublic:\n"
           "\tfloat                                              Health;                        // 0x0348 (0x0004) [0x0018001040022a01] FloatProperty\n"
           "\tfloat                                              MaxHealth;                     // 0x034c (0x0004) [0x0018001040022a01] FloatProperty\n"
           "\tbool                                               bIsEnableMuteki;               // 0x0350 (0x0001) [0x0018001040022a21] BoolProperty\n\npublic:\n" + fn + "};\n")
    Path(os.path.join(d, "SDK", "SDK_HEADERS", "Game_classes.hpp")).write_bytes(hdr.replace("\n", "\r\n").encode("utf-8"))
    Path(os.path.join(d, "offsets.json")).write_text(json.dumps({"title": "PPSA00000", "base": 0x400000, "gnames": 0x1000, "gobjects": 0x2000,
               "offsets": {"UObject_Class": 16, "UObject_Name": 24, "UObject_Outer": 32}}), encoding="utf-8")
    pad = (len(code) + 0xFFF) & ~0xFFF
    total = pad + 0x1000
    Path(os.path.join(d, "dump.bin")).write_bytes(code.ljust(total, b"\0"))
    Path(os.path.join(d, "dump.json")).write_text(json.dumps({"title_id": "PPSA00000", "name": "eboot.bin", "regions": [
        {"name": "executable", "start": 0x400000, "end": 0x400000 + pad, "prot": 5, "offset": 0},
        {"name": "executable", "start": 0x400000 + pad, "end": 0x400000 + total, "prot": 3, "offset": pad}]}), encoding="utf-8")
    Path(os.path.join(d, "GObjects.txt")).write_text("[00000000] {0x300b060000} Package /Script/CoreUObject\r\n", encoding="utf-8")
    return d, sym


@unittest.skipUnless(HAVE, "Toolchain fehlt")
class T(unittest.TestCase):
    def test_everything(self):
        d, sym = make_game()
        proj = P.GameProject(d, log=lambda m: None)
        self.assertTrue(proj.files["sdk"].endswith("SDK_HEADERS") and proj.files["dump_bin"])
        proj.dis = None
        proj.load()
        self.assertEqual(proj.base, 0x400000); self.assertEqual(proj.title, "PPSA00000")
        self.assertEqual(proj.native_info[0], "rva")                      # automatisch erkannt
        self.assertEqual(proj.sdk.stats["members"], 3)
        # Kandidaten + Instruktionen
        cands = proj.candidates(8)
        keys = {c.key for c in cands}
        self.assertIn("UHealthComponent.Health", keys); self.assertIn("UHealthComponent.bIsEnableMuteki", keys)
        by = proj.analyze([c for c in cands if c.key == "UHealthComponent.Health"])
        h = by["UHealthComponent.Health"][0]
        self.assertEqual(h.ins.mnem, "movss"); self.assertEqual(h.rva, h.addr - 0x400000)
        # Funktionen: Thunk -> Implementierung
        fns = {f["name"]: f for f in proj.functions(0)}
        self.assertEqual(fns["AddHP5"]["native"], sym["thunk5"])
        impl = proj.resolve_impl(fns["AddHP5"])
        self.assertEqual(impl[0], 0x400000 + sym["impl5"])
        p = proj.function_patch(impl[0], "false", "UHealthComponent.AddHP5", with_aob=False)
        v = p["Variables"][0]
        self.assertEqual(int(v["offset"], 16), sym["impl5"]); self.assertEqual(v["newValue"], "31 C0 C3")
        self.assertEqual(bytes.fromhex(v["defaultValue"].replace(" ", ""))[:1], b"\xB8")   # mov eax, imm32
        proj.close()

    def test_va_convention_detected(self):
        d, sym = make_game()
        # Header mit VAs statt RVAs
        p = os.path.join(d, "SDK", "SDK_HEADERS", "Game_classes.hpp")
        t = Path(p).read_bytes().decode("utf-8")
        import re
        t = re.sub(r"native (0x[0-9a-f]+)", lambda m: f"native {int(m.group(1), 16) + 0x400000:#x}", t)
        Path(p).write_bytes(t.encode("utf-8"))
        proj = P.GameProject(d, log=lambda m: None).load()
        self.addCleanup(proj.close)
        self.assertEqual(proj.native_info[0], "va")
        fns = {f["name"]: f for f in proj.functions(0)}
        self.assertEqual(proj.resolve_impl(fns["AddHP2"])[0], 0x400000 + sym["impl2"])

    def test_without_dump(self):
        d, _ = make_game(); os.remove(os.path.join(d, "dump.bin"))
        proj = P.GameProject(d, log=lambda m: None).load()
        self.addCleanup(proj.close)
        self.assertIsNone(proj.dm)
        self.assertTrue(proj.candidates(8))
        with self.assertRaises(RuntimeError): proj.code()



@unittest.skipUnless(HAVE, "Toolchain fehlt")
class CliGame(unittest.TestCase):
    def test_cli_game(self):
        import io, contextlib
        d, sym = make_game()
        cwd = os.getcwd(); os.chdir(d)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = ue_auto.main(["--game", d, "--min-score", "8", "--functions", "5", "--out", os.path.join(d, "P"),
                                   "--func-patch", "UHealthComponent.AddHP3:false"])
            txt = out.getvalue()
            self.assertEqual(rc, 0, txt)
            self.assertIn("native-Adressen: RVA", txt)
            self.assertIn("UHealthComponent.Health", txt)
            self.assertIn("Impl RVA", txt)
            files = os.listdir(os.path.join(d, "P"))
            self.assertTrue(any("AddHP3" in f for f in files), files)
            rep = json.loads(Path(os.path.join(d, "ue_report.json")).read_text(encoding="utf-8"))
            self.assertTrue(rep["functions"] and rep["candidates"])
        finally:
            os.chdir(cwd)

if __name__ == "__main__":
    unittest.main()
