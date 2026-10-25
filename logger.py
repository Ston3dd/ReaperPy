"""logger.py - Function-Logger: protokolliert jeden Aufruf einer Spiel-Funktion.

Die ersten >= 8 Byte der Funktion werden durch einen Sprung in eine Code-Cave ersetzt.  Die Cave
legt bei jedem Aufruf einen 128-Byte-Eintrag (Argument-Register, Rueckkehradresse, Stack-Argumente,
xmm0/xmm1) in einen Ringpuffer im Spiel-Speicher, fuehrt die verschobenen Original-Befehle aus und
springt zurueck.  Das Tool liest den Ringpuffer nur noch aus - das Spiel wird nie angehalten.

Idee (Funktionen per Code-Cave loggen) wie im Function-Logger von PS5Debug-studio (alfizari,
Apache-2.0); Stub, Ringpuffer-Layout und Session sind eigene Umsetzung.

Ringpuffer (Anfang des Datenblocks)
  +0x00  u32 Schreibindex (wird per `lock xadd` hochgezaehlt, mehrere Threads sind ok)
  +0x40  Eintrag[N], je 128 Byte, N = Zweierpotenz
Eintrag
  +0x00 seq   (= Index+1, ZULETZT geschrieben -> ein Eintrag ist nur gueltig, wenn seq stimmt)
  +0x08 rdi  +0x10 rsi  +0x18 rdx  +0x20 rcx  +0x28 r8  +0x30 r9
  +0x38 Rueckkehradresse   +0x40 rax   +0x48 rsp beim Eintritt
  +0x50 Stack-Arg 7  +0x58 Stack-Arg 8  +0x60 xmm0 (low64)  +0x68 xmm1 (low64)  +0x70 Thread (fs:0)
"""
import re
import struct
import time

REC = 128
HEADER = 0x40
FIELDS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9", "ret", "rax", "rsp", "s7", "s8", "xmm0", "xmm1",
          "thread")


def stub_asm(data_addr, ring_entries=1024, thread=False):
    """Logging-Teil der Cave (Intel-Syntax, laeuft in Keystone und GNU as).  Erhaelt alle Register
    und Flags."""
    if ring_entries & (ring_entries - 1) or ring_entries < 2:
        raise ValueError("ring_entries muss eine Zweierpotenz sein")
    L = ["pushfq", "push rax", "push rdx", "sub rsp, 8",
         f"mov rdx, {data_addr:#x}",
         "mov eax, 1", "lock xadd dword ptr [rdx], eax", "mov dword ptr [rsp], eax",
         f"and eax, {ring_entries - 1:#x}", "shl eax, 7", f"lea rdx, [rdx + rax + {HEADER:#x}]",
         "mov qword ptr [rdx + 0x08], rdi", "mov qword ptr [rdx + 0x10], rsi",
         "mov qword ptr [rdx + 0x20], rcx", "mov qword ptr [rdx + 0x28], r8",
         "mov qword ptr [rdx + 0x30], r9",
         "mov rax, qword ptr [rsp + 8]", "mov qword ptr [rdx + 0x18], rax",      # rdx
         "mov rax, qword ptr [rsp + 0x10]", "mov qword ptr [rdx + 0x40], rax",   # rax
         "mov rax, qword ptr [rsp + 0x20]", "mov qword ptr [rdx + 0x38], rax",   # Rueckkehr
         "lea rax, [rsp + 0x20]", "mov qword ptr [rdx + 0x48], rax",
         "mov rax, qword ptr [rsp + 0x28]", "mov qword ptr [rdx + 0x50], rax",
         "mov rax, qword ptr [rsp + 0x30]", "mov qword ptr [rdx + 0x58], rax",
         "movq qword ptr [rdx + 0x60], xmm0", "movq qword ptr [rdx + 0x68], xmm1"]
    if thread:
        L += ["mov rax, qword ptr fs:[0]", "mov qword ptr [rdx + 0x70], rax"]
    L += ["mov eax, dword ptr [rsp]", "add eax, 1", "mov qword ptr [rdx], rax",   # seq zuletzt
          "add rsp, 8", "pop rdx", "pop rax", "popfq"]
    return L


