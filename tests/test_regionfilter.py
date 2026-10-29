"""Bereichsfilter des Cheat-Searchers: eboot.bin aufsplitten, Libs ausblenden, Auswahl = Scan-Regionen."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import regionfilter as RF
import scanner as SC
from pathlib import Path

MB = 1048576
MAPS = [
    (0x400000, 0x400000 + 80 * MB, 5, "eboot.bin"),           # Code
    (0x6470000, 0x6470000 + 15 * MB, 1, "eboot.bin"),         # Konstanten
    (0x72DC000, 0x72DC000 + 64 * 1024, 3, "eboot.bin"),       # Daten
    (0x10000000, 0x10000000 + 600 * MB, 3, "libSceLibcInternal.sprx"),
    (0x20000000, 0x20000000 + 2 * MB, 3, "libc.prx"),
    (0x30000000, 0x30000000 + 8 * MB, 3, "Il2CppUserAssemblies.prx"),
    (0x200000000, 0x200000000 + 800 * MB, 3, "anon:0008009af2a1"),
    (0x300000000, 0x300000000 + 64 * 1024, 3, "anon:000800e49077"),
    (0x300100000, 0x300100000 + 8192, 3, ""),
    (0x400000000, 0x400000000 + 16 * 1024, 3, "/SceAuOut2SysShm0xdf"),
    (0x500000000, 0x500000000 + 4096, 0, "anon:noaccess"),    # nicht lesbar
]


class Classify(unittest.TestCase):
    def test_categories(self):
        c = RF.classify
        self.assertEqual(c("eboot.bin"), "eboot")
        self.assertEqual(c("libSceFios2.sprx"), "syslib")
        self.assertEqual(c("libc.prx"), "syslib")
        self.assertEqual(c("libkernel.sprx"), "syslib")
        self.assertEqual(c("Il2CppUserAssemblies.prx"), "gamemod")
        self.assertEqual(c("anon:000800e49077"), "heap")
        self.assertEqual(c("1000e21a90"), "heap")
        self.assertEqual(c(""), "heap")
        self.assertEqual(c("/SceAuOut2SysShm0xdf"), "shm")
        self.assertEqual(c("main thread stack"), "stack")
        self.assertEqual(c("whatever"), "other")


class Sections(unittest.TestCase):
    def setUp(self):
        self.secs = RF.build_sections(MAPS)

    def test_eboot_is_split_into_its_regions(self):
        eb = self.secs["eboot"]
        self.assertEqual([s.label.split()[0] for s in eb], ["Code-Bereich", "Nur-Lesen-Bereich", "Daten-Bereich"])
        self.assertEqual([s.rights for s in eb], ["r-x", "r--", "rw-"])

    def test_modules_one_row_each_and_small_regions_merged(self):
        self.assertEqual(sorted(s.label for s in self.secs["syslib"]), ["libSceLibcInternal.sprx", "libc.prx"])
        heap = self.secs["heap"]
        self.assertEqual(len(heap), 2)                          # 1 grosse + 1 Sammelzeile
        self.assertEqual(heap[-1].label, RF.SMALL_LABEL)
        self.assertEqual(len(heap[-1].regions), 2)

    def test_unreadable_regions_are_dropped(self):
        starts = [r.start for l in self.secs.values() for s in l for r in s.regions]
        self.assertNotIn(0x500000000, starts)

    def test_accepts_dict_maps(self):
        d = [{"name": n, "start": s, "end": e, "prot": p} for s, e, p, n in MAPS]
        self.assertEqual(RF.included_starts(d, RF.FilterState(hide=())), RF.included_starts(MAPS, RF.FilterState(hide=())))


class Filtering(unittest.TestCase):
    def test_default_hides_system_libs_only(self):
        st = RF.FilterState()
        got = RF.included_starts(MAPS, st, "rw")
        self.assertNotIn(0x10000000, got)
        self.assertNotIn(0x20000000, got)
        for a in (0x6470000 + 0, 0x72DC000, 0x30000000, 0x200000000, 0x300000000, 0x400000000):
            if a == 0x6470000:
                continue                                        # r-- ist nicht schreibbar
            self.assertIn(a, got, hex(a))

    def test_scope_matches_scanner_rules(self):
        st = RF.FilterState(hide=())
        self.assertNotIn(0x400000, RF.included_starts(MAPS, st, "rw"))        # Code nicht schreibbar
        self.assertIn(0x400000, RF.included_starts(MAPS, st, "all"))
        self.assertIn(0x300100000, RF.included_starts(MAPS, st, "rw"))        # 8 KB >= Mindestgroesse 0x1000
        tiny = MAPS + [(0x700000000, 0x700000000 + 0x800, 3, "anon:tiny")]
        self.assertNotIn(0x700000000, RF.included_starts(tiny, st, "rw"))     # 2 KB wird nie gescannt

    def test_libsce_vs_libc_presets(self):
        st = RF.FilterState(hide=("libsce",))
        got = RF.included_starts(MAPS, st, "rw")
        self.assertNotIn(0x10000000, got)
        self.assertIn(0x20000000, got)
        st = RF.FilterState(hide=("libc",))
        got = RF.included_starts(MAPS, st, "rw")
        self.assertIn(0x10000000, got)
        self.assertNotIn(0x20000000, got)

    def test_custom_patterns_wildcard_and_substring(self):
        st = RF.FilterState(hide=(), custom="Il2Cpp*, shm")
        got = RF.included_starts(MAPS, st, "rw")
        self.assertNotIn(0x30000000, got)
        self.assertNotIn(0x400000000, got)
        self.assertIn(0x10000000, got)

    def test_uncheck_one_eboot_section(self):
        st = RF.FilterState(hide=())
        secs = RF.build_sections(MAPS)
        data = next(s for s in secs["eboot"] if s.label.startswith("Daten-Bereich"))
        st.set_section(data, False, secs["eboot"])
        self.assertNotIn(0x72DC000, RF.included_starts(MAPS, st, "rw"))

    def test_category_off_applies_to_new_regions(self):
        st = RF.FilterState(hide=())
        secs = RF.build_sections(MAPS)
        st.set_category("heap", False, secs["heap"])
        self.assertEqual(st.category_state("heap", secs["heap"]), "off")
        grown = MAPS + [(0x600000000, 0x600000000 + 50 * MB, 3, "anon:new")]
        got = RF.included_starts(grown, st, "rw")
        self.assertNotIn(0x600000000, got)
        self.assertNotIn(0x200000000, got)

    def test_enable_single_child_of_disabled_category(self):
        st = RF.FilterState(hide=())
        secs = RF.build_sections(MAPS)
        st.set_category("heap", False, secs["heap"])
        st.set_section(secs["heap"][0], True, secs["heap"])
        self.assertEqual(st.category_state("heap", secs["heap"]), "mixed")
        got = RF.included_starts(MAPS, st, "rw")
        self.assertIn(0x200000000, got)
        self.assertNotIn(0x300000000, got)

    def test_only_presets(self):
        st = RF.FilterState(hide=())
        st.only(("eboot",))
        self.assertEqual(RF.included_starts(MAPS, st, "all"), {0x400000, 0x6470000, 0x72DC000})
        st.all_off(); self.assertEqual(RF.included_starts(MAPS, st, "all"), set())
        st.all_on(); self.assertTrue(RF.included_starts(MAPS, st, "all"))

    def test_hide_pattern_no_duplicates(self):
        st = RF.FilterState(hide=())
        st.hide_pattern("libFoo.sprx"); st.hide_pattern("LIBFOO.sprx"); st.hide_pattern("bar")
        self.assertEqual(RF.split_patterns(st.custom), ["libfoo.sprx", "bar"])


class StatsMatchScan(unittest.TestCase):
    def test_stats_count_equals_selection(self):
        st = RF.FilterState()
        secs = RF.build_sections(MAPS)
        for scope in ("data", "rw", "all"):
            s = RF.stats(secs, st, scope)
            self.assertEqual(s["sel_n"], len(RF.included_starts(MAPS, st, scope)), scope)
            self.assertLess(s["sel_b"], s["total_b"])

    def test_filtering_libs_removes_most_bytes(self):
        secs = RF.build_sections(MAPS)
        s = RF.stats(secs, RF.FilterState(), "rw")
        self.assertGreater(s["total_b"] - s["sel_b"], 600 * MB)

    def test_fmt_size(self):
        self.assertEqual(RF.fmt_size(9.2 * 1024 * MB), "9.20 GB")
        self.assertEqual(RF.fmt_size(80 * MB), "80.0 MB")
        self.assertEqual(RF.fmt_size(64 * 1024), "64 KB")


class Persistence(unittest.TestCase):
    def test_roundtrip_drops_address_keys(self):
        st = RF.FilterState(hide=("libsce", "bogus"), custom="x*", off={"cat:heap", "lib:a.prx", "reg:1000"})
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.json")
            self.assertTrue(RF.save_state(st, p))
            back = RF.load_state(p)
        self.assertEqual(back.hide, {"libsce"} | ({"bogus"} & set(RF.PRESETS)))
        self.assertEqual(back.off, {"cat:heap", "lib:a.prx"})
        self.assertEqual(back.custom, "x*")

    def test_missing_or_broken_file_gives_defaults(self):
        self.assertEqual(RF.load_state("/nonexistent/x.json").hide, set(RF.DEFAULT_HIDE))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.json"); Path(p).write_text("", encoding="utf-8") or Path(p).write_text("{kaputt", encoding="utf-8")
            self.assertEqual(RF.load_state(p).hide, set(RF.DEFAULT_HIDE))


class ScannerPick(unittest.TestCase):
    def test_regions_uses_pick(self):
        class C:
            def get_maps_named(self): return MAPS
            def get_maps(self): return [(s, e, p) for s, e, p, _ in MAPS]
        sc = SC.Scanner("h", 1, 1); sc.client = C()
        full = sc.regions("rw")
        st = RF.FilterState()
        part = sc.regions("rw", pick=lambda m: RF.included_starts(m, st, "rw"))
        self.assertLess(len(part), len(full))
        self.assertNotIn((0x10000000, 0x10000000 + 600 * MB), part)
        self.assertEqual(sc.regions("rw"), full)               # ohne pick unveraendert


if __name__ == "__main__":
    unittest.main()
