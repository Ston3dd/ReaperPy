"""ue_quick.py - Logik fuer den Tab UE-LIVE (Wert anklicken -> Live-Daten -> aendern/einfrieren).

Keine Oberflaeche, kein Netzwerk-Code: alles bekommt read/write-Funktionen uebergeben und ist
deshalb ohne Konsole testbar.

  Target          ein anklickbarer UE-Wert (Klasse.Member, Offset, Typ, Bit)
  read_value      Rohwert + Anzeige lesen
  parse_input     Eingabetext -> neuer Wert  ('100', '0x10', '+50', '*2', 'an', 'aus')
  write_value     schreiben (Bitfelder per Lesen-Aendern-Schreiben)
  Freezer         haelt Werte fest (ein Bulk-Write je Tick)
  connect_live    GObjects/GNames im laufenden Spiel erkennen (mehrere Basisadressen probieren)
"""

import struct
from dataclasses import dataclass

PACK = {
    "float": "<f",
    "double": "<d",
    "int32": "<i",
    "int": "<i",
    "uint32": "<I",
    "int64": "<q",
    "uint64": "<Q",
    "int16": "<h",
    "uint16": "<H",
    "uint8": "<B",
    "int8": "<b",
    "bool": "<B",
    "int32_t": "<i",
    "uint32_t": "<I",
    "int64_t": "<q",
    "uint64_t": "<Q",
    "int16_t": "<h",
    "uint16_t": "<H",
    "uint8_t": "<B",
    "int8_t": "<b",
    "ffixedpoint64": "<q",
}
FIXED_SCALE = 1000  # FFixedPoint64.Value = Anzeigewert x 1000 (Palworld)
TRUE_WORDS = {"1", "an", "on", "true", "ja", "yes", "ein", "t", "y"}
FALSE_WORDS = {"0", "aus", "off", "false", "nein", "no", "f", "n"}


def norm_type(t):
    return (t or "").replace("struct ", "").replace("class ", "").replace(" ", "").lower()


@dataclass
class Target:
    cls: str
    member: str
    type: str
    offset: int
    bit: int = -1  # >= 0: Bitfeld-Bool (ein Bit eines Bytes)
    category: str = ""
    score: float = 0.0
    parent: str = ""  # Struct-Wrapper (z. B. GAS-Attribut): Name des Members im Objekt, member = "Health.CurrentValue"
    sub: int = 0  # Offset des Zahlenwerts im Struct (CurrentValue = 0xC)

    @property
    def key(self):
        return f"{self.cls}.{self.member}"

    @property
    def fmt(self):
        if self.bit >= 0:
            return "<B"
        return PACK.get(norm_type(self.type))

    @property
    def size(self):
        return struct.calcsize(self.fmt) if self.fmt else 0

    @property
    def is_bool(self):
        return self.bit >= 0 or norm_type(self.type) == "bool"

    @property
    def is_fixed(self):
        return norm_type(self.type) == "ffixedpoint64"

    @property
    def is_float(self):
        return self.fmt in ("<f", "<d")

    @property
    def writable(self):
        return self.fmt is not None


# Struct-Wrapper um Zahlenwerte (GAS FGameplayAttributeData, eigene FStat-Typen ...): automatische Erkennung in
# uestruct.py - kein Typ muss von Hand eingetragen werden.
def struct_fields(sdk, mtype):
    """-> [(Feldname, Offset, Typ)], wichtigstes Feld zuerst; [] = kein Wrapper."""
    import uestruct

    return uestruct.wrapper_fields(sdk, mtype)


def expand_member(sdk, cls, name, mtype, offset, bit=-1, category="", score=0.0):
    """Ein SDK-Member -> [Target].  Einfache Zahlentypen: ein Target; Wrapper-Structs: je Feld eines."""
    fields = struct_fields(sdk, mtype)
    if not fields:
        t = Target(cls, name, mtype, offset, bit, category, score)
        return [t] if t.writable else []
    return [
        Target(cls, f"{name}.{fname}", ftype, offset + foff, -1, category, score, parent=name, sub=foff)
        for fname, foff, ftype in fields
    ]


