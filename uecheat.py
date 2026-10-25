"""uecheat.py - filtert aus einem SDK die cheat-relevanten Member und Funktionen.

Bewertet jeden Member nach Namen (CamelCase wird in Woerter zerlegt), Typ und Klasse.  Heuristik:
Treffer sind Kandidaten, keine Garantie - jede Zeile nennt ihre Gruende.
"""

import re
from dataclasses import dataclass, field

# Kategorie -> (Woerter, Gewicht, erlaubte Typen)
NUM = {
    "float",
    "double",
    "int32",
    "int",
    "int64",
    "uint32",
    "uint64",
    "int16",
    "uint16",
    "uint8",
    "int8",
    "int32_t",
    "float32",
    "int64_t",
    "uint32_t",
    "uint64_t",
    "int16_t",
    "uint16_t",
    "uint8_t",
    "int8_t",
    "ffixedpoint64",
    "ffixedpoint",
    "ffixedpoint32",
}  # Pal: FFixedPoint64 {int64 Value} (HP, SP ...)
BOOLS = {"bool", "uint8", "uint8_t"}
FIXED = {"ffixedpoint64", "ffixedpoint", "ffixedpoint32"}
BP_CLASS = re.compile(r"^[AU]?(WBP|ABP|BP|BPI|PRESET)_|_C$")
NOISE_CLASS = re.compile(r"^[AU]?(BT|GameFeature|GameNetworkManager|EnvQuery|MovieScene|Niagara|Behavior)")
DATA_CLASS = re.compile(r"(DatabaseRow|DataTable|DataStruct|MasterData|Row)$|^[AU]?\w*Static\w*(Data|Param\w*)$")
TIMEISH = {"time", "span", "timer", "duration", "interval", "delay", "seconds", "sec", "rate", "ratio"}
CATEGORIES = {
    "Cheat-Schalter": (
        {
            "muteki",
            "invincible",
            "invincibility",
            "godmode",
            "god",
            "immortal",
            "infinity",
            "infinite",
            "unlimited",
            "nodamage",
            "ignoredamage",
            "invulnerable",
            "immotal",  # Tippfehler im ARS-Plugin: bIsStatisticsImmotal
            "immune",
            "cheat",
            "freecraft",
            "nocost",
            "noconsume",
            "unbreakable",
            "freebuild",
            "noreload",
        },
        12,
        BOOLS,
    ),
    "Leben": ({"health", "hp", "hitpoints", "vitality", "hitpoint", "hitpts"}, 10, NUM),
    "Ausdauer": ({"stamina", "endurance", "sprint"}, 8, NUM),
    "Mana/Energie": ({"mana", "energy", "magic", "focus", "power", "ult", "ultimate", "rage"}, 7, NUM),
    "Schild/Rüstung": ({"shield", "armor", "armour", "defense", "defence", "barrier"}, 7, NUM),
    "Munition": ({"ammo", "ammunition", "clip", "magazine", "bullets", "rounds", "reserve", "mag"}, 9, NUM),
    "Währung": (
        {
            "money",
            "gold",
            "cash",
            "coins",
            "coin",
            "currency",
            "credits",
            "gems",
            "gem",
            "silver",
            "souls",
            "points",
            "scrap",
            "bolts",
            "wallet",
            "balance",
            "funds",
            "tokens",
        },
        9,
        NUM,
    ),
    "Erfahrung": ({"xp", "exp", "experience", "level", "skillpoints", "skillpoint", "talentpoints"}, 7, NUM),
    "Item-Menge": (
        {
            "quantity",
            "count",
            "amount",
            "stack",
            "stacksize",
            "stackcount",
            "numitems",
            "uses",
            "charges",
            "durability",
            "condition",
        },
        6,
        NUM,
    ),
    "Gewicht/Last": ({"weight", "encumbrance", "load", "carryweight", "capacity"}, 5, NUM),
    "Schaden/Werte": (
        {
            "damage",
            "dmg",
            "multiplier",
            "modifier",
            "speed",
            "jump",
            "firerate",
            "recoil",
            "spread",
            "range",
            "crit",
            "critical",
        },
        3,
        NUM,
    ),
    "Abklingzeit": ({"cooldown", "reload", "delay", "timer", "remaining", "interval"}, 4, NUM),
    "Treibstoff": ({"fuel", "oxygen", "air", "battery", "heat", "hunger", "thirst", "food", "water"}, 5, NUM),
}
MAXISH = {
    "max",
    "maximum",
    "base",
    "default",
    "initial",
    "regen",
    "regeneration",
    "rate",
    "percent",
    "ratio",
    "normalized",
    "pct",
    "min",
    "minimum",
    "size",
    "limit",
    "cap",
}
CUR = {"current", "cur", "now", "remaining", "value", "amount"}
GOOD_CLASS = (
    "character",
    "pawn",
    "playerstate",
    "playercontroller",
    "inventory",
    "weapon",
    "ammo",
    "item",
    "stats",
    "attribute",
    "health",
    "wallet",
    "currency",
    "resource",
    "player",
    "hero",
    "survival",
)
BAD_CLASS = (
    "widget",
    "umg",
    "slate",
    "anim",
    "niagara",
    "material",
    "audio",
    "sound",
    "movie",
    "mesh",
    "texture",
    "particle",
    "ui_",
    "hud",
    "brush",
    "style",
    "viewmodel",
    "settings",
    "config",
)
FUNC_WORDS = {
    "Schaden": ("takedamage", "applydamage", "receivedamage", "damage", "hit", "applypointdamage", "onhit"),
    "Leben": (
        "heal",
        "addhealth",
        "sethealth",
        "modifyhealth",
        "restorehealth",
        "revive",
        "kill",
        "die",
        "death",
        "ondeath",
        "isdead",
        "isalive",
        "godmode",
    ),
    "Munition": (
        "consumeammo",
        "useammo",
        "removeammo",
        "reload",
        "fire",
        "shoot",
        "decrementammo",
        "addammo",
        "setammo",
    ),
    "Items": (
        "additem",
        "removeitem",
        "consumeitem",
        "useitem",
        "dropitem",
        "craft",
        "pickup",
        "decrementitem",
        "setquantity",
        "canafford",
        "canaddItem".lower(),
    ),
    "Währung": (
        "addcurrency",
        "spendcurrency",
        "addmoney",
        "removemoney",
        "spendmoney",
        "addgold",
        "removegold",
        "addcoins",
        "purchase",
        "buy",
        "sell",
        "canafford",
        "setmoney",
    ),
    "Erfahrung": ("addxp", "addexperience", "grantexperience", "levelup", "addlevel", "gainxp"),
    "Ausdauer": ("usestamina", "consumestamina", "drainstamina", "spendstamina", "setstamina"),
}


