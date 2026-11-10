"""unity_cheatmenu + Tab UNITY > CHEAT-MENUE: Eintraege aus dem Dump, live schreiben/festhalten, Cave/Patch (Spiel nachgebaut)."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import il2cpp_dump as D
import test_unity_items as TU
import unity_cheatmenu as UM
from test_gui_smoke import FakeWin

BASE = 0x400000
OBJ = 0x7000_0000


def make_game(tmp):
    parts = ["// Image 0: Assembly-CSharp.dll - 0\n// Image 1: UnityEngine.CoreModule.dll - 50\n"]
    player = ("\tpublic float health; // 0x120\n\tpublic int gold; // 0x124\n\tpublic float stamina; // 0x128\n"
              "\tpublic int experience; // 0x12C\n\tpublic float healthRegenRate; // 0x130\n\tpublic bool isInvincible; // 0x134\n"
              "\tpublic float hunger; // 0x138\n\tpublic int skillPoints; // 0x13C\n"
              + TU.meth(0x2100, "public void TakeDamage(float amount)") + TU.meth(0x2110, "public void SpendGold(int amount)"))
    parts.append(TU.cls_text("Player", 3, player))
    parts.append(TU.cls_text("EnemyBrute", 4, "\tpublic float health; // 0x120\n"))
    parts.append("// Namespace: UnityEngine\npublic class MonoBehaviour // TypeDefIndex: 50\n{\n}\n")
    path = os.path.join(tmp, "dump.cs")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    g = D.GameDump({"dump_cs": path}, log=lambda *_a: None)
    g.load()
    return g


class Mem:
    def __init__(self):
        self.m = {}
        self.code = bytearray(b"\x90" * 0x3000)

    def read_memory(self, a, n):
        if BASE <= a < BASE + len(self.code):
            return bytes(self.code[a - BASE:a - BASE + n])
        return bytes(self.m.get(a + i, 0) for i in range(n))

    def write_memory(self, a, d):
        if BASE <= a < BASE + len(self.code):
            self.code[a - BASE:a - BASE + len(d)] = d
        for i, b in enumerate(d):
            self.m[a + i] = b

    def get_maps(self):
        return [(BASE, BASE + 0x3000, 5)]


class Live:
    base = BASE

    def __init__(self, objs):
        self.objs = objs

    def instances(self, cls, limit=400, **_k):
        return self.objs if cls.name == "Player" else []

    def method_addr(self, m):
        return BASE + m.rva

    def set_maps(self, _m):
        pass


class Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.g = make_game(cls.tmp)
        cls.ents = UM.build_entries(cls.g)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def by(self, label):
        return next(e for e in self.ents if e.label.startswith(label))

    def test_fields_are_found_per_category(self):
        cats = {e.label.split("  ")[0]: e.cat for e in self.ents if e.kind == "field"}
        self.assertEqual(cats["Game.Player.health"], "Leben")
        self.assertEqual(cats["Game.Player.gold"], "Geld")
        self.assertEqual(cats["Game.Player.stamina"], "Ausdauer")
        self.assertEqual(cats["Game.Player.experience"], VA_XP)
        self.assertEqual(cats["Game.Player.hunger"], "Hunger/Durst")
        self.assertEqual(cats["Game.Player.skillPoints"], VA_XP)
        self.assertEqual(cats["Game.Player.isInvincible"], "Schalter")

    def test_rate_fields_are_not_offered(self):
        self.assertFalse(any("healthRegenRate" in e.label for e in self.ents))

    def test_enemy_gets_warning_and_ranks_below_player(self):
        brute = self.by("Game.EnemyBrute.health")
        self.assertTrue(brute.warn)
        health = [e for e in self.ents if e.kind == "field" and e.cat == "Leben"]
        self.assertEqual(health[0].cls, "Game.Player")

    def test_method_patches_present(self):
        names = [e.label for e in self.ents if e.kind == "patch"]
        self.assertTrue(any("TakeDamage" in n for n in names))

    def test_encode(self):
        self.assertEqual(UM.encode("int32", "300"), (300).to_bytes(4, "little"))
        self.assertEqual(UM.encode("float", "1.5"), bytes.fromhex("0000c03f"))
        self.assertEqual(UM.encode("bool", "1"), b"\x01")
        self.assertEqual(UM.encode("int32", "auto", "9999"), (9999).to_bytes(4, "little"))
        with self.assertRaises(UM.MenuError):
            UM.encode("int32", "abc")

    def test_cave_entry_only_for_fields(self):
        f = self.by("Game.Player.gold")
        ce = UM.cave_entry(f)
        self.assertEqual((ce.kind, ce.offset), ("value", 0x124))
        self.assertEqual(UM.cave_entry(self.by("Game.Player.isInvincible")).kind, "toggle")
        with self.assertRaises(UM.MenuError):
            UM.cave_entry(next(e for e in self.ents if e.kind == "patch"))

    def test_write_hold_and_restore(self):
        mem = Mem()
        mem.write_memory(OBJ + 0x124, (50).to_bytes(4, "little"))
        mem.write_memory(OBJ + 0x1000 + 0x124, (70).to_bytes(4, "little"))
        menu = UM.UnityMenu(self.g, mem, Live([OBJ, OBJ + 0x1000]), entries=UM.build_entries(self.g))
        gold = menu.by_key[self.by("Game.Player.gold").key]
        self.assertEqual(menu.write_field(gold, "777"), 2)
        self.assertEqual(mem.read_memory(OBJ + 0x124, 4), (777).to_bytes(4, "little"))
        mem.write_memory(OBJ + 0x124, (1).to_bytes(4, "little"))               # Spiel ueberschreibt
        self.assertEqual(menu.tick(), [])
        self.assertEqual(mem.read_memory(OBJ + 0x124, 4), (777).to_bytes(4, "little"))
        menu.set_off(gold)
        self.assertEqual(mem.read_memory(OBJ + 0x124, 4), (50).to_bytes(4, "little"))
        self.assertEqual(mem.read_memory(OBJ + 0x1000 + 0x124, 4), (70).to_bytes(4, "little"))
        self.assertFalse(gold.active)

    def test_no_object_is_a_clear_error(self):
        mem = Mem()
        menu = UM.UnityMenu(self.g, mem, Live([]), entries=UM.build_entries(self.g))
        with self.assertRaises(UM.MenuError) as c:
            menu.set_on(menu.by_key[self.by("Game.Player.health").key])
        self.assertIn("Game.Player", str(c.exception))

    def test_switch_and_method_patch_toggle(self):
        mem = Mem()
        menu = UM.UnityMenu(self.g, mem, Live([OBJ]), entries=UM.build_entries(self.g))
        sw = menu.by_key[self.by("Game.Player.isInvincible").key]
        menu.toggle(sw)
        self.assertEqual(mem.read_memory(OBJ + 0x134, 1), b"\x01")
        menu.toggle(sw)
        self.assertEqual(mem.read_memory(OBJ + 0x134, 1), b"\x00")
        p = next(e for e in menu.entries if e.kind == "patch" and "TakeDamage" in e.label)
        addr = BASE + p.cand.method.rva
        before = mem.read_memory(addr, 4)
        menu.toggle(p)
        self.assertNotEqual(mem.read_memory(addr, 4), before)
        menu.toggle(p)
        self.assertEqual(mem.read_memory(addr, 4), before)

    def test_tick_releases_entry_on_write_error(self):
        class Boom(Mem):
            def write_memory(self, a, d):
                if getattr(self, "fail", False):
                    raise OSError("weg")
                super().write_memory(a, d)
        mem = Boom()
        menu = UM.UnityMenu(self.g, mem, Live([OBJ]), entries=UM.build_entries(self.g))
        gold = menu.by_key[self.by("Game.Player.gold").key]
        menu.write_field(gold, "5")
        mem.fail = True
        msgs = menu.tick()
        self.assertTrue(msgs and "Festhalten beendet" in msgs[0])
        self.assertFalse(gold.held)


VA_XP = UM.VA.XP_CATEGORY


class FakeUnity:
    def __init__(self, game, live):
        self.game, self.live, self.mod_base = game, live, BASE

    def _ensure_base(self, _c):
        return self.live

    @staticmethod
    def _maps(_c):
        return []


FakeUnity.__name__ = "UnityTab"


class Gui(unittest.TestCase):
    def setUp(self):
        import tools_unity_cheatmenu_gui as G
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.game = make_game(self.tmp)
        self.mem = Mem()
        self.mem.write_memory(OBJ + 0x124, (50).to_bytes(4, "little"))
        self.w = FakeWin()
        self.w.client = self.mem
        self.w.app.PATCH_DIR = os.path.join(self.tmp, "patches")
        self.w.app.load_patches = lambda: None
        self.w.extra_tabs = [FakeUnity(self.game, Live([OBJ]))]
        self.t = G.UnityCheatMenuTab(None, self.w)

    def pick(self, label):
        self.t._fill()
        for i, e in enumerate(self.t.view):
            if e.label.startswith(label):
                self.t.tv.selection_set(str(i))
                return e
        self.fail(label)

    def logs(self, kind):
        return [m for m, k in self.w.logged if k == kind] if hasattr(self.w, "logged") else []

    def test_build_fills_menu(self):
        self.t.build()
        self.assertIsNotNone(self.t.menu)
        self.assertGreater(len(self.t.view), 5)
        self.assertIn("Einträge", self.t.v_info.get())

    def test_build_without_game_or_client(self):
        self.w.extra_tabs[0].game = None
        self.t.build()
        self.assertIsNone(self.t.menu)
        self.w.extra_tabs[0].game = self.game
        self.w.client = None
        self.t.build()
        self.assertIsNone(self.t.menu)

    def test_toggle_value_and_all_off(self):
        self.t.build()
        e = self.pick("Game.Player.gold")
        self.t.v_val.set("999")
        self.t.toggle()
        self.assertEqual(self.mem.read_memory(OBJ + 0x124, 4), (999).to_bytes(4, "little"))
        self.assertTrue(e.active)
        self.t.all_off()
        self.assertEqual(self.mem.read_memory(OBJ + 0x124, 4), (50).to_bytes(4, "little"))

    def test_cave_refused_for_method_and_save_patch_works(self):
        self.t.build()
        p = next(e for e in self.t.menu.entries if e.kind == "patch" and "TakeDamage" in e.label)
        self.pick(p.label.split("  ")[0])
        self.assertIsNone(self.t._cave_target())
        self.t.save_patch()
        files = os.listdir(self.w.app.PATCH_DIR)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith(".reapproj"))

    def test_cave_target_for_field_is_adapted(self):
        self.t.build()
        self.pick("Game.Player.gold")
        ce = self.t._cave_target()
        self.assertEqual((ce.kind, ce.offset), ("value", 0x124))

    def test_get_code_reads_module_from_console_once(self):
        import ue_instr
        try:
            ue_instr.get_disasm()
        except Exception:  # noqa: BLE001
            self.skipTest("kein Disassembler")
        self.t.build()
        code, dis = self.t._get_code()
        self.assertEqual(code["base_va"], BASE)
        self.assertGreaterEqual(len(code["buf"]), 0x3000)
        self.assertEqual(self.t._get_code()[0], code)                  # gemerkt, nicht neu gelesen

    def test_save_patch_on_field_says_cave(self):
        self.t.build()
        self.pick("Game.Player.gold")
        self.t.save_patch()
        self.assertFalse(os.path.isdir(self.w.app.PATCH_DIR) and os.listdir(self.w.app.PATCH_DIR))


if __name__ == "__main__":
    unittest.main()
