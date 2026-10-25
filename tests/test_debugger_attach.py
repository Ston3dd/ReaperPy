"""Debugger-Attach gegen einen Fake-PS5 (mehrere Verbindungen, Rueckkanal wie bei ps5debug-NG)."""

import os
import socket
import struct
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import debugger as D
import ps5_ext as X
from ps5_client import STATUS_SUCCESS, PS5DebugClient

OK = struct.pack("<I", STATUS_SUCCESS)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def rx(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError
        b += c
    return b


class BadBind(socket.socket):
    """Socket, dessen bind() wie unter Windows (TIME_WAIT / SO_EXCLUSIVEADDRUSE) scheitert."""

    def __init__(self, code, text):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self._err = (code, text)

    def bind(self, addr):
        raise OSError(*self._err)


class FakePS5(threading.Thread):
    """Beantwortet VERSION / DEBUG_ATTACH / DEBUG_DETACH.  attach_results: Liste von Status-Woertern."""

    def __init__(self, listener_port, attach_results):
        super().__init__(daemon=True)
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        self.listener_port = listener_port
        self.attach_results = list(attach_results)
        self.detaches = 0
        self.attaches = 0
        self.back = []
        self.cmds = []
        self.conns = []
        self.refuse = False
        self._stop = False

    def run(self):
        while not self._stop:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            if self.refuse:
                conn.close()
                continue
            self.conns.append(conn)
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, s):
        try:
            while True:
                _magic, cmd, ln = struct.unpack("<III", rx(s, 12))
                if ln:
                    rx(s, ln)
                self.cmds.append(cmd)
                if cmd == 0xBD000001:  # VERSION
                    s.sendall(struct.pack("<I", 4) + b"1.3\x00")
                elif cmd == X.CMD_DEBUG_ATTACH:
                    self.attaches += 1
                    status = self.attach_results.pop(0) if self.attach_results else STATUS_SUCCESS
                    if status == STATUS_SUCCESS and self.listener_port:
                        back = socket.create_connection(("127.0.0.1", self.listener_port), timeout=2)
                        self.back.append(back)
                    s.sendall(struct.pack("<I", status))
                elif cmd == X.CMD_DEBUG_DETACH:
                    self.detaches += 1
                    s.sendall(OK)
                else:
                    s.sendall(OK)
        except (EOFError, OSError):
            pass
        finally:
            s.close()

    def close(self):
        self._stop = True
        self.srv.close()
        for b in self.back:
            b.close()


