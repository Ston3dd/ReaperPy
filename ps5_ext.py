"""ps5_ext.py – Erweiterungen für ps5debug-NG (nach PROTOCOL.md v1.3.2).

  * serverseitiger AOB-Scan, Maps mit Namen, Notification
  * Xrefs, Stack-Walk, Assembler (Keystone auf der PS5)
  * Debugger-Befehle (Attach, Breakpoints, Watchpoints, Register, Step ...)
  * InterruptListener für den Async-Kanal (PS5 -> PC, Port 755)

Alle Funktionen sperren die Client-Verbindung (client.lock), damit sich Antworten
verschiedener Threads nicht vermischen.
"""
import os
import socket
import struct
import threading

from ps5_client import (STATUS_SUCCESS, STATUS_ERROR, STATUS_DATA_NULL,
                        STATUS_ALREADY_DEBUG, STATUS_INVALID_INDEX)

SENTINEL64 = 0xFFFFFFFFFFFFFFFF

# --- Prozess / Scan / Disasm ---------------------------------------------
CMD_PROC_FIND_XREFS_TO  = 0xBDAA0022
CMD_PROC_READ_STACK     = 0xBDAA0023
CMD_PROC_ASSEMBLE       = 0xBDAA0024
CMD_PROC_SCAN_AOB       = 0xBDAA0501
CMD_PROC_SCAN_AOB_MULTI = 0xBDAA0502

CMD_CONSOLE_PRINT  = 0xBDDD0003
CMD_CONSOLE_NOTIFY = 0xBDDD0004

# --- Debugger -------------------------------------------------------------
CMD_DEBUG_ATTACH          = 0xBDBB0001
CMD_DEBUG_DETACH          = 0xBDBB0002
CMD_DEBUG_SET_BREAKPOINT  = 0xBDBB0003
CMD_DEBUG_SET_WATCHPOINT  = 0xBDBB0004
CMD_DEBUG_GET_THREAD_LIST = 0xBDBB0005
CMD_DEBUG_SUSPEND_THREAD  = 0xBDBB0006
CMD_DEBUG_RESUME_THREAD   = 0xBDBB0007
CMD_DEBUG_GETREGS         = 0xBDBB0008
CMD_DEBUG_SETREGS         = 0xBDBB0009
CMD_DEBUG_GETDBREGS       = 0xBDBB000C
CMD_DEBUG_SETDBREGS       = 0xBDBB000D
CMD_DEBUG_CONTINUE        = 0xBDBB0010
CMD_DEBUG_THREAD_INFO     = 0xBDBB0011
CMD_DEBUG_STEP            = 0xBDBB0012
CMD_DEBUG_STEP_THREAD     = 0xBDBB0013

MAX_BREAKPOINTS = 30          # protocol.h
MAX_WATCHPOINTS = 4

# breaktype (DR7-Kodierung, PROTOCOL.md 7.3)
WP_EXEC  = 0
WP_WRITE = 1
WP_RDWR  = 3
# Länge in Bytes -> DR7-Längenfeld (0=1, 1=2, 2=8, 3=4 Bytes)
_WP_LEN_CODE = {1: 0, 2: 1, 4: 3, 8: 2}

REGS_SIZE = 176
FPREGS_SIZE = 832
DBREGS_SIZE = 128
INTERRUPT_PACKET_SIZE = 0x4A0          # 1184 Byte

# FreeBSD amd64 `struct reg` (176 Byte)
_REG_NAMES = ["r15", "r14", "r13", "r12", "r11", "r10", "r9", "r8",
              "rdi", "rsi", "rbp", "rbx", "rdx", "rcx", "rax",
              "trapno", "fs", "gs", "err", "es", "ds",
              "rip", "cs", "rflags", "rsp", "ss"]
_REG_FMT = "<15QIHHIHH5Q"
_REG_MASK = {"trapno": 0xFFFFFFFF, "err": 0xFFFFFFFF,
             "fs": 0xFFFF, "gs": 0xFFFF, "es": 0xFFFF, "ds": 0xFFFF}
REG_SHOW_ORDER = ["rip", "rsp", "rbp", "rax", "rbx", "rcx", "rdx", "rsi", "rdi",
                  "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15",
                  "rflags", "cs", "ss", "ds", "es", "fs", "gs"]
assert struct.calcsize(_REG_FMT) == REGS_SIZE