def words(name):
    """'CurrentHealthPercent' -> ['current','health','percent']; 'bIsDead' -> ['is','dead']"""
    name = re.sub(r"^(b)(?=[A-Z])", "", name)
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)
    return [part.lower() for part in parts]


def base_type(t):
    t = re.sub(r"\b(class|struct|enum|const)\b", "", t).strip()
    return t.lower().replace(" ", "")


@dataclass
class Candidate:
    cls: str
    member: str
    owner: str
    offset: int
    type: str
    size: int
    category: str
    score: float
    reasons: list = field(default_factory=list)
    is_max: bool = False

    @property
    def key(self):
        return f"{self.cls}.{self.member}"


def classify_member(m, cls_name, wrap=None):
    name_l = m.name.lower()
    w = words(m.name)
    if not w:
        return None
    t = base_type(m.type)
    if wrap is None and t == "fgameplayattributedata":
        wrap = "float"
    gas = wrap is not None  # Struct-Wrapper (GAS-Attribut, eigener FStat ...): wichtigstes Feld statt Struct bewerten
    if gas:
        t = base_type(wrap)
    best = None
    for cat, (kw, weight, types) in CATEGORIES.items():
        hit = [x for x in w if x in kw]
        joined = "".join(w)
        sub = [k for k in kw if len(k) >= 6 and k in joined]
        if not hit and not sub:
            continue
        hit = hit or sub
        if cat == "Cheat-Schalter":
            if t not in types and m.ptype != "BoolProperty":
                continue
        elif t not in types and m.bit < 0:
            continue
        sc = float(weight)
        reasons = [f"Name enthält '{hit[0]}'"]
        if gas:
            sc += 2
            reasons.append("GAS-Attribut (CurrentValue +0xC)" if "gameplayattributedata" in m.type.lower() else "Zahlen-Struct: " + m.type.replace("struct ", ""))
        if any(x in CUR for x in w):
            sc += 2
            reasons.append("'Current'-Wert")
        if cat not in {"Abklingzeit", "Cheat-Schalter"} and any(x in TIMEISH for x in w):
            sc -= 6
            reasons.append("Zeit/Rate-Wert")
        if "delegate" in name_l or "delegate" in t:
            sc -= 8
            reasons.append("Delegate")
        if BP_CLASS.search(cls_name):
            sc -= 3
            reasons.append("Blueprint-Klasse (Code greift selten direkt zu)")
        if NOISE_CLASS.search(cls_name):
            sc -= 8
            reasons.append("Engine-Hilfsklasse")
        if DATA_CLASS.search(cls_name):
            sc -= 4
            reasons.append("Daten-Tabelle (statische Werte, kein Live-Objekt)")
        if t in FIXED:
            reasons.append("FixedPoint (Value = Anzeige x1000, Palworld)")
        is_max = any(x in MAXISH for x in w)
        if is_max:
            sc -= 4
            reasons.append("Max/Basis/Rate-Wert (eher Begleitwert)")
        if m.bit >= 0 and cat != "Cheat-Schalter":
            sc -= 6
            reasons.append("Bitfeld (kein Zahlenwert)")
        if t in ("float", "int32", "int"):
            sc += 1
        if t in ("uint8", "int8", "uint16", "int16"):
            sc -= 2
            reasons.append("kleiner Typ")
        cl = cls_name.lower()
        if any(b in cl for b in BAD_CLASS):
            sc -= 6
            reasons.append("UI/Grafik-Klasse")
        elif any(g in cl for g in GOOD_CLASS):
            sc += 2
            reasons.append("Klasse wirkt spielrelevant")
        if best is None or sc > best[0]:
            best = (sc, cat, reasons, is_max)
    return best


