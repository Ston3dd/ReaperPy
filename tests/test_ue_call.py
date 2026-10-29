import os, struct, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import uesdk, ue_call as K, ue_live as L, test_ue_live as TL
from pathlib import Path

FX = os.path.join(os.path.dirname(__file__), "fixtures")
PARAMS = uesdk.parse_params_text(Path(os.path.join(FX, "engine_params_excerpt.hpp")).read_text(encoding="utf-8"))
SET = PARAMS["/Script/Engine.GameplayStatics.SetGlobalTimeDilation"]
LOC = PARAMS["/Script/Engine.Actor.K2_GetActorLocation"]


class Mem:
    def __init__(self): self.m = bytearray(0x100000); self.freed = []; self.next = 0x80000
    def read_memory(self, a, n): return bytes(self.m[a:a + n])
    def write_memory(self, a, d): self.m[a:a + len(d)] = d
    def allocate_memory(self, n): a = self.next; self.next += n + 0x40; return a
    def free_memory(self, a, n): self.freed.append(a)


class T(unittest.TestCase):
    def test_parse_real_params(self):
        self.assertEqual(SET.size, 0x10)
        self.assertEqual([(p.name, p.offset) for p in SET.params], [("WorldContextObject", 0), ("TimeDilation", 8)])
        self.assertTrue(LOC.params[0].pflags & uesdk.CPF_RETURN)

    def test_encode(self):
        b = K.encode_params(SET, K.parse_assignments("TimeDilation=0.3 WorldContextObject=0x1038e68080"))
        self.assertEqual(len(b), 0x10)
        self.assertEqual(struct.unpack_from("<Q", b, 0)[0], 0x1038e68080)
        self.assertAlmostEqual(struct.unpack_from("<f", b, 8)[0], 0.3, places=6)
        with self.assertRaises(K.CallError): K.encode_params(SET, {"Nope": "1"})
        with self.assertRaises(K.CallError): K.parse_assignments("kaputt")
        raw = K.encode_params(LOC, {"ReturnValue": "hex:" + "00" * 24})                # Struct nur ueber hex:
        self.assertEqual(len(raw), 0x18)
        with self.assertRaises(K.CallError): K.encode_params(LOC, {"ReturnValue": "1"})

    def test_decode_vector(self):
        raw = struct.pack("<3d", 1.5, -2.0, 300.25)
        out = dict(K.decode_outputs(LOC, raw))
        self.assertIn("1.5000, -2.0000, 300.2500", out["ReturnValue"])

    def test_process_event_from_vtable(self):
        m = Mem(); m.write_memory(0x1000, struct.pack("<Q", 0x2000)); m.write_memory(0x2000 + 8 * 77, struct.pack("<Q", 0x3086340 + 0x400000))
        self.assertEqual(K.process_event_addr(m.read_memory, 0x1000, 77), 0x3486340)
        self.assertEqual(K.process_event_addr(m.read_memory, 0x9999999, 77, fallback=0x1234), 0x1234)   # nicht lesbar -> Fallback
        with self.assertRaises(K.CallError): K.process_event_addr(lambda a, n: (_ for _ in ()).throw(OSError()), 1, 77)

    def test_call_flow(self):
        m = Mem(); seen = {}

        def caller(c, rip, obj, fn, params):
            seen.update(rip=rip, obj=obj, fn=fn, params=params, pre=c.read_memory(params, 0x10))
            c.write_memory(params, struct.pack("<3d", 7.0, 8.0, 9.0))               # "Spiel" schreibt den Rueckgabewert
            return 0
        out = K.call_ufunction(m, 0xAAAA, 0xBBBB, LOC, {}, 0x3486340, caller)
        self.assertEqual((seen["rip"], seen["obj"], seen["fn"]), (0x3486340, 0xAAAA, 0xBBBB))
        self.assertIn("7.0000, 8.0000, 9.0000", dict(out)["ReturnValue"])
        self.assertEqual(m.freed, [seen["params"]])                                  # Puffer wird freigegeben
        out = K.call_ufunction(m, 1, 2, SET, {"TimeDilation": "0.5"}, 0x1, lambda c, r, o, f, p: seen.update(pre=c.read_memory(p, 0x10)) or 0)
        self.assertAlmostEqual(struct.unpack_from("<f", seen["pre"], 8)[0], 0.5, places=6); self.assertEqual(out, [])

    def test_find_function_and_cdo(self):
        im, ref = TL.build(True)
        import test_ue_live
        sdk = uesdk.parse_header_text(TL.SDK_TXT)
        lv = L.UELive(im.read, TL.BASE, sdk, gobjects_rva=0x100, gnames_rva=0x400, log=lambda m: None); lv.setup(); lv.build_index()
        fn = lv.find_function("UHealthComponent", "TakeDamage")
        self.assertEqual(lv.name(fn), "TakeDamage")
        self.assertEqual(lv.find_function("BP_HealthComponent_C", "TakeDamage"), fn)      # aus Elternklasse
        self.assertIsNone(lv.find_function("UHealthComponent", "NichtDa"))
        self.assertEqual(lv.name(lv.default_object("UHealthComponent")), "Default__HealthComponent")

    def test_sdk_params_lookup_by_class_path(self):
        sdk = uesdk.parse_header_text("// Class /Script/Engine.GameplayStatics\nclass UGameplayStatics : public UBlueprintFunctionLibrary\n{\npublic:\n};\n")
        sdk.func_params.update(PARAMS)
        self.assertIs(sdk.params_for("UGameplayStatics", "SetGlobalTimeDilation"), SET)
        self.assertIsNone(sdk.params_for("UGameplayStatics", "Nix"))

if __name__ == "__main__":
    unittest.main()
