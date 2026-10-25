import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ptrscan_server as P

STATIC = [(0x400000, 0x500000)]
SEG = [(0x400000, 0x500000), (0x10000000, 0x100000)]


class T(unittest.TestCase):
    def test_chain_found_and_resolves(self):
        target = 0x10005040
        mem = {0x10000100: 0x10005000 - 0x0,      # heap A zeigt auf 0x10005000 (Ziel = +0x40)
               0x10000200: 0x10000100 - 0x10,     # heap B zeigt 0x10 vor A
               0x450000: 0x10000200 - 0x8,        # statischer Zeiger -> B-0x8
               0x450008: 0x1234}                   # Rauschen
        sim = P.Simulation(mem, SEG, 0x100)
        chains, info = P.scan(sim, target, SEG, STATIC, 0x100, 5)
        self.assertEqual(len(chains), 1)
        c = chains[0]
        self.assertEqual(c.static, 0x450000)
        self.assertEqual(c.offsets, [0x8, 0x10, 0x40])
        read = lambda a: mem[a]
        self.assertEqual(P.resolve(read, c), target)
        self.assertIn("->", c.text(("eboot", 0x400000)))

    def test_multiple_paths_and_depth_limit(self):
        target = 0x10000000
        mem = {0x401000: 0x10000000, 0x402000: 0x10000000 - 0x20,
               0x10000800: 0x10000000, 0x403000: 0x10000800}
        chains, _ = P.scan(P.Simulation(mem, SEG, 0x40), target, SEG, STATIC, 0x40, 1)
        self.assertEqual({c.static for c in chains}, {0x401000, 0x402000})   # Tiefe 1: nur direkte
        chains, _ = P.scan(P.Simulation(mem, SEG, 0x40), target, SEG, STATIC, 0x40, 2)
        self.assertIn(0x403000, {c.static for c in chains})
        self.assertEqual(chains[0].depth(), 1)                                # kurze Ketten zuerst

    def test_cycle_terminates(self):
        mem = {0x10000100: 0x10000200, 0x10000200: 0x10000100}
        chains, info = P.scan(P.Simulation(mem, SEG, 0x10), 0x10000100, SEG, STATIC, 0x10, 6)
        self.assertEqual(chains, [])

if __name__ == "__main__":
    unittest.main()
