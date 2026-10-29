"""Test von ps5_more gegen einen kleinen Fake-Server (Protokoll nach PROTOCOL.md)."""
import os, socket, struct, sys, threading, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ps5_client as C, ps5_more as M

OK = struct.pack("<I", C.STATUS_SUCCESS)


def rx(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c: raise EOFError
        b += c
    return b


class Fake(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.srv = socket.socket(); self.srv.bind(("127.0.0.1", 0)); self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.writes, self.calls = [], []
        self.mem = {0x1000: 0x2000, 0x2008: 0x3000}      # slot -> wert
    def run(self):
        s, _ = self.srv.accept()
        try:
            while True:
                magic, cmd, ln = struct.unpack("<III", rx(s, 12))
                body = rx(s, ln) if ln else b""
                if cmd == M.CMD_FOREGROUND:
                    s.sendall(OK + struct.pack("<I16s64s40s16s", 77, b"CUSA12345", b"cid", b"Mein Spiel", b"01.05"))
                elif cmd == M.CMD_WRITE_MULTI:
                    pid, n, st = struct.unpack("<III", body)
                    s.sendall(OK)
                    for _ in range(n):
                        a, l = struct.unpack("<QI", rx(s, 12)); self.writes.append((a, rx(s, l)))
                    if st: s.sendall(bytes(n))
                    s.sendall(OK)
                elif cmd == M.CMD_PROC_CALL:
                    f = struct.unpack("<IQQQQQQQQ", body); self.calls.append(f)
                    s.sendall(OK + struct.pack("<IQ", f[0], sum(f[3:])))
                elif cmd == M.CMD_PTRSCAN:
                    pid, alias, mo, nseg, nfr = struct.unpack("<IIQII", body)
                    s.sendall(OK)
                    segs = [struct.unpack("<QQ", rx(s, 16)) for _ in range(nseg)]
                    fr = [struct.unpack("<Q", rx(s, 8))[0] for _ in range(nfr)]
                    s.sendall(OK)
                    hits = [(sl, v) for sl, v in self.mem.items()
                            if any(a <= sl < a + n for a, n in segs) and any(v <= f <= v + mo for f in fr)]
                    s.sendall(struct.pack("<I", 0xFFFFFFFF) + struct.pack("<QQ", 5, 10))
                    if hits:
                        s.sendall(struct.pack("<I", len(hits)) + b"".join(struct.pack("<QQ", *h) for h in hits))
                    s.sendall(struct.pack("<I", 0) + struct.pack("<QQ", len(hits), 4096) + struct.pack("<I", 0) + OK)
        except EOFError:
            pass
        finally:
            s.close()


class T(unittest.TestCase):
    def setUp(self):
        self.f = Fake(); self.f.start()
        self.c = C.PS5DebugClient("127.0.0.1", self.f.port)
        self.c.sock = socket.create_connection(("127.0.0.1", self.f.port)); self.c.pid = 77
        self.c.authenticate = lambda *a, **k: True
        self.pool = 0x70000000
        self.c.allocate_memory = lambda n: self.pool
        self.c.write_memory = lambda a, d: self.f.writes.append((a, bytes(d)))
    def tearDown(self):
        self.c.sock.close()
        self.f.join(2)                  # Server-Thread beenden lassen, erst danach den Listen-Socket schliessen
        self.f.srv.close()

    def test_foreground(self):
        self.assertEqual(M.foreground_app(self.c), (77, "CUSA12345", "Mein Spiel", "01.05"))

    def test_write_multi(self):
        M.write_multi(self.c, [(0x10, b"\x90\x90"), (0x20, b"\xC3")])
        self.assertEqual(self.f.writes, [(0x10, b"\x90\x90"), (0x20, b"\xC3")])
        self.assertEqual(M.write_multi(self.c, [(0x30, b"AB")], want_status=True), b"\x00")

    def test_call_and_trampoline_cache(self):
        r = M.call(self.c, 0x500000, 1, 2, 3, gap=0)
        entry = self.f.calls[0][2]
        self.assertEqual(entry, self.pool)                       # Aufruf geht ueber Trampolin
        self.assertIn((self.pool, M.build_trampoline(0x500000)), self.f.writes)
        self.assertEqual(r, 1 + 2 + 3)                           # Fake: Summe der Argumente
        M.call(self.c, 0x500000, gap=0)
        self.assertEqual(self.f.calls[1][2], self.pool)          # gleiches Ziel -> gleicher Slot
        M.call(self.c, 0x600000, gap=0)
        self.assertEqual(self.f.calls[2][2], self.pool + M.TRAMP_SLOT)
        M.call(self.c, 0x600000, safe=False, gap=0)
        self.assertEqual(self.f.calls[3][2], 0x600000)

    def test_ptrscan(self):
        hits, scanned, st = M.ptrscan_level(self.c, [(0x1000, 0x2000)], [0x2010], 0x20)
        self.assertEqual(hits, [(0x1000, 0x2000)]); self.assertEqual(st, 0)

    def test_trampoline_bytes(self):
        t = M.build_trampoline(0x1122334455667788)
        self.assertEqual(len(t), M.TRAMP_SLOT)
        self.assertIn(struct.pack("<Q", 0x1122334455667788), t)
        self.assertEqual(t.rstrip(b"\xCC")[-1], 0xC3)


if __name__ == "__main__":
    unittest.main()
