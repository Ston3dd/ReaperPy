"""unity_items.py - Items eines Unity-(IL2CPP)-Spiels als fertiger Trainer, in drei Klicks (Logik ohne Oberflaeche).

Das Gegenstueck zu ue_items.py.  Der Weg im Tab UNITY > ITEMS:  Spiel laden  ->  ITEMS FINDEN  ->  TRAINER SPEICHERN
  * ITEMS FINDEN   sucht in dump.cs selbst die Item-Liste (Enum wie ItemID) und die Methode, die Items gibt
                   (AddItem, GiveItem ...), und waehlt einen Haken: eine Update-Methode, die staendig laeuft und aus der
                   sich das Inventar erreichen laesst.
  * TRAINER        alle gehakten Items, je Kategorie in 14er-Paketen ("Waffen 1", "Waffen 2" ...).

Technik (anders als bei Unreal, wo der ProcessEvent-Zeiger im vtable umgebogen wird):
  Unity-Spiele haben kein ProcessEvent.  Der Trainer setzt deshalb einen Sprung (jmp rel32) an den ANFANG einer
  Update-Methode (LateUpdate/FixedUpdate gehen auch).  Die ersten Befehle der Methode werden in die Cave kopiert und dort
  ausgefuehrt (verschoben: rip-relative Adressen und Spruenge werden angepasst).  Die Cave prueft Schalter-Bytes; ist
  einer 1, wird er atomar auf 0 gesetzt und die Geben-Methode des Spiels je Item einmal aufgerufen.  Danach laufen die
  kopierten Befehle und die Methode geht ganz normal weiter.

Die Cave selbst ist reiner Maschinencode (kein Assembler noetig): Platz-/Schalter-Suche, Namen und Projekt-Dateien
teilen sich die Bausteine mit cave_trainer.py.  Alles hier bekommt read()/Dump-Objekte uebergeben -> ohne Konsole
testbar (tests/test_unity_items.py, inkl. echter Ausfuehrung der Cave auf einem x86-64-Prozessor).

NICHT an einem echten Spiel getestet.  Annahmen: Aufrufkonvention System V x86-64 (PS4/PS5), das letzte Argument jeder
IL2CPP-Methode ist der MethodInfo-Zeiger (hier 0), die Geben-Methode nimmt nur Zahlen/Enums/bool/float.
"""
import json
import os
import re
import struct

import cave_trainer as TR
import il2cpp_dump as D
import ue_items as IT

# ----------------------------------------------------------------------------------------------------------------
# Konstanten
# ----------------------------------------------------------------------------------------------------------------
SPEC_FILE = "_trainer_spec.json"
README_FILE = "LIESMICH_TRAINER.txt"
BASE_FILE = "00_BASIS - Item-Cave.reapproj"
FORMAT = "reaperpy-unity-item-trainer"
HOOK_NAMES = ("Update", "LateUpdate", "FixedUpdate")
HOOK_LEN_MIN = 5                         # jmp rel32
HOOK_LEN_MAX = 20                        # so viele Byte hoechstens aus dem Funktionsanfang verschieben
MAX_ROWS = TR.MAX_ROWS
MAX_OPTIONS = TR.MAX_OPTIONS
PACK_SIZE = TR.PACK_SIZE

ITEM_ENUM = re.compile(r"(?i)item|inventor|loot|weapon|equip|consum|material|resource|gear|armo|ingredient|food|tool")
ITEM_ENUM_GOOD = re.compile(r"(?i)^(e)?(item|inventoryitem|lootitem)(s)?(id|ids|name|names|key|keys)?$")
ITEM_ENUM_TYPE = re.compile(r"(?i)type|kind|class|group")       # ItemType = meist nur 5-20 Kategorien, nicht die Items selbst
ITEM_ENUM_BAD = re.compile(r"(?i)slot|rarity|quality|state|status|category|flag|event|action|sound|sfx|anim|button|"
                           r"tutorial|quest|achievement|trophy|input|keycode|keyboard|layer|mode$|result|error|"
                           r"direction|language|platform|shader|render|texture|materialtype|materialproperty")
SKIP_VALUE_NAMES = re.compile(r"(?i)^(none|null|empty|invalid|unknown|undefined|default|count|max|min|length|size|"
                              r"num[a-z]*|total|last|first|end|begin|all|any|__.*|.*_?(count|max|min|none|end)$)$")
GIVE_NAME = re.compile(r"(?i)^(add|give|grant|obtain|receive|pickup|pick_?up|collect|gain|acquire|award|reward|"
                       r"put|insert|store|spawn|create|try_?add|can_?add)(item|items|to_?inventory|to_?bag|loot|stack)?$|"
                       r"^(add|give|grant|obtain|receive|get|gain|acquire|award|try_?add)_?(item|items|loot|stack|resource|material)$|"
                       r"^(add|give|grant|obtain|receive|gain)(item|items|loot|stack|resource|material)[a-z0-9_]*$")
GIVE_NAME_LOOSE = re.compile(r"(?i)add|give|grant|obtain|receive|pickup|collect|gain|acquire|award|reward")
GIVE_CLASS = re.compile(r"(?i)inventor|bag|backpack|storage|chest|stash|container|pocket|loot|item(manager|holder|bag|box)|"
                        r"player|character|hero|wallet|equipment")
BAD_GIVE_NAME = re.compile(r"(?i)remove|delete|drop|use|consume|sell|buy|destroy|clear|reset|can|has|is|get(count|amount)|"
                           r"check|contains|find|try(remove|use)|on(add|remove)|event|callback|update|refresh|save|load|"
                           r"serial|sync|rpc|network|cmd|ui|display|show|text")
ID_PARAM = re.compile(r"(?i)^(id|item_?id|itemid|item|type|item_?type|kind|key|index|idx|uid|code|name|what)$|item")
COUNT_PARAM = re.compile(r"(?i)count|amount|num|quantity|qty|stack|number|n$|size|value")
PLAYER_CLASS = re.compile(r"(?i)player|hero|character|protagonist|avatar|local|main|controller")
ENEMY_CLASS = re.compile(r"(?i)enemy|monster|boss|npc|ai|mob|zombie|creature|animal|hostile|pet|companion|minion")

INT_KINDS = {"int8": 1, "uint8": 1, "int16": 2, "uint16": 2, "int32": 4, "uint32": 4, "int64": 8, "uint64": 8}
# Ganzzahl-Argumentregister (System V): mov r32,imm32 | movabs r64,imm64 | xor r32,r32 | Name
INT_REGS = [
    ("BF", "48BF", "31FF", "rdi"),
    ("BE", "48BE", "31F6", "rsi"),
    ("BA", "48BA", "31D2", "rdx"),
    ("B9", "48B9", "31C9", "rcx"),
    ("41B8", "49B8", "4531C0", "r8"),
    ("41B9", "49B9", "4531C9", "r9"),
]
MAX_FLOAT_REGS = 8


