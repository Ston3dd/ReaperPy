"""patch_engine.py – Assembly -> Bytes -> Cave oder Simple-Patch.

Wichtig:
  - KEIN set_rwx auf Hook-Adressen! ps5debug-NG schreibt via DMAP direkt in
    r-x Pages ohne die Page-Table zu verändern. set_rwx würde die CPU zwingen,
    die Page neu zu laden -> I-Cache-Invalidierung -> Crash.
  - Cave bleibt set_rwx, da sie in einer RW-Region liegt.
  - Kurzer sleep nach Hook-Write für Cache-Relaxation.
"""
import re
import struct
import time

LOG_HEX_BYTES = 32      # laengere Byte-Folgen werden im Log gekuerzt (ganze Hooks/Caves koennen hunderte Bytes haben)


def fmt_bytes(data, limit=LOG_HEX_BYTES):
    """Hex fuers Log: die ersten `limit` Bytes, bei mehr '... (+N bytes)'.  Aendert nichts an den Daten selbst."""
    data = bytes(data)
    if len(data) <= limit:
        return data.hex(" ")
    return f"{data[:limit].hex(' ')} ... (+{len(data) - limit} bytes)"


# ==================================================================
# Hilfsfunktionen
# ==================================================================
def _extract_bytes(result):
    """Keystone gibt je nach Version bytes oder list zurück."""
    if isinstance(result, bytes):
        return result
    if isinstance(result, (list, tuple)):
        if result and isinstance(result[0], int):
            return bytes(result)
        return _extract_bytes(result[0])
    raise RuntimeError(f"assemble() unbekannte Rückgabe: {type(result)}")


# ------------------------------------------------------------------
# Robuster Assembly-Parser (Kommentare, Hex-Bytes, db, nop x8, Adress-Zeilen)
# ------------------------------------------------------------------
_HEX_BYTES_RE = re.compile(r"^(?:0x)?[0-9a-fA-F]{2}(?:[\s,]+(?:0x)?[0-9a-fA-F]{2})*$")
_HEX_BLOB_RE = re.compile(r"^(?:[0-9a-fA-F]{2}){2,}$")
_DB_RE = re.compile(r"^(?:db|\.byte)\s+(.+)$", re.I)
_NUM = r"(0x[0-9a-fA-F]+|\d+)"
_NOP_N_RE1 = re.compile(r"^nop\s*[x*:]\s*" + _NUM + r"$", re.I)
_NOP_N_RE2 = re.compile(r"^" + _NUM + r"\s*[x*:]\s*nop$", re.I)
_NOP_N_RE3 = re.compile(r"^nop\s+" + _NUM + r"$", re.I)
_ADDR_LINE_RE = re.compile(r"^\[?\s*(\+?0x[0-9a-fA-F]+)\s*\]?\s*[:=]?\s*(.*)$")


def _clean_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    line = re.split(r"//|\s#", line, maxsplit=1)[0].strip()
    # 'nop x8 ; Kommentar' / '90 90 ; Kommentar' -> Kommentar abschneiden
    pre = line.split(";")[0].strip()
    if pre != line and pre and _raw_bytes(pre) is not None:
        return pre
    return line


def _raw_bytes(line):
    """Gibt bytes zurück wenn die Zeile reine Bytes sind (90 90 / db 0x90 / nop x5)."""
    m = _NOP_N_RE1.match(line) or _NOP_N_RE2.match(line) or _NOP_N_RE3.match(line)
    if m:
        n = m.group(1)
        return b"\x90" * (int(n, 16) if n.lower().startswith("0x") else int(n))
    m = _DB_RE.match(line)
    if m:
        vals = [v.strip() for v in m.group(1).split(",") if v.strip()]
        return bytes(int(v, 0) & 0xFF for v in vals)
    if _HEX_BYTES_RE.match(line):
        return bytes(int(t.replace("0x", ""), 16)
                     for t in re.split(r"[\s,]+", line) if t)
    if _HEX_BLOB_RE.match(line):
        return bytes.fromhex(line)
    return None


def _ks_assemble(backend, text, addr):
    return _extract_bytes(backend.assemble(text, addr))