class ProtocolError(RuntimeError):
    pass


# ------------------------------------------------------------------
# Hilfen
# ------------------------------------------------------------------
def _check(client, what):
    st = client._recv_status()
    if st != STATUS_SUCCESS:
        raise ProtocolError(f"{what}: Status 0x{st:08X}")
    return st


def _long_timeout(client, seconds):
    class _Ctx:
        def __enter__(s):
            s.old = client.sock.gettimeout()
            client.sock.settimeout(seconds)

        def __exit__(s, *a):
            try:
                client.sock.settimeout(s.old)
            except Exception:
                pass
    return _Ctx()


def _recover(client):
    try:
        client._drain_pending(0.2)
    except Exception:
        pass


def _status_cmd(client, cmd, body=b""):
    """Befehl senden, einzelnes Status-Wort zurückgeben."""
    with client.lock:
        client._send_packet(cmd, body)
        return client._recv_status()


# ------------------------------------------------------------------
# AOB-Scan
# ------------------------------------------------------------------
def aob_scan(client, address, length, pattern, mask, nth=1, unique_only=False):
    """Führt den serverseitigen AOB-Scan direkt über ps5debug aus."""
    if len(pattern) != len(mask) or not pattern:
        raise ValueError("Pattern/Mask ungültig")
    length = max(0, min(int(length), 0xFFFFFFFF))
    hdr = struct.pack("<IQIBBI", client.pid, address, length,
                      max(1, min(255, nth)), 1 if unique_only else 0, len(pattern))
    with client.lock:
        try:
            client._send_packet(CMD_PROC_SCAN_AOB, hdr)
            _check(client, "AOB ack")
            client.sock.sendall(bytes(pattern) + bytes(mask))
            _check(client, "AOB data")
            with _long_timeout(client, 180):
                addr = client._recv_u64()
                _check(client, "AOB done")
            return addr
        except Exception:
            _recover(client)
            raise


def aob_scan_multi(client, address, length, patterns, stop_unique=False):
    blob = b""
    for pat, mask, nth in patterns:
        blob += struct.pack("<BI", max(1, min(255, nth)), len(pat)) + bytes(pat) + bytes(mask)
    length = max(0, min(int(length), 0xFFFFFFFF))
    hdr = struct.pack("<IQIBI", client.pid, address, length,
                      1 if stop_unique else 0, len(blob))
    with client.lock:
        try:
            client._send_packet(CMD_PROC_SCAN_AOB_MULTI, hdr)
            _check(client, "AOB-Multi ack")
            client.sock.sendall(blob)
            _check(client, "AOB-Multi data")
            with _long_timeout(client, 300):
                res = [client._recv_u64() for _ in patterns]
                _check(client, "AOB-Multi done")
            return res
        except Exception:
            _recover(client)
            raise


# ------------------------------------------------------------------
# Maps mit Namen / Notification
# ------------------------------------------------------------------
def maps_named(client):
    with client.lock:
        client._send_packet(0xBDAA0004, struct.pack("<I", client.pid))
        _check(client, "MAPS")
        count = client._recv_u32()
        if count == 0 or count > 100000:
            client._drain_pending()
            return []
        data = client._recv_exact(count * 58)
        client._drain_pending()
    out = []
    for i in range(count):
        o = i * 58
        name = data[o:o + 32].split(b"\x00", 1)[0].decode(errors="replace")
        start, end, offset = struct.unpack_from("<QQQ", data, o + 32)
        prot = struct.unpack_from("<H", data, o + 56)[0]
        out.append({"name": name, "start": start, "end": end, "offset": offset, "prot": prot})
    return out


def notify(client, message, msg_type=0):
    if not message:
        return False
    body = message.encode("utf-8") + b"\x00"
    with client.lock:
        try:
            client._send_packet(CMD_CONSOLE_NOTIFY, struct.pack("<II", msg_type, len(body)))
            client.sock.sendall(body)
            st = client._recv_status()
            client._drain_pending()
            return st == STATUS_SUCCESS
        except Exception:
            _recover(client)
            raise


