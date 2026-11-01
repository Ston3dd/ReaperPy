"""item_check.py - Items TESTEN, bevor ein Trainer daraus gebaut wird (Logik ohne Oberflaeche, ohne Konsole testbar).

Zwei Stufen, beide fuer jedes Unreal-Spiel gleich:

  1) preflight()   NUR LESEN.  Prueft die Kette, an der ein Item-Trainer scheitern kann:
                     * Image-Basis liegt in der Speicherkarte
                     * Geben-Funktion im Spiel vorhanden, native Implementierung gefunden und ausfuehrbar
                     * `this` der Funktion erreichbar (PlayerController -> Zeiger -> Objekt, nicht 0)
                     * ProcessEvent-Haken (vtable-Slots) gefunden
                     * genug Platz fuer die Cave
                     * je Item: Name/FName/ID gueltig, FName stimmt mit dem Namenspool DIESER Sitzung ueberein
  2) live_probe()  SCHREIBT kurz ins Spiel.  Baut aus den Items eine Test-Cave (je Item ein Schalter), haengt den
                   Haken ein, setzt nacheinander die Schalter und wartet, bis die Cave sie zuruecksetzt.  Das beweist
                   fuer jedes Item: Haken wird erreicht, Cave laeuft, die Funktion des Spiels wurde ohne Absturz
                   aufgerufen.  Der Haken wird IMMER wieder entfernt (auch bei Fehlern).  Ob das Item danach im Inventar
                   liegt, sieht nur der Mensch - die Oberflaeche fragt dafuer EINMAL nach.

Ergebnis je Item: status 'ok' | 'warn' | 'fail' + Gruende (leicht verstaendlich).
"""
import struct
import time
from dataclasses import dataclass, field

import cave_trainer as TR
import ue_cavegen as CG
import ue_items as IT

OK, WARN, FAIL = "ok", "warn", "fail"
MAX_PROBE = 60                       # so viele Items hoechstens je Live-Test (je Item ein Schalter)
PROBE_WAIT = 4.0                     # Sekunden, die auf das Zuruecksetzen eines Schalters gewartet wird
POLL = 0.05
ICON = {OK: "✔", WARN: "⚠", FAIL: "✗"}


@dataclass
class Check:
    name: str
    status: str
    text: str


@dataclass
class Result:
    status: str = OK
    reasons: list = field(default_factory=list)
    ran: bool = None                 # Live-Test: Cave hat den Schalter verbraucht (None = nicht getestet)

    def add(self, status, text):
        self.reasons.append(text)
        if status == FAIL or (status == WARN and self.status == OK):
            self.status = status

    @property
    def label(self):
        if self.ran is True and self.status != FAIL:
            return f"{ICON[OK]} läuft"
        if self.status == OK:
            return f"{ICON[OK]} ok"
        return f"{ICON[self.status]} " + (self.reasons[0] if self.reasons else "")[:60]


@dataclass
class Report:
    checks: list = field(default_factory=list)       # [Check] - gilt fuer ALLE Items
    results: list = field(default_factory=list)      # [Result] - je Item, gleiche Reihenfolge wie die Eingabe
    func_title: str = ""

    @property
    def blocking(self):
        """Ein Gesamt-Check ist gescheitert: KEIN Item kann mit dieser Funktion funktionieren."""
        return any(c.status == FAIL for c in self.checks)

    def counts(self):
        n = {OK: 0, WARN: 0, FAIL: 0}
        for r in self.results:
            n[r.status] += 1
        return n

    def text(self):
        lines = [f"Geben-Funktion: {self.func_title}"] if self.func_title else []
        lines += [f"  {ICON[c.status]} {c.name}: {c.text}" for c in self.checks]
        n = self.counts()
        lines.append(f"  Items: {n[OK]} ok, {n[WARN]} mit Hinweis, {n[FAIL]} nicht brauchbar")
        return "\n".join(lines)


def _u32(b):
    return struct.unpack("<I", b)[0]


def _readable(read, addr, n=16):
    try:
        data = bytes(read(addr, n))
    except Exception:  # noqa: BLE001
        return None
    return data if len(data) == n else None