class AttachTests(unittest.TestCase):
    def setUp(self):
        self.lp = free_port()
        self.logs = []
        self.fakes = []

    def tearDown(self):
        for f in self.fakes:
            f.close()

    def fake(self, results):
        f = FakePS5(self.lp, results)
        f.start()
        self.fakes.append(f)
        return f

    def session(self, fake):
        s = D.DebugSession("127.0.0.1", fake.port, 77, on_log=self.logs.append, listener_port=self.lp)
        s.retry_delay = 0
        return s

    def port_is_free(self):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # TIME_WAIT-Reste zaehlen nicht als belegt
        try:
            s.bind(("127.0.0.1", self.lp))
            s.listen(1)  # nur ein aktiv lauschender Socket macht den Port wirklich "belegt"
            return True
        except OSError:
            return False
        finally:
            s.close()

    def test_attach_detach_attach_again_immediately(self):
        fake = self.fake([])
        for _ in range(2):  # zweiter Attach direkt nach Detach darf nicht an Port 755 scheitern
            sess = self.session(fake)
            sess.attach()
            self.assertTrue(sess.attached)
            self.assertTrue(sess.listener.connected.is_set())
            sess.detach()
            self.assertFalse(sess.attached)
        self.assertEqual(fake.detaches, 2)

    def test_borrowed_main_connection_is_used_and_stays_open(self):
        fake = self.fake([])
        main = PS5DebugClient("127.0.0.1", fake.port)
        main.connect()
        sess = D.DebugSession("127.0.0.1", fake.port, 77, on_log=self.logs.append, listener_port=self.lp, client=main)
        sess.attach()
        self.assertIs(sess.client, main)
        self.assertEqual(fake.attaches, 1)
        sess.detach()
        self.assertIsNotNone(main.sock)  # Hauptverbindung nicht geschlossen
        self.assertTrue(main._recv_status is not None and X._status_cmd(main, 0xBDAACC06) == STATUS_SUCCESS)
        # nach Fehlschlag bleibt sie ebenfalls offen
        with mock.patch.object(X, "dbg_attach", side_effect=TimeoutError("t")):
            with self.assertRaises(D.DebugError):
                sess.attach()
        self.assertIsNotNone(main.sock)
        self.assertTrue(self.port_is_free())
        main.close()

    def test_already_debugged_is_recovered(self):
        fake = self.fake([0xF0000004, STATUS_SUCCESS])
        sess = self.session(fake)
        sess.attach()
        self.assertTrue(sess.attached)
        self.assertEqual(fake.attaches, 2)
        self.assertGreaterEqual(fake.detaches, 1)  # alter Zustand wurde zuerst geloest
        self.assertTrue(any("bereits debuggt" in m for m in self.logs))
        sess.detach()

    def test_permanent_already_debugged_gives_clear_error_and_frees_port(self):
        fake = self.fake([0xF0000004, 0xF0000004])
        sess = self.session(fake)
        with self.assertRaises(D.DebugError) as ctx:
            sess.attach()
        self.assertIn("debuggt", str(ctx.exception))
        self.assertFalse(sess.attached)
        self.assertTrue(self.port_is_free())

    def test_other_status_frees_everything(self):
        fake = self.fake([0xF0000001])
        sess = self.session(fake)
        with self.assertRaises(D.DebugError) as ctx:
            sess.attach()
        self.assertIn("0xF0000001", str(ctx.exception))
        self.assertTrue(self.port_is_free())

    def test_timeout_mentions_firewall_and_frees_port(self):
        fake = self.fake([])
        sess = self.session(fake)
        with mock.patch.object(X, "dbg_attach", side_effect=TimeoutError("timed out")):
            with self.assertRaises(D.DebugError) as ctx:
                sess.attach()
        self.assertIn("Firewall", str(ctx.exception))
        self.assertTrue(self.port_is_free())
        sess.attach()  # und danach geht es sofort wieder
        self.assertTrue(sess.attached)
        sess.detach()

    def test_busy_port_gives_clear_error(self):
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", self.lp))
        blocker.listen(1)
        try:
            fake = self.fake([])
            sess = self.session(fake)
            with self.assertRaises(D.DebugError) as ctx:
                sess.attach()
            self.assertIn("nicht verfügbar", str(ctx.exception))
        finally:
            blocker.close()
        time.sleep(0.05)

    def test_windows_exclusive_bind_falls_back_when_nobody_listens(self):
        """Windows: SO_EXCLUSIVEADDRUSE scheitert an TIME_WAIT -> Fallback, solange niemand lauscht."""
        real = X.InterruptListener._make_socket

        def fake_make(mode):
            if mode == "exclusive":
                return BadBind(10013, "Zugriff verweigert (TIME_WAIT)")
            return real("reuse")

        with mock.patch.object(X.os, "name", "nt"), mock.patch.object(
            X.InterruptListener, "_make_socket", staticmethod(fake_make)
        ):
            lst = X.InterruptListener(lambda p: None, port=self.lp)
            lst.close()

    def test_windows_fallback_refuses_when_port_really_taken(self):
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", self.lp))
        blocker.listen(1)
        real = X.InterruptListener._make_socket

        def fake_make(mode):
            if mode == "exclusive":
                return BadBind(10048, "belegt")
            return real("reuse")

        try:
            with mock.patch.object(X.os, "name", "nt"), mock.patch.object(
                X.InterruptListener, "_make_socket", staticmethod(fake_make)
            ):
                with self.assertRaises(OSError):
                    X.InterruptListener(lambda p: None, port=self.lp, host="127.0.0.1")
        finally:
            blocker.close()


