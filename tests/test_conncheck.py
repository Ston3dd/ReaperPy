"""conncheck.py: Verbindungstest in Klartext - ohne Konsole (Netz und Client sind ersetzt)."""
import errno
import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import conncheck as C  # noqa: E402


class FakeClient:
    def __init__(self, version="1.3.2", connect_exc=None, pid=77, pid_exc=None):
        self.version, self.connect_exc, self.pid, self.pid_exc = version, connect_exc, pid, pid_exc
        self.closed = False

    def connect(self):
        if self.connect_exc:
            raise self.connect_exc
        return self.version

    def find_pid(self, name):
        if self.pid_exc:
            raise self.pid_exc
        return self.pid

    def close(self):
        self.closed = True


def tcp_ok(host, port, timeout):
    return None


def tcp_raises(exc, open_ports=()):
    def f(host, port, timeout):
        if port in open_ports:
            return None
        raise exc
    return f


class CheckHost(unittest.TestCase):
    def test_good_addresses(self):
        for h in ("192.168.1.20", " 10.0.0.5 ", "ps5.local"):
            self.assertTrue(C.check_host(h)[0], h)

    def test_typical_mistakes_are_named(self):
        self.assertIn("keine IP", C.check_host("")[1])
        self.assertIn("Doppelpunkt", C.check_host("192.168.1.20:744")[1])
        self.assertIn("keine gültige", C.check_host("192.168.1")[1])
        self.assertIn("keine gültige", C.check_host("192.168.1.256")[1])
        self.assertFalse(C.check_host("http://192.168.1.20")[0])
        self.assertFalse(C.check_host("0.0.0.0")[0])

    def test_english(self):
        self.assertIn("colon", C.check_host("1.2.3.4:5", "en")[1])


class Classify(unittest.TestCase):
    def test_by_type(self):
        self.assertEqual(C.classify(ConnectionRefusedError()), "refused")
        self.assertEqual(C.classify(socket.timeout("timed out")), "timeout")
        self.assertEqual(C.classify(socket.gaierror(-2, "Name or service not known")), "dns")
        self.assertEqual(C.classify(OSError(errno.EHOSTUNREACH, "No route to host")), "unreachable")

    def test_wrapped_errors_are_unwrapped(self):
        """PS5DebugClient.connect verpackt alles in RuntimeError(... from e)."""
        try:
            try:
                raise ConnectionRefusedError("nope")
            except Exception as e:
                raise RuntimeError("Kein gültiges ps5debug-NG auf 1.2.3.4:744: nope") from e
        except RuntimeError as wrapped:
            self.assertEqual(C.classify(wrapped), "refused")

    def test_by_text_after_connect_auto(self):
        e = ConnectionError("Kein Payload auf 1.2.3.4: Kein gültiges ps5debug-NG auf 1.2.3.4:1401: "
                            "[WinError 10061] Es konnte keine Verbindung hergestellt werden, da der Zielcomputer die "
                            "Verbindung verweigert hat")
        self.assertEqual(C.classify(e), "refused")
        self.assertEqual(C.classify(RuntimeError("Kein gültiges ps5debug-NG auf x:744: timed out")), "timeout")
        self.assertEqual(C.classify(RuntimeError("'eboot.bin' nicht gefunden")), "nogame")
        self.assertEqual(C.classify(RuntimeError("leere VERSION-Antwort")), "protocol")
        self.assertEqual(C.classify(RuntimeError("irgendwas")), "other")

    def test_explain_error(self):
        self.assertIn("Payload", C.explain_error(ConnectionRefusedError(), "1.2.3.4", 744))
        self.assertIn("payload", C.explain_error(ConnectionRefusedError(), "1.2.3.4", 744, "en"))
        self.assertIsNone(C.explain_error(RuntimeError("irgendwas")))


