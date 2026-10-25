"""asm_tools.py – Disassemblieren / Assemblieren / Zahlen-Konverter.

  Disassembler : Capstone (pip install capstone)
  Assembler    : Keystone lokal (pip install keystone-engine); fehlt es, wird
                 der Assembler im ps5debug-NG-Payload auf der PS5 benutzt.
"""
import re
import struct

try:
    import capstone as _cs
    HAVE_CAPSTONE = True
except Exception:
    _cs = None
    HAVE_CAPSTONE = False


# ------------------------------------------------------------------
# Disassembler
# ------------------------------------------------------------------
def disassemble(data, addr, detail=False):
    """Gibt Liste von dicts: addr, size, bytes, mnemonic, op_str, insn (nur detail)."""
    if not HAVE_CAPSTONE:
        raise RuntimeError("Capstone fehlt: pip install capstone")
    md = _cs.Cs(_cs.CS_ARCH_X86, _cs.CS_MODE_64)
    md.detail = bool(detail)
    out, pos = [], 0
    for ins in md.disasm(bytes(data), addr):
        out.append({"addr": ins.address, "size": ins.size, "bytes": bytes(ins.bytes),
                    "mnemonic": ins.mnemonic, "op_str": ins.op_str,
                    "insn": ins if detail else None})
        pos = (ins.address - addr) + ins.size
    return out, pos


def disassemble_lines(data, addr, max_insn=None):
    """Wie disassemble(), aber ungültige Bytes erscheinen als 'db 0xNN' und es geht weiter."""
    if not HAVE_CAPSTONE:
        raise RuntimeError("Capstone fehlt: pip install capstone")
    data = bytes(data)
    lines, off = [], 0
    while off < len(data) and (max_insn is None or len(lines) < max_insn):
        chunk, used = disassemble(data[off:off + 64], addr + off)
        if chunk:
            for c in chunk:
                lines.append(c)
                if max_insn is not None and len(lines) >= max_insn:
                    return lines
            off += used
        else:
            lines.append({"addr": addr + off, "size": 1, "bytes": data[off:off + 1],
                          "mnemonic": "db", "op_str": f"0x{data[off]:02x}", "insn": None})
            off += 1
    return lines


_HEX = re.compile(r"(0x[0-9a-fA-F]+)")


def branch_target(line):
    """Ziel eines direkten call/jmp/jcc (nur wenn Operand eine Zahl ist)."""
    m = line["mnemonic"]
    if m == "call" or m == "jmp" or (m.startswith("j") and len(m) <= 4):
        s = line["op_str"].strip()
        if re.fullmatch(r"0x[0-9a-fA-F]+", s):
            return int(s, 16)
    return None


def rip_target(line):
    """Adresse eines [rip + disp]-Operanden (Capstone liefert sie als Kommentar-frei -> selbst rechnen)."""
    m = re.search(r"\[rip ([+-]) (0x[0-9a-fA-F]+)\]", line["op_str"])
    if not m:
        return None
    disp = int(m.group(2), 16)
    if m.group(1) == "-":
        disp = -disp
    return line["addr"] + line["size"] + disp


# ------------------------------------------------------------------
# Assembler
# ------------------------------------------------------------------
def assemble(text, addr=0, remote_client=None):
    """Assembler-Text -> bytes. Reihenfolge: Keystone lokal, sonst PS5-Payload."""
    err_local = None
    try:
        from keystone import Ks, KS_ARCH_X86, KS_MODE_64
        enc, _ = Ks(KS_ARCH_X86, KS_MODE_64).asm(text, addr=addr)
        if enc is None:
            raise RuntimeError("Keystone: nichts assembliert")
        return bytes(enc)
    except (ImportError, OSError) as e:      # nicht installiert / DLL defekt
        err_local = e
    except Exception as e:
        # echter Syntaxfehler: Meldung weitergeben, kein Fallback nötig
        raise RuntimeError(str(e))
    if remote_client is not None:
        import ps5_ext
        return ps5_ext.assemble_remote(remote_client, text, addr)
    raise RuntimeError(f"Kein Assembler verfügbar ({err_local}). "
                       f"pip install keystone-engine")


def parse_hex_bytes(text):
    """'48 8B 05', '48,8b,05', '0x48 0x8b', '488b05' -> bytes."""
    t = re.sub(r"0x", "", text, flags=re.I)
    t = re.sub(r"[^0-9a-fA-F]", "", t)
    if len(t) % 2:
        raise ValueError("Ungerade Anzahl Hex-Ziffern")
    return bytes.fromhex(t)


def hexdump_line(data):
    return " ".join(f"{b:02X}" for b in data)