class KeepAliveTests(unittest.TestCase):
    def setUp(self):
        self.lp = free_port()
        self.fake = FakePS5(self.lp, [])
        self.fake.start()
        self.states, self.logs = [], []

    def tearDown(self):
        self.fake.close()

    def session(self, **kw):
        s = D.DebugSession("127.0.0.1", self.fake.port, 1234, on_log=self.logs.append, on_state=self.states.append,
                           listener_port=self.lp, **kw)
        s.keepalive_s = 0.05
        return s

    def wait(self, cond, t=5.0):
        end = time.time() + t
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.02)
        return False

    def test_idle_debug_connection_gets_pings(self):
        s = self.session()
        s.attach()
        try:
            n0 = self.fake.cmds.count(0xBD000000 + 0) if False else len(self.fake.cmds)
            self.assertTrue(self.wait(lambda: len(self.fake.cmds) > n0 + 3))      # ohne Keep-Alive blieb die Verbindung still
            self.assertEqual(self.states[:1], ["attached"])
        finally:
            s.detach()

    def test_dropped_debug_connection_is_rebuilt_with_breakpoints(self):
        s = self.session()
        s.attach()
        try:
            s.set_breakpoint(2, 0x401000)
            s.set_watchpoint(1, 0x7000, 4, 1)
            first = self.fake.conns[0]
            n_bp = self.fake.cmds.count(X.CMD_DEBUG_SET_BREAKPOINT)
            first.shutdown(socket.SHUT_RDWR)                                        # PS5/Netz kappt die Debug-Verbindung
            first.close()
            self.assertTrue(self.wait(lambda: s.reconnects == 1), self.logs)
            self.assertEqual(self.states, ["attached", "reconnecting", "attached"])
            self.assertEqual(self.fake.attaches, 2)
            self.assertTrue(self.wait(lambda: self.fake.cmds.count(X.CMD_DEBUG_SET_BREAKPOINT) > n_bp))   # Breakpoint neu gesetzt
            self.assertIn(X.CMD_DEBUG_SET_WATCHPOINT, self.fake.cmds)
            self.assertTrue(s.attached)
            self.assertTrue(s.health()["debug_ping"])
            self.assertTrue(any("wiederhergestellt" in m for m in self.logs))
        finally:
            s.detach()

    def test_rebuild_failure_reports_lost(self):
        s = self.session()
        s.keepalive_misses = 1
        s.attach()
        self.fake.refuse = True                                                     # PS5 komplett weg
        for c in list(self.fake.conns):
            try:
                c.shutdown(socket.SHUT_RDWR)
                c.close()
            except OSError:
                pass
        self.assertTrue(self.wait(lambda: "lost" in self.states, 15), (self.states, self.logs))
        self.assertFalse(s.attached)
        s.detach()

    def test_borrowed_connection_reports_lost_instead_of_rebuilding(self):
        main = PS5DebugClient("127.0.0.1", self.fake.port)
        main.connect()
        main.pid = 1234
        s = self.session(client=main)
        s.attach()
        for c in list(self.fake.conns):
            c.shutdown(socket.SHUT_RDWR)
            c.close()
        self.assertTrue(self.wait(lambda: "lost" in self.states, 5), self.states)
        self.assertEqual(s.reconnects, 0)
        s.detach()

    def test_detach_stops_keepalive_and_health_reports_back_channel(self):
        s = self.session()
        s.attach()
        h = s.health()
        self.assertTrue(h["debug_ping"])
        self.assertIsNone(h["main_ping"])
        s.detach()
        self.assertIsNone(s._ka_thread)
        self.assertEqual(self.states[-1], "detached")
        n = len(self.fake.cmds)
        time.sleep(0.3)
        self.assertEqual(len(self.fake.cmds), n)                                     # nach Detach keine Pings mehr


# ---------------------------------------------------------------------------------------------
# Treffer / WEITER / STEP wie im PS5 Debug Toolkit (Server macht den Breakpoint-Schritt selbst)
# ---------------------------------------------------------------------------------------------
def make_packet(lwpid, rip, rsp=0x7FFF0000, signal=5, dr6=0):
    buf = bytearray(X.INTERRUPT_PACKET_SIZE)
    struct.pack_into("<II", buf, 0, lwpid, (signal << 8) | 0x7F)
    regs = {n: 0 for n in X._REG_NAMES}
    regs["rip"], regs["rsp"] = rip, rsp
    buf[0x30:0x30 + X.REGS_SIZE] = X.pack_regs(regs)
    struct.pack_into("<Q", buf, 0x420 + 6 * 8, dr6)
    return bytes(buf)


