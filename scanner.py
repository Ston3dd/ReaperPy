"""scanner.py – schnelle Memory-Scans (Cheat-Searcher-Engine) für ps5debug-NG."""
import socket
import struct
import threading
import time
from array import array

from ps5_client import PS5DebugClient, STATUS_SUCCESS, STATUS_ERROR, STATUS_DATA_NULL

SENT64 = 0xFFFFFFFFFFFFFFFF

CMD_SCAN_START  = 0xBDAACC01
CMD_SCAN_COUNT  = 0xBDAACC02
CMD_SCAN_GET    = 0xBDAACC03
CMD_TS_CAPS     = 0xBDAACC10
CMD_TS_START    = 0xBDAACC11
CMD_TS_COUNT    = 0xBDAACC12
CMD_TS_GET      = 0xBDAACC13
CMD_TS_END      = 0xBDAACC14
MAX_SNAPSHOT_RAM_MB = 2048     # mehr verkraftet die PS5 nicht: ab 3072 MB meldet sie "nicht genug Speicher"
CMD_TS_CONFIG   = 0xBDAACC15
CMD_TS_REGIONS  = 0xBDAACC16
CMD_TS_CANCEL   = 0xBDAACC17

TSE_SIMD, TSE_ALIASING, TSE_RESIDENT, TSE_SNAPSHOT, TSE_SEGMENTS, TSE_CONFIG = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
TSE_FIRST, TSE_PREVIOUS, TSE_PARALLEL, TSE_RESCAN_ALIAS, TSE_FLOAT_POLICY, TSE_COMPACT = 0x40, 0x80, 0x100, 0x200, 0x400, 0x800

TS_USE_ALIASING, TS_RESIDENT, TS_SNAPSHOT, TS_INCLUDE_ZEROS, TS_SEGMENTS = 0x01, 0x02, 0x04, 0x08, 0x10
TS_KEEP_FIRST, TS_KEEP_PREVIOUS, TS_PARALLEL, TS_RESCAN_ALIASING = 0x20, 0x40, 0x80, 0x100
TS_FLOAT_SIMPLE, TS_FLOAT_EXACT = 0x200, 0x400
FLOAT_EXP_SHIFT = 16

VTYPES = {
    "UInt8": (0, 1, "B"), "Int8": (1, 1, "b"),
    "UInt16": (2, 2, "H"), "Int16": (3, 2, "h"),
    "UInt32": (4, 4, "I"), "Int32": (5, 4, "i"),
    "UInt64": (6, 8, "Q"), "Int64": (7, 8, "q"),
    "Float": (8, 4, "f"), "Double": (9, 8, "d"),
}
CTYPES = {
    "Genau": (0, 1), "Ungefähr (Float)": (1, 1), "Größer als": (2, 1), "Kleiner als": (3, 1),
    "Zwischen": (4, 2), "Größer geworden": (5, 0), "Größer geworden um": (6, 1),
    "Kleiner geworden": (7, 0), "Kleiner geworden um": (8, 1), "Verändert": (9, 0),
    "Unverändert": (10, 0), "Unbekannter Startwert": (11, 0),
}
FIRST_ONLY = {"Unbekannter Startwert"}
NEXT_ONLY = {"Größer geworden", "Größer geworden um", "Kleiner geworden",
             "Kleiner geworden um", "Verändert", "Unverändert"}


class ScanError(RuntimeError):
    pass


class Cancelled(ScanError):
    pass


def encode_value(vname, text):
    _id, size, code = VTYPES[vname]
    t = text.strip().replace(",", ".") if code in "fd" else text.strip()
    if code in "fd":
        return struct.pack("<" + code, float(t))
    v = int(t, 0)
    bits = size * 8
    if code.isupper():
        if not 0 <= v < (1 << bits):
            raise ValueError(f"{vname}: Wert außerhalb Bereich")
    else:
        if not -(1 << (bits - 1)) <= v < (1 << (bits - 1)):
            raise ValueError(f"{vname}: Wert außerhalb Bereich")
    return struct.pack("<" + code, v)


def decode_value(vname, data):
    _id, size, code = VTYPES[vname]
    return struct.unpack("<" + code, bytes(data[:size]))[0]


def fmt_value(vname, data):
    v = decode_value(vname, data)
    if vname in ("Float", "Double"):
        return f"{v:.6g}"
    return str(v)


