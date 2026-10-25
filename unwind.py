"""unwind.py - Aufrufkette aus dem Stack rekonstruieren, auch ohne Frame-Pointer.

Der Server-seitige RBP-Walk scheitert an Code ohne Frame-Pointer.  Hier wird der Stack ab RSP
gelesen und jeder Wert, der (a) in ausfuehrbarem Speicher liegt und (b) direkt hinter einem
CALL-Befehl steht, als Rueckkehradresse gewertet.  Das findet auch ueberschriebene/alte Rahmen
(Kandidaten), daher ist die Liste eine gute Naeherung, kein Beweis.
"""
import struct


def call_len_ending_at(code, end):
    """Laenge eines CALL-Befehls, der bei `end` (Index in code) endet, sonst 0.
    code: bytes, end: Index hinter dem Befehl."""
    if end >= 5 and code[end - 5] == 0xE8:
        return 5                                   # call rel32
    for n in range(2, 10):                         # call r/m64  (FF /2)
        s = end - n
        if s < 0:
            break
        i = s
        while i < end and (0x40 <= code[i] <= 0x4F or code[i] in (0x66, 0x67, 0x2E, 0x3E)):
            i += 1
        if i + 1 >= end or code[i] != 0xFF:
            continue
        modrm = code[i + 1]
        if (modrm >> 3) & 7 != 2:
            continue
        mod, rm = modrm >> 6, modrm & 7
        ln = i - s + 2
        sib_base = None
        if mod != 3 and rm == 4:
            if i + 2 >= end:
                continue
            ln += 1
            sib_base = code[i + 2] & 7
        if mod == 1:
            ln += 1
        elif mod == 2:
            ln += 4
        elif mod == 0 and (rm == 5 or sib_base == 5):
            ln += 4
        if ln == n:
            while s > 0 and 0x40 <= code[s - 1] <= 0x4F and n < 9:   # REX-Praefix (z.B. 41 FF D3)
                s, n = s - 1, n + 1
            return n
    return 0


def unwind(read, rsp, in_code, depth=0x800, max_frames=32, rip=None):
    """read(addr, n) -> bytes ; in_code(addr) -> bool.
    -> [{'slot','ret','call_len'}]  (aufsteigend nach Stack-Adresse)"""
    raw = read(rsp, depth)
    out = []
    for off in range(0, len(raw) - 7, 8):
        val = struct.unpack_from("<Q", raw, off)[0]
        if val < 0x10000 or not in_code(val):
            continue
        try:
            window = bytes(read(val - 10, 10))
        except Exception:
            continue
        n = call_len_ending_at(window, 10)
        if n:
            out.append({"slot": rsp + off, "ret": val, "call_len": n,
                        "callsite": val - n})
            if len(out) >= max_frames:
                break
    return out
