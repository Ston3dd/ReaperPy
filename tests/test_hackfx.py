"""Tests fuer hackfx (ACCESS GRANTED / ACCESS DENIED beim Verbinden)."""
import os
import random
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import hackfx as F


class FakeCanvas:
    def __init__(self, *a, **k): self.texts = []; self.rects = 0; self.lines = 0; self.bound = {}
    def pack(self, **k): pass
    def bind(self, seq, fn): self.bound[seq] = fn
    def delete(self, *a): self.texts = []; self.rects = 0; self.lines = 0
    def create_text(self, x, y, **k): self.texts.append(k.get("text", ""))
    def create_rectangle(self, *a, **k): self.rects += 1
    def create_line(self, *a, **k): self.lines += 1


class FakeTop:
    instances = []
    def __init__(self, root=None, **k):
        self.attrs, self.afters, self.destroyed, self.bound, self.cancelled = {}, [], False, {}, []
        FakeTop.instances.append(self)
    def overrideredirect(self, v): self.over = v
    def configure(self, **k): pass
    def attributes(self, *a): self.attrs[a[0]] = a[1] if len(a) > 1 else None
    def geometry(self, g): self.geo = g
    def bind(self, seq, fn): self.bound[seq] = fn
    def after(self, ms, fn): self.afters.append((ms, fn)); return len(self.afters)
    def after_cancel(self, job): self.cancelled.append(job)
    def destroy(self): self.destroyed = True


class Root:
    def winfo_rootx(self): return 100
    def winfo_rooty(self): return 50
    def winfo_width(self): return 1000
    def winfo_height(self): return 700


FAKE_TK = types.SimpleNamespace(Toplevel=FakeTop, Canvas=FakeCanvas)


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


class Pure(unittest.TestCase):
    def test_classify_error_gives_helpful_reason(self):
        self.assertEqual(F.classify_error(ConnectionRefusedError(10061, "refused"))[0], "> CONNECTION REFUSED")
        self.assertIn("PAYLOAD", F.classify_error("Connection refused")[1])
        self.assertEqual(F.classify_error("[Errno 11001] getaddrinfo failed")[0], "> HOST UNREACHABLE")
        self.assertEqual(F.classify_error("[Errno 101] Network is unreachable")[0], "> HOST UNREACHABLE")
        self.assertEqual(F.classify_error("timed out")[0], "> NO RESPONSE FROM HOST")
        self.assertEqual(F.classify_error("Kein ps5debug-Payload gefunden")[0], "> CONNECTION REFUSED")
        self.assertEqual(F.classify_error("Kein Spiel-Prozess gefunden")[0], "> LINK OK - NO GAME PROCESS")
        other = F.classify_error("irgendein seltsamer Fehler " * 5)
        self.assertEqual(other[0], "> CONNECTION FAILED")
        self.assertLessEqual(len(other[1]), 48)
        self.assertEqual(F.classify_error("")[1], "> UNKNOWN ERROR")

    def test_granted_lines(self):
        self.assertEqual(F.granted_lines("1.2.3.4", 744, 99),
                         ["> HANDSHAKE ............ OK", "> TARGET 1.2.3.4:744", "> GAME PROCESS 99 ATTACHED"])
        self.assertEqual(F.granted_lines(), ["> HANDSHAKE ............ OK"])

    def test_typewriter(self):
        self.assertEqual(F.typed("ACCESS", 0.0, 10), "")
        self.assertEqual(F.typed("ACCESS", 0.25, 10), "AC")
        self.assertEqual(F.typed("ACCESS", 5, 10), "ACCESS")
        self.assertEqual(F.typed("ACCESS", 0.5, 10, start=0.3), "AC")
        self.assertEqual(F.typed("ACCESS", 0.1, 10, start=0.3), "")

    def test_glitch_only_in_window_and_deterministic(self):
        self.assertEqual(F.glitch(0.2), (0, 0, True))
        self.assertEqual(F.glitch(2.0), (0, 0, True))
        g = F.glitch(1.1, seed=3)
        self.assertEqual(g, F.glitch(1.1, seed=3))
        seen = {F.glitch(0.95 + i * 0.025, 0) for i in range(22)}
        self.assertGreater(len(seen), 3)                                  # es flackert wirklich
        self.assertTrue(all(abs(dx) <= 5 and abs(dy) <= 2 for dx, dy, _b in seen))

    def test_shake_decays(self):
        self.assertEqual(F.shake(1.3), 0)
        self.assertNotEqual(F.shake(0.02), 0)
        self.assertLessEqual(abs(F.shake(1.0)), 2)

    def test_alpha_fades_at_the_end(self):
        self.assertEqual(F.alpha(0.0, 3.0), 1.0)
        self.assertEqual(F.alpha(2.5, 3.0), 1.0)
        self.assertAlmostEqual(F.alpha(2.9, 3.0), 0.1 / F.FADE_S, places=3)
        self.assertEqual(F.alpha(3.0, 3.0), 0.0)

    def test_rain_falls_and_wraps(self):
        rng = random.Random(1)
        cols = [[0, 6, "A"], [F.H + 20, 6, "B"]]
        nxt = F.rain_step(cols, rng, F.H)
        self.assertEqual(nxt[0][0], 6)
        self.assertLessEqual(nxt[1][0], 0)                                # unten raus -> oben neu
        self.assertIn(nxt[1][1], (4, 6, 8, 10))

    def test_enabled_flag_and_env(self):
        self.assertTrue(F.enabled({}))
        self.assertFalse(F.enabled({"hack_fx": False}))
        os.environ["REAPERPY_NO_FX"] = "1"
        try:
            self.assertFalse(F.enabled({}))
        finally:
            del os.environ["REAPERPY_NO_FX"]


