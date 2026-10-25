"""ps5_more.py - zusaetzliche ps5debug-NG-Befehle fuer den vorhandenen PS5DebugClient.

  foreground_app  Titel-ID / Name / Version des Spiels im Vordergrund (0xBDDD0006)
  write_multi     viele Schreibzugriffe in EINEM Austausch (0xBDAACC04) - Freeze-Listen
  call            Funktion im Spiel aufrufen (0xBDAA0006), mit Stack-sicherem Trampolin
  ptrscan_level   ein Pointer-Scan-Durchgang auf der Konsole (0xBDAACC30, nur mit Payload-Erweiterung)

Protokoll nach PROTOCOL.md v1.3.2 (ps5debug-NG).  Das Trampolin-Verfahren (Stack 2 KB vom
gekaperten Spiel-Thread wegschieben) und das ptrscan-Format stammen aus PS5Debug-studio von
alfizari (Apache-2.0); Code hier eigene Umsetzung auf dem ReaperPy-Client.
"""
import struct
import time

import ps5_client as C

CMD_PROC_CALL = 0xBDAA0006
CMD_WRITE_MULTI = 0xBDAACC04
CMD_FOREGROUND = 0xBDDD0006
CMD_PTRSCAN = 0xBDAACC30
SENTINEL64 = 0xFFFFFFFFFFFFFFFF
TRAMP_SLOT, TRAMP_POOL = 64, 0x4000


class MoreError(RuntimeError):
    pass


def _ok(client, what):
    st = client._recv_status()
    if st != C.STATUS_SUCCESS:
        client._drain_pending(0.1)
        raise MoreError(f"{what}: Status 0x{st:08X}")


# ---------------------------------------------------------------- Vordergrund-Spiel
def foreground_app(client):
    """-> (pid, titleid, name, version); pid 0 = kein Spiel."""
    with client.lock:
        client._send_packet(CMD_FOREGROUND)
        _ok(client, "foreground app")
        blob = client._recv_exact(140)
    pid, tid, _cid, name, ver = struct.unpack("<I16s64s40s16s", blob)
    dec = lambda b: b.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
    return pid, dec(tid).upper(), dec(name), dec(ver)


# ---------------------------------------------------------------- Bulk-Write
def write_multi(client, entries, want_status=False):
    """entries: [(adresse, bytes)].  -> Status-Bytes (0 = ok) wenn want_status, sonst None."""
    entries = [(a, bytes(d)) for a, d in entries if d][:0xFFFF]
    if not entries:
        return b"" if want_status else None
    payload = bytearray()
    for addr, data in entries:
        if len(data) > 0x100000:
            raise MoreError("write_multi: Eintrag groesser als 1 MiB")
        payload += struct.pack("<QI", addr, len(data)) + data
    with client.lock:
        client._send_packet(CMD_WRITE_MULTI, struct.pack("<III", client.pid, len(entries),
                                                           1 if want_status else 0))
        _ok(client, "write_multi (ack)")
        client.sock.sendall(bytes(payload))
        status = client._recv_exact(len(entries)) if want_status else None
        final = client._recv_status()
    if final != C.STATUS_SUCCESS and not want_status:
        raise MoreError("write_multi: einzelne Eintraege fehlgeschlagen")
    return status


# ---------------------------------------------------------------- Funktionsaufruf
def build_trampoline(target):
    """Stub, zu dem der Server statt `target` springt: Stack 2 KB weg vom Spiel-Thread, 16-Byte-
    ausgerichtet, 256 Byte Scratch; danach Rueckkehr zum Server.  Register darf er verbiegen
    (der Server stellt sie wieder her)."""
    code = (b"\x49\x89\xE3"                              # mov r11, rsp
            b"\x48\x8D\xA4\x24\x00\xF8\xFF\xFF"          # lea rsp, [rsp-0x800]
            b"\x48\x83\xE4\xF0"                          # and rsp, -16
            b"\x41\x53\x41\x53"                          # push r11 ; push r11
            b"\x48\x81\xEC\x00\x01\x00\x00"              # sub rsp, 0x100
            b"\x31\xC0"                                  # xor eax, eax
            b"\x49\xBB" + struct.pack("<Q", target & (2**64 - 1)) +   # mov r11, imm64
            b"\x41\xFF\xD3"                              # call r11
            b"\x48\x81\xC4\x00\x01\x00\x00"              # add rsp, 0x100
            b"\x41\x5B\x5C\xC3")                         # pop r11 ; pop rsp ; ret
    assert len(code) <= TRAMP_SLOT
    return code.ljust(TRAMP_SLOT, b"\xCC")