class UnityTrainerError(TR.TrainerError):
    pass


def _register_cave_head():
    """cave_trainer.find_remnant() erkennt Reste einer frueheren Cave (BASIS aus -> Cave bleibt am Region-Ende stehen) am Anfang
    der Unreal-Cave.  Der Anfang der Unity-Cave kommt dazu: xor eax,eax / (or rax,[rip+d32])+ / jz run / push rdi,rsi,rdx /
    xor eax,eax / xchg [rip+d32],al.  Das jz-rel32 steht genau 4 Byte vor dem Ende des Treffers (wie das jmp bei Unreal)."""
    head = getattr(TR, "_CAVE_HEAD", None)
    if head is None or getattr(TR, "_UNITY_HEAD_ADDED", False):
        return
    unity = rb"\x31\xc0(?:\x48\x0b\x05....)+\x0f\x84....(?=\x57\x56\x52\x31\xc0\x86\x05)"
    TR._CAVE_HEAD = re.compile(b"(?:" + head.pattern + b")|(?:" + unity + b")", re.DOTALL)
    TR._UNITY_HEAD_ADDED = True


_register_cave_head()


# ----------------------------------------------------------------------------------------------------------------
# 1) Parameter einer Methode lesen
# ----------------------------------------------------------------------------------------------------------------
def split_params(text):
    """'ItemID id, int count = 1' -> ['ItemID id', 'int count']  (Kommas in <> [] () werden nicht getrennt)."""
    out, depth, cur = [], 0, ""
    for ch in text or "":
        if ch in "<[(":
            depth += 1
        elif ch in ">])":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def parse_param(text, enums):
    """'ItemID id' -> dict(name, type, kind, size, ref).  kind: int | enum | bool | float | double | other.
    enums: {Name: Class} aller Enums (kurzer und voller Name)."""
    t = text.split("=")[0].strip()
    ref = bool(re.match(r"^(ref|out|in)\s", t))
    t = re.sub(r"^(ref|out|in|params|this)\s+", "", t)
    parts = t.rsplit(None, 1)
    typ, name = (parts[0], parts[1]) if len(parts) == 2 else (t, "")
    typ = typ.strip()
    prim = D.PRIMS.get(typ)
    kind, size = "other", 0
    if typ in enums:
        kind, size = "enum", D.SIZES.get(enums[typ].enum_underlying, 4)
    elif prim == "bool":
        kind, size = "bool", 1
    elif prim in INT_KINDS:
        kind, size = "int", INT_KINDS[prim]
    elif prim == "float":
        kind, size = "float", 4
    elif prim == "double":
        kind, size = "double", 8
    return {"name": name, "type": typ, "kind": kind, "size": size, "ref": ref,
            "signed": bool(prim and prim.startswith("int"))}


def enum_map(game):
    out = {}
    for c in game.classes:
        if c.kind == "enum":
            out.setdefault(c.name, c)
            out.setdefault(c.full, c)
    return out


# ----------------------------------------------------------------------------------------------------------------
# 2) Item-Liste: Enum waehlen, Items einteilen
# ----------------------------------------------------------------------------------------------------------------
def real_values(enum_cls):
    """Enum-Eintraege ohne Platzhalter (None, Count, Max ...) und ohne doppelte Werte -> [(Name, Wert)]."""
    out, seen = [], set()
    for n, v in enum_cls.enum_values:
        if SKIP_VALUE_NAMES.match(n) or v in seen:
            continue
        seen.add(v)
        out.append((n, v))
    return out


def enum_score(cls, give_types=()):
    """Wie wahrscheinlich ist dieses Enum DIE Item-Liste?  0 = gar nicht."""
    if cls.kind != "enum":
        return 0
    vals = real_values(cls)
    if len(vals) < 4:
        return 0
    name = cls.name.split(".")[-1]
    s = 0.0
    if ITEM_ENUM_GOOD.match(name):
        s += 6
    elif ITEM_ENUM.search(name):
        s += 3
    elif not ITEM_ENUM.search(cls.full):
        return 0
    if ITEM_ENUM_TYPE.search(name) and len(vals) < 40:
        s -= 3                                    # sieht nach Kategorien aus, nicht nach der Item-Liste
    if len(vals) < 12:
        s -= 3
    if ITEM_ENUM_BAD.search(name):
        s -= 5
    if cls.name in give_types or cls.full in give_types:
        s += 6                                    # eine Geben-Methode nimmt genau dieses Enum
    if cls.image.startswith("Assembly-CSharp"):
        s += 1
    s += min(len(vals), 400) / 100.0              # lange Listen sind eher die Item-Liste
    if len(vals) > 3000:
        s -= 2
    return s


def item_enums(game, give_types=()):
    """Alle Enums, die als Item-Liste in Frage kommen -> [(Klasse, Score)], beste zuerst."""
    ranked = [(c, enum_score(c, give_types)) for c in game.classes if c.kind == "enum"]
    ranked = [(c, s) for c, s in ranked if s > 0]
    ranked.sort(key=lambda x: -x[1])
    return ranked


def build_items(enum_cls):
    """Enum -> [Item] (name, id, category, fname=b'') mit denselben Kategorien-Regeln wie bei Unreal (Namens-Vorsilbe)."""
    rows = [{"name": n, "fname_hex": "", "row_ptr": 0, "values": {"ItemId": v}} for n, v in real_values(enum_cls)]
    items = IT.build_items(rows)
    for it in items:
        it["fname"] = b""
    return items


group_items = IT.group_items
packages = IT.packages
split_projects = IT.split_projects


# ----------------------------------------------------------------------------------------------------------------
# 3) Geben-Methode finden
# ----------------------------------------------------------------------------------------------------------------
class Give:
    """Eine Methode, die ein Item gibt: Parameter eingeordnet (id / count / other), Bewertung."""

    def __init__(self, method, params, id_i, count_i, score, note=""):
        self.method, self.params, self.id_i, self.count_i = method, params, id_i, count_i
        self.score, self.note = score, note

    @property
    def title(self):
        m = self.method
        return f"{m.cls.full}.{m.name}({m.params})"

    @property
    def id_param(self):
        return self.params[self.id_i]

    @property
    def count_param(self):
        return self.params[self.count_i] if self.count_i is not None else None


