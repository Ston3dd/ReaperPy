"""unity_objects.py - lebende Objekte einer Klasse finden, ohne den Spiel-Speicher immer wieder abzusuchen (ohne tkinter).

Ein Voll-Scan des schreibbaren Speichers dauert in grossen Spielen Minuten.  Frueher startete jeder Klick auf ein Feld (MANUELL),
jedes Geben und jeder Cheat-Menue-Eintrag einen eigenen.  Jetzt gilt:

  1. Cache      Ein Durchlauf (census) hat schon alle Klassen erfasst -> sofort (jede Adresse wird kurz geprueft).
  2. Singleton  (nur mode="any") Statisches Feld 'instance'/'Instance'/... der Klasse zeigt auf das Objekt -> ein Lesezugriff.
  3. Census     Genau EIN Durchlauf fuer ALLE Klassen (mit Fortschritt, abbrechbar); danach sind alle weiteren Abfragen Cache.

mode="all": alle Objekte (Feldliste im MANUELL-Tab);  mode="any": ein Objekt genuegt (Geben, Cheat-Menue) - Singleton zuerst.
Ergebnis: (Adressen, wie) mit wie = "cache" | "singleton" | "census" | "none".
"""
import struct

SINGLETON_NAMES = ("instance", "_instance", "s_instance", "sinstance", "m_instance", "minstance", "singleton", "_singleton",
                   "current", "_current", "shared", "sharedinstance", "inst")


def _norm(name):
    return name.lstrip("_<>").replace("k__BackingField", "").lower().strip("_<>")


def singleton_fields(game, cls):
    """Statische Felder der Klasse, die vom Typ der Klasse (oder einer Basisklasse) sind und wie 'instance' heissen."""
    out = []
    bases = {cls.full, cls.name}
    if cls.base:
        bases.add(cls.base.split("<")[0])
    for f in cls.fields:
        if not f.static or f.offset < 0:
            continue
        ft = (f.type or "").split("<")[0]
        if _norm(f.name) in SINGLETON_NAMES and (ft in bases or ft == cls.name):
            out.append(f)
    return out


def singleton(live, game, cls):
    """Adresse des Singleton-Objekts oder None (nichts geraten: der Zeiger muss auf ein Objekt der Klasse zeigen)."""
    fields = singleton_fields(game, cls)
    if not fields:
        return None
    sb = live.static_base(cls)
    if not sb:
        return None
    kps = set()
    for c in game.family(cls, cap=24):
        kp = live.klass_ptr(c, by_name=(c is cls))
        if kp:
            kps.add(kp)
    if not kps:
        return None
    for f in fields:
        try:
            p = struct.unpack("<Q", live.read(sb + f.offset, 8))[0]
        except Exception:  # noqa: BLE001
            continue
        if p > 0x10000 and live._header_ok(p, kps):
            return p
    return None


def has_cache(live, game, cls):
    objs = getattr(live, "objects", None)
    return objs is not None and any(c.full in live.known for c in game.family(cls, cap=24))


def find(live, game, cls, mode="all", limit=400, progress=None, cancel=None, census=True):
    """-> (Adressen, wie).  census=False: nie scannen (nur Cache/Singleton)."""
    if not hasattr(live, "census"):                      # einfacher Ersatz (Tests): direkt fragen
        return live.instances(cls, limit=limit), "scan"
    if has_cache(live, game, cls):
        return live.instances(cls, limit=limit), "cache"
    if mode == "any":
        p = singleton(live, game, cls)
        if p:
            return [p], "singleton"
    if not census:
        return [], "none"
    live.census(progress=progress, cancel=cancel)
    if cancel and cancel():
        return [], "none"
    if has_cache(live, game, cls):
        return live.instances(cls, limit=limit), "census"
    return [], "none"
