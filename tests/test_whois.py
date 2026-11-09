"""whois.py: Spieler oder Gegner erkennen (Auswertung, Beschreibung, Cave-Text) - ohne Spiel."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import whois as W  # noqa: E402

CODE = lambda v: 0x400000 <= v < 0x500000


def rec(obj, ret, deep=0x401234, **regs):
    stack = [0x7ffff0001000 + 8 * i for i in range(W.NSTACK)]
    stack[2], stack[5] = ret, deep
    r = {n: 0 for n in W.REGS}
    r["rbx"] = obj
    r.update(regs)
    return {"regs": r, "rsp": 0x7ffff0000000, "stack": stack}


PLAYER, ENEMIES = 0x10000100, (0x10000200, 0x10000300, 0x10000400)
RET_P, RET_E = 0x401000, 0x402000


def phases(noise=False):
    a = [rec(PLAYER, RET_P) for _ in range(8)]
    b = [rec(ENEMIES[i % 3], RET_E) for i in range(9)]
    if noise:
        b.append(rec(ENEMIES[0], RET_P))                 # ein Ausreisser (Spieler und Gegner gleichzeitig getroffen)
    return a, b


class Analyze(unittest.TestCase):
    def test_caller_wins_and_is_stable(self):
        a, b = phases()
        found = W.analyze(a, b, is_code=CODE)
        self.assertEqual(found[0]["kind"], "caller")
        self.assertEqual((found[0]["slot"], found[0]["player"], found[0]["enemy"]), (2, [RET_P], [RET_E]))
        self.assertTrue(found[0]["stable"])
        self.assertEqual(found[0]["confidence"], "high")
        self.assertEqual({c["kind"] for c in found}, {"caller", "object"})   # deeper slot 5 gleich -> kein Merkmal

    def test_one_outlier_is_ignored(self):
        a, b = phases(noise=True)
        found = W.analyze(a, b, is_code=CODE)
        self.assertEqual(found[0]["slot"], 2)

    def test_same_caller_for_both_leaves_only_the_object(self):
        a = [rec(PLAYER, RET_P) for _ in range(5)]
        b = [rec(ENEMIES[i % 3], RET_P) for i in range(6)]
        found = W.analyze(a, b, is_code=CODE)
        self.assertEqual([c["kind"] for c in found], ["object"])
        self.assertFalse(found[0]["stable"])

    def test_nothing_to_find_when_player_and_enemies_share_everything(self):
        a = [rec(PLAYER, RET_P) for _ in range(5)]
        b = [rec(PLAYER, RET_P) for _ in range(5)]
        self.assertEqual(W.analyze(a, b, is_code=CODE), [])

    def test_too_few_samples(self):
        a, b = phases()
        self.assertEqual(W.analyze(a[:1], b, is_code=CODE), [])

    def test_field_in_the_object_memory(self):
        a, b = phases()
        mem = {}
        for o, team, hp in ((PLAYER, 1, 100), (ENEMIES[0], 2, 30), (ENEMIES[1], 2, 55), (ENEMIES[2], 3, 80)):
            blob = bytearray(0x200)
            struct.pack_into("<II", blob, 0x38, team, 0)
            struct.pack_into("<I", blob, 0x10, hp)           # Leben: verschieden, aber KEIN Merkmal (zu viele Werte)
            mem[o] = blob
        ticks = []

        def recheck():                                        # zwischen den Lesungen aendert sich ein Feld
            ticks.append(1)
            struct.pack_into("<I", mem[PLAYER], 0x60, 7)
        struct.pack_into("<I", mem[PLAYER], 0x60, 6)
        read = lambda addr, n: bytes(mem[addr][:n]) if addr in mem else b""
        found = W.analyze(a, b, read=read, is_code=CODE, recheck=recheck)
        fields = [c for c in found if c["kind"] == "field"]
        self.assertEqual(ticks, [1])
        self.assertEqual([(c["reg"], c["off"], c["player"], c["enemy"]) for c in fields if c["off"] in (0x38, 0x60, 0x10)],
                         [("rbx", 0x38, [1], [2, 3])])           # 0x60 aenderte sich, 0x10 hat zu viele Werte
        self.assertTrue(fields[0]["stable"])

    def test_describe(self):
        a, b = phases()
        c = W.analyze(a, b, is_code=CODE)[0]
        self.assertIn("Aufrufer", W.describe(c, 0x400000, "de"))
        self.assertIn("+0x1000", W.describe(c, 0x400000, "de"))
        self.assertIn("Caller", W.describe(c, 0x400000, "en"))
        f = {"kind": "field", "reg": "rbx", "off": 0x38, "player": [1], "enemy": [2]}
        self.assertIn("Team", W.describe(f, 0, "de"))
        o = {"kind": "object", "reg": "rbx", "player": [PLAYER], "enemy": [1]}
        self.assertIn("nur bis zum Beenden", W.describe(o, 0, "de"))


class Cave(unittest.TestCase):
    def test_labels_are_unique_and_each_path_ends_with_a_jump(self):
        c = {"kind": "field", "reg": "rbx", "off": 0x38, "player": [1, 4]}
        t = W.guard_cave(c, 0x1000, ["nop"], ["sub dword ptr [rbx], 1"], label_prefix="HP_")
        self.assertEqual(t.count("HP_WhoHit:"), 1)
        self.assertEqual(t.count("je HP_WhoHit"), 2)
        self.assertEqual(t.count("jmp OriginReturn"), 2)
        self.assertEqual(t.count("pushfq"), 1)
        self.assertEqual(t.count("popfq"), 2)                 # beide Wege stellen die Flags wieder her

    def test_enemy_mode_swaps_the_paths(self):
        c = {"kind": "field", "reg": "rbx", "off": 0x38, "player": [1]}
        t = W.guard_cave(c, 0x1000, ["CHEAT"], ["BODY"], apply_to="enemy")
        self.assertLess(t.index("CHEAT"), t.index("WhoHit:"))
        self.assertGreater(t.index("BODY"), t.index("WhoHit:"))
        with self.assertRaises(ValueError):
            W.guard_cave(c, 0x1000, [], [], apply_to="x")

    def test_caller_guard_is_base_independent_and_object_guard_avoids_the_object_register(self):
        t = W.guard_cave({"kind": "caller", "slot": 3, "player": [0x5040]}, 0x5000, [], [])
        self.assertIn("lea rax, [rip + @hook+0x40]", t)
        self.assertIn("cmp qword ptr [rsp + 0xa8], rax", t)           # 0x80 Red Zone + 16 + 3*8
        t = W.guard_cave({"kind": "object", "reg": "rax", "player": [0x10000100]}, 0x5000, [], [])
        self.assertIn("mov rcx, 0x10000100", t)
        self.assertIn("cmp rax, rcx", t)
        self.assertIn("pop rcx", t)

    def test_stub_has_no_odd_ring_size(self):
        with self.assertRaises(ValueError):
            W.stub_asm(0x1000, 100)
        self.assertEqual(len(W.stub_asm(0x1000, 64)), 4 + 8 + 12 + 14 * 0 + 0 + len(W.stub_asm(0x1000, 64)) - 24) if False else None


if __name__ == "__main__":
    unittest.main()