def classify_give(method, enums, item_enum=None):
    """Methode -> Give oder UnityTrainerError mit Klartext, warum sie sich nicht aufrufen laesst."""
    if method.rva <= 0:
        raise UnityTrainerError("hat keine Adresse (abstrakt oder vom Compiler entfernt)")
    if method.name in (".ctor", ".cctor") or method.name.startswith("<"):
        raise UnityTrainerError("ist ein Konstruktor / Compiler-Methode")
    if "<" in method.cls.name or "<" in method.name:
        raise UnityTrainerError("ist generisch (Typ erst zur Laufzeit bekannt)")
    params = [parse_param(p, enums) for p in split_params(method.params)]
    for p in params:
        if p["ref"]:
            raise UnityTrainerError(f"Parameter '{p['name']}' ist ref/out")
        if p["kind"] == "other":
            raise UnityTrainerError(f"Parameter '{p['name']}' ({p['type']}) ist ein Objekt/Text - das kann eine feste Cave "
                                    "nicht liefern")
    n_int = sum(1 for p in params if p["kind"] in ("int", "enum", "bool"))
    n_flt = sum(1 for p in params if p["kind"] in ("float", "double"))
    n_int += 0 if method.static else 1                              # this
    n_int += 1                                                      # MethodInfo*
    if n_int > len(INT_REGS):
        raise UnityTrainerError(f"zu viele Parameter ({n_int} Ganzzahl-Register, mehr als {len(INT_REGS)})")
    if n_flt > MAX_FLOAT_REGS:
        raise UnityTrainerError("zu viele Kommazahl-Parameter")
    id_i = None
    for i, p in enumerate(params):                                  # 1. Parameter mit dem Item-Enum
        if item_enum is not None and p["kind"] == "enum" and p["type"] in (item_enum.name, item_enum.full):
            id_i = i
            break
    if id_i is None:
        for i, p in enumerate(params):                              # 2. irgendein Enum, dessen Name nach Item klingt
            if p["kind"] == "enum" and ITEM_ENUM.search(p["type"]):
                id_i = i
                break
    if id_i is None:
        for i, p in enumerate(params):                              # 3. Zahl, die wie eine ID heisst
            if p["kind"] == "int" and ID_PARAM.search(p["name"]) and not COUNT_PARAM.search(p["name"]):
                id_i = i
                break
    if id_i is None:
        raise UnityTrainerError("hat keinen Parameter fuer die Item-ID (Enum oder Zahl)")
    count_i = None
    for i, p in enumerate(params):
        if i != id_i and p["kind"] in ("int", "float", "double") and COUNT_PARAM.search(p["name"]):
            count_i = i
            break
    if count_i is None:
        for i, p in enumerate(params):
            if i != id_i and p["kind"] == "int" and p["size"] == 4:
                count_i = i
                break
    return Give(method, params, id_i, count_i, 0.0)


def give_score(g, item_enum):
    m, s = g.method, 0.0
    if GIVE_NAME.match(m.name):
        s += 6
    elif GIVE_NAME_LOOSE.search(m.name):
        s += 2
    else:
        s -= 3
    if BAD_GIVE_NAME.search(m.name) and not GIVE_NAME_LOOSE.search(m.name):
        s -= 6
    if re.search(r"(?i)^(remove|delete|drop|use|consume|sell|clear)", m.name):
        s -= 8
    if GIVE_CLASS.search(m.cls.name):
        s += 3
    if item_enum is not None and g.id_param["type"] in (item_enum.name, item_enum.full):
        s += 5
    if g.count_i is not None:
        s += 2
    if m.ret in ("void", "bool"):
        s += 1
    if m.cls.image.startswith("Assembly-CSharp"):
        s += 2
    if len(g.params) > 3:
        s -= len(g.params) - 3
    if re.search(r"(?i)^(try|can|has)", m.name):
        s -= 2
    return s


def give_candidates(game, item_enum=None, limit=40):
    """Methoden, die ein Item geben koennten -> (baubar: [Give] nach Score, abgelehnt: [(Methode, Grund)]).
    Nur Methoden im Spiel-Code (Assembly-CSharp); Unity-/System-Bibliotheken geben keine Spiel-Items."""
    enums = enum_map(game)
    ok, bad = [], []
    for m in game.all_methods():
        if not m.cls.image.startswith("Assembly-CSharp") or m.cls.kind == "enum":
            continue
        if not (GIVE_NAME_LOOSE.search(m.name) or m.name in ("Put", "Insert", "Store")):
            continue
        if re.search(r"(?i)^(remove|delete|drop|use|consume|sell|clear|can|has|is)", m.name):
            continue
        try:
            g = classify_give(m, enums, item_enum)
        except UnityTrainerError as e:
            if item_enum is not None and any(p.strip().startswith((item_enum.name, item_enum.full))
                                             for p in split_params(m.params)):
                bad.append((m, str(e)))
            continue
        g.score = give_score(g, item_enum)
        if g.score < 3:
            continue
        ok.append(g)
    ok.sort(key=lambda g: -g.score)
    return ok[:limit], bad[:limit]


# ----------------------------------------------------------------------------------------------------------------
# 4) Haken: eine Update-Methode, die staendig laeuft und das Inventar erreicht
# ----------------------------------------------------------------------------------------------------------------
class Hook:
    """Wo die Cave einsteigt und woher sie das Objekt der Geben-Methode (this) bekommt."""

    def __init__(self, method, this_mode, this_off=0, why="", score=0.0):
        self.method, self.this_mode, self.this_off, self.why, self.score = method, this_mode, this_off, why, score

    @property
    def title(self):
        return f"{self.method.cls.full}.{self.method.name}  ({self.why})"


def _ancestry(game, cls, cap=8):
    out = [cls]
    while len(out) < cap:
        par = game.parent_of(out[-1])
        if par is None:
            break
        out.append(par)
    return out


def _tick_methods(cls):
    return [m for m in cls.methods if m.name in HOOK_NAMES and not m.static and m.n_params == 0 and m.rva > 0]


