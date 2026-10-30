"""aob.py – AOB-Muster mit Wildcards, Scans, Signaturen und Patch-Updates.

Idee: Jeder Patch bekommt eine Signatur (Byte-Muster rund um den Hook).
Nach einem Spiel-Update findet der Update-Scan die neue Adresse selbst und
rechnet den Offset in der Patch-Datei neu aus.

Signatur-Format in der Patch-Datei (am OriginSource-Eintrag):
    "aob": "48 8B ?? ?? ?? ?? ?? 89 45 E8"
    "aobOffset": 0          # Hook = Treffer + aobOffset
"""
import json
import re

import ps5_ext as X
import asm_tools

CHUNK = 0x100000
_cache = {}          # (pid, pattern) -> Adresse


def clear_cache():
    _cache.clear()


# ------------------------------------------------------------------
# Muster
# ------------------------------------------------------------------
def parse_pattern(text):
    """'48 8B ?? 05' -> (bytes, mask). Wildcards: ?, ??, *, xx. mask 1 = muss passen."""
    pat, mask = bytearray(), bytearray()
    for tok in re.split(r"[\s,]+", text.strip()):
        if not tok:
            continue
        t = tok[2:] if tok.lower().startswith("0x") else tok
        if t in ("?", "??", "*", "**", "xx", "XX"):
            pat.append(0); mask.append(0)
        elif re.fullmatch(r"[0-9a-fA-F]{2}", t):
            pat.append(int(t, 16)); mask.append(1)
        elif re.fullmatch(r"(?:[0-9a-fA-F?]{2})+", t):      # '48??8B' ohne Leerzeichen
            for i in range(0, len(t), 2):
                p = t[i:i + 2]
                if p == "??":
                    pat.append(0); mask.append(0)
                elif "?" in p:
                    raise ValueError(f"Halbes Wildcard nicht unterstützt: {p}")
                else:
                    pat.append(int(p, 16)); mask.append(1)
        else:
            raise ValueError(f"Ungültiges Muster-Token: {tok!r}")
    if not pat:
        raise ValueError("Leeres Muster")
    if not any(mask):
        raise ValueError("Muster besteht nur aus Wildcards")
    return bytes(pat), bytes(mask)


def format_pattern(pat, mask):
    return " ".join(f"{b:02X}" if m else "??" for b, m in zip(pat, mask))


def _regex(pat, mask):
    parts = []
    for b, m in zip(pat, mask):
        parts.append(re.escape(bytes([b])) if m else b".")
    return re.compile(b"".join(parts), re.S)


# ------------------------------------------------------------------
# Regionen
# ------------------------------------------------------------------
def exec_regions(maps, min_size=0x1000):
    """Ausführbare Regionen (prot & 4), sortiert nach Adresse."""
    return sorted([(s, e) for s, e, p in maps if (p & 4) and (e - s) >= min_size])


def readable_regions(maps, min_size=0x1000):
    return sorted([(s, e) for s, e, p in maps if (p & 1) and (e - s) >= min_size])


# ------------------------------------------------------------------
# Scannen
# ------------------------------------------------------------------
def scan_local(client, regions, pat, mask, limit=100, progress=None):
    """Client-seitiger Scan (liest den Speicher). Langsam, aber findet ALLE Treffer."""
    rx = _regex(pat, mask)
    n = len(pat)
    out = []
    for ri, (start, end) in enumerate(regions):
        pos = start
        while pos < end:
            size = min(CHUNK + n - 1, end - pos)
            try:
                data = client.read_memory(pos, size)
            except Exception:
                pos += CHUNK
                continue
            for m in rx.finditer(data):
                if m.start() < CHUNK or pos + CHUNK >= end:
                    out.append(pos + m.start())
                    if len(out) >= limit:
                        return out
            pos += CHUNK
            if progress:
                progress(ri, len(regions), pos)
    return sorted(set(out))