def _prot(span, addr):
    for s, e, p in span:
        if s <= addr < e:
            return p
    return None


# ----------------------------------------------------------------------------------------------------------------
# 1) Vorab-Test (nur Lesen)
# ----------------------------------------------------------------------------------------------------------------
def _check_function(func, sdk, live, read, base, span, rep):
    """Gesamt-Checks der Geben-Funktion -> impl-Adresse oder None."""
    d = func.data
    title = f"{d.get('owner', '')}.{d.get('name', func.title)}"
    try:
        ent = live.function_entry(d["owner"], d["name"])
    except Exception as e:  # noqa: BLE001
        ent = None
        rep.checks.append(Check("Funktion im Spiel", FAIL, f"{title}: {e}"))
        return None
    if not ent:
        rep.checks.append(Check("Funktion im Spiel", FAIL,
                                f"{title} gibt es im laufenden Spiel nicht (Blueprint-Funktion oder anderer Build?)"))
        return None
    rep.checks.append(Check("Funktion im Spiel", OK, f"{title} gefunden"))
    impl = CG.find_impl(read, base, ent[0])
    if impl is None:
        rep.checks.append(Check("Native Implementierung", FAIL,
                                "Hinter der Funktion wurde kein normaler C++-Code erkannt (Blueprint/ungewohnter Thunk) - "
                                "dafür lässt sich keine feste Cave bauen. Andere Geben-Funktion wählen."))
        return None
    prot = _prot(span, impl)
    head = _readable(read, impl)
    if prot is None:
        rep.checks.append(Check("Native Implementierung", FAIL, f"{impl:#x} liegt nicht im Spiel-Image (Basis falsch?)"))
        return None
    if head is None:
        rep.checks.append(Check("Native Implementierung", FAIL, f"{impl:#x} ist nicht lesbar"))
        return None
    if not prot & 4:
        rep.checks.append(Check("Native Implementierung", FAIL, f"{impl:#x} liegt in keinem ausführbaren Bereich"))
        return None
    if set(head) <= {0, 0xCC}:
        rep.checks.append(Check("Native Implementierung", FAIL, f"{impl:#x} enthält keinen Code (nur Füllbytes)"))
        return None
    rep.checks.append(Check("Native Implementierung", OK, f"Code bei Basis+{impl - base:#x}"))
    return impl


def _check_this(func, sdk, live, read, rep, impl=None):
    d = func.data
    unused = CG.impl_ignores_this(read, impl) if impl else None
    mode, off, note = CG.choose_this(sdk, d.get("owner", ""), this_unused=unused)
    if unused and mode == "zero":
        rep.checks.append(Check("Objekt (this)", OK,
                                "Die Funktion liest this nie (aus dem Code erkannt) - der Trainer ruft sie direkt auf, "
                                f"{d.get('owner', '')} muss im Spiel nicht existieren."))
        return
    if mode == "hooked":
        rep.checks.append(Check("Objekt (this)", OK, "die Funktion gehört zum PlayerController selbst"))
        return
    if mode == "zero" and IT.live_object(live, read, d.get("owner", "")):
        rep.checks.append(Check("Objekt (this)", OK,
                                f"{d.get('owner', '')} ist im laufenden Spiel vorhanden - der Trainer ruft es über seine feste "
                                "Adresse auf (gilt nur bis zum Spielende; nach jedem Spielstart neu speichern)."))
        return
    if mode == "zero":
        rep.checks.append(Check("Objekt (this)", WARN,
                                "Der Trainer erreicht kein Objekt dieser Klasse (this = 0). Das klappt nur, wenn die "
                                "Funktion this nicht benutzt - sonst passiert nichts oder das Spiel stürzt ab."))
        return
    chain = list(off) if isinstance(off, (tuple, list)) else [off]
    try:
        pcs = [i["addr"] for i in live.instances("APlayerController") if "Default__" not in i["name"]]
    except Exception:  # noqa: BLE001
        pcs = []
    if not pcs:
        rep.checks.append(Check("Objekt (this)", FAIL, "Kein PlayerController im Spiel - Spielstand laden (nicht im Hauptmenü)."))
        return
    cur = pcs[0]
    for k, o in enumerate(chain):
        try:
            cur = struct.unpack("<Q", bytes(read(cur + o, 8)))[0]
        except Exception as e:  # noqa: BLE001
            rep.checks.append(Check("Objekt (this)", FAIL, f"Zeiger bei +{o:#x} nicht lesbar ({e})"))
            return
        if cur < 0x10000:
            rep.checks.append(Check("Objekt (this)", WARN,
                                    f"Der Zeiger zu {d.get('owner', '')} ist gerade 0 (Schritt {k + 1}). Der Trainer überspringt "
                                    "dann den Aufruf - Spielstand laden / im Spiel sein, dann erneut testen."))
            return
    rep.checks.append(Check("Objekt (this)", OK, f"{d.get('owner', '')} über den PlayerController erreichbar"))


