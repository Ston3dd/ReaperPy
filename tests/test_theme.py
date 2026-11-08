"""Tests: eine zentrale Farbpalette (theme.py) - gleiche Werte ueberall, gut lesbar, keine verstreuten Farbcodes."""
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
import theme as T

try:                                   # ohne Tk (z. B. reiner Testlauf auf einem Server) wird dieser eine Test uebersprungen
    import tools_common as TC
except ImportError:
    TC = None

HEX = re.compile(r"^#[0-9a-f]{6}$")
# Dateien, die bewusst eigene Farben haben: das Matrix-Effekt-Fenster und das eingebettete Icon
OWN_COLORS = {"theme.py", "hackfx.py", "icon_data.py"}


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class Palette(unittest.TestCase):
    def test_all_values_are_hex_colors(self):
        for name in dir(T):
            v = getattr(T, name)
            if name.isupper() and isinstance(v, str):
                self.assertRegex(v, HEX, name)
        for c in T.COVER_COLORS:
            self.assertRegex(c, HEX)

    def test_text_is_readable_on_every_surface(self):
        for fg, need in (("TEXT", 7.0), ("TEXT_DIM", 4.5), ("ACCENT", 4.5), ("OK", 4.5), ("WARN", 4.5), ("ERROR", 4.5)):
            for bg in ("BG", "BG_BAR", "BG_CARD", "BG_CARD_HVR", "BG_CARD_ON"):
                self.assertGreaterEqual(contrast(getattr(T, fg), getattr(T, bg)), need, (fg, bg))

    def test_selection_and_accent_buttons_are_readable(self):
        self.assertGreaterEqual(contrast(T.TEXT, T.SELECT), 4.5)
        self.assertGreaterEqual(contrast(T.ACCENT, T.SELECT), 4.5)
        self.assertGreaterEqual(contrast(T.INK_ON_ACCENT, T.ACCENT), 7.0)
        self.assertGreaterEqual(contrast(T.INK_ON_ACCENT, T.ACCENT_HI), 7.0)

    def test_surfaces_get_lighter_step_by_step_and_borders_are_visible(self):
        steps = [_lum(getattr(T, n)) for n in ("BG", "BG_BAR", "BG_CARD", "BG_CARD_HVR")]
        self.assertEqual(steps, sorted(steps))
        self.assertGreaterEqual(contrast(T.BORDER, T.BG), 1.5)
        self.assertGreaterEqual(contrast(T.BORDER_HVR, T.BG_CARD), 2.5)

    def test_how_to_callout_colors_are_readable(self):
        self.assertGreaterEqual(contrast(T.TEXT, T.ACCENT_BG), 7.0)             # Tipp-Kasten
        self.assertGreaterEqual(contrast(T.WARN, T.CALLOUT_WARN_BG), 7.0)       # Achtung-Kasten
        self.assertGreaterEqual(contrast(T.TEXT, T.CALLOUT_WARN_BG), 7.0)

    def test_status_colors_are_distinct(self):
        self.assertEqual(len({T.OK, T.WARN, T.ERROR, T.ACCENT}), 4)

    @unittest.skipIf(TC is None, "tkinter fehlt")
    def test_tools_common_uses_the_central_palette(self):
        for name in ("BG", "BG_BAR", "BG_CARD", "BG_CARD_HVR", "BORDER", "BORDER_HVR", "ACCENT", "ACCENT_DIM", "TEXT",
                     "TEXT_DIM", "WARN", "ERROR", "OK", "SELECT"):
            self.assertEqual(getattr(TC, name), getattr(T, name), name)

    def test_no_stray_color_codes_in_the_program_files(self):
        stray = []
        for fn in sorted(os.listdir(ROOT)):
            if not fn.endswith(".py") or fn in OWN_COLORS:
                continue
            with open(os.path.join(ROOT, fn), encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if re.search(r"""["']#[0-9a-fA-F]{6}["']""", line):
                        stray.append(f"{fn}:{n}")
        self.assertEqual(stray, [], "Farben gehoeren nach theme.py")


if __name__ == "__main__":
    unittest.main()
