"""ToolsWindow.read_code: Speicher zum Disassemblieren ohne das 0xCC gesetzter Breakpoints."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk  # noqa: E402

ghost_tk.install()
import tools_gui as G  # noqa: E402


def window(overrides=None, with_session=True):
    client = types.SimpleNamespace(read_memory=lambda a, n: bytes([0xCC]) * n)
    sess = types.SimpleNamespace(bp_overrides=lambda: overrides or {}) if with_session else None
    return types.SimpleNamespace(client=client, dbg_tab=types.SimpleNamespace(sess=sess))


class ReadCode(unittest.TestCase):
    def test_original_bytes_replace_the_breakpoint_bytes(self):
        win = window({0x1001: b"\x48", 0x1003: b"\x89"})
        self.assertEqual(G.ToolsWindow.read_code(win, 0x1000, 4), b"\xcc\x48\xcc\x89")

    def test_without_a_debug_session_the_memory_is_returned_raw(self):
        self.assertEqual(G.ToolsWindow.read_code(window(with_session=False), 0x1000, 2), b"\xcc\xcc")

    def test_window_without_debug_tab_still_reads(self):
        win = types.SimpleNamespace(client=types.SimpleNamespace(read_memory=lambda a, n: b"\x90" * n))
        self.assertEqual(G.ToolsWindow.read_code(win, 0, 3), b"\x90\x90\x90")


if __name__ == "__main__":
    unittest.main()
