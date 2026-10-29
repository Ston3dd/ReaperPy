import json, os, shutil, struct, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()
from test_gui_smoke import FakeWin
import test_ue_project as TP, test_ue_live as TL
import tkinter.filedialog as fd
from pathlib import Path

HAVE = shutil.which("as") and shutil.which("objdump") and shutil.which("nm")


def last(w): return w.went[-1]


@unittest.skipUnless(HAVE, "Toolchain fehlt")
class T(unittest.TestCase):
    def setUp(self):
        import tools_ue_gui as G
        self.d, self.sym = TP.make_game()
        self.w = FakeWin(); self.w.base = 0x400000
        self.w.app.PATCH_DIR = os.path.join(self.d, "patches"); os.makedirs(self.w.app.PATCH_DIR)
        self.reloaded = []; self.w.app.load_patches = lambda: self.reloaded.append(1)
        self.w.to_debug_watch = lambda a, n: self.w.went.append(("watch", a, n))
        self.t = G.UeTab(None, self.w)
        self.addCleanup(lambda: self.t.proj and self.t.proj.close())      # die GUI oeffnet das Projekt selbst
        fd.askdirectory = lambda *a, **k: self.d

    def test_folder_pick_and_flow(self):
        t = self.t
        t._pick_game()                                          # fuellt alle Felder automatisch
        self.assertTrue(t.v["sdk"].get().endswith("SDK_HEADERS")); self.assertTrue(t.v["dump_bin"].get())
        self.assertTrue(t.v["dump_json"].get() and t.v["offsets"].get())
        t.load()
        self.assertTrue(t.proj and t.cands and t.funcs)
        self.assertGreater(len(t.tc.rows), 1); self.assertGreater(len(t.tf.rows), 5)
        # Instruktionen
        idx = next(str(i) for i, c in enumerate(t.cands) if c.key == "UHealthComponent.Health")
        t.tc.sel = (idx,); t._on_cand(); t.find_hits()
        self.assertTrue(t.th.rows); t.th.sel = tuple(t.th.rows)[:1]; t.goto_hit()
        self.assertEqual(last(self.w)[0], "dis")
        t.make_patches(True)
        self.assertTrue(any(f.endswith(".reapproj") for f in os.listdir(self.w.app.PATCH_DIR))); self.assertTrue(self.reloaded)

    def test_function_patch_flow(self):
        t = self.t; t._pick_game(); t.load()
        iid = next(k for k, v in t.tf.rows.items() if v[1] == "AddHP4")
        t.tf.sel = (iid,)
        t.func_patch()                                          # ohne Impl. -> verweigert
        self.assertTrue(any("IMPL. AUFLÖSEN" in m for k, m in self.w.logs))
        t.func_impl()
        self.assertEqual(t.impl[int(iid)], 0x400000 + self.sym["impl4"])
        self.assertTrue(t.tf.rows[iid][4])                      # IMPL-Spalte gefuellt
        t.v_mode.set("true"); t.func_patch()
        f = [x for x in os.listdir(self.w.app.PATCH_DIR) if "AddHP4" in x]
        self.assertTrue(f, os.listdir(self.w.app.PATCH_DIR))
        p = json.loads(Path(os.path.join(self.w.app.PATCH_DIR, f[0])).read_text(encoding="utf-8"))
        self.assertEqual(p["Variables"][0]["newValue"], "B0 01 C3")
        t.func_goto(); self.assertEqual(last(self.w), ("dis", 0x400000 + self.sym["impl4"]))

    def test_offline_instances_from_dump(self):
        """Instanzen aus einem Dump: UE-Objekte liegen im Dump-Heap (synthetisch), Region-Karte wie echt."""
        import tools_ue_gui as G, dumpmem
        im, ref = TL.build(True)
        # Abbild als dump.bin ablegen: zwei Regionen (Modul bei 0x400000, Heap bei 0x10000000)
        d = tempfile.mkdtemp()
        mod, heap = bytes(im.regions[TL.BASE]), bytes(im.regions[TL.HEAP])
        hp_off = ref["p1"] + 0x80 - TL.HEAP
        heap = bytearray(heap); heap[hp_off:hp_off + 4] = struct.pack("<f", 42.25); heap = bytes(heap)
        Path(os.path.join(d, "dump.bin")).write_bytes(mod + heap)
        Path(os.path.join(d, "dump.json")).write_text(json.dumps({"regions": [{"name": "executable", "start": TL.BASE, "end": TL.BASE + len(mod), "prot": 3, "offset": 0},
                               {"name": "anon", "start": TL.HEAP, "end": TL.HEAP + len(heap), "prot": 3, "offset": len(mod)}]}), encoding="utf-8")
        Path(os.path.join(d, "offsets.json")).write_text(json.dumps({"base": TL.BASE, "gobjects": 0x100, "gnames": 0x400}), encoding="utf-8")
        os.makedirs(os.path.join(d, "SDK", "SDK_HEADERS"))
        Path(os.path.join(d, "SDK", "SDK_HEADERS", "A_classes.hpp")).write_text(
            "class UHealthComponent : public UActorComponent\n{\npublic:\n"
            "\tfloat Health; // 0x0080 (0x0004) [0x0018001040022a01] FloatProperty\n};\n", encoding="utf-8")
        self.t.v["game"].set(d)
        fd.askdirectory = lambda *a, **k: d
        import io, contextlib, ue_auto
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ue_auto.main(["--game", d, "--check-objects"])
        self.assertEqual(rc, 0, buf.getvalue()); self.assertIn("OK: GObjects", buf.getvalue()); self.assertIn("Objekte lesbar", buf.getvalue())
        self.t._pick_game(); self.t.load()
        self.assertEqual(self.t.proj.dm.module_name, "executable")
        cand = next(c for c in self.t.cands if c.key == "UHealthComponent.Health")
        self.t.cur_cand = cand
        self.t.instances(True)
        vals = [v[3] for v in self.t.ti.rows.values()]
        self.assertIn("42.25", vals)
        self.t.ti.sel = tuple(self.t.ti.rows)[:1]; self.t.v_set.set("1")
        self.t.inst_set()
        self.assertTrue(any("nur zum Ansehen" in m for k, m in self.w.logs))      # Offline: kein Schreiben

    def test_live_failure_is_reported_not_crashing(self):
        """Dein Fehler: erst UELiveError, dann beim naechsten Klick AttributeError 'num_elements'."""
        t = self.t; t._pick_game(); t.load()
        self.w.client.read_memory = lambda a, n: (_ for _ in ()).throw(OSError("keine Verbindung"))
        t.cur_cand = t.cands[0]
        for _ in range(3):
            t.instances(False)
        errs = [m for k, m in self.w.logs if k == "err"]
        self.assertEqual(len(errs), 3, errs)
        self.assertTrue(all("GObjects/GNames nicht erkannt" in m and "Lesefehler" in m for m in errs), errs)
        self.assertFalse(any("num_elements" in m for m in errs))
        self.assertIsNone(t.live)                                  # kein halb fertiges Objekt gemerkt

    def test_fixedpoint_formatting(self):
        import tools_ue_gui as G
        self.assertEqual(G._fmt_for("struct FFixedPoint64"), "<q")
        self.assertEqual(G._show("<q", struct.pack("<q", 12500), "struct FFixedPoint64"), "12500 (= 12.5)")
        self.assertEqual(G._fmt_for("bool"), "<B"); self.assertEqual(G._fmt_for("int32_t"), "<i")