class Diagnose(unittest.TestCase):
    def run_diag(self, host="192.168.1.20", port=744, tcp=tcp_ok, client=None, lang="de"):
        cl = client or FakeClient()
        return C.diagnose(host, port, lang=lang, tcp_connect=tcp, client_factory=lambda h, p, t: cl), cl

    def states(self, steps):
        return [s.state for s in steps]

    def test_everything_fine(self):
        steps, cl = self.run_diag()
        self.assertEqual(self.states(steps), ["ok", "ok", "ok", "ok", "info"])
        self.assertTrue(cl.closed)
        self.assertIn("755", steps[-1].detail)
        self.assertIn("Alles in Ordnung", C.summary(steps))

    def test_bad_address_stops_at_once(self):
        steps, _cl = self.run_diag(host="192.168.1")
        self.assertEqual(self.states(steps), ["fail", "skip", "skip", "skip"])
        self.assertIn("Adresse", C.summary(steps))

    def test_timeout_means_wrong_ip_or_console_off(self):
        steps, _cl = self.run_diag(tcp=tcp_raises(socket.timeout("timed out")))
        self.assertEqual(self.states(steps), ["ok", "fail", "skip", "skip"])
        self.assertIn("IP", steps[1].detail)
        self.assertIn("Ruhemodus", steps[1].detail)

    def test_refused_means_payload_not_loaded(self):
        steps, _cl = self.run_diag(tcp=tcp_raises(ConnectionRefusedError()))
        self.assertEqual(self.states(steps), ["ok", "fail", "skip", "skip"])
        self.assertIn("Payload", steps[1].detail)
        self.assertIn("nicht geladen", steps[1].detail)

    def test_refused_but_other_port_open_is_used(self):
        seen = []

        def client(h, p, t):
            seen.append(p)
            return FakeClient()
        steps = C.diagnose("192.168.1.20", 744, tcp_connect=tcp_raises(ConnectionRefusedError(), open_ports=(9020,)),
                           client_factory=client)
        self.assertEqual(self.states(steps)[:4], ["ok", "warn", "ok", "ok"])
        self.assertIn("9020", steps[1].detail)
        self.assertEqual(seen, [9020])

    def test_wrong_protocol(self):
        cl = FakeClient(connect_exc=RuntimeError("leere VERSION-Antwort"))
        steps, cl = self.run_diag(client=cl)
        self.assertEqual(self.states(steps), ["ok", "ok", "fail", "skip"])
        self.assertIn("ps5debug-NG", steps[2].detail)
        self.assertTrue(cl.closed)

    def test_payload_answers_but_game_missing(self):
        cl = FakeClient(pid_exc=RuntimeError("'eboot.bin' nicht gefunden"))
        steps, cl = self.run_diag(client=cl)
        self.assertEqual(self.states(steps), ["ok", "ok", "ok", "fail"])
        self.assertIn("Spielstand", steps[3].detail)
        self.assertTrue(cl.closed)                                   # Verbindung wird auch im Fehlerfall geschlossen
        self.assertIn("Spiel läuft", C.summary(steps))

    def test_english(self):
        steps, _cl = self.run_diag(tcp=tcp_raises(ConnectionRefusedError()), lang="en")
        self.assertIn("not loaded", steps[1].detail)
        self.assertEqual(steps[1].title, "PS5 reachable")

    def test_render_shows_marks_and_details_only_for_problems(self):
        steps, _cl = self.run_diag(tcp=tcp_raises(ConnectionRefusedError()))
        text = C.render(steps)
        self.assertIn("✓  Adresse", text)
        self.assertIn("✗  PS5 erreichbar", text)
        self.assertIn("–  Spiel läuft", text)
        self.assertEqual(text.count("\n     "), 1)                  # nur der Fehler hat eine Detailzeile

    def test_bad_port_text_falls_back_to_default(self):
        seen = []
        C.diagnose("192.168.1.20", "abc", tcp_connect=lambda h, p, t: seen.append(p),
                   client_factory=lambda h, p, t: FakeClient())
        self.assertEqual(seen, [744])


if __name__ == "__main__":
    unittest.main()