def asm_to_bytes(backend, asm, addr):
    """Assembly-Text -> Bytes. Verträgt Kommentare, Hex-Bytes, db, 'nop x8'.
    Wirft bei Fehlern eine Meldung mit der betroffenen Zeile."""
    if not asm or not asm.strip():
        return b""
    lines = [l for l in (_clean_line(x) for x in asm.splitlines()) if l]
    if not lines:
        return b""

    # Schneller Weg: alles auf einmal (unterstützt Labels)
    if all(_raw_bytes(l) is None for l in lines):
        try:
            return _ks_assemble(backend, "\n".join(lines), addr)
        except Exception:
            pass

    # Zeile für Zeile
    out = b""
    for line in lines:
        rb = _raw_bytes(line)
        if rb is not None:
            out += rb
            continue
        try:
            out += _ks_assemble(backend, line, addr + len(out))
        except Exception as e:
            if ";" in line:  # ';' evtl. als Kommentar gemeint
                try:
                    out += _ks_assemble(backend, line.split(";")[0].strip(), addr + len(out))
                    continue
                except Exception:
                    pass
            raise RuntimeError(f"Assembly-Fehler in Zeile {line!r}: {e}")
    return out


def parse_segments(text, site_addr, image_base):
    """Teilt Text in [(adresse, asm_text), ...]. Zeilen wie '0x4aa9093: nop' oder
    '+0xaa9093: nop' starten ein neues Segment (zweite Adresse = fusionierter Patch)."""
    segs = []
    cur_addr, cur = site_addr, []
    for raw in (text or "").splitlines():
        line = _clean_line(raw)
        if not line:
            continue
        m = _ADDR_LINE_RE.match(line)
        if m and (m.group(2) == "" or not _raw_bytes(line)):
            tok, rest = m.group(1), m.group(2).strip()
            val = int(tok.lstrip("+"), 16)
            if tok.startswith("+"):
                addr = image_base + val
            else:
                a_abs, a_rel = val, image_base + val
                addr = a_abs if abs(a_abs - site_addr) < abs(a_rel - site_addr) else a_rel
            if cur:
                segs.append((cur_addr, "\n".join(cur)))
            cur_addr, cur = addr, ([rest] if rest else [])
        else:
            cur.append(line)
    if cur:
        segs.append((cur_addr, "\n".join(cur)))
    return segs


def _asm_or_empty(backend, asm, addr):
    """Kompatibel zur alten Version: alle Segmente hintereinander als Bytes."""
    if not asm or not asm.strip():
        return b""
    out = b""
    for a, t in parse_segments(asm, addr, addr):
        out += asm_to_bytes(backend, t, a)
    return out


def _plan_sites(backend, reapatch, hook_addr):
    """Liste aller Patch-Stellen: [{addr, new_asm, default_asm}, ...]."""
    base = hook_addr - reapatch.origin_source[0]
    plan = []
    for off, dv, nv in reapatch.sites():
        site = base + off
        def_map = dict(parse_segments(dv, site, base)) if dv else {}
        for addr, text in parse_segments(nv, site, base):
            plan.append({"addr": addr, "new_asm": text,
                         "default_asm": def_map.get(addr, "")})
    return plan


def _is_in_exec_region(backend, addr):
    """Prüft ob die Adresse in einem r-x oder rwx Bereich liegt."""
    try:
        maps = backend.get_maps()
    except Exception:
        return True
    for start, end, prot in maps:
        if start <= addr < end:
            return bool(prot & 0x4)
    return False


def _verify_write(backend, addr, expected, label="write"):
    """Liest zurück und vergleicht. Gibt True bei Erfolg."""
    try:
        actual = backend.read(addr, len(expected))
    except Exception as e:
        print(f"[verify] {label} @ {addr:#x} konnte nicht gelesen werden: {e}")
        return False
    if bytes(actual) == bytes(expected):
        return True
    print(f"[verify] {label} @ {addr:#x} STIMMT NICHT ÜBEREIN!")
    print(f"[verify]   Erwartet: {fmt_bytes(expected)}")
    print(f"[verify]   Gelesen:  {fmt_bytes(actual)}")
    return False


