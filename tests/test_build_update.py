"""Tests: Update-Pruefung, Versionsinfo, Build-Dateien (Spec/Bat), Start-Tab-Knopf und Hauptfenster-Handler."""
import os
import re
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import buildtools
import update_check as U
import version

ROOT = os.path.join(os.path.dirname(__file__), "..")


def rd(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class Versions(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(U.parse_version("v5.7.0"), ((5, 7, 0), 1, ""))
        self.assertEqual(U.parse_version("5.7"), ((5, 7, 0), 1, ""))
        self.assertEqual(U.parse_version("5.7.0-beta1"), ((5, 7, 0), 0, "beta1"))
        self.assertTrue(U.is_newer("5.8.0", "5.7.0"))
        self.assertTrue(U.is_newer("5.10.0", "5.9.9"))                           # numerisch, nicht als Text
        self.assertTrue(U.is_newer("5.7.0", "5.7.0-beta1"))
        self.assertFalse(U.is_newer("5.7.0-beta1", "5.7.0"))
        self.assertFalse(U.is_newer("5.7.0", "5.7.0"))
        for bad in ("", "abc", "x.y"):
            with self.assertRaises(ValueError):
                U.parse_version(bad)

    def test_project_version_is_valid(self):
        U.parse_version(version.__version__)
        self.assertEqual(version.APP_NAME, "ReaperPy")


class Resp:
    def __init__(self, data): self.data = data
    def read(self, n=-1): return self.data[:n] if n >= 0 else self.data
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Opener:
    def __init__(self, data): self.data, self.req = data, None
    def open(self, req, timeout=None): self.req = (req, timeout); return Resp(self.data)


class Fetch(unittest.TestCase):
    def test_fetch_json_validates_scheme_size_and_content(self):
        op = Opener(b'{"version": "5.8.0", "url": "https://x/dl"}')
        self.assertEqual(U.fetch_json("https://example.org/v.json", opener=op)["version"], "5.8.0")
        self.assertEqual(op.req[0].get_header("User-agent"), "ReaperPy-update-check")
        self.assertEqual(op.req[1], U.TIMEOUT)
        for url in ("http://example.org/v.json", "ftp://x/y", "file:///etc/passwd", "javascript:alert(1)", "example.org/v.json"):
            with self.assertRaises(ValueError):
                U.fetch_json(url, opener=op)
        U.fetch_json("http://localhost:8000/v.json", opener=op)                  # lokal darf http
        with self.assertRaises(ValueError):
            U.fetch_json("https://x/y", opener=Opener(b"x" * (U.MAX_BYTES + 5)))
        with self.assertRaises(ValueError):
            U.fetch_json("https://x/y", opener=Opener(b"[1, 2]"))

    def test_check_results(self):
        ok = lambda d: (lambda url: d)  # noqa: E731
        self.assertEqual(U.check("", "5.7.0").status, "off")
        r = U.check("https://x", "5.7.0", ok({"version": "5.8.0", "url": "https://x/dl", "notes": "Neu: Hotkeys"}))
        self.assertEqual((r.status, r.remote, r.url, r.notes, r.local), ("newer", "5.8.0", "https://x/dl", "Neu: Hotkeys", "5.7.0"))
        self.assertEqual(U.check("https://x", "5.7.0", ok({"version": "5.7.0"})).status, "uptodate")
        self.assertEqual(U.check("https://x", "5.7.0", ok({"version": "5.6.9"})).status, "uptodate")

    def test_bad_data_and_errors_become_error_results_without_raising(self):
        def boom(url): raise OSError("Netz weg")
        r = U.check("https://x", "5.7.0", boom)
        self.assertEqual(r.status, "error")
        self.assertIn("Netz weg", r.error)
        self.assertEqual(U.check("https://x", "5.7.0", lambda u: {"nope": 1}).status, "error")
        self.assertEqual(U.check("https://x", "5.7.0", lambda u: {"version": "kaputt"}).status, "error")
        self.assertEqual(U.check("https://x", "5.7.0", lambda u: (_ for _ in ()).throw(RuntimeError("x"))).status, "error")

    def test_only_https_download_links_are_passed_on_and_notes_are_cut(self):
        r = U.check("https://x", "1.0", lambda u: {"version": "2.0", "url": "javascript:alert(1)", "notes": "n" * 900})
        self.assertEqual((r.status, r.url, len(r.notes)), ("newer", "", 500))
        r = U.check("https://x", "1.0", lambda u: {"version": "2.0", "url": "http://evil/dl"})
        self.assertEqual(r.url, "")                                              # auch kein unverschluesseltes http


class BuildFiles(unittest.TestCase):
    def test_version_info_is_valid_pyinstaller_syntax(self):
        calls = {}

        def rec(name):
            return lambda *a, **k: calls.setdefault(name, []).append((a, k)) or (name, a, k)
        env = {n: rec(n) for n in ("VSVersionInfo", "FixedFileInfo", "StringFileInfo", "StringTable", "StringStruct", "VarFileInfo", "VarStruct")}
        eval(buildtools.version_info_text("5.7.0").split("\n", 1)[1], env)
        ffi = calls["FixedFileInfo"][0][1]
        self.assertEqual((ffi["filevers"], ffi["prodvers"]), ((5, 7, 0, 0), (5, 7, 0, 0)))
        strings = {a[0]: a[1] for a, _k in calls["StringStruct"]}
        self.assertEqual((strings["FileVersion"], strings["ProductVersion"], strings["OriginalFilename"]), ("5.7.0.0", "5.7.0.0", "ReaperPy.exe"))
        self.assertEqual(buildtools.version_info_text("5.8.1-beta2").count("5.8.1.0"), 2)

    def test_spec_covers_modules_assets_icon_and_version(self):
        spec = rd("ReaperPy.spec")
        self.assertIn("glob.glob(os.path.join(ROOT, '*.py'))", spec)             # alle Module automatisch
        self.assertIn("'test_', 'build', 'icon_art'", spec)
        self.assertIn("'assets'", spec)
        self.assertIn("reaperpy.ico", spec)
        self.assertIn("version_info.txt", spec)
        self.assertIn("collect_all(pkg)", spec)
        self.assertIn("console=False", spec)
        self.assertIn("exclude_binaries=True", spec)                              # Ordner-Version
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "assets", "reaperpy.ico")))

    def test_every_dynamically_imported_tab_module_is_a_project_file(self):
        """tools_gui laedt Tabs per __import__(name): jedes dieser Module muss als .py im Projekt liegen (die Spec nimmt alle mit)."""
        src = rd("tools_gui.py")
        mods = set(re.findall(r'\("(tools_\w+|klog_tab|script_tab)", "\w+Tab"', src)) | set(re.findall(r"from (tools_\w+|klog_tab|script_tab) import", src))
        self.assertGreaterEqual(len(mods), 8)
        for m in mods:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, m + ".py")), m)

    def test_batch_files_use_the_spec_and_keep_windows_line_endings(self):
        with open(os.path.join(ROOT, "build_exe.bat"), "rb") as f:
            raw = f.read()
        bat = raw.decode("utf-8")
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))                        # ueberall CRLF
        for needle in ("buildtools.py", "PyInstaller --noconfirm --clean ReaperPy.spec", "Compress-Archive", "version.__version__"):
            self.assertIn(needle, bat)
        self.assertNotIn("--hidden-import", bat)                                  # eine Quelle der Wahrheit: die Spec
        with open(os.path.join(ROOT, "ReaperPy.spec"), "rb") as f:
            self.assertNotIn(b"\n", f.read().replace(b"\r\n", b""))

    def test_no_stellar_blade_modules_left_for_the_build(self):
        for f in os.listdir(ROOT):
            if f.endswith(".py"):
                self.assertFalse(f.startswith("sb_") or f == "tools_sb_gui.py", f)


