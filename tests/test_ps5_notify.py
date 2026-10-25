"""Tests fuer ps5_notify: Meldungen bei Verbinden, Cheats (einzeln / Sammelaktion) und Debugger - ohne Konsole."""
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ps5_notify as N
from i18n import STRINGS, Translator


class Sink:
    def __init__(self):
        self.msgs = []
        self.got = threading.Event()

    def __call__(self, text):
        self.msgs.append(text)
        self.got.set()


def make(cfg=None, lang="en"):
    sink = Sink()
    n = N.Notifier(backend=None, cfg={} if cfg is None else cfg, tr=Translator(lang), sender=sink)
    return n, sink


class Helpers(unittest.TestCase):
    def test_summarize_names(self):
        self.assertEqual(N.summarize_names(["A", "B"]), "A, B")
        self.assertEqual(N.summarize_names(["A", "B", "C", "D", "E"]), "A, B, C +2")

    def test_shorten(self):
        self.assertEqual(N.shorten("a  b\n c"), "a b c")
        self.assertEqual(len(N.shorten("x" * 500)), N.MAX_LEN)

    def test_all_notify_keys_exist_in_both_languages(self):
        keys = {k for k in STRINGS["de"] if k.startswith("notify_")}
        self.assertTrue(keys)
        self.assertEqual(keys, {k for k in STRINGS["en"] if k.startswith("notify_")})


class Events(unittest.TestCase):
    def test_connected(self):
        n, s = make()
        n.connected(1234)
        n.flush()
        self.assertEqual(s.msgs, ["ReaperPy connected (PID 1234)"])

    def test_cheat_on_off_single(self):
        n, s = make()
        n.cheat(True, "Infinite HP")
        n.cheat(False, "Infinite HP")
        n.flush()
        self.assertEqual(s.msgs, ["ON: Infinite HP", "OFF: Infinite HP"])

    def test_cheat_while_debugger_attached(self):
        n, s = make()
        n.debugger("attached", 77)
        n.cheat(True, "God mode")
        n.debugger("detached")
        n.cheat(False, "God mode")
        n.flush()
        self.assertEqual(s.msgs, ["Debugger attached (PID 77)", "ON: God mode (debugger attached)",
                                  "Debugger detached", "OFF: God mode"])

    def test_german_texts(self):
        n, s = make(lang="de")
        n.cheat(True, "Unendlich Leben")
        n.flush()
        self.assertEqual(s.msgs, ["AKTIV: Unendlich Leben"])

    def test_bulk_sends_one_summary(self):
        n, s = make()
        n.bulk_begin()
        for name in ("A", "B", "C", "D"):
            n.cheat(True, name)
        n.bulk_end()
        n.flush()
        self.assertEqual(s.msgs, ["ON: 4 cheats (A, B, C +1)"])

    def test_bulk_with_single_item_uses_normal_text(self):
        n, s = make()
        n.bulk_begin()
        n.cheat(False, "Solo")
        n.bulk_end()
        n.flush()
        self.assertEqual(s.msgs, ["OFF: Solo"])

    def test_nested_bulk_only_flushes_at_outer_end(self):
        n, s = make()
        n.bulk_begin()
        n.bulk_begin()
        n.cheat(True, "A")
        n.cheat(True, "B")
        n.bulk_end()
        n.flush(0.1)
        self.assertEqual(s.msgs, [])
        n.bulk_end()
        n.flush()
        self.assertEqual(s.msgs, ["ON: 2 cheats (A, B)"])

    def test_debugger_states_are_deduplicated(self):
        n, s = make()
        n.debugger("attached", 5)
        n.debugger("attached", 5)          # doppelt gemeldet
        n.debugger("reconnecting")         # Wiederaufbau bleibt stumm ...
        self.assertTrue(n.debugger_attached)
        n.debugger("attached", 5)          # ... auch das Ende davon
        n.debugger("lost")
        self.assertFalse(n.debugger_attached)
        n.flush()
        self.assertEqual(s.msgs, ["Debugger attached (PID 5)", "Debugger: connection lost"])

    def test_hits_off_by_default_and_rate_limited(self):
        n, s = make()
        self.assertFalse(n.hit("breakpoint", 0x1000))
        n2, s2 = make({"ps5_notify_hits": True})
        self.assertTrue(n2.hit("breakpoint", 0x401000))
        self.assertFalse(n2.hit("breakpoint", 0x401000))      # innerhalb von HIT_MIN_INTERVAL
        n2.flush()
        self.assertEqual(s2.msgs, ["Debugger: breakpoint at 0x401000"])

    def test_disabled_by_config(self):
        n, s = make({"ps5_notifications": False})
        n.connected(1)
        n.cheat(True, "X")
        n.debugger("attached", 1)
        n.flush(0.1)
        self.assertEqual(s.msgs, [])

    def test_sender_errors_do_not_kill_the_worker(self):
        calls = []

        def bad(text):
            calls.append(text)
            if len(calls) == 1:
                raise RuntimeError("boom")

        n = N.Notifier(None, {}, Translator("en"), sender=bad)
        n.send("one")
        n.send("two")
        n.flush()
        self.assertEqual(calls, ["one", "two"])


if __name__ == "__main__":
    unittest.main()