def _is_writable_region(backend, addr):
    """Liegt addr in einer beschreibbaren Region? (Maps ggf. einmal neu laden: Caves aus
    allocate_memory sind im Cache noch nicht enthalten.)"""
    for force in (False, True):
        try:
            maps = backend.get_maps(force=force)
        except Exception:
            return True
        for start, end, prot in maps:
            if start <= addr < end:
                return bool(prot & 0x2)
    return False


# ==================================================================
# Cave-Erkennung
# ==================================================================
def is_cave_patch(reapatch):
    """True wenn newValue auf ein Label im Reapatch springt."""
    if not reapatch.origin_source:
        return False
    _, _, new_asm = reapatch.origin_source
    if not new_asm:
        return False
    label_names = {name for name, _ in reapatch.labels}
    if not label_names:
        return False
    for m in re.finditer(r"\b(?:jmp|call)\s+([A-Za-z_]\w*)", new_asm):
        if m.group(1) in label_names:
            return True
    return False


# ==================================================================
# Cave-Assembly
# ==================================================================
# [rip + @hook+0x1234]  -> Ziel = Hook-Adresse + 0x1234   (basis-unabhängig, vom Hook-Generator)
# [rip + @0x7F000000]   -> absolutes Ziel
_RIP_TOKEN = re.compile(r"\[\s*rip\s*\+\s*@(hook\s*[+-]\s*)?(0x[0-9a-fA-F]+|\d+)\s*\]", re.I)


_HOOK_REL = re.compile(r"@hook\s*([+-])\s*(0x[0-9a-fA-F]+|\d+)", re.I)


def _resolve_rip_tokens(backend, src_lines, cave_base, hook_addr):
    """Rechnet RIP-relative Operanden für die Cave-Position aus.

    Kopiert man `mov rax,[rip+0x1234]` in eine Cave, bleibt die Displacement-Zahl gleich, das Ziel
    wandert aber mit. Hier wird die Zahl für die tatsächliche Cave-Adresse neu berechnet. Die
    Instruktionsgröße ändert sich dabei nie ([rip+disp32] hat immer 4 Byte Displacement)."""
    out = list(src_lines)
    for k, line in enumerate(out):
        m = _RIP_TOKEN.search(line)
        if not m:
            continue
        val = int(m.group(2), 0)
        if m.group(1):
            target = hook_addr + (-val if "-" in m.group(1) else val)
        else:
            target = val
        prefix = "\n".join(out[:k]) + "\n"
        try:
            off = len(_extract_bytes(backend.assemble(prefix, cave_base))) if k else 0
            probe = line[:m.start()] + "[rip + 0]" + line[m.end():]
            isz = len(_extract_bytes(backend.assemble(probe, cave_base + off)))
        except Exception as e:
            raise RuntimeError(f"RIP-Operand in Zeile {line.strip()!r} nicht auflösbar "
                               f"(Vorwärts-Label davor?): {e}")
        disp = target - (cave_base + off + isz)
        if not -0x80000000 <= disp <= 0x7FFFFFFF:
            raise RuntimeError(f"RIP-Ziel {target:#x} liegt außerhalb ±2 GB der Cave ({cave_base:#x})")
        sign = "+" if disp >= 0 else "-"
        out[k] = line[:m.start()] + f"[rip {sign} {abs(disp):#x}]" + line[m.end():]
    # übrige @hook±N (z.B. direkte call/jmp-Ziele) -> absolute Adresse
    def _abs(m):
        v = int(m.group(2), 0)
        return f"{hook_addr + (-v if m.group(1) == '-' else v):#x}"
    return [_HOOK_REL.sub(_abs, ln) for ln in out]


def assemble_cave(backend, reapatch, cave_base, hook_addr, return_offset):
    """Baut den Cave-Code aus allen Labels zusammen."""
    ext = {"OriginReturn": hook_addr + return_offset}
    labels = list(reapatch.labels)
    labels.sort(key=lambda t: 0 if t[0] == "OriginTarget" else 1)

    src_lines = []
    for name, asm in labels:
        src_lines.append(f"{name}:")
        for line in asm.splitlines():
            line = line.strip()
            if not line or line.startswith((";", "#", "//")):
                continue                              # Kommentarzeilen (Keystone kennt kein ';')
            line = re.split(r"\s;|\s//", line, maxsplit=1)[0].strip()
            if not line:
                continue
            for ext_name, ext_addr in ext.items():
                line = re.sub(r"\b" + re.escape(ext_name) + r"\b",
                              f"{ext_addr:#x}", line)
            src_lines.append("    " + line)
    src_lines = _resolve_rip_tokens(backend, src_lines, cave_base, hook_addr)
    src = "\n".join(src_lines) + "\n"
    return _extract_bytes(backend.assemble(src, cave_base)), src


