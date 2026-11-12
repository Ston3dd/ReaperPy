"""unity_cheatmenu.py - Cheat-Menue fuer Unity/IL2CPP-Spiele, Gegenstueck zum Unreal-Menue (cheatmenu.py), ohne Oberflaeche.

Zwei Arten von Eintraegen, beide aus dump.cs:
  patch  Methode des Spiels (Schaden nehmen, Geld ausgeben, Ausdauer verbrauchen ...) - AN = Methode wird live ueberschrieben
         (Rueckgabe/leer), AUS = Originalbytes zurueck.  Dieselben Kandidaten wie im Tab WERTE UNITY.
  field  Zahlen-/Schalter-Feld einer Klasse (Health, Gold, Stamina ...) - AN = der Wert wird in allen lebenden Objekten der
         Klasse gesetzt und festgehalten, AUS = Originalwerte zurueck.

Code Cave: Zu jedem Feld laesst sich - wie bei Unreal - eine Cave bauen (cheatmenu_cave: welche Instruktion schreibt das Feld?);
zu jeder Methode ein fertiger .reapproj-Patch (values_auto.unity_patch_doc).
"""
import struct
from dataclasses import dataclass, field, replace

import il2cpp_dump as D
import unity_objects as UO
import uecheat as UC
import values_auto as VA

PER_CAT = 4
MAX_OBJECTS = 16                 # so viele lebende Objekte je Klasse werden beschrieben
FIELD_CATS = ("Leben", "Ausdauer", "Mana/Energie", "Schild/Rüstung", "Munition", "Währung", "Erfahrung", "Hunger/Durst")
SWITCH_WORDS = {"invincible", "invulnerable", "godmode", "god", "immortal", "infinite", "unlimited", "nodamage"}
_BAD_WORDS = UC.TIMEISH | {"max", "min", "regen", "regeneration", "multiplier", "mult", "cost", "ratio", "percent", "delay"}
DISPLAY = {"Währung": "Geld", "Erfahrung": VA.XP_CATEGORY}      # Kategorienamen wie im Tab WERTE UNITY
_NUM_PRIMS = {"int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64", "float", "double"}


class MenuError(ValueError):
    pass


@dataclass
class UEntry:
    key: str
    cat: str
    label: str
    kind: str                       # "patch" | "field"
    cls: str = ""                   # nur field: voller Klassenname
    member: str = ""
    type: str = ""                  # primitiver Typ (float, int32, bool ...)
    offset: int = -1
    cls_obj: object = None
    cand: object = None             # nur patch: values_auto.Candidate
    default: str = "auto"
    toggle: bool = False            # Schalter (bool-Feld) statt Zahl
    score: float = 0.0
    warn: str = ""
    active: bool = False
    status: str = ""
    orig: dict = field(default_factory=dict)         # Adresse -> Originalbytes
    held: bool = False
    held_bytes: bytes = b""
    note: str = ""
    hidden: bool = False
    # --- Felder, die cheatmenu_cave von einem Eintrag erwartet ---
    bit: int = -1
    source: str = "spiel"
    target: object = None
    on: object = True
    off: object = False

    @property
    def ok(self):
        return not self.status


# --------------------------------------------------------------------------------------------------
def _score_field(cls, f, cat, words):
    s = 10.0 + (4 if VA.PLAYERISH.search(cls.full) else 0) - (6 if VA.ENEMYISH.search(cls.full) else 0)
    if (cls.image or "").startswith("Assembly-CSharp"):
        s += 3
    if any(w in ("current", "cur", "now") for w in words):
        s += 2
    return s


