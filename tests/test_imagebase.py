import imagebase as IB

MAPS = [(0x1000, 0x2000, 3, "libc.prx"),
        (0x800000, 0x900000, 5, "eboot.bin"), (0x900000, 0x910000, 3, "eboot.bin"),
        (0x7000000, 0x7100000, 3, "")]


def test_detect_lowest_eboot():
    assert IB.detect_image_base(MAPS) == 0x800000


def test_detect_none():
    assert IB.detect_image_base([(1, 2, 3, "libc.prx")]) is None


def test_check_mismatch_and_match():
    det, ok, txt = IB.check_base(MAPS, 0x400000)
    assert det == 0x800000 and not ok and "NICHT" in txt
    assert IB.check_base(MAPS, 0x800000)[1]
    assert IB.check_base([(1, 2, 3, "x")], 0x400000)[1]


def test_summary_sorted():
    rows = IB.module_summary(MAPS)
    assert rows[0][0] == "libc.prx" and [r[0] for r in rows].count("eboot.bin") == 1
