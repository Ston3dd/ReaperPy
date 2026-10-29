"""Regression: "Cave-Adresse 0xffd0 liegt unter der Basis 0x400000".  Der Cave-Allokator suchte in ALLEN ausfuehrbaren
Regionen des Prozesses (Bibliotheken, Tiny-Regionen unter der Basis) und nahm die groesste Padding-Luecke - ein JSON-
Offset kann dort aber nicht hinzeigen.  Jetzt: nur das Spiel-Image."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cave_trainer
import export_goldhen as E
from pathlib import Path

BASE = 0x400000
# (start, end, prot, fuellbyte am Ende, Laenge des Fuellers)
REGIONS = [
    (0x0000E000, 0x00010000, 5, 0xCC, 0x1800),        # winzige Exec-Region UNTER der Basis (hier lag 0xffd0), groesster Fueller
    (0x00400000, 0x00600000, 5, 0x00, 0x300),         # Spiel-Image: .text
    (0x00600000, 0x00700000, 1, 0x00, 0x0),           # Spiel-Image: .rodata
    (0x00700000, 0x00800000, 3, 0x00, 0x0),           # Spiel-Image: .data
    (0x7F0000000, 0x7F0100000, 5, 0xCC, 0x4000),      # Systembibliothek weit weg, ebenfalls grosser Fueller
]


class Backend:
    def __init__(self, regions=REGIONS):
        self.regions = regions

    def get_maps(self, force=False):
        return [(s, e, p) for s, e, p, _f, _n in self.regions]

    def read(self, addr, n):
        for s, e, _p, fill, run in self.regions:
            if s <= addr and addr + n <= e:
                data = bytearray(b"\x90" * (e - s))              # Code
                data[len(data) - run:] = bytes([fill]) * run     # Padding am Ende
                return bytes(data[addr - s:addr - s + n])
        raise OSError(f"nicht lesbar {addr:#x}")


class CaveScopeTests(unittest.TestCase):
    def test_old_behaviour_picked_the_region_below_the_base(self):
        a = E.CaveAllocator(Backend(), log=lambda _m: None)                 # ohne Basis = altes Verhalten
        cave, _n = a.alloc(0x100, 0xB2C491)
        self.assertLess(cave, BASE)                                          # genau der gemeldete Fehler (0xffd0)

    def test_cave_is_taken_from_the_game_image_only(self):
        a = E.CaveAllocator(Backend(), log=lambda _m: None, image_base=BASE)
        cave, n = a.alloc(0x100, 0xB2C491)
        self.assertTrue(BASE <= cave and cave + n <= 0x600000, hex(cave))   # im .text des Spiels
        self.assertEqual(cave + n, 0x600000 & ~0xF)                          # am Region-Ende (Segment-Padding)
        cave2, _n = a.alloc(0x100, 0xB2C491)
        self.assertEqual(cave2 + 0x100, cave)                                # naechste Cave davor, nie woanders

    def test_many_caves_never_leave_the_image(self):
        a = E.CaveAllocator(Backend(), log=lambda _m: None, image_base=BASE)
        for _ in range(3):
            cave, n = a.alloc(0x100, 0xB2C491)
            self.assertTrue(0x600000 - 0x300 <= cave and cave + n <= 0x600000)
        with self.assertRaises(E.ExportError):                               # Padding ist alle -> Fehler statt Fremdregion
            for _ in range(5):
                a.alloc(0x100, 0xB2C491)

    def test_image_span(self):
        span = cave_trainer.image_span(Backend().get_maps(), BASE)
        self.assertEqual([(s, e) for s, e, _p in span], [(0x400000, 0x600000), (0x600000, 0x700000), (0x700000, 0x800000)])
        self.assertEqual(cave_trainer.image_span(Backend().get_maps(), 0x123456), [])

    def test_wrong_base_falls_back_to_regions_above_it_and_says_so(self):
        msgs = []
        a = E.CaveAllocator(Backend(), log=msgs.append, image_base=0x500)         # Basis liegt in keiner Region
        cave, _n = a.alloc(0x100, 0xB2C491)
        self.assertGreaterEqual(cave, 0x500)                                 # nie unter der Basis
        self.assertTrue(any("keiner Speicherregion" in m for m in msgs))

    def test_build_mods_uses_the_game_image(self):
        """Durchgang durch build_mods: Offsets sind nie negativ, die Cave liegt im Image."""
        import reapatch
        import tempfile, json
        d = tempfile.mkdtemp()
        patch = os.path.join(d, "Inf Hp.reapproj")
        Path(patch).write_text(json.dumps({"name": "Inf Hp", "ImageBase": hex(BASE), "Variables": [
            {"label": "OriginSource", "offset": "0xb2c491", "defaultValue": "90 90 90 90 90",
             "newValue": "90 90 90 90 90"}]}), encoding="utf-8")
        rp = reapatch.ReapPatch.load(patch)
        be = Backend()
        be.pid = 1
        mods, report = E.build_mods(be, [rp], BASE, log=lambda _m: None)
        self.assertNotIn("liegt unter der Basis", " ".join(r["msg"] for r in report))


HOOK_RVA = 0x1000                                   # Hook-Stelle im Image: vmovss [rbx+0x11C], xmm0
ORIG = bytes.fromhex("C5FA11831C010000")
HP_ASM = """cmp byte ptr [rbx+0x49A], 1
jne skip
mov dword ptr [rbx+0x11C], 0x457A0000
jmp OriginReturn
skip:
vmovss dword ptr [rbx+0x11C], xmm0
jmp OriginReturn"""


class CaveBackend(Backend):
    """Image mit der Hook-Stelle; assemble() ueber Keystone wie im echten Tool."""
    pid = 1

    def __init__(self, regions):
        super().__init__(regions)

    def read(self, addr, n):
        data = bytearray(super().read(addr, n))
        for i in range(n):
            if BASE + HOOK_RVA <= addr + i < BASE + HOOK_RVA + len(ORIG):
                data[i] = ORIG[addr + i - BASE - HOOK_RVA]
        return bytes(data)

    def assemble(self, text, base=0):
        from asm_tools import assemble
        return assemble(text, base)


def hp_patch():
    import reapatch
    rp = reapatch.ReapPatch("Inf Hp.reapproj")
    rp.name = "Inf Hp"
    rp.origin_source = (HOOK_RVA, "vmovss dword ptr [rbx+0x11C], xmm0", "jmp OriginTarget\nnop\nnop\nnop")
    rp.origin_return_offset = 8
    rp.labels = [("OriginTarget", HP_ASM)]
    return rp


try:
    import keystone  # noqa: F401
    import capstone  # noqa: F401
    HAVE_ASM = True
except ImportError:  # pragma: no cover
    HAVE_ASM = False


@unittest.skipUnless(HAVE_ASM, "keystone/capstone fehlen")
class CaveExportTests(unittest.TestCase):
    TEXT = (0x00400000, 0x00600000, 5, 0x00, 0x300)       # r-x, Padding am Ende
    RWX = (0x00600000, 0x00700000, 7, 0x00, 0x4000)       # rwx mit GROESSEREM Padding (unsicher: kann Spiel-Daten sein)
    DATA = (0x00700000, 0x00800000, 3, 0x00, 0x0)

    def export(self, regions):
        msgs = []
        mods, report = E.build_mods(CaveBackend(regions), [hp_patch()], BASE, log=msgs.append)
        return mods, report, msgs

    def test_cave_goes_to_rx_region_even_if_a_writable_one_has_more_room(self):
        mods, report, _m = self.export([self.TEXT, self.RWX, self.DATA])
        self.assertEqual(report[0]["status"], "ok", report)
        cave, hook = mods[0]["memory"]
        addr = BASE + int(cave["offset"], 16)
        self.assertTrue(0x600000 - 0x300 <= addr < 0x600000, hex(addr))                 # im r-x-Padding
        self.assertIn("r-x", report[0]["msg"])
        self.assertIn("Region 0x400000-0x600000", report[0]["msg"])

    def test_untick_keeps_the_cave_and_only_restores_the_hook(self):
        """Reihenfolge der Eintraege = Reihenfolge des Schreibens: 'off' darf die Cave nicht vor dem Hook nullen."""
        mods, _r, _m = self.export([self.TEXT, self.RWX, self.DATA])
        cave, hook = mods[0]["memory"]
        self.assertEqual(cave["on"], cave["off"])
        self.assertNotEqual(set(bytes.fromhex(cave["off"])), {0})
        self.assertEqual(bytes.fromhex(hook["off"]), ORIG)                              # Hook: Original zurueck
        self.assertTrue(hook["on"].startswith("E9"))                                    # jmp rel32 + nops
        self.assertEqual(len(bytes.fromhex(hook["on"])), 8)

    def test_falls_back_to_writable_region_with_warning_only_when_needed(self):
        full_text = (0x00400000, 0x00600000, 5, 0x00, 0x0)                              # r-x ohne freies Padding
        mods, report, msgs = self.export([full_text, self.RWX, self.DATA])
        self.assertEqual(report[0]["status"], "ok", report)
        addr = BASE + int(mods[0]["memory"][0]["offset"], 16)
        self.assertTrue(0x700000 - 0x4000 <= addr < 0x700000, hex(addr))
        self.assertTrue(any("WARNUNG" in m and "beschreibbare" in m for m in msgs))
        self.assertIn("rwx", report[0]["msg"])

    def test_no_space_anywhere_is_an_error_not_a_foreign_region(self):
        full = (0x00400000, 0x00600000, 5, 0x00, 0x0)
        _mods, report, _m = self.export([full, self.DATA, REGIONS[0], REGIONS[4]])      # unter der Basis / Bibliothek ignoriert
        self.assertEqual(report[0]["status"], "error")
        self.assertIn("Kein freier Platz", report[0]["msg"])


if __name__ == "__main__":
    unittest.main()
