"""ue_profile.py - universeller Entdecker fuer JEDES Unreal-Spiel: schlaegt die gaengigen Cheat-Bausteine vor.

Dieses Modul erkennt die gaengigen Cheat-Bausteine aus dem SDK selbst - ohne spielspezifische Namen.  Alles ist ein VORSCHLAG mit Begruendung (kein Beweis); jede Zeile nennt ihre Belege.

  stat_enum      Enum mit Leben/Ausdauer/... (Stat-Array, TArray<float> je Enum-Wert)
  stat_array     Klassen-Member TArray<float|int>, der ueber so ein Enum indiziert sein koennte
  attribute_set  GAS (UAttributeSet / FGameplayAttributeData): Base/Current je Attribut
  item_struct    Struct/Klasse mit ID-Feld (FName, Int, GameplayTag, RowHandle ...) + Mengen-Feld (= ein Inventar-Eintrag),
                 dazu Slot-/Haltbarkeits-/Level-Felder und die Klassen, die ein TArray davon halten (= das Inventar)
  table          DataTable-Zeilenstruct (FTableRowBase), Rolle (Items, Shop, Loot, Skills ...), ID-Spalten,
                 Halter-Member (UDataTable*) und - falls ein GObjects-Dump geladen ist - die Tabellen-Objekte
  id_enum        Enums fuer Slots, Kategorien, Seltenheit, Waehrung, Ausruestungs-Platz
  slot_member    Member mit Slot-/Platz-IDs (SlotIndex, EquipSlot, PocketId ...)
  give_function  Funktionen wie AddItem(FName, int)/GiveItem(id, count)/AddMoney(...), mit Parameter-Form
  cheat_manager  UCheatManager-Unterklassen und ihre Debug-Funktionen (Gott, Fliegen, Teleport, XP ...)
  currency       Waehrungs-Member (Gold, Geld, Muenzen ...)

Danach (Live, nur lesend): `read_table` liest eine DataTable aus dem laufenden Spiel inkl. der 8-Byte-FNames je
Zeile (damit direkt als Funktionsargument/Trainer-Cave nutzbar) und decodiert die Spalten nach dem Zeilenstruct.

    python ue_profile.py <SDK_HEADERS-Ordner> [GObjects.txt] [-o BERICHT.md]
"""
from __future__ import annotations

import json
import re
import struct
import sys
from collections import defaultdict
from dataclasses import dataclass, field

FUNC_EXEC = 0x200

# --------------------------------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------------------------------
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
NUM_INT = {"int32", "int", "uint32", "int64", "uint64", "int16", "uint16", "uint8", "int8", "int32_t", "uint32_t",
           "int64_t", "uint64_t", "int16_t", "uint16_t", "uint8_t", "int8_t"}
NUM_FLOAT = {"float", "double", "float32"}
INT_FMT = {"int8": "<b", "uint8": "<B", "int16": "<h", "uint16": "<H", "int32": "<i", "int": "<i", "uint32": "<I",
           "int64": "<q", "uint64": "<Q", "float": "<f", "double": "<d"}
NOT_GAME = re.compile(r"widget|umg|slate|blueprintlibrary|kismet|montage|animinstance|animnotify|sequence|"
                      r"tooltip|thumbnail|icon|scrolllist|button|entrywidget|userwidget|editor|^uvr|niagara|"
                      r"navigation|landscape|foliage|decal|particle", re.I)


def words(name):
    return [w.lower() for w in _CAMEL.findall(str(name))]