def scan_server(client, regions, pat, mask, limit=20):
    """Serverseitiger AOB-Scan (schnell). Gibt bis zu `limit` Treffer zurück."""
    out = []
    for start, end in regions:
        for nth in range(1, limit + 1):
            a = X.aob_scan(client, start, min(end - start, 0xFFFFFFFF), pat, mask, nth=nth)
            if not a:
                break
            out.append(a)
            if len(out) >= limit:
                return out
    return out


def find_matches(client, regions, pat, mask, limit=20):
    try:
        return scan_server(client, regions, pat, mask, limit)
    except Exception:
        try:
            return scan_local(client, regions, pat, mask, limit)
        except Exception as e:
            raise RuntimeError(f"Scan-Fehler: {e}")


def find_first(client, regions, pat, mask):
    """Schnell: erster Treffer in irgendeiner Region (0 = keiner)."""
    for start, end in regions:
        try:
            a = X.aob_scan(client, start, min(end - start, 0xFFFFFFFF), pat, mask, nth=1)
        except Exception:
            r = scan_local(client, [(start, end)], pat, mask, limit=1)
            a = r[0] if r else 0
        if a:
            return a
    return 0


# ------------------------------------------------------------------
# Signatur erzeugen
# ------------------------------------------------------------------
def _wildcard_flags(data, addr):
    """Welche Bytes ab `addr` sind Adressen/Displacements (variieren bei Updates)?"""
    flags = [False] * len(data)
    if not asm_tools.HAVE_CAPSTONE:
        return flags
    import capstone as cs
    md = cs.Cs(cs.CS_ARCH_X86, cs.CS_MODE_64)
    md.detail = True
    for ins in md.disasm(bytes(data), addr):
        off = ins.address - addr
        try:
            if ins.disp_size == 4 and any(
                    op.type == cs.x86.X86_OP_MEM and op.mem.base == cs.x86.X86_REG_RIP
                    for op in ins.operands):
                for i in range(ins.disp_offset, ins.disp_offset + 4):
                    flags[off + i] = True
            if ins.imm_size == 4 and (ins.group(cs.CS_GRP_CALL) or ins.group(cs.CS_GRP_JUMP)):
                for i in range(ins.imm_offset, ins.imm_offset + 4):
                    flags[off + i] = True
            if ins.disp_size == 4 and not ins.group(cs.CS_GRP_JUMP):
                # große absolute/relative Offsets (z.B. [rbx+0x1A38]) ändern sich oft
                for i in range(ins.disp_offset, ins.disp_offset + 4):
                    flags[off + i] = True
        except Exception:
            continue
    return flags


def make_signature(client, maps, address, hook_len=8, wildcard_hook=True,
                   min_len=12, max_len=96, log=None):
    """Erzeugt ein eindeutiges Muster für `address`.

    Das Muster beginnt am Hook. Die Hook-Bytes selbst sind Wildcards (damit
    die Signatur auch im gepatchten Zustand passt); danach folgen Original-
    bytes mit Wildcards auf Displacements.  Rückgabe: (muster_text, treffer)
    """
    log = log or (lambda m: None)
    regions = exec_regions(maps)
    if not regions:
        raise RuntimeError("Keine ausführbaren Regionen")
    data = client.read_memory(address, hook_len + max_len + 16)
    tail_addr = address + (hook_len if wildcard_hook else 0)
    tail = data[hook_len:] if wildcard_hook else data
    flags = _wildcard_flags(tail, tail_addr)
    if not asm_tools.HAVE_CAPSTONE:
        log("Hinweis: Capstone fehlt - keine automatischen Wildcards auf Adressen.")

    last = []
    n = min_len
    while n <= max_len:
        body = tail[:n]
        pat = (b"\x00" * hook_len if wildcard_hook else b"") + body
        mask = (b"\x00" * hook_len if wildcard_hook else b"") + bytes(
            0 if flags[i] else 1 for i in range(len(body)))
        if sum(mask) < 6:
            n += 4
            continue
        # führende Wildcards sind erlaubt, aber das Muster darf nicht komplett leer sein
        hits = find_matches(client, regions, pat, mask, limit=3)
        last = hits
        if len(hits) == 1 and hits[0] == address:
            return format_pattern(pat, mask), hits
        if len(hits) == 1 and hits[0] != address:
            raise RuntimeError(
                f"Muster trifft eine andere Stelle ({hits[0]:#x}) - Adresse hat sich "
                f"vermutlich verändert oder Hook-Länge stimmt nicht.")
        n += 8
    raise RuntimeError(f"Keine eindeutige Signatur bis {max_len} Bytes "
                       f"({len(last)}+ Treffer). Hook-Länge/Wildcards prüfen.")