# ==================================================================
# Hook-Bau (JMP rel32)
# ==================================================================
def build_hook(backend, hook_addr, cave_addr, length=8):
    """Baut einen 8-Byte-Hook: jmp rel32 + nops."""
    distance = cave_addr - (hook_addr + 5)
    if not (-0x80000000 <= distance <= 0x7FFFFFFF):
        raise RuntimeError(
            f"Hook-Distanz außerhalb rel32: {distance:#x} "
            f"(cave={cave_addr:#x}, hook={hook_addr:#x})"
        )
    if abs(distance) > 0x40000000:
        print(f"[hook]   INFO: Distanz {abs(distance) / 1024 / 1024:.1f} MB "
              f"(innerhalb ±2 GB, kein Problem)")

    result = backend.assemble(f"jmp {cave_addr:#x}", hook_addr)
    data = _extract_bytes(result)
    if len(data) > length:
        raise RuntimeError(f"Hook zu groß: {len(data)} > {length}")
    data += b"\x90" * (length - len(data))
    return data


# ==================================================================
# Cave-Patch anwenden
# ==================================================================
def _apply_cave(backend, reapatch, hook_addr, size_hint=0x4000):
    if not reapatch.origin_source:
        raise RuntimeError("OriginSource fehlt")
    return_offset = reapatch.origin_return_offset or 8

    # --- 1. Original-Bytes lesen ---
    orig = backend.read(hook_addr, 8)
    if orig is None:
        raise RuntimeError(f"Hook {hook_addr:#x} nicht lesbar")
    original_bytes = bytes(orig)
    print(f"[cave]   Original @ {hook_addr:#x}: {fmt_bytes(original_bytes)}")

    # --- 2. Cave-Adresse suchen ---
    cave_addr = backend.find_cave(hook_addr, size_hint)
    print(f"[cave]   Cave-Adresse: {cave_addr:#x}")

    # --- 3. Cave-Code assemblieren ---
    cave_bytes, src = assemble_cave(backend, reapatch, cave_addr,
                                    hook_addr, return_offset)
    if len(cave_bytes) > size_hint:
        raise RuntimeError(f"Cave zu groß: {len(cave_bytes)} > {size_hint}")

    print(f"[cave]   Cave-Code: {len(cave_bytes)} Bytes generiert")

    # --- 4. Cave-Bereich RWX (Cave liegt in einer RW-Region) ---
    try:
        backend.set_rwx(cave_addr, size_hint)
    except Exception as e:
        print(f"[cave]   set_rwx cave: {e}")

    # --- 5. Cave schreiben + verifizieren ---
    backend.write(cave_addr, cave_bytes)
    if not _verify_write(backend, cave_addr, cave_bytes, "Cave"):
        raise RuntimeError("Cave-Write fehlgeschlagen!")
    print(f"[cave]   Cave-Verifikation OK")

    # --- 6. Hook schreiben (KEIN set_rwx!) ---
    hook_bytes = build_hook(backend, hook_addr, cave_addr, length=8)
    backend.write(hook_addr, hook_bytes)
    print(f"[cave]   Hook-Bytes: {fmt_bytes(hook_bytes)} @ {hook_addr:#x}")

    if not _verify_write(backend, hook_addr, hook_bytes, "Hook"):
        raise RuntimeError("Hook-Write fehlgeschlagen!")
    print(f"[cave]   Hook-Verifikation OK")

    # --- 7. Cache relax ---
    time.sleep(0.15)

    return {
        "hook_addr": hook_addr,
        "cave_addr": cave_addr,
        "cave_size": len(cave_bytes),
        "cave_region_size": size_hint,
        "original_bytes": original_bytes,
        "simple": False,
    }