# ------------------------------------------------------------------
# Xrefs / Stack / Assembler
# ------------------------------------------------------------------
def find_xrefs_to(client, address, length, target, limit=200000):
    """Adressen aller Instruktionen in [address, address+length), deren RIP-relatives
    Ziel `target` ist (CMD_PROC_FIND_XREFS_TO, Stream bis 0xFFFF...FF)."""
    length = max(0, min(int(length), 0xFFFFFFFF))
    hdr = struct.pack("<IQIQ", client.pid, address, length, target)
    out = []
    with client.lock:
        try:
            client._send_packet(CMD_PROC_FIND_XREFS_TO, hdr)
            _check(client, "XREFS")
            with _long_timeout(client, 180):
                while True:
                    a = client._recv_u64()
                    if a == SENTINEL64:
                        break
                    if len(out) < limit:
                        out.append(a)
            return out
        except Exception:
            _recover(client)
            raise


def read_stack(client, rbp, rsp, depth=32):
    """Serverseitiger RBP-Ketten-Walk. Rückgabe: [{rbp, rsp, saved_rbp, ret, flags,
    locals, code}, ...] (Frame 0 = oberster Frame)."""
    depth = max(1, min(int(depth), 64))
    with client.lock:
        try:
            client._send_packet(CMD_PROC_READ_STACK,
                                struct.pack("<IQQI", client.pid, rbp, rsp, depth))
            _check(client, "STACK")
            blen = client._recv_u32()
            if blen > 64 * 1024 * 1024:
                raise ProtocolError(f"STACK: unsinnige Länge {blen}")
            blob = client._recv_exact(blen) if blen else b""
        except Exception:
            _recover(client)
            raise
    if len(blob) < 4:
        return []
    n = struct.unpack_from("<I", blob, 0)[0]
    off, frames = 4, []
    for _ in range(n):
        if off + 44 > len(blob):
            break
        f_rbp, f_rsp, saved, ret, flags, llen, clen = struct.unpack_from("<QQQQIII", blob, off)
        off += 44
        loc = blob[off:off + llen]
        off += llen
        code = blob[off:off + clen]
        off += clen
        frames.append({"rbp": f_rbp, "rsp": f_rsp, "saved_rbp": saved, "ret": ret,
                       "flags": flags, "locals": loc, "code": code})
    return frames


def assemble_remote(client, text, addr=0, syntax=0):
    """x86-64-Assembler auf der PS5 (CMD 0xBDAA0024, Keystone im Payload).
    Braucht weder Prozess noch Auth. Rückgabe: bytes."""
    body = struct.pack("<QI", addr & 0xFFFFFFFFFFFFFFFF, syntax) + text.encode("utf-8")
    with client.lock:
        try:
            client._send_packet(CMD_PROC_ASSEMBLE, body)
            st = client._recv_status()
            if st == STATUS_SUCCESS:
                nbytes, _ninsn = struct.unpack("<II", client._recv_exact(8))
                return client._recv_exact(nbytes) if nbytes else b""
            if st == STATUS_ERROR:
                _errno, mlen = struct.unpack("<II", client._recv_exact(8))
                msg = client._recv_exact(min(mlen, 4096)).decode(errors="replace") if mlen else ""
                raise ProtocolError(f"Assembler (PS5): {msg or 'Fehler'}")
            raise ProtocolError(f"Assembler (PS5): Status 0x{st:08X}")
        except ProtocolError:
            raise
        except Exception:
            _recover(client)
            raise


# ------------------------------------------------------------------
# Debugger: Register-Blobs
# ------------------------------------------------------------------
def parse_regs(raw):
    """176-Byte `struct reg` -> dict {name: int}."""
    raw = bytes(raw)
    if len(raw) < REGS_SIZE:
        raise ProtocolError(f"Register-Blob zu kurz: {len(raw)}")
    return dict(zip(_REG_NAMES, struct.unpack(_REG_FMT, raw[:REGS_SIZE])))


def pack_regs(regs):
    """dict -> 176-Byte `struct reg` (Werte werden auf die Feldbreite maskiert)."""
    vals = [int(regs[n]) & _REG_MASK.get(n, 0xFFFFFFFFFFFFFFFF) for n in _REG_NAMES]
    return struct.pack(_REG_FMT, *vals)


def parse_interrupt(buf):
    """1184-Byte Async-Paket (PROTOCOL.md 1.9) -> dict."""
    buf = bytes(buf)
    if len(buf) < INTERRUPT_PACKET_SIZE:
        raise ProtocolError(f"Interrupt-Paket zu kurz: {len(buf)}")
    lwpid, status = struct.unpack_from("<II", buf, 0)
    name = buf[8:48].split(b"\x00", 1)[0].decode(errors="replace")
    regs = parse_regs(buf[0x30:0x30 + REGS_SIZE])
    dbregs = list(struct.unpack_from("<16Q", buf, 0x420))
    # wait4-Status: gestoppt = 0x7F im Low-Byte, Signal im zweiten Byte
    signal = (status >> 8) & 0xFF if (status & 0xFF) == 0x7F else status & 0x7F
    return {"lwpid": lwpid, "status": status, "signal": signal, "name": name,
            "regs": regs, "dbregs": dbregs, "fpregs": buf[0xE0:0xE0 + FPREGS_SIZE]}


# ------------------------------------------------------------------
# Debugger: Befehle (alle geben das rohe Status-Wort zurück, außer Daten-Funktionen)
# ------------------------------------------------------------------
def dbg_attach(client, pid):
    with client.lock:
        client._send_packet(CMD_DEBUG_ATTACH, struct.pack("<I", pid))
        with _long_timeout(client, 30):        # Attach kann dauern (ptrace + Resume)
            return client._recv_status()


def dbg_detach(client):
    with client.lock:
        client._send_packet(CMD_DEBUG_DETACH)
        with _long_timeout(client, 30):
            return client._recv_status()


def dbg_set_breakpoint(client, index, enabled, address):
    return _status_cmd(client, CMD_DEBUG_SET_BREAKPOINT,
                       struct.pack("<IIQ", index, 1 if enabled else 0, address))


def dbg_set_watchpoint(client, index, enabled, size, breaktype, address):
    """size in Bytes (1/2/4/8) - wird hier in die DR7-Kodierung umgerechnet."""
    if size not in _WP_LEN_CODE:
        raise ValueError(f"Watchpoint-Größe {size} nicht erlaubt (1, 2, 4, 8)")
    if breaktype == WP_EXEC:
        size = 1                                  # Exec-Watchpoints: nur 1 Byte
    return _status_cmd(client, CMD_DEBUG_SET_WATCHPOINT,
                       struct.pack("<IIIIQ", index, 1 if enabled else 0,
                                   _WP_LEN_CODE[size], breaktype, address))


def dbg_thread_list(client):
    with client.lock:
        client._send_packet(CMD_DEBUG_GET_THREAD_LIST)
        _check(client, "THREAD_LIST")
        n = client._recv_u32()
        if n > 4096:
            raise ProtocolError(f"THREAD_LIST: unsinnige Anzahl {n}")
        data = client._recv_exact(n * 4) if n else b""
    return list(struct.unpack(f"<{n}I", data)) if n else []


def dbg_thread_info(client, lwpid):
    with client.lock:
        client._send_packet(CMD_DEBUG_THREAD_INFO, struct.pack("<I", lwpid))
        _check(client, "THREAD_INFO")
        data = client._recv_exact(40)
    tid, prio = struct.unpack_from("<II", data, 0)
    return {"lwpid": tid, "priority": prio,
            "name": data[8:40].split(b"\x00", 1)[0].decode(errors="replace")}


def dbg_get_regs_raw(client, lwpid):
    with client.lock:
        client._send_packet(CMD_DEBUG_GETREGS, struct.pack("<I", lwpid))
        _check(client, "GETREGS")
        return client._recv_exact(REGS_SIZE)


def dbg_set_regs_raw(client, lwpid, raw):
    raw = bytes(raw)
    if len(raw) != REGS_SIZE:
        raise ValueError(f"Register-Blob muss {REGS_SIZE} Byte haben")
    with client.lock:
        try:
            client._send_packet(CMD_DEBUG_SETREGS, struct.pack("<II", lwpid, len(raw)))
            _check(client, "SETREGS ack")
            client.sock.sendall(raw)
            _check(client, "SETREGS")
        except Exception:
            _recover(client)
            raise


def dbg_get_dbregs_raw(client, lwpid):
    with client.lock:
        client._send_packet(CMD_DEBUG_GETDBREGS, struct.pack("<I", lwpid))
        _check(client, "GETDBREGS")
        return client._recv_exact(DBREGS_SIZE)


def dbg_continue(client, action=0):
    """0 = fortsetzen, 1 = anhalten (SIGSTOP), 2 = beenden (SIGKILL)."""
    return _status_cmd(client, CMD_DEBUG_CONTINUE, struct.pack("<I", action))


