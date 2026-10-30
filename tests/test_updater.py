"""Tests: updater.py (GitHub release -> download -> unpack -> install -> restart) and the update dialog logic.
Everything runs offline against fake release data and local zip files."""
import hashlib
import io
import os
import sys
import tempfile
import threading
import types
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import updater as U


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)


def release_json(tag="v9.9.9", assets=None):
    return {"tag_name": tag, "body": "notes", "html_url": "https://github.com/a/b/releases/tag/" + tag,
            "zipball_url": "https://api.github.com/repos/a/b/zipball/" + tag, "assets": assets or []}


def asset(name, size=10, digest=""):
    return {"name": name, "browser_download_url": "https://github.com/a/b/releases/download/v9/" + name,
            "size": size, "digest": digest}


class Parsing(unittest.TestCase):
    def test_release_and_asset_choice(self):
        rel = U.parse_release(release_json(assets=[asset("ReaperPy_v9.9.9_win64.zip"), asset("src.zip")]))
        self.assertEqual(rel.version, "9.9.9")
        self.assertIn("win64", U.pick_asset(rel, True)[1])
        self.assertEqual(U.pick_asset(rel, False)[1], "src.zip")
        only_src = U.parse_release(release_json(assets=[asset("src.zip")]))
        with self.assertRaises(U.UpdateError):
            U.pick_asset(only_src, True)                       # EXE needs the win64 build
        none = U.parse_release(release_json())
        self.assertTrue(U.pick_asset(none, False)[1].endswith("-source.zip"))   # falls back to the tag archive

    def test_foreign_hosts_are_dropped(self):
        d = release_json(assets=[{"name": "x.zip", "browser_download_url": "https://evil.example/x.zip", "size": 1}])
        self.assertEqual(U.parse_release(d).assets, [])
        self.assertFalse(U.allowed_url("http://github.com/x"))
        self.assertFalse(U.allowed_url("https://github.com.evil.example/x"))
        self.assertTrue(U.allowed_url("https://github.com/x"))

    def test_bad_tags_and_repo_names(self):
        with self.assertRaises(U.UpdateError):
            U.parse_release({"tag_name": ""})
        with self.assertRaises(ValueError):
            U.parse_release({"tag_name": "nightly"})
        with self.assertRaises(U.UpdateError):
            U.latest_release("not a repo", fetch=lambda u: {})

    def test_check_status(self):
        newer = U.check("a/b", "5.9.0", fetch=lambda u: release_json("v5.10.0"))
        self.assertEqual((newer.status, newer.release.version), ("newer", "5.10.0"))
        self.assertEqual(U.check("a/b", "5.9.0", fetch=lambda u: release_json("v5.9.0")).status, "uptodate")

        def boom(u):
            raise OSError("offline")
        self.assertEqual(U.check("a/b", "5.9.0", fetch=boom).status, "error")

    def test_should_offer_respects_skip(self):
        c = U.check("a/b", "5.9.0", fetch=lambda u: release_json("v6.0.0"))
        self.assertTrue(U.should_offer(c, ""))
        self.assertFalse(U.should_offer(c, "6.0.0"))
        self.assertFalse(U.should_offer(c, "v6.0.0"))
        self.assertTrue(U.should_offer(c, "5.9.5"))
        self.assertFalse(U.should_offer(U.Check(status="uptodate"), ""))