def find_candidates(sdk, min_score=4.0, include_inherited=False, only_classes=None):
    """-> [Candidate] absteigend nach Score.  Vererbte Member werden nur bei ihrer Definitions-Klasse
    gelistet (include_inherited=True: zusaetzlich bei jeder Unterklasse)."""
    out = []
    for name, value in sdk.classes.items():
        if only_classes and name not in only_classes:
            continue
        mems = sdk.all_members(name) if include_inherited else value.members
        for mem in mems:
            wrap = None
            if "struct " in mem.type or mem.type.startswith("F"):
                import uestruct

                wrap = uestruct.representative_type(sdk, mem.type)
            r = classify_member(mem, mem.owner or name, wrap)
            if not r or r[0] < min_score:
                continue
            sc, cat, reasons, is_max = r
            out.append(
                Candidate(name, mem.name, mem.owner or name, mem.offset, mem.type, mem.size, cat, sc, reasons, is_max)
            )
    out.sort(key=lambda c: (-c.score, c.cls, c.offset))
    return out


def find_functions(sdk, only_classes=None):
    """Funktionen, die nach Cheat-Zielen klingen -> [(klasse, funktion, kategorie, signatur)]."""
    out = []
    for name, value in sdk.classes.items():
        if only_classes and name not in only_classes:
            continue
        for fn, sig in value.functions:
            low = fn.lower()
            for cat, kws in FUNC_WORDS.items():
                if any(low == k or low.endswith(k) or low.startswith(k) for k in kws):
                    cl = name.lower()
                    pen = any(b in cl for b in BAD_CLASS)
                    out.append((name, fn, cat, sig, pen))
                    break
    out.sort(key=lambda t: (t[4], t[2], t[0], t[1]))
    return [(a, b, c, d) for a, b, c, d, _p in out]