def hook_candidates(game, give, limit=12):
    """Haken fuer eine Geben-Methode -> [Hook], beste zuerst.
      statische Methode          : this nicht noetig -> jede Update-Methode des Spielcodes taugt (Spieler bevorzugt)
      Instanz, Update in der Klasse (oder Basisklasse): this = das gehakte Objekt selbst
      Instanz, Klasse mit Feld vom Typ der Zielklasse und eigener Update: this = Feld des gehakten Objekts"""
    owner = give.method.cls
    out = []
    if give.method.static:
        for c in game.classes:
            if c.kind != "class" or not c.image.startswith("Assembly-CSharp"):
                continue
            for m in _tick_methods(c):
                s = 2 + (3 if PLAYER_CLASS.search(c.name) else 0) - (4 if ENEMY_CLASS.search(c.name) else 0) \
                    + (1 if m.name == "Update" else 0)
                out.append(Hook(m, "zero", 0, "statische Methode - braucht kein Objekt", s))
    else:
        # Nur die EIGENE Klasse: Eine Update der Basisklasse wird auch von fremden Klassen aufgerufen - dann waere
        # `this` kein Inventar und der Aufruf stuerzt ab.
        for m in _tick_methods(owner):
            out.append(Hook(m, "hooked", 0, "laeuft im Inventar-Objekt selbst", 10 + (1 if m.name == "Update" else 0)))
        fam = _ancestry(game, owner)
        names = {c.name for c in fam} | {c.full for c in fam}
        for c in game.classes:
            if c.kind != "class" or not c.image.startswith("Assembly-CSharp"):
                continue
            ticks = _tick_methods(c)
            if not ticks:
                continue
            for f in c.fields:
                if f.static or f.offset <= 0 or f.type not in names:
                    continue
                for m in ticks:
                    s = 5 + (3 if PLAYER_CLASS.search(c.name) else 0) - (5 if ENEMY_CLASS.search(c.name) else 0) \
                        + (1 if m.name == "Update" else 0)
                    out.append(Hook(m, "member", f.offset, f"{c.full}.{f.name} (+{f.offset:#x}) zeigt auf das Inventar", s))
    seen, uniq = set(), []
    for h in sorted(out, key=lambda h: -h.score):
        k = (h.method.rva, h.this_mode, h.this_off)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(h)
    return uniq[:limit]


# ----------------------------------------------------------------------------------------------------------------
# 5) Aufruf-Beschreibung und Zeilen
# ----------------------------------------------------------------------------------------------------------------
class Call:
    """Wie die Geben-Methode aufgerufen wird (gilt fuer alle Zeilen eines Trainers)."""

    def __init__(self, impl_rva, static, this_mode, this_off, params, id_i, count_i, function=""):
        self.impl_rva, self.static = int(impl_rva), bool(static)
        self.this_mode, self.this_off = this_mode, int(this_off)
        self.params, self.id_i, self.count_i, self.function = list(params), id_i, count_i, function

    def to_json(self):
        return {"function": self.function, "impl_rva": hex(self.impl_rva), "static": self.static, "this": self.this_mode,
                "this_off": hex(self.this_off), "id_param": self.id_i, "count_param": self.count_i,
                "params": [{k: p[k] for k in ("name", "type", "kind", "size")} for p in self.params]}

    @classmethod
    def from_json(cls, d):
        params = [dict(p, ref=False, signed=False) for p in d["params"]]
        return cls(int(d["impl_rva"], 16), d.get("static", False), d["this"], int(d.get("this_off", "0"), 16), params,
                   d["id_param"], d.get("count_param"), d.get("function", ""))


def make_call(give, hook):
    this_mode = "zero" if give.method.static else hook.this_mode
    return Call(give.method.rva, give.method.static, this_mode, hook.this_off if this_mode == "member" else 0,
                give.params, give.id_i, give.count_i, f"{give.method.cls.full}.{give.method.name}")


class UnityRow:
    """Eine Trainer-Zeile = ein Item (ID) mit Menge, aufgerufen ueber das gemeinsame Call."""

    def __init__(self, alias, call, item_id, amount):
        if not 1 <= int(amount) <= 0x7FFFFFFF:
            raise UnityTrainerError(f"{alias}: Menge {amount} ausserhalb 1..2147483647")
        self.alias, self.call, self.item_id, self.amount = alias, call, int(item_id), int(amount)
        self.call_impl_rva = call.impl_rva
        self.fname = None
        self._check_values()

    def _check_values(self):
        c = self.call
        for i, v in ((c.id_i, self.item_id), (c.count_i, self.amount)):
            if i is None:
                continue
            p = c.params[i]
            if p["kind"] in ("int", "enum"):
                sz = p["size"] or 4
                if not -(1 << (8 * sz - 1)) <= v < (1 << (8 * sz)):
                    raise UnityTrainerError(f"{self.alias}: Wert {v} passt nicht in Parameter '{p['name']}' ({sz} Byte)")

    def to_json(self):
        return {"alias": self.alias, "id": self.item_id, "amount": self.amount}

    def _value(self, i):
        if i == self.call.id_i:
            return self.item_id
        if i == self.call.count_i:
            return self.amount
        return 0

    def emit(self, e, base):
        """Ein kompletter Aufruf.  Die Originalregister liegen auf dem Stack: [rsp]=rdx, [rsp+8]=rsi, [rsp+0x10]=rdi."""
        c, skip = self.call, None
        ireg = freg = 0
        if not c.static:
            e.raw("488B7C2410")                                     # mov rdi,[rsp+0x10]   (gehooktes Objekt)
            if c.this_mode == "member":
                e.raw("488BBF" + struct.pack("<i", c.this_off).hex())   # mov rdi,[rdi+off]
                e.raw("4885FF")                                     # test rdi,rdi
                skip = e.uniq("skip")
                e.raw("0F84")                                       # jz skip
                e.rel32(skip)
            ireg = 1
        for i, p in enumerate(c.params):
            v, k, sz = self._value(i), p["kind"], p["size"]
            if k in ("float", "double"):
                if k == "float":
                    e.raw("B8" + struct.pack("<f", float(v)).hex())            # mov eax,imm32
                    e.raw("660F6E" + f"{0xC0 + 8 * freg:02X}")                 # movd xmmN,eax
                else:
                    e.raw("48B8" + struct.pack("<d", float(v)).hex())          # mov rax,imm64
                    e.raw("66480F6E" + f"{0xC0 + 8 * freg:02X}")               # movq xmmN,rax
                freg += 1
                continue
            mov32, mov64, _xor, _n = INT_REGS[ireg]
            ireg += 1
            if k == "bool":
                e.raw(mov32 + struct.pack("<I", 1 if v else 0).hex())
            elif sz == 8:
                e.raw(mov64 + struct.pack("<Q", int(v) & 0xFFFFFFFFFFFFFFFF).hex())
            else:
                e.raw(mov32 + struct.pack("<I", int(v) & 0xFFFFFFFF).hex())
        e.raw(INT_REGS[ireg][2])                                    # MethodInfo* = 0
        e.raw("E8")                                                 # call impl
        e.rel32(base + c.impl_rva)
        if skip:
            e.label(skip)


class Option(TR.Option):
    """Trainer-Eintrag (= eine Datei im Projekt) mit UnityRow-Zeilen."""


# ----------------------------------------------------------------------------------------------------------------
# 6) Funktionsanfang verschieben (Relocation)
# ----------------------------------------------------------------------------------------------------------------
class RelocError(UnityTrainerError):
    pass


def _target_rel32(raw, off):
    return struct.unpack_from("<i", raw, off)[0]