class _IO:
    def __init__(self, client, debug=False, log=None):
        self.c = client
        self.buf = b""
        self.debug = debug
        self.log = log or (lambda m: None)

    def recv(self, n):
        while len(self.buf) < n:
            chunk = self.c.sock.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise ConnectionError("Verbindung geschlossen")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def push(self, b):
        self.buf = b + self.buf

    def u32(self):
        return struct.unpack("<I", self.recv(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.recv(8))[0]

    def drain_progress(self, on_value, check=None, interval=0.1):
        """Fortschritts-Stream (u64-Werte bis SENT64) in grossen Bloecken lesen.  Das Payload blockiert, solange wir
        nicht mitlesen - deshalb kein Python-Aufruf je Meldung: on_value(letzter Wert) hoechstens alle `interval`
        Sekunden, check() je Block (darf abbrechen).  Bytes hinter SENT64 bleiben fuer die naechste Antwort im Puffer."""
        last_cb, last_v = 0.0, None
        while True:
            if len(self.buf) < 8:
                chunk = self.c.sock.recv(1 << 20)
                if not chunk:
                    raise ConnectionError("Verbindung geschlossen")
                self.buf += chunk
                continue
            n = len(self.buf) // 8
            vals = struct.unpack_from(f"<{n}Q", self.buf)
            try:
                k = vals.index(SENT64)
            except ValueError:
                k = -1
            if k >= 0:
                if k:
                    last_v = vals[k - 1]
                self.buf = self.buf[(k + 1) * 8:]
                if last_v is not None and on_value:
                    on_value(last_v)
                return last_v
            last_v = vals[-1]
            self.buf = self.buf[n * 8:]
            if check:
                check()
            now = time.monotonic()
            if on_value and now - last_cb >= interval:
                last_cb = now
                on_value(last_v)

    def send(self, b):
        self.c.sock.sendall(b)

    def pkt(self, cmd, data=b""):
        self.c._send_packet(cmd, data)

    def expect(self, what):
        st = self.u32()
        if self.debug:
            self.log(f"[scan] {what}: Status 0x{st:08X}")
        if st != STATUS_SUCCESS:
            raise ScanError(f"{what}: Status 0x{st:08X}")

    def skip_acks(self, what, limit=2):
        n = 0
        while n < limit:
            w = self.u32()
            if w == STATUS_SUCCESS:
                n += 1
                continue
            if w in (STATUS_ERROR, STATUS_DATA_NULL) or (w & 0xFFFFFFF0) == 0xF0000000:
                raise ScanError(f"{what}: Fehlerstatus 0x{w:08X}")
            self.push(struct.pack("<I", w))
            break
        return n

    def try_status(self, timeout=1.5):
        old = self.c.sock.gettimeout()
        self.c.sock.settimeout(timeout)
        try:
            return self.u32()
        except (socket.timeout, TimeoutError):
            return None
        finally:
            self.c.sock.settimeout(old)


class Scanner:
    def __init__(self, host, port, pid, log=None, debug=False):
        self.host, self.port, self.pid = host, port, pid
        self.log = log or (lambda m: None)
        self.debug = debug
        self.client = None
        self.io = None
        self.caps = None
        self.mode = "turbo"
        self.vname = "Int32"
        self.vsize = 4
        self.count = 0
        self.session = None
        self.first_scan_done = False
        self.last_flags = None
        self.payload_brand = ""
        self.snap_ram_mb = 512
        self.spill_dir = ""
        self.last_plan = None
        self.last_mbps = 0.0
        self.keep_first = False
        self.keep_prev = False
        self.cands = []
        self.cancelled = False
        self.lock = threading.RLock()

    def connect(self):
        """Connect, probe real TurboScan capabilities, then authenticate scans."""
        c = PS5DebugClient(self.host, self.port, timeout=10)
        try:
            version = c.connect()
            c.pid = self.pid

            # The scan commands require auth flag 0x02. Do this before creating
            # the buffered _IO wrapper so raw socket reads cannot bypass its buffer.
            if not c.authenticate(flags=2):
                detail = c.last_error or "unbekannter Fehler"
                raise ScanError(f"CMD_PROC_AUTH fehlgeschlagen: {detail}")

            io = _IO(c, self.debug, self.log)
            # CAPS is explicitly unauthenticated, but probing after auth is valid
            # and keeps all subsequent reply parsing on the same buffered reader.
            io.pkt(CMD_TS_CAPS)
            io.expect("TURBOSCAN_CAPS")
            cap_version, engines, threads, _reserved = struct.unpack("<IIII", io.recv(16))
            if cap_version < 1:
                raise ScanError(f"Nicht unterstützte TurboScan-CAPS-Version: {cap_version}")

            self.client = c
            self.io = io
            self.caps = {"version": cap_version, "engines": engines, "threads": threads}

            if not self.has(TSE_RESIDENT):
                raise ScanError(
                    f"Payload meldet keine serverseitigen Turbo-Ergebnisse (engines=0x{engines:08X}). "
                    "Prüfe, ob tatsächlich ps5debug-NG v1.3.2 geladen ist."
                )

            self.mode = "turbo"
            self._log_payload()
            self.log(
                f"[scan] Verbindung OK: Protokoll {version}; CAPS v{cap_version}; "
                f"engines=0x{engines:08X}; Threads={threads}; Scan-Auth aktiv; "
                "Suche serverseitig (PS5)"
            )
            return self.mode
        except Exception:
            c.close()
            self.client = None
            self.io = None
            self.caps = None
            raise

    def _log_payload(self):
        """Payload-Name/Version loggen (z.B. 'ps5debug-NG by Pharaoh2k v1.5.0') - Scan-Tempo haengt stark davon ab.
        Eigene Kurzverbindung: ein Fehler hier kann den Scan-Stream nie durcheinanderbringen."""
        try:
            c = PS5DebugClient(self.host, self.port, timeout=3)
            try:
                c.connect()
                brand = c.get_branding()
                fw = c.get_firmware_version()
            finally:
                c.close()
            self.payload_brand = brand
            self.log(f"[scan] Payload: {brand or '?'} | FW {fw >> 8}.{fw & 0xFF:02d}  ({fw:#06x})")
        except Exception as e:
            self.log(f"[scan] Payload-Version nicht lesbar ({e})")

    def close(self):
        try:
            if self.client and self.session in ("resident", "snapshot"):
                self.io.pkt(CMD_TS_END)
                self.io.try_status(0.5)
        except Exception:
            pass
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass

    def configure_snapshot(self, ram_mb=0, spill_dir=""):
        """CMD_PROC_TURBOSCAN_CONFIG (0xBDAACC15): wie viel vom Snapshot-Speicher im RAM bleibt (ram_mb; 0 = Standard
        512 MiB) und wohin der Rest ausgelagert wird (spill_dir, leer = /data).  Gilt global fuer die naechsten
        Snapshot-Scans.  Laut PROTOCOL.md liest/schreibt /data (verschluesselt) nur ~35-240 MB/s - bei grossen
        Snapshots ist das die Bremse."""
        if not self.has(TSE_CONFIG):
            raise ScanError("Dieses Payload kennt CMD_PROC_TURBOSCAN_CONFIG nicht (TSE_SNAPSHOT_CONFIG fehlt)")
        path = (spill_dir or "").encode("utf-8")
        if len(path) > 63:
            raise ScanError("Auslagerungs-Ordner: Pfad darf höchstens 63 Bytes lang sein")
        ram_mb = int(ram_mb)
        if not 0 <= ram_mb <= 0xFFFFFFFF:
            raise ScanError("Snapshot-RAM außerhalb des Bereichs")
        self._set_timeout(15)
        self.io.pkt(CMD_TS_CONFIG, struct.pack("<II", ram_mb, len(path)) + path)
        self.io.expect("CONFIG")
        self.snap_ram_mb = ram_mb or 512
        self.spill_dir = spill_dir or ""
        self.log(f"[scan] Snapshot-RAM: {self.snap_ram_mb} MB, Auslagerung nach {spill_dir or '/data (Standard)'}")

    def snapshot_advice(self, count, slots, vs):
        """Nach einem Snapshot-Scan: wie gross ist der Speicher, passt er in den RAM-Anteil?  -> (mb, tipp|None)"""
        compact = (self.vname in ("Float", "Double") and bool(self.last_flags and self.last_flags & TS_FLOAT_SIMPLE)
                   and self.has(TSE_COMPACT))
        mb = (count * (8 + vs) if compact else slots * vs) / 1048576
        ram = getattr(self, "snap_ram_mb", 512)
        art = "nur Überlebende, 8+%d Byte je Treffer" % vs if compact else "alle Speicherplätze, dicht"
        if mb <= ram:
            self.log(f"[scan] Snapshot ≈ {mb:.0f} MB ({art}) - passt komplett in den RAM-Anteil ({ram} MB)")
            return mb, None
        tip = min(int(mb * 1.05) + 1, MAX_SNAPSHOT_RAM_MB)
        if ram >= MAX_SNAPSHOT_RAM_MB:               # schon am Limit: mehr RAM geht nicht, nur ein schnelleres Medium hilft
            tip = None
            self.log(f"[scan] Snapshot ≈ {mb:.0f} MB ({art}); nur {ram} MB im RAM (PS5-Grenze {MAX_SNAPSHOT_RAM_MB} MB), "
                     f"≈{mb - ram:.0f} MB werden auf die Platte ausgelagert (langsam). Tipp: schnelleres Medium "
                     f"(M.2 / USB) wählen")
            return mb, tip
        self.log(f"[scan] Snapshot ≈ {mb:.0f} MB ({art}); nur {ram} MB im RAM, ≈{max(mb - ram, 0):.0f} MB werden auf die "
                 f"Platte ausgelagert (langsam). Tipp: Snapshot-RAM auf {tip} MB stellen (PS5-Grenze "
                 f"{MAX_SNAPSHOT_RAM_MB} MB, ab 3072 MB meldet die PS5 zu wenig Speicher) oder schnelleres Medium wählen")
        return mb, tip

    def speed_mode(self, opts=None):
        """Kurztext fuers Log: welche Beschleuniger das Payload anbietet / benutzt wurden."""
        c = self.caps or {}
        f = getattr(self, "last_flags", None)
        used = lambda bit: "ja" if f is not None and f & bit else "nein"
        can = lambda b: "ja" if self.has(b) else "nein"
        return (f"Payload kann: Parallel {can(TSE_PARALLEL)} (Threads={c.get('threads', '?')}), SIMD {can(TSE_SIMD)}, "
                f"Aliasing {can(TSE_ALIASING)}  |  ANGEFORDERT: Parallel {used(TS_PARALLEL)}, "
                f"Aliasing {used(TS_USE_ALIASING)}")

    def has(self, bit):
        return bool(self.caps and self.caps["engines"] & bit)

    def regions(self, scope="data", min_mbps=0, min_size=0x1000, report=False, pick=None):
        """Scanbare Regionen [(start, end)].  pick(maps_named) -> Startadressen: Bereichsfilter des Searchers
        (eboot.bin / Libs ausblenden, siehe regionfilter.py); ohne pick wird nichts zusaetzlich gefiltert."""
        allowed = None
        if pick is not None:
            named = self.client.get_maps_named()
            allowed = set(pick(named))
            maps = [(s, e, p) for s, e, p, _n in named]
        else:
            maps = self.client.get_maps()
        info = None
        if min_mbps or report:
            try:
                info = self._classify()
            except Exception as e:
                self.log(f"[scan] Regions-Messung nicht möglich ({e}) - scanne alles")
        slow = self._slow_regions(min_mbps, info) if (min_mbps and info is not None) else []
        out = []
        for s, e, p in maps:
            if e - s < min_size or not (p & 1):
                continue
            if scope == "data" and (not (p & 2) or (p & 4)):
                continue
            if scope == "rw" and not (p & 2):
                continue
            if any(cs <= s < ce for cs, ce in slow):
                continue
            if allowed is not None and s not in allowed:
                continue
            out.append((s, e))
        out.sort()
        if allowed is not None:
            self.log(f"[scan] Bereichsfilter: {len(out)} Regionen, {sum(e - s for s, e in out) / 1048576:.0f} MB")
        if report and info:
            self.speed_report(out, info)
        return out

    SPEED_BUCKETS = (100, 300, 600, 1000)

    def speed_report(self, regions, info):
        """Loggt, wie viele MB der gewählten Regionen mit welchem (vom Payload gemessenen) Lesetempo liegen und
        was das Auslassen langsamer Regionen kosten/sparen würde.  -> dict fuer Tests/GUI."""
        starts = sorted((a, b, mb) for a, b, _p, _f, mb, _r in info)
        keys = [a for a, _b, _m in starts]
        import bisect
        edges = self.SPEED_BUCKETS
        names = [f"< {edges[0]}"] + [f"{edges[i]}-{edges[i + 1]}" for i in range(len(edges) - 1)] + [f"≥ {edges[-1]}"]
        mbs, secs, unknown = [0.0] * len(names), [0.0] * len(names), 0.0
        for s0, e0 in regions:
            i = bisect.bisect_right(keys, s0) - 1
            size = (e0 - s0) / 1048576
            if i < 0 or not (starts[i][0] <= s0 < starts[i][1]) or starts[i][2] <= 0:
                unknown += size
                continue
            speed = starts[i][2]
            b = bisect.bisect_right(edges, speed)
            mbs[b] += size
            secs[b] += size / speed
        total_mb, total_s = sum(mbs) + unknown, sum(secs)
        parts = [f"{n} MB/s: {m:.0f} MB (≈{t:.0f} s)" for n, m, t in zip(names, mbs, secs) if m]
        if unknown:
            parts.append(f"unbekannt: {unknown:.0f} MB")
        self.log("[scan] Lesetempo (vom Payload gemessen): " + "; ".join(parts) + f"  -> geschätzte Lesezeit ≈ {total_s:.0f} s")
        hints, cm, cs = [], 0.0, 0.0
        for i, edge in enumerate(edges):
            cm, cs = cm + mbs[i], cs + secs[i]
            if cm and total_mb:
                hints.append(f"< {edge} MB/s auslassen: -{cm:.0f} MB ({100 * cm / total_mb:.1f} %), spart ≈{cs:.0f} s")
        if hints:
            self.log("[scan] Auswahl-Hilfe: " + " | ".join(hints))
        return {"names": names, "mb": mbs, "sec": secs, "unknown_mb": unknown, "total_s": total_s}

    def _classify(self):
        """0xBDAACC16: alle lesbaren Regionen mit gemessener Lesegeschwindigkeit."""
        io = self.io
        self._set_timeout(300)
        io.pkt(CMD_TS_REGIONS, struct.pack("<IIII", self.pid, 0, 0, 0))
        io.expect("REGIONS")
        n = io.u32()
        if n > 8192:
            raise ScanError(f"REGIONS: unsinnige Anzahl {n}")
        data = io.recv(n * 32) if n else b""
        io.expect("REGIONS final")
        return [struct.unpack_from("<QQIIII", data, i * 32) for i in range(n)]

    def _slow_regions(self, min_mbps, info=None):
        """[(start, end)] der Regionen, die langsamer als min_mbps gelesen werden
        (z.B. der GPU/Garlic-Block mit ~40 MB/s). Bei Fehlern: nichts auslassen."""
        if self.io is None:
            return []
        if info is None:
            try:
                info = self._classify()
            except Exception as e:
                self.log(f"[scan] Regions-Messung nicht möglich ({e}) - scanne alles")
                return []
        slow = [(s, e) for s, e, _prot, _flags, mbps, _r in info if 0 < mbps < min_mbps]
        if slow:
            mb = sum(e - s for s, e in slow) / 1048576
            self.log(f"[scan] {len(slow)} langsame Region(en) ausgelassen ({mb:.0f} MB, < {min_mbps} MB/s)")
        return slow

    def _flags(self, opts, vname, ctype, segments=False, resident=True, snapshot=False,
               first=False):
        f = 0
        if first and opts.get("aliasing") and self.has(TSE_ALIASING):
            f |= TS_USE_ALIASING          # nur im ersten Scan: Lesen per Page-Aliasing
        if resident:
            f |= TS_RESIDENT
        if snapshot:
            f |= TS_SNAPSHOT
        # PROTOCOL.md: TS_PARALLEL_COMPARE wirkt nur bei START + Aliasing + exaktem Vergleich im Streaming-Modus
        # (kein Snapshot) und wird sonst ignoriert - nur dann anfordern, damit das Log nichts Falsches behauptet.
        if (opts.get("parallel", True) and self.has(TSE_PARALLEL) and not snapshot and ctype == "Genau"
                and f & TS_USE_ALIASING):
            f |= TS_PARALLEL
        # Nur nach erfolgreichem CAPS-Probe aktivieren; bei v1.3.2 scannt das
        # die ausgewählten Bereiche einzeln statt ungültige Lücken mitzulesen.
        if segments:
            f |= TS_SEGMENTS
        if vname in ("Float", "Double") and self.has(TSE_FLOAT_POLICY):
            if ctype == "Genau":
                f |= TS_FLOAT_EXACT
            elif opts.get("float_simple", True):
                f |= TS_FLOAT_SIMPLE | (int(opts.get("float_exp", 11)) << FLOAT_EXP_SHIFT)
        return f

    def first_scan(self, vname, ctype, text1, text2, regions, opts=None, progress=None):
        with self.lock:
            opts = opts or {}
            self.cancelled = False
            self.vname = vname
            self.vsize = VTYPES[vname][1]
            self.count, self.cands = 0, []
            if self.session in ("resident", "snapshot"):
                self._end_session()
            if not regions:
                raise ScanError("Keine Speicherregionen ausgewählt")
            vals = self._values(vname, ctype, text1, text2)
            unknown = ctype in FIRST_ONLY
            segs = self._normalise_regions(regions)
            small_limit = int(opts.get("min_region") or 0)
            small = [(a, b) for a, b in segs if b - a < 256 * 1024]
            self.log(f"[scan] {len(regions)} Regionen -> {len(segs)} Segmente nach Zusammenfassen; "
                     f"{len(small)} davon < 256 KB ({sum(b - a for a, b in small) / 1048576:.0f} MB)")
            if small_limit:
                kept = [(a, b) for a, b in segs if b - a >= small_limit]
                self.log(f"[scan] kleine Segmente (< {small_limit // 1024} KB) ausgelassen: "
                         f"{len(segs) - len(kept)} Stück, {sum(b - a for a, b in segs if b - a < small_limit) / 1048576:.0f} MB")
                segs = kept
                if not segs:
                    raise ScanError("Nach dem Auslassen kleiner Segmente bleibt nichts übrig")
            regions = segs
            if unknown and opts.get("snap_ram_mb") is not None:
                try:
                    self.configure_snapshot(opts["snap_ram_mb"], opts.get("spill_dir", ""))
                except ScanError as e:
                    self.log(f"[scan] Snapshot-Einstellung nicht gesetzt ({e}) - Standard bleibt aktiv")
            t0 = time.time()
            n = self._turbo_first(vname, ctype, vals, regions, opts, progress, unknown)
            self.count = n
            self.first_scan_done = True
            dt = max(time.time() - t0, 1e-6)
            mb = sum(e - s for s, e in self._normalise_regions(regions)) / 1048576
            self.last_mbps = mb / dt
            self.log(f"[scan] erster Scan: {n} Treffer in {dt:.1f}s ({self.session}) - {mb:.0f} MB = "
                     f"{mb / dt:.0f} MB/s; {self.speed_mode()}")
            if unknown and self.last_plan:
                self.snapshot_advice(n, self.last_plan[0], self.vsize)
            return n

    def _values(self, vname, ctype, t1, t2):
        need = CTYPES[ctype][1]
        v = b""
        if need >= 1:
            v += encode_value(vname, t1)
        if need >= 2:
            v += encode_value(vname, t2)
        return v

    def _normalise_regions(self, regions):
        """Validate ranges and split any region whose length exceeds a wire u32."""
        out = []
        max_len = 0xFFFFFFFF
        merged = []
        for start, end in sorted(regions):
            if start < 0 or end <= start:
                continue
            if merged and start <= merged[-1][1]:            # lueckenlos benachbart/ueberlappend -> ein Segment
                if end > merged[-1][1]:
                    merged[-1][1] = end
            else:
                merged.append([start, end])
        for start, end in merged:
            pos = start
            while pos < end:
                stop = min(end, pos + max_len)
                out.append((pos, stop))
                pos = stop
        if len(out) > 1_048_576:
            raise ScanError(f"Zu viele Scan-Segmente: {len(out)}")
        return out

    def _segments(self, regions):
        regions = self._normalise_regions(regions)
        return struct.pack("<I", len(regions)) + b"".join(
            struct.pack("<QI", start, end - start) for start, end in regions)

    def _turbo_first(self, vname, ctype, vals, regions, opts, progress, unknown):
        io = self.io
        vid, vs, _ = VTYPES[vname]
        cid = CTYPES[ctype][0]
        regions = self._normalise_regions(regions)
        if not regions:
            raise ScanError("Nach der Bereichsprüfung sind keine gültigen Speicherregionen übrig")

        need_engine = TSE_SNAPSHOT if unknown else TSE_RESIDENT
        if not self.has(need_engine):
            label = "Snapshot" if unknown else "serverseitige Ergebnismenge"
            raise ScanError(f"TurboScan kann nicht starten: CAPS meldet keine Unterstützung für {label}")

        use_segments = len(regions) > 1
        if use_segments and not self.has(TSE_SEGMENTS):
            raise ScanError(
                "Mehrere getrennte Speicherregionen ausgewählt, aber das Payload meldet keine "
                "Multi-Segment-Unterstützung. Ein zusammengezogener Bereich wäre unsicher, "
                "weil er ungültige Speicherlücken überbrücken kann."
            )

        flags = self._flags(
            opts, vname, ctype, segments=use_segments,
            resident=not unknown, snapshot=unknown, first=True
        )
        self.last_flags = flags
        s0 = regions[0][0]
        total_len = regions[0][1] - regions[0][0]
        if use_segments:
            # In segment mode address/length are ignored by the v1.3.2 server.
            total_len = min(regions[-1][1] - s0, 0xFFFFFFFF)

        pkt = struct.pack(
            "<IQIBBBII", self.pid, s0, total_len,
            vid, cid, vs, len(vals), flags
        )
        payload = vals + (self._segments(regions) if use_segments else b"")
        self._set_timeout(1800)
        io.pkt(CMD_TS_START, pkt)
        if payload:
            io.send(payload)
        io.skip_acks("START", 2)

        if unknown:
            slots, total = struct.unpack("<QQ", io.recv(16))
            self.last_plan = (slots, total)
            def _chk():
                if self.cancelled:
                    raise Cancelled("abgebrochen")
            io.drain_progress(
                (lambda v: progress(min(1.0, v / max(total, 1)), "Snapshot auf der PS5 ...")) if progress else None,
                _chk)
            _chk()
            ok, count = struct.unpack("<IQ", io.recv(12))
            io.expect("START final")
            if not ok:
                self.session = None
                raise ScanError(
                    f"PS5 hat den Turbo-Snapshot abgelehnt (Slots={slots}, Bytes={total}). "
                    "Prüfe freien Speicher bzw. CAPS-Snapshot-Unterstützung."
                    + (f" Auslagerungs-Ordner '{self.spill_dir}' gesetzt - existiert er (Laufwerk eingesteckt) und ist "
                       "Platz frei? Sonst 'intern /data' wählen." if self.spill_dir else "")
                )
            self.session = "snapshot"
            return count

        stored, count = struct.unpack("<IQ", io.recv(12))
        if stored:
            io.expect("START final")
            self.session = "resident"
            return count
        # Der Server hat die Ergebnismenge NICHT abgelegt (Puffergrenze) und streamt sie nun
        # komplett hinterher. Statt Gigabyte zu lesen: Verbindung verwerfen (wird beim
        # nächsten Scan automatisch neu aufgebaut) - sonst wäre der Stream desynchronisiert.
        self._abort_connection()
        raise ScanError(
            f"Zu viele Treffer für die serverseitige Ergebnismenge (Treffer={count}). "
            "Bereich einschränken (z.B. 'Daten' statt 'Alles') oder einen selteneren Wert suchen."
        )

    def next_scan(self, ctype, text1, text2, opts=None, progress=None):
        with self.lock:
            opts = opts or {}
            self.cancelled = False
            if not self.first_scan_done:
                raise ScanError("Erst einen ersten Scan machen")
            vals = self._values(self.vname, ctype, text1, text2)
            t0 = time.time()
            before = self.count
            n = self._turbo_count(ctype, vals, opts, progress)
            self.count = n
            self.log(f"[scan] nächster Scan: {before} -> {n} Treffer in {time.time() - t0:.1f}s")
            return n

    def _turbo_count(self, ctype, vals, opts, progress):
        io = self.io
        vid, vs, _ = VTYPES[self.vname]
        cid = CTYPES[ctype][0]
        flags = self._flags(opts, self.vname, ctype, resident=True)
        if opts.get("aliasing") and self.has(TSE_RESCAN_ALIAS):
            flags |= TS_RESCAN_ALIASING
        if not self.has(TSE_RESIDENT):
            raise ScanError("CAPS meldet keine serverseitigen Turbo-Ergebnisse")
        pkt = struct.pack("<IQBBII", self.pid, 0, vid, cid, len(vals), flags)
        self._set_timeout(1800)
        io.pkt(CMD_TS_COUNT, pkt)
        if vals:
            io.send(vals)
        io.skip_acks("COUNT", 2)
        total = max(self.count, 1)

        def _chk():
            if self.cancelled:
                raise Cancelled("abgebrochen")
        io.drain_progress((lambda v: progress(min(1.0, v / total), "Vergleiche ...")) if progress else None, _chk)
        _chk()
        new = io.u64()
        io.expect("COUNT final")
        return new

    def results(self, start=0, count=500):
        with self.lock:
            count = max(0, min(count, self.count - start))
            if count == 0:
                return []
            return self._turbo_get(start, count)

    def _turbo_get_raw(self, start, count):
        io = self.io
        vs = self.vsize
        self._set_timeout(120)
        io.pkt(CMD_TS_GET, struct.pack("<III", start, count, 0))
        io.expect("GET")
        hdr = io.u32()
        n = hdr & 0x7FFFFFFF
        three = bool(hdr & 0x80000000)
        rec = 8 + (3 if three else 2) * vs
        data = io.recv(n * rec) if n else b""
        io.expect("GET final")
        return data, rec, n, three

    def _turbo_get(self, start, count):
        vs = self.vsize
        data, rec, n, three = self._turbo_get_raw(start, count)
        out = []
        for i in range(n):
            o = i * rec
            a = struct.unpack_from("<Q", data, o)[0]
            out.append({"addr": a, "cur": data[o + 8:o + 8 + vs],
                        "prev": data[o + 8 + vs:o + 8 + 2 * vs],
                        "first": data[o + 8 + 2 * vs:o + 8 + 3 * vs] if three else None})
        return out

    def _abort_connection(self):
        """Verbindung hart schließen (Stream-Zustand unbekannt). Der Aufrufer baut bei Bedarf
        einen neuen Scanner auf (ScanTab._ensure prüft client/sock)."""
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        self.client = None
        self.io = None
        self.session = None
        self.count = 0
        self.first_scan_done = False

    def dump_u64(self, progress=None, cap=8_000_000, page=65536):
        """Holt alle Treffer eines UInt64-Scans als (Adressen, Werte) - für den Pointer-Scanner."""
        with self.lock:
            if self.vsize != 8:
                raise ScanError("dump_u64 braucht einen UInt64-Scan")
            total = min(self.count, cap)
            addrs, vals = array("Q"), array("Q")
            pos = 0
            while pos < total:
                if self.cancelled:
                    raise Cancelled("abgebrochen")
                data, rec, got, three = self._turbo_get_raw(pos, min(page, total - pos))
                if not got:
                    break
                fmt = "<QQQQ" if three else "<QQQ"          # addr, current, previous[, first]
                for row in struct.iter_unpack(fmt, data[:got * rec]):
                    addrs.append(row[0])
                    vals.append(row[1])
                pos += got
                if progress:
                    progress(pos / max(total, 1), f"Lese Zeiger {pos}/{total}")
            return addrs, vals

    def reset(self):
        with self.lock:
            if self.session in ("resident", "snapshot"):
                self._end_session()
            self.session = None
            self.count = 0
            self.cands = []
            self.first_scan_done = False

    def _end_session(self):
        try:
            self.io.pkt(CMD_TS_END)
            self.io.try_status(2.0)
        except Exception:
            pass
        self.session = None

    def _set_timeout(self, seconds):
        try:
            self.client.sock.settimeout(seconds)
        except Exception:
            pass

    def cancel(self):
        self.cancelled = True
        try:
            c = PS5DebugClient(self.host, self.port, timeout=5)
            c.connect()
            c.pid = self.pid
            c._send_packet(CMD_TS_CANCEL, struct.pack("<I", self.pid))
            c._recv_status()
            c.close()
        except Exception as e:
            self.log(f"[scan] Abbruch: {e}")