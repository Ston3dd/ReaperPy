"""memtools.py - kleine Speicher-Werkzeuge: Snapshot-Vergleich, Daten-Inspektor, Hexdump."""
import struct


def diff_bytes(old, new, base=0, merge_gap=4):
    """Geaenderte Bereiche -> [(adresse, alt, neu)]; Luecken <= merge_gap werden verschmolzen."""
    n = min(len(old), len(new))
    runs, i = [], 0
    while i < n:
        if old[i] == new[i]:
            i += 1
            continue
        j, last = i + 1, i
        while j < n and j - last <= merge_gap:
            if old[j] != new[j]:
                last = j
            j += 1
        end = last + 1
        runs.append((base + i, bytes(old[i:end]), bytes(new[i:end])))
        i = end
    return runs


def inspect(raw):
    """Bytes ab dem Cursor als verschiedene Typen deuten -> [(name, text)]."""
    raw = bytes(raw)
    out = []
    for fmt, name in (("<B", "u8"), ("<b", "i8"), ("<H", "u16"), ("<h", "i16"), ("<I", "u32"),
                      ("<i", "i32"), ("<Q", "u64"), ("<q", "i64")):
        sz = struct.calcsize(fmt)
        if len(raw) >= sz:
            v = struct.unpack_from(fmt, raw)[0]
            out.append((name, f"{v}" + (f"  ({v & ((1 << 8 * sz) - 1):#x})" if v < 0 or sz > 1 else "")))
    if len(raw) >= 4:
        out.append(("float", f"{struct.unpack_from('<f', raw)[0]:.9g}"))
    if len(raw) >= 8:
        out.append(("double", f"{struct.unpack_from('<d', raw)[0]:.17g}"))
        p = struct.unpack_from("<Q", raw)[0]
        if 0x10000 <= p < 0x800000000000:
            out.append(("zeigt auf", f"{p:#x}"))
    s = raw.split(b"\x00", 1)[0][:48]
    if len(s) >= 2 and all(32 <= c < 127 for c in s):
        out.append(("ASCII", s.decode()))
    return out


def hexdump(data, base=0, width=16):
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hx = " ".join(f"{b:02X}" for b in chunk).ljust(width * 3 - 1)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base + i:016X}  {hx}  {asc}")
    return "\n".join(lines)
