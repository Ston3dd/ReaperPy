import os, struct, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ue_live as L, uesdk

BASE = 0x400000
HEAP = 0x10000000


class Image:
    def __init__(self):
        self.regions = {}           # start -> bytearray
        self.reads = 0
    def map(self, start, size):
        self.regions[start] = bytearray(size)
    def w(self, addr, data):
        for s, b in self.regions.items():
            if s <= addr and addr + len(data) <= s + len(b):
                b[addr - s:addr - s + len(data)] = data; return
        raise KeyError(hex(addr))
    def read(self, addr, n):
        self.reads += 1
        for s, b in self.regions.items():
            if s <= addr and addr + n <= s + len(b):
                return bytes(b[addr - s:addr - s + n])
        raise OSError(f"unmapped {addr:#x}")


def build(wrapped=True, style="ue5", none_gap=0):
    im = Image(); im.map(BASE, 0x2000); im.map(HEAP, 0x200000)
    # --- Name-Pool: Block 0 bei HEAP
    pool_block, cur, names = HEAP, 0, {}
    def add_name(s):
        nonlocal cur
        if s in names: return names[s]
        raw = s.encode()
        entry = struct.pack("<H", len(raw) << (6 if style == "ue5" else 1)) + raw
        if len(entry) % 2: entry += b"\0"
        im.w(pool_block + cur, entry)
        names[s] = cur // 2
        cur += len(entry)
        return names[s]
    cur = none_gap                                   # Abstand vor dem ersten Eintrag (Test: "None" nicht am Blockanfang)
    add_name("None")
    # FNamePool bei BASE+0x400: Blocks ab +0x10
    im.w(BASE + 0x400 + 0x10, struct.pack("<Q", pool_block))
    # --- Objekte
    nxt = [HEAP + 0x100000]
    objs = []
    def new_obj(name, cls, outer=0, number=0, size=0x100, extra=None):
        a = nxt[0]; nxt[0] += size
        hdr = bytearray(size)
        struct.pack_into("<QII", hdr, 0, 0x500000, 0, len(objs))
        struct.pack_into("<Q", hdr, 0x10, cls)
        struct.pack_into("<II", hdr, 0x18, add_name(name), number)
        struct.pack_into("<Q", hdr, 0x20, outer)
        for off, v in (extra or {}).items():
            struct.pack_into("<Q", hdr, off, v)
        im.w(a, bytes(hdr)); objs.append(a); return a
    cls_class = new_obj("Class", 0)
    im.w(cls_class + 0x10, struct.pack("<Q", cls_class))
    actor_comp = new_obj("ActorComponent", cls_class)
    health = new_obj("HealthComponent", cls_class, extra={0x40: actor_comp})
    bp_health = new_obj("BP_HealthComponent_C", cls_class, extra={0x40: health})
    fn_class = new_obj("Function", cls_class)
    new_obj("TakeDamage", fn_class, outer=health, extra={0xD8: BASE + 0x900})
    new_obj("Default__HealthComponent", health)
    p1 = new_obj("HealthComp", health, number=1)           # -> HealthComp_0
    p2 = new_obj("BP_HealthComponent_C", bp_health, number=3)
    new_obj("Other", actor_comp)
    # --- TUObjectArray: Table -> Chunk0 -> Items (0x18)
    chunk_table, chunk0 = HEAP + 0x80000, HEAP + 0x90000
    for i, a in enumerate(objs):
        im.w(chunk0 + i * 0x18, struct.pack("<Q", a))
    im.w(chunk_table, struct.pack("<Q", chunk0))
    arr = struct.pack("<QQiiii", chunk_table, 0, 65536, 200, 1, 1)
    arr = arr[:0x14] + struct.pack("<i", len(objs) + 200) + arr[0x18:]      # NumElements > 100 (Erkennung)
    # NumElements muss real sein: Platz fuer Pseudo-Objekte (leere Items = 0) ist ok
    im.w(BASE + 0x100 + (0x10 if wrapped else 0), arr)
    return im, dict(health=health, bp=bp_health, p1=p1, p2=p2, fn=BASE + 0x900)


SDK_TXT = """class UFunction : public UStruct
{
public:
	void*                                        ExecFunction;                                      // 0x00D8(0x0008)(ZeroConstructor)
};
"""


class T(unittest.TestCase):
    def live(self, wrapped):
        im, ref = build(wrapped)
        sdk = uesdk.parse_header_text(SDK_TXT)
        lv = L.UELive(im.read, BASE, sdk, gobjects_rva=0x100, gnames_rva=0x400, log=lambda m: None)
        return lv, ref, im

    def test_setup_both_layouts(self):
        for wrapped in (False, True):
            lv, ref, _ = self.live(wrapped)
            rep = lv.setup()
            self.assertEqual(rep["item_size"], 0x18)
            self.assertEqual(lv.fname_str(0), "None")

    def test_names_and_full_name(self):
        lv, ref, _ = self.live(True); lv.setup()
        self.assertEqual(lv.name(ref["p1"]), "HealthComp_0")
        self.assertEqual(lv.class_name(ref["p1"]), "HealthComponent")
        self.assertEqual(lv.full_name(ref["p1"]), "HealthComponent HealthComp_0")

    def test_instances_with_subclass_and_cdo_filter(self):
        lv, ref, _ = self.live(True); lv.setup()
        lv.build_index()
        inst = lv.instances("UHealthComponent")
        self.assertEqual({i["addr"] for i in inst}, {ref["p1"], ref["p2"]})          # inkl. BP-Unterklasse, ohne Default__
        self.assertEqual({i["addr"] for i in lv.instances("UHealthComponent", subclasses=False)}, {ref["p1"]})
        self.assertEqual(lv.instances("UNichtDa"), [])
        self.assertEqual(len(lv.instances("UHealthComponent", include_defaults=True)), 3)

    def test_function_entry(self):
        lv, ref, _ = self.live(True); lv.setup()
        self.assertEqual(lv.function_entry("UHealthComponent", "TakeDamage"), (BASE + 0x900, 0x900))
        self.assertIsNone(lv.function_entry("UHealthComponent", "Nope"))

    def test_scan_helper(self):
        lv, ref, _ = self.live(True); lv.setup()
        hits = lv.__class__  # noqa
        objs = L.instances_by_scan(lv, ref["health"], lambda v: [ref["p1"] + 0x10] if v == ref["health"] else [])
        self.assertEqual(objs, [ref["p1"]])

    def test_block_cache_reduces_reads(self):
        lv, ref, im = self.live(True); lv.setup(); im.reads = 0
        lv.drop_cache(); lv.build_index()
        self.assertLess(im.reads, 60)                       # nicht ein Read pro Feld

    def test_wrong_gnames_reports(self):
        im, _ = build(True)
        lv = L.UELive(im.read, BASE, None, gobjects_rva=0x100, gnames_rva=0x800)
        with self.assertRaises(L.UELiveError):
            lv.setup()



