"""cave_check.py - prueft einen gebauten Hook (.reapproj-Dokument) mit ReaperPys EIGENEM Parser und Cave-Assembler,
bevor er gespeichert oder an die Konsole geschickt wird.  Gilt für Unity (cavemaker.py) und Unreal gleichermassen.

Warum: Ein Hook, den ReaperPy beim Laden nicht versteht, wird still uebergangen (kein OriginSource), steht ohne Cave-Code
da (Label fehlt / Sprung geht ins Leere) oder bricht erst beim Aktivieren ab.  Hier wird dasselbe geprueft, was ReaperPy
spaeter tut - und zwar VORHER, mit einer klaren Meldung:

  1. Die Datei wird mit reapatch.ReapPatch.load() gelesen (derselbe Weg wie im Hauptfenster).
  2. Es gibt eine Patch-Stelle (OriginSource) mit Offset, Original-Bytes und neuem Code.
  3. Cave: patch_engine.is_cave_patch() erkennt sie, das Label OriginTarget ist da und nicht leer, OriginReturn passt zur
     Laenge der überschriebenen Original-Befehle, jedes Sprungziel ist ein bekanntes Label, am Ende steht der Rücksprung.
  4. Mit einem Assembler (Backend) wird die Cave probeweise assembliert - mit demselben Code wie beim Aktivieren.
  5. Einfacher Patch: der neue Code passt in die Original-Bytes.

Keine Oberflaeche, kein Netzwerk: das Backend wird nur zum Assemblieren gebraucht (backend.assemble), alles andere liest
nur das Dokument.
"""
import json
import os
import re
import tempfile

import patch_engine as PE
from reapatch import ReapPatch, is_patch_file

HOOK_LEN = 5                         # jmp rel32 + NOPs (patch_engine.build_hook)
PROBE_DISTANCE = 0x4000000          # Probe-Cave 64 MB hinter dem Hook (rel32-Sprung und rip-relative Zugriffe passen)
JUMP_RE = re.compile(r"^\s*(?:jmp|call|j[a-z]{1,3}|loop[a-z]*)\s+([A-Za-z_]\w*)\s*$", re.I)
LABEL_DEF_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:\s*$")
HEX_BYTES_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}\s*)+$")
KNOWN_EXTERN = {"OriginReturn"}


class CaveCheckError(ValueError):
    """Der Hook ist nicht in Ordnung - Text ist die Meldung für den Nutzer."""