def dbg_step(client):
    return _status_cmd(client, CMD_DEBUG_STEP)


def dbg_step_thread(client, lwpid):
    return _status_cmd(client, CMD_DEBUG_STEP_THREAD, struct.pack("<I", lwpid))


def dbg_suspend_thread(client, lwpid):
    return _status_cmd(client, CMD_DEBUG_SUSPEND_THREAD, struct.pack("<I", lwpid))


def dbg_resume_thread(client, lwpid):
    return _status_cmd(client, CMD_DEBUG_RESUME_THREAD, struct.pack("<I", lwpid))


# ------------------------------------------------------------------
# Async-Kanal (Port 755): die PS5 verbindet sich nach dem Attach zu UNS
# ------------------------------------------------------------------
class InterruptListener:
    """Lauscht auf Port 755 und liefert jedes 1184-Byte-Paket geparst an `callback`.

    Muss VOR dem Attach gestartet werden (die PS5 baut die Verbindung beim Attach
    selbst auf).  Der Konstruktor bindet den Port und wirft OSError, falls er belegt ist.
    """

    def __init__(self, callback, port=755, host="0.0.0.0"):
        self.callback = callback
        self.port = port
        self.connected = threading.Event()
        self._stop = threading.Event()
        self._conn = None
        self._thread = None
        self._srv = self._bind(host, port)
        try:
            self._srv.listen(2)
            self._srv.settimeout(0.5)
        except Exception:
            self._srv.close()
            raise

    @staticmethod
    def _make_socket(mode):
        """Ungebundener Server-Socket.  mode "exclusive": SO_EXCLUSIVEADDRUSE (nur Windows, verhindert
        das Kapern eines belegten Ports); mode "reuse": SO_REUSEADDR (Neustart trotz TIME_WAIT)."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if mode == "exclusive":
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            s.close()
            raise
        return s

    @staticmethod
    def _someone_listens(host, port):
        """True, wenn auf dem Port gerade wirklich jemand lauscht."""
        probe = "127.0.0.1" if host in ("", "0.0.0.0") else host
        try:
            with socket.create_connection((probe, port), timeout=0.3):
                return True
        except OSError:
            return False

    @classmethod
    def _bind(cls, host, port):
        """Windows: erst exklusiv.  Scheitert das nur an TIME_WAIT-Resten des vorigen Attach (sofortiges
        Re-Attach), wird mit SO_REUSEADDR gebunden - aber nie, wenn dort wirklich jemand lauscht."""
        if os.name != "nt":
            s = cls._make_socket("reuse")
            try:
                s.bind((host, port))
            except Exception:
                s.close()
                raise
            return s
        s = cls._make_socket("exclusive")
        try:
            s.bind((host, port))
            return s
        except OSError as first:
            s.close()
            if cls._someone_listens(host, port):
                raise first
        s = cls._make_socket("reuse")
        try:
            s.bind((host, port))
        except Exception:
            s.close()
            raise
        return s

    def start(self):
        self._thread = threading.Thread(target=self._run, name="ps5-interrupts", daemon=True)
        self._thread.start()

    def close(self):
        """Beendet den Listener und gibt den Port sofort frei (ein in accept() blockierter Thread
        haelt den Socket sonst noch bis zu 0,5 s offen)."""
        self._stop.set()
        for s in (self._conn, self._srv):
            try:
                if s:
                    s.shutdown(socket.SHUT_RDWR)      # weckt accept()/recv() sofort auf
            except Exception:
                pass
            try:
                if s:
                    s.close()
            except Exception:
                pass
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(1.5)

    def _run(self):
        while not self._stop.is_set():
            try:
                conn, _addr = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self._conn = conn
            self.connected.set()
            try:
                self._serve(conn)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
                self._conn = None

    def _serve(self, conn):
        conn.settimeout(0.5)
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            while len(buf) >= INTERRUPT_PACKET_SIZE:
                raw, buf = buf[:INTERRUPT_PACKET_SIZE], buf[INTERRUPT_PACKET_SIZE:]
                try:
                    pkt = parse_interrupt(raw)
                except Exception:
                    continue
                try:
                    self.callback(pkt)
                except Exception:
                    pass          # Fehler im Callback dürfen den Kanal nicht töten