def field_entries(game, per_cat=PER_CAT):
    """Felder, deren Name nach Leben/Ausdauer/Geld/Erfahrung ... klingt -> [UEntry], je Kategorie die besten zuerst."""
    found = {}
    for c in game.classes:
        if c.kind != "class" or D.is_generated(c) or "<" in c.name:
            continue
        for f in c.fields:
            if f.static or f.offset <= 0 or f.prim not in _NUM_PRIMS | {"bool"}:
                continue
            w = UC.words(f.name)
            if not w or any(x in _BAD_WORDS for x in w):
                continue
            if f.prim == "bool":
                if not SWITCH_WORDS & set(w):
                    continue
                cat = "Schalter"
            else:
                cat = next((k for k in FIELD_CATS if (UC.CATEGORIES.get(k) or ({},))[0] & set(w)), None)
                if cat == "Währung" and set(w) & UC.POINT_OWNERS:
                    cat = "Erfahrung"                  # SkillPoints/PerkPoints: Erfahrung, kein Geld
                if cat is None:
                    continue
            cat = DISPLAY.get(cat, cat)
            e = UEntry(key=f"{c.full}.{f.name}@{f.offset:x}", cat=cat, label=f"{c.full}.{f.name}", kind="field", cls=c.full,
                       member=f.name, type=f.prim, offset=f.offset, cls_obj=c, toggle=f.prim == "bool",
                       default="1" if f.prim == "bool" else (VA.XP_DEFAULT if cat == VA.XP_CATEGORY else VA.FORCE_DEFAULTS.get(cat, "9999")),
                       score=_score_field(c, f, cat, w),
                       warn="Klassenname sieht nach Gegner aus - betrifft auch Gegner" if VA.ENEMYISH.search(c.full) else "")
            found.setdefault(cat, []).append(e)
    out = []
    for cat in ("Schalter",) + tuple(DISPLAY.get(k, k) for k in FIELD_CATS):
        out += sorted(found.get(cat, []), key=lambda e: (-e.score, e.label))[:per_cat]
    return out


def patch_entries(game, per_cat=VA.UNITY_PER_CAT):
    out = []
    for c in VA.find_unity_candidates(game, per_cat):
        out.append(UEntry(key=c.key, cat=c.cat, label=f"{c.label}  [{c.effect}]", kind="patch", cand=c, score=c.score,
                          warn=c.warn))
    return out


def build_entries(game, per_cat=PER_CAT):
    """Alle Eintraege: erst Methoden-Patches, dann Felder (nach Kategorie sortiert)."""
    ents = patch_entries(game) + field_entries(game, per_cat)
    order = {c: i for i, c in enumerate(VA.CATEGORY_ORDER + ["Schalter"])}
    ents.sort(key=lambda e: (order.get(e.cat, 99), e.kind != "patch", -e.score))
    return ents


# --------------------------------------------------------------------------------------------------
def encode(type_name, text, default=""):
    """'999' -> Bytes passend zum Feldtyp; 'auto' = Vorgabe des Eintrags."""
    t = (text or "").strip().lower()
    if t in UC_AUTO:
        t = default
    try:
        if type_name == "float":
            return struct.pack("<f", float(t))
        if type_name == "double":
            return struct.pack("<d", float(t))
        if type_name == "bool":
            return b"\x01" if t not in ("0", "false", "aus", "off") else b"\x00"
        size = D.SIZES[type_name]
        v = int(float(t)) if "." in t else int(t, 0)
        return (v & ((1 << (8 * size)) - 1)).to_bytes(size, "little")
    except (ValueError, KeyError, struct.error) as e:
        raise MenuError(f"'{text}' ist keine passende Zahl fuer {type_name}") from e


UC_AUTO = ("", "auto", "max")


