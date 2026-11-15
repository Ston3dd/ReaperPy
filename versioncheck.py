"""versioncheck.py - passen die geladenen Patches zur Spielversion, die gerade auf der Konsole laeuft?

Die Spielversion kommt vom Vordergrund-Spiel (autocodes.Detected.version, z. B. '01.002.000' oder '01.02').
Die Patch-Version steht meist im Datei- oder Ordnernamen (PPSA16096_01.003.000.json, 'Game v01.02').
Vorsichtig: gewarnt wird nur, wenn Versionen gefunden wurden und KEINE davon zur Spiel-Version passt.
"""
import os
import re

VER_RE = re.compile(r"(?<![\d.])(\d{2}\.\d{2,3}(?:\.\d{3})?)(?![\d.]*\d)")


def parse(v):
    """'01.002.000' / '1.02' -> (1, 2); fuehrende Nullen und angehaengte .0 zaehlen nicht."""
    try:
        parts = [int(x) for x in str(v).strip().lstrip("vV").split(".") if x != ""]
    except ValueError:
        return None
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts) or None


def same(a, b):
    pa, pb = parse(a), parse(b)
    return pa is not None and pa == pb


def versions_in(*texts):
    """Alle Versionsangaben aus den Texten (ohne Duplikate, Reihenfolge bleibt)."""
    out = []
    for t in texts:
        for m in VER_RE.finditer(str(t or "")):
            v = m.group(1)
            if not any(same(v, o) for o in out):
                out.append(v)
    return out


def check(game_version, names):
    """-> (status, patch_versions).  status: 'ok' | 'mismatch' | 'unknown'."""
    if parse(game_version) is None:
        return "unknown", []
    found = versions_in(*[os.path.basename(str(n)) if os.sep in str(n) or "/" in str(n) else n for n in names])
    if not found:
        return "unknown", []
    if any(same(game_version, v) for v in found):
        return "ok", found
    return "mismatch", found