def relocate(code, old_addr, new_addr, dis, min_len=HOOK_LEN_MIN, max_len=HOOK_LEN_MAX):
    """Ganze Befehle ab `old_addr` (Bytes `code`) kopieren, bis mindestens `min_len` Byte zusammen sind, und fuer die
    Adresse `new_addr` neu kodieren (rip-relative Adressen, call/jmp/jcc).  -> (stolen_len, neue_bytes).
    Wirft RelocError mit Klartext, wenn das nicht sicher geht (dann einen anderen Haken waehlen)."""
    insns = dis.sweep(bytes(code), 0, len(code), old_addr)
    out, used, total = bytearray(), [], 0
    for i in insns:
        used.append(i)
        total += i.size
        if total >= min_len:
            break
    if total < min_len:
        raise RelocError("Funktionsanfang laesst sich nicht lesen/zerlegen (zu wenig gueltige Befehle)")
    if total > max_len:
        raise RelocError(f"Die ersten Befehle sind zusammen {total} Byte lang (mehr als {max_len}) - ungewoehnlich")
    stolen_end = old_addr + total
    for k, i in enumerate(used):
        raw = bytes(i.raw)
        op0 = raw[0]
        off = 0
        while off < len(raw) and raw[off] in (0x66, 0x67, 0xF2, 0xF3, 0x2E, 0x3E, 0x26, 0x36, 0x64, 0x65):
            off += 1                                                # Prefixe stehen vor dem Opcode
        op0 = raw[off] if off < len(raw) else op0
        last = k == len(used) - 1
        if op0 in (0xC3, 0xC2, 0xCC):
            if not last:
                raise RelocError("'ret'/'int3' mitten im verschobenen Bereich - Funktion ist zu kurz fuer einen Haken")
            out += raw
            continue
        if op0 in (0xE8, 0xE9) and len(raw) == off + 5:             # call/jmp rel32
            tgt = old_addr + sum(x.size for x in used[:k]) + len(raw) + _target_rel32(raw, off + 1)
            if old_addr <= tgt < stolen_end:
                raise RelocError("Sprung in den verschobenen Bereich")
            nxt = new_addr + len(out) + len(raw)
            out += raw[:off + 1] + struct.pack("<i", tgt - nxt)
            if op0 == 0xE9 and not last:
                raise RelocError("Unbedingter Sprung mitten im verschobenen Bereich")
            continue
        if op0 == 0xEB and len(raw) == off + 2:                     # jmp rel8 -> jmp rel32
            tgt = old_addr + sum(x.size for x in used[:k]) + len(raw) + struct.unpack_from("<b", raw, off + 1)[0]
            if old_addr <= tgt < stolen_end:
                raise RelocError("Sprung in den verschobenen Bereich")
            out += b"\xE9" + struct.pack("<i", tgt - (new_addr + len(out) + 5))
            if not last:
                raise RelocError("Unbedingter Sprung mitten im verschobenen Bereich")
            continue
        if 0x70 <= op0 <= 0x7F and len(raw) == off + 2:             # jcc rel8 -> jcc rel32
            tgt = old_addr + sum(x.size for x in used[:k]) + len(raw) + struct.unpack_from("<b", raw, off + 1)[0]
            if old_addr <= tgt < stolen_end:
                raise RelocError("Sprung in den verschobenen Bereich")
            out += bytes([0x0F, 0x80 + (op0 - 0x70)]) + struct.pack("<i", tgt - (new_addr + len(out) + 6))
            continue
        if op0 == 0x0F and len(raw) == off + 6 and 0x80 <= raw[off + 1] <= 0x8F:     # jcc rel32
            tgt = old_addr + sum(x.size for x in used[:k]) + len(raw) + _target_rel32(raw, off + 2)
            if old_addr <= tgt < stolen_end:
                raise RelocError("Sprung in den verschobenen Bereich")
            out += raw[:off + 2] + struct.pack("<i", tgt - (new_addr + len(out) + len(raw)))
            continue
        if i.branch and op0 in (0xE3, 0xE0, 0xE1, 0xE2):
            raise RelocError(f"'{i.text}' (loop/jrcxz) laesst sich nicht verschieben")
        if i.mem is not None and i.mem.base == "rip":               # rip-relative Adresse neu rechnen
            d_off = None
            for wo, wl in (i.wild or []):
                if wl == 4:
                    d_off = wo
                    break
            if d_off is None:
                pos = raw.find(struct.pack("<i", i.mem.disp))
                d_off = pos if pos >= 0 else None
            if d_off is None:
                raise RelocError(f"rip-relative Adresse in '{i.text}' nicht gefunden")
            tgt = old_addr + sum(x.size for x in used[:k]) + len(raw) + struct.unpack_from("<i", raw, d_off)[0]
            nxt = new_addr + len(out) + len(raw)
            rel = tgt - nxt
            if not -2**31 <= rel < 2**31:
                raise RelocError("rip-relative Adresse liegt zu weit von der Cave entfernt")
            out += raw[:d_off] + struct.pack("<i", rel) + raw[d_off + 4:]
            continue
        if i.branch and op0 in (0xFF,) and len(raw) > off + 1 and (raw[off + 1] >> 3) & 7 in (2, 3, 4, 5):
            out += raw                                              # indirekter Sprung/Aufruf ueber Register/Speicher
            continue
        if i.branch:
            raise RelocError(f"Befehl '{i.text}' laesst sich nicht verschieben")
        out += raw
    return total, bytes(out)