def parse_record(raw):
    v = struct.unpack("<16Q", raw[:REC])
    d = {"seq": v[0]}
    d.update({n: v[i + 1] for i, n in enumerate(FIELDS)})
    return d


def collect(read, data_addr, ring_entries, last):
    """Neue Eintraege seit `last` (absoluter Index) holen.  read(addr, n) -> bytes.
    -> (eintraege, neuer_index, verloren)."""
    cur = struct.unpack("<I", read(data_addr, 4))[0]
    new = (cur - last) & 0xFFFFFFFF
    if new == 0 or new > 0x80000000:
        return [], last, 0
    lost = 0
    if new > ring_entries:
        lost = new - ring_entries
        last = (last + lost) & 0xFFFFFFFF
        new = ring_entries
    first = last & (ring_entries - 1)
    n1 = min(new, ring_entries - first)
    raw = read(data_addr + HEADER + first * REC, n1 * REC)
    if new > n1:
        raw += read(data_addr + HEADER, (new - n1) * REC)
    out, idx = [], last
    for i in range(new):
        rec = parse_record(raw[i * REC:(i + 1) * REC])
        if rec["seq"] != ((idx + 1) & 0xFFFFFFFF):
            break                          # Eintrag wird gerade geschrieben -> naechste Runde
        rec["index"] = idx
        out.append(rec)
        idx = (idx + 1) & 0xFFFFFFFF
    return out, idx, lost


class LoggerSession:
    def __init__(self, backend, hook_addr, ring_entries=1024, thread=False):
        self.b, self.hook, self.ring, self.thread = backend, hook_addr, ring_entries, thread
        self.data = self.cave = None
        self.original = b""
        self.last = 0
        self.lost = 0
        self.active = False

    def start(self, force=False):
        import asm_tools
        import patch_engine as pe
        b = self.b
        code = bytes(b.read(self.hook, 32) or b"")
        if len(code) < 16:
            raise RuntimeError(f"{self.hook:#x} nicht lesbar")
        if code[:1] == b"\xE9" and not force:
            raise RuntimeError("an der Adresse liegt schon ein JMP (anderer Hook?) - erst entfernen")
        info = asm_tools.build_cave_hook(code, self.hook, 8)
        size = info["size"]
        self.original = code[:size]
        size_total = HEADER + self.ring * REC
        self.data = b.alloc_mem(size_total)
        b.write(self.data, bytes(size_total))                     # Puffer sicher auf 0
        body = [ln.strip() for ln in info["cave"].splitlines()
                if ln.strip() and not ln.strip().startswith(";")]
        body = [re.sub(r"\bOriginReturn\b", f"{self.hook + size:#x}", ln) for ln in body]
        lines = stub_asm(self.data, self.ring, self.thread) + body
        self.cave = b.find_cave(self.hook, 0x400)
        lines = pe._resolve_rip_tokens(b, lines, self.cave, self.hook)
        cave_bytes = pe._extract_bytes(b.assemble("\n".join(lines) + "\n", self.cave))
        try:
            b.set_rwx(self.cave, 0x400)
        except Exception:
            pass
        b.write(self.cave, cave_bytes)
        if bytes(b.read(self.cave, len(cave_bytes)) or b"") != cave_bytes:
            raise RuntimeError("Cave-Write nicht verifiziert")
        hook = pe.build_hook(b, self.hook, self.cave, length=8)
        if size > 8:
            hook = hook + b"\x90" * (size - 8)
        b.write(self.hook, hook)
        time.sleep(0.1)
        self.last, self.lost, self.active = 0, 0, True
        return {"data": self.data, "cave": self.cave, "cave_size": len(cave_bytes), "stolen": size}

    def poll(self):
        recs, self.last, lost = collect(self.b.read, self.data, self.ring, self.last)
        self.lost += lost
        return recs

    def stop(self):
        """Original-Bytes zurueck.  Cave und Puffer bleiben liegen (ein Thread koennte noch drin
        sein) - sie sind harmlos."""
        if self.active:
            self.b.write(self.hook, self.original)
            self.active = False