# ==================================================================
# Simple-Patch anwenden
# ==================================================================
def _apply_simple(backend, reapatch, hook_addr):
    if not reapatch.origin_source[2] and not reapatch.extra_sources:
        raise RuntimeError("newValue fehlt (nichts zu patchen)")

    plan = _plan_sites(backend, reapatch, hook_addr)
    if not plan:
        raise RuntimeError("newValue fehlt (nichts zu patchen)")

    done = []
    try:
        for p in plan:
            addr = p["addr"]
            new_raw = asm_to_bytes(backend, p["new_asm"], addr)
            if not new_raw:
                raise RuntimeError(f"newValue @ {addr:#x} ergibt keine Bytes")
            try:
                default_bytes = asm_to_bytes(backend, p["default_asm"], addr)
            except Exception as e:
                print(f"[patch]  defaultValue @ {addr:#x} ignoriert: {e}")
                default_bytes = b""

            size = len(default_bytes) or len(new_raw)
            if len(new_raw) > size:
                raise RuntimeError(
                    f"Neuer Code zu groß @ {addr:#x}: {len(new_raw)} > {size}")
            new_bytes = new_raw + b"\x90" * (size - len(new_raw))

            mem = backend.read(addr, size)
            if mem is None:
                raise RuntimeError(f"Original-Bytes an {addr:#x} nicht lesbar")
            mem = bytes(mem)
            # Wächter fuer Patches mit "Verify": true (Item-Trainer von ReaperPy): steht dort weder das erwartete
            # Original noch der Patch, ist es eine ANDERE Spielversion/Basis - nicht blind drueberschreiben.
            if (getattr(reapatch, "raw", None) or {}).get("Verify") and default_bytes \
                    and len(default_bytes) == size and mem not in (default_bytes, new_bytes):
                raise RuntimeError(
                    f"Passt nicht zu diesem Spiel: an {addr:#x} stehen {mem[:16].hex(' ')} statt der erwarteten "
                    f"{default_bytes[:16].hex(' ')}. Der Patch wurde fuer eine andere Spielversion (oder Image-Basis) "
                    "gebaut - NICHT aktiviert. Trainer: im Tab ITEMS 'TRAINER PRUEFEN' / neu bauen; die Basis im "
                    "Hauptfenster pruefen.")
            original = default_bytes if (mem == new_bytes and default_bytes) else mem

            print(f"[patch]  Original @ {addr:#x}: {fmt_bytes(original)}")
            print(f"[patch]  Neuer Code @ {addr:#x}: {fmt_bytes(new_bytes)}")

            # KEIN set_rwx auf Hook!
            backend.write(addr, new_bytes)
            site = {"addr": addr, "size": size,
                    "original_bytes": original, "new_bytes": new_bytes}
            done.append(site)
            if not _verify_write(backend, addr, new_bytes, "Patch"):
                raise RuntimeError(f"Patch-Write fehlgeschlagen @ {addr:#x}!")
    except Exception:
        # Bereits geschriebene Stellen zurückrollen
        for s in reversed(done):
            try:
                backend.write(s["addr"], s["original_bytes"])
            except Exception:
                pass
        raise

    print(f"[patch]  Verifikation OK ({len(done)} Stelle(n))")
    time.sleep(0.15)

    first = done[0]
    return {
        "hook_addr": hook_addr,
        "size": sum(s["size"] for s in done),
        "original_bytes": first["original_bytes"],
        "new_bytes": first["new_bytes"],
        "sites": done,
        "simple": True,
    }


# ==================================================================
# Dispatch
# ==================================================================
def apply_patch(backend, reapatch, hook_addr, size_hint=0x4000):
    """Erkennt automatisch Cave oder SimplePatch und wendet ihn an."""
    if is_cave_patch(reapatch):
        return _apply_cave(backend, reapatch, hook_addr, size_hint)
    return _apply_simple(backend, reapatch, hook_addr)