def _check_hook(sdk, live, read, base, rep):
    try:
        pe, slots, notes = IT.hook_targets(sdk, live, read, base)
    except Exception as e:  # noqa: BLE001
        rep.checks.append(Check("Haken (ProcessEvent)", FAIL, str(e)))
        return None
    if not slots:
        why = "; ".join(notes[:2]) or "kein vtable-Slot zeigt auf ProcessEvent"
        who = _who_hooked(sdk, live, read, base, pe_hint=None)
        if who:
            why += "; " + who
        rep.checks.append(Check("Haken (ProcessEvent)", FAIL,
                                f"{why}. Ist schon ein Haken gesetzt? Erst die Trainer-BASIS ausschalten / Spiel neu starten."))
        return None
    rep.checks.append(Check("Haken (ProcessEvent)", OK, f"{len(slots)} vtable-Slot(s) gefunden"))
    return pe, slots


def _who_hooked(sdk, live, read, base, pe_hint=None):
    """Wohin zeigt der ProcessEvent-Slot des PlayerControllers statt auf ProcessEvent?  -> Text oder ''.
    Haeufigster Grund: ein frueherer Trainer ist noch eingehaengt (z. B. von GoldHEN/etaHEN beim Spielstart geladen)."""
    try:
        pidx = sdk.offset("process_event_index", "processeventindex", default=77)
        objs = [i["addr"] for i in live.instances("APlayerController") if "Default__" not in i["name"]]
        vt = struct.unpack("<Q", bytes(read(objs[0], 8)))[0]
        cur = struct.unpack("<Q", bytes(read(vt + pidx * 8, 8)))[0]
    except Exception:  # noqa: BLE001
        return ""
    if base <= cur < base + 0x2000_0000:
        return (f"der ProcessEvent-Slot zeigt auf Code bei Basis+{cur - base:#x} - dort hängt schon ein anderer Trainer/Cheat "
                "(bei einem frischen Spielstart: ein GoldHEN/etaHEN-Cheat dieses Spiels ist aktiv und muss ausgeschaltet werden)")
    return ""


def _check_room(n_items, maps, base, read, rep, log):
    try:
        cap = TR.capacity(read, maps, base, log=log)
    except Exception as e:  # noqa: BLE001
        rep.checks.append(Check("Platz für die Cave", FAIL, str(e)))
        return
    per = IT.rows_per_project(cap["code"])
    if cap["code"] <= 0:
        rep.checks.append(Check("Platz für die Cave", FAIL,
                                "Im Spiel-Image ist kein freier Code-Platz (Padding) für eine Cave. Ein anderer Cheat/ein "
                                "Plugin belegt ihn oder dieser Spielstand hat keine Lücke - BASIS anderer Trainer ausschalten "
                                "oder das Spiel neu starten."))
    elif cap["data"] < 8:
        rep.checks.append(Check("Platz für die Cave", FAIL, "Kein beschreibbarer Leerraum für die Schalter im Spiel-Image."))
    elif n_items > per:
        rep.checks.append(Check("Platz für die Cave", WARN,
                                f"Frei: {cap['code']} Byte = ca. {per} Items je Projekt; bei {n_items} Items entstehen mehrere "
                                "Projekte (immer nur EINES gleichzeitig aktivieren)."))
    else:
        rep.checks.append(Check("Platz für die Cave", OK, f"{cap['code']} Byte frei (reicht für ca. {per} Items)"))


