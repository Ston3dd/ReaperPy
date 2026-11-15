"""Tests: alle Spiele per FTP listen/holen, Bibliothek mit Konsolen-Cache, Versionspruefung."""
import ftplib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gamemeta as G
import library as L
import versioncheck as V
from tests.test_gamemeta import PNG, param


class FTP2:
    files, dirs = {}, {}

    def connect(self, host, port, timeout=None): pass
    def login(self, *a): pass
    def set_pasv(self, v): pass
    def quit(self): pass
    def close(self): pass
    def abort(self): pass

    def nlst(self, root):
        if root not in FTP2.dirs:
            raise ftplib.error_perm("550")
        return FTP2.dirs[root]

    def retrbinary(self, cmd, cb):
        p = cmd[5:]
        if p not in FTP2.files:
            raise ftplib.error_perm("550")
        cb(FTP2.files[p])


class T(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        G._DOWN.clear()
        FTP2.dirs = {"/user/app": ["/user/app/PPSA06929", "/user/app/PPSA13197", "/user/app/random"],
                     "/mnt/ext0/user/app": ["PPSA06929", "CUSA00001"]}
        FTP2.files = {}
        for tid, nm in (("PPSA06929", "Trails through Daybreak"), ("PPSA13197", "Anderes Spiel")):
            d = f"/user/app/{tid}/sce_sys"
            FTP2.files[f"{d}/param.json"] = param(**{"en-US": nm})
            FTP2.files[f"{d}/pic0.png"] = PNG
            FTP2.files[f"{d}/icon0.png"] = PNG + b"i"

    def test_list_and_fetch_all(self):
        ids, err = G.list_titles("h", {}, FTP2)
        self.assertEqual((ids, err), (["CUSA00001", "PPSA06929", "PPSA13197"], ""))
        seen = []
        metas, _ = G.fetch_all("h", {}, progress=lambda i, n, m: seen.append((i, n)), ftp_factory=FTP2,
                               directory=self.dir)
        self.assertEqual(seen[-1], (3, 3))
        by = {m.title_id: m for m in metas}
        self.assertEqual(by["PPSA13197"].name, "Anderes Spiel")
        self.assertTrue(by["PPSA06929"].icon.endswith("PPSA06929_icon0.png"))
        self.assertEqual(by["CUSA00001"].name, "")                 # nichts gefunden, aber kein Absturz
        self.assertEqual(len(G.cached(self.dir)), 2)               # nur was wirklich im Cache liegt

    def test_no_titles_message(self):
        FTP2.dirs = {}
        self.assertIn("keine Spiele-Ordner", G.list_titles("h", {}, FTP2)[1])

    def test_library_uses_console_cache(self):
        G.fetch_all("h", {}, ftp_factory=FTP2, directory=self.dir)
        lib_dir = os.path.join(self.dir, "lib")
        os.makedirs(os.path.join(lib_dir, "PPSA06929 - daybreak patches"))
        Path(lib_dir, "PPSA06929 - daybreak patches", "Gold.reapproj").write_text("", encoding="utf-8")
        lib = L.Library(lib_dir, covers=G.cached(self.dir))
        lib.scan()
        by = {e.id: e for e in lib.entries}
        self.assertEqual(by["PPSA06929"].title, "Trails through Daybreak")      # exakter Name statt Ordnername
        self.assertEqual(len(by["PPSA06929"].patches), 1)
        self.assertTrue(by["PPSA06929"].icon.endswith("icon0.png"))
        self.assertEqual(by["PPSA13197"].title, "Anderes Spiel")                # Spiel ohne Patches ist trotzdem da
        self.assertEqual(by["PPSA13197"].patches, [])

    def test_own_icon_beats_console_icon(self):
        G.fetch_all("h", {}, ftp_factory=FTP2, directory=self.dir)
        lib_dir = os.path.join(self.dir, "lib")
        os.makedirs(lib_dir)
        Path(lib_dir, "PPSA13197.png").write_bytes(PNG)
        lib = L.Library(lib_dir, covers=G.cached(self.dir))
        lib.scan()
        e = next(x for x in lib.entries if x.id == "PPSA13197")
        self.assertEqual(os.path.basename(e.icon), "PPSA13197.png")

    def test_version_check(self):
        self.assertTrue(V.same("01.002.000", "1.02"))
        self.assertFalse(V.same("01.003", "01.02"))
        self.assertEqual(V.check("01.002.000", ["PPSA1_01.02.json"])[0], "ok")
        st, found = V.check("01.03", ["PPSA1_01.02.json", "x_01.01.reapproj"])
        self.assertEqual((st, found), ("mismatch", ["01.02", "01.01"]))
        self.assertEqual(V.check("01.03", ["Unendlich Leben.reapproj"])[0], "unknown")   # nichts gefunden -> still
        self.assertEqual(V.check("", ["a_01.02.json"])[0], "unknown")


if __name__ == "__main__":
    unittest.main()


class Dumps(unittest.TestCase):
    """Spiele als Ordner-Dumps in /data/homebrew/<beliebiger Name>/sce_sys/..."""
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        G._DOWN.clear()
        FTP2.dirs = {"/data/homebrew": ["/data/homebrew/Daybreak dump", "meins", ".hidden"]}
        FTP2.files = {"/data/homebrew/Daybreak dump/sce_sys/param.json":
                      json.dumps({"titleId": "PPSA06929", "localizedParameters": {
                          "defaultLanguage": "en-US", "en-US": {"titleName": "Trails through Daybreak"}}}).encode(),
                      "/data/homebrew/Daybreak dump/sce_sys/pic0.png": PNG,
                      "/data/homebrew/Daybreak dump/sce_sys/icon0.png": PNG + b"i"}

    def test_folder_name_does_not_matter(self):
        m = G.fetch("h", "PPSA06929", {}, ftp_factory=FTP2, directory=self.dir)
        self.assertEqual((m.name, m.cover_kind), ("Trails through Daybreak", "pic0"))
        self.assertEqual(m.source, "/data/homebrew/Daybreak dump/sce_sys")

    def test_index_is_cached_and_new_folders_are_read(self):
        G.fetch("h", "PPSA06929", {}, ftp_factory=FTP2, directory=self.dir)
        idx = json.load(open(os.path.join(self.dir, "dumps.json"), encoding="utf-8"))
        self.assertEqual(idx["/data/homebrew/Daybreak dump"], "PPSA06929")
        reads = []
        orig = FTP2.retrbinary
        FTP2.retrbinary = lambda self, cmd, cb: (reads.append(cmd), orig(self, cmd, cb))[1]
        self.addCleanup(setattr, FTP2, "retrbinary", orig)
        FTP2.dirs["/data/homebrew"].append("/data/homebrew/Neu PPSA13197")          # neuer Ordner, ID nur im Namen
        ids, _ = G.list_titles("h", {}, FTP2, self.dir)
        self.assertEqual(ids, ["PPSA06929", "PPSA13197"])
        self.assertFalse(any("Daybreak dump" in c for c in reads))                  # bekannter Ordner: kein FTP-Lesen

    def test_custom_dump_root(self):
        FTP2.dirs = {"/data/games": ["/data/games/x"]}
        FTP2.files = {"/data/games/x/sce_sys/param.json": json.dumps({"titleId": "PPSA13197"}).encode()}
        ids, _ = G.list_titles("h", {"dump_roots": ["/data/games"]}, FTP2, self.dir)
        self.assertEqual(ids, ["PPSA13197"])