def _trampoline(client, target):
    pools = client.__dict__.setdefault("_tramp_pools", {})
    pool = pools.get(client.pid)
    if pool and target in pool["slots"]:
        return pool["slots"][target]
    if pool is None or pool["used"] + TRAMP_SLOT > TRAMP_POOL:
        pool = {"base": client.allocate_memory(TRAMP_POOL), "used": 0, "slots": {}}
        pools[client.pid] = pool
    addr = pool["base"] + pool["used"]
    client.write_memory(addr, build_trampoline(target))
    pool["used"] += TRAMP_SLOT
    pool["slots"][target] = addr
    return addr


def forget_trampolines(client):
    client.__dict__.pop("_tramp_pools", None)


def call(client, rip, rdi=0, rsi=0, rdx=0, rcx=0, r8=0, r9=0, safe=True, gap=0.15):
    """rip(rdi, rsi, rdx, rcx, r8, r9) im Spiel ausfuehren -> RAX.  Wird NIE wiederholt (die
    Funktion koennte schon gelaufen sein).  `gap`: Mindestabstand zwischen zwei Thread-Kaperungen."""
    m = 2**64 - 1
    with client.lock:
        wait = client.__dict__.get("_last_hijack", 0.0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            entry = _trampoline(client, rip) if safe else rip
            body = struct.pack("<IQQQQQQQQ", client.pid, 0, entry & m, rdi & m, rsi & m, rdx & m,
                               rcx & m, r8 & m, r9 & m)
            client._send_packet(CMD_PROC_CALL, body)
            st = client._recv_status()
            if st != C.STATUS_SUCCESS:
                client._drain_pending(0.1)
                hint = (" (Konsole lehnt Aufrufe ab, solange der Debugger das Spiel anhaelt)"
                        if st == C.STATUS_ERROR else "")
                raise MoreError(f"call: Status 0x{st:08X}{hint}")
            _pid, rax = struct.unpack("<IQ", client._recv_exact(12))
            return rax
        finally:
            client.__dict__["_last_hijack"] = time.monotonic()


# ---------------------------------------------------------------- Pointer-Scan-Level
def ptrscan_level(client, segments, frontier, max_off, alias=True, on_progress=None):
    """Ein Durchgang auf der Konsole.  frontier: aufsteigend sortierte Adressen (Liste von int).
    -> (treffer [(slot, wert)], scanned_bytes, status 0 ok / 1 abgebrochen / 2 Limit)."""
    if not client.__dict__.get("_ptr_authed"):          # Auth gilt pro Verbindung
        if not client.authenticate():
            raise MoreError(f"Auth fehlgeschlagen: {client.last_error}")
        client.__dict__["_ptr_authed"] = True
    if not frontier:
        return [], 0, 0
    fr = b"".join(struct.pack("<Q", a) for a in frontier)
    hdr = struct.pack("<IIQII", client.pid, 1 if alias else 0, max_off, len(segments), len(frontier))
    segs = b"".join(struct.pack("<QQ", a, n) for a, n in segments)
    hits = []
    with client.lock:
        client._send_packet(CMD_PTRSCAN, hdr)
        _ok(client, "ptrscan")
        client.sock.sendall(segs + fr)
        _ok(client, "ptrscan (Eingabe)")
        while True:
            n = client._recv_u32()
            if n == 0:
                break
            if n == 0xFFFFFFFF:
                done, total = struct.unpack("<QQ", client._recv_exact(16))
                if on_progress:
                    on_progress(done, total)
                continue
            if n > (1 << 20):
                raise MoreError("ptrscan: unsinnige Blockgroesse")
            raw = client._recv_exact(n * 16)
            hits += list(struct.iter_unpack("<QQ", raw))
        _total, scanned = struct.unpack("<QQ", client._recv_exact(16))
        status = client._recv_u32()
        _ok(client, "ptrscan (Ende)")
    return hits, scanned, status
