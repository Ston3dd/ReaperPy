"""ps5_client.py – ps5debug-NG Client nach PROTOCOL.md v1.3.2."""
import functools
import socket
import struct
import sys
import select
import threading
import time

PACKET_MAGIC = 0xFFAABBCC
AUTH_MAGIC   = 0xBB40E64D

CMD_VERSION      = 0xBD000001
CMD_FW_VERSION   = 0xBD000500
CMD_BRANDING     = 0xBD000501
CMD_PLATFORM_ID  = 0xBD000502
CMD_PROC_NOP     = 0xBDAACC06

CMD_CONSOLE_PRINT  = 0xBDDD0003
CMD_CONSOLE_NOTIFY = 0xBDDD0004

CMD_PROC_LIST    = 0xBDAA0001
CMD_PROC_READ    = 0xBDAA0002
CMD_PROC_WRITE   = 0xBDAA0003
CMD_PROC_MAPS    = 0xBDAA0004
CMD_PROC_INFO    = 0xBDAA000A
CMD_PROC_ALLOC   = 0xBDAA000B
CMD_PROC_FREE    = 0xBDAA000C
CMD_PROC_PROTECT = 0xBDAA0008
CMD_PROC_CALL    = 0xBDAA0006
CMD_PROC_ALLOC_HINTED = 0xBDAA000E
CMD_PROC_AUTH    = 0xBDAACCFF

STATUS_SUCCESS   = 0x80000000
STATUS_ERROR     = 0xF0000001
STATUS_DATA_NULL = 0xF0000003
STATUS_ALREADY_DEBUG = 0xF0000004
STATUS_INVALID_INDEX = 0xF0000005

COMMON_PORTS = [744, 9020, 9021, 7555, 3232, 9025, 1401]



def _generate_keystream(n=64):
    """Erzeugt den ps5debug-NG-Keystream gemäß auth.c."""
    mask32 = 0xFFFFFFFF
    s1, s2, s3, s4 = 200, 300, 400, 500
    out = bytearray()

    for _ in range(n):
        s1_next = (
            ((s1 << 18) & 0xFFF80000)
            ^ ((s1 ^ ((s1 << 6) & mask32)) >> 13)
        )

        s2_next = (
            ((s2 << 2) & 0xFFFFFFE0)
            ^ ((s2 ^ ((s2 << 2) & mask32)) >> 27)
        )

        s3_next = (
            ((s3 << 7) & 0xFFFFF800)
            ^ ((s3 ^ ((s3 << 13) & mask32)) >> 21)
        )

        s4_next = (
            ((s4 << 13) & 0xFFF00000)
            ^ ((s4 ^ ((s4 << 3) & mask32)) >> 12)
        )

        s1, s2, s3, s4 = (
            s1_next & mask32,
            s2_next & mask32,
            s3_next & mask32,
            s4_next & mask32,
        )

        out.append((s1 ^ s2 ^ s3 ^ s4) & 0xFF)

    return bytes(out)



def _locked(fn):
    """Serialisiert alle Zugriffe auf den Socket (GUI-, Watchdog- und Patch-Threads
    teilen sich eine Verbindung - ohne Lock vermischen sich die Antworten)."""
    @functools.wraps(fn)
    def wrapper(self, *a, **k):
        with self.lock:
            return fn(self, *a, **k)
    return wrapper