class StartButtonAndHandler(unittest.TestCase):
    def make_start(self, url):
        import tools_start_gui as S
        logs = []
        app = types.SimpleNamespace(backend=types.SimpleNamespace(client=None, pid=None), current_project=None, patches={}, gp=None,
                                    cfg={"update_url": url}, root=None)
        win = types.SimpleNamespace(app=app, log=lambda m, k="info": logs.append((k, m)), ui=lambda fn: fn())
        t = S.StartTab(None, win)
        t.bg = lambda job, ok=None, err=None: ok(job())
        return t, logs

    def test_no_url_gives_a_hint(self):
        t, logs = self.make_start("")
        t.check_updates()
        self.assertEqual(logs[-1][0], "info")
        self.assertIn("update_url", logs[-1][1])

    def test_results_are_reported_and_download_needs_confirmation(self):
        import tools_start_gui as S
        t, logs = self.make_start("https://x/v.json")
        opened, asked = [], []
        old_ask = S.messagebox.askyesno
        self.addCleanup(setattr, S.messagebox, "askyesno", old_ask)           # Fake-Dialogmodul wird von allen Tests geteilt
        S.messagebox.askyesno = lambda *a, **k: asked.append(a) or True
        import webbrowser
        old = webbrowser.open
        webbrowser.open = opened.append
        try:
            orig = U.check
            U.check = lambda url, cur, fetch=None: U.Result("newer", cur, "9.9.9", "https://x/dl", "Hotkeys")
            t.check_updates()
            self.assertIn("Neue Version 9.9.9", logs[-1][1])
            self.assertIn("Hotkeys", logs[-1][1])
            self.assertEqual(opened, ["https://x/dl"])
            self.assertEqual(len(asked), 1)
            S.messagebox.askyesno = lambda *a, **k: False
            opened.clear()
            t.check_updates()
            self.assertEqual(opened, [])                                           # ohne Zustimmung wird nichts geoeffnet
            U.check = lambda url, cur, fetch=None: U.Result("uptodate", cur, cur)
            t.check_updates()
            self.assertEqual(logs[-1][0], "ok")
            U.check = lambda url, cur, fetch=None: U.Result("error", cur, error="OSError: weg")
            t.check_updates()
            self.assertEqual(logs[-1][0], "err")
        finally:
            U.check = orig
            webbrowser.open = old

    def test_main_window_logs_only_when_newer(self):
        import gui
        from i18n import Translator
        app = object.__new__(gui.App)
        app.tr = Translator("en")
        out = []
        app.log_msg = lambda m, tag=None: out.append((tag, m))
        app._on_update(U.Result("uptodate", "5.7.0", "5.7.0"))
        app._on_update(U.Result("error", "5.7.0", error="x"))
        app._on_update(U.Result("off"))
        self.assertEqual(out, [])
        app._on_update(U.Result("newer", "5.7.0", "5.8.0", "https://x/dl"))
        self.assertEqual(out, [("accent", "[update] New version 5.8.0 available (installed: 5.7.0) - download: https://x/dl")])

    def test_async_check_runs_by_default_and_only_off_when_disabled(self):
        import gui
        app = object.__new__(gui.App)
        started = []
        orig = gui.threading.Thread
        gui.threading.Thread = lambda **k: started.append(k) or types.SimpleNamespace(start=lambda: None)
        try:
            app.cfg = {"auto_update_check": False}
            app._update_check_async()
            app.cfg = {"update_url": "https://x/v.json", "auto_update_check": False}
            app._update_check_async()
            self.assertEqual(started, [])
            app.cfg = {}                                              # Standard: GitHub-Releases pruefen
            app._update_check_async()
            app.cfg = {"update_url": "https://x/v.json"}              # alte JSON-Variante bleibt moeglich
            app._update_check_async()
            self.assertEqual(len(started), 2)
        finally:
            gui.threading.Thread = orig


if __name__ == "__main__":
    unittest.main()