# ------------------------------------------------------------------
# Patches: auflösen / aktualisieren
# ------------------------------------------------------------------
def resolve_hook(backend, rp, image_base, log=None):
    """Hook-Adresse eines Patches: per Signatur (falls vorhanden), sonst Basis+Offset."""
    default = image_base + rp.origin_source[0]
    aob = getattr(rp, "origin_aob", "")
    if not aob:
        return default
    pid = backend.pid
    key = (pid, aob)
    if key in _cache:
        return _cache[key] + getattr(rp, "origin_aob_offset", 0)
    try:
        pat, mask = parse_pattern(aob)
        regions = exec_regions(backend.get_maps())
        addr = find_first(backend.client, regions, pat, mask)
        if not addr:
            if log:
                log(f"[aob] {rp.name}: Signatur nicht gefunden - nutze Basis+Offset")
            return default
        _cache[key] = addr
        hook = addr + getattr(rp, "origin_aob_offset", 0)
        if log and hook != default:
            log(f"[aob] {rp.name}: {default:#x} -> {hook:#x} (Update erkannt)")
        return hook
    except Exception as e:
        if log:
            log(f"[aob] {rp.name}: {e} - nutze Basis+Offset")
        return default


def _label(v):
    return str(v.get("label") or v.get("Label") or v.get("name") or v.get("Name") or "")


def _is_source(v):
    return _label(v).lower().replace("_", "").startswith("originsource")


def _num(v, key):
    for k in (key, key.capitalize()):
        if k in v:
            x = v[k]
            if isinstance(x, str):
                try:
                    return int(x, 0), True
                except ValueError:
                    return 0, True
            return int(x), False
    return 0, False


def _set_num(v, key, value, as_str):
    k = key if key in v else key.capitalize() if key.capitalize() in v else key
    v[k] = f"0x{value:X}" if as_str else value


def update_patch_file(path, new_offset=None, delta=None, aob=None, aob_offset=0):
    """Schreibt Offset und/oder Signatur in eine JSON-basierte Patch-Datei.

    new_offset: neuer Offset der ersten OriginSource; alle weiteren Quellen werden
    um dieselbe Differenz verschoben (oder delta direkt angeben)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    variables = None
    for k in ("Variables", "variables", "cheats", "Cheats", "items"):
        if isinstance(data.get(k), list):
            variables = data[k]
            break
    if variables is None:
        raise RuntimeError("Datei hat kein Variables-Array (nur JSON-Formate)")
    sources = [v for v in variables if isinstance(v, dict) and _is_source(v)]
    if not sources:
        raise RuntimeError("Kein OriginSource gefunden")
    first = sources[0]
    old, as_str = _num(first, "offset")
    if new_offset is not None:
        delta = new_offset - old
    if delta:
        for v in variables:
            if not isinstance(v, dict):
                continue
            off, s = _num(v, "offset")
            if _is_source(v) or (off and str(v.get("newValue") or v.get("NewValue") or "").strip()):
                _set_num(v, "offset", off + delta, s)
    if aob is not None:
        first["aob"] = aob
        first["aobOffset"] = aob_offset
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return old, old + (delta or 0)