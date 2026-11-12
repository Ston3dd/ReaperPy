"""tools_ui.py + Komfort im Werkzeug-Fenster: Tooltips, gesperrte Knoepfe, Ampel, farbiges Ergebnis, Leerzustand, "arbeitet ..."."""
import glob
import os
import re
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk  # noqa: E402

ghost_tk.install()
import conncheck  # noqa: E402
import tools_common as TC  # noqa: E402
import tools_gui as G  # noqa: E402
import tools_i18n as T  # noqa: E402
import tools_ui as U  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


class FW:
    """Fake-Widget mit der Tk-Schnittstelle, die tools_ui benutzt."""
    def __init__(self, cls="Button", text="", state="normal", children=()):
        self.cls, self.opts, self.kids = cls, {"text": text, "state": state}, list(children)
        self.binds = []

    def winfo_class(self):
        return self.cls

    def winfo_children(self):
        return self.kids

    def cget(self, k):
        return self.opts[k]

    def configure(self, **kw):
        self.opts.update(kw)

    def bind(self, seq, fn, add=None):
        self.binds.append(seq)

    def after(self, ms, fn=None):
        return "job"

    def after_cancel(self, job):
        pass


class Terms(unittest.TestCase):
    def test_exact_and_prefix_matches(self):
        self.assertIsNotNone(U.find_term("OFFSET (ab Image-Base)"))
        self.assertIsNotNone(U.find_term("OriginReturn (Bytes, leer = automatisch)"))      # Anfang
        self.assertIsNotNone(U.find_term("SIGNATUR AUS ADRESSE"))                          # Anfang
        self.assertIsNotNone(U.find_term("NOP"))
        self.assertIsNone(U.find_term("OFFSETS ÜBERNEHMEN"))                               # kein versehentlicher Treffer
        self.assertIsNone(U.find_term("OFFSET"))                                           # im Signatur-Feld anders gemeint
        self.assertIsNone(U.find_term("NOPE"))
        self.assertIsNone(U.find_term(""))

    def test_every_term_has_both_languages(self):
        keys = [k for k, _p, _d, _e in U.TERMS]
        self.assertEqual(len(keys), len(set(keys)))
        for key, _prefix, de, en in U.TERMS:
            self.assertTrue(de.strip() and en.strip(), key)
            self.assertNotRegex(en, "[äöüßÄÖÜ]", key)

    def test_attach_terms_marks_labels_and_buttons(self):
        lbl, btn, other = FW("Label", "SIGNATUR"), FW("Button", "NOP"), FW("Label", "Irgendwas")
        root = FW("Frame", "", children=[lbl, btn, other])
        self.assertEqual(U.attach_terms(root), 2)
        self.assertEqual(lbl.opts.get("cursor"), "question_arrow")
        self.assertNotIn("cursor", btn.opts)                    # Knoepfe behalten ihre Hand
        self.assertIsNotNone(lbl.__dict__.get("_tooltip"))
        self.assertEqual(U.attach_terms(root), 0)               # idempotent

    def test_german_original_is_used_when_english_is_shown(self):
        lbl = FW("Label", "SIGNATURE")
        lbl._i18n = {"text": ("SIGNATUR", "SIGNATURE")}
        self.assertEqual(U.de_text(lbl), "SIGNATUR")
        self.assertEqual(U.attach_terms(FW("Frame", "", children=[lbl])), 1)

    def test_tooltip_text_in_both_languages(self):
        lbl = FW("Label", "SIGNATUR")
        U.attach_terms(FW("Frame", "", children=[lbl]))
        text = lbl.__dict__["_tooltip"].current()
        self.assertIn("Byte-Muster", text)
        old = T.lang()
        T.set_lang("en")
        try:
            self.assertIn("byte pattern", lbl.__dict__["_tooltip"].current())
        finally:
            T.set_lang(old)


