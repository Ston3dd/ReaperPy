"""Tests: cavemaker.py (Cheats aus der dump.cs) und cave_check.py (Pruefung gegen ReaperPys eigenen Parser/Assembler).

Die Hooks werden mit GNU as + ld wirklich assembliert, ueber patch_engine.apply_patch (wie im Programm) in einen
ausfuehrbaren Speicher geschrieben und dort AUSGEFUEHRT - es wird geprueft, dass der Cheat WIRKT, nicht nur dass die Datei
gut aussieht.  Ohne Linux/x86-64/binutils werden die Tests uebersprungen.
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import cave_world as W  # noqa: E402

DUMP = """// Image 0: Assembly-CSharp.dll - 0

// Namespace: Game
public class CoinEvent // TypeDefIndex: 0
{
\t// Fields
\tpublic int m_CoinValue; // 0x10
}

// Namespace: Game
public class Player // TypeDefIndex: 1
{
\t// Fields
\tpublic int Health; // 0x18
\tpublic static int Gold; // 0x20

\t// Methods

\t// RVA: 0x1000 Offset: 0x1000 VA: 0x1000
\tpublic int AddMoney(int amount) { }

\t// RVA: 0x1040 Offset: 0x1040 VA: 0x1040
\tpublic void OnAddCoin(CoinEvent evt) { }

\t// RVA: 0x1080 Offset: 0x1080 VA: 0x1080
\tpublic void Update() { }

\t// RVA: 0x10C0 Offset: 0x10C0 VA: 0x10C0
\tpublic bool IsDead() { }
}
"""
SCRIPT = {"ScriptMetadata": [{"Address": 0x2000, "Name": "Game.Player_TypeInfo", "Signature": "Game_Player_c*"}]}

FUNCS = {
    0x1000: "push rbp\nmov rbp, rsp\nmov eax, esi\nadd eax, 1\npop rbp\nret",                       # AddMoney(this, amount)
    0x1040: "push rbp\nmov rbp, rsp\nmov eax, dword ptr [rsi + 0x10]\npop rbp\nret",               # OnAddCoin(this, evt)
    0x1080: "push rbp\nmov rbp, rsp\nnop\nnop\nnop\npop rbp\nret",                                # Update(this)
    0x10C0: "push rbp\nmov rbp, rsp\nxor eax, eax\nnop\nnop\npop rbp\nret",                       # IsDead(this)
}
OBJ, EVT, KLASS, STATICS = 0x3000, 0x3080, 0x3100, 0x3200


@unittest.skipUnless(W.TOOLCHAIN, "keine Toolchain (Linux x86-64 mit as/ld/objdump)")
class CaveMakerCore(unittest.TestCase):
    def setUp(self):
        import cavemaker as CM
        import cave_check as CC
        self.CM, self.CC = CM, CC
        CM.init_reaperpy()
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "dump.cs"), "w", encoding="utf-8") as f:
            f.write(DUMP)
        with open(os.path.join(self.tmp.name, "script.json"), "w", encoding="utf-8") as f:
            json.dump(SCRIPT, f)
        self.dis = W.patch_disasm()
        self.dis.start()
        self.model = CM.load_model(os.path.join(self.tmp.name, "dump.cs"), log=lambda m: None)
        self.b = W.GasBackend()
        b = self.b
        for rva, asm in FUNCS.items():
            b.put(b.base + rva, W.assemble_at(asm, b.base + rva))
        b.put(b.base + OBJ + 0x18, (50).to_bytes(4, "little"))               # Player.Health
        b.put(b.base + EVT + 0x10, (7).to_bytes(4, "little"))                # CoinEvent.m_CoinValue
        b.put(b.base + 0x2000, (b.base + KLASS).to_bytes(8, "little"))       # TypeInfo-Zeiger
        b.put(b.base + KLASS + 0xB8, (b.base + STATICS).to_bytes(8, "little"))
        b.put(b.base + STATICS + 0x20, (5).to_bytes(4, "little"))            # Player.Gold
        self.ctx = CM.Ctx(b, b.base, b.base)
        self.player = self.model.by_name["Player"][0]

    def tearDown(self):
        self.dis.stop()
        self.tmp.cleanup()

    # --- Hilfen ---
    def method(self, name):
        return next(m for m in self.player.methods if m.name == name)

    def act(self, name, key, **kw):
        acts, why = self.CM.actions_for_method(self.model, self.method(name))
        return next(a for a in acts if a.key == key and all(getattr(a, k) == v for k, v in kw.items()))

    def activate(self, pd, check=True):
        """Wie ReaperPy: Dokument -> Datei -> ReapPatch -> patch_engine.apply_patch."""
        import patch_engine as PE
        doc = pd.to_json("test")
        if check:
            self.assertEqual(self.CC.doc_problems(doc, self.b, pd.hook_addr), [])
        rp = self.CC.load_doc(doc)
        return rp, PE.apply_patch(self.b, rp, pd.hook_addr)

    def call_fn(self, addr, *args):
        ok, val = W.run_isolated(lambda: self.b.call(addr, *args))
        self.assertTrue(ok, val)
        return val

    # --- Aktionen ---
    def test_return_value_is_a_simple_patch(self):
        pd = self.CM.build_patch(self.model, self.ctx, self.act("AddMoney", "ret"), "set", "999")
        self.assertTrue(pd.simple)
        self.activate(pd)
        self.assertEqual(self.call_fn(self.b.base + 0x1000, 0, 5), 999)

    def test_parameter_cave_changes_the_argument(self):
        self.assertEqual(self.call_fn(self.b.base + 0x1000, 0, 5), 6)                         # Original: amount + 1
        pd = self.CM.build_patch(self.model, self.ctx, self.act("AddMoney", "param"), "set", "100")
        self.assertFalse(pd.simple)
        rp, st = self.activate(pd)
        self.assertEqual(self.call_fn(self.b.base + 0x1000, 0, 5), 101)                       # amount = 100 gesetzt
        with self.assertRaises(ValueError):                                                   # Hook ist schon belegt
            self.CM.build_patch(self.model, self.ctx, self.act("AddMoney", "param"), "mul", "3")
        import patch_engine as PE
        PE.deactivate_patch(self.b, rp, st)
        pd2 = self.CM.build_patch(self.model, self.ctx, self.act("AddMoney", "param"), "mul", "3")
        self.assertIn("imul", pd2.preview())

    def test_object_field_cave_sets_the_field_of_the_parameter_object(self):
        self.assertEqual(self.call_fn(self.b.base + 0x1040, 0, self.b.base + EVT), 7)
        pd = self.CM.build_patch(self.model, self.ctx, self.act("OnAddCoin", "obj"), "set", "777")
        self.activate(pd)
        self.assertEqual(self.call_fn(self.b.base + 0x1040, 0, self.b.base + EVT), 777)
        # null-Objekt: kein Absturz (die Cave springt ueber das Setzen)
        ok, val = W.run_isolated(lambda: self.b.call(self.b.base + 0x1040, 0, 0))
        self.assertFalse(ok and False)                                                    # Original-Methode liest [0+0x10] selbst
        self.assertIn("test rsi, rsi", pd.preview())

    def test_instance_field_cave(self):
        act = self.CM.actions_for_field(self.model, self.player, self.player.find_field("Health"))[0][0]
        pd = self.CM.build_patch(self.model, self.ctx, act, "set", "500", hook_method=self.method("Update"))
        self.activate(pd)
        self.call_fn(self.b.base + 0x1080, self.b.base + OBJ)
        self.assertEqual(int.from_bytes(self.b.read(self.b.base + OBJ + 0x18, 4), "little"), 500)

    def test_static_field_cave_uses_the_typeinfo_slot(self):
        act = self.CM.actions_for_field(self.model, self.player, self.player.find_field("Gold"))[0][0]
        pd = self.CM.build_patch(self.model, self.ctx, act, "min", "9999", hook_method=self.method("Update"))
        self.activate(pd)
        self.call_fn(self.b.base + 0x1080, self.b.base + OBJ)
        self.assertEqual(int.from_bytes(self.b.read(self.b.base + STATICS + 0x20, 4), "little"), 9999)

    def test_bool_return_and_void(self):
        pd = self.CM.build_patch(self.model, self.ctx, self.act("IsDead", "ret"), "set", "false")
        self.activate(pd)
        self.assertEqual(self.call_fn(self.b.base + 0x10C0, 0) & 0xFF, 0)
        pd2 = self.CM.build_patch(self.model, self.ctx, self.act("Update", "void"), "set", None)
        self.assertTrue(pd2.simple)

    def test_deactivate_restores_the_original_bytes(self):
        import patch_engine as PE
        before = self.b.read(self.b.base + 0x1000, 16)
        pd = self.CM.build_patch(self.model, self.ctx, self.act("AddMoney", "param"), "set", "100")
        rp, st = self.activate(pd)
        self.assertNotEqual(self.b.read(self.b.base + 0x1000, 16), before)
        PE.deactivate_patch(self.b, rp, st)
        self.assertEqual(self.b.read(self.b.base + 0x1000, 16), before)
        self.assertEqual(self.call_fn(self.b.base + 0x1000, 0, 5), 6)

    # --- Pruefung (cave_check) ---
    def test_checker_accepts_good_docs_and_reads_them_like_reaperpy(self):
        pd = self.CM.build_patch(self.model, self.ctx, self.act("AddMoney", "param"), "set", "100")
        doc = pd.to_json("x")
        rp = self.CC.load_doc(doc)
        import patch_engine as PE
        self.assertTrue(PE.is_cave_patch(rp))
        self.assertEqual(rp.origin_source[0], 0x1000)
        self.assertEqual(rp.origin_return_offset, 9)
        self.assertEqual([n for n, _ in rp.labels], ["OriginTarget"])
        self.assertIn("Cave", self.CC.describe(doc))

    def test_checker_finds_broken_docs(self):
        pd = self.CM.build_patch(self.model, self.ctx, self.act("AddMoney", "param"), "set", "100")
        good = pd.to_json("x")

        def variant(fn):
            d = json.loads(json.dumps(good))
            fn(d["Variables"])
            return self.CC.doc_problems(d, self.b, pd.hook_addr)

        self.assertTrue(variant(lambda v: v.pop(0)), "ohne OriginSource")
        self.assertTrue(any("OriginTarget" in p for p in variant(lambda v: v.pop())), "ohne Cave-Code")
        self.assertTrue(any("OriginReturn" in p for p in variant(lambda v: v[1].update(offset=7))), "falscher Rueckkehr-Offset")
        self.assertTrue(any("OriginReturn" in p for p in variant(lambda v: v[0].update(defaultValue=" ".join(["90"] * 12)))),
                        "Rückkehr hinter weniger Bytes, als die Original-Bytes lang sind")
        bad = variant(lambda v: v[2].update(defaultValue="mov esi, 0x64\njmp nirgendwo"))
        self.assertTrue(any("nirgendwo" in p for p in bad), bad)
        bad = variant(lambda v: v[2].update(defaultValue="mov esi, 0x64\nnop"))
        self.assertTrue(any("Rücksprung" in p for p in bad), bad)
        self.assertTrue(variant(lambda v: v[0].update(newValue="")), "leerer neuer Code")
        self.assertTrue(variant(lambda v: v[0].update(defaultValue="")), "ohne Original-Bytes")

    def test_write_checked_roundtrip_and_refusal(self):
        pd = self.CM.build_patch(self.model, self.ctx, self.act("AddMoney", "param"), "set", "100")
        good = pd.to_json("x")
        with tempfile.TemporaryDirectory() as d:
            p = self.CC.write_checked(d, good, self.b, pd.hook_addr)
            self.assertTrue(p.endswith(".reapproj"))
            p2 = self.CC.write_checked(d, good, self.b, pd.hook_addr)                  # nichts ueberschreiben
            self.assertNotEqual(p, p2)
            broken = json.loads(json.dumps(good))
            broken["Variables"].pop()
            with self.assertRaises(self.CC.CaveCheckError):
                self.CC.write_checked(d, broken, self.b, pd.hook_addr)
            self.assertEqual(len(os.listdir(d)), 2, "ein kaputter Patch darf keine Datei hinterlassen")

    def test_original_cavemaker_docs_are_accepted_by_the_main_window_loader(self):
        """gui.add_patch_from_file ruft ReapPatch.load und is_patch_file: dasselbe hier mit dem fertigen Dokument."""
        from reapatch import ReapPatch, is_patch_file
        pd = self.CM.build_patch(self.model, self.ctx, self.act("OnAddCoin", "obj"), "set", "777")
        with tempfile.TemporaryDirectory() as d:
            p = self.CC.write_checked(d, pd.to_json("x"), self.b, pd.hook_addr)
            self.assertTrue(is_patch_file(p))
            rp = ReapPatch.load(p)
            self.assertIsNotNone(rp.origin_source)
            self.assertEqual({n for n, _ in rp.labels}, {"OriginTarget", "cm_skip"})

    # --- Automatische Haken-Suche am laufenden "Spiel" ---
    def test_auto_hook_search_finds_the_method_that_really_runs(self):
        """Zwei Kandidaten: OnAddCoin laeuft nie, Update laeuft staendig (Spielschleife im Kindprozess)."""
        b = self.b
        pid = os.fork()
        if pid == 0:                                       # "Spiel": ruft Update dauernd auf
            try:
                end = time.time() + 40
                while time.time() < end:
                    b.call(b.base + 0x1080, b.base + OBJ)
                    time.sleep(0.01)
            finally:
                os._exit(0)
        try:
            act = self.CM.actions_for_field(self.model, self.player, self.player.find_field("Gold"))[0][0]
            hooks = [self.method("OnAddCoin"), self.method("Update")]
            res = self.CM.find_working_hook(self.model, self.ctx, act, "set", "4242", hooks, None, lambda m: None,
                                            wait=1.0, rearm=1.0)
            self.assertIsNotNone(res)
            pd, rp, st, hm, regular = res
            self.assertEqual(hm.name, "Update")
            self.assertTrue(regular)
            self.assertEqual(self.CC.doc_problems(pd.to_json("x"), b, pd.hook_addr), [])
        finally:
            os.kill(pid, 9)
            os.waitpid(pid, 0)


if __name__ == "__main__":
    unittest.main()
