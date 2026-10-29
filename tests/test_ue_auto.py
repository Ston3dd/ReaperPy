"""Ende-zu-Ende: SDK-Header + Offsets + (echter Maschinencode) Dump -> Bericht + Patch-Dateien."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ue_auto as A, ue_instr as U, uesdk, uecheat, reapatch
from pathlib import Path

HAVE = shutil.which("as") and shutil.which("objdump")
SDK = """class UHealthComponent final : public UActorComponent
{
public:
	float                                        Health;                                            // 0x0348(0x0004)(Edit)
	float                                        MaxHealth;                                         // 0x034C(0x0004)(Edit)
};
class UWeaponComponent : public UActorComponent
{
public:
	int32                                        CurrentAmmo;                                       // 0x0200(0x0004)(Edit)
	int32                                        ClipSize;                                          // 0x0204(0x0004)(Edit)
};
class UWalletComponent : public UActorComponent
{
public:
	int32                                        Gold;                                              // 0x0100(0x0004)(Edit)
};
"""

@unittest.skipUnless(HAVE, "Toolchain fehlt")
class T(unittest.TestCase):
    def test_pipeline(self):
        import test_ue_instr as TI
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "sdk")); Path(os.path.join(d, "sdk", "Game_classes.hpp")).write_text(SDK, encoding="utf-8")
        Path(os.path.join(d, "Offsets.json")).write_text(json.dumps({"OFFSET_GOBJECTS": "0x1234"}), encoding="utf-8")
        dump = TI.build_dump(d)
        Path(os.path.join(d, "Dump.bin")).write_bytes(dump)
        sdk = uesdk.load(os.path.join(d, "sdk"), os.path.join(d, "Offsets.json"))
        self.assertEqual(sdk.offset("gobjects"), 0x1234)
        cands = uecheat.find_candidates(sdk, 8)
        self.assertEqual({c.member for c in cands}, {"Health", "CurrentAmmo", "Gold", "MaxHealth", "ClipSize"} & {c.member for c in cands})
        dm = A.load_dump(os.path.join(d, "Dump.bin"))
        dis = U.ObjdumpDisasm()
        by = A.analyze(sdk, dm, dis, cands, 0x400000, 0)
        self.assertIn("UHealthComponent.Health", by)
        self.assertEqual(by["UHealthComponent.Health"][0].ins.mnem, "movss")
        self.assertEqual(by["UWeaponComponent.CurrentAmmo"][0].ins.mnem, "sub")
        self.assertEqual(by["UWalletComponent.Gold"][0].ins.mnem, "mov")
        out = os.path.join(d, "patches")
        hits = [by["UHealthComponent.Health"][0], by["UWeaponComponent.CurrentAmmo"][0], by["UWalletComponent.Gold"][0]]
        files = A.write_patches(out, dm, dis, hits, 0x400000, log=lambda m: None)
        self.assertGreaterEqual(len(files), 5)                    # 3 NOP + Caves (Health, Gold)
        # jede erzeugte Datei muss von ReaperPys eigenem Loader gelesen werden
        loaded = {}
        for fn in files:
            p = reapatch.ReapPatch.load(os.path.join(out, fn))
            self.assertIsNotNone(p.origin_source, fn)
            loaded[fn] = p
        caves = [p for p in loaded.values() if p.labels]
        self.assertEqual(len(caves), 2)
        import patch_engine
        for p in caves:
            self.assertTrue(patch_engine.is_cave_patch(p))        # Engine erkennt sie als Cave
            self.assertEqual(p.origin_return_offset >= 8, True)
            self.assertIn("OriginReturn", p.labels[0][1])
        nops = [p for p in loaded.values() if not p.labels]
        self.assertFalse(any(patch_engine.is_cave_patch(p) for p in nops))
        for p in nops:
            off, default, new = p.origin_source
            self.assertTrue(set(new.split()) == {"90"})

    def test_cli(self):
        import test_ue_instr as TI, io, contextlib
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "sdk"))
        Path(os.path.join(d, "sdk", "a.hpp")).write_text(SDK, encoding="utf-8")
        Path(os.path.join(d, "Dump.bin")).write_bytes(TI.build_dump(d))
        cwd = os.getcwd(); os.chdir(d)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                rc = A.main(["--sdk", os.path.join(d, "sdk"), "--dump", os.path.join(d, "Dump.bin"), "--disasm", "objdump",
                             "--out", os.path.join(d, "o")])
            self.assertEqual(rc, 0)
            self.assertIn("UHealthComponent.Health", buf.getvalue())
            self.assertTrue(os.path.exists(os.path.join(d, "ue_report.json")))
            self.assertTrue(os.listdir(os.path.join(d, "o")))
        finally:
            os.chdir(cwd)

if __name__ == "__main__":
    unittest.main()
