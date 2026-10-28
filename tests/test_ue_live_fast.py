"""Schneller Unreal-Objekt-Index: gleiches Ergebnis wie der alte Einzel-Weg, weniger Reads, Rueckfaelle, Verbindungen."""
import os
import random
import struct
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import fastread
import ue_live as L
import ue_quick as Q

BASE = 0x400000
HEAP = 0x10000000
HEAP_SIZE = 0x2000000
OBJ0 = HEAP + 0x400000                                   # hier beginnen die Objekte
POOL = (HEAP, HEAP + 0x20000)                            # zwei Name-Pool-Bloecke
TABLE, CHUNK0, CHUNK1 = HEAP + 0x40000, HEAP + 0x50000, HEAP + 0x200000
ITEM = 0x18


class Mem:
    """Speicherabbild mit Zaehler und Sperre (Lesen kommt aus mehreren Threads)."""

    def __init__(self, latency=0.0):
        self.regions, self.reads, self.latency = {}, 0, latency
        self.lock = threading.Lock()

    def map(self, start, size):
        self.regions[start] = bytearray(size)
        return self.regions[start]

    def read(self, addr, n):
        with self.lock:
            self.reads += 1
        if self.latency:
            time.sleep(self.latency)
        for s, b in self.regions.items():
            if s <= addr and addr + n <= s + len(b):
                return bytes(b[addr - s:addr - s + n])
        raise OSError(f"unmapped {addr:#x}")