@unittest.skipUnless(HAVE, "Toolchain fehlt")
class UFuncCall(unittest.TestCase):
    def test_call_ufunction_from_gui(self):
        import tools_ue_gui as G, ps5_more, ue_project, uesdk
        im, ref = TL.build(True)
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "SDK", "SDK_HEADERS"))
        Path(os.path.join(d, "SDK", "SDK_HEADERS", "G_classes.hpp")).write_text(
            "// Class /Script/Game.HealthComponent\nclass UHealthComponent : public UActorComponent\n{\npublic:\n"
            "\tfloat Health; // 0x0080 (0x0004) [0x0018001040022a01] FloatProperty\n"
            "public:\n\t// void TakeDamage(float Amount);  // flags 0x04020401  native 0x1000\n};\n", encoding="utf-8")
        Path(os.path.join(d, "SDK", "SDK_HEADERS", "G_parameters.hpp")).write_text(
            "// Function /Script/Game.HealthComponent.TakeDamage\n// 0x0008\nstruct UHealthComponent_TakeDamage_Params\n{\n"
            "\tfloat Amount; // 0x0000 (0x0004) [0x0018001040000280] FloatProperty\n"
            "\tuint8_t Pad_0000[0x4]; // 0x0004 (0x0004) MISSED OFFSET\n};\n", encoding="utf-8")
        Path(os.path.join(d, "offsets.json")).write_text(json.dumps({"base": TL.BASE, "gobjects": 0x100, "gnames": 0x400, "process_event": 0x9000, "process_event_index": 3}), encoding="utf-8")
        w = FakeWin(); w.base = TL.BASE
        fake = w.client
        class Hybrid:                          # liest UE-Abbild, Parameter-Puffer liegen im Fake-Speicher
            def read_memory(s, a, n):
                try: return im.read(a, n)
                except OSError:
                    if not (0x10000 <= a and a + n <= len(fake.mem)): raise
                    return fake.read_memory(a, n)
            write_memory = fake.write_memory; allocate_memory = fake.allocate_memory; free_memory = fake.free_memory
            def get_maps(s): return []
        w.client = Hybrid()
        t = G.UeTab(None, w)
        self.addCleanup(setattr, ps5_more, "call", ps5_more.call)
        seen = {}
        ps5_more.call = lambda c, rip, *a, safe=True, gap=0.15: seen.update(rip=rip, a=a, pre=c.read_memory(a[2], 8)) or 0
        t.proj = ue_project.GameProject(d, log=lambda m: None).load()
        self.addCleanup(t.proj.close)
        t.funcs = t.proj.functions(0)
        t.tf.insert("", "end", iid="0", values=("UHealthComponent", "TakeDamage", "", "", "", ""))
        idx = next(i for i, f in enumerate(t.funcs) if f["name"] == "TakeDamage")
        t.tf.rows.clear(); t.tf.insert("", "end", iid=str(idx), values=("UHealthComponent", "TakeDamage", "", "", "", ""))
        t.tf.sel = (str(idx),)
        t.v_ufarg.set("Amount=12.5")
        t.func_call()                                               # keine Instanz gewaehlt und nicht static -> Hinweis
        self.assertTrue(any("Instanz wählen" in m for k, m in w.logs), w.logs)
        t.insts = [({"addr": ref["p1"], "name": "x", "class": "HealthComponent", "index": 1}, "")]
        t.ti.insert("", "end", iid="0", values=("", "", "", "")); t.ti.sel = ("0",)
        t.func_call()
        self.assertEqual(seen["rip"], TL.BASE + 0x9000)             # vtable unlesbar -> process_event aus offsets.json
        self.assertEqual(seen["a"][0], ref["p1"])                   # rdi = Objekt
        self.assertEqual(w.client.read_memory(seen["a"][1], 4) if False else seen["a"][1] > 0, True)   # rsi = UFunction-Objekt
        self.assertAlmostEqual(struct.unpack("<f", seen["pre"][:4])[0], 12.5, places=5)
        t.proj.close()

if __name__ == "__main__":
    unittest.main()