class PS5DebugClient:
    def __init__(self, host, port=744, timeout=5):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.pid = None
        self.protocol_version = "?"
        self.notify_cmd = None
        self.last_error = None
        self.lock = threading.RLock()

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Verbindung geschlossen")
            buf += chunk
        return buf

    def _send_packet(self, cmd, data=b""):
        pkt = struct.pack("<III", PACKET_MAGIC, cmd, len(data)) + data
        self.sock.sendall(pkt)

    def _recv_status(self):
        return struct.unpack("<I", self._recv_exact(4))[0]

    def _recv_u32(self):
        return struct.unpack("<I", self._recv_exact(4))[0]

    def _recv_u64(self):
        return struct.unpack("<Q", self._recv_exact(8))[0]

    def _has_pending(self):
        try:
            r, _, _ = select.select([self.sock], [], [], 0)
            return bool(r)
        except Exception:
            return False

    def _drain_pending(self, timeout=0.05):
        if not self._has_pending():
            return 0
        old = self.sock.gettimeout()
        self.sock.settimeout(timeout)
        count = 0
        try:
            while True:
                try:
                    chunk = self.sock.recv(65536)
                    if not chunk:
                        break
                    count += len(chunk)
                except (socket.timeout, BlockingIOError):
                    break
        finally:
            try:
                self.sock.settimeout(old)
            except Exception:
                pass
        return count

    @_locked
    def connect(self):
        self.close()
        self.last_error = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        try:
            self.sock.connect((self.host, self.port))
            self._send_packet(CMD_VERSION)
            length = self._recv_u32()
            if length > 64:
                raise RuntimeError(f"VERSION-Länge unsinnig: {length}")
            data = self._recv_exact(length) if length else b""
            self.protocol_version = data.decode(errors="replace").strip("\x00")
            if not self.protocol_version:
                raise RuntimeError("leere VERSION-Antwort")
            return self.protocol_version
        except Exception as e:
            self.close()
            raise RuntimeError(f"Kein gültiges ps5debug-NG auf {self.host}:{self.port}: {e}") from e

    @_locked
    def reconnect(self):
        old_pid = self.pid
        self.close()
        time.sleep(0.2)
        self.connect()
        if old_pid is not None:
            try:
                self.find_pid()
            except Exception:
                pass

    @classmethod
    def connect_auto(cls, host, ports=None, timeout=2.5):
        if ports is None:
            ports = COMMON_PORTS
        last_err = None
        for p in ports:
            try:
                c = cls(host, p, timeout=timeout)
                c.connect()
                return c, p
            except Exception as e:
                last_err = e
        raise ConnectionError(f"Kein Payload auf {host}: {last_err}")

    def close(self):
        if self.sock:
            try: self.sock.close()
            except Exception: pass
            self.sock = None

    @_locked
    def authenticate(self, flags=2):
        """ps5debug-NG CMD_PROC_AUTH; flag 0x02 enables scan commands."""
        self.last_error = None
        if self.sock is None:
            self.last_error = "keine TCP-Verbindung"
            return False
        try:
            pkt = struct.pack("<II", AUTH_MAGIC, flags)
            self._send_packet(CMD_PROC_AUTH, pkt)
            status = self._recv_status()
            if status != STATUS_SUCCESS:
                raise RuntimeError(f"AUTH-Anforderung abgelehnt: 0x{status:08X}")
            chal_len = struct.unpack("<H", self._recv_exact(2))[0]
            if chal_len != 64:
                raise RuntimeError(f"unerwartete Challenge-Länge: {chal_len} (erwartet 64)")
            challenge = self._recv_exact(chal_len)
            ks = _generate_keystream(chal_len)
            response = bytes(a ^ b for a, b in zip(challenge, ks))
            self.sock.sendall(response)
            status = self._recv_status()
            if status != STATUS_SUCCESS:
                raise RuntimeError(f"AUTH-Antwort abgelehnt: 0x{status:08X}")
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    @_locked
    def get_firmware_version(self):
        self._send_packet(CMD_FW_VERSION)
        return struct.unpack("<H", self._recv_exact(2))[0]

    @_locked
    def get_branding(self):
        self._send_packet(CMD_BRANDING)
        length = self._recv_u32()
        if length == 0 or length > 4096:
            return ""
        return self._recv_exact(length).split(b"\x00", 1)[0].decode(errors="replace")

    @_locked
    def get_platform_id(self):
        self._send_packet(CMD_PLATFORM_ID)
        return struct.unpack("<H", self._recv_exact(2))[0]

    @_locked
    def ping(self):
        try:
            self._send_packet(CMD_PROC_NOP)
            return self._recv_status() == STATUS_SUCCESS
        except Exception:
            return False

    @_locked
    def send_notification(self, message):
        if not message:
            return False
        body = message.encode("utf-8") + b"\x00"
        try:
            self._send_packet(CMD_CONSOLE_NOTIFY, struct.pack("<II", 0, len(body)))
            self.sock.sendall(body)
            status = self._recv_status()
            self._drain_pending()
            return status == STATUS_SUCCESS
        except Exception:
            return False

    @_locked
    def get_process_list(self):
        self._send_packet(CMD_PROC_LIST)
        status = self._recv_status()
        if status != STATUS_SUCCESS:
            self._drain_pending()
            self._send_packet(CMD_PROC_LIST)
            status = self._recv_status()
            if status != STATUS_SUCCESS:
                self._drain_pending()
                raise RuntimeError(f"PROC_LIST status=0x{status:08X}")
        count = self._recv_u32()
        if count == 0 or count > 10000:
            return []
        data = self._recv_exact(count * 36)
        out = []
        for i in range(count):
            off = i * 36
            name = (data[off:off + 32].split(b"\x00", 1)[0].decode(errors="replace"))
            pid = struct.unpack_from("<i", data, off + 32)[0]
            if name:
                out.append((pid, name))
        self._drain_pending()
        return out

    @_locked
    def find_pid(self, name="eboot.bin"):
        procs = self.get_process_list()
        if not procs:
            raise RuntimeError("Prozessliste leer")
        exact = [(p, n) for p, n in procs if n.lower() == name.lower()]
        if exact:
            exact.sort(reverse=True)
            self.pid = exact[0][0]
            return self.pid
        sub = [(p, n) for p, n in procs if name.lower() in n.lower()]
        if sub:
            sub.sort(reverse=True)
            self.pid = sub[0][0]
            return self.pid
        raise RuntimeError(f"'{name}' nicht gefunden")

    @_locked
    def read_memory(self, address, length, _retry=True):
        if self.pid is None:
            raise RuntimeError("Kein PID gesetzt")
        payload = struct.pack("<IQI", self.pid, address, length)
        self._send_packet(CMD_PROC_READ, payload)
        status = self._recv_status()
        if status != STATUS_SUCCESS:
            if _retry:
                self._drain_pending(0.1)
                return self.read_memory(address, length, _retry=False)
            raise RuntimeError(f"read_memory @ 0x{address:x} status=0x{status:08X}")
        out = bytearray()
        remaining = length
        while remaining > 0:
            chunk = min(remaining, 0x10000)
            out += self._recv_exact(chunk)
            remaining -= chunk
        return bytes(out)

    @_locked
    def write_memory(self, address, data):
        if self.pid is None:
            raise RuntimeError("Kein PID gesetzt")
        payload = struct.pack("<IQI", self.pid, address, len(data))
        self._send_packet(CMD_PROC_WRITE, payload)
        status = self._recv_status()
        if status != STATUS_SUCCESS:
            self._drain_pending(0.1)
            raise RuntimeError(f"write ack status=0x{status:08X}")
        off = 0
        while off < len(data):
            chunk = data[off:off + 0x10000]
            self.sock.sendall(chunk)
            off += len(chunk)
        status2 = self._recv_status()
        if status2 != STATUS_SUCCESS:
            self._drain_pending(0.1)
            raise RuntimeError(f"write verify status=0x{status2:08X}")
        self._drain_pending()
        return True

    @_locked
    def get_maps(self, names=False):
        if self.pid is None:
            raise RuntimeError("Kein PID gesetzt")
        self._send_packet(CMD_PROC_MAPS, struct.pack("<I", self.pid))
        status = self._recv_status()
        if status != STATUS_SUCCESS:
            self._drain_pending(0.1)
            self._send_packet(CMD_PROC_MAPS, struct.pack("<I", self.pid))
            status = self._recv_status()
            if status != STATUS_SUCCESS:
                self._drain_pending()
                raise RuntimeError(f"PROC_MAPS status=0x{status:08X}")
        count = self._recv_u32()
        if count == 0 or count > 100000:
            return []
        data = self._recv_exact(count * 58)
        out = []
        for i in range(count):
            off = i * 58
            start, end, _offset = struct.unpack_from("<QQQ", data, off + 32)
            prot = struct.unpack_from("<H", data, off + 56)[0]
            if names:
                nm = data[off:off + 32].split(b"\0", 1)[0].decode("utf-8", "replace")
                out.append((start, end, prot, nm))
            else:
                out.append((start, end, prot))
        return out

    def get_maps_named(self):
        """Wie get_maps(), aber (start, end, prot, modulname) - Name z. B. 'Il2CppUserAssemblies.prx'."""
        return self.get_maps(names=True)

    # ------------------------------------------------------------------
    # PID-Abfrage ohne Seiteneffekt (fuer den Watchdog)
    # ------------------------------------------------------------------
    @_locked
    def lookup_pid(self, name="eboot.bin"):
        """Wie find_pid(), setzt self.pid aber NICHT. None = Prozess laeuft nicht."""
        procs = self.get_process_list()
        low = name.lower()
        exact = sorted([p for p, n in procs if n.lower() == low], reverse=True)
        if exact:
            return exact[0]
        sub = sorted([p for p, n in procs if low in n.lower()], reverse=True)
        return sub[0] if sub else None

    # ------------------------------------------------------------------
    # Speicher-Verwaltung (Cave-Allokation / Protection)
    # ------------------------------------------------------------------
    @_locked
    def change_protection(self, address, length, prot):
        """CMD_PROC_PROTECT: u32 pid, u64 address, u32 length, u32 prot  ->  Status."""
        if self.pid is None:
            raise RuntimeError("Kein PID gesetzt")
        self._send_packet(CMD_PROC_PROTECT, struct.pack("<IQII", self.pid, address, length, prot))
        status = self._recv_status()
        if status != STATUS_SUCCESS:
            self._drain_pending(0.1)
            raise RuntimeError(f"protect @ 0x{address:x} status=0x{status:08X}")
        return True

    @_locked
    def allocate_memory(self, size):
        """CMD_PROC_ALLOC: u32 pid, u32 length  ->  Status + u64 Adresse."""
        if self.pid is None:
            raise RuntimeError("Kein PID gesetzt")
        self._send_packet(CMD_PROC_ALLOC, struct.pack("<II", self.pid, size))
        status = self._recv_status()
        if status != STATUS_SUCCESS:
            self._drain_pending(0.1)
            raise RuntimeError(f"alloc status=0x{status:08X}")
        return self._recv_u64()

    @_locked
    def allocate_memory_hinted(self, hint, size):
        """CMD_PROC_ALLOC_HINTED: u32 pid, u64 hint, u32 length. Bei Fehler sendet der
        Server trotzdem noch die (leere) Antwort-Struktur - sie wird hier mitgelesen."""
        if self.pid is None:
            raise RuntimeError("Kein PID gesetzt")
        self._send_packet(CMD_PROC_ALLOC_HINTED, struct.pack("<IQI", self.pid, hint, size))
        status = self._recv_status()
        addr = self._recv_u64()
        if status != STATUS_SUCCESS:
            self._drain_pending(0.1)
            raise RuntimeError(f"alloc_hinted status=0x{status:08X}")
        return addr

    @_locked
    def free_memory(self, address, size):
        """CMD_PROC_FREE: u32 pid, u64 address, u32 length  ->  Status."""
        if self.pid is None:
            raise RuntimeError("Kein PID gesetzt")
        self._send_packet(CMD_PROC_FREE, struct.pack("<IQI", self.pid, address, size))
        status = self._recv_status()
        if status != STATUS_SUCCESS:
            self._drain_pending(0.1)
            raise RuntimeError(f"free status=0x{status:08X}")
        return True

    @_locked
    def call_function(self, rip, args=None, stub=0):
        """CMD_PROC_CALL: u32 pid, u64 stub, u64 rip, 6 x u64 Argumente (rdi rsi rdx rcx r8 r9)
        ->  Status + u32 pid + u64 RAX.  Wird nie wiederholt (die Funktion koennte schon gelaufen sein)."""
        if self.pid is None:
            raise RuntimeError("Kein PID gesetzt")
        args = list(args or [])
        if len(args) > 6:
            raise ValueError("Maximal sechs Argumente (rdi rsi rdx rcx r8 r9)")
        m = 2**64 - 1
        regs = [a & m for a in args] + [0] * (6 - len(args))
        self._send_packet(CMD_PROC_CALL, struct.pack("<IQQ6Q", self.pid, stub & m, rip & m, *regs))
        status = self._recv_status()
        if status != STATUS_SUCCESS:
            self._drain_pending(0.1)
            raise RuntimeError(f"call @ 0x{rip:x} status=0x{status:08X}")
        self._recv_u32()                      # pid
        return self._recv_u64()
