import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import self_update as S  # noqa: E402


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)


def gh(tag="v5.9.1", sha=True, **over):
    base = "https://github.com/Ston3dd/ReaperPy/releases/download/" + tag + "/"
    name = f"ReaperPy_{tag}_win64.zip"
    d = {"tag_name": tag, "draft": False, "prerelease": False, "body": "Notes", "html_url": "https://github.com/Ston3dd/ReaperPy/releases/tag/" + tag,
         "assets": [{"name": name, "browser_download_url": base + name, "size": 10}]}
    if sha:
        d["assets"].append({"name": name + ".sha256", "browser_download_url": base + name + ".sha256", "size": 90})
    d.update(over)
    return d


class Resp:
    def __init__(self, data, url="https://x"):
        self.b, self.url, self.headers = io.BytesIO(data), url, {"Content-Length": str(len(data))}

    def read(self, n=-1): return self.b.read(n)
    def geturl(self): return self.url
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Opener:
    def __init__(self, routes): self.routes, self.seen = routes, []

    def open(self, req, timeout=None):
        self.seen.append(req.full_url)
        data = self.routes[req.full_url]
        return data if isinstance(data, Resp) else Resp(data, req.full_url)


class Check(unittest.TestCase):
    def test_newer_and_uptodate(self):
        r = S.check("Ston3dd/ReaperPy", "5.9.0", fetch=lambda u: json.dumps(gh()).encode())
        self.assertEqual((r.status, r.remote), ("newer", "5.9.1"))
        self.assertTrue(r.release.asset_url.endswith("ReaperPy_v5.9.1_win64.zip") and r.release.sha_url.endswith(".sha256"))
        self.assertEqual(S.check("a/b", "5.9.1", fetch=lambda u: json.dumps(gh()).encode()).status, "uptodate")
        self.assertEqual(S.check("a/b", "5.10.0", fetch=lambda u: json.dumps(gh()).encode()).status, "uptodate")

    def test_prerelease_draft_and_garbage(self):
        for d in (gh(prerelease=True), gh(draft=True), {"tag_name": ""}):
            self.assertEqual(S.check("a/b", "5.0.0", fetch=lambda u, d=d: json.dumps(d).encode()).status, "uptodate")
        self.assertEqual(S.check("a/b", "5.0.0", fetch=lambda u: b"<html>").status, "error")
        self.assertEqual(S.check("../x", "5.0.0", fetch=lambda u: b"{}").status, "error")

    def test_foreign_asset_hosts_are_ignored(self):
        d = gh()
        d["assets"][0]["browser_download_url"] = "https://evil.example/ReaperPy_v5.9.1_win64.zip"
        rel = S.parse_release(d)
        self.assertEqual(rel.asset_url, "")

    def test_host_rules(self):
        for u in ("https://github.com/x", "https://objects.githubusercontent.com/x", "https://a.githubusercontent.com/x"):
            self.assertTrue(S.host_ok(u), u)
        for u in ("http://github.com/x", "https://github.com.evil.io/x", "https://evilgithubusercontent.com/x", "file:///x", "https:///x"):
            self.assertFalse(S.host_ok(u), u)


class Download(unittest.TestCase):
    def test_download_hash_and_limits(self):
        data = os.urandom(200_000)
        url = "https://github.com/a/b/f.zip"
        with tempfile.TemporaryDirectory() as d:
            calls = []
            h = S.download(url, os.path.join(d, "f"), progress=lambda a, b: calls.append((a, b)), opener=Opener({url: data}))
            self.assertEqual(h, hashlib.sha256(data).hexdigest())
            self.assertEqual(calls[-1], (len(data), len(data)))
            with self.assertRaises(S.UpdateError):
                S.download(url, os.path.join(d, "g"), opener=Opener({url: data}), max_bytes=1000)
            with self.assertRaises(S.UpdateError):                      # Weiterleitung auf fremden Host
                S.download(url, os.path.join(d, "h"), opener=Opener({url: Resp(data, "https://evil.example/x")}))
            with self.assertRaises(S.UpdateError):
                S.download("http://github.com/x", os.path.join(d, "i"))

    def test_parse_sha(self):
        h = "ab" * 32
        self.assertEqual(S.parse_sha256(f"{h.upper()}  ReaperPy.zip\n"), h)
        with self.assertRaises(S.UpdateError):
            S.parse_sha256("nothing")


