"""imagebase.py - Stimmt die eingestellte Image-Basis mit der Speicherkarte der Konsole ueberein?

Nur PRUEFEN, nie raten: Es wird ausschliesslich die benannte Speicherkarte der Konsole (get_maps_named) ausgewertet - die
Regionen des Moduls 'eboot.bin'.  Gibt es keine Namen, lautet das Ergebnis 'unbekannt' (nicht 'irgendeine Zahl').

Warum keine automatische Umrechnung in read()/write(): Fast alle Zugriffe im Tool arbeiten mit LIVE-Adressen (Pointer, Heap,
Bibliotheken) oder rechnen selbst IMAGE_BASE + RVA.  Eine zentrale Umrechnung wuerde diese Adressen ein zweites Mal
verschieben.  Stimmt die Basis nicht, wird sie sichtbar gemeldet und kann bewusst uebernommen werden (Hauptfenster).
"""
from collections import namedtuple

Result = namedtuple("Result", "status live_base base message")   # status: ok | shifted | unknown | missing
MAIN_MODULES = ("eboot.bin",)


def eboot_regions(named_maps, names=MAIN_MODULES):
    """[(start, end, prot)] aller Regionen des Hauptmoduls, sortiert.  named_maps: Tupel (start, end, prot, name)
    oder dicts {'start','end','prot','name'}."""
    out = []
    for m in named_maps or ():
        if isinstance(m, dict):
            s, e, p, n = m.get("start"), m.get("end"), m.get("prot", 0), m.get("name", "")
        else:
            s, e, p = m[0], m[1], m[2]
            n = m[3] if len(m) > 3 else ""
        if str(n or "").strip().lower() in names:
            out.append((int(s), int(e), int(p)))
    return sorted(out)


def check_image_base(named_maps, base, names=MAIN_MODULES):
    """-> Result.  ok = eboot.bin beginnt genau bei `base`;  shifted = beginnt woanders (live_base nennt die Adresse);
    missing = es gibt eboot.bin-Regionen, aber `base` liegt in keiner Region des Spiels;  unknown = keine Namen in der Karte."""
    regs = eboot_regions(named_maps, names)
    if not regs:
        return Result("unknown", None, base,
                      "Die Image-Basis kann nicht geprüft werden (die Speicherkarte enthält keine Modulnamen).")
    live = regs[0][0]
    if live == base:
        return Result("ok", live, base, f"Image-Basis {base:#x} stimmt mit der Speicherkarte überein.")
    return Result("shifted", live, base,
                  f"Image-Basis stimmt nicht: im Hauptfenster steht {base:#x}, laut Speicherkarte beginnt eboot.bin bei "
                  f"{live:#x} (Unterschied {live - base:+#x}). Mit dieser Basis finden Trainer keine Cave und Patches "
                  "treffen falsche Adressen.")


def module_summary(named_maps, limit=12):
    """Kurzuebersicht fuers Log: [(name, niedrigster Start, hoechstes Ende, Anzahl Regionen)] nach Start sortiert."""
    mods = {}
    for m in named_maps or ():
        if isinstance(m, dict):
            s, e, n = m.get("start"), m.get("end"), m.get("name", "")
        else:
            s, e, n = m[0], m[1], (m[3] if len(m) > 3 else "")
        r = mods.setdefault(str(n) or "(ohne Name)", [int(s), int(e), 0])
        r[0], r[1], r[2] = min(r[0], int(s)), max(r[1], int(e)), r[2] + 1
    rows = sorted(((n, a, b, c) for n, (a, b, c) in mods.items()), key=lambda r: r[1])
    return rows[:limit]
