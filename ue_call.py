"""ue_call.py - eine UFunction im laufenden Spiel aufrufen (ProcessEvent), mit Parametern per Namen.

    ProcessEvent(UObject* obj, UFunction* fn, void* params)    -> Adresse aus der vtable von obj

Der Aufruf laeuft ueber ps5_more.call (Trampolin, Thread des Prozesses wird kurz gekapert).  Gut fuer
Funktionen, die Werte lesen/schreiben (SetGlobalTimeDilation, AddHP ...).  Alles, was Objekte ERZEUGT
(SpawnActor, Widgets), gehoert auf den Game-Thread und kann hier abstuerzen - dasselbe Verfahren und
dieselbe Einschraenkung wie `uecall` im ps4-unreal-dumper (TetzkatLipHoka, MIT).
"""
import struct

import uesdk

SCALAR = {"float": "<f", "double": "<d", "int32_t": "<i", "int": "<i", "int32": "<i", "uint32_t": "<I", "uint32": "<I",
          "int64_t": "<q", "int64": "<q", "uint64_t": "<Q", "uint64": "<Q", "int16_t": "<h", "uint16_t": "<H",
          "uint8_t": "<B", "int8_t": "<b", "uint8": "<B", "int8": "<b", "bool": "<B"}


class CallError(ValueError):
    pass


def _norm(t):
    return t.replace("class ", "").replace("struct ", "").replace("enum ", "").replace(" ", "")


def _kind(p):
    t = _norm(p.type)
    if t.endswith("*") or p.ptype in ("ObjectProperty", "ClassProperty", "WeakObjectProperty", "InterfaceProperty"):
        return "ptr"
    if t.lower() in SCALAR:
        return "scalar"
    if p.ptype == "ByteProperty" or p.ptype == "EnumProperty":
        return "byte"
    if p.ptype == "BoolProperty":
        return "bool"
    return "raw"


def parse_assignments(text):
    """'TimeDilation=0.3 WorldContextObject=0x1038e68080 Flag=true' -> {name: text}"""
    out = {}
    for tok in text.split():
        if "=" not in tok:
            raise CallError(f"'{tok}': erwartet Name=Wert")
        k, v = tok.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _to_bytes(p, text):
    k = _kind(p)
    if text.lower().startswith("hex:"):
        raw = bytes.fromhex(text[4:].replace(" ", ""))
        if len(raw) != p.size:
            raise CallError(f"{p.name}: hex: braucht genau {p.size} Byte")
        return raw
    if k == "ptr":
        return struct.pack("<Q", int(text, 0) & (2**64 - 1))
    if k == "bool" or _norm(p.type).lower() == "bool":
        return bytes([1 if text.lower() in ("1", "true", "ja", "an", "on") else 0])
    if k == "byte":
        return bytes([int(text, 0) & 0xFF])
    if k == "scalar":
        fmt = SCALAR[_norm(p.type).lower()]
        v = float(text) if fmt in ("<f", "<d") else int(text, 0)
        return struct.pack(fmt, v)
    raise CallError(f"{p.name}: Typ '{p.type}' wird nicht unterstuetzt (Struct/String/Name) - hex:AABB.. verwenden")


def encode_params(fp, assign):
    """-> bytearray der Parameter-Struct.  Nicht angegebene Eingaben bleiben 0."""
    names = {p.name for p in fp.params}
    unknown = set(assign) - names
    if unknown:
        raise CallError(f"unbekannte Parameter: {', '.join(sorted(unknown))} (gueltig: {', '.join(sorted(names))})")
    buf = bytearray(max(fp.size, max((p.offset + p.size for p in fp.params), default=0)))
    for p in fp.params:
        if p.name in assign:
            raw = _to_bytes(p, assign[p.name])
            buf[p.offset:p.offset + len(raw)] = raw
    return buf


def decode_outputs(fp, raw):
    """Ausgabe-/Rueckgabeparameter -> [(name, text)]"""
    out = []
    for p in fp.params:
        if not p.pflags & (uesdk.CPF_OUT | uesdk.CPF_RETURN):
            continue
        b = bytes(raw[p.offset:p.offset + p.size])
        k, t = _kind(p), _norm(p.type).lower()
        if k == "ptr":
            txt = f"{struct.unpack('<Q', b[:8])[0]:#x}"
        elif k == "scalar":
            fmt = SCALAR[t]
            v = struct.unpack(fmt, b[:struct.calcsize(fmt)])[0]
            txt = f"{v:.9g}" if fmt in ("<f", "<d") else str(v)
        elif k in ("byte", "bool"):
            txt = str(b[0])
        else:
            txt = b.hex(" ").upper()
            if t == "fvector" and len(b) == 24:
                txt = ", ".join(f"{x:.4f}" for x in struct.unpack("<3d", b)) + "  (double x/y/z)"
            elif t == "fvector" and len(b) == 12:
                txt = ", ".join(f"{x:.4f}" for x in struct.unpack("<3f", b))
        out.append(("ReturnValue" if p.pflags & uesdk.CPF_RETURN else p.name, txt))
    return out


def process_event_addr(read, obj, index, fallback=None):
    """ProcessEvent aus der vtable von obj (Slot `index`); sonst `fallback` (Adresse aus offsets.json)."""
    try:
        vt = struct.unpack("<Q", read(obj, 8))[0]
        pe = struct.unpack("<Q", read(vt + 8 * index, 8))[0]
        if pe >= 0x10000:
            return pe
    except Exception:
        pass
    if fallback:
        return fallback
    raise CallError("ProcessEvent-Adresse nicht ermittelbar")


def call_ufunction(client, obj, ufunc, fp, assign, pe_addr, caller=None):
    """-> [(name, wert)] der Ausgaben.  caller(client, rip, rdi, rsi, rdx) -> rax  (Standard ps5_more.call)."""
    if caller is None:
        import ps5_more
        def caller(c, rip, a, b, d):
            return ps5_more.call(c, rip, a, b, d)
    buf = encode_params(fp, assign)
    addr = client.allocate_memory((len(buf) + 0xF) & ~0xF or 0x10)
    try:
        client.write_memory(addr, bytes(buf))
        caller(client, pe_addr, obj, ufunc, addr)
        raw = client.read_memory(addr, len(buf))
    finally:
        try:
            client.free_memory(addr, (len(buf) + 0xF) & ~0xF or 0x10)
        except Exception:
            pass
    return decode_outputs(fp, raw)