# ----------------------------------------------------------------------------------------------------------------
# 7) Die Cave
# ----------------------------------------------------------------------------------------------------------------
def build_cave(cave_addr, flag_addr, hook_ret, stolen, options, base=0):
    """-> Cave-Bytes.  Einsprung = cave_addr (ersetzt den Anfang der gehakten Methode).

        xor eax,eax / or rax,[Schalter+8k] ...   ; irgendein Schalter gesetzt?
        jz  run                                  ; Normalfall: kaum Kosten
        push rdi / rsi / rdx                     ; Originalargumente retten (rsp: 8 + 24 = 0 mod 16 -> am call ausgerichtet)
        je Eintrag:  xor eax,eax ; xchg [Schalter+i],al ; test al,al ; jz naechster
                     je Zeile:   this laden ; Parameter ; xor MethodInfo ; call impl
        pop rdx / rsi / rdi
      run:
        <verschobene Original-Befehle>           ; (hier mit dem Ziel `stolen`, schon fuer cave_addr+Position kodiert)
        jmp hook_ret                             ; hinter die ueberschriebenen Bytes der Methode

    `stolen` ist ein Callable (adresse -> bytes), weil die Position der Befehle erst beim Bau feststeht."""
    if not options:
        raise UnityTrainerError("Keine Eintraege")
    if len(options) > MAX_OPTIONS:
        raise UnityTrainerError(f"Hoechstens {MAX_OPTIONS} Eintraege (hier {len(options)})")
    if flag_addr % TR.FLAG_ALIGN:
        raise UnityTrainerError("Schalter-Bereich nicht 8-Byte-ausgerichtet")
    e = TR._Emit(cave_addr)
    e.raw("31C0")                                           # xor eax,eax
    for k in range(TR.n_flag_qwords(len(options))):
        e.raw("480B05")                                     # or rax,[rip+disp32]
        e.rel32(flag_addr + 8 * k)
    e.raw("0F84")                                           # jz run
    e.rel32("run")
    e.raw("57" "56" "52")                                   # push rdi, rsi, rdx
    for i, opt in enumerate(options):
        e.raw("31C0")                                       # xor eax,eax
        e.raw("8605")                                       # xchg [rip+disp32],al   (implizit atomar)
        e.rel32(flag_addr + i)
        e.raw("84C0")                                       # test al,al
        e.raw("0F84")                                       # jz next_i
        e.rel32(f"next{i}")
        for row in opt.rows:
            row.emit(e, base)
        e.label(f"next{i}")
    e.raw("5A" "5E" "5F")                                   # pop rdx, rsi, rdi
    e.label("run")
    e.buf += stolen(e.here)
    e.raw("E9")                                             # jmp hook_ret
    e.rel32(hook_ret)
    return e.finish()


STOLEN_GUESS = 48                         # Vorab-Schaetzung der verschobenen Befehle (verschobene Spruenge werden laenger)


def cave_size(options, stolen_len=STOLEN_GUESS):
    """Laenge der Cave (unabhaengig von den Adressen: jedes rel32 ist immer 4 Byte)."""
    return len(build_cave(0, 0, 0, lambda _a: b"\x90" * stolen_len, options, 0))


def fit_options(options, code_capacity, max_options=None, max_rows=None, stolen_len=STOLEN_GUESS):
    """Eintraege der Reihe nach auf Projekte verteilen, bis die Cave nicht mehr in `code_capacity` passt."""
    max_options = max_options or MAX_OPTIONS
    max_rows = max_rows or MAX_ROWS
    out, cur, rows = [], [], 0
    if code_capacity <= 0:
        raise UnityTrainerError("Im laufenden Spiel ist KEIN freier Code-Platz fuer die Cave da (0 Byte). Meist liegt am Ende der "
                                "Code-Region noch etwas: ein Cheat/Plugin (z. B. GoldHEN/etaHEN) oder eine Cave von ReaperPy, die "
                                "noch aktiv ist. Erst die BASIS bzw. den Cheat ausschalten oder das Spiel neu starten; Details "
                                "stehen im Log (Zeilen mit [trainer]).")
    for o in options:
        if cave_size([o], stolen_len) > code_capacity:
            raise UnityTrainerError(f"Schon der Eintrag '{o.name}' ({len(o.rows)} Zeilen, {cave_size([o], stolen_len)} Byte) passt "
                                    f"nicht in die groesste freie Code-Luecke des Spiels ({code_capacity} Byte)")
        if cur and (len(cur) + 1 > max_options or rows + len(o.rows) > max_rows or cave_size(cur + [o], stolen_len) > code_capacity):
            out.append(cur)
            cur, rows = [], 0
        cur.append(o)
        rows += len(o.rows)
    if cur:
        out.append(cur)
    return out


def make_options(pkgs, call, amount, log=lambda _m: None):
    """Pakete [(Name, [Item])] -> [Option] mit je einer Zeile je Item."""
    amount = int(amount) if call.count_i is not None else 1        # ohne Mengen-Parameter gibt die Methode immer 1 Stueck
    options, skipped = [], 0
    for name, items in pkgs:
        rows = []
        for it in items:
            if it.get("id") is None:
                skipped += 1
                continue
            rows.append(UnityRow(TR.clean_name(it["name"]), call, it["id"], amount))
        if rows:
            options.append(Option(name, rows))
    return options, skipped


# ----------------------------------------------------------------------------------------------------------------
# 8) Planen (nur LESEND) und Projekt schreiben
# ----------------------------------------------------------------------------------------------------------------
class Plan:
    def __init__(self):
        self.base = self.cave = self.flag_addr = self.flag_size = self.hook_addr = self.hook_len = 0
        self.cave_bytes = self.cave_orig = self.hook_orig = self.hook_new = b""
        self.verify_also = []                 # weitere erlaubte Ist-Inhalte der Cave-Stelle (Rest einer frueheren Cave)
        self.call = None
        self.hook_title = ""
        self.options, self.warnings, self.anchors = [], [], []

    def rva(self, addr):
        return addr - self.base


