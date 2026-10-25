"""autocodes.py - beim Verbinden erkennen, welches Spiel laeuft, und dessen Codes (Patches) automatisch anzeigen.

Ablauf (ohne GUI, testbar):
  detect()  fragt die PS5 nach dem Vordergrund-Spiel (Titel-ID, Name, Version) und sucht in der Bibliothek einen Eintrag
            mit dieser Titel-ID, der Patch-Dateien hat.
  decide()  entscheidet, was das Hauptfenster tut:
              ("load", entry)   Codes des Spiels oeffnen
              ("clear", None)   das Spiel hat keine Codes -> Liste bleibt leer (ein Projekt eines ANDEREN Spiels wird
                                geschlossen; ein Projekt ohne erkennbare Titel-ID bleibt, damit nichts verloren geht)
              ("keep", None)    nichts aendern (Projekt gehoert schon zu diesem Spiel / Erkennung nicht moeglich)
"""
from dataclasses import dataclass

import library as lib_mod


@dataclass
class Detected:
    title_id: str = ""
    name: str = ""
    version: str = ""
    entry: object = None        # library.GameEntry mit Patches oder None
    error: str = ""


def foreground(client):
    import ps5_more
    return ps5_more.foreground_app(client)


def detect(client, cfg, defaults=None, foreground_fn=None, library_cls=None):
    """-> Detected.  Wirft nie: Fehler landen in .error (dann bleibt alles wie es ist)."""
    d = Detected()
    try:
        pid, tid, name, ver = (foreground_fn or foreground)(client)
    except Exception as e:  # noqa: BLE001
        d.error = f"{e}"
        return d
    if not pid or not tid:
        d.error = "kein Spiel im Vordergrund"
        return d
    d.title_id, d.name, d.version = tid.upper(), name, ver
    try:
        lib_dir = cfg.get("library_dir") or (defaults or {}).get("library_dir", "")
        lib = (library_cls or lib_mod.Library)(lib_dir, cfg.get("projects_root", ""), list(cfg.get("projects", {})))
        lib.scan()
        d.entry = next((e for e in lib.entries if e.id == d.title_id and e.patches), None)
    except Exception as e:  # noqa: BLE001
        d.error = f"Bibliothek: {e}"
    return d


def decide(det, current_text=""):
    """current_text: Name/Pfad des aktuell geoeffneten Projekts ('' = keins)."""
    if det.error and not det.title_id:
        return "keep", None
    if det.entry is not None:
        return "load", det.entry
    if det.error:                                   # Spiel erkannt, Bibliothek nicht lesbar -> nichts zerstoeren
        return "keep", None
    cur_id = lib_mod.extract_id(current_text)
    if not current_text:
        return "keep", None                         # ist schon leer
    if cur_id and cur_id != det.title_id:
        return "clear", None                        # Projekt eines anderen Spiels
    if cur_id == det.title_id:
        return "keep", None
    return "keep", None                             # Projekt ohne Titel-ID: kann nicht beurteilt werden