def companions(sdk, cand):
    """Max-/Basis-Werte der gleichen Klasse, die zum Kandidaten passen (Health -> MaxHealth)."""
    base = [w for w in words(cand.member) if w not in CUR and w not in MAXISH]
    out = []
    for m in sdk.all_members(cand.cls):
        if m.name == cand.member:
            continue
        w = words(m.name)
        if base and all(b in w for b in base) and any(x in MAXISH for x in w):
            out.append(m)
    return out


ACTIONS = {
    "add",
    "remove",
    "consume",
    "use",
    "spend",
    "reduce",
    "decrease",
    "decrement",
    "increase",
    "set",
    "apply",
    "take",
    "drain",
    "pay",
    "cost",
    "heal",
    "damage",
    "kill",
    "die",
    "grant",
    "give",
    "gain",
    "drop",
}
OBJECTS = {
    "hp",
    "health",
    "stamina",
    "sp",
    "ammo",
    "bullet",
    "bullets",
    "money",
    "gold",
    "coin",
    "coins",
    "currency",
    "item",
    "items",
    "xp",
    "exp",
    "experience",
    "durability",
    "damage",
    "muteki",
    "mana",
    "energy",
    "fuel",
    "cooldown",
    "weight",
    "technology",
    "point",
    "points",
    "satiety",
    "hunger",
    "shield",
    "armor",
}
SHARED_MIN = 25  # so viele Funktionen mit gleicher Adresse = gemeinsamer Stub (Blueprint/Delegate)


def native_usage(sdk):
    """{adresse: anzahl funktionen}"""
    cnt = {}
    for cls in sdk.classes.values():
        for function in cls.funcs:
            if function.native:
                cnt[function.native] = cnt.get(function.native, 0) + 1
    return cnt


def find_function_targets(sdk, only_classes=None, min_score=3.0):
    """Cheat-typische Funktionen mit nativer Adresse (aus dem Header).
    -> [dict(cls, name, category, native, shared, flags, sig, score)]  (beste zuerst)"""
    usage = native_usage(sdk)
    out = []
    for cname, value in sdk.classes.items():
        if only_classes and cname not in only_classes:
            continue
        cl = cname.lower()
        for function in value.funcs:
            w = words(function.name)
            objs = [x for x in w if x in OBJECTS]
            acts = [x for x in w if x in ACTIONS]
            cat = None
            for k, kws in FUNC_WORDS.items():
                low = function.name.lower()
                if any(low == x or low.endswith(x) or low.startswith(x) for x in kws):
                    cat = k
                    break
            if not (objs and acts) and not cat:
                continue
            sc = 2.0 * bool(acts) + 3.0 * bool(objs) + 2.0 * bool(cat)
            if function.native is None:
                sc -= 2
            shared = bool(function.native) and usage.get(function.native, 0) >= SHARED_MIN
            if shared:
                sc -= 6
            if "delegate" in function.name.lower() or "delegatesignature" in function.name.lower():
                sc -= 8
            if any(b in cl for b in BAD_CLASS) or BP_CLASS.search(cname):
                sc -= 3
            lowname = function.name.lower()
            if lowname.startswith("on") and len(lowname) > 3 and function.name[2].isupper():
                sc -= 2  # Ereignis-Callback statt Aktion
            if lowname.startswith(("get", "is", "can", "has")) and not cat:
                sc -= 3  # reine Abfrage
            if any(x in lowname for x in ("_toserver", "_toall", "_multicast", "_toclient", "_client")):
                sc -= 3  # reine Netzwerk-Huelle (RPC)
            if sc < min_score:
                continue
            out.append(
                {
                    "cls": cname,
                    "name": function.name,
                    "category": cat or (objs[0] if objs else "?"),
                    "native": function.native,
                    "shared": shared,
                    "flags": function.flags,
                    "sig": function.signature,
                    "score": sc,
                }
            )
    out.sort(key=lambda d: (-d["score"], d["cls"], d["name"]))
    return out
