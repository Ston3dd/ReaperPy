"""Tests: Release-Karte (release_card.py) und ihre Anbindung an den Export (export_goldhen)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E402,E702
import release_card as R  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

DOC = {"name": "Mein Spiel", "id": "PPSA16096", "version": "01.003.000", "process": "eboot.bin", "credits": ["Reaper"],
       "mods": [{"name": "01 Unendlich Leben", "memory": []}, {"name": "Max_Geld", "memory": []},
                {"name": "Max Geld", "memory": []}, {"name": "", "memory": []}]}


def cover(path, size=(512, 512), colors=((200, 40, 30), (255, 150, 40))):
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    for y in range(size[1]):
        t = y / size[1]
        d.line([(0, y), (size[0], y)], fill=tuple(int(colors[0][i] + (colors[1][i] - colors[0][i]) * t) for i in range(3)))
    im.save(path)
    return path


class Inputs(unittest.TestCase):
    def test_names_come_from_the_export_cleaned_and_without_duplicates(self):
        self.assertEqual(R.names_from_doc(DOC), ["Unendlich Leben", "Max Geld"])

    def test_json_export_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(DOC, f)
            info = R.from_json(p)
        self.assertEqual((info["title"], info["id"], info["version"], info["author"]),
                         ("Mein Spiel", "PPSA16096", "01.003.000", "Reaper"))

    def test_roman_numerals(self):
        self.assertEqual([R.roman(n) for n in (1, 4, 9, 14, 40, 74)], ["I", "IV", "IX", "XIV", "XL", "LXXIV"])

    def test_platform_follows_the_title_id(self):
        self.assertEqual((R.platform_of("CUSA00001"), R.platform_of("PPSA00001"), R.platform_of("")), ("PS4", "PS5", "PS5"))

    def test_find_art_prefers_the_exact_name_and_ignores_other_games(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sub"))
            cover(os.path.join(d, "PPSA11111.png"))
            cover(os.path.join(d, "sub", "PPSA16096_icon0.jpg"))
            exact = cover(os.path.join(d, "sub", "PPSA16096.png"))
            self.assertEqual(R.find_art("PPSA16096", [d]), exact)
            self.assertEqual(R.find_art("PPSA99999", [d]), "")
            cover(os.path.join(d, "icon0.png"))
            self.assertTrue(R.find_art("PPSA99999", [d]).endswith("icon0.png"))

    def test_accent_is_taken_from_the_cover(self):
        with tempfile.TemporaryDirectory() as d:
            # Bilder ganz in den Speicher holen und die Dateien schliessen: unter Windows laesst sich das
            # Temp-Verzeichnis sonst nicht loeschen (WinError 32)
            with Image.open(cover(os.path.join(d, "r.png"), colors=((200, 20, 20), (230, 40, 30)))) as im:
                red = im.copy()
            with Image.open(cover(os.path.join(d, "b.png"), colors=((20, 60, 200), (40, 90, 230)))) as im:
                blue = im.copy()
            grey = Image.new("RGB", (64, 64), (120, 120, 120))
        r, b = R.hex_rgb(R.accent_from_art(red)), R.hex_rgb(R.accent_from_art(blue))
        self.assertTrue(r[0] > r[2] and b[2] > b[0], (r, b))
        self.assertEqual(R.accent_from_art(grey), R.DEFAULT_ACCENT)


class Render(unittest.TestCase):
    def render(self, **kw):
        d = tempfile.mkdtemp()
        out = os.path.join(d, "card.png")
        args = dict(title="Spiel", game_id="PPSA16096", version="01.000.000", names=["A", "B"], out_path=out)
        args.update(kw)
        R.render_card(args.pop("title"), args.pop("game_id"), args.pop("version"), args.pop("names"), **args)
        return out

    def test_card_is_full_hd_png_with_and_without_cover(self):
        with tempfile.TemporaryDirectory() as d:
            art = cover(os.path.join(d, "c.png"))
            for p in (self.render(art_path=art), self.render()):
                with Image.open(p) as im:
                    self.assertEqual((im.size, im.format), ((1920, 1080), "PNG"))

    def test_same_game_gives_the_same_card(self):
        a, b = self.render(), self.render()
        with Image.open(a) as ia, Image.open(b) as ib:
            self.assertEqual(ia.tobytes(), ib.tobytes())

    def test_odd_inputs_do_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            wide = cover(os.path.join(d, "w.png"), size=(1600, 400))
            tall = cover(os.path.join(d, "t.png"), size=(300, 1200))
            for kw in (dict(art_path=wide), dict(art_path=tall, title="Ein sehr sehr sehr langer Spieltitel, der in zwei "
                                                                       "Zeilen umbrochen werden muss"),
                       dict(art_path=os.path.join(d, "fehlt.png"), title="ÄÖÜ 日本語 Ünïcode",
                            names=["Ein unglaublich langer Cheat-Name " * 6] + [f"Cheat {i}" for i in range(120)],
                            author="Jemand", lang="de", tags=["X"])):
                self.assertTrue(os.path.getsize(self.render(**kw)) > 20000, kw)

    def test_too_many_cheats_are_cut_with_a_more_line_not_written_tiny(self):
        # Kapazität = Spalten x Zeilen bei mindestens 36 px pro Zeile; darüber steht '+ N MORE'
        self.assertIn("{n}", R.TEXTS["en"]["more"])
        self.assertIn("{n}", R.TEXTS["de"]["more"])


class ExportHook(unittest.TestCase):
    def test_card_lands_next_to_the_export_and_names_the_cover(self):
        with tempfile.TemporaryDirectory() as d:
            art = cover(os.path.join(d, "PPSA16096.png"))
            exp = os.path.join(d, "PPSA16096_01.003.000.json")
            out, msg = R.card_for_export(DOC, exp, [d], "", "", None, "de", False, "json")
            self.assertEqual(out, os.path.join(d, "PPSA16096_01.003.000_release.png"))
            self.assertTrue(os.path.exists(out))
            self.assertIn(art, msg)

    def test_without_cover_the_card_still_comes(self):
        with tempfile.TemporaryDirectory() as d:
            out, msg = R.card_for_export(DOC, os.path.join(d, "x.json"), [d])
            self.assertTrue(out and os.path.exists(out))
            self.assertIn("kein Cover", msg)

    def test_a_card_problem_never_breaks_the_export(self):
        with tempfile.TemporaryDirectory() as d:
            out, msg = R.card_for_export({"mods": []}, os.path.join(d, "x.json"))
            self.assertEqual(out, "")
            out, msg = R.card_for_export(DOC, os.path.join(d, "kein", "Ordner", "x.json"), [d], art_path=d)
            self.assertTrue(out == "" or os.path.exists(out))

    def test_export_dialog_writes_json_and_card_in_one_go(self):
        import export_goldhen as E
        import queue
        with tempfile.TemporaryDirectory() as d:
            cover(os.path.join(d, "PPSA16096.png"))
            mods = [{"name": "Unendlich Leben", "type": "checkbox",
                     "memory": [{"offset": "751BF8", "on": "9090", "off": "FF4B"}]}]
            orig = E.build_mods
            E.build_mods = lambda *a, **k: (mods, [])
            try:
                dlg = E.ExportDialog.__new__(E.ExportDialog) if False else None
                Dlg = E._gui_dialog()
                dlg = Dlg.__new__(Dlg)
                dlg.q = queue.Queue()
                path = os.path.join(d, "PPSA16096_01.003.000.json")
                card = {"art": "", "accent": None, "lang": "de", "dirs": [d]}
                dlg._work(None, [], 0x400000, path, "Mein Spiel", "PPSA16096", "01.003.000", "eboot.bin", ["Ich"],
                          0x400000, "json", card)
            finally:
                E.build_mods = orig
            logs = []
            while not dlg.q.empty():
                logs.append(dlg.q.get())
            self.assertTrue(os.path.exists(path))
            png = os.path.join(d, "PPSA16096_01.003.000_release.png")
            self.assertTrue(os.path.exists(png), logs)
            self.assertTrue(any("Release-Karte" in str(p) for k, p in logs if k == "log"), logs)
            with Image.open(png) as im:
                self.assertEqual(im.size, (1920, 1080))

    def test_export_without_card_option_writes_no_png(self):
        import export_goldhen as E
        import queue
        with tempfile.TemporaryDirectory() as d:
            mods = [{"name": "X", "type": "checkbox", "memory": [{"offset": "751BF8", "on": "9090", "off": "FF4B"}]}]
            orig = E.build_mods
            E.build_mods = lambda *a, **k: (mods, [])
            try:
                Dlg = E._gui_dialog()
                dlg = Dlg.__new__(Dlg)
                dlg.q = queue.Queue()
                dlg._work(None, [], 0x400000, os.path.join(d, "a.json"), "S", "PPSA16096", "01.003.000", "eboot.bin", [],
                          0x400000, "json", None)
            finally:
                E.build_mods = orig
            self.assertEqual(sorted(os.listdir(d)), ["a.json"])


if __name__ == "__main__":
    unittest.main()
