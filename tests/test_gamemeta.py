"""Tests fuer gamemeta: Cover (pic0.png) + exakter Name (param.json) per FTP, mit Cache; autocodes-Anbindung."""
import ftplib
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import autocodes as A
import gamemeta as G

PNG = G.PNG_MAGIC + b"fakepng" * 50


def param(default="en-US", **names):
    return json.dumps({"localizedParameters": {"defaultLanguage": default,
                                               **{k: {"titleName": v} for k, v in names.items()}}}).encode()


class FakeFTP:
    files = {}
    refuse = set()
    log = []

    def connect(self, host, port, timeout=None):
        if port in FakeFTP.refuse:
            raise ConnectionRefusedError("nein")
        self.port = port

    def login(self, *a):
        pass

    def set_pasv(self, v):
        pass

    def retrbinary(self, cmd, cb):
        path = cmd[5:]
        FakeFTP.log.append(path)
        if path not in FakeFTP.files:
            raise ftplib.error_perm("550 not found")
        data = FakeFTP.files[path]
        for i in range(0, len(data), 64):
            cb(data[i:i + 64])

    def abort(self):
        pass

    def quit(self):
        pass

    def close(self):
        pass


class T(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        FakeFTP.files, FakeFTP.refuse, FakeFTP.log = {}, set(), []
        G._DOWN.clear()

    def fetch(self, tid="PPSA06929", **cfg):
        return G.fetch("10.0.0.2", tid, cfg, ftp_factory=FakeFTP, directory=self.dir)

    def test_param_json_default_language_wins(self):
        raw = param("de-DE", **{"en-US": "Sword", "de-DE": "Schwert"})
        self.assertEqual(G.parse_param_json(raw), "Schwert")
        self.assertEqual(G.parse_param_json(param("fr-FR", **{"en-US": "Sword"})), "Sword")
        self.assertEqual(G.parse_param_json(b'{"titleName": " Foo  Bar "}'), "Foo Bar")
        self.assertEqual(G.parse_param_json(b"kaputt"), "")

    def test_bad_names_are_not_names(self):
        for bad in ("eboot.bin", "PPSA06929", "", None, "game.elf"):
            self.assertEqual(G.clean_name(bad), "")
        self.assertEqual(G.pick_name("PPSA1", "", "eboot.bin", "Lib Titel"), ("Lib Titel", "bibliothek"))
        self.assertEqual(G.pick_name("PPSA06929", "Exakt", "Konsole", "Lib"), ("Exakt", "param.json"))
        self.assertEqual(G.pick_name("PPSA06929"), ("PPSA06929", "id"))

    def test_fetch_gets_cover_and_name_and_caches(self):
        d = "/mnt/sandbox/pfsmnt/PPSA06929-app0/sce_sys"
        FakeFTP.files = {f"{d}/pic0.png": PNG, f"{d}/param.json": param(**{"en-US": "Trails through Daybreak"})}
        m = self.fetch()
        self.assertEqual(m.name, "Trails through Daybreak")
        self.assertEqual((m.cover_kind, m.source), ("pic0", d))
        self.assertEqual(open(m.cover, "rb").read(), PNG)
        n = len(FakeFTP.log)
        m2 = self.fetch()                                    # zweiter Aufruf: nur Cache, kein FTP
        self.assertEqual((m2.name, m2.source, len(FakeFTP.log)), ("Trails through Daybreak", "cache", n))

    def test_falls_through_to_other_folder_and_icon0(self):
        FakeFTP.files = {"/user/app/PPSA06929/sce_sys/icon0.png": PNG,
                         "/system_data/priv/appmeta/PPSA06929/param.json": param(**{"en-US": "X"})}
        m = self.fetch()
        self.assertEqual((m.name, m.cover_kind), ("X", "icon0"))
        self.assertTrue(m.cover.endswith("PPSA06929_icon0.png"))

    def test_non_png_is_rejected_and_custom_dir_first(self):
        FakeFTP.files = {"/mnt/sandbox/pfsmnt/PPSA06929-app0/sce_sys/pic0.png": b"<html>",
                         "/eigener/PPSA06929/pic0.png": PNG}
        m = self.fetch(meta_dirs=["/eigener/{id}"])
        self.assertEqual((m.cover_kind, m.source), ("pic0", "/eigener/PPSA06929"))

    def test_second_port_and_unreachable_is_remembered(self):
        FakeFTP.refuse = {2121}
        FakeFTP.files = {"/user/app/PPSA06929/sce_sys/pic0.png": PNG}
        self.assertEqual(self.fetch().cover_kind, "pic0")
        FakeFTP.refuse = {2121, 1337}
        m = self.fetch("PPSA11111")
        self.assertIn("nicht erreichbar", m.error)
        FakeFTP.refuse = set()
        self.assertIn("vorhin", self.fetch("PPSA22222").error)   # kein erneuter Haenger innerhalb der Sperrzeit

    def test_never_raises_and_respects_off_switch(self):
        self.assertIn("Titel-ID", G.fetch("h", "kaputt", {}, ftp_factory=FakeFTP, directory=self.dir).error)
        self.assertIn("abgeschaltet", self.fetch(game_meta=False).error)
        self.assertTrue(self.fetch().error)                    # nichts gefunden -> Meldung, kein Fehler

    def test_autocodes_uses_exact_name(self):
        cfg = {"library_dir": os.path.join(self.dir, "lib"), "projects_root": "", "projects": {}}
        meta = G.Meta(title_id="PPSA06929", name="Trails through Daybreak", cover="x.png", cover_kind="pic0")
        d = A.detect(None, cfg, {}, foreground_fn=lambda c: (7, "PPSA06929", "eboot.bin", "01.00"),
                     meta_fn=lambda t: meta)
        self.assertEqual((d.display_name, d.name_source), ("Trails through Daybreak", "param.json"))
        d = A.detect(None, cfg, {}, foreground_fn=lambda c: (7, "PPSA06929", "Kiseki", "01.00"),
                     meta_fn=lambda t: None)                  # FTP aus -> Name der Konsole
        self.assertEqual((d.display_name, d.name_source), ("Kiseki", "konsole"))
        d = A.detect(None, cfg, {}, foreground_fn=lambda c: (7, "PPSA06929", "eboot.bin", ""),
                     meta_fn=lambda t: 1 / 0)                 # kaputte Meta-Funktion bricht nichts
        self.assertEqual(d.display_name, "PPSA06929")


if __name__ == "__main__":
    unittest.main()