def _check_item(it, id_kind, live, res):
    name = str(it.get("name", "")).strip()
    if not name or name.lower() in ("none", "null"):
        res.add(FAIL, "kein gültiger Name")
        return
    fn = it.get("fname")
    if id_kind == "int":
        if it.get("id") is None:
            res.add(FAIL, "keine Zahlen-ID in der Tabelle")
        return
    if not isinstance(fn, (bytes, bytearray)) or len(fn) != 8:
        res.add(FAIL, "FName hat nicht 8 Byte")
        return
    idx, num = _u32(bytes(fn[:4])), _u32(bytes(fn[4:]))
    if idx == 0:
        res.add(FAIL, "FName ist 'None'")
        return
    try:
        txt = live.fname_str(idx, num)
    except Exception as e:  # noqa: BLE001
        res.add(WARN, f"FName im Namenspool nicht lesbar ({e})")
        return
    if str(txt).startswith("<name"):
        res.add(FAIL, "FName zeigt ins Leere (Namenspool passt nicht zu dieser Sitzung)")
    elif str(txt) != name:
        res.add(FAIL, f"FName gehört zu '{txt}', nicht zu '{name}' (Tabelle veraltet - ITEMS FINDEN erneut)")


def preflight(items, func, sdk, live, read, base, maps, log=lambda _m: None):
    """Nur LESEN.  items = [Item-Dicts aus ue_items], func = Vorschlag (Suggestion) der Geben-Funktion
    -> Report (checks fuer alle, results je Item)."""
    rep = Report(func_title=f"{func.data.get('owner', '')}.{func.data.get('name', func.title)}")
    span = TR.image_span(maps, base)
    if not span:
        rep.checks.append(Check("Image-Basis", FAIL, f"Die Basis {base:#x} liegt in keiner Speicherregion (falsche Basis?)"))
    else:
        rep.checks.append(Check("Image-Basis", OK, f"{base:#x} liegt im Spiel-Image"))
    id_kind = "fname"
    try:
        ida = IT.id_param(func, sdk)
        id_kind = ida["kind"] if ida else "fname"
    except Exception:  # noqa: BLE001
        pass
    if span:
        impl = _check_function(func, sdk, live, read, base, span, rep)
        _check_this(func, sdk, live, read, rep, impl)
        _check_hook(sdk, live, read, base, rep)
        _check_room(len(items), maps, base, read, rep, log)
    for it in items:
        res = Result()
        if rep.blocking:
            res.add(FAIL, "Gesamttest gescheitert (siehe oben)")
        else:
            _check_item(it, id_kind, live, res)
        rep.results.append(res)
    return rep


# ----------------------------------------------------------------------------------------------------------------
# 2) Live-Test (schreibt kurz ins Spiel, entfernt den Haken IMMER wieder)
# ----------------------------------------------------------------------------------------------------------------
def probe_indices(items, results, limit=MAX_PROBE):
    """Welche Items sollen live getestet werden: nicht gescheiterte, hoechstens `limit`."""
    return [i for i, r in enumerate(results) if r.status != FAIL][:limit]


