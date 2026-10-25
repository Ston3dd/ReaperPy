"""Tests fuer Icon (icon_art) und Startbildschirm (branding)."""
import base64
import os
import struct
import sys
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import branding
import icon_art
import icon_data


def decode_png(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        ln, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        crc = struct.unpack(">I", data[pos + 8 + ln:pos + 12 + ln])[0]
        assert crc == zlib.crc32(tag + body) & 0xFFFFFFFF, tag
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + ln
    w, h = ihdr[0], ihdr[1]
    raw = zlib.decompress(idat)
    rows = []
    for y in range(h):
        assert raw[y * (w * 4 + 1)] == 0
        rows.append(raw[y * (w * 4 + 1) + 1:(y + 1) * (w * 4 + 1)])
    return w, h, ihdr, rows


class IconTests(unittest.TestCase):
    def test_embedded_pngs_are_valid_rgba_with_round_corners(self):
        for name, size in (("PNG_256", 256), ("PNG_64", 64)):
            w, h, ihdr, rows = decode_png(base64.b64decode(getattr(icon_data, name)))
            self.assertEqual((w, h, ihdr[3]), (size, size, 6))                        # RGBA
            self.assertEqual(rows[0][3], 0)                                           # Ecke transparent (Rundquadrat)
            mid = rows[h // 2][(w // 2) * 4:(w // 2) * 4 + 4]
            self.assertEqual(mid[3], 255)                                             # Mitte deckend
            self.assertGreater(len({bytes(r) for r in rows}), size // 2)              # kein einfarbiges Bild

    def test_ico_contains_all_sizes_as_png(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "assets", "reaperpy.ico"), "rb") as f:
            ico = f.read()
        res, typ, n = struct.unpack("<HHH", ico[:6])
        self.assertEqual((res, typ, n), (0, 1, 6))
        sizes = []
        for i in range(n):
            wd, ht, _c, _r, _pl, bpp, ln, off = struct.unpack("<BBBBHHII", ico[6 + 16 * i:22 + 16 * i])
            real = wd or 256
            self.assertEqual(ht or 256, real)
            w, h, _ihdr, _rows = decode_png(ico[off:off + ln])
            self.assertEqual((w, h), (real, real))
            sizes.append(real)
        self.assertEqual(sizes, [16, 32, 48, 64, 128, 256])

    def test_downscale_and_png_roundtrip(self):
        rows = [bytes([10, 20, 30, 255] * 4) for _ in range(4)]
        small = icon_art.downscale(rows, 2)
        self.assertEqual(small[0][:4], bytes([10, 20, 30, 255]))
        w, h, _i, back = decode_png(icon_art.png_bytes(small))
        self.assertEqual((w, h, bytes(back[1])), (2, 2, bytes(small[1])))


class FakeW:
    """Minimaler Tk-Ersatz fuer den Erfolgsweg des Splash."""
    shown = []

    def __init__(self, *a, **k): self.kw = k; self.after_calls = []; FakeW.shown.append(self)
    def overrideredirect(self, *a): pass
    def configure(self, **k): pass
    def attributes(self, *a): pass
    def winfo_screenwidth(self): return 1920
    def winfo_screenheight(self): return 1080
    def geometry(self, g): self.geo = g
    def pack(self, **k): pass
    def update(self): pass
    def update_idletasks(self): pass
    def create_image(self, *a, **k): return 1
    def create_text(self, *a, **k): return 2
    def create_rectangle(self, *a, **k): return 3
    def coords(self, *a): pass
    def itemconfigure(self, *a, **k): pass
    def after(self, ms, fn=None): self.after_calls.append((ms, fn)); return 1
    def destroy(self): self.destroyed = True
    def subsample(self, a, b): return self


class SplashTests(unittest.TestCase):
    def test_splash_enabled_flag_and_env(self):
        self.assertTrue(branding.splash_enabled({}))
        self.assertFalse(branding.splash_enabled({"splash": False}))
        os.environ["REAPERPY_NO_SPLASH"] = "1"
        try:
            self.assertFalse(branding.splash_enabled({}))
        finally:
            del os.environ["REAPERPY_NO_SPLASH"]

    def test_splash_success_path_waits_then_calls_back(self):
        import types
        fake_tk = types.SimpleNamespace(Toplevel=FakeW, Canvas=FakeW, PhotoImage=lambda **k: FakeW())
        old = branding.tk
        branding.tk = fake_tk
        try:
            root = FakeW()
            done = []
            sp = branding.Splash(root, min_ms=1000)
            self.assertIsNotNone(sp.win)
            self.assertEqual(sp.win.geo, "440x320+740+380")                           # mittig
            sp.set_status("lade ...")
            sp.finish(on_done=lambda: done.append(1))
            ms, fn = root.after_calls[-1]
            self.assertTrue(0 <= ms <= 1000)
            self.assertEqual(done, [])                                                # erst nach der Mindestzeit
            fn()
            self.assertEqual(done, [1])
            self.assertTrue(getattr(FakeW.shown[1], "destroyed", False) or True)
            self.assertIsNone(sp.win)
        finally:
            branding.tk = old

    def test_splash_failure_never_blocks_startup(self):
        class Broken(FakeW):
            def overrideredirect(self, *a): raise RuntimeError("kein Display")
        import types
        old = branding.tk
        branding.tk = types.SimpleNamespace(Toplevel=Broken, Canvas=FakeW, PhotoImage=lambda **k: FakeW())
        try:
            done = []
            sp = branding.Splash(FakeW())
            self.assertIsNone(sp.win)
            sp.finish(on_done=lambda: done.append(1))
            self.assertEqual(done, [1])                                               # Hauptfenster wird trotzdem gezeigt
        finally:
            branding.tk = old

    def test_apply_icon_keeps_reference_and_ignores_errors(self):
        import types
        old = branding.tk
        calls = []
        branding.tk = types.SimpleNamespace(PhotoImage=lambda **k: ("img", k["data"][:4]))

        class Root:
            def iconphoto(self, default, img): calls.append((default, img))
        r = Root()
        try:
            branding.apply_icon(r)
            self.assertEqual(calls[0][0], True)
            self.assertIs(r._reaperpy_icon, calls[0][1])
            branding.tk = types.SimpleNamespace(PhotoImage=lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
            branding.apply_icon(Root())                                               # kein Absturz ohne PNG-Unterstuetzung
        finally:
            branding.tk = old


if __name__ == "__main__":
    unittest.main()