def make_world(n_objects=3000, seed=1, latency=0.0, hole=True):
    """Synthetische UE-Welt mit n_objects Objekten, zwei Name-Pool-Bloecken, breiten Namen und Namens-Nummern."""
    rnd = random.Random(seed)
    mem = Mem(latency)
    base = mem.map(BASE, 0x2000)
    heap = mem.map(HEAP, HEAP_SIZE)
    names, cur = {}, [0, 0]                              # Name -> FName-Index; Schreibposition je Block

    def add_name(s, blk=0):
        key = (s, blk)
        if key in names:
            return names[key]
        wide = any(ord(c) > 255 for c in s)
        raw = s.encode("utf-16-le") if wide else s.encode("latin-1")
        length = len(s)
        entry = struct.pack("<H", (length << 6) | (1 if wide else 0)) + raw
        if len(entry) % 2:
            entry += b"\0"
        off = POOL[blk] - HEAP + cur[blk]
        heap[off:off + len(entry)] = entry
        names[key] = (blk << 16) | (cur[blk] // 2)
        cur[blk] += len(entry)
        return names[key]

    add_name("None")
    struct.pack_into("<Q", base, 0x400 + 0x10, POOL[0])  # FNamePool: Blocks ab +0x10
    struct.pack_into("<Q", base, 0x400 + 0x18, POOL[1])

    objs, nxt = [], [OBJ0]

    def new_obj(name, cls, outer=0, number=0, flags=0, size=0x40, extra=None, blk=0):
        a = nxt[0]
        nxt[0] += size
        if hole and len(objs) == n_objects // 2:         # Luecke im Adressraum: ein Fenster darueber waere nicht lesbar
            nxt[0] += 0x4000
            a = nxt[0]
            nxt[0] += size
        struct.pack_into("<QII", heap, a - HEAP, 0x500000, flags, len(objs))
        struct.pack_into("<Q", heap, a - HEAP + 0x10, cls)
        struct.pack_into("<II", heap, a - HEAP + 0x18, add_name(name, blk), number)
        struct.pack_into("<Q", heap, a - HEAP + 0x20, outer)
        for off, v in (extra or {}).items():
            struct.pack_into("<Q", heap, a - HEAP + off, v)
        objs.append(a)
        return a

    cls_class = new_obj("Class", 0)
    struct.pack_into("<Q", heap, cls_class - HEAP + 0x10, cls_class)
    actor = new_obj("ActorComponent", cls_class, extra={0x40: 0}, size=0x80)
    health = new_obj("HealthComponent", cls_class, extra={0x40: actor}, size=0x80)
    bp = new_obj("BP_HealthComponent_C", cls_class, extra={0x40: health}, size=0x80)
    other = new_obj("OtherThing", cls_class, extra={0x40: 0}, size=0x80)
    new_obj("Default__HealthComponent", health, flags=0x10)
    for k in range(n_objects):
        pick = rnd.random()
        cls = health if pick < 0.2 else bp if pick < 0.3 else other if pick < 0.9 else actor
        title = rnd.choice(["Comp", "Thing", "Gold", "ÄÖÜ_日本語", "X"])      # auch breite Namen (UTF-16)
        new_obj(f"{title}{k % 97}", cls, outer=rnd.choice(objs), number=rnd.choice([0, 0, 1, 5]),
                flags=rnd.choice([0, 0, 0, 0x20]), size=rnd.choice([0x40, 0x40, 0x80, 0x100, 0x300]),
                blk=1 if k % 3 == 0 else 0)
    # GObjects: Tabelle -> Chunks (je 65536 Eintraege zu 0x18 Byte)
    for i, a in enumerate(objs):
        chunk = CHUNK0 if i < L.BLOCK else CHUNK1
        struct.pack_into("<Q", heap, chunk - HEAP + (i % L.BLOCK) * ITEM, a)
    struct.pack_into("<QQ", heap, TABLE - HEAP, CHUNK0, CHUNK1)
    nchunks = 1 + (len(objs) - 1) // L.BLOCK
    struct.pack_into("<QQiiii", base, 0x100, TABLE, 0, 65536 * nchunks, len(objs) + 200, nchunks, nchunks)
    struct.pack_into("<i", base, 0x100 + 0x14, len(objs))
    return mem, objs


def connect(mem, **kw):
    live = L.UELive(mem.read, BASE, None, gobjects_rva=0x100, gnames_rva=0x400, **kw)
    live.setup([BASE])
    return live


class IndexEquality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mem, cls.objs = make_world(3000)
        live = connect(cls.mem)
        live.fast = False
        cls.ref = live.build_index()
        cls.ref_state = (dict(live.outers), dict(live.rflags))
        cls.ref_inst = live.instances("UHealthComponent")
        cls.ref_inst_all = live.instances("UHealthComponent", include_defaults=True)
        cls.ref_inst_exact = live.instances("UHealthComponent", subclasses=False)

    def test_setup_found_the_world(self):
        self.assertGreater(len(self.ref), 2500)

    def _fast(self, **kw):
        live = connect(self.mem, **kw)
        live.fast = True
        return live

    def test_same_index_one_reader(self):
        live = self._fast()
        idx = live.build_index()
        self.assertEqual(idx, self.ref)
        self.assertEqual(list(idx), list(self.ref))                        # auch die Reihenfolge (Index-Reihenfolge)
        self.assertEqual((live.outers, live.rflags), self.ref_state)
        self.assertEqual(live.index_stats["mode"], "fast")

    def test_same_index_four_readers(self):
        live = self._fast(extra_readers=[self.mem.read] * 3)
        idx = live.build_index()
        self.assertEqual(idx, self.ref)
        self.assertEqual(list(idx), list(self.ref))
        self.assertEqual(live.index_stats["readers"], 4)

    def test_instances_identical(self):
        live = self._fast(extra_readers=[self.mem.read] * 3)
        live.build_index()
        self.assertEqual(live.instances("UHealthComponent"), self.ref_inst)
        self.assertEqual(live.instances("UHealthComponent", include_defaults=True), self.ref_inst_all)
        self.assertEqual(live.instances("UHealthComponent", subclasses=False), self.ref_inst_exact)
        self.assertGreater(len(self.ref_inst), 100)

    def test_names_with_numbers_and_wide_chars(self):
        live = self._fast()
        idx = live.build_index()
        names = {v[2] for v in idx.values()}
        self.assertTrue(any("日本語" in n for n in names))
        self.assertTrue(any(n.endswith("_4") for n in names))              # number 5 -> "_4"
        self.assertEqual(names, {v[2] for v in self.ref.values()})

    def test_progress_reaches_total(self):
        seen = []
        live = self._fast()
        live.build_index(progress=lambda d, t: seen.append((d, t)))
        self.assertEqual(seen[-1][0], seen[-1][1])
        self.assertEqual([d for d, _ in seen], sorted(d for d, _ in seen))

    def test_unreadable_windows_fall_back_to_single_reads(self):
        calls = [0]

        def flaky(addr, n):
            calls[0] += 1
            if n > 0x1000 and calls[0] % 2 == 0:                          # jedes zweite grosse Fenster scheitert
                raise OSError("kaputt")
            return self.mem.read(addr, n)
        live = connect(self.mem, extra_readers=[flaky, flaky])
        live.fast = True
        self.assertEqual(live.build_index(), self.ref)
        self.assertEqual(live.index_stats["mode"], "fast")

    def test_failed_name_blocks_fall_back_to_single_names(self):
        def no_name_blocks(addr, n):
            if n == L.NAME_BLOCK:
                raise OSError("kein Block")
            return self.mem.read(addr, n)
        live = connect(self.mem, extra_readers=[no_name_blocks])
        live._read = self.mem.read
        live.fast = True
        live.readers = lambda: [no_name_blocks]
        self.assertEqual(live.build_index(), self.ref)

    def test_hard_failure_uses_serial_path(self):
        live = self._fast()
        live.log = lambda m: None
        with mock.patch.object(L.UELive, "_build_index_fast", side_effect=RuntimeError("x")):
            self.assertEqual(live.build_index(), self.ref)
        self.assertEqual(live.index_stats["mode"], "serial")


class FewerReads(unittest.TestCase):
    def test_far_fewer_reads_than_serial_path(self):
        mem, _ = make_world(20000, seed=3)
        live = connect(mem)
        live.fast = False
        before = mem.reads
        ref = live.build_index()
        serial_reads = mem.reads - before
        live = connect(mem, extra_readers=[mem.read] * 3)
        live.fast = True
        before = mem.reads
        idx = live.build_index()
        fast_reads = mem.reads - before
        self.assertEqual(idx, ref)
        self.assertLess(fast_reads, serial_reads)

    def test_two_chunks_of_the_object_table(self):
        mem, objs = make_world(L.BLOCK + 500, seed=5, hole=False)
        live = connect(mem, extra_readers=[mem.read] * 2)
        live.fast = True
        idx = live.build_index()
        self.assertEqual(len(idx), len(objs))
        self.assertEqual(sorted(v[0] for v in idx.values())[-1], len(objs) - 1)
        ref_live = connect(mem)
        ref_live.fast = False
        self.assertEqual(idx, ref_live.build_index())

    def test_more_connections_are_faster_with_latency(self):
        mem, _ = make_world(6000, seed=2, latency=0.01)
        one = connect(mem)
        t = time.time()
        one.build_index()
        t1 = time.time() - t
        four = connect(mem, extra_readers=[mem.read] * 3)
        t = time.time()
        four.build_index()
        t4 = time.time() - t
        self.assertLess(t4, t1)


class FastReadModule(unittest.TestCase):
    def test_stream_order_and_failure(self):
        mem = os.urandom(1 << 16)

        def rd(addr, n):
            time.sleep(random.random() * 0.002)
            if addr == 8192:
                raise OSError("x")
            return mem[addr:addr + n]
        jobs = [(a, 4096, a) for a in range(0, len(mem), 4096)]
        got = list(fastread.stream([rd] * 4, jobs))
        self.assertEqual([g[0] for g in got], [j[2] for j in jobs])
        self.assertIsNone(dict(got)[8192])
        self.assertEqual(dict(got)[4096], mem[4096:8192])

    def test_short_read_counts_as_failure(self):
        got = list(fastread.stream([lambda a, n: b"x"], [(0, 10, "t")]))
        self.assertEqual(got, [("t", None)])

    def test_cancel(self):
        flag = threading.Event()
        n = 0
        for _ in fastread.stream([lambda a, k: bytes(k)] * 2, [(i, 8, i) for i in range(500)], cancel=flag.is_set):
            n += 1
            if n == 3:
                flag.set()
        self.assertLess(n, 10)

    def test_plan_windows(self):
        addrs = [0x1000, 0x1040, 0x1080, 0x9000, 0x9040, 0x20000]
        w = fastread.plan_windows(addrs, 0x28, gap=0x100, maxlen=0x1000)
        self.assertEqual([(s, lo, hi) for s, _l, lo, hi in w], [(0x1000, 0, 3), (0x9000, 3, 5), (0x20000, 5, 6)])
        self.assertEqual(w[0][1], 0x80 + 0x28)
        # maxlen trennt auch dicht liegende Adressen
        dense = list(range(0, 0x4000, 0x40))
        w = fastread.plan_windows(dense, 0x28, gap=0x100, maxlen=0x1000)
        self.assertTrue(all(length <= 0x1000 for _s, length, _lo, _hi in w))
        self.assertEqual(sum(hi - lo for _s, _l, lo, hi in w), len(dense))
        self.assertEqual(fastread.plan_windows([], 8), [])

    def test_open_readers_without_host_gives_nothing(self):
        class C:
            pid = 1
        self.assertEqual(fastread.open_readers(C()), ([], [], None))


class FakeClient:
    instances = []

    def __init__(self, host, port, timeout=5):
        self.host, self.port, self.pid, self.closed = host, port, None, False
        FakeClient.instances.append(self)

    def connect(self):
        pass

    def read_memory(self, a, n):
        return bytes(n)

    def close(self):
        self.closed = True


class Main:
    host, port, pid = "10.0.0.2", 744, 77
    read_memory = staticmethod(lambda a, n: bytes(n))


class AttachTests(unittest.TestCase):
    def setUp(self):
        FakeClient.instances = []
        self.live = L.UELive(lambda a, n: bytes(n), BASE, None)

    def test_attach_opens_three_connections_with_the_game_pid(self):
        with mock.patch("ps5_client.PS5DebugClient", FakeClient):
            n = Q.attach_fast(self.live, Main(), log=lambda m: None, fast=True)
        self.assertEqual(n, 3)
        self.assertEqual(len(self.live.readers()), 4)
        self.assertTrue(all(c.pid == 77 for c in FakeClient.instances))

    def test_attach_twice_does_not_open_more(self):
        with mock.patch("ps5_client.PS5DebugClient", FakeClient):
            Q.attach_fast(self.live, Main(), log=lambda m: None, fast=True)
            Q.attach_fast(self.live, Main(), log=lambda m: None, fast=True)
        self.assertEqual(len(FakeClient.instances), 3)

    def test_switching_off_closes_them(self):
        with mock.patch("ps5_client.PS5DebugClient", FakeClient):
            Q.attach_fast(self.live, Main(), log=lambda m: None, fast=True)
            Q.attach_fast(self.live, Main(), log=lambda m: None, fast=False)
        self.assertTrue(all(c.closed for c in FakeClient.instances))
        self.assertEqual(len(self.live.readers()), 1)

    def test_connection_failure_is_logged_and_not_fatal(self):
        class Bad(FakeClient):
            def connect(self):
                raise OSError("refused")
        msgs = []
        with mock.patch("ps5_client.PS5DebugClient", Bad):
            n = Q.attach_fast(self.live, Main(), log=msgs.append, fast=True)
        self.assertEqual(n, 0)
        self.assertTrue(any("nicht möglich" in m for m in msgs))

    def test_default_follows_module_switch(self):
        old = Q.FAST_READ
        try:
            Q.FAST_READ = False
            with mock.patch("ps5_client.PS5DebugClient", FakeClient):
                self.assertEqual(Q.attach_fast(self.live, Main(), log=lambda m: None), 0)
        finally:
            Q.FAST_READ = old
        self.assertEqual(FakeClient.instances, [])

    def test_connect_live_closes_readers_of_the_replaced_live(self):
        import ue_world as W
        im, ref, sdk, client = W.world()
        proj = W.Proj(sdk)
        first = Q.connect_live(client, proj, log=lambda m: None, fast=False)
        closed = []
        first.attach_readers([lambda a, n: b""], [lambda: closed.append(1)])
        client2 = W.Client(im)                          # neue Verbindung -> anderes read_memory -> neues UELive
        second = Q.connect_live(client2, proj, log=lambda m: None, cached=first, fast=False)
        self.assertIsNot(first, second)
        self.assertEqual(closed, [1])
        self.assertEqual(first.extra_readers, [])


if __name__ == "__main__":
    unittest.main()