def clean_type(t):
    t = re.sub(r"\b(?:struct|class|enum|const|TObjectPtr|volatile)\b", " ", str(t))
    t = re.sub(r"[*&]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def base_name(t):
    """'TArray<struct FItem>' -> 'TArray'; 'class UItem*' -> 'UItem'"""
    return re.split(r"[<\s]", clean_type(t), maxsplit=1)[0]


def inner_types(t):
    """Alle Typnamen innerhalb von <...> (flach): 'TMap<FName, struct FItem>' -> ['FName', 'FItem']"""
    t = str(t)
    if "<" not in t:
        return []
    inner = t[t.index("<") + 1:t.rindex(">")] if ">" in t else t[t.index("<") + 1:]
    out = []
    for part in re.split(r"[,<>]", inner):
        c = clean_type(part)
        if c:
            out.append(c.split()[-1])
    return out


def derives_from(sdk, name, base, limit=40):
    """Folgt den Eltern-Namen auch dann, wenn die Basisklasse selbst nicht im SDK steht (z. B. FTableRowBase)."""
    seen = set()
    cur = name
    for _ in range(limit):
        if cur == base:
            return True
        if not cur or cur in seen:
            return False
        seen.add(cur)
        c = sdk.classes.get(cur)
        if c is None:
            return False
        cur = c.parent
    return False


def split_args(text):
    """'struct FName A, TArray<float> B' -> [('struct FName','A'), ('TArray<float>','B')]"""
    parts, depth, cur = [], 0, ""
    for ch in text or "":
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    out = []
    for part in parts:
        m = re.match(r"^(?P<t>.+?)\s*(?P<n>[A-Za-z_]\w*)$", part.strip())
        out.append((m.group("t").strip(), m.group("n")) if m else (part.strip(), ""))
    return out


def class_functions(cls):
    """[(name, ret, args_text, flags, native)] - aus funcs (UE4SS/Kommentar-Stil) oder aus den Signaturzeilen (Dumper-7)."""
    out, seen = [], set()
    for f in getattr(cls, "funcs", []) or []:
        out.append((f.name, f.ret, f.args, f.flags, f.native))
        seen.add(f.name)
    for name, sig in getattr(cls, "functions", []) or []:
        if name in seen:
            continue
        m = re.match(r"^\s*(?:static\s+)?(?P<ret>[A-Za-z_][\w:<>\*&,\s]*?)\s+" + re.escape(name) + r"\((?P<args>[^;]*)\)", sig)
        out.append((name, m.group("ret").strip() if m else "", m.group("args").strip() if m else "", 0, None))
    return out


def _id_kind(mtype):
    """Wie ist so ein Feld als ID zu lesen?  -> 'fname' | 'int' | 'tag' | 'rowhandle' | 'primary' | 'string' | 'ref' | ''"""
    b = base_name(mtype)
    if b == "FName":
        return "fname"
    if b in NUM_INT:
        return "int"
    if b == "FGameplayTag":
        return "tag"
    if b == "FDataTableRowHandle":
        return "rowhandle"
    if b == "FPrimaryAssetId":
        return "primary"
    if b == "FString":
        return "string"
    if b in ("TSoftObjectPtr", "TSoftClassPtr", "TSubclassOf", "TSoftObjectPath"):
        return "ref"
    return ""


ID_NAME = re.compile(r"(?i)^(id|uid|guid|key|alias|rowname|name|tag|index|item)$|item.?(id|key|alias|name|index|row|tag|def|type|data)"
                     r"|(id|key|alias|rowname|handle)$")
COUNT_NAME = re.compile(r"(?i)^(count|quantity|qty|amount|num|number|stack|stacks|stackcount|itemcount|itemnum|"
                        r"itemquantity|itemamount|cnt)$|(count|quantity|amount|stack)$")
COUNT_BAD = re.compile(r"(?i)max|min|index|\bid\b|limit|capacity|total|rate|chance|weight|price|cost|cooldown|time")
SLOT_NAME = re.compile(r"(?i)slot|pocket|hotbar|quickbar|equip|socket|grid|position|column|row\b|inventoryindex|bagindex")
EXTRA_NAME = re.compile(r"(?i)durab|level|grade|tier|rarity|quality|enhanc|upgrade|ammo|charge|expir|bind|guid|lock|new$|isnew")
ITEM_WORDS = {"item", "inventory", "stack", "slot", "loot", "pickup", "entry", "content", "equipment", "consumable",
              "bag", "backpack", "container", "storage", "gear", "resource", "material"}


# --------------------------------------------------------------------------------------------------
# Ergebnis
# --------------------------------------------------------------------------------------------------
@dataclass
class Suggestion:
    kind: str
    title: str
    score: float
    detail: str = ""
    evidence: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    howto: str = ""

    def key(self):
        return f"{self.kind}:{self.title}"


@dataclass
class Profile:
    game: str = ""
    suggestions: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def of(self, *kinds):
        return [s for s in self.suggestions if s.kind in kinds]


HOWTO = {
    "stat_enum": "Spielwerte stehen als Array, der mit diesem Enum indiziert wird (Wert = Index).  Im Spiel Leben/Ausdauer "
                 "lesen, das Array im Speicher suchen (Wert-Suche) und den Eintrag je Enum-Index aendern.",
    "stat_array": "Dieser Member ist eine Liste von Zahlen - vermutlich die Werte je Stat-Enum-Eintrag.  UE-LIVE: Instanz "
                  "waehlen, Array-Adresse ansehen, Index = Enum-Wert.",
    "attribute_set": "GAS: je Attribut liegt FGameplayAttributeData (Base +0x8, Current +0xC) im AttributeSet.  UE-LIVE zeigt "
                     "sie als Klasse.Member.CurrentValue/BaseValue - dort setzen/einfrieren.",
    "item_struct": "Ein Inventar-Eintrag: ID-Feld + Mengen-Feld.  Die ID kommt aus der Item-Tabelle (siehe Tabellen).  "
                   "Live: Item geben/Menge im Spiel merken, nach der ID-Bytefolge + Menge suchen -> Mengenfeld aendern; "
                   "oder die Give-Funktion aus den Funktionen benutzen.",
    "table": "Tabellen-Browser: TABELLE LIVE LESEN zeigt Zeilen mit Namen, FName-Bytes (fuer Cave/Trainer) und Spalten "
             "(IDs, Preise, Kategorien).  Die Zeilen-Namen sind die Item-IDs des Spiels.",
    "id_enum": "Zahlen-IDs dieses Enums stehen in Item-/Slot-Feldern (Kategorie, Platz, Seltenheit).  Tabelle der Werte "
               "zeigt, welche Zahl welcher Slot/Kategorie ist.",
    "slot_member": "Feld mit Slot-/Platz-ID: bestimmt, wo ein Item im Inventar/der Ausruestung liegt.",
    "give_function": "Funktion zum Geben von Items/Waehrung.  Mit FName-Argument: Namen aus der Tabelle, FName-Bytes als "
                     "'hex:..'.  Aufruf ueber FUNKTION AUFRUFEN oder als Trainer mit CAVE-TRAINER EXPORTIEREN.",
    "cheat_manager": "Die Debug-Befehle des Entwicklers sind im Spiel eingebaut (UCheatManager).  Meist per "
                     "Funktionsaufruf auf der CheatManager-Instanz des PlayerControllers nutzbar.",
    "currency": "Waehrung als direkter Zahlen-Member: in UE-LIVE anklicken, Wert setzen/einfrieren.  Taucht sie nicht "
                "auf, ist sie vermutlich ein Item (siehe Item-Struct/Tabellen).",
}


def _sug(kind, title, score, detail="", evidence=None, data=None):
    return Suggestion(kind, title, round(float(score), 1), detail, list(evidence or []), dict(data or {}), HOWTO.get(kind, ""))


# --------------------------------------------------------------------------------------------------
# 1) Stats: Enum + Array, GAS
# --------------------------------------------------------------------------------------------------
STAT_ROLES = [
    ("hp", r"^(hp|health|life|vitality|hitpoint)$"),
    ("maxhp", r"^(max.?hp|max.?health|health.?max|hp.?max)$"),
    ("stamina", r"stamina|endurance|energy"),
    ("mana", r"^(mp|mana|magic|focus|spirit)$|max.?mana"),
    ("shield", r"shield|armor|armour|defen[sc]e|guard|poise"),
    ("speed", r"speed|haste|agility"),
    ("damage", r"attack|damage|power|strength|crit"),
    ("level", r"^(level|lv|lvl|rank)$|exp|xp|experience|skill.?point|^sp$"),
    ("resource", r"hunger|thirst|oxygen|fuel|ammo|gauge|rage|burst"),
]
STAT_ENUM_NAME = re.compile(r"(?i)stat|attrib|parameter|param|property|status|ability.?value")


def _enum_entries(enum):
    out = []
    for name, val in enum.values:
        key = name.split("_", 1)[-1] if "_" in name else name
        out.append((val, name, key))
    return out


def find_stat_enums(sdk):
    out = []
    for ename, enum in sdk.enums.items():
        entries = _enum_entries(enum)
        if len(entries) < 4:
            continue
        roles = defaultdict(list)
        for val, name, key in entries:
            for role, rx in STAT_ROLES:
                if re.search(rx, key.replace("_", " ").strip(), re.I) or re.search(rx, "".join(words(key)), re.I):
                    roles[role].append((val, name))
                    break
        n_roles = len(roles)
        named = bool(STAT_ENUM_NAME.search(ename))
        if n_roles < 3 or not ("hp" in roles or "maxhp" in roles or n_roles >= 4):
            continue
        score = 3 + n_roles * 0.9 + (2 if named else 0) + (1.5 if "hp" in roles and "maxhp" in roles else 0)
        count = next((v for v, n, _k in entries if re.search(r"(?i)(^|_)(num|count)$", n)), len(entries))
        sample = [(v, n) for lst in roles.values() for v, n in lst][:12]
        out.append(_sug("stat_enum", ename, min(score, 10),
                        f"{len(entries)} Werte, Rollen: {', '.join(sorted(roles))}",
                        [f"{n}={v}" for v, n in sample],
                        {"enum": ename, "count": count, "roles": {r: l[:4] for r, l in roles.items()}}))
    return sorted(out, key=lambda s: -s.score)


def find_stat_arrays(sdk, stat_enums):
    out = []
    enum_names = [s.title for s in stat_enums]
    for cname, cls in sdk.classes.items():
        if NOT_GAME.search(cname):
            continue
        for m in cls.members:
            if base_name(m.type) != "TArray":
                continue
            inner = inner_types(m.type)
            if not inner or inner[0] not in NUM_FLOAT | NUM_INT | {"FFixedPoint64", "FFixedPoint"}:
                continue
            w = words(m.name)
            hit = any(x in w for x in ("stat", "stats", "attribute", "attributes", "status", "values", "param", "params"))
            if not hit and not (enum_names and re.search(r"(?i)stat|attrib", cname)):
                continue
            score = 3 + (3 if hit else 0) + (1.5 if re.search(r"(?i)character|pawn|actor|player|state|stat", cname) else 0)
            via = ""
            for fname, _r, args, _fl, _n in class_functions(cls):
                for t, _a in split_args(args):
                    if clean_type(t) in enum_names:
                        via = clean_type(t)
            if via:
                score += 2
            elif enum_names:
                via = enum_names[0]
            out.append(_sug("stat_array", f"{cname}.{m.name}", min(score, 10),
                            f"TArray<{inner[0]}> @+{m.offset:#x}" + (f", Index-Enum {via}" if via else ""),
                            [f"Member {m.type} @+{m.offset:#x}"] + ([f"Funktion mit Enum-Parameter {via}"] if via else []),
                            {"owner": cname, "member": m.name, "offset": m.offset, "elem": inner[0], "enum": via}))
    return sorted(out, key=lambda s: -s.score)[:15]


def find_attribute_sets(sdk):
    out = []
    for cname, cls in sdk.classes.items():
        attrs = [m for m in cls.members if base_name(m.type) == "FGameplayAttributeData"]
        if not attrs:
            continue
        out.append(_sug("attribute_set", cname, 6 + min(3, len(attrs) * 0.3),
                        f"{len(attrs)} GAS-Attribute: " + ", ".join(m.name for m in attrs[:6]),
                        [f"{m.name} @+{m.offset:#x} (Base +{m.offset + 8:#x}, Current +{m.offset + 12:#x})" for m in attrs[:8]],
                        {"owner": cname, "attrs": [(m.name, m.offset) for m in attrs]}))
    return sorted(out, key=lambda s: -s.score)


# --------------------------------------------------------------------------------------------------
# 2) Item-Structs + Container + Slots
# --------------------------------------------------------------------------------------------------
def _container_index(sdk):
    idx = defaultdict(list)
    for cname, cls in sdk.classes.items():
        for m in cls.members:
            if base_name(m.type) in ("TArray", "TMap", "TSet"):
                for t in inner_types(m.type):
                    idx[t].append((cname, m.name, m.offset, base_name(m.type)))
    return idx


def find_item_structs(sdk, limit=25):
    containers = _container_index(sdk)
    out = []
    for cname, cls in sdk.classes.items():
        if NOT_GAME.search(cname):
            continue
        mem = [m for m in cls.members if m.owner == cname or not m.owner]
        if not mem or len(mem) > 80:
            continue
        ids, counts, slots, extras = [], [], [], []
        for m in mem:
            kind = _id_kind(m.type)
            if kind and ID_NAME.search(m.name) and not (kind == "int" and COUNT_NAME.search(m.name)):
                ids.append((m, kind))
            b = base_name(m.type)
            if (b in NUM_INT or b in NUM_FLOAT) and COUNT_NAME.search(m.name) and not COUNT_BAD.search(m.name):
                counts.append(m)
            if (b in NUM_INT or _id_kind(m.type) in ("fname",)) and SLOT_NAME.search(m.name) and not COUNT_NAME.search(m.name):
                slots.append(m)
            if EXTRA_NAME.search(m.name):
                extras.append(m)
        if not ids and not counts:
            continue
        w = set(words(cname))
        name_hit = bool(w & ITEM_WORDS)
        # bevorzugt: ID, die 'item' im Namen hat oder FName ist
        ids.sort(key=lambda x: (0 if "item" in x[0].name.lower() else 1, 0 if x[1] == "fname" else 1, x[0].offset))
        score = 0.0
        if ids:
            score += 3 + (1 if ids[0][1] in ("fname", "tag", "rowhandle") else 0)
        if counts:
            score += 3
        if name_hit:
            score += 2
        score += min(2.0, 0.5 * (len(slots) + len(extras)))
        cont = [c for c in containers.get(cname, []) if not NOT_GAME.search(c[0])]
        if cont:
            score += 2
        if cls.kind == "struct":
            score += 1
        if not (ids and counts):
            score = min(score, 4.5)
        if not name_hit and not (ids and counts):
            continue
        if score < 4:
            continue
        idm, idk = (ids[0] if ids else (None, ""))
        cm = counts[0] if counts else None
        ev = []
        if idm:
            ev.append(f"ID: {idm.name} ({idm.type}) @+{idm.offset:#x}")
        if cm:
            ev.append(f"Menge: {cm.name} ({cm.type}) @+{cm.offset:#x}")
        for m in slots[:3]:
            ev.append(f"Slot: {m.name} ({m.type}) @+{m.offset:#x}")
        for m in extras[:3]:
            ev.append(f"Zusatz: {m.name} ({m.type}) @+{m.offset:#x}")
        for o, mn, off, kind in cont[:3]:
            ev.append(f"Inventar-Liste: {o}.{mn} ({kind}) @+{off:#x}")
        mk = lambda m: {"name": m.name, "type": m.type, "offset": m.offset, "size": m.size} if m else None  # noqa: E731
        out.append(_sug("item_struct", cname, min(score, 10),
                        (f"ID {idm.name}({idk}) + Menge {cm.name}" if idm and cm else "Item-aehnlich (unvollstaendig)")
                        + (f", {len(cont)} Halter" if cont else ""), ev,
                        {"struct": cname, "kind": cls.kind, "id": dict(mk(idm), id_kind=idk) if idm else None,
                         "count": mk(cm), "slots": [mk(m) for m in slots[:4]], "extras": [mk(m) for m in extras[:4]],
                         "containers": [{"owner": o, "member": mn, "offset": off, "type": k} for o, mn, off, k in cont[:6]],
                         "size": cls.size}))
    return sorted(out, key=lambda s: -s.score)[:limit]


def find_slot_members(sdk, limit=30):
    agg = defaultdict(list)
    for cname, cls in sdk.classes.items():
        if NOT_GAME.search(cname):
            continue
        for m in cls.members:
            if m.owner not in ("", cname):
                continue
            b = base_name(m.type)
            if SLOT_NAME.search(m.name) and (b in NUM_INT or b == "FName" or b in {e for e in sdk.enums}):
                agg[m.name].append((cname, m))
    out = []
    for name, lst in agg.items():
        owners = [c for c, _m in lst]
        itemish = sum(1 for c in owners if set(words(c)) & ITEM_WORDS)
        score = 3 + min(3, len(owners) * 0.4) + min(3, itemish * 1.0)
        m0 = lst[0][1]
        out.append(_sug("slot_member", name, min(score, 9), f"{len(owners)}x, z. B. {', '.join(owners[:3])}",
                        [f"{c}.{m.name} ({m.type}) @+{m.offset:#x}" for c, m in lst[:5]],
                        {"name": name, "type": m0.type, "owners": [(c, m.offset) for c, m in lst[:20]]}))
    return sorted(out, key=lambda s: -s.score)[:limit]


ID_ENUM_ROLES = [
    ("slot", r"slot|pocket|equip|socket|hotbar|quickbar|gearslot|wearing"),
    ("kategorie", r"categor|itemtype|item.?kind|itemclass|itemgroup|inventorytype|bagtype"),
    ("seltenheit", r"rarity|quality|grade|tier"),
    ("waehrung", r"currency|money|coin|wallet"),
]


def find_id_enums(sdk, limit=30):
    out = []
    for ename, enum in sdk.enums.items():
        entries = _enum_entries(enum)
        if len(entries) < 2 or NOT_GAME.search(ename):
            continue
        for role, rx in ID_ENUM_ROLES:
            if re.search(rx, ename, re.I):
                vis = [(v, k) for v, _n, k in entries if k.lower() not in ("none", "max", "num", "count")]
                score = 4 + (1.5 if "item" in ename.lower() or "inventory" in ename.lower() else 0) + min(2, len(vis) / 8)
                out.append(_sug("id_enum", ename, min(score, 9), f"{role}, {len(vis)} Werte",
                                [f"{v} = {k}" for v, k in vis[:14]],
                                {"enum": ename, "role": role, "values": vis[:200]}))
                break
    return sorted(out, key=lambda s: -s.score)[:limit]


# --------------------------------------------------------------------------------------------------
# 3) Tabellen
# --------------------------------------------------------------------------------------------------
TABLE_ROLES = [
    ("Items", r"item|goods|ware|inventory|consumable|equipment|weapon|armor|gear|material"),
    ("Shop/Preise", r"shop|store|merchant|vendor|price|trade"),
    ("Loot/Drops", r"loot|drop|reward|chest|treasure"),
    ("Rezepte/Craft", r"recipe|craft|blueprint|cook|forge"),
    ("Skills/Talente", r"skill|talent|perk|ability|spell|tech"),
    ("Quests", r"quest|mission|objective|task"),
    ("Charaktere/Gegner", r"enemy|monster|npc|character|creature|pal|boss|spawn"),
    ("Waehrung", r"currency|money|coin"),
    ("Dialog/Text", r"dialog|dialogue|string|text|subtitle|localiz"),
]
TABLE_HOLDER = re.compile(r"DataTable|CompositeDataTable")


def _row_role(name, members):
    w = " ".join(words(name))
    for role, rx in TABLE_ROLES:
        if re.search(rx, w, re.I):
            return role
    cols = " ".join(words(" ".join(m.name for m in members)))
    for role, rx in TABLE_ROLES[:5]:
        if len(re.findall(rx, cols, re.I)) >= 2:
            return role
    return "Sonstiges"


def _table_objects(sdk):
    objs = defaultdict(list)
    for _idx, addr, typ, full in getattr(sdk, "gobjects", []) or []:
        if typ in ("DataTable", "CompositeDataTable") and "/Default__" not in full:
            objs[full.rsplit(".", 1)[-1]].append((addr, full))
    return objs


def _stem(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def _match_table_name(row_struct, table_names):
    rs = {_stem(w) for w in words(re.sub(r"^F", "", row_struct)) if w not in ("row", "table", "data", "property", "info")}
    best, bs = None, 0
    for tn in table_names:
        tw = {_stem(w) for w in words(tn) if w not in ("dt", "table", "data", "row", "datatable")}
        s = len(rs & tw)
        if s > bs:
            best, bs = tn, s
    return best if bs else None


def find_tables(sdk, limit=60):
    holders = defaultdict(list)
    for cname, cls in sdk.classes.items():
        if NOT_GAME.search(cname):
            continue
        for m in cls.members:
            t = m.type
            if TABLE_HOLDER.search(t) or base_name(t) == "FDataTableRowHandle":
                holders["*"].append((cname, m))
    tobjs = _table_objects(sdk)
    out = []
    for cname, cls in sdk.classes.items():
        if cls.kind != "struct" and not derives_from(sdk, cname, "FTableRowBase"):
            continue
        if not derives_from(sdk, cname, "FTableRowBase") or cname == "FTableRowBase":
            continue
        mem = [m for m in sdk.all_members(cname) if m.owner not in ("FTableRowBase",)]
        role = _row_role(cname, mem)
        idcols = [m for m in mem if _id_kind(m.type) in ("fname", "int", "tag") and ID_NAME.search(m.name)]
        mname = _match_table_name(cname, list(tobjs))
        score = 5 + (2 if role in ("Items", "Shop/Preise", "Loot/Drops", "Waehrung") else 1 if role != "Sonstiges" else 0)
        score += min(1.5, len(idcols) * 0.5) + (1 if mname else 0)
        ev = [f"{m.name} ({m.type}) @+{m.offset:#x}" for m in mem[:8]]
        if mname:
            ev.insert(0, f"Tabellen-Objekt im GObjects-Dump: {mname} ({tobjs[mname][0][0]:#x})")
        out.append(_sug("table", cname, min(score, 10), f"{role}, {len(mem)} Spalten" + (f", Tabelle {mname}" if mname else ""),
                        ev, {"row_struct": cname, "role": role, "table_name": mname,
                             "tables": [(a, f) for a, f in tobjs.get(mname, [])] if mname else [],
                             "columns": [(m.name, m.type, m.offset, m.size) for m in mem],
                             "id_columns": [m.name for m in idcols]}))
    # Tabellen ohne bekannte Zeilenstruct: nur nach Objektnamen
    used = {s.data["table_name"] for s in out if s.data.get("table_name")}
    for tn, lst in tobjs.items():
        if tn in used:
            continue
        role = next((r for r, rx in TABLE_ROLES if re.search(rx, " ".join(words(tn)), re.I)), "Sonstiges")
        out.append(_sug("table", tn, 4 + (1.5 if role != "Sonstiges" else 0), f"{role}, Zeilenstruct unbekannt (Objekt im Dump)",
                        [f"{a:#x} {f}" for a, f in lst[:3]],
                        {"row_struct": "", "role": role, "table_name": tn, "tables": list(lst), "columns": [], "id_columns": []}))
    # Halter am Ende als eigener Hinweis
    hold = holders.get("*", [])
    if hold:
        out.append(_sug("table", "Tabellen-Halter im SDK", 3,
                        f"{len(hold)} Member vom Typ DataTable/RowHandle",
                        [f"{c}.{m.name} ({m.type}) @+{m.offset:#x}" for c, m in hold[:10]],
                        {"row_struct": "", "role": "Halter", "table_name": "", "tables": [], "columns": [], "id_columns": [],
                         "holders": [(c, m.name, m.offset, m.type) for c, m in hold[:60]]}))
    return sorted(out, key=lambda s: -s.score)[:limit]


# --------------------------------------------------------------------------------------------------
# 4) Funktionen: Geben, Cheat-Manager
# --------------------------------------------------------------------------------------------------
GIVE_STRONG = re.compile(r"(?i)(add|give|grant|obtain|acquire|gain|receive|insert|spawn|award|pickup|collect)"
                         r".*(item|inventory|loot|gold|money|coin|currency|cash|credit|resource|material)"
                         r"|(item|inventory|gold|money|coin|currency|cash|credit).*(add|give|grant|obtain|get)")
GIVE_WEAK = re.compile(r"(?i)^(add|give|grant|obtain|acquire)(xp|exp|experience|level|skill|point|ammo)|^(set|add)(gold|money)")
GIVE_OWNER = [(r"(?i)cheat", 3.0), (r"(?i)inventory|bag|storage|backpack", 2.5), (r"(?i)playercontroller|playerstate|player", 1.5),
              (r"(?i)gameinstance|gamemode|gamestate|savegame|profile", 1.0)]
CHEAT_CATS = [
    ("Unverwundbar", r"god|invinc|immortal|mutek|nodamage|undying"),
    ("Fliegen/Geist", r"fly|ghost|walk$|noclip|spectate"),
    ("Teleport", r"teleport|warp|goto|setposition"),
    ("XP/Level", r"xp|exp|level|skill.?point|talent"),
    ("Items/Geld", r"item|gold|money|coin|currency|inventory|give|add"),
    ("Heilen/Ressourcen", r"heal|health|stamina|mana|refill|restore|revive"),
    ("Freischalten", r"unlock|complete|clear|achiev|all"),
    ("Zeit/Wetter", r"time|weather|day|night|speed|slomo"),
    ("Gegner/Spawn", r"kill|spawn|summon|enemy|damage"),
]


def _shape(params):
    """Parameterform: 'name+menge', 'id+menge', 'tag+menge', 'klasse+menge', 'name', 'id', 'menge', ''"""
    kinds = []
    for t, n in params:
        k = _id_kind(t)
        num = base_name(t) in NUM_INT | NUM_FLOAT
        cnt = num and bool(COUNT_NAME.search(n)) and not COUNT_BAD.search(n)
        kinds.append((k, num, cnt, n, t))
    has_count = any(c for _k, _n, c, *_ in kinds)
    named = [x for x in kinds if x[0] in ("fname", "string", "tag", "rowhandle", "primary")]
    idnum = [x for x in kinds if x[0] == "int" and ID_NAME.search(x[3]) and not x[2]]
    cls = [x for x in kinds if x[0] == "ref"]
    if named and has_count:
        return "name+menge"
    if idnum and has_count:
        return "id+menge"
    if cls and has_count:
        return "klasse+menge"
    if named and any(x[1] and not x[2] for x in kinds):
        return "name+zahl"
    if named:
        return "name"
    if idnum:
        return "id"
    if has_count or (len(kinds) == 1 and kinds[0][1]):
        return "menge"
    return ""


def find_give_functions(sdk, limit=30):
    out = []
    for cname, cls in sdk.classes.items():
        if NOT_GAME.search(cname) and "cheat" not in cname.lower():
            continue
        for fname, ret, args, flags, native in class_functions(cls):
            strong, weak = GIVE_STRONG.search(fname), GIVE_WEAK.search(fname)
            if not (strong or weak):
                continue
            params = split_args(args)
            shape = _shape(params)
            score = (4.5 if strong else 3.0)
            ev = [f"Name: {fname}"]
            for rx, bonus in GIVE_OWNER:
                if re.search(rx, cname):
                    score += bonus
                    ev.append(f"Klasse {cname}")
                    break
            if shape in ("name+menge", "id+menge", "klasse+menge"):
                score += 2.5 if shape == "name+menge" else 2.0
                ev.append(f"Form {shape}")
            elif shape:
                score += 0.5
            if flags & FUNC_EXEC:
                score += 1.0
                ev.append("Exec-Funktion (Konsolenbefehl)")
            if native:
                score += 0.5
                ev.append(f"native Adresse {native:#x}")
            out.append(_sug("give_function", f"{cname}.{fname}", min(score, 10),
                            f"({', '.join(f'{clean_type(t)} {n}' for t, n in params)}) -> {shape or 'unbekannte Form'}", ev,
                            {"owner": cname, "name": fname, "params": params, "shape": shape, "ret": ret, "flags": flags,
                             "native": native}))
    return sorted(out, key=lambda s: -s.score)[:limit]


def find_cheat_managers(sdk):
    out = []
    for cname, cls in sdk.classes.items():
        if not (derives_from(sdk, cname, "UCheatManager") or re.search(r"CheatManager$", cname)) or cname == "UCheatManager":
            continue
        funcs = class_functions(cls)
        if not funcs:
            continue
        cats = defaultdict(list)
        for fname, _ret, args, flags, _nat in funcs:
            for cat, rx in CHEAT_CATS:
                if re.search(rx, fname, re.I):
                    cats[cat].append(fname)
                    break
            else:
                cats["Sonstige"].append(fname)
        score = 6 + min(3, len(funcs) / 60) + (1 if cats.get("Items/Geld") else 0)
        out.append(_sug("cheat_manager", cname, min(score, 10), f"{len(funcs)} Funktionen",
                        [f"{c}: {', '.join(v[:4])}" + (" ..." if len(v) > 4 else "") for c, v in sorted(cats.items(), key=lambda x: -len(x[1]))[:8]],
                        {"class": cname, "count": len(funcs), "categories": {c: v[:60] for c, v in cats.items()}}))
    return sorted(out, key=lambda s: -s.score)


# --------------------------------------------------------------------------------------------------
# 5) Waehrung als Member
# --------------------------------------------------------------------------------------------------
CURRENCY_NAME = re.compile(r"(?i)(gold|money|coin|currency|cash|credit|souls?|shard|gems?|bucks|silver|crystal|wallet|bolts|zeni|yen)")
CURRENCY_BAD = re.compile(r"(?i)max|min|rate|multi|bonus|cost|price|chance|drop|reward|required|cap$|limit|text|name|icon|bIs|^b[A-Z]")


def find_currency_members(sdk, limit=15):
    out = []
    for cname, cls in sdk.classes.items():
        if NOT_GAME.search(cname):
            continue
        for m in cls.members:
            if m.owner not in ("", cname):
                continue
            b = base_name(m.type)
            if b not in NUM_INT | NUM_FLOAT | {"FFixedPoint64", "FFixedPoint"}:
                continue
            if CURRENCY_NAME.search(m.name) and not CURRENCY_BAD.search(m.name):
                score = 5 + (1.5 if re.search(r"(?i)player|state|save|wallet|inventory|profile|character", cname) else 0)
                out.append(_sug("currency", f"{cname}.{m.name}", min(score, 9), f"{m.type} @+{m.offset:#x}",
                                [f"Member {m.type} @+{m.offset:#x}"],
                                {"owner": cname, "member": m.name, "type": m.type, "offset": m.offset}))
    return sorted(out, key=lambda s: -s.score)[:limit]


# --------------------------------------------------------------------------------------------------
# Alles zusammen
# --------------------------------------------------------------------------------------------------
def game_name(sdk):
    for k in ("title", "name", "game", "GameName"):
        v = (getattr(sdk, "meta", {}) or {}).get(k)
        if v:
            return str(v)
    return ""


def build(sdk, progress=None):
    prof = Profile(game=game_name(sdk))
    steps = [
        ("stat_enum", lambda: find_stat_enums(sdk)),
        ("attribute_set", lambda: find_attribute_sets(sdk)),
        ("item_struct", lambda: find_item_structs(sdk)),
        ("table", lambda: find_tables(sdk)),
        ("id_enum", lambda: find_id_enums(sdk)),
        ("slot_member", lambda: find_slot_members(sdk)),
        ("give_function", lambda: find_give_functions(sdk)),
        ("cheat_manager", lambda: find_cheat_managers(sdk)),
        ("currency", lambda: find_currency_members(sdk)),
    ]
    sugs = []
    for i, (kind, fn) in enumerate(steps):
        if progress:
            progress(i, len(steps), kind)
        found = fn()
        prof.counts[kind] = len(found)
        sugs += found
        if kind == "stat_enum":
            arr = find_stat_arrays(sdk, found)
            prof.counts["stat_array"] = len(arr)
            sugs += arr
    prof.suggestions = sorted(sugs, key=lambda s: (-s.score, s.kind, s.title))
    prof.summary = {"klassen": len(sdk.classes), "enums": len(sdk.enums),
                    "mitglieder": sum(len(c.members) for c in sdk.classes.values())}
    if not sdk.classes:
        prof.notes.append("Das SDK enthaelt keine Klassen - Spielordner/Header geladen?")
    if not prof.of("item_struct", "table", "give_function", "cheat_manager", "currency"):
        prof.notes.append("Keine Item-/Tabellen-/Give-Hinweise gefunden: Das Spiel nutzt vermutlich eigene Namen. UE-LIVE "
                          "(Wert anklicken) und die freie Suche bleiben der Weg; die Namens-Suche unten kann Muster ergaenzen.")
    if not prof.of("table") and not getattr(sdk, "gobjects", None):
        prof.notes.append("Kein GObjects-Dump geladen: Tabellen-Objekte werden erst live (verbunden) gefunden.")
    return prof


def suggestions_for(profile, kind=None, min_score=0.0):
    return [s for s in profile.suggestions if (kind is None or s.kind == kind) and s.score >= min_score]


KIND_LABEL = {
    "stat_enum": "Stat-Enum", "stat_array": "Stat-Array", "attribute_set": "GAS-Attribute", "item_struct": "Item-Struct",
    "table": "Tabelle", "id_enum": "ID-/Slot-Enum", "slot_member": "Slot-Feld", "give_function": "Geben-Funktion",
    "cheat_manager": "Cheat-Manager", "currency": "Waehrung",
}


def render_markdown(profile, per_kind=12):
    L = [f"# UE-Entdecker{(' - ' + profile.game) if profile.game else ''}", "",
         f"{profile.summary.get('klassen', 0)} Klassen, {profile.summary.get('enums', 0)} Enums, "
         f"{profile.summary.get('mitglieder', 0)} Member.  Alles sind Vorschlaege mit Begruendung - keine Garantie.", ""]
    for n in profile.notes:
        L.append(f"> {n}")
    for kind, label in KIND_LABEL.items():
        items = [s for s in profile.suggestions if s.kind == kind][:per_kind]
        if not items:
            continue
        L += ["", f"## {label}", "", HOWTO.get(kind, ""), ""]
        for s in items:
            L.append(f"- **{s.title}** ({s.score}) - {s.detail}")
            for e in s.evidence[:5]:
                L.append(f"    - {e}")
    return "\n".join(L) + "\n"


def signature(sdk):
    """Kennzeichnet den SDK-Stand (Anzahl Klassen/Enums/Member + Funktionen) - gleiche Signatur = Zwischenspeicher gueltig."""
    nf = sum(len(getattr(c, "functions", []) or []) + len(getattr(c, "funcs", []) or []) for c in sdk.classes.values())
    return (f"{len(sdk.classes)}/{len(sdk.enums)}/{sum(len(c.members) for c in sdk.classes.values())}/{nf}/"
            f"{len(getattr(sdk, 'gobjects', []) or [])}")


def from_json(text):
    """Gegenstueck zu to_json (fuer den Zwischenspeicher); wirft ValueError bei kaputten Daten."""
    try:
        d = json.loads(text)
        prof = Profile(game=d.get("game", ""), counts=dict(d.get("counts", {})), notes=list(d.get("notes", [])),
                       summary=dict(d.get("summary", {})))
        for x in d["suggestions"]:
            prof.suggestions.append(Suggestion(x["kind"], x["title"], float(x["score"]), x.get("detail", ""),
                                               list(x.get("evidence", [])), dict(x.get("data", {})), HOWTO.get(x["kind"], "")))
        return prof
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as e:
        raise ValueError(f"Zwischenspeicher unbrauchbar: {e}")


def to_json(profile):
    return json.dumps({"game": profile.game, "counts": profile.counts, "notes": profile.notes, "summary": profile.summary,
                       "suggestions": [{"kind": s.kind, "title": s.title, "score": s.score, "detail": s.detail,
                                        "evidence": s.evidence, "data": s.data} for s in profile.suggestions]},
                      indent=2, ensure_ascii=False, default=str)


# --------------------------------------------------------------------------------------------------
# Live (nur lesend): DataTable lesen, Zeilen decodieren
# --------------------------------------------------------------------------------------------------
def find_table_objects(live, name_filter=None, limit=2000):
    """Alle DataTable-/CompositeDataTable-Objekte des laufenden Spiels -> [(addr, name)]"""
    if live.index is None:
        live.build_index()
    out = []
    for ptr, (_i, cl, nm) in live.index.items():
        try:
            cn = live.name(cl)
        except Exception:
            continue
        if cn not in ("DataTable", "CompositeDataTable"):
            continue
        if nm.startswith("Default__") or live.is_template(ptr):
            continue
        if name_filter and name_filter.lower() not in nm.lower():
            continue
        out.append((ptr, nm))
        if len(out) >= limit:
            break
    return sorted(out, key=lambda x: x[1].lower())


def decode_value(raw, mtype, fname_str=None):
    """Spaltenwert fuer die Vorschau: Zahlen, Bool, FName.  Unbekanntes -> '<typ>'."""
    b = base_name(mtype)
    try:
        if b == "FName" and fname_str and len(raw) >= 8:
            ix, nb = struct.unpack_from("<II", raw, 0)
            return "" if ix == 0 and nb == 0 else fname_str(ix, nb)
        if b == "bool":
            return bool(raw[0])
        fmt = INT_FMT.get(b)
        if fmt and len(raw) >= struct.calcsize(fmt):
            v = struct.unpack_from(fmt, raw, 0)[0]
            return round(v, 4) if isinstance(v, float) else v
    except Exception:
        return "?"
    return f"<{b}>"


def read_table(read, fname_str, table_obj, columns=None, limit=100000, max_columns=14):
    """-> (rows, columns).  rows = [{'name', 'fname_hex', 'row_ptr', 'values': {Spalte: Wert}}]
    columns = [(name, type, offset, size)] des Zeilenstructs (aus find_tables().data['columns']); ohne -> nur Namen."""
    import ue_tables as L
    trs = L.read_datatable_rows(read, fname_str, table_obj, limit=limit)
    cols = [c for c in (columns or []) if base_name(c[1]) in NUM_INT | NUM_FLOAT | {"FName", "bool"}][:max_columns]
    rows = []
    for r in trs:
        vals = {}
        for name, mtype, off, size in cols:
            try:
                vals[name] = decode_value(read(r.row_ptr + off, max(size, 1)), mtype, fname_str)
            except Exception:
                vals[name] = "?"
        rows.append({"name": r.name, "fname_hex": r.fname.hex(), "row_ptr": r.row_ptr, "values": vals})
    return rows, cols


def table_to_csv(rows, cols):
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Name", "FName(hex)"] + [c[0] for c in cols])
    for r in rows:
        w.writerow([r["name"], r["fname_hex"]] + [r["values"].get(c[0], "") for c in cols])
    return buf.getvalue()


def table_to_json(rows, cols, table_name=""):
    return json.dumps({"table": table_name, "columns": [c[0] for c in cols],
                       "rows": [{"name": r["name"], "fname": r["fname_hex"], **{k: v for k, v in r["values"].items()}} for r in rows]},
                      indent=1, ensure_ascii=False, default=str)


def best_table_for(suggestion, tables):
    """Zu einem 'table'-Vorschlag das passende Live-Objekt waehlen: [(addr, name)] -> (addr, name) oder None."""
    tn = suggestion.data.get("table_name") or ""
    if tn:
        for a, n in tables:
            if n == tn:
                return a, n
    rs = suggestion.data.get("row_struct") or suggestion.title
    best = _match_table_name(rs, [n for _a, n in tables])
    for a, n in tables:
        if n == best:
            return a, n
    return None


# --------------------------------------------------------------------------------------------------
# Live: Inventar-Eintraege (Item-Struct) im Speicher finden und die Menge aendern - fuer jedes Spiel
# --------------------------------------------------------------------------------------------------
@dataclass
class InstanceHit:
    base: int          # Adresse des Eintrags (Struct)
    name: str
    count: float
    count_addr: int
    count_type: str = "int32"


def id_pattern(id_kind, fname_bytes=None, number=None, size=4):
    """Bytefolge, nach der gesucht wird: FName -> die 8 Byte der Tabellenzeile; Int-ID -> Zahl."""
    if id_kind == "fname":
        if not fname_bytes or len(fname_bytes) != 8:
            raise ValueError("Fuer FName-IDs wird der 8-Byte-FName der Tabellenzeile gebraucht")
        return bytes(fname_bytes)
    if id_kind == "int":
        if number is None:
            raise ValueError("Fuer Zahlen-IDs die ID-Zahl angeben")
        return int(number).to_bytes(size, "little", signed=False)
    raise ValueError(f"ID-Art '{id_kind}' kann nicht per Byte-Suche gefunden werden (nur FName und Zahl)")


def find_instances(read, ranges, id_off, patterns, count_off, count_type="int32", count_value=None,
                   chunk=0x100000, max_hits=300, max_count=99_999_999):
    """Sucht Eintraege 'ID-Bytes @ +id_off, Menge @ +count_off'.  patterns = {bytes: Name}.
    Mit count_value (die Menge, die man im Spiel sieht) nur exakte Treffer; ohne nur plausible Mengen (1..max_count)."""
    fmt = INT_FMT.get(count_type)
    if fmt is None:
        raise ValueError(f"Mengen-Typ {count_type} wird nicht unterstuetzt")
    csz = struct.calcsize(fmt)
    hits = []
    for start, end in ranges:
        pos = start
        while pos < end and len(hits) < max_hits:
            n = min(chunk + 0x100, end - pos)
            try:
                buf = read(pos, n)
            except Exception:
                pos += chunk
                continue
            for key, name in patterns.items():
                i = buf.find(key)
                while i != -1 and i < chunk:
                    b = i - id_off
                    if b >= 0 and (pos + i) % 4 == 0 and b + count_off + csz <= len(buf):
                        cnt = struct.unpack_from(fmt, buf, b + count_off)[0]
                        ok = (cnt == count_value) if count_value is not None else (0 < cnt <= max_count)
                        if ok:
                            hits.append(InstanceHit(pos + b, name, cnt, pos + b + count_off, count_type))
                    i = buf.find(key, i + 1)
            pos += chunk
    seen, out = set(), []
    for h in hits:
        if h.count_addr not in seen:
            seen.add(h.count_addr)
            out.append(h)
    return out


def set_count(write, hit, value):
    """Schreibt die neue Menge (Typ des Treffers).  -> geschriebene Bytes"""
    fmt = INT_FMT[hit.count_type]
    data = struct.pack(fmt, float(value) if hit.count_type in ("float", "double") else int(value))
    write(hit.count_addr, data)
    return data


def main(argv=None):
    import argparse

    import uesdk
    ap = argparse.ArgumentParser(description="Universeller UE-Entdecker (statisch, aus dem SDK)")
    ap.add_argument("sdk")
    ap.add_argument("gobjects", nargs="?")
    ap.add_argument("-o", "--out")
    a = ap.parse_args(argv)
    sdk = uesdk.load(a.sdk, gobjects_path=a.gobjects)
    prof = build(sdk)
    text = render_markdown(prof)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
