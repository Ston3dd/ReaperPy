"""Tests: Datenordner (normal/gepackt) und Log-Rotation mit Absturzberichten."""
import logging
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import logsetup
import paths
from pathlib import Path


class Paths(unittest.TestCase):
    def setUp(self):
        self.env = dict(os.environ)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        if hasattr(sys, "frozen"):
            del sys.frozen

    def test_default_is_next_to_the_sources(self):
        os.environ.pop("REAPERPY_HOME", None)
        self.assertEqual(paths.data_dir(), paths.app_dir())

    def test_env_override_wins_and_creates_subfolders(self):
        os.environ["REAPERPY_HOME"] = os.path.join(self.tmp, "home")
        self.assertEqual(paths.data_dir(), os.path.join(self.tmp, "home"))
        self.assertTrue(os.path.isdir(paths.logs_dir()))
        self.assertTrue(os.path.isdir(paths.profiles_dir()))

    def test_frozen_uses_the_exe_folder_when_writable(self):
        os.environ.pop("REAPERPY_HOME", None)
        sys.frozen = True
        old = sys.executable
        sys.executable = os.path.join(self.tmp, "ReaperPy.exe")
        try:
            self.assertEqual(paths.data_dir(), self.tmp)
            self.assertTrue(paths.is_frozen())
        finally:
            sys.executable = old

    def test_frozen_falls_back_to_appdata_when_the_exe_folder_is_read_only(self):
        os.environ.pop("REAPERPY_HOME", None)
        os.environ["APPDATA"] = os.path.join(self.tmp, "ad")
        sys.frozen = True
        old_exe, old_access = sys.executable, os.access
        sys.executable = os.path.join(self.tmp, "ReaperPy.exe")
        paths.os.access = lambda p, m: False
        try:
            self.assertEqual(paths.data_dir(), os.path.join(self.tmp, "ad", "ReaperPy"))
        finally:
            paths.os.access = old_access
            sys.executable = old_exe

    def test_resource_uses_meipass_when_present(self):
        sys._MEIPASS = self.tmp
        try:
            self.assertEqual(paths.resource("assets", "x.ico"), os.path.join(self.tmp, "assets", "x.ico"))
        finally:
            del sys._MEIPASS
        self.assertTrue(paths.resource("assets", "reaperpy.ico").endswith(os.path.join("assets", "reaperpy.ico")))


class Logs(unittest.TestCase):
    def setUp(self):
        lg = logsetup.logger()
        for h in list(lg.handlers):
            lg.removeHandler(h)
            h.close()
        logsetup._inited = False
        self.tmp = tempfile.mkdtemp()
        self.old_hook, self.old_thook = sys.excepthook, threading.excepthook
        self.addCleanup(self.cleanup)

    def cleanup(self):
        lg = logsetup.logger()
        for h in list(lg.handlers):
            lg.removeHandler(h)
            h.close()
        logsetup._inited = False
        sys.excepthook, threading.excepthook = self.old_hook, self.old_thook
        shutil.rmtree(self.tmp, True)

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_rotation_keeps_at_most_backups_and_newest_lines(self):
        path = logsetup.init(self.tmp, max_bytes=2000, backups=3, hook_exceptions=False)
        for i in range(400):
            logsetup.log(f"Zeile {i:04d} " + "x" * 40)
        files = sorted(os.listdir(self.tmp))
        self.assertEqual(files, ["reaperpy.log", "reaperpy.log.1", "reaperpy.log.2", "reaperpy.log.3"])
        self.assertLessEqual(sum(os.path.getsize(os.path.join(self.tmp, f)) for f in files), 4 * 2200)
        self.assertIn("Zeile 0399", self.read(path))                       # Neuestes steht im aktuellen Log
        self.assertNotIn("Zeile 0000", "".join(self.read(os.path.join(self.tmp, f)) for f in files))   # Aeltestes rotiert weg
        self.assertEqual(logsetup.log_files()[0], path)

    def test_levels_and_multiline_messages(self):
        path = logsetup.init(self.tmp, hook_exceptions=False)
        logsetup.log("alles gut", "ok")
        logsetup.log("kaputt", "err")
        logsetup.log("achtung\nzweite Zeile", "warn")
        txt = self.read(path)
        self.assertRegex(txt, r"INFO\s+alles gut")
        self.assertRegex(txt, r"ERROR\s+kaputt")
        self.assertRegex(txt, r"WARNING\s+achtung \| zweite Zeile")

    def test_init_is_idempotent(self):
        p1 = logsetup.init(self.tmp, hook_exceptions=False)
        p2 = logsetup.init(self.tmp, hook_exceptions=False)
        self.assertEqual(p1, p2)
        self.assertEqual(len(logsetup.logger().handlers), 1)

    def test_uncaught_exceptions_and_tk_callbacks_are_logged_with_traceback(self):
        path = logsetup.init(self.tmp)
        shown = []
        sys.excepthook = lambda *a: None
        logsetup._hook_exceptions()                                          # Haken auf dem Test-Haken
        try:
            raise ValueError("Testfehler eins")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        root = type("R", (), {"report_callback_exception": lambda self, *a: shown.append(a[1])})()
        logsetup.install_tk(root)
        try:
            int(object())
        except TypeError:
            root.report_callback_exception(*sys.exc_info())
        txt = self.read(path)
        self.assertIn("Unbehandelter Fehler", txt)
        self.assertIn("ValueError: Testfehler eins", txt)
        self.assertIn("Tk-Callback-Fehler", txt)
        self.assertIn("TypeError", txt)
        self.assertEqual(len(shown), 1)                                      # urspruengliche Ausgabe bleibt erhalten

    def test_thread_exceptions_are_logged(self):
        path = logsetup.init(self.tmp)

        def boom():
            raise RuntimeError("Thread-Fehler")
        t = threading.Thread(target=boom, name="worker-x")
        t.start()
        t.join()
        self.assertIn("Fehler im Thread worker-x", self.read(path))
        self.assertIn("RuntimeError: Thread-Fehler", self.read(path))

    def test_broken_log_dir_never_raises(self):
        blocker = os.path.join(self.tmp, "datei")
        Path(blocker).write_text("", encoding="utf-8")
        self.assertIsNone(logsetup.init(os.path.join(blocker, "unter"), hook_exceptions=False))
        logsetup.log("geht trotzdem")                                        # kein Absturz


if __name__ == "__main__":
    unittest.main()