def targets_from_candidates(sdk, cands):
    """Candidate-Liste (uecheat) -> [Target] (nur Typen, die sich anzeigen/schreiben lassen)."""
    out = []
    for candidate in cands:
        member = sdk.find_member(candidate.cls, candidate.member) if sdk else None
        got = expand_member(
            sdk, candidate.cls, candidate.member, candidate.type, candidate.offset,
            member.bit if member else -1, candidate.category, candidate.score,
        )
        # Wrapper-Struct: in der Kandidatenliste nur das wichtigste Feld (CurrentValue/Value); Rest in der freien Suche
        out.extend(got[:1] if got and got[0].parent else got)
    return out


def targets_from_all_members(sdk):
    """ALLE schreibbaren Member jeder Klasse (nicht nur Cheat-Kandidaten) - fuer die freie Suche."""
    out = []
    for name, value in sdk.classes.items():
        for member in value.members:
            out.extend(expand_member(sdk, name, member.name, member.type, member.offset, member.bit, "alle"))
    return out


def decode(target, raw):
    """Rohbytes -> (Python-Wert, Anzeigetext).  Bitfeld: raw ist das Byte, Wert ist bool."""
    if target.bit >= 0:
        value = bool(raw[0] & (1 << target.bit))
        return value, ("AN" if value else "AUS")
    value = struct.unpack(target.fmt, raw[: target.size])[0]
    if target.is_bool:
        return bool(value), ("AN" if value else "AUS")
    if target.is_fixed:
        return value, f"{value / FIXED_SCALE:.6g}"
    if target.is_float:
        return value, ("nan" if value != value else f"{value:.6g}")
    return value, str(value)


def is_zero(v):
    return v is False or v == 0


def read_value(read, addr, t):
    return decode(t, read(addr, t.size))


def parse_input(target, text, current=None):
    """Eingabetext -> neuer Python-Wert.  '+50' / '*2' wirken relativ zum aktuellen Wert (current).
    Bool-Ziele: an/aus/1/0/true/false.  FixedPoint: Eingabe = Anzeigewert."""
    cleaned = (text or "").strip().replace(",", ".") if not target.is_bool else (text or "").strip().lower()
    if not cleaned:
        raise ValueError("Wert fehlt")
    if target.is_bool:
        if cleaned in TRUE_WORDS:
            return True
        if cleaned in FALSE_WORDS:
            return False
        raise ValueError("Bool: an/aus, 1/0, true/false")
    rel = None
    if cleaned[0] in "+*":
        rel, cleaned = cleaned[0], cleaned[1:].strip()
    elif cleaned[0] == "/":
        rel, cleaned = "/", cleaned[1:].strip()
    try:
        num = (
            float(cleaned)
            if (target.is_float or target.is_fixed or rel or "." in cleaned) and not cleaned.lower().startswith("0x")
            else int(cleaned, 0)
        )
    except ValueError:
        raise ValueError(f"'{text}' ist keine Zahl") from None
    if rel:
        if current is None:
            raise ValueError("relative Eingabe braucht einen gelesenen Wert")
        cur = current / FIXED_SCALE if target.is_fixed else current
        if rel == "/" and num == 0:
            raise ValueError("Division durch 0")
        num = cur + num if rel == "+" else (cur * num if rel == "*" else cur / num)
    if target.is_fixed:
        return int(round(num * FIXED_SCALE))
    if target.is_float:
        return float(num)
    return int(round(num))


def encode(target, value):
    """Python-Wert -> Bytes (ohne Bitfeld - dort siehe write_value)."""
    if target.is_bool:
        value = 1 if value else 0
    if target.is_float:
        if target.fmt == "<f" and abs(value) > 3.4028235e38 and value == value:
            raise ValueError("Wert zu gross fuer float")
        return struct.pack(target.fmt, value)
    try:
        return struct.pack(target.fmt, int(value))
    except struct.error:
        raise ValueError(f"{value} liegt ausserhalb des Bereichs von {target.type}") from None


def write_value(read, write, addr, target, value):
    """Schreibt einen Wert.  Bitfeld: das Byte lesen, nur das eine Bit aendern, zurueckschreiben."""
    if target.bit >= 0:
        cur = read(addr, 1)[0]
        new = (cur | (1 << target.bit)) if value else (cur & ~(1 << target.bit) & 0xFF)
        write(addr, bytes([new]))
        return bytes([new])
    data = encode(target, value)
    write(addr, data)
    return data


