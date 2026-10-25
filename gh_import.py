"""gh_import.py - GoldHEN/etaHEN-Cheat-JSON -> ReaperPy-Patches (.reapproj), eine Datei pro Mod.

Jeder memory-Eintrag wird eine Patch-Stelle (Bytes). Damit laufen auch Community-Dateien mit
fertigen Caves direkt in ReaperPy: Cave-Bytes und Hook sind einfach weitere Stellen desselben
Patches (an/aus schaltet alle gemeinsam, 'off' stellt die Original-Bytes wieder her).
Offsets in der JSON sind relativ zu `target_base` (0x400000); ReaperPy rechnet relativ zur
Image-Basis des Projekts - die Differenz wird hier ausgeglichen.
"""
import json
import os
import re


def _spaced(hexstr):
    h = re.sub(r"[^0-9A-Fa-f]", "", hexstr or "")
    if len(h) % 2:
        raise ValueError(f"ungerade Hex-Laenge: {hexstr!r}")
    return " ".join(h[i:i + 2].upper() for i in range(0, len(h), 2))


def _safe(name):
    s = "".join(c if c.isalnum() or c in " ._-()+" else "_" for c in name).strip(" .")
    return s or "Mod"


def convert(doc, image_base=0x400000, target_base=0x400000, notes=None):
    """-> [(dateiname, dict)] ; wirft ValueError bei kaputten Eintraegen.

    Eintraege in einer anderen Section als 0 (nur .shn/.mc4 kennen Sections) lassen sich nicht auf
    die Image-Basis abbilden: der ganze Mod wird ausgelassen (nie halb uebernehmen) und in `notes`
    (Liste, optional) vermerkt."""
    if not isinstance(doc, dict) or not isinstance(doc.get("mods"), list):
        raise ValueError("keine GoldHEN/etaHEN-Cheat-JSON (Feld 'mods' fehlt)")
    author = ", ".join(str(c).strip() for c in doc.get("credits", []) if str(c).strip())
    shift = target_base - image_base
    out, used = [], set()
    for mod in doc["mods"]:
        name = str(mod.get("name") or "Mod")
        mem = mod.get("memory") or []
        vars_ = []
        if any(int(e.get("section", 0) or 0) for e in mem):
            if notes is not None:
                notes.append(f"'{name}' ausgelassen: patcht eine andere Section als 0")
            continue
        for e in mem:
            off = int(str(e["offset"]), 16) + shift
            on, offb = _spaced(e.get("on", "")), _spaced(e.get("off", ""))
            if len(on) != len(offb):
                raise ValueError(f"'{name}' @ {e['offset']}: on/off verschieden lang")
            vars_.append({"label": "OriginSource", "offset": hex(off),
                          "defaultValue": offb, "newValue": on})
        if not vars_:
            continue
        if all(v["defaultValue"] == v["newValue"] for v in vars_):
            continue                                  # Button ohne Wirkung (on == off)
        base = _safe(name)
        fn, i = base + ".reapproj", 2
        while fn.lower() in used:
            fn, i = f"{base} ({i}).reapproj", i + 1
        used.add(fn.lower())
        out.append((fn, {"name": name, "author": author, "Variables": vars_}))
    return out


def import_into(patch_dir, json_path, image_base=0x400000, target_base=0x400000, overwrite=False,
                notes=None):
    """Schreibt die Patches nach patch_dir. -> (geschrieben, uebersprungen)

    `json_path` darf eine .json-, .shn- oder .mc4-Datei sein (siehe cheatfmt.py)."""
    import cheatfmt
    doc = cheatfmt.load_file(json_path)
    written, skipped = [], []
    for fn, data in convert(doc, image_base, target_base, notes):
        path = os.path.join(patch_dir, fn)
        if os.path.exists(path) and not overwrite:
            skipped.append(fn)
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        written.append(fn)
    return written, skipped