# ------------------------------------------------------------------
# Wert-Konverter
# ------------------------------------------------------------------
def convert_value(text):
    """Hex/Dez/Float eingeben -> Dict mit allen Darstellungen."""
    t = text.strip()
    out = {}
    iv = None
    try:
        iv = int(t, 0)
    except ValueError:
        try:
            iv = int(t, 16) if re.fullmatch(r"[0-9a-fA-F]+", t) and re.search(r"[a-fA-F]", t) else None
        except ValueError:
            iv = None
    if iv is not None:
        u = iv & 0xFFFFFFFFFFFFFFFF
        out["u64"] = u
        out["s64"] = u - (1 << 64) if u >> 63 else u
        out["u32"] = u & 0xFFFFFFFF
        out["s32"] = out["u32"] - (1 << 32) if out["u32"] >> 31 else out["u32"]
        out["u16"] = u & 0xFFFF
        out["u8"] = u & 0xFF
        out["hex"] = f"0x{u:X}"
        out["float32"] = struct.unpack("<f", struct.pack("<I", out["u32"]))[0]
        out["float64"] = struct.unpack("<d", struct.pack("<Q", u))[0]
        out["bytes32 (LE)"] = hexdump_line(struct.pack("<I", out["u32"]))
        out["bytes64 (LE)"] = hexdump_line(struct.pack("<Q", u))
        return out
    try:
        f = float(t)
        out["float32 -> hex"] = f"0x{struct.unpack('<I', struct.pack('<f', f))[0]:08X}"
        out["float32 bytes (LE)"] = hexdump_line(struct.pack("<f", f))
        out["float64 -> hex"] = f"0x{struct.unpack('<Q', struct.pack('<d', f))[0]:016X}"
        out["float64 bytes (LE)"] = hexdump_line(struct.pack("<d", f))
    except ValueError:
        raise ValueError("Keine Zahl")
    return out


# ------------------------------------------------------------------
# Hook-Template-Generator (Cheat-Editor: ALS CAVE-HOOK)
# ------------------------------------------------------------------
_RIP_OP = re.compile(r"\[rip(?: ([+-]) (0x[0-9a-fA-F]+))?\]")


def _rel(delta):
    return f"@hook{'+' if delta >= 0 else '-'}{abs(delta):#x}"


def build_cave_hook(data, addr, min_len=8):
    """Aus den Bytes ab `addr` ein fertiges Cave-Hook-Gerüst bauen.

    Der Hook überschreibt min_len (8) Byte: jmp rel32 + NOPs.  Es werden ganze Befehle kopiert, bis
    mindestens min_len Byte abgedeckt sind; OriginReturn = Summe der Befehlsgrößen.
    RIP-relative Operanden und direkte Sprungziele werden als `@hook±N` geschrieben - der
    Cave-Assembler (patch_engine) rechnet sie für die echte Cave-Position aus.

    Rückgabe: dict(size, default, cave, new, warnings)."""
    lines = disassemble_lines(data, addr, max_insn=16)
    used, total, warnings = [], 0, []
    for l in lines:
        if l["mnemonic"] == "db":
            raise ValueError(f"Ungültiger Opcode bei {l['addr']:#x} - Startadresse prüfen")
        used.append(l)
        total += l["size"]
        if total >= min_len:
            break
    if total < min_len:
        raise ValueError("Zu wenig dekodierbare Bytes für einen Hook")
    if total > 15:
        warnings.append(f"{total} Byte überschrieben - sehr lange Befehle am Anfang")
    first = bytes(data[:1])
    if first == b"\xE9":
        warnings.append("Startbyte ist E9 (jmp) - evtl. schon gepatcht (erst TEST AUS / deaktivieren)")

    body = []
    for i, l in enumerate(used):
        op = l["op_str"]
        m = _RIP_OP.search(op)
        if m:
            disp = int(m.group(2), 16) * (-1 if m.group(1) == "-" else 1) if m.group(2) else 0
            target = l["addr"] + l["size"] + disp
            op = _RIP_OP.sub("[rip + " + _rel(target - addr) + "]", op)
        else:
            t = branch_target(l)
            if t is not None:
                op = _rel(t - addr)
        body.append(f"{l['mnemonic']} {op}".strip())
        if i < len(used) - 1 and (l["mnemonic"] in ("ret", "jmp") or l["mnemonic"].startswith("ret")):
            warnings.append(f"'{l['mnemonic']}' mitten im überschriebenen Bereich - Code danach unerreichbar")

    cave = ("; --- eigener Code hier (vor den Original-Befehlen) ---\n"
            + "\n".join(body) + "\njmp OriginReturn\n")
    return {"size": total, "default": " ".join(f"{b:02X}" for b in data[:total]),
            "cave": cave, "new": "jmp OriginTarget", "warnings": warnings}