class Freezer:
    """Haelt Werte fest.  tick() schreibt alles in EINEM Bulk-Write (Bitfelder: erst Byte lesen)."""

    def __init__(self):
        self.items = {}  # addr -> (Target, Python-Wert)
        self._no_multi = False

    def __len__(self):
        return len(self.items)

    def __contains__(self, addr):
        return addr in self.items

    def add(self, addr, t, value):
        self.items[addr] = (t, value)

    def remove(self, addr):
        self.items.pop(addr, None)

    def clear(self):
        self.items.clear()

    def tick(self, client):
        """Alle eingefrorenen Werte schreiben.  -> Anzahl; Fehler einzelner Adressen stoppen nichts."""
        writes = []
        for addr, (target, value) in list(self.items.items()):
            try:
                if target.bit >= 0:
                    cur = client.read_memory(addr, 1)[0]
                    new = (cur | (1 << target.bit)) if value else (cur & ~(1 << target.bit) & 0xFF)
                    if new != cur:
                        writes.append((addr, bytes([new])))
                else:
                    writes.append((addr, encode(target, value)))
            except Exception:
                continue
        if not writes:
            return 0
        if not self._no_multi:
            try:
                import ps5_more

                ps5_more.write_multi(client, writes)
                return len(writes)
            except Exception:
                self._no_multi = True  # aeltere Payloads ohne write_multi
        for a, data in writes:
            try:
                client.write_memory(a, data)
            except Exception:
                pass
        return len(writes)


def connect_live(client, proj, log=print, cached=None):
    """UELive fuer das laufende Spiel bereitstellen (gleiche Strategie wie UE-AUTO: mehrere
    Basisadressen, absolute Adressen und Layout aus dump.bin.engine.json).  cached = vorheriges UELive."""
    import ue_live

    pid = getattr(client, "pid", None)
    if cached is not None and cached._read == client.read_memory and cached.arr:
        if getattr(cached, "pid", None) == pid:  # Spiel neu gestartet (neue PID) -> alles neu live suchen
            return cached
    bases = [proj.base]
    try:
        module_base = ue_live.live_module_base(client.get_maps())
        if module_base:
            bases.append(module_base)
    except Exception:
        pass
    live = ue_live.UELive(client.read_memory, proj.base, proj.sdk, log=log)
    live.pid = pid
    try:
        try:
            maps = client.get_maps()
        except Exception:
            maps = None
        live.setup(bases, maps=maps, **proj.live_args())
    except ue_live.UELiveError as error:
        raise RuntimeError(
            f"{error}\n(Spiel gestartet und Level/Spielstand geladen? Heap-Adressen aendern sich bei jedem Start.)"
        ) from None
    return live


def find_instances(live, t, limit=400):
    """Alle Live-Instanzen der Klasse von t -> [{addr, name, class, vaddr}] (Index wird einmal gebaut)."""
    if live.index is None:
        live.build_index()
    rows = []
    off = t.offset
    try:  # Offset live aus dem Spiel lesen (Header koennen zu einer anderen Version gehoeren)
        live_off = live.member_offset(t.cls, t.parent or t.member)
    except Exception:
        live_off = None
    if live_off is not None:
        live_off += t.sub
        off = live_off
    for i in live.instances(t.cls)[:limit]:
        rows.append(
            {
                "addr": i["addr"],
                "name": i["name"],
                "owner": i.get("owner", ""),
                "class": i["class"],
                "vaddr": i["addr"] + off,
                "off": off,
                "off_live": live_off is not None,
            }
        )
    return rows


def explain_no_instances(live, t):
    """Verstaendliche Begruendung, warum find_instances nichts liefert (Klasse fehlt vs. noch nicht erzeugt)."""
    if live.find_class(t.cls) is None:
        similar = live.similar_classes(t.cls)
        hint = f" Aehnliche Klassen im Spiel: {', '.join(similar)}." if similar else ""
        return (
            f"Die Klasse '{t.cls}' gibt es im laufenden Spiel nicht unter diesem Namen (SDK und Spiel-Version "
            f"passen evtl. nicht zusammen).{hint} Such links nach einem dieser Namen."
        )
    return (
        f"Die Klasse '{t.cls}' ist im Spiel vorhanden, aber es gibt noch kein Objekt davon "
        f"(nur Vorlage/Default). Meist wird sie erst im Spiel erzeugt: Spielstand/Level laden, "
        f"Charakter muss sichtbar sein, dann '↻ INSTANZEN NEU'."
    )


# Einfach-Modus: Zahl aus dem Spiel -> Treffer
