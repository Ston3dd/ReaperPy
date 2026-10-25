import os, struct, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import scanner as SC


class FakeIO:
    """Zeichnet die gesendeten Pakete auf und beantwortet START/COUNT wie ein Payload."""
    def __init__(self, reply): self.sent, self.reply = [], reply
    def pkt(self, cmd, data=b""): self.sent.append((cmd, data))
    def send(self, b): self.sent.append(("payload", b))
    def skip_acks(self, *a, **k): return 2
    def expect(self, *a): pass
    def recv(self, n): return self.reply[:n]
    def u64(self): return SC.SENT64
    def drain_progress(self, on_value, check=None, interval=0.1): return None


def scanner(engines, threads=8):
    s = SC.Scanner("h", 1, 1)
    s.caps = {"version": 1, "engines": engines, "threads": threads}
    return s


ALL = 0x00000FFF                        # exakt die CAPS aus dem echten Log: engines=0x00000FFF


class Flags(unittest.TestCase):
    def test_parallel_only_where_protocol_says_it_works(self):
        """PROTOCOL.md: TS_PARALLEL_COMPARE = START + Aliasing + exakt + Streaming (kein Snapshot)."""
        ok = dict(opts={"aliasing": True}, first=True)
        self.assertTrue(scanner(ALL)._flags(vname="Int32", ctype="Genau", **ok) & SC.TS_PARALLEL)
        self.assertFalse(scanner(ALL & ~SC.TSE_PARALLEL)._flags(vname="Int32", ctype="Genau", **ok) & SC.TS_PARALLEL)
        self.assertFalse(scanner(ALL)._flags({}, "Int32", "Genau", first=True) & SC.TS_PARALLEL)          # ohne Aliasing
        self.assertFalse(scanner(ALL)._flags({"aliasing": True}, "Int32", "Größer als", first=True) & SC.TS_PARALLEL)
        self.assertFalse(scanner(ALL)._flags({"aliasing": True}, "Float", "Unbekannter Startwert", snapshot=True,
                                             resident=False, first=True) & SC.TS_PARALLEL)                # Snapshot
        self.assertFalse(scanner(ALL)._flags({"aliasing": True, "parallel": False}, "Int32", "Genau",
                                             first=True) & SC.TS_PARALLEL)                                # abgeschaltet

    def test_other_flags_unchanged(self):
        f = scanner(ALL)._flags({}, "Int32", "Genau", resident=True)
        self.assertTrue(f & SC.TS_RESIDENT)
        self.assertFalse(f & (SC.TS_USE_ALIASING | SC.TS_SNAPSHOT | SC.TS_SEGMENTS))

    def test_first_scan_packet_flags_on_the_wire(self):
        s = scanner(ALL); s.io = FakeIO(struct.pack("<IQ", 1, 5))
        s._turbo_first("Int32", "Genau", SC.encode_value("Int32", "7"), [(0x1000, 0x3000)], {"aliasing": True}, None, False)
        cmd, pkt = s.io.sent[0]
        self.assertEqual(cmd, SC.CMD_TS_START)
        flags = struct.unpack("<IQIBBBII", pkt)[-1]
        self.assertTrue(flags & SC.TS_PARALLEL and flags & SC.TS_USE_ALIASING and flags & SC.TS_RESIDENT, hex(flags))
        s = scanner(ALL); s.io = FakeIO(b"")                                   # Snapshot: nie Parallel
        s.io.recv = lambda n, seq=iter([struct.pack("<QQ", 1, 8), struct.pack("<IQ", 1, 5)]): next(seq)
        s._turbo_first("Float", "Unbekannter Startwert", b"", [(0x1000, 0x3000)], {"aliasing": True}, None, True)
        flags = struct.unpack("<IQIBBBII", s.io.sent[0][1])[-1]
        self.assertTrue(flags & SC.TS_SNAPSHOT and flags & SC.TS_FLOAT_SIMPLE)
        self.assertFalse(flags & SC.TS_PARALLEL)

    def test_rescan_packet_never_requests_parallel(self):
        s = scanner(ALL); s.io = FakeIO(b""); s.vname = "Int32"; s.count = 4; s.first_scan_done = True
        s._turbo_count("Genau", SC.encode_value("Int32", "7"), {"aliasing": True}, None)
        flags = struct.unpack("<IQBBII", s.io.sent[0][1])[-1]
        self.assertFalse(flags & SC.TS_PARALLEL)
        self.assertTrue(flags & SC.TS_RESCAN_ALIASING)

    def test_speed_mode_text(self):
        self.assertIn("Parallel ja (Threads=8)", scanner(ALL).speed_mode())
        self.assertIn("ANGEFORDERT: Parallel nein", scanner(ALL).speed_mode())
        self.assertIn("Parallel nein", scanner(SC.TSE_RESIDENT).speed_mode())