def live_probe(items, results, func, sdk, live, read, write, base, maps, amount, client=None,
               log=lambda _m: None, wait=PROBE_WAIT, tick=None, progress=None):
    """Je Item ein Schalter in einer Test-Cave.  Setzt das Ergebnis `ran` (True/False) und erweitert die Gruende.
    tick(): optionaler Aufruf in jeder Warte-Runde (Tests simulieren damit den Spiel-Thread).
    -> Anzahl der Items, deren Schalter von der Cave verbraucht wurde.  Wirft TrainerError, wenn gar nicht
    getestet werden kann (Haken belegt, kein Platz ...) - dann wurde nichts veraendert."""
    idx = probe_indices(items, results)
    if not idx:
        return 0
    pkgs = [(f"T{k + 1}", [items[i]]) for k, i in enumerate(idx)]
    options, _skipped = IT.make_options(pkgs, func, sdk, live, read, base, amount, log=log)
    if len(options) != len(idx):
        raise TR.TrainerError("Für einige Items ließ sich keine Test-Zeile bauen (ID fehlt).")
    pe, slots, _notes = IT.hook_targets(sdk, live, read, base)
    cap = TR.capacity(read, maps, base, log=log)
    groups = TR.fit_options(options, cap["code"], max_options=TR.MAX_OPTIONS)
    done, pos = 0, 0
    for g in groups:
        sub = idx[pos:pos + len(g)]
        pos += len(g)
        done += _probe_group(g, sub, results, read, write, base, maps, pe, slots, log, wait, tick, progress)
    return done


def _probe_group(options, sub, results, read, write, base, maps, pe, slots, log, wait, tick, progress):
    consumed = _run_options(options, read, write, base, maps, pe, slots, log, wait, tick, progress)
    ran = 0
    for ok_, i in zip(consumed, sub):
        results[i].ran = ok_
        if ok_:
            ran += 1
        else:
            results[i].add(WARN, "Die Cave wurde nicht ausgeführt (Spiel ruft ProcessEvent gerade nicht auf - "
                                 "im Spiel bewegen/Menü schließen und erneut testen)")
    return ran


def _run_options(options, read, write, base, maps, pe, slots, log, wait, tick, progress):
    """Eine kurze Cave mit allen `options` ins Spiel schreiben, je Eintrag den Schalter setzen und warten, bis die Cave ihn
    auf dem SPIEL-Thread verbraucht hat; der Haken wird IMMER wieder entfernt (die Cave bleibt stehen, siehe BASIS).
    -> [True/False je Eintrag: Schalter verbraucht]"""
    p = TR.plan(read, maps, base, options, None, pe, slots, log=log, settle=0.4)
    hooked = []
    out = []
    try:
        write(p.cave, p.cave_bytes)                                       # erst die Cave, dann der Haken
        if bytes(read(p.cave, len(p.cave_bytes))) != p.cave_bytes:
            raise TR.TrainerError("Die Test-Cave ließ sich nicht schreiben (Schreibschutz?).")
        for s in p.slots:
            write(s, struct.pack("<Q", p.cave))
            hooked.append(s)
        for k in range(len(options)):
            if progress:
                progress(k, len(options))
            write(p.flag_addr + k, b"\x01")
            end = time.monotonic() + wait
            consumed = False
            while True:
                if tick:
                    tick()
                if bytes(read(p.flag_addr + k, 1)) == b"\x00":
                    consumed = True
                    break
                if time.monotonic() >= end:
                    break
                time.sleep(POLL)
            out.append(consumed)
            if not consumed:
                write(p.flag_addr + k, b"\x00")
            time.sleep(0.15)                                              # der Aufruf soll fertig sein, bevor der naechste kommt
    finally:
        for s in hooked:                                                  # IMMER: Haken zurueck auf das echte ProcessEvent
            try:
                write(s, struct.pack("<Q", pe))
            except Exception as e:  # noqa: BLE001
                log(f"[test] Haken {s:#x} konnte nicht zurückgesetzt werden: {e}")
        time.sleep(0.2)
        try:
            write(p.flag_addr, bytes(p.flag_size))
        except Exception:  # noqa: BLE001
            pass
    return out


