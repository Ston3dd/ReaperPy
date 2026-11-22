"""DebugTab: Filter 'nur dieses Ziel' laesst Treffer auf andere Objekte automatisch weiterlaufen."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk  # noqa: E402

ghost_tk.install()
import hit_targets as TG  # noqa: E402
import tools_debug_gui as G  # noqa: E402

LINE = {"addr": 0x1000, "size": 3, "mnemonic": "mov", "op_str": "dword ptr [rdi + 0x1c], eax"}


def hit(rdi, rip=0x1000):
    regs = {r: 0 for r in ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp")}
    regs.update(rip=rip, rdi=rdi)
    return {"kind": "BP", "regs": regs}


def stub(only_ea, cached=True):
    s = types.SimpleNamespace(only_ea=only_ea, book=TG.TargetBook(), resumed=0,
                              _insn_cache={("BP", 0x1000): LINE} if cached else {},
                              win=types.SimpleNamespace(ui=lambda f: None))
    s._resume_async = lambda: setattr(s, "resumed", s.resumed + 1)
    s._show_filter_label = lambda: None
    return s


class Filter(unittest.TestCase):
    def test_other_object_is_skipped_and_game_resumed(self):
        s = stub(only_ea=0x701C)
        self.assertTrue(G.DebugTab._filtered_out(s, hit(0x9000)))
        self.assertEqual((s.resumed, s.book.skipped), (1, 1))

    def test_wanted_object_is_shown(self):
        s = stub(only_ea=0x701C)
        self.assertFalse(G.DebugTab._filtered_out(s, hit(0x7000)))
        self.assertEqual(s.resumed, 0)

    def test_no_filter_or_unknown_instruction_shows_everything(self):
        self.assertFalse(G.DebugTab._filtered_out(stub(None), hit(0x9000)))
        self.assertFalse(G.DebugTab._filtered_out(stub(0x701C, cached=False), hit(0x9000)))

    def test_step_hits_are_never_filtered(self):
        h = hit(0x9000)
        h["kind"] = "STEP"
        self.assertFalse(G.DebugTab._filtered_out(stub(0x701C), h))


if __name__ == "__main__":
    unittest.main()