class NetButtons(unittest.TestCase):
    def tree(self):
        self.read = FW("Button", "LESEN")
        self.load = FW("Button", "LADEN…")
        self.test = FW("Button", "TEST AN")
        self.root = FW("Frame", "", children=[FW("Frame", "", children=[self.read, self.load]), self.test])

    def test_console_ready(self):
        mk = lambda c, p: types.SimpleNamespace(backend=types.SimpleNamespace(client=c, pid=p))  # noqa: E731
        self.assertTrue(U.console_ready(mk(object(), 5)))
        self.assertFalse(U.console_ready(mk(None, 5)))
        self.assertFalse(U.console_ready(mk(object(), None)))
        self.assertFalse(U.console_ready(None))

    def test_disconnected_blocks_only_console_buttons(self):
        self.tree()
        self.assertEqual(U.set_net_state(self.root, False), 2)
        self.assertEqual(self.read.opts["state"], "disabled")
        self.assertEqual(self.test.opts["state"], "disabled")
        self.assertEqual(self.load.opts["state"], "normal")            # Dateiarbeit bleibt frei
        self.assertIn("VERBINDEN", self.read.__dict__["_tooltip"].current())   # sagt, warum

    def test_connecting_unlocks_what_we_locked(self):
        self.tree()
        U.set_net_state(self.root, False)
        self.assertEqual(U.set_net_state(self.root, True), 2)
        self.assertEqual(self.read.opts["state"], "normal")
        self.assertNotIn("VERBINDEN", self.read.__dict__["_tooltip"].current())

    def test_a_button_the_tab_disabled_itself_stays_disabled(self):
        self.tree()
        self.test.opts["state"] = "disabled"                           # z. B. vom Tab selbst gesperrt
        U.set_net_state(self.root, False)
        U.set_net_state(self.root, True)
        self.assertEqual(self.test.opts["state"], "disabled")
        self.assertEqual(self.read.opts["state"], "normal")

    def test_repeated_calls_change_nothing(self):
        self.tree()
        U.set_net_state(self.root, False)
        self.assertEqual(U.set_net_state(self.root, False), 0)

    def test_list_only_names_buttons_that_exist(self):
        """Wird ein Knopf umbenannt, faellt das hier auf (sonst bliebe er stillschweigend ungesperrt)."""
        src = ""
        for f in glob.glob(os.path.join(ROOT, "tools_*.py")):
            if not f.endswith(("_en.py", "_en_more.py")):
                src += open(f, encoding="utf-8").read()
        missing = [t for t in sorted(U.NET_BUTTONS) if f'"{t}"' not in src and f"'{t}'" not in src]
        self.assertEqual(missing, [])

    def test_offline_buttons_are_never_blocked(self):
        for name in ("VERBINDUNG PRÜFEN", "SPEICHERN…", "LADEN…", "NEU", "KONVERTIEREN", "CSV EXPORT", "OK", "SCHLIESSEN",
                     "ABBRECHEN", "ZUM ASSISTENTEN", "HAUPTFENSTER ZEIGEN", "? HILFE", "SESSION LADEN…",
                     "IN ALLEN LISTEN SUCHEN", "ALLE LISTEN PRÜFEN"):                 # UNITY arbeitet ohne Konsole aus dem Dump
            self.assertNotIn(name, U.NET_BUTTONS, name)


class FakeText:
    def __init__(self):
        self.parts, self.tags, self.opts = [], {}, {}

    def configure(self, **kw):
        self.opts.update(kw)

    def delete(self, a, b):
        self.parts.clear()

    def insert(self, idx, text, tags=()):
        self.parts.append((text, tuple(tags)))

    def tag_configure(self, name, **kw):
        self.tags[name] = kw


class PaintCheck(unittest.TestCase):
    def steps(self):
        S = conncheck.Step
        return [S("ok", "Adresse", "Adresse sieht gut aus."), S("fail", "PS5 erreichbar", "Keine Antwort von 1.2.3.4."),
                S("skip", "Payload antwortet"), S("warn", "Port", "anderer Port"), S("info", "Hinweis", "Firewall 755")]

    def test_colours_follow_the_state(self):
        t = FakeText()
        U.paint_steps(t, self.steps())
        self.assertEqual(t.tags["ok"]["foreground"], TC.OK)
        self.assertEqual(t.tags["fail"]["foreground"], TC.ERROR)
        self.assertEqual(t.tags["warn"]["foreground"], TC.WARN)
        marks = {tags[0]: text.strip() for text, tags in t.parts if tags[0] in ("ok", "fail", "warn", "skip", "info")}
        self.assertEqual(marks, {"ok": "✓", "fail": "✗", "skip": "–", "warn": "!", "info": "•"})

    def test_details_only_for_problems_and_notes(self):
        t = FakeText()
        U.paint_steps(t, self.steps())
        details = [text.strip() for text, tags in t.parts if tags == ("detail",)]
        self.assertEqual(details, ["Keine Antwort von 1.2.3.4.", "anderer Port", "Firewall 755"])   # nicht beim gruenen Haken

    def test_height_fits_and_is_capped(self):
        t = FakeText()
        U.paint_steps(t, self.steps())
        self.assertGreaterEqual(t.opts["height"], 5)
        self.assertEqual(t.opts["state"], "disabled")
        long = [conncheck.Step("fail", "x", "y" * 5000)]
        U.paint_steps(t, long)
        self.assertEqual(t.opts["height"], 14)

    def test_single_message(self):
        t = FakeText()
        U.paint_message(t, "fail", "kaputt")
        self.assertEqual(t.parts[0][1], ("fail",))
        self.assertEqual(t.parts[1][0], "kaputt\n")