def give_via_cave(items, func, sdk, live, read, write, base, maps, amount, log=lambda _m: None, wait=PROBE_WAIT,
                  progress=None, tick=None):
    """Items SOFORT geben - aber nicht von einem fremden Thread aus, sondern ueber eine kurze Cave, die das Spiel selbst im
    ProcessEvent-Aufruf des PlayerControllers ausfuehrt (derselbe sichere Weg wie der Trainer; der direkte Aufruf von aussen
    bleibt nach 1-2 Items haengen).  Der Haken wird danach wieder entfernt.
    -> {'total','given','rejected': [],'skipped': [Name],'error': None|Text,'reach'}.
    Wirft TrainerError/ValueError, wenn dieser Weg gar nicht moeglich ist (dann wurde nichts veraendert)."""
    ida = IT.id_param(func, sdk)
    kind = ida["kind"] if ida else "fname"
    ok_items, bad = IT.usable(items, kind)
    if not ok_items:
        raise TR.TrainerError("Kein Item mit gültiger ID (Zahlen-ID fehlt in der Tabelle).")
    pkgs = [(f"G{n + 1}", ok_items[i:i + TR.PACK_SIZE]) for n, i in enumerate(range(0, len(ok_items), TR.PACK_SIZE))]
    options, _skipped = IT.make_options(pkgs, func, sdk, live, read, base, amount, log=log)
    if len(options) != len(pkgs):
        raise TR.TrainerError("Für einige Items ließ sich keine Zeile bauen (ID fehlt).")
    pe, slots, _notes = IT.hook_targets(sdk, live, read, base)
    cap = TR.capacity(read, maps, base, log=log)
    groups = TR.fit_options(options, cap["code"], max_options=TR.MAX_OPTIONS)
    res = {"total": len(items), "given": 0, "rejected": [], "skipped": [i["name"] for i in bad], "error": None,
           "reach": _reach(func, sdk, live, read, base)}
    pos = 0
    for n, g in enumerate(groups):
        pk = pkgs[pos:pos + len(g)]
        pos += len(g)
        try:
            consumed = _run_options(g, read, write, base, maps, pe, slots, log, wait, tick, progress)
        except Exception as e:  # noqa: BLE001
            if n == 0:
                raise                                               # nichts veraendert -> Aufrufer darf es anders versuchen
            res["error"] = str(e) or e.__class__.__name__
            break
        for ok_, (_name, its) in zip(consumed, pk):
            if ok_:
                res["given"] += len(its)
            else:
                res["error"] = ("Die Cave wurde für einen Teil der Items nicht ausgeführt (das Spiel ruft ProcessEvent gerade "
                                "nicht auf) - im Spiel bewegen / Menü schließen und die übrigen noch einmal geben.")
    return res


def run_expand(func, sdk, live, read, write, base, maps, log=lambda _m: None, wait=PROBE_WAIT, tick=None):
    """Parameterlose Erweiterungs-Funktion (Inventar/Slots auf Max) EINMAL auf dem Spiel-Thread ausfuehren (kurze Cave, Haken
    wird danach entfernt).  -> True, wenn die Cave gelaufen ist.  Wirft TrainerError/ValueError, wenn das nicht moeglich ist."""
    option = IT.make_expand_option(func, sdk, live, read, base, log)
    pe, slots, _notes = IT.hook_targets(sdk, live, read, base)
    return bool(_run_options([option], read, write, base, maps, pe, slots, log, wait, tick, None)[0])


def _reach(func, sdk, live, read, base):
    """Woher kommt `this` fuer diese Funktion ('hooked' | 'member' | 'zero' | 'unused')?"""
    d = func.data
    try:
        ent = live.function_entry(d["owner"], d["name"])
        impl = CG.find_impl(read, base, ent[0]) if ent else None
        unused = CG.impl_ignores_this(read, impl) if impl else None
    except Exception:  # noqa: BLE001
        unused = None
    mode = CG.choose_this(sdk, d.get("owner", ""), this_unused=unused)[0]
    if mode == "zero" and not unused and IT.live_object(live, read, d.get("owner", "")):
        return "abs"                                                      # Objekt im laufenden Spiel da: feste Adresse
    return "unused" if unused and mode == "zero" else mode


def apply_manual_answer(results, indices, worked):
    """Antwort auf 'Ist im Inventar etwas angekommen?' (fuer ein Beispiel-Item): Nein -> die Funktion wirkt nicht,
    also alle live getesteten Items mit Hinweis versehen."""
    if worked:
        return
    for i in indices:
        if results[i].ran:
            results[i].add(WARN, "Cave läuft, aber im Inventar kam nichts an (Funktion/Objekt passt vermutlich nicht)")