class UnityMenu:
    """Live-Seite: schreibt/haelt die Werte.  live = il2cpp_dump.Il2CppLive, client = Konsole."""

    def __init__(self, game, client, live, entries=None, log=print):
        self.game, self.client, self.live, self.log = game, client, live, log
        self.entries = entries if entries is not None else build_entries(game)
        self.by_key = {e.key: e for e in self.entries}
        self._seen = {}                                   # Klasse -> Objektadressen (nicht bei jedem Eintrag neu suchen)
        self.progress = self.cancel = None                # vom Tab gesetzt: Scan-Fortschritt / Abbruch

    def _alive(self, e, addr):
        """Steht an addr noch ein Objekt der Klasse? (Klassenzeiger lesbar und unveraendert)"""
        try:
            kps = {k for k in (self.live.klass_ptr(c, by_name=(c is e.cls_obj)) for c in self.game.family(e.cls_obj, cap=24)) if k}
            return bool(kps) and self.live._header_ok(addr, kps)
        except Exception:  # noqa: BLE001
            return True                                    # Ersatz-Live ohne Pruefung: Adresse behalten

    # -- Methoden-Patch ----------------------------------------------------------------------------
    def _patch_on(self, e):
        c = e.cand
        new = D.make_patch(c.method, c.mode, c.value)
        addr = self.live.method_addr(c.method)
        orig = bytes(self.client.read_memory(addr, len(new)))
        if orig == new or orig[:1] == b"\xc3":
            raise MenuError("Die Methode ist schon gepatcht/leer - erst alle Patches ausschalten")
        self.client.write_memory(addr, new)
        e.orig = {addr: orig}

    # -- Feld ------------------------------------------------------------------------------------------
    def objects(self, e, progress=None, cancel=None):
        """Lebende Objekte der Klasse: erst die schon bekannten (kurz geprueft), sonst Cache/Singleton/ein einziger Scan."""
        known = [a for a in self._seen.get(e.cls, ()) if self._alive(e, a)]
        if known:
            return known
        objs, _how = UO.find(self.live, self.game, e.cls_obj, mode="any", limit=MAX_OBJECTS, progress=progress, cancel=cancel)
        self._seen[e.cls] = list(objs)
        if not objs:
            raise MenuError(f"Kein lebendes Objekt der Klasse {e.cls} gefunden - im Spiel muss es gerade existieren")
        return objs

    def write_field(self, e, text=None, hold=True):
        data = encode(e.type, text if text is not None else e.default, e.default)
        n = 0
        for o in self.objects(e, self.progress, self.cancel):
            a = o + e.offset
            if a not in e.orig:
                e.orig[a] = bytes(self.client.read_memory(a, len(data)))
            self.client.write_memory(a, data)
            n += 1
        e.held, e.held_bytes, e.active = hold, data, True
        return n

    # -- AN / AUS --------------------------------------------------------------------------------------
    def set_on(self, e, text=None):
        if e.kind == "patch":
            self._patch_on(e)
            e.active = True
            return 1
        return self.write_field(e, "1" if e.toggle else text)

    def set_off(self, e):
        for a, b in list(e.orig.items()):
            try:
                self.client.write_memory(a, b)
            except Exception as ex:  # noqa: BLE001
                self.log(f"{e.label}: Zurueckschreiben bei {a:#x} fehlgeschlagen: {ex}")
        e.orig, e.held, e.active = {}, False, False

    def toggle(self, e):
        if e.active:
            self.set_off(e)
        else:
            self.set_on(e)
        return e.active

    def release_all(self):
        for e in self.entries:
            if e.active:
                self.set_off(e)

    def tick(self):
        """Festgehaltene Felder erneut schreiben (alle ~250 ms).  Fehler -> Eintrag freigeben und melden."""
        msgs = []
        for e in self.entries:
            if not (e.held and e.active):
                continue
            try:
                for a in e.orig:
                    self.client.write_memory(a, e.held_bytes)
            except Exception as ex:  # noqa: BLE001
                e.held = e.active = False
                msgs.append(f"{e.label}: Festhalten beendet ({ex})")
        return msgs


def entry_from_target(game, target, amount_text):
    """Beliebiges Feld aus dem MANUELL-Tab (ue_quick.Target) + feste Menge -> UEntry fuer die Cave.  Wirft MenuError mit
    verstaendlicher Meldung (statisches Feld, kein Zahlenfeld, Menge unpassend)."""
    cls = game.by_full.get(target.cls)
    if cls is None:
        raise MenuError(f"Klasse {target.cls} nicht im Dump")
    t = (target.type or "").lower()
    if t not in D.SIZES:
        raise MenuError(f"{target.key}: Typ {target.type} - eine Cave geht nur bei Zahlen-, Bool- und Enum-Feldern")
    if target.offset is None or target.offset <= 0 or getattr(target, "bit", -1) >= 0:
        raise MenuError(f"{target.key}: Feld ohne festen Objekt-Offset (statisch oder Bitfeld) - dafür gibt es keine Cave")
    encode(t, amount_text)                                  # Menge zum Typ pruefen (wirft MenuError)
    return UEntry(key=f"manuell:{target.key}@{target.offset:x}", cat="Manuell", label=target.key, kind="field", cls=cls.full,
                  member=target.member, type=t, offset=target.offset, cls_obj=cls, toggle=t == "bool",
                  default=str(amount_text).strip())


def cave_entry(e):
    """Feld-Eintrag in die Form, die cheatmenu_cave erwartet (kind 'value'/'toggle', Offset aus dump.cs)."""
    if e.kind != "field":
        raise MenuError("Code Cave gibt es nur fuer Felder - bei Methoden den fertigen Patch speichern (PATCH SPEICHERN)")
    return replace(e, kind="toggle" if e.toggle else "value")