class Chips(unittest.TestCase):
    def test_help_chip_carries_the_explanation(self):
        chip = U.help_chip(None, "SIGNATUR")
        self.assertIn("Byte-Muster", chip.__dict__["_tooltip"].current())


class EmptyTables(unittest.TestCase):
    def setUp(self):                                            # andere Tests legen Tabellen an: hier mit leerer Liste arbeiten
        self._saved = TC._EMPTY[:]
        TC._EMPTY[:] = []

    def tearDown(self):
        TC._EMPTY[:] = self._saved

    def test_hint_shows_in_empty_tables_and_hides_with_the_first_row(self):
        class Tv:
            rows = []

            def get_children(self):
                return self.rows

        class Lbl:
            def __init__(self):
                self.mgr, self.log = "", []

            def winfo_manager(self):
                return self.mgr

            def place(self, **kw):
                self.mgr = "place"
                self.log.append("show")

            def place_forget(self):
                self.mgr = ""
                self.log.append("hide")

            def lift(self):
                pass
        tv, lbl = Tv(), Lbl()
        import weakref
        TC._EMPTY.append((weakref.ref(tv), lbl))
        try:
            TC.refresh_empty()
            self.assertEqual(lbl.log, ["show"])
            TC.refresh_empty()
            self.assertEqual(lbl.log, ["show"])                    # kein Flackern
            tv.rows = ["r1"]
            TC.refresh_empty()
            self.assertEqual(lbl.log, ["show", "hide"])
            tv.rows = []
            TC.refresh_empty()
            self.assertEqual(lbl.log, ["show", "hide", "show"])
        finally:
            TC._EMPTY[:] = [e for e in TC._EMPTY if e[1] is not lbl]

    def test_dead_tables_are_forgotten(self):
        import weakref

        class Tv:
            def get_children(self):
                return []
        tv = Tv()
        TC._EMPTY.append((weakref.ref(tv), types.SimpleNamespace()))
        self.assertEqual(len(TC._EMPTY), 1)
        del tv
        TC.refresh_empty()
        self.assertEqual(TC._EMPTY, [])

    def test_main_tables_have_a_hint(self):
        for f, needle in (("tools_scan_gui.py", "ERSTER SCAN"), ("tools_pointer_gui.py", "KARTE ERSTELLEN"),
                          ("tools_assist_gui.py", "SUCHEN"), ("tools_gui.py", "SERVER-SCAN")):
            src = open(os.path.join(ROOT, f), encoding="utf-8").read()
            self.assertRegex(src, rf'empty="[^"]*{re.escape(needle)}')
        for text in ("Noch keine Treffer. Gib einen Wert ein und klicke ERSTER SCAN.",):
            old = T.lang()
            T.set_lang("en")
            try:
                self.assertIn("FIRST SCAN", T.translate(text))
            finally:
                T.set_lang(old)


class Button(unittest.TestCase):
    def test_return_key_and_focus_ring(self):
        calls = []

        class B:
            def __init__(self, *a, **kw):
                self.kw = kw
                self.binds = {}

            def bind(self, seq, fn, add=None):
                self.binds[seq] = fn

            def invoke(self):
                calls.append("invoke")
        old = TC.tk.Button
        TC.tk.Button = B
        try:
            b = TC.button(None, "X", lambda: None)
        finally:
            TC.tk.Button = old
        self.assertEqual(b.kw["highlightcolor"], TC.ACCENT)                  # heller Fokusring
        self.assertEqual(b.kw["disabledforeground"], TC.TEXT_DIM2)
        b.binds["<Return>"](None)
        b.binds["<KP_Enter>"](None)
        self.assertEqual(calls, ["invoke", "invoke"])