def load_doc(doc):
    """Dokument -> ReapPatch, auf demselben Weg wie eine Datei im Projekt (temp. .reapproj, dann ReapPatch.load)."""
    fd, path = tempfile.mkstemp(suffix=".reapproj")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        return ReapPatch.load(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def hex_len(text):
    """Anzahl Bytes, wenn `text` eine Hex-Byte-Folge ist ('48 8B 05 ...'), sonst None."""
    t = (text or "").strip()
    if t and HEX_BYTES_RE.match(t):
        return len(re.findall(r"[0-9A-Fa-f]{2}", t))
    return None


def _label_names(rp):
    return {name for name, _asm in rp.labels}


def _inline_labels(rp):
    out = set()
    for _name, asm in rp.labels:
        for ln in asm.splitlines():
            m = LABEL_DEF_RE.match(ln)
            if m:
                out.add(m.group(1))
    return out


def doc_problems(doc, backend=None, hook_addr=None):
    """-> Liste von Problemen (leer = ReaperPy versteht den Hook und kann ihn aktivieren).

    backend/hook_addr: mit beiden wird die Cave probeweise assembliert (wie beim Aktivieren)."""
    probs = []
    try:
        rp = load_doc(doc)
    except Exception as e:  # noqa: BLE001
        return [f"ReaperPy kann den Patch nicht lesen: {e}"]
    if not (rp.name or "").strip():
        probs.append("Der Patch hat keinen Namen")
    if not rp.origin_source:
        return probs + ["Keine Patch-Stelle (OriginSource) - ReaperPy würde den Patch beim Laden übergehen"]
    off, default, new = rp.origin_source
    if not isinstance(off, int) or off < 0:
        probs.append(f"Ungültiger Offset {off!r}")
    if not (new or "").strip():
        probs.append("Der neue Code (newValue) der Patch-Stelle ist leer - der Patch würde nichts tun")
    if not (default or "").strip():
        probs.append("Die Original-Bytes (defaultValue) fehlen - ReaperPy könnte den Patch nicht zurücknehmen")

    if PE.is_cave_patch(rp):
        probs += _cave_problems(rp, default, backend, hook_addr)
    else:
        if re.match(r"\s*(?:jmp|call)\s+[A-Za-z_]\w*\s*$", new or "", re.I):
            probs.append(f"Der Patch springt auf ein Label, das es nicht gibt: '{new.strip()}'")
        elif backend is not None and hook_addr is not None:
            probs += _simple_problems(rp, default, new, backend, hook_addr)
    return probs


def _cave_problems(rp, default, backend, hook_addr):
    probs = []
    labels = dict(rp.labels)
    if "OriginTarget" not in labels:
        probs.append("Das Label OriginTarget fehlt - die Cave hätte keinen Anfang")
    elif not labels["OriginTarget"].strip():
        probs.append("Das Label OriginTarget ist leer")
    n = hex_len(default)
    ret = rp.origin_return_offset
    if ret < HOOK_LEN:
        probs.append(f"OriginReturn {ret} ist kleiner als der Hook ({HOOK_LEN} Byte) - die Cave würde mitten in "
                     f"überschriebenen Bytes weiterlaufen")
    elif n is not None and ret < n:
        probs.append(f"OriginReturn ({ret} Byte) ist kleiner als die Original-Bytes ({n} Byte) - nach der Cave würde "
                     f"mitten in einem Befehl weitergemacht")
    known = set(labels) | _inline_labels(rp) | KNOWN_EXTERN
    for name, asm in rp.labels:
        for ln in asm.splitlines():
            code = re.split(r"\s;|\s//", ln.strip(), maxsplit=1)[0].strip()
            m = JUMP_RE.match(code)
            if m and m.group(1) not in known:
                probs.append(f"Sprung auf unbekanntes Ziel '{m.group(1)}' in {name}: '{code}'")
    if not probs and backend is not None and hook_addr is not None:
        try:
            _bytes, src = PE.assemble_cave(backend, rp, hook_addr + PROBE_DISTANCE, hook_addr, rp.origin_return_offset or 8)
        except Exception as e:  # noqa: BLE001
            probs.append(f"Die Cave lässt sich nicht assemblieren: {e}")
        else:
            lines = [ln.strip() for ln in src.splitlines() if ln.strip() and not LABEL_DEF_RE.match(ln)]
            want = f"{hook_addr + (rp.origin_return_offset or 8):#x}"
            if not lines or not re.match(rf"^jmp\s+{re.escape(want)}\s*$", lines[-1], re.I):
                probs.append(f"Die Cave endet nicht mit dem Rücksprung nach {want} - das Spiel würde hinter dem "
                             f"Code ins Leere laufen (letzte Zeile: '{lines[-1] if lines else ''}')")
    return probs


def _simple_problems(rp, default, new, backend, hook_addr):
    probs = []
    try:
        raw = PE.asm_to_bytes(backend, new, hook_addr)
    except Exception as e:  # noqa: BLE001
        return [f"Der neue Code lässt sich nicht assemblieren: {e}"]
    n = hex_len(default)
    if n is None:
        try:
            n = len(PE.asm_to_bytes(backend, default, hook_addr))
        except Exception:  # noqa: BLE001
            n = None
    if not raw:
        probs.append("Der neue Code ergibt keine Bytes")
    elif n and len(raw) > n:
        probs.append(f"Der neue Code ({len(raw)} Byte) ist länger als die Original-Bytes ({n} Byte)")
    return probs


def safe_filename(name, default="Patch"):
    s = re.sub(r"[^\w .()+=-]", "_", name or "").strip(" ._")
    return (s or default)[:100]


def write_checked(folder, doc, backend=None, hook_addr=None, fname=None):
    """Prueft, schreibt als .reapproj und liest die Datei noch einmal mit ReaperPys Parser zurück.  -> Pfad.
    Wirft CaveCheckError (mit allen Problemen), wenn etwas nicht stimmt - dann wird NICHTS geschrieben."""
    probs = doc_problems(doc, backend, hook_addr)
    if probs:
        raise CaveCheckError("; ".join(probs))
    os.makedirs(folder, exist_ok=True)
    base = fname or (safe_filename(doc.get("name")) + ".reapproj")
    path = os.path.join(folder, base)
    stem, ext = os.path.splitext(path)
    k = 1
    while os.path.exists(path):                       # nichts ueberschreiben
        k += 1
        path = f"{stem} ({k}){ext}"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    try:
        if not is_patch_file(path):
            raise CaveCheckError(f"{os.path.basename(path)} wird von ReaperPy nicht als Patch-Datei erkannt")
        back = ReapPatch.load(path)
        ref = load_doc(doc)
        if back.origin_source != ref.origin_source or back.labels != ref.labels \
                or back.origin_return_offset != ref.origin_return_offset or back.origin_aob != ref.origin_aob:
            raise CaveCheckError("Die gespeicherte Datei weicht nach dem Zurücklesen vom gebauten Patch ab")
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return path


def describe(doc):
    """Kurzbeschreibung für das Protokoll: 'Cave, 3 Labels, OriginReturn 9, Signatur 24 Byte'."""
    rp = load_doc(doc)
    if PE.is_cave_patch(rp):
        sig = len((rp.origin_aob or "").split()) if rp.origin_aob else 0
        return (f"Cave, {len(rp.labels)} Label(s) ({', '.join(n for n, _ in rp.labels)}), "
                f"OriginReturn {rp.origin_return_offset}" + (f", Signatur {sig} Byte" if sig else ", ohne Signatur"))
    return "einfacher Patch" + (f", Signatur {len(rp.origin_aob.split())} Byte" if rp.origin_aob else "")
