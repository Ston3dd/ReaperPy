"""unity_live.py - Items in einem LAUFENDEN Unity-Spiel sofort geben (ohne Trainer-Datei), Logik ohne Oberflaeche.

Die Geben-Methode (aus dump.cs) wird im Spiel aufgerufen (ps5_more.call): this = ein lebendes Objekt der Klasse
(Il2CppLive.instances), das Item (Enum-/Zahlenwert) und die Menge in den Argumentregistern (System V), das letzte
Argument (MethodInfo*) bleibt 0.  Nur Ganzzahl-/Enum-/Bool-Parameter sind moeglich - Kommazahlen, Texte und Objekte kann
ein Aufruf aus ReaperPy nicht liefern; solche Methoden werden schon bei der Suche abgelehnt bzw. hier klar gemeldet.

Das Ergebnis "getestet" (verified) merkt sich, welche Methoden wirklich Items gegeben haben: ok = +4, bad = -8 im Ranking.
"""
import ps5_more
import unity_items as U
import unity_objects as UO

VERIFIED_OK, VERIFIED_BAD = "ok", "bad"
BONUS = {VERIFIED_OK: 4.0, VERIFIED_BAD: -8.0}
MAX_TEST_ALL = 40                     # TEST CHECKED ITEMS: so viele angehakte Items hoechstens nacheinander


class LiveError(U.UnityTrainerError):
    pass


def give_key(give):
    m = give.method
    return f"{m.cls.full}.{m.name}({m.params})"


def rank_gives(gives, verified):
    """Geben-Methoden nach Score + 'getestet'-Bonus, beste zuerst (stabil)."""
    def s(g):
        return g.score + BONUS.get((verified or {}).get(give_key(g)), 0.0)
    return sorted(gives, key=lambda g: -s(g))


def register_args(give, this, item_value, amount):
    """-> {'rdi': .., 'rsi': ..} fuer ps5_more.call.  Reihenfolge: this (wenn nicht static), Parameter, MethodInfo*=0."""
    vals = [] if give.method.static else [this]
    for i, p in enumerate(give.params):
        if p["kind"] in ("float", "double"):
            raise LiveError(f"Parameter '{p['name']}' ist eine Kommazahl - das kann der Live-Aufruf nicht uebergeben")
        if i == give.id_i:
            vals.append(int(item_value))
        elif i == give.count_i:
            vals.append(int(amount))
        else:
            vals.append(0)
    vals.append(0)                                           # MethodInfo*
    if len(vals) > len(U.INT_REGS):
        raise LiveError("zu viele Parameter fuer die Argumentregister")
    return {U.INT_REGS[i][3]: v & 0xFFFFFFFFFFFFFFFF for i, v in enumerate(vals)}


def find_this(live, give, progress=None, cancel=None):
    """Adresse eines lebenden Objekts der Klasse der Geben-Methode (0 bei static).  Cache -> Singleton -> ein einziger Scan."""
    if give.method.static:
        return 0
    found, _how = UO.find(live, getattr(live, "game", None), give.method.cls, mode="any", limit=8, progress=progress,
                          cancel=cancel)
    if not found:
        raise LiveError(f"Kein lebendes Objekt der Klasse {give.method.cls.full} gefunden - im Spiel muss es gerade "
                        "existieren (Inventar/Spielwelt geladen, nicht im Hauptmenue)")
    return found[0]


def give_one(client, live, give, item_value, amount, this=None, progress=None, cancel=None):
    """Ein Item geben -> RAX der Methode.  this kann vorab ermittelt werden (find_this)."""
    this = find_this(live, give, progress, cancel) if this is None else this
    regs = register_args(give, this, item_value, amount)
    try:
        return ps5_more.call(client, live.base + give.method.rva, **regs)
    except ps5_more.MoreError as e:
        raise LiveError(str(e)) from e


def item_amount(it, default):
    """Menge dieses Items: eigene Menge (it['amount'], vom Nutzer gesetzt) oder die allgemeine."""
    a = it.get("amount")
    return int(a) if a else int(default)


def give_many(client, live, give, items, amount, progress=None, log=lambda _m: None, scan_progress=None, cancel=None):
    """Mehrere Items nacheinander -> (gegeben, [(Item, Fehlertext)]).  Beim ersten Verbindungs-/Aufruffehler Abbruch.
    Jedes Item nimmt seine eigene Menge (item_amount), sonst `amount`."""
    this = find_this(live, give, scan_progress, cancel)
    done, errors = 0, []
    for k, it in enumerate(items):
        try:
            give_one(client, live, give, it["id"], item_amount(it, amount), this)
            done += 1
        except LiveError as e:
            errors.append((it, str(e)))
            log(f"{it['name']}: {e}")
            break                                            # der Aufruf wird nie wiederholt, weitere wuerden dasselbe tun
        if progress:
            progress(k, len(items))
    return done, errors