class NameStyles(unittest.TestCase):
    def live(self, **kw):
        im, ref = build(True, **kw)
        return L.UELive(im.read, BASE, uesdk.parse_header_text(SDK_TXT), gobjects_rva=0x100, gnames_rva=0x400, log=lambda m: None), ref

    def test_ue4_style_len_in_15_bits(self):
        lv, ref = self.live(style="ue4")
        lv.setup([BASE])
        self.assertEqual(lv.name_style, "ue4")
        self.assertEqual(lv.name(ref["p1"]), "HealthComp_0")           # Namen werden auch im UE4-Format richtig gelesen

    def test_ue5_still_works(self):
        lv, _ = self.live(style="ue5"); lv.setup([BASE]); self.assertEqual(lv.name_style, "ue5")

    def test_none_not_at_block_start(self):
        lv, ref = self.live(style="ue4", none_gap=8)
        lv.setup([BASE])
        self.assertEqual(lv.none_index, 4); self.assertEqual(lv.fname_str(4), "None")

    def test_offsets_json_with_absolute_values(self):
        """Dein Fall: offsets.json enthaelt absolute VAs statt RVAs."""
        im, ref = build(True, style="ue4")
        lv = L.UELive(im.read, BASE, None, gobjects_rva=BASE + 0x100, gnames_rva=BASE + 0x400, log=lambda m: None)
        rep = lv.setup([BASE])
        self.assertIn("absolute", "\n".join(lv.diag)); self.assertTrue(rep["count"] > 100)

    def test_diag_shows_head_bytes_when_no_none(self):
        im, ref = build(True)
        im.w(HEAP, b"\x11\x22\x33\x44\x55\x66\x77\x88" + bytes(60))        # Block 0 zerstoeren
        lv = L.UELive(im.read, BASE, None, gobjects_rva=0x100, gnames_rva=0x400, log=lambda m: None)
        with self.assertRaises(L.UELiveError) as cm: lv.setup([BASE])
        self.assertIn("Kopf 11 22 33 44", str(cm.exception))


class Robust(unittest.TestCase):
    def mk(self, **kw):
        im, ref = build(True)
        return L.UELive(im.read, BASE, uesdk.parse_header_text(SDK_TXT), log=lambda m: None, **kw), im, ref

    def test_second_base_candidate_wins(self):
        lv, _, _ = self.mk(gobjects_rva=0x100, gnames_rva=0x400)
        rep = lv.setup([0x1000000, BASE])                       # erste Basis falsch (Prozess an anderer Adresse)
        self.assertEqual(rep["base"], BASE); self.assertEqual(lv.base, BASE)
        self.assertEqual(lv.fname_str(0), "None")

    def test_absolute_addresses_fallback(self):
        lv, _, _ = self.mk(gobjects_rva=0x999, gnames_rva=0x999)    # RVAs falsch
        with self.assertRaises(L.UELiveError):
            lv.setup([BASE])
        rep = lv.setup([BASE], abs_gobjects=BASE + 0x100, abs_gnames=BASE + 0x400)
        self.assertEqual(rep["array"], BASE + 0x110)               # FUObjectArray + 0x10

    def test_diagnostics_explain_failure(self):
        lv, im, _ = self.mk(gobjects_rva=0x100, gnames_rva=0x400)
        im.w(BASE + 0x110 + 0x14, struct.pack("<i", 5))              # NumElements kaputt
        with self.assertRaises(L.UELiveError) as cm:
            lv.setup([BASE])
        msg = str(cm.exception)
        self.assertIn("Elementzahl unplausibel", msg); self.assertIn("num=5", msg); self.assertIn("Basis 0x400000", msg)
        lv2 = L.UELive(lambda a, n: (_ for _ in ()).throw(OSError("kein Zugriff")), BASE, None, gobjects_rva=1, gnames_rva=2)
        with self.assertRaises(L.UELiveError) as cm:
            lv2.setup()
        self.assertIn("Lesefehler: kein Zugriff", str(cm.exception))

    def test_custom_layout_from_engine_json(self):
        lv, im, _ = self.mk(gobjects_rva=0x100, gnames_rva=0x400)
        self.assertTrue(lv.setup([BASE], layout=[0, 16, 20, 24, 28])["count"] > 100)

    def test_module_base_from_maps(self):
        self.assertEqual(L.live_module_base([(0x7000000, 0x7100000, 5), (0x400000, 0x500000, 5), (0x10000000, 0x10100000, 3)]), 0x400000)
        self.assertIsNone(L.live_module_base([(0x10000000, 0x10100000, 3)]))

if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()
