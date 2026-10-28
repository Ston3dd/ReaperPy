"""Image-Basis des Spiels aus den benannten Memory-Maps ermitteln.

Patches und Trainer speichern Offsets (RVA) relativ zur Image-Basis.  Stimmt die Basis auf einer anderen Konsole
nicht (bisher fester Standardwert 0x400000), liest das Tool an der falschen Stelle: "kein Platz fuer die Cave",
"schon aktiv" oder ein Patch, der im Spiel nichts bewirkt.  Hier wird die Basis stattdessen aus dem laufenden Spiel
bestimmt.
"""
DEFAULT_BASE = 0x400000
MAIN_NAMES = ("eboot",)


def detect_image_base(named_maps, main_names=MAIN_NAMES):
    """named_maps = [(start, end, prot, name)] -> niedrigste Startadresse der Regionen des Hauptmoduls oder None."""
    starts = [int(s) for s, _e, _p, n in named_maps if any(m in str(n).lower() for m in main_names)]
    return min(starts) if starts else None


def module_summary(named_maps, limit=12):
    """Kurzuebersicht fuer das Log: [(name, niedrigste Start, hoechstes Ende, Anzahl Regionen)] nach Start sortiert."""
    mods = {}
    for s, e, _p, n in named_maps:
        m = mods.setdefault(str(n) or "(ohne Name)", [int(s), int(e), 0])
        m[0], m[1], m[2] = min(m[0], int(s)), max(m[1], int(e)), m[2] + 1
    rows = sorted(((n, a, b, c) for n, (a, b, c) in mods.items()), key=lambda r: r[1])
    return rows[:limit]


def in_exec_region(maps, addr):
    return any(s <= addr < e and (p & 4) for s, e, p, *_ in maps)


def check_base(named_maps, base):
    """-> (detected, ok, text).  ok=False, wenn die konfigurierte Basis nicht zur erkannten passt."""
    det = detect_image_base(named_maps)
    if det is None:
        return None, True, "Image-Basis nicht erkennbar (kein 'eboot'-Modul in den Memory-Maps)"
    if det == base:
        return det, True, f"Image-Basis {base:#x} stimmt mit dem laufenden Spiel ueberein"
    return det, False, (f"Image-Basis {base:#x} passt NICHT zum laufenden Spiel (erkannt: {det:#x}) - "
                        "Patches/Trainer wuerden an falschen Adressen lesen und schreiben")