class Install(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.app = os.path.join(self.t.name, "app"); os.makedirs(os.path.join(self.app, "_internal"))
        self.zip = os.path.join(self.t.name, "u.zip")

    def write(self, rel, data):
        p = Path(self.app, rel); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)

    def read(self, rel): return Path(self.app, rel).read_bytes()

    def test_replaces_adds_and_keeps_user_data(self):
        self.write("ReaperPy.exe", b"old"); self.write("_internal/a.dll", b"old-a")
        self.write("reaperpy_config.json", b'{"ps5_ip":"1.2.3.4"}'); self.write("profiles/x.json", b"mine")
        make_zip(self.zip, {"ReaperPy.exe": b"NEW", "_internal/a.dll": b"NEW-a", "_internal/b.dll": b"NEW-b",
                            "reaperpy_config.json": b"{}", "profiles/x.json": b"overwrite!", "assets/i.png": b"p"})
        n = S.install(self.zip, self.app, required="ReaperPy.exe")
        self.assertEqual(n, 4)
        self.assertEqual((self.read("ReaperPy.exe"), self.read("_internal/a.dll"), self.read("_internal/b.dll")), (b"NEW", b"NEW-a", b"NEW-b"))
        self.assertEqual(self.read("reaperpy_config.json"), b'{"ps5_ip":"1.2.3.4"}')
        self.assertEqual(self.read("profiles/x.json"), b"mine")
        left = [p for p in Path(self.app).rglob("*") if p.suffix in (".old", ".rpnew")]
        self.assertEqual(left, [])

    def test_rejects_unsafe_archives_and_changes_nothing(self):
        self.write("ReaperPy.exe", b"old")
        for bad in ("../evil.txt", "a/../../evil.txt", "/abs.txt", "C:/evil.txt", "..\\evil.txt"):
            make_zip(self.zip, {"ReaperPy.exe": b"NEW", bad: b"x"})
            with self.assertRaises(S.UpdateError, msg=bad):
                S.install(self.zip, self.app)
            self.assertEqual(self.read("ReaperPy.exe"), b"old")
        self.assertFalse(os.path.exists(os.path.join(self.t.name, "evil.txt")))
        make_zip(self.zip, {"other.txt": b"x"})
        with self.assertRaises(S.UpdateError):
            S.install(self.zip, self.app, required="ReaperPy.exe")

    def test_rollback_when_swap_fails_midway(self):
        self.write("ReaperPy.exe", b"old"); self.write("_internal/a.dll", b"old-a")
        make_zip(self.zip, {"ReaperPy.exe": b"NEW", "_internal/a.dll": b"NEW-a"})
        real, calls = os.replace, []

        def flaky(src, dst):
            calls.append(dst)
            if str(src).endswith("a.dll.rpnew"):
                raise PermissionError("gesperrt")
            return real(src, dst)
        os.replace = flaky
        try:
            with self.assertRaises(PermissionError):
                S.install(self.zip, self.app)
        finally:
            os.replace = real
        self.assertEqual((self.read("ReaperPy.exe"), self.read("_internal/a.dll")), (b"old", b"old-a"))
        self.assertEqual([p for p in Path(self.app).rglob("*") if p.suffix in (".old", ".rpnew")], [])

    def test_locked_old_file_is_listed_and_cleaned_next_start(self):
        self.write("ReaperPy.exe", b"old")
        make_zip(self.zip, {"ReaperPy.exe": b"NEW"})
        real = os.remove

        def locked(p):
            if str(p).endswith(".old"):
                raise PermissionError("laeuft noch")
            return real(p)
        os.remove = locked
        try:
            S.install(self.zip, self.app)
        finally:
            os.remove = real
        self.assertTrue(os.path.exists(os.path.join(self.app, "ReaperPy.exe.old")))
        self.assertEqual(json.loads(Path(self.app, S.OLD_LIST).read_text(encoding="utf-8")), ["ReaperPy.exe.old"])
        self.assertEqual(S.cleanup_old(self.app), 1)
        self.assertFalse(os.path.exists(os.path.join(self.app, "ReaperPy.exe.old")))
        self.assertFalse(os.path.exists(os.path.join(self.app, S.OLD_LIST)))

    def test_cleanup_never_deletes_foreign_files(self):
        self.write("keep.txt", b"x"); self.write("../outside.old", b"x")
        Path(self.app, S.OLD_LIST).write_text(json.dumps(["keep.txt", "../outside.old"]), encoding="utf-8")
        S.cleanup_old(self.app)
        self.assertTrue(os.path.exists(os.path.join(self.app, "keep.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.t.name, "outside.old")))

    def test_run_update_end_to_end_and_hash_mismatch(self):
        self.write("ReaperPy.exe", b"old")
        make_zip(self.zip, {"ReaperPy.exe": b"NEW"})
        blob = Path(self.zip).read_bytes()
        rel = S.parse_release(gh())
        routes = {rel.asset_url: blob, rel.sha_url: (hashlib.sha256(blob).hexdigest() + "  x.zip\n").encode()}
        stages = []
        self.assertEqual(S.run_update(rel, self.app, progress=lambda *a: stages.append(a[0]), opener=Opener(routes)), 1)
        self.assertEqual(self.read("ReaperPy.exe"), b"NEW")
        self.assertTrue({"download", "verify", "install"} <= set(stages))
        routes[rel.sha_url] = ("0" * 64).encode()
        self.write("ReaperPy.exe", b"old")
        with self.assertRaises(S.UpdateError):
            S.run_update(rel, self.app, opener=Opener(routes))
        self.assertEqual(self.read("ReaperPy.exe"), b"old")
        with self.assertRaises(S.UpdateError):                          # ohne .sha256 nie automatisch
            S.run_update(S.parse_release(gh(sha=False)), self.app, opener=Opener(routes))

    def test_can_self_update_only_when_frozen(self):
        self.assertFalse(S.can_self_update(self.app, frozen=False))
        self.assertTrue(S.can_self_update(self.app, frozen=True))


if __name__ == "__main__":
    unittest.main()


class GuiFlow(unittest.TestCase):
    """Hauptfenster-Handler (ohne echtes Tk): Nachfrage, Start des Updates, Abschlussmeldung."""

    def make_app(self, frozen=True, answer=True):
        import types

        import ghost_tk
        ghost_tk.install()
        import gui
        from i18n import Translator
        self.gui = gui
        app = object.__new__(gui.App)
        app.tr = Translator("en")
        app.logs, app.asked, app.q = [], [], types.SimpleNamespace(put=lambda m: app.logs.append(m))
        app.log_msg = lambda m, tag=None: app.logs.append((tag, m))
        self.addCleanup(setattr, gui.paths, "is_frozen", gui.paths.is_frozen)
        gui.paths.is_frozen = lambda: frozen
        self.addCleanup(setattr, gui.messagebox, "askyesno", gui.messagebox.askyesno)
        gui.messagebox.askyesno = lambda title, msg, **k: app.asked.append(msg) or answer
        return app

    def test_newer_with_release_asks_and_starts_download_only_on_yes(self):
        rel = S.parse_release(gh())
        d = tempfile.mkdtemp(); self.addCleanup(__import__("shutil").rmtree, d, True)
        for answer, expect in ((False, 0), (True, 1)):
            app = self.make_app(answer=answer)
            app._app_target_dir = lambda d=d: d
            started = []
            app._start_update = lambda r, t: started.append((r.version, t))
            app._on_update(S.GhResult("newer", "5.9.0", "5.9.1", rel.html_url, release=rel))
            self.assertEqual(len(app.asked), 1)
            self.assertIn("5.9.1", app.asked[0])
            self.assertEqual(len(started), expect)

    def test_source_install_only_offers_release_page(self):
        import webbrowser
        rel = S.parse_release(gh())
        app = self.make_app(frozen=False)
        opened = []
        self.addCleanup(setattr, webbrowser, "open", webbrowser.open)
        webbrowser.open = lambda u: opened.append(u)
        app._app_target_dir = lambda: "/nonexistent"
        app._start_update = lambda *a: self.fail("darf nicht installieren")
        app._on_update(S.GhResult("newer", "5.9.0", "5.9.1", rel.html_url, release=rel))
        self.assertEqual(opened, [rel.html_url])

    def test_no_sha_means_no_auto_install(self):
        rel = S.parse_release(gh(sha=False))
        d = tempfile.mkdtemp(); self.addCleanup(__import__("shutil").rmtree, d, True)
        app = self.make_app()
        app._app_target_dir = lambda: d
        app._start_update = lambda *a: self.fail("ohne Pruefsumme nie automatisch")
        app._on_update(S.GhResult("newer", "5.9.0", "5.9.1", rel.html_url, release=rel))
        self.assertIn("checksum", app.asked[0])

    def test_done_messages_tell_to_restart(self):
        app = self.make_app()
        shown = []
        mb = self.gui.messagebox
        self.addCleanup(setattr, mb, "showinfo", mb.showinfo)
        self.addCleanup(setattr, mb, "showerror", mb.showerror)
        mb.showinfo = lambda t, m, **k: shown.append(("info", m))
        mb.showerror = lambda t, m, **k: shown.append(("error", m))
        app._on_update_done((True, "5.9.1", 12))
        app._on_update_done((False, "5.9.1", "UpdateError: x"))
        self.assertIn("start it again", shown[0][1])
        self.assertEqual(shown[1][0], "error")
        self.assertIn("unchanged", shown[1][1])

    def test_start_update_reports_success_and_failure_through_queue(self):
        import threading
        rel = S.parse_release(gh())
        app = self.make_app()
        self.addCleanup(setattr, S, "run_update", S.run_update)
        for outcome in (3, S.UpdateError("Pruefsumme stimmt nicht")):
            app.logs.clear()

            def fake(r, target, progress=None, outcome=outcome):
                progress("download", 5, 10); progress("download", 10, 10); progress("verify", 1, 1); progress("install", 1, 2)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            S.run_update = fake
            app._start_update(rel, "/x")
            for t in threading.enumerate():
                if t.name == "reaperpy-update":
                    t.join(5)
            done = [m for m in app.logs if m[0] == "update_done"][-1][1]
            self.assertEqual(done[0], not isinstance(outcome, Exception))
            self.assertTrue(any("Verifying" in m[1][0] for m in app.logs if m[0] == "log"))