if __name__ == "__main__":
    unittest.main()


class Merge(unittest.TestCase):
    def setUp(self): self.s = scanner(ALL)

    def test_adjacent_and_overlapping_merge_but_gaps_stay(self):
        r = self.s._normalise_regions([(0x3000, 0x4000), (0x1000, 0x2000), (0x2000, 0x3000), (0x5000, 0x6000),
                                       (0x5800, 0x6800), (0x9000, 0x9000), (-5, 10)])
        self.assertEqual(r, [(0x1000, 0x4000), (0x5000, 0x6800)])        # Luecke 0x4000..0x5000 bleibt

    def test_idempotent_and_u32_split_kept(self):
        a = self.s._normalise_regions([(0, 0x1_8000_0000), (0x1_8000_0000, 0x3_0000_0000)])
        self.assertEqual(self.s._normalise_regions(a), a)
        self.assertTrue(all(e - b <= 0xFFFFFFFF for b, e in a))
        self.assertEqual((a[0][0], a[-1][1]), (0, 0x3_0000_0000))
        self.assertEqual(sum(e - b for b, e in a), 0x3_0000_0000)        # nichts verloren/ueberbrueckt

    def test_many_small_regions_collapse(self):
        regs = [(0x10000 + i * 0x1000, 0x10000 + (i + 1) * 0x1000) for i in range(20000)]
        self.assertEqual(len(self.s._normalise_regions(regs)), 1)

    def test_first_scan_logs_and_filters_small(self):
        logs = []
        s = scanner(ALL); s.log = logs.append; s.client = object(); s.session = None
        s.io = FakeIO(struct.pack("<IQ", 1, 5))
        regs = [(0x100000, 0x100000 + 0x1000), (0x400000, 0x400000 + 0x100000)]      # 4 KB und 1 MB
        s.first_scan("Int32", "Genau", "7", "", regs, {"min_region": 256 * 1024, "aliasing": True})
        _pid, s0, length = struct.unpack_from("<IQI", s.io.sent[0][1])
        self.assertEqual((s0, length), (0x400000, 0x100000))               # nur das 1-MB-Segment geht raus
        self.assertTrue(any("2 Regionen -> 2 Segmente" in m for m in logs))
        self.assertTrue(any("ausgelassen: 1 Stück" in m for m in logs))
        self.assertTrue(any("ANGEFORDERT: Parallel ja" in m for m in logs))