class SessionFake(FakePS5):
    """Wie FakePS5, kennt aber Register, CONTINUE und STEP und kann Ereignisse auf dem Rueckkanal senden."""

    def __init__(self, listener_port):
        super().__init__(listener_port, [])
        self.live_rip = {}            # lwpid -> RIP, den GETREGS liefert
        self.on_step = None           # callable(lwpid) -> sendet Ereignis
        self.continues = 0

    def send_event(self, pkt):
        self.back[-1].sendall(pkt)

    def _serve(self, s):
        try:
            while True:
                _m, cmd, ln = struct.unpack("<III", rx(s, 12))
                body = rx(s, ln) if ln else b""
                self.cmds.append(cmd)
                if cmd == 0xBD000001:
                    s.sendall(struct.pack("<I", 4) + b"1.3\x00")
                elif cmd == X.CMD_DEBUG_ATTACH:
                    self.attaches += 1
                    self.back.append(socket.create_connection(("127.0.0.1", self.listener_port), timeout=2))
                    s.sendall(OK)
                elif cmd == X.CMD_DEBUG_GETREGS:
                    lw = struct.unpack("<I", body[:4])[0]
                    regs = {n: 0 for n in X._REG_NAMES}
                    regs["rip"] = self.live_rip.get(lw, 0)
                    s.sendall(OK + X.pack_regs(regs))
                elif cmd == 0xBDAA0002:
                    _pid, _addr, n = struct.unpack("<IQI", body[:16])
                    s.sendall(OK + b"\x90" * n)
                elif cmd == X.CMD_DEBUG_CONTINUE:
                    self.continues += 1
                    s.sendall(OK)
                elif cmd == X.CMD_DEBUG_STEP_THREAD:
                    lw = struct.unpack("<I", body[:4])[0]
                    s.sendall(OK)
                    if self.on_step:
                        self.on_step(lw)
                elif cmd == X.CMD_DEBUG_DETACH:
                    self.detaches += 1
                    s.sendall(OK)
                else:
                    s.sendall(OK)
        except (EOFError, OSError):
            pass
        finally:
            s.close()