# ==================================================================
# Deaktivieren
# ==================================================================
def deactivate_patch(backend, reapatch, state):
    """Setzt Original-Bytes zurück."""
    hook_addr = state["hook_addr"]
    cave_addr = state.get("cave_addr")

    # --- Simple-Patch (ggf. mehrere Stellen) ---
    if state.get("simple"):
        sites = state.get("sites")
        if not sites and reapatch is not None and reapatch.origin_source:
            # State kommt aus dem Status-Scan: Originalbytes aus defaultValue
            sites = []
            for p in _plan_sites(backend, reapatch, hook_addr):
                try:
                    d = asm_to_bytes(backend, p["default_asm"], p["addr"])
                except Exception:
                    d = b""
                if not d and p["addr"] == hook_addr:
                    d = state.get("original_bytes") or b""
                if d:
                    sites.append({"addr": p["addr"], "original_bytes": d})
        if sites:
            # umgekehrte Reihenfolge der Schreibreihenfolge: erst der Haken (zeigt in die Cave), dann die Cave selbst -
            # sonst koennte ein Spiel-Thread in eine schon geloeschte Cave springen
            for s in reversed(sites):
                backend.write(s["addr"], s["original_bytes"])
                print(f"[restore] {s['addr']:#x} -> {fmt_bytes(s['original_bytes'])}")
            time.sleep(0.1)
            return True

    original = state.get("original_bytes")
    size = state.get("size", 8) if state.get("simple") else 8
    if original is None and reapatch is not None and reapatch.origin_source:
        default_asm = reapatch.origin_source[1]
        try:
            original = _asm_or_empty(backend, default_asm, hook_addr)
        except Exception:
            original = b""
    if original is None:
        original = b""
    if len(original) < size:
        original = original + b"\x90" * (size - len(original))
    elif len(original) > size:
        original = original[:size]

    # KEIN set_rwx auf Hook!
    backend.write(hook_addr, original)
    print(f"[restore] Hook {hook_addr:#x} -> {fmt_bytes(original)}")

    # Cave-Protection zurück auf RW
    if cave_addr:
        try:
            backend.set_rw(cave_addr, state.get("cave_region_size", 0x4000))
            print(f"[restore] Cave {cave_addr:#x} Protection -> RW")
        except Exception as e:
            print(f"[restore] Cave-Protection: {e}")

    time.sleep(0.1)
    return True


# ==================================================================
# Patch-Erkennung (Status-Scan)
# ==================================================================
def detect_patched(backend, reapatch, hook_addr):
    """Rückgabe: (ist_gepatcht: bool, cave_addr_or_none, typ: str)."""
    if not reapatch.origin_source:
        return False, None, "?"
    _, default_asm, new_asm = reapatch.origin_source
    if not new_asm:
        return False, None, "?"

    try:
        new_bytes = _asm_or_empty(backend, new_asm, hook_addr)
    except Exception:
        new_bytes = b""
    try:
        default_bytes = _asm_or_empty(backend, default_asm, hook_addr)
    except Exception:
        default_bytes = b""

    cave = is_cave_patch(reapatch)
    typ = "Cave" if cave else "Patch"

    if cave:
        cur = backend.read(hook_addr, 8)
        if cur is None:
            return False, None, typ
        cur = bytes(cur)
        if len(cur) >= 5 and cur[0] == 0xE9:
            rel = struct.unpack("<i", cur[1:5])[0]
            target = (hook_addr + 5 + rel) & 0xFFFFFFFFFFFFFFFF
            # Ein Original-jmp des Spiels zeigt in Code (nicht schreibbar); unsere Cave liegt in
            # beschreibbarem Speicher. Sonst würde jeder Original-E9 als "gepatcht" gelten.
            if _is_writable_region(backend, target):
                return True, target, typ
            return False, None, typ
        if default_bytes and cur[:len(default_bytes)] == default_bytes:
            return False, None, typ
        return False, None, typ

    # Simple-Patch: gepatcht, sobald eine der Stellen die neuen Bytes enthält
    try:
        plan = _plan_sites(backend, reapatch, hook_addr)
    except Exception:
        plan = []
    for p in plan:
        try:
            nb = asm_to_bytes(backend, p["new_asm"], p["addr"])
        except Exception:
            continue
        if not nb:
            continue
        cur = backend.read(p["addr"], len(nb))
        if cur is not None and bytes(cur) == nb:
            return True, None, typ
    return False, None, typ