class BusyAndReconnect(unittest.TestCase):
    def make(self, ready=False):
        w = G.ToolsWindow.__new__(G.ToolsWindow)
        w._jobs, w._busy_shown, w._busy_pending, w._connecting = 0, False, False, False
        w._was_ready = ready
        w.log_ = []
        w.afters, w.packed, w.running = [], [], []
        w.winfo_exists = lambda: True
        w.after = lambda ms, fn=None: w.afters.append((ms, getattr(fn, "__name__", fn)))
        w.lbl_state = object()
        w.busy = types.SimpleNamespace(pack=lambda **k: w.packed.append("bar"), pack_forget=lambda: w.packed.append("-bar"),
                                       start=lambda ms: w.running.append("start"), stop=lambda: w.running.append("stop"))
        w.lbl_busy = types.SimpleNamespace(pack=lambda **k: w.packed.append("lbl"), pack_forget=lambda: w.packed.append("-lbl"))
        w.app = types.SimpleNamespace(backend=types.SimpleNamespace(client=None, pid=None))
        w.bg_calls = []
        w.bg = lambda fn, ok=None, err=None, lock=True: w.bg_calls.append(fn.__name__)

        def _connect():
            return None
        w._connect = _connect
        return w

    def test_indicator_waits_a_moment_and_follows_the_job_count(self):
        w = self.make()
        w._jobs = 1
        w._busy_changed()
        self.assertEqual(w.afters, [(250, "_busy_show")])                  # nicht sofort: kurze Jobs sollen nicht flackern
        w._busy_changed()
        self.assertEqual(len(w.afters), 1)                                 # nur einmal planen
        w._busy_show()
        self.assertEqual(w.packed, ["bar", "lbl"])
        self.assertEqual(w.running, ["start"])
        w._job_done()
        self.assertEqual(w._jobs, 0)
        self.assertEqual(w.running, ["start", "stop"])
        self.assertEqual(w.packed[-2:], ["-bar", "-lbl"])

    def test_short_job_never_shows_the_indicator(self):
        w = self.make()
        w._jobs = 1
        w._busy_changed()
        w._job_done()                                                      # fertig, bevor die 0,25 s um sind
        w._busy_show()
        self.assertEqual(w.packed, [])

    def test_counter_never_goes_negative(self):
        w = self.make()
        w._job_done()
        self.assertEqual(w._jobs, 0)

    def test_main_window_connecting_later_reconnects_the_tools(self):
        w = self.make(ready=False)
        seen = []
        old = U.set_net_state
        U.set_net_state = lambda root, ready: seen.append(ready)
        try:
            w.app.backend.client, w.app.backend.pid = object(), 42         # Hauptfenster verbindet
            w._ui_tick()
            self.assertEqual(seen, [True])                                 # Knoepfe werden frei ...
            self.assertEqual(w.bg_calls, ["_connect"])                     # ... und die Werkzeuge verbinden nach
            self.assertTrue(w._connecting)
            w._ui_tick()
            self.assertEqual(w.bg_calls, ["_connect"])                     # kein zweiter Versuch
            w.app.backend.client = None                                    # Hauptfenster getrennt
            w._ui_tick()
            self.assertEqual(seen, [True, False])
            self.assertEqual(w.bg_calls, ["_connect"])                     # Trennen loest keinen Verbindungsversuch aus
            self.assertEqual(w.afters[-1][0], 700)                         # laeuft weiter
        finally:
            U.set_net_state = old

    def test_connected_callbacks_update_the_buttons(self):
        w = self.make()
        states, updates = [], []
        w._set_state = lambda text, color: states.append(text)
        w._net_update = lambda: updates.append(1)
        w._connecting = True
        w._connected_ok()
        self.assertEqual((states, updates, w._connecting), (["verbunden"], [1], False))
        w._connecting = True
        w._connected_fail(RuntimeError("weg"))
        self.assertIn("Fehler: weg", states[-1])
        self.assertFalse(w._connecting)


class SpacingScale(unittest.TestCase):
    SCALE = {0, 2, 4, 8, 12, 16}

    def test_all_paddings_use_the_scale(self):
        import ast
        bad = []
        files = [f for f in glob.glob(os.path.join(ROOT, "tools_*.py")) if not f.endswith(("_en.py", "_en_more.py"))]
        files.append(os.path.join(ROOT, "universal_gui.py"))
        for f in sorted(files):
            tree = ast.parse(open(f, encoding="utf-8").read())
            for n in ast.walk(tree):
                if isinstance(n, ast.keyword) and n.arg in ("padx", "pady"):
                    vals = []
                    if isinstance(n.value, ast.Constant):
                        vals = [n.value.value]
                    elif isinstance(n.value, ast.Tuple):
                        vals = [e.value for e in n.value.elts if isinstance(e, ast.Constant)]
                    bad += [(os.path.basename(f), n.value.lineno, v) for v in vals if v not in self.SCALE]
        self.assertEqual(bad, [], "Abstände nur aus 0, 2, 4, 8, 12, 16 (siehe theme/Abstandsraster)")


if __name__ == "__main__":
    unittest.main()