class SpeedReport(unittest.TestCase):
    MB = 1048576

    def make(self):
        s = scanner(ALL); logs = []
        s.log = logs.append
        # (start, end, prot, flags, MB/s, reserved)
        info = [(0x10000000, 0x10000000 + 1000 * self.MB, 3, 0, 1500, 0),      # schnell
                (0x100000000, 0x100000000 + 2000 * self.MB, 3, 0, 400, 0),      # mittel
                (0x200000000, 0x200000000 + 100 * self.MB, 3, 0, 40, 0)]        # langsam (GPU-Block)
        s.client = type("C", (), {"get_maps": lambda self_: [(a, b, 3) for a, b, *_ in info]})()
        s.io = object(); s._classify = lambda: info
        return s, logs, info

    def test_report_numbers_and_hints(self):
        s, logs, info = self.make()
        regs = [(a, b) for a, b, *_ in info]
        r = s.speed_report(regs, info)
        self.assertEqual([round(x) for x in r["mb"]], [100, 0, 2000, 0, 1000])          # <100 | 100-300 | 300-600 ...
        self.assertAlmostEqual(r["sec"][0], 2.5, 1)                                    # 100 MB bei 40 MB/s
        self.assertAlmostEqual(r["total_s"], 2.5 + 5.0 + 1000 / 1500, 1)
        text = " ".join(logs)
        self.assertIn("< 100 MB/s: 100 MB", text)
        self.assertIn("< 100 MB/s auslassen: -100 MB (3.2 %)", text)
        self.assertIn("< 600 MB/s auslassen: -2100 MB", text)

    def test_regions_applies_threshold_and_reports(self):
        s, logs, info = self.make()
        all_ = s.regions("rw", min_mbps=0, report=True)
        self.assertEqual(len(all_), 3)
        cut = s.regions("rw", min_mbps=300, report=False)
        self.assertEqual([b - a for a, b in cut], [1000 * self.MB, 2000 * self.MB])    # 40-MB/s-Block fehlt
        cut = s.regions("rw", min_mbps=600)
        self.assertEqual([b - a for a, b in cut], [1000 * self.MB])
        self.assertTrue(any("langsame Region" in m for m in logs))

    def test_unknown_speed_counted_and_measure_failure_scans_everything(self):
        s, logs, info = self.make()
        r = s.speed_report([(0x70000000, 0x70000000 + 5 * self.MB)], info)             # in keiner Messregion
        self.assertEqual(round(r["unknown_mb"]), 5)
        s._classify = lambda: (_ for _ in ()).throw(OSError("kaputt"))
        self.assertEqual(len(s.regions("rw", min_mbps=300, report=True)), 3)           # nichts ausgelassen
        self.assertTrue(any("Regions-Messung nicht möglich" in m for m in logs))


import socket, threading, time


def pair():
    a, b = socket.socketpair()
    return a, SC._IO(type("C", (), {"sock": b})())


class Drain(unittest.TestCase):
    def test_values_end_marker_and_leftover_bytes(self):
        a, io = pair()
        a.sendall(struct.pack("<5Q", 10, 20, 30, 40, SC.SENT64) + struct.pack("<QI", 777, 0x1234))   # + naechste Antwort
        seen = []
        last = io.drain_progress(seen.append, interval=0)
        self.assertEqual(last, 40)
        self.assertEqual(seen[-1], 40)
        self.assertEqual(io.u64(), 777)                       # Bytes hinter SENT64 bleiben erhalten
        self.assertEqual(io.u32(), 0x1234)

    def test_fragmented_stream(self):
        a, io = pair()
        data = struct.pack("<1000Q", *range(1000)) + struct.pack("<Q", SC.SENT64) + b"\xAA\xBB"
        def feed():
            for i in range(0, len(data), 3):                  # 3-Byte-Haeppchen quer ueber u64-Grenzen
                a.sendall(data[i:i + 3])
        threading.Thread(target=feed, daemon=True).start()
        self.assertEqual(io.drain_progress(None), 999)
        self.assertEqual(io.recv(2), b"\xAA\xBB")

    def test_throttled_callbacks_and_no_value_stream(self):
        a, io = pair()
        a.sendall(struct.pack("<Q", SC.SENT64))               # sofort fertig, keine Werte
        calls = []
        self.assertIsNone(io.drain_progress(calls.append))
        self.assertEqual(calls, [])
        a, io = pair()
        n = 300_000
        threading.Thread(target=lambda: a.sendall(struct.pack(f"<{n}Q", *range(n)) + struct.pack("<Q", SC.SENT64)),
                         daemon=True).start()
        calls = []
        t0 = time.time(); io.drain_progress(calls.append, interval=0.5)
        self.assertLess(len(calls), 20)                       # nicht 300000 Rueckrufe
        self.assertEqual(calls[-1], n - 1)
        self.assertLess(time.time() - t0, 3.0)

    def test_cancel_raises_and_closed_connection(self):
        a, io = pair()
        a.sendall(struct.pack("<8Q", *range(8)))
        def boom(): raise SC.Cancelled("abgebrochen")
        with self.assertRaises(SC.Cancelled):
            io.drain_progress(None, boom)
        a, io = pair(); a.close()
        with self.assertRaises(ConnectionError):
            io.drain_progress(None)

    def test_snapshot_and_count_use_drain(self):
        """Ende-zu-Ende ueber einen echten Socket: Snapshot-Start, Fortschritt, Ergebnis, danach Vergleich."""
        a, io = pair()
        s = scanner(ALL); s.io = io; s.client = type("C", (), {"sock": io.c.sock, "_send_packet": lambda *x: None})()
        io.pkt = lambda cmd, data=b"": None; io.send = lambda b: None
        io.expect = lambda *x: None; io.skip_acks = lambda *x, **k: 2
        a.sendall(struct.pack("<QQ", 5, 100) + struct.pack("<3Q", 10, 60, 100) + struct.pack("<Q", SC.SENT64)
                  + struct.pack("<IQ", 1, 42))
        prog = []
        n = s._turbo_first("Float", "Unbekannter Startwert", b"", [(0x1000, 0x5000)], {}, lambda f, t: prog.append(f), True)
        self.assertEqual((n, s.session), (42, "snapshot"))
        self.assertTrue(prog and prog[-1] == 1.0)
        s.vname, s.count, s.first_scan_done = "Float", 42, True
        a.sendall(struct.pack("<2Q", 20, 42) + struct.pack("<Q", SC.SENT64) + struct.pack("<Q", 7))
        self.assertEqual(s._turbo_count("Verändert", b"", {}, None), 7)