def plan(read, maps, base, options, call, hook_rva, hook_title="", dis=None, log=print, settle=0.4, client=None):
    """Alles was gebraucht wird, nur LESEND: Adressen waehlen, Funktionsanfang verschieben, Cave bauen, pruefen."""
    import time
    options = list(options)
    if not options:
        raise UnityTrainerError("Nichts zu exportieren: keine Eintraege")
    names = [o.name.lower() for o in options]
    if len(set(names)) != len(names):
        raise UnityTrainerError("Zwei Eintraege heissen gleich - Namen muessen verschieden sein")
    if sum(len(o.rows) for o in options) > MAX_ROWS:
        raise UnityTrainerError(f"Zu viele Items insgesamt (mehr als {MAX_ROWS}) - auf mehrere Projekte aufteilen")
    span = TR.image_span(maps, base)
    if not span:
        raise UnityTrainerError(f"Die Modul-Basis {base:#x} liegt in keiner Speicherregion")
    hook_addr, impl = base + hook_rva, base + call.impl_rva
    for what, a in (("Haken-Methode", hook_addr), ("Geben-Methode", impl)):
        if not TR.in_span(span, a):
            raise UnityTrainerError(f"{what} ({a:#x}) liegt nicht im Spiel-Modul ({span[0][0]:#x}-{span[-1][1]:#x})")
    if dis is None:
        import ue_instr
        dis = ue_instr.get_disasm()
    head = bytes(read(hook_addr, 48))
    if len(head) < 16 or head[0] == 0xE9:
        raise UnityTrainerError("Der Anfang der Haken-Methode ist schon ein Sprung (E9) - ist ein anderer Trainer/Cheat aktiv? "
                                "Erst deaktivieren oder das Spiel neu starten.")
    p = Plan()
    p.base, p.options, p.call, p.hook_addr, p.hook_title = base, options, call, hook_addr, hook_title
    if client is not None:
        names_a = {impl: "item_function", hook_addr: "hook_function"}
        p.anchors = TR.signature_anchors(client, maps, base, names_a, read, log)
    else:
        p.anchors = [(a - base, bytes(read(a, TR.ANCHOR_LEN)).hex()) for a in sorted({impl, hook_addr})]
    sl = TR.Slots(read, span, log)
    sl.code_capacity()                        # Code-Platz zuerst suchen: erkennt Reste einer frueheren Cave (und ihre Schalter)
    p.flag_addr, p.flag_size = sl.alloc_data(TR.flag_bytes_needed(len(options)), hook_addr)
    first = bytes(read(p.flag_addr, p.flag_size))
    if any(first):
        raise UnityTrainerError(f"Schalter-Bereich {p.flag_addr:#x} ist nicht leer - das Spiel nutzt ihn")
    if settle:
        time.sleep(settle)
        if bytes(read(p.flag_addr, p.flag_size)) != first:
            raise UnityTrainerError(f"Schalter-Bereich {p.flag_addr:#x} aendert sich - das Spiel schreibt dort")
    p.warnings.append(f"Schalter @ base+{p.flag_addr - base:#x} ({p.flag_size} Byte): Null-Stueck am Ende einer "
                      "beschreibbaren Region (Heuristik, mehrere Sekunden lang unveraendert gelesen)")
    try:
        stolen_len, probe = relocate(head, hook_addr, hook_addr, dis)     # Laenge haengt nicht von der Zieladresse ab
    except RelocError as e:
        raise UnityTrainerError(f"Die Haken-Methode laesst sich nicht haken: {e}") from e
    p.hook_len = stolen_len
    p.cave, reserved = sl.alloc_code(cave_size(options, len(probe)), hook_addr)

    def stolen(addr):
        return relocate(head, hook_addr, addr, dis)[1]

    p.cave_bytes = build_cave(p.cave, p.flag_addr, hook_addr + stolen_len, stolen, options, base)
    if len(p.cave_bytes) > reserved:
        raise UnityTrainerError(f"Cave-Groesse stimmt nicht ({len(p.cave_bytes)} > {reserved}) - Programmfehler")
    live = bytes(read(p.cave, len(p.cave_bytes)))
    reclaim = getattr(sl, "last_reclaim", None)
    if reclaim is not None:                   # Rest einer frueheren ReaperPy-Cave: gilt als frei
        n = len(p.cave_bytes)
        p.cave_orig = bytes([reclaim]) * n    # "Original" = Padding, so bleibt der Trainer auf einer frischen Konsole gueltig
        p.verify_also = [x for x in dict.fromkeys((live, bytes([0xCC]) * n, bytes(n))) if x not in (p.cave_orig, p.cave_bytes)]
        p.warnings.append("Die Cave liegt auf den Resten einer frueheren ReaperPy-Cave (Trainer war auf dieser Konsole schon "
                          "einmal aktiv / ueber GoldHEN geladen). Zuerst die alte BASIS bzw. den GoldHEN-Cheat AUSschalten.")
    else:
        p.cave_orig = live
        if len(set(p.cave_orig)) != 1 or p.cave_orig[0] not in TR.FILL:
            raise UnityTrainerError(f"Cave-Platz {p.cave:#x} ist nicht leer (das Spiel hat dort Daten)")
    if abs(p.cave - hook_addr) >= 0x7FFFFFFF:
        raise UnityTrainerError("Cave liegt zu weit vom Haken entfernt")
    p.hook_orig = head[:stolen_len]
    p.hook_new = b"\xE9" + struct.pack("<i", p.cave - (hook_addr + 5)) + b"\x90" * (stolen_len - 5)
    if p.hook_orig == p.hook_new:
        raise UnityTrainerError("Haken ist schon gesetzt")
    return p


def _var(label, offset, default="", new=""):
    return {"label": label, "offset": hex(offset), "defaultValue": default, "newValue": new}


def base_patch(p, author=""):
    """Cave schreiben, DANN den Funktionsanfang umbiegen (Reihenfolge = Schreibreihenfolge; Abbau umgekehrt)."""
    sp = TR._spaced
    variables = [_var("OriginSource", p.rva(p.cave), sp(p.cave_orig), sp(p.cave_bytes)),
                 _var("Haken (Anfang der Update-Methode)", p.rva(p.hook_addr), sp(p.hook_orig), sp(p.hook_new))]
    doc = {"name": "00 BASIS - Item-Cave (zuerst aktivieren)", "author": author,
           "ImageBase": hex(p.base), "Verify": True, "Variables": variables}
    if p.verify_also:                                     # patch_engine akzeptiert diese Inhalte zusaetzlich zum Original
        doc["VerifyAlso"] = [sp(x) for x in p.verify_also]
    return doc


def option_patch(p, i, author=""):
    return TR.option_patch(p, i, author)


def spec_document(p, game="", title_id=""):
    return {
        "format": FORMAT, "version": 1, "game": game, "title_id": title_id,
        "image_base": hex(p.base), "hook_rva": hex(p.hook_addr - p.base), "hook_len": p.hook_len,
        "hook_title": p.hook_title, "cave_rva": hex(p.cave - p.base), "cave_size": len(p.cave_bytes),
        "flag_rva": hex(p.flag_addr - p.base), "flag_size": p.flag_size,
        "call": p.call.to_json(), "anchors": TR._anchors_json(p.anchors),
        "options": [o.to_json() for o in p.options],
    }