class Unpack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def test_zip_slip_and_absolute_paths_are_refused(self):
        for bad in ("../evil.txt", "/abs.txt", "a/../../evil.txt", "C:/win.txt"):
            z = os.path.join(self.d, "bad.zip")
            make_zip(z, {bad: "x"})
            with self.assertRaises(U.UpdateError, msg=bad):
                U.extract_zip(z, os.path.join(self.d, "out"))
        self.assertFalse(os.path.exists(os.path.join(self.d, "evil.txt")))

    def test_not_a_zip(self):
        p = os.path.join(self.d, "x.zip")
        with open(p, "wb") as f:
            f.write(b"hello")
        with self.assertRaises(U.UpdateError):
            U.extract_zip(p, os.path.join(self.d, "out"))

    def test_find_root_and_validation(self):
        z = os.path.join(self.d, "s.zip")
        make_zip(z, {"proj-abc/gui.py": "x", "proj-abc/version.py": "x"})
        out = os.path.join(self.d, "o")
        U.extract_zip(z, out)
        root = U.find_root(out)
        self.assertTrue(root.endswith("proj-abc"))
        U.validate_root(root, frozen=False)
        with self.assertRaises(U.UpdateError):
            U.validate_root(root, frozen=True)                 # no ReaperPy.exe


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = os.path.join(self.tmp.name, "app")
        self.s = os.path.join(self.tmp.name, "new")
        self.addCleanup(self.tmp.cleanup)
        for base, files in ((self.t, {"gui.py": "OLD", "reaperpy_config.json": "MYCFG", "applied.json": "MINE",
                                      "profiles/mine.json": "keep", "logs/a.log": "log", "old_only.py": "o"}),
                            (self.s, {"gui.py": "NEW", "version.py": "NEW", "reaperpy_config.json": "DEFAULT",
                                      "profiles/mine.json": "overwrite?", "profiles/shipped.json": "new",
                                      "logs/a.log": "SHOULD NOT", "sub/x.py": "NEW"})):
            for n, c in files.items():
                p = os.path.join(base, *n.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(c)

    def rd(self, *p):
        with open(os.path.join(self.t, *p), encoding="utf-8") as f:
            return f.read()

    def test_user_data_is_protected_and_code_replaced(self):
        U.install(self.s, self.t)
        self.assertEqual(self.rd("gui.py"), "NEW")
        self.assertEqual(self.rd("sub", "x.py"), "NEW")
        self.assertEqual(self.rd("reaperpy_config.json"), "MYCFG")      # config kept
        self.assertEqual(self.rd("applied.json"), "MINE")
        self.assertEqual(self.rd("profiles", "mine.json"), "keep")      # own profile kept ...
        self.assertEqual(self.rd("profiles", "shipped.json"), "new")    # ... shipped one added
        self.assertEqual(self.rd("logs", "a.log"), "log")               # logs untouched
        self.assertEqual(self.rd("old_only.py"), "o")                   # nothing is deleted

    def test_rollback_restores_everything_on_failure(self):
        real = U.shutil.copy2
        calls = []

        def flaky(src, dst, *a, **k):
            calls.append(dst)
            if len(calls) == 3:
                raise OSError("disk full")
            return real(src, dst, *a, **k)
        U.shutil.copy2 = flaky
        try:
            with self.assertRaises(U.UpdateError):
                U.install(self.s, self.t)
        finally:
            U.shutil.copy2 = real
        self.assertEqual(self.rd("gui.py"), "OLD")                       # back to the old state
        self.assertFalse(os.path.exists(os.path.join(self.t, "version.py")))
        self.assertFalse(os.path.exists(os.path.join(self.t, "sub", "x.py")))

    def test_full_run_with_checksum(self):
        pkg = os.path.join(self.tmp.name, "pkg.zip")
        make_zip(pkg, {"gui.py": "V2", "version.py": "V2"})
        with open(pkg, "rb") as f:
            data = f.read()
        good = "sha256:" + hashlib.sha256(data).hexdigest()

        class FakeOpener:
            def open(self, req, timeout=0):
                r = io.BytesIO(data)
                r.headers = {"Content-Length": str(len(data))}
                r.__enter__ = lambda s=r: s
                return _Ctx(r)

        class _Ctx:
            def __init__(self, r): self.r, self.headers = r, r.headers
            def read(self, n=-1): return self.r.read(n)
            def __enter__(self): return self
            def __exit__(self, *a): return False

        rel = U.parse_release(release_json(assets=[asset("src.zip", len(data), good)]))
        stages = []
        files = U.run_update(rel, self.t, False, stage=stages.append, opener=FakeOpener())
        self.assertEqual(stages, ["download", "unpack", "install"])
        self.assertIn("gui.py", files)
        self.assertEqual(self.rd("gui.py"), "V2")
        self.assertFalse(os.path.exists(os.path.join(self.t, U.STAGING)))   # staging removed
        self.assertFalse(os.path.exists(os.path.join(self.t, U.BACKUP)))

        bad = U.parse_release(release_json(assets=[asset("src.zip", len(data), "sha256:" + "0" * 64)]))
        with self.assertRaises(U.UpdateError):
            U.run_update(bad, self.t, False, opener=FakeOpener())
        self.assertEqual(self.rd("gui.py"), "V2")                           # wrong checksum: nothing touched

    def test_sha256_sidecar_file_is_used_when_github_gives_no_digest(self):
        pkg = os.path.join(self.tmp.name, "pkg2.zip")
        make_zip(pkg, {"gui.py": "V3", "version.py": "V3"})
        with open(pkg, "rb") as f:
            data = f.read()
        side_ok = (hashlib.sha256(data).hexdigest() + "  src.zip\n").encode()
        side_bad = ("0" * 64 + "  src.zip\n").encode()

        class Resp:
            def __init__(self, b): self.b, self.headers = io.BytesIO(b), {"Content-Length": str(len(b))}
            def read(self, n=-1): return self.b.read(n)
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def opener(sidecar):
            class O:
                def open(self, req, timeout=0):
                    return Resp(sidecar if req.full_url.endswith(".sha256") else data)
            return O()

        assets = [asset("src.zip", len(data)), asset("src.zip.sha256", 90)]
        rel = U.parse_release(release_json(assets=assets))
        logs = []
        U.run_update(rel, self.t, False, opener=opener(side_ok), log=logs.append)
        self.assertEqual(self.rd("gui.py"), "V3")
        self.assertEqual(logs, [])                                   # Pruefsumme vorhanden -> keine Warnung
        Path(os.path.join(self.t, "gui.py")).write_text("OLD", encoding="utf-8")
        with self.assertRaises(U.UpdateError):                       # falsche Pruefsumme -> nichts angefasst
            U.run_update(rel, self.t, False, opener=opener(side_bad))
        self.assertEqual(self.rd("gui.py"), "OLD")
        rel2 = U.parse_release(release_json(assets=[asset("src.zip", len(data))]))
        logs.clear()
        U.run_update(rel2, self.t, False, opener=opener(side_ok), log=logs.append)       # gar keine Pruefsumme
        self.assertTrue(any("no checksum" in m for m in logs))


class Environment(unittest.TestCase):
    def test_git_checkout_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(U.blocked_reason(d, False), "")
            os.makedirs(os.path.join(d, ".git"))
            self.assertEqual(U.blocked_reason(d, False), "git")
            self.assertEqual(U.blocked_reason(d, True), "")                  # an EXE folder is no checkout

    def test_restart_command(self):
        self.assertEqual(U.restart_command(True, "C:/R/ReaperPy.exe", ["C:/R/ReaperPy.exe", "--x"]),
                         ["C:/R/ReaperPy.exe", "--x"])
        cmd = U.restart_command(False, "python", ["gui.py"])
        self.assertEqual(cmd[0], "python")
        self.assertTrue(os.path.isabs(cmd[1]) and cmd[1].endswith("gui.py"))

    def test_cleanup_removes_leftovers_only(self):
        with tempfile.TemporaryDirectory() as d:
            for n in (U.STAGING, U.BACKUP, "profiles"):
                os.makedirs(os.path.join(d, n))
            U.cleanup(d)
            self.assertEqual(sorted(os.listdir(d)), ["profiles"])


class Job(unittest.TestCase):
    def drain(self, job):
        job.thread.join(5)
        out = []
        while not job.events.empty():
            out.append(job.events.get())
        return out

    def test_events_on_success_error_and_cancel(self):
        def ok(rel, target, frozen, progress, cancel, stage, log):
            stage("download"); progress(5, 10); return ["a.py"]
        ev = self.drain(U.UpdateJob(None, "t", False, run=ok).start())
        self.assertEqual(ev, [("stage", "download"), ("progress", 5, 10), ("done", ["a.py"])])

        def fail(*a, **k):
            raise U.UpdateError("kaputt")
        self.assertEqual(self.drain(U.UpdateJob(None, "t", False, run=fail).start()), [("error", "kaputt")])

        def cancelled(*a, **k):
            raise U.Cancelled("x")
        self.assertEqual(self.drain(U.UpdateJob(None, "t", False, run=cancelled).start()), [("cancelled",)])


class GuiHandler(unittest.TestCase):
    def make_app(self, **cfg):
        import ghost_tk; ghost_tk.install()  # noqa: E702
        import gui
        from i18n import Translator
        app = object.__new__(gui.App)
        app.tr = Translator("en")
        app.cfg = cfg
        app.root = None
        app.logs = []
        app.log_msg = lambda m, tag=None: app.logs.append((tag, m))
        return gui, app

    def test_no_dialog_for_uptodate_error_or_git_checkout(self):
        gui, app = self.make_app()
        app._on_update_gh(U.Check(status="error", error="x"), manual=False)
        app._on_update_gh(U.Check(status="uptodate", local="5.9.0"), manual=False)
        self.assertEqual(app.logs, [])                                       # silent at startup
        app._on_update_gh(U.Check(status="uptodate", local="5.9.0"), manual=True)
        self.assertEqual(app.logs[-1][0], "ok")
        app._on_update_gh(U.Check(status="error", error="offline"), manual=True)
        self.assertEqual(app.logs[-1][0], "err")
        # this test folder is a source tree: with a .git folder the update is only announced
        orig = U.blocked_reason
        U.blocked_reason = lambda t, f: "git"
        try:
            rel = U.parse_release(release_json("v99.0.0"))
            app._on_update_gh(U.Check("newer", "5.9.0", rel), manual=False)
        finally:
            U.blocked_reason = orig
        self.assertIn("git pull", app.logs[-1][1])

    def test_skipped_version_is_not_offered_again(self):
        gui, app = self.make_app(update_skip_version="99.0.0")
        opened = []
        import update_ui
        orig, ob = update_ui.UpdateDialog, U.blocked_reason
        update_ui.UpdateDialog = lambda *a, **k: opened.append(a) or types.SimpleNamespace()
        U.blocked_reason = lambda t, f: ""
        try:
            rel = U.parse_release(release_json("v99.0.0"))
            app._on_update_gh(U.Check("newer", "5.9.0", rel), manual=False)
            self.assertEqual(opened, [])
            app._on_update_gh(U.Check("newer", "5.9.0", rel), manual=True)    # manual check shows it anyway
            self.assertEqual(len(opened), 1)
            app.cfg = {}
            app._update_dlg = None
            app._on_update_gh(U.Check("newer", "5.9.0", rel), manual=False)
            self.assertEqual(len(opened), 2)
        finally:
            update_ui.UpdateDialog, U.blocked_reason = orig, ob


if __name__ == "__main__":
    unittest.main()