class BannerTests(unittest.TestCase):
    def setUp(self):
        FakeTop.instances.clear()
        self.clock = Clock()
        self.old = F.time.time
        F.time.time = self.clock
        F._current = None

    def tearDown(self):
        F.time.time = self.old
        F._current = None

    def run_to_end(self, banner, step=0.1):
        top = FakeTop.instances[-1]
        guard = 0
        while not banner.closed and guard < 200:
            ms, fn = top.afters[-1]
            self.clock.now += step
            fn()
            guard += 1
        return top

    def test_granted_runs_about_three_seconds_then_closes(self):
        done = []
        b = F.Banner(Root(), True, F.granted_lines("1.2.3.4", 744, 7), on_done=lambda: done.append(1), tk=FAKE_TK)
        top = FakeTop.instances[-1]
        self.assertTrue(top.over)
        self.assertEqual(top.attrs["-topmost"], True)
        self.assertEqual(top.geo, "600x260+300+196")                      # mittig ueber dem Hauptfenster
        self.assertEqual(top.afters[-1][0], 45)
        self.clock.now += 0.4
        top.afters[-1][1]()
        shown = " ".join(b.cv.texts)
        self.assertTrue(any(t.startswith("ACC") for t in b.cv.texts), shown)    # Schreibmaschine laeuft
        self.assertGreater(b.cv.lines, 10)                                # Scanlines
        self.clock.now += 1.9                                              # alles getippt
        top.afters[-1][1]()
        self.assertTrue(any("ACCESS GRANTED" in t for t in b.cv.texts))
        self.assertTrue(any("TARGET 1.2.3.4:744" in t for t in b.cv.texts))
        self.run_to_end(b)
        self.assertTrue(top.destroyed)
        self.assertEqual(done, [1])
        self.assertGreaterEqual(self.clock.now - b.t0, F.GRANTED_S)
        self.assertLess(self.clock.now - b.t0, F.GRANTED_S + 0.3)

    def test_denied_is_red_and_shows_reason(self):
        b = F.Banner(Root(), False, F.classify_error("timed out"), tk=FAKE_TK)
        top = FakeTop.instances[-1]
        self.assertEqual(b.fg, F.RED)
        self.clock.now += 2.5
        top.afters[-1][1]()
        self.assertTrue(any("ACCESS DENIED" in t for t in b.cv.texts))
        self.assertTrue(any("NO RESPONSE FROM HOST" in t for t in b.cv.texts))
        self.run_to_end(b)
        self.assertGreaterEqual(self.clock.now - b.t0, F.DENIED_S)

    def test_click_closes_immediately_and_only_once(self):
        done = []
        b = F.Banner(Root(), True, ["x"], on_done=lambda: done.append(1), tk=FAKE_TK)
        b.cv.bound["<Button-1>"](None)
        b.close()
        self.assertTrue(FakeTop.instances[-1].destroyed)
        self.assertEqual(done, [1])
        self.assertIsNone(b.win)

    def test_fade_sets_alpha_near_the_end(self):
        b = F.Banner(Root(), True, ["x"], tk=FAKE_TK)
        top = FakeTop.instances[-1]
        self.clock.now += F.GRANTED_S - 0.1
        top.afters[-1][1]()
        self.assertLess(top.attrs.get("-alpha", 1.0), 1.0)

    def test_failures_in_the_ui_never_raise(self):
        class BadTop(FakeTop):
            def overrideredirect(self, v): raise RuntimeError("kein Display")
        b = F.Banner(Root(), True, ["x"], tk=types.SimpleNamespace(Toplevel=BadTop, Canvas=FakeCanvas))
        self.assertTrue(b.closed)
        self.assertIsNone(b.win)

        class BadCanvas(FakeCanvas):
            def create_text(self, *a, **k): raise RuntimeError("Zeichenfehler")
        done = []
        b = F.Banner(Root(), False, ["x"], on_done=lambda: done.append(1), tk=types.SimpleNamespace(Toplevel=FakeTop, Canvas=BadCanvas))
        self.assertTrue(b.closed)                                          # Fehler beim Zeichnen schliesst still
        self.assertEqual(done, [1])

    def test_show_respects_flag_replaces_previous_and_maps_kinds(self):
        self.assertIsNone(F.show(Root(), "granted", {}, {"hack_fx": False}, tk=FAKE_TK))
        self.assertEqual(FakeTop.instances, [])
        a = F.show(Root(), "granted", {"host": "h", "port": 1, "pid": 5}, {}, tk=FAKE_TK)
        self.assertTrue(a.ok)
        b = F.show(Root(), "denied", {"error": "Connection refused"}, {}, tk=FAKE_TK)
        self.assertTrue(a.closed)                                          # altes Banner wird ersetzt
        self.assertFalse(b.ok)
        self.assertEqual(b.lines[0], "> CONNECTION REFUSED")
        self.assertIsNone(F.show(Root(), "granted", {}, {}, tk=types.SimpleNamespace(Toplevel=None, Canvas=None)))


if __name__ == "__main__":
    unittest.main()