def load_spec(out_dir):
    try:
        with open(os.path.join(out_dir, SPEC_FILE), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("format") == FORMAT else None


def load_options(out_dir):
    d = load_spec(out_dir)
    if not d:
        return []
    call = Call.from_json(d["call"])
    return [Option(o["name"], [UnityRow(r["alias"], call, r["id"], r["amount"]) for r in o["rows"]]) for o in d["options"]]


def file_name_for(i, opt):
    return TR.file_name_for(i, opt)


def readme_text(p, project_name):
    lines = [
        f"ReaperPy Unity-Item-Trainer: {project_name}",
        "=" * (len(project_name) + 30),
        "",
        "BENUTZUNG",
        "  1. Spiel starten, Spielstand LADEN (nicht im Hauptmenue bleiben), in ReaperPy verbinden, diesen Ordner als",
        "     Projekt waehlen.  Die Image-Basis steht schon in den Dateien.",
        "  2. '00 BASIS - Item-Cave' EINMAL aktivieren (schreibt die Cave und biegt den Anfang der Update-Methode um).",
        "  3. Danach ein Eintrag = ein Klick: Er setzt sein Schalter-Byte auf 1, das Spiel legt beim naechsten Durchlauf",
        "     der Update-Methode die Items ins Inventar und setzt den Schalter selbst zurueck.  Im Spiel bleiben (nicht",
        "     pausieren), Inventar danach neu oeffnen.  Zeigt die Karte noch 'AN': einmal aus- und wieder anklicken.",
        "  4. Zum Beenden BASIS deaktivieren (stellt die Original-Bytes der Methode wieder her).",
        "",
        "EINTRAEGE",
    ]
    for i, o in enumerate(p.options):
        lines.append(f"  {i + 1:02d} {o.name}: " + ", ".join(f"{r.alias} x{r.amount}" for r in o.rows[:6])
                     + (f" ... (+{len(o.rows) - 6})" if len(o.rows) > 6 else ""))
    lines += [
        "",
        "TECHNIK (Offsets = RVA, Basis " + hex(p.base) + ")",
        f"  Geben-Methode  {p.call.function}  base+{p.call.impl_rva:#x}",
        f"  Haken          {p.hook_title or '?'}  base+{p.hook_addr - p.base:#x}  ({p.hook_len} Byte verschoben)",
        f"  Cave           base+{p.cave - p.base:#x}  ({len(p.cave_bytes)} Byte, Code-Padding)",
        f"  Schalter       base+{p.flag_addr - p.base:#x}  ({p.flag_size} Byte, 1 Byte je Eintrag, Reihenfolge wie oben)",
        "",
        "WICHTIG / NICHT GETESTET",
        "  * Nur fuer diese Spielversion.  Nach einem Spiel-Update neu exportieren.",
        "  * Am echten Spiel/an der PS5 NICHT getestet.  Die Cave wurde auf einem x86-64-Prozessor ausgefuehrt",
        "    (Register, Stack, Schalter, verschobene Befehle), aber nicht im Spiel.  Vorher speichern.",
        "  * Items, die der Spielstand nicht kennt (nicht freigeschaltet/Test-Items), koennen das Spiel zum Absturz",
        "    bringen - im Zweifel erst ein einzelnes Paket ausprobieren.",
        "  * Die Geben-Methode wird mit MethodInfo = 0 aufgerufen (wie bei den meisten Unity-Trainern ueblich).",
        "  * GoldHEN/etaHEN: Die Dateien sind einfache Hex-Patches; der Export 'alle geladenen Patches -> GoldHEN-JSON'",
        "    wandelt sie um (BASIS + Eintraege als Checkboxen).",
    ]
    for w in p.warnings:
        lines.append("  * " + w)
    return "\n".join(lines) + "\n"


def write_project(out_dir, p, project_name=None, game="", title_id="", author="", set_image_base=None):
    """Schreibt den Projekt-Ordner.  Alte Eintrag-Dateien dieses Trainers werden vorher entfernt (falsche Schalter-Nummern)."""
    os.makedirs(out_dir, exist_ok=True)
    project_name = project_name or os.path.basename(os.path.normpath(out_dir))
    for i, o in enumerate(load_options(out_dir)):
        f = os.path.join(out_dir, file_name_for(i, o))
        if os.path.isfile(f):
            os.remove(f)
    written = []

    def put(name, doc):
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        written.append(path)

    put(BASE_FILE, base_patch(p, author))
    for i, o in enumerate(p.options):
        put(file_name_for(i, o), option_patch(p, i, author))
    put(SPEC_FILE, spec_document(p, game, title_id))
    path = os.path.join(out_dir, README_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(readme_text(p, project_name))
    written.append(path)
    if set_image_base:
        try:
            set_image_base(p.base)
        except Exception:  # noqa: BLE001 - nur Komfort
            pass
    return written


def project_dirs(base_dir, n, name="Items"):
    return IT.project_dirs(base_dir, n, name)


# ----------------------------------------------------------------------------------------------------------------
# 9) Vorschau vor dem Schreiben und Pruefung eines fertigen Trainers
# ----------------------------------------------------------------------------------------------------------------
def preview_lines(p, maps):
    """Plan -> Textzeilen fuer die Rueckfrage vor dem Speichern (es wurde noch nichts geschrieben)."""
    def where(a):
        r = TR.region_info(maps, a)
        return f"Region {r[0]:#x}-{r[1]:#x} ({r[2]})" if r else "ausserhalb bekannter Regionen"
    rows = sum(len(o.rows) for o in p.options)
    lines = [f"{len(p.options)} Einträge, {rows} Items",
             f"Haken: base+{p.hook_addr - p.base:#x} ({p.hook_title or '?'}) - {p.hook_len} Byte werden in die Cave verschoben",
             f"Cave: base+{p.cave - p.base:#x} ({p.cave:#x}), {len(p.cave_bytes)} Byte - {where(p.cave)}",
             f"Schalter: base+{p.flag_addr - p.base:#x} ({p.flag_addr:#x}), {p.flag_size} Byte - {where(p.flag_addr)}"]
    r = TR.region_info(maps, p.cave)
    if r and "w" in r[2]:
        lines.append("WARNUNG: Die Cave liegt in einer beschreibbaren Region (rwx) - nur Ausweichplatz, bitte testen.")
    if p.anchors:
        lines.append(f"Versions-Prüfung: {len(p.anchors)} Funktions-Anker")
    return lines


def check_project(out_dir, client, maps, base):
    """Trainer-Ordner gegen das laufende Spiel pruefen (nur Lesen).  -> dict(ok, problems, active)
    Der Haken ist bei aktivem Trainer absichtlich veraendert: dann steht dort der Sprung zur Cave (das ist in Ordnung)."""
    d = load_spec(out_dir)
    if not d:
        raise UnityTrainerError(f"Kein Unity-Trainer in {out_dir} ({SPEC_FILE} fehlt)")
    problems = []
    spec_base = int(d.get("image_base", "0x0"), 16)
    if spec_base != base:
        problems.append(f"Modul-Basis: Trainer {spec_base:#x}, Spiel {base:#x}")
    hook_rva, cave_rva = int(d["hook_rva"], 16), int(d["cave_rva"], 16)
    active = False
    try:
        head = bytes(client.read_memory(base + hook_rva, 5))
        if head[0] == 0xE9 and base + hook_rva + 5 + struct.unpack_from("<i", head, 1)[0] == base + cave_rva:
            active = True
    except Exception as e:  # noqa: BLE001
        problems.append(f"Haken nicht lesbar ({e})")
    anchors = dict(d.get("anchors") or {})
    if isinstance(anchors, dict):
        if active:
            anchors.pop("hook_function", None)                  # der Anfang ist durch den eigenen Haken ersetzt
        res = TR.check_anchors(client, maps, base, dict(d, anchors=anchors))
        msg = TR.anchor_problem(res, base)
        if msg:
            problems.append(msg)
    elif not anchors:
        problems.append("Der Trainer enthaelt keinen Versions-Fingerabdruck - neu bauen")
    return {"ok": not problems, "problems": problems, "active": active}