class HitTests(unittest.TestCase):
    def setUp(self):
        self.lp = free_port()
        self.fake = SessionFake(self.lp)
        self.fake.start()
        self.hits, self.logs = [], []
        self.s = D.DebugSession("127.0.0.1", self.fake.port, 77, on_hit=self.hits.append,
                                on_log=self.logs.append, listener_port=self.lp)
        self.s.keepalive_s = 60
        self.s.attach()

    def tearDown(self):
        self.s.detach()
        self.fake.close()

    def wait(self, cond, t=3.0):
        end = time.time() + t
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.02)
        return False

    def hit_at(self, addr, lwpid=5, live=None):
        self.fake.live_rip[lwpid] = addr if live is None else live
        self.fake.send_event(make_packet(lwpid, addr))
        self.assertTrue(self.wait(lambda: self.hits))
        return self.hits[-1]

    def test_hit_rip_equals_breakpoint_address(self):
        self.s.set_breakpoint(0, 0x401000)
        h = self.hit_at(0x401000)
        self.assertEqual((h["kind"], h["index"], h["addr"]), ("BP", 0, 0x401000))
        self.assertFalse(h["prestepped"])

    def test_hit_rip_behind_int3_is_still_recognised(self):
        self.s.set_breakpoint(1, 0x402000)
        h = self.hit_at(0x402001)
        self.assertEqual((h["kind"], h["addr"]), ("BP", 0x402000))

    def test_resume_is_a_plain_continue_without_register_writes(self):
        self.s.set_breakpoint(0, 0x401000)
        self.hit_at(0x401000)
        n_set = self.fake.cmds.count(X.CMD_DEBUG_SETREGS)
        n_bp = self.fake.cmds.count(X.CMD_DEBUG_SET_BREAKPOINT)
        self.s.resume()
        self.assertEqual(self.fake.continues, 1)
        self.assertEqual(self.fake.cmds.count(X.CMD_DEBUG_SETREGS), n_set)        # kein RIP-Zuruecksetzen
        self.assertEqual(self.fake.cmds.count(X.CMD_DEBUG_SET_BREAKPOINT), n_bp)  # kein Entfernen/Neusetzen
        self.assertNotIn(X.CMD_DEBUG_STEP_THREAD, self.fake.cmds)
        self.assertEqual(self.s.stopped, {})

    def test_prestepped_is_detected_and_step_does_not_wait_for_the_console(self):
        self.s.set_breakpoint(0, 0x401000)
        h = self.hit_at(0x401000, live=0x401003)          # Konsole hat den Befehl schon ausgefuehrt
        self.assertTrue(h["prestepped"])
        self.s.step()
        self.assertNotIn(X.CMD_DEBUG_STEP_THREAD, self.fake.cmds)
        self.assertEqual(self.hits[-1]["kind"], "STEP")
        self.assertEqual(self.hits[-1]["regs"]["rip"], 0x401003)
        self.assertFalse(self.hits[-1]["prestepped"])

    def test_step_waits_for_the_step_event(self):
        self.s.set_breakpoint(0, 0x401000)
        self.hit_at(0x401000)
        self.fake.on_step = lambda lw: self.fake.send_event(make_packet(lw, 0x401004))
        self.s.step()
        self.assertIn(X.CMD_DEBUG_STEP_THREAD, self.fake.cmds)
        self.assertEqual((self.hits[-1]["kind"], self.hits[-1]["addr"]), ("STEP", 0x401004))

    def test_step_without_event_reports_clear_error(self):
        self.s.set_breakpoint(0, 0x401000)
        self.hit_at(0x401000)
        old = D.STEP_TIMEOUT
        D.STEP_TIMEOUT = 0.3
        try:
            with self.assertRaises(D.DebugError) as cm:
                self.s.step()
            self.assertIn(str(self.lp), str(cm.exception))
        finally:
            D.STEP_TIMEOUT = old

    def test_clear_breakpoint_while_stopped_is_deferred_until_resume(self):
        self.s.set_breakpoint(0, 0x401000)
        self.hit_at(0x401000)
        n_bp = self.fake.cmds.count(X.CMD_DEBUG_SET_BREAKPOINT)
        self.s.clear_breakpoint(0)
        self.assertEqual(self.fake.cmds.count(X.CMD_DEBUG_SET_BREAKPOINT), n_bp)  # noch scharf auf der Konsole
        self.assertEqual(self.s.bps, {})
        self.assertEqual(self.s.free_bp_index(), 1)                                # Slot 0 noch belegt
        self.s.resume()
        self.assertEqual(self.fake.cmds.count(X.CMD_DEBUG_SET_BREAKPOINT), n_bp + 1)
        self.assertEqual(self.s.free_bp_index(), 0)

    def test_clear_breakpoint_while_running_is_immediate(self):
        self.s.set_breakpoint(0, 0x401000)
        n_bp = self.fake.cmds.count(X.CMD_DEBUG_SET_BREAKPOINT)
        self.s.clear_breakpoint(0)
        self.assertEqual(self.fake.cmds.count(X.CMD_DEBUG_SET_BREAKPOINT), n_bp + 1)

    def test_run_slots_are_reserved(self):
        for i in range(X.MAX_BREAKPOINTS - len(D.RUN_SLOTS)):
            self.s.set_breakpoint(self.s.free_bp_index(), 0x1000 + i)
        with self.assertRaises(D.DebugError):
            self.s.free_bp_index()

    def test_run_to_recursion_keeps_running_until_stack_is_unwound(self):
        self.s.run_to(0x500000, min_rsp=0x7FFF0000)
        n = self.fake.continues
        self.fake.live_rip[5] = 0x500000
        self.fake.send_event(make_packet(5, 0x500000, rsp=0x7FFE0000))               # tiefere Rekursion -> weiter
        self.assertTrue(self.wait(lambda: self.fake.continues == n + 1))
        self.assertEqual(self.hits, [])
        self.fake.send_event(make_packet(5, 0x500000, rsp=0x7FFF0008))               # Ziel erreicht
        self.assertTrue(self.wait(lambda: self.hits))
        self.assertEqual((self.hits[-1]["kind"], self.hits[-1]["addr"]), ("STEP", 0x500000))

    def test_keepalive_does_not_ping_or_rebuild_while_a_thread_is_stopped(self):
        self.s.set_breakpoint(0, 0x401000)
        self.hit_at(0x401000)
        self.s.keepalive_s = 0.05
        self.s._start_keepalive()
        n = len(self.fake.cmds)
        time.sleep(0.4)
        self.assertEqual(len(self.fake.cmds), n)
        self.assertEqual(self.s.reconnects, 0)


if __name__ == "__main__":
    unittest.main()