class SnapshotConfig(unittest.TestCase):
    """CMD_PROC_TURBOSCAN_CONFIG laut PROTOCOL.md: {u32 ram_thresh_mb; u32 spill_path_len} + Pfad (<=63, ohne NUL)."""

    def test_packet_layout(self):
        s = scanner(ALL | SC.TSE_CONFIG); s.io = FakeIO(b""); logs = []; s.log = logs.append
        s.configure_snapshot(4608, "/mnt/ext1")
        cmd, data = s.io.sent[0]
        self.assertEqual(cmd, 0xBDAACC15)
        self.assertEqual(struct.unpack_from("<II", data), (4608, 9))
        self.assertEqual(data[8:], b"/mnt/ext1")
        self.assertEqual(len(data), 8 + 9)
        self.assertEqual(s.snap_ram_mb, 4608); self.assertEqual(s.spill_dir, "/mnt/ext1")
        s.configure_snapshot(0, "")                                           # Standard zuruecksetzen
        self.assertEqual(s.io.sent[1][1], struct.pack("<II", 0, 0))
        self.assertEqual(s.snap_ram_mb, 512)

    def test_limits_and_missing_capability(self):
        s = scanner(ALL | SC.TSE_CONFIG); s.io = FakeIO(b"")
        with self.assertRaises(SC.ScanError): s.configure_snapshot(100, "/" + "x" * 63)     # 64 Bytes
        s.configure_snapshot(100, "/" + "x" * 62)                                           # 63 Bytes ok
        with self.assertRaises(SC.ScanError): s.configure_snapshot(2 ** 32, "")
        with self.assertRaises(SC.ScanError): s.configure_snapshot(-1, "")
        old = scanner(SC.TSE_RESIDENT | SC.TSE_SNAPSHOT); old.io = FakeIO(b"")
        with self.assertRaises(SC.ScanError): old.configure_snapshot(4096, "")
        self.assertEqual(old.io.sent, [])                                                   # nichts gesendet

    def test_first_scan_sends_config_before_start_only_for_snapshot(self):
        s = scanner(ALL | SC.TSE_CONFIG | SC.TSE_COMPACT); s.log = lambda m: None; s.client = object()
        s.io = FakeIO(b"")
        s.io.recv = lambda n, seq=iter([struct.pack("<QQ", 100, 400), struct.pack("<IQ", 1, 50)]): next(seq)
        s.first_scan("Float", "Unbekannter Startwert", "", "", [(0x1000, 0x5000)],
                     {"snap_ram_mb": 4608, "spill_dir": "/mnt/usb0"})
        self.assertEqual([c for c, _d in s.io.sent[:2]], [0xBDAACC15, SC.CMD_TS_START])
        s2 = scanner(ALL | SC.TSE_CONFIG); s2.log = lambda m: None; s2.client = object()
        s2.io = FakeIO(struct.pack("<IQ", 1, 5))
        s2.first_scan("Int32", "Genau", "7", "", [(0x1000, 0x5000)], {"snap_ram_mb": 4608})
        self.assertNotIn(0xBDAACC15, [c for c, _d in s2.io.sent])                            # exakter Scan: kein CONFIG

    def test_config_failure_does_not_abort_scan(self):
        s = scanner(SC.TSE_RESIDENT | SC.TSE_SNAPSHOT | SC.TSE_SEGMENTS); logs = []; s.log = logs.append; s.client = object()
        s.io = FakeIO(b"")
        s.io.recv = lambda n, seq=iter([struct.pack("<QQ", 100, 400), struct.pack("<IQ", 1, 50)]): next(seq)
        s.first_scan("Int32", "Unbekannter Startwert", "", "", [(0x1000, 0x5000)], {"snap_ram_mb": 4608})
        self.assertTrue(any("Standard bleibt aktiv" in m for m in logs))
        self.assertEqual(s.session, "snapshot")

    def test_advice_matches_the_real_log_of_this_user(self):
        """369 031 386 Float-Treffer x 12 Byte = ~4,4 GB bei 512 MB RAM-Anteil -> Auslagerung + Tipp."""
        s = scanner(ALL | SC.TSE_COMPACT); logs = []; s.log = logs.append
        s.vname = "Float"; s.last_flags = SC.TS_SNAPSHOT | SC.TS_FLOAT_SIMPLE
        mb, tip = s.snapshot_advice(369_031_386, 2_400_000_000, 4)
        self.assertAlmostEqual(mb, 369_031_386 * 12 / 1048576, 0)
        self.assertEqual(tip, SC.MAX_SNAPSHOT_RAM_MB)                                       # nie mehr als die PS5-Grenze raten
        self.assertIn("ausgelagert", logs[-1])
        s.snap_ram_mb = 4608
        mb, tip = s.snapshot_advice(369_031_386, 2_400_000_000, 4)
        self.assertIsNone(tip); self.assertIn("passt komplett", logs[-1])
        s.snap_ram_mb = 2048                                                                # am Limit: nur noch Medium-Tipp
        mb, tip = s.snapshot_advice(369_031_386, 2_400_000_000, 4)
        self.assertIsNone(tip); self.assertIn("schnelleres Medium", logs[-1])
        s.snap_ram_mb = 512
        s.vname = "Int32"; s.last_flags = SC.TS_SNAPSHOT                                    # dicht: slots x 4 Byte
        mb, tip = s.snapshot_advice(1, 2_400_000_000, 4)
        self.assertAlmostEqual(mb, 2_400_000_000 * 4 / 1048576, 0); self.assertIsNotNone(tip)


class SnapshotRamLimit(unittest.TestCase):
    """Die PS5 vertraegt hoechstens 2048 MB Snapshot-RAM; ab 3072 MB meldet sie zu wenig Speicher."""

    def test_gui_offers_at_most_2048_mb_and_defaults_to_it(self):
        import ast
        src = open(os.path.join(os.path.dirname(__file__), "..", "tools_scan_gui.py"), encoding="utf-8").read()
        choices = next(ast.literal_eval(n.value) for n in ast.parse(src).body
                       if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "RAM_CHOICES")
        self.assertEqual(SC.MAX_SNAPSHOT_RAM_MB, 2048)
        self.assertLessEqual(max(choices.values()), SC.MAX_SNAPSHOT_RAM_MB)
        self.assertIn("list(RAM_CHOICES)[2]", src)                # Standard-Auswahl = 2048 MB
        self.assertEqual(list(choices.values())[2], 2048)

