#!/usr/bin/env python3
"""cavemaker.py - Logik für Cheats aus einer dump.cs: auswählen, Wert setzen, Code-Cave erzeugen, testen.

Bedienung: Tab UNITY > CAVEMAKER (tools_unity_cave_gui.py); Prüfung vor dem Speichern: cave_check.py.
Keine Oberfläche, mit Tests (tests/test_cavemaker_core.py).

Ablauf
    1. dump.cs laden (script.json im selben Ordner wird automatisch mitgenommen -> statische Felder möglich)
    2. Mit der Konsole verbinden (ps5debug), Modul mit dem IL2CPP-Code wählen
    3. In der Liste etwas wählen (Suche, Kategorie), Wert / Flag eintragen
    4. HINZUFÜGEN: das Tool liest die Original-Bytes live, baut Patch oder Code-Cave und eine Signatur
    5. TEST AN / TEST AUS direkt auf der Konsole, SPEICHERN als .reapproj / .ReapPatch / .json,
       ALLE EXPORTIEREN als GoldHEN/etaHEN (.json / .shn / .mc4)

Was das Tool erzeugt (je nach Auswahl)
    ret      Rückgabewert festlegen        einfacher Patch   mov eax,N / ret
    void     Methode leer machen            einfacher Patch   ret
    param    Parameter einer Methode        Code-Cave         Register vor den Original-Befehlen ändern
    obj      Feld eines Objekt-Parameters   Code-Cave         z. B. evt.m_CoinValue bei OnAddCoin(evt)
    inst     Feld von 'this' festhalten     Code-Cave         in einer Methode derselben Klasse
    static   statisches Feld festhalten     Code-Cave         braucht script.json (TypeInfo-Zeiger)
"""
import json
import math
import os
import re
import struct
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ReaperPy-Module - werden in init_reaperpy() geladen (Tests setzen sie selbst)
D = AT = PE = AOB = RP = RF = EG = PB = PRJ = None


def init_reaperpy():
    global D, AT, PE, AOB, RP, RF, EG, PB, PRJ
    try:
        import il2cpp_dump as _d
        import asm_tools as _at
        import patch_engine as _pe
        import aob as _aob
        import reapatch as _rp
        import reappatch_fmt as _rf
        import export_goldhen as _eg
        import ps5_backend as _pb
        import projects as _prj
    except ImportError as e:
        raise RuntimeError(f"ReaperPy-Module fehlen ({e}). cavemaker.py muss im ReaperPy-Ordner liegen "
                           f"und mit demselben Python gestartet werden wie ReaperPy.") from e
    D, AT, PE, AOB, RP, RF, EG, PB, PRJ = _d, _at, _pe, _aob, _rp, _rf, _eg, _pb, _prj


# ======================================================================
# Typen
# ======================================================================
INT_TYPES = {"bool": (1, False), "byte": (1, False), "sbyte": (1, True), "char": (2, False),
             "short": (2, True), "ushort": (2, False), "int": (4, True), "uint": (4, False),
             "long": (8, True), "ulong": (8, False)}
FLT_TYPES = {"float": 4, "double": 8}
ALIASES = {"Boolean": "bool", "Byte": "byte", "SByte": "sbyte", "Char": "char", "Int16": "short",
           "UInt16": "ushort", "Int32": "int", "UInt32": "uint", "Int64": "long", "UInt64": "ulong",
           "Single": "float", "Double": "double"}
ENUM_UNDER = {"int8": (1, True), "uint8": (1, False), "int16": (2, True), "uint16": (2, False),
              "int32": (4, True), "uint32": (4, False), "int64": (8, True), "uint64": (8, False)}
STRUCT_GENERICS = {"Nullable", "KeyValuePair", "ValueTuple", "ValueTask", "ArraySegment", "Span", "ReadOnlySpan"}
INT_REG64 = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
INT_REG32 = ("edi", "esi", "edx", "ecx", "r8d", "r9d")
STATIC_OFF = 0xB8                  # Il2CppClass.static_fields
MASK32, MASK64 = 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF
LABEL = "cm_skip"

MODE_NAMES = {"set": "festlegen (=)", "mul": "vervielfachen (x)", "add": "addieren (+)", "min": "mindestens (>=)"}


@dataclass
class TI:
    kind: str          # int | float | ref | struct | void | unknown
    size: int = 0
    signed: bool = False
    name: str = ""
    enum: bool = False


@dataclass
class Param:
    mod: str
    type: str
    name: str
    info: TI


@dataclass
class Slot:
    kind: str          # int | xmm
    idx: int
    reg: str


def split_top(s, sep=","):
    out, depth, cur = [], 0, []
    for ch in s:
        if ch in "<([":
            depth += 1
        elif ch in ">])":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [p.strip() for p in out if p.strip()]


def clean_name(n):
    m = re.match(r"^<(.+)>k__BackingField$", n)
    return m.group(1) if m else n


def tokens(name):
    return [t.lower() for t in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", clean_name(name))]


# ======================================================================
# Werte
# ======================================================================
def f32_bits(x):
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def f64_bits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


def s32(v):
    v &= MASK32
    return v - (1 << 32) if v >= 1 << 31 else v


def s64(v):
    v &= MASK64
    return v - (1 << 64) if v >= 1 << 63 else v


def norm_value(ti, raw, mode="set"):
    """Eingabe (Text / bool) -> Zahl, mit verständlichen Fehlern."""
    if ti.name == "bool":
        if isinstance(raw, str):
            return 1 if raw.strip().lower() in ("1", "true", "an", "ja", "wahr", "on") else 0
        return 1 if raw else 0
    s = str(raw).strip().replace(",", ".")
    if not s:
        raise ValueError("Wert fehlt")
    if ti.kind == "float":
        try:
            v = float(s)
        except ValueError:
            raise ValueError(f"'{raw}' ist keine Zahl") from None
        if not math.isfinite(v) or (ti.size == 4 and abs(v) > 3.4028234e38):
            raise ValueError("Wert außerhalb des Bereichs")
        return v
    try:
        v = int(s, 0)
    except ValueError:
        try:
            f = float(s)
        except ValueError:
            raise ValueError(f"'{raw}' ist keine Zahl") from None
        if f != int(f):
            raise ValueError("Ganze Zahl erwartet")
        v = int(f)
    bits = ti.size * 8
    lo, hi = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if ti.signed else (0, (1 << bits) - 1)
    if not lo <= v <= hi:
        raise ValueError(f"Wert außerhalb des Bereichs ({lo} .. {hi})")
    if mode in ("mul", "add") and not -(1 << 31) <= v < (1 << 31):
        raise ValueError("Für x und + sind nur Werte bis 2147483647 möglich")
    return v


# ======================================================================
# Erzeuger fuer Assembler-Zeilen (Intel-Syntax, Keystone)
# ======================================================================
def mov_imm64(reg, v):
    sv = s64(v)
    if -(1 << 31) <= sv < (1 << 31):
        return f"mov {reg}, {sv}"
    return f"movabs {reg}, {v & MASK64:#x}"


def ret_asm(ti, value):
    if ti.kind == "float":
        if ti.size == 4:
            return [f"mov eax, {f32_bits(value):#x}", "movd xmm0, eax", "ret"]
        return [f"movabs rax, {f64_bits(value):#x}", "movq xmm0, rax", "ret"]
    if ti.size == 8:
        return [f"movabs rax, {value & MASK64:#x}", "ret"]
    return [f"mov eax, {value & MASK32:#x}", "ret"]


def void_asm(ret_ti):
    if ret_ti.kind == "float":
        return ["xor eax, eax", "xorps xmm0, xmm0", "ret"]
    if ret_ti.kind == "void":
        return ["ret"]
    return ["xor eax, eax", "ret"]


def prelude_param(ti, slot, mode, v):
    """Argument in Register / xmm ändern (nur rax, xmm15 als Hilfsregister)."""
    L = []
    if slot.kind == "int":
        if ti.size == 8:
            r = slot.reg
            if mode == "set":
                L.append(mov_imm64(r, v))
            elif mode == "mul":
                L.append(f"imul {r}, {r}, {s32(v)}")
            elif mode == "add":
                L.append(f"add {r}, {s32(v)}")
        else:
            r = INT_REG32[slot.idx]
            if mode == "set":
                L.append(f"mov {r}, {v & MASK32:#x}")
            elif mode == "mul":
                L.append(f"imul {r}, {r}, {s32(v)}")
            elif mode == "add":
                L.append(f"add {r}, {s32(v)}")
    else:
        x = slot.reg
        if ti.size == 4:
            L.append(f"mov eax, {f32_bits(v):#x}")
            if mode == "set":
                L.append(f"movd {x}, eax")
            else:
                L += ["movd xmm15, eax", f"{'mulss' if mode == 'mul' else 'addss'} {x}, xmm15"]
        else:
            L.append(f"movabs rax, {f64_bits(v):#x}")
            if mode == "set":
                L.append(f"movq {x}, rax")
            else:
                L += ["movq xmm15, rax", f"{'mulsd' if mode == 'mul' else 'addsd'} {x}, xmm15"]
    return L


def prelude_mem(base, off, ti, mode, v):
    """Wert in [base+off] ändern.  base: rdi..r9 oder r11 (nie rax/r10); Hilfsregister rax, r10, xmm14, xmm15."""
    op = f"[{base} + {off:#x}]"
    L = []
    if ti.kind == "float":
        if ti.size == 4:
            bits = f32_bits(v)
            if mode == "set":
                L.append(f"mov dword ptr {op}, {bits:#x}")
            else:
                ins = {"mul": "mulss", "add": "addss", "min": "maxss"}[mode]
                L += [f"movss xmm15, dword ptr {op}", f"mov eax, {bits:#x}", "movd xmm14, eax",
                      f"{ins} xmm15, xmm14", f"movss dword ptr {op}, xmm15"]
        else:
            bits = f64_bits(v)
            if mode == "set":
                L += [f"movabs rax, {bits:#x}", f"mov qword ptr {op}, rax"]
            else:
                ins = {"mul": "mulsd", "add": "addsd", "min": "maxsd"}[mode]
                L += [f"movsd xmm15, qword ptr {op}", f"movabs rax, {bits:#x}", "movq xmm14, rax",
                      f"{ins} xmm15, xmm14", f"movsd qword ptr {op}, xmm15"]
        return L
    size = ti.size
    ptr = {1: "byte", 2: "word", 4: "dword", 8: "qword"}[size]
    if mode == "set":
        if size == 8:
            sv = s64(v)
            if -(1 << 31) <= sv < (1 << 31):
                L.append(f"mov qword ptr {op}, {sv}")
            else:
                L += [f"movabs rax, {v & MASK64:#x}", f"mov qword ptr {op}, rax"]
        else:
            L.append(f"mov {ptr} ptr {op}, {v & ((1 << (8 * size)) - 1):#x}")
    elif mode == "add":
        L.append(f"add {ptr} ptr {op}, {s32(v)}")
    elif mode == "mul":
        if size == 8:
            L += [f"imul rax, qword ptr {op}, {s32(v)}", f"mov qword ptr {op}, rax"]
        else:
            L += [f"imul eax, dword ptr {op}, {s32(v)}", f"mov dword ptr {op}, eax"]
    elif mode == "min":
        cc = "l" if ti.signed else "b"
        if size == 8:
            L += [f"mov rax, qword ptr {op}", f"movabs r10, {v & MASK64:#x}", "cmp rax, r10",
                  f"cmov{cc} rax, r10", f"mov qword ptr {op}, rax"]
        else:
            L += [f"mov eax, dword ptr {op}", f"mov r10d, {v & MASK32:#x}", "cmp eax, r10d",
                  f"cmov{cc} eax, r10d", f"mov dword ptr {op}, eax"]
    return L


def null_checked(reg, lines):
    return [f"test {reg}, {reg}", f"jz {LABEL}"] + lines


def prelude_static(slot_rva, hook_rva, off, ti, mode, v, abs_slot=None):
    """Statisches Feld: TypeInfo-Slot -> Klasse -> static_fields -> Feld.
    Mit abs_slot (absolute Adresse des Slots) wird 'movabs' benutzt - das erreicht jede Cave, egal wie weit
    der Slot weg ist. Ohne abs_slot rip-relativ (@hook), das nur innerhalb von +-2 GB der Cave klappt."""
    if abs_slot is not None:
        load = [f"movabs r11, {abs_slot & MASK64:#x}", "mov r11, qword ptr [r11]"]
    else:
        delta = slot_rva - hook_rva
        tok = f"@hook{'+' if delta >= 0 else '-'}{abs(delta):#x}"
        load = [f"mov r11, qword ptr [rip + {tok}]"]
    pre = load + ["test r11, r11", f"jz {LABEL}",
                  f"mov r11, qword ptr [r11 + {STATIC_OFF:#x}]", "test r11, r11", f"jz {LABEL}"]
    return pre + prelude_mem("r11", off, ti, mode, v)


# ======================================================================
# Modell des Dumps
# ======================================================================
CATS = [
    ("Geld", {"money", "coin", "coins", "cash", "gold", "gem", "gems", "diamond", "diamonds", "currency", "credit",
              "credits", "buck", "bucks", "dollar", "silver", "wallet", "balance", "funds",
              "price", "cost", "purchase", "buy", "sell", "income", "profit", "revenue", "earn", "salary",
              "wage", "gil", "zeny", "rupee", "crystal", "shard", "fame", "geld", "munzen"}),
    ("EXP/Level", {"exp", "xp", "experience", "level", "lvl", "rank", "tier", "prestige", "reputation", "skill",
                   "perk", "talent", "mastery", "progress", "stufe", "erfahrung"}),
    ("Leben/Schaden", {"health", "hp", "life", "lives", "heal", "damage", "dmg", "armor", "armour", "shield",
                       "defense", "defence", "invincible", "immortal", "revive", "hurt", "regen", "vitality",
                       "leben", "schaden"}),
    ("Ressource", {"energy", "stamina", "mana", "mp", "sp", "fuel", "ammo", "ammunition", "bullet", "magazine",
                   "clip", "reload", "charge", "power", "oxygen", "hunger", "thirst", "food", "water",
                   "durability", "battery", "boost", "rage", "focus"}),
    ("Item/Inventar", {"item", "items", "inventory", "capacity", "slot", "slots", "stack", "amount", "count",
                       "quantity", "weight", "carry", "storage", "bag", "backpack", "craft", "resource",
                       "material", "ingredient", "loot", "reward", "chest", "card", "cards"}),
    ("Freischaltung", {"unlock", "unlocked", "owned", "purchased", "achievement", "trophy", "collected",
                       "requirement", "require", "enough", "afford", "license"}),
    ("Zeit/Tempo", {"timer", "cooldown", "delay", "duration", "speed", "velocity", "jump", "fly", "gravity",
                    "sprint", "accel"}),
    ("Kampf", {"enemy", "attack", "crit", "critical", "range", "aggro", "target", "spawn", "wave", "boss"}),
]
V_CHANGE = {"add", "give", "grant", "reward", "earn", "gain", "increase", "increment", "collect", "receive",
            "deposit", "reduce", "spend", "pay", "consume", "remove", "take", "deduct", "decrease", "decrement",
            "lose", "drain", "use", "withdraw", "subtract", "damage", "hurt", "set"}
V_QUERY = {"is", "has", "can", "should", "need", "check", "enough", "afford", "require"}
KIND_NAMES = {"method": "Methode", "field": "Feld"}


@dataclass
class Cand:
    kind: str                  # method | field
    cls: object
    mem: object                # Method | Field
    score: int
    cat: str
    label: str
    sig: str
    hay: str


class Model:
    def __init__(self, classes, typeinfo=None, log=print):
        self.log = log
        self.classes = classes
        self.typeinfo = typeinfo or {}
        self.by_full, self.by_name = {}, {}
        for c in classes:
            self.by_full.setdefault(c.full, c)
            self.by_name.setdefault(c.name, []).append(c)
        self._parent = {}
        self._cf = {}
        self.rvas =sorted({m.rva for c in classes for m in c.methods if m.rva})
        self.rva_users = Counter(m.rva for c in classes for m in c.methods if m.rva)
        self._cands = {}

    # --- Typen ---
    def find_class(self, typ):
        base = typ.split("<", 1)[0].strip()
        if base in self.by_full:
            return self.by_full[base]
        cs = self.by_name.get(base)
        return cs[0] if cs else None

    def resolve(self, t):
        t = (t or "").strip()
        if t.startswith("ref "):
            t = t[4:].strip()
        if t == "void":
            return TI("void", 0, False, t)
        key = t[7:] if t.startswith("System.") else t
        key = ALIASES.get(key, key)
        if key in INT_TYPES:
            return TI("int", INT_TYPES[key][0], INT_TYPES[key][1], key)
        if key in FLT_TYPES:
            return TI("float", FLT_TYPES[key], True, key)
        if key in ("string", "object") or key.endswith("]") or key.endswith("*"):
            return TI("ref", 8, False, key)
        base = key.split("<", 1)[0].strip()
        cs = self.by_name.get(base) or ([self.by_full[base]] if base in self.by_full else [])
        kinds = {c.kind for c in cs}
        if len(kinds) == 1:
            k = kinds.pop()
            if k == "enum":
                size, signed = ENUM_UNDER.get(cs[0].enum_underlying, (4, True))
                return TI("int", size, signed, key, True)
            if k == "struct":
                return TI("struct", 0, False, key)
            return TI("ref", 8, False, key)
        if len(kinds) > 1:
            return TI("unknown", 0, False, key)
        if base in STRUCT_GENERICS:
            return TI("struct", 0, False, key)
        if "<" in key:
            return TI("ref", 8, False, key)
        return TI("unknown", 0, False, key)

    def parent(self, c):
        if c.full in self._parent:
            return self._parent[c.full]
        par = None
        b = (c.base or "").split(",")[0].strip().split("<")[0].strip()
        if b and c.kind == "class":
            par = self.by_full.get(f"{c.namespace}.{b}" if c.namespace else b) or self.by_full.get(b)
            if par is None:
                cs = self.by_name.get(b)
                par = cs[0] if cs else None
            if par is c:
                par = None
        self._parent[c.full] = par
        return par

    def chain(self, c, cap=16):
        out = []
        while c is not None and len(out) < cap:
            out.append(c)
            c = self.parent(c)
        return out

    def chain_fields(self, c):
        """Primitive Instanzfelder der Klasse und ihrer Basisklassen: [(Klasse, Feld, TI)]."""
        if c.full in self._cf:
            return self._cf[c.full]
        out = []
        for k in self.chain(c):
            for f in k.fields:
                if f.static or f.const_value is not None or f.offset < 0x10:
                    continue
                ti = self.resolve(f.type)
                if ti.kind in ("int", "float"):
                    out.append((k, f, ti))
        self._cf[c.full] = out
        return out

    def can_set_value(self, m):
        """Schnelle Prüfung: gibt es bei dieser Methode mindestens eine Aktion, die einen WERT setzt?
        (Rückgabewert, Parameter oder Feld eines Objekt-Parameters - 'Methode leer machen' zählt nicht.)"""
        if not self.hookable(m)[0]:
            return False
        if self.resolve(m.ret).kind in ("int", "float"):
            return True
        params, slots = self.slots_of(m)
        for p, s in zip(params, slots):
            if s is None or p.mod:
                continue
            if p.info.kind in ("int", "float"):
                return True
            if p.info.kind == "ref":
                cls = self.find_class(p.type)
                if cls is not None and cls.kind == "class" and self.chain_fields(cls):
                    return True
        return False

    def can_set_field(self, c, f, ti):
        """Instanzfeld: immer (Cave in Instanz-Methode). Statisch: nur mit TypeInfo aus script.json."""
        if ti.kind not in ("int", "float"):
            return False
        if f.static:
            return c.full in self.typeinfo and f.offset >= 0
        return f.offset >= 0x10

    def bound(self, rva):
        """Höchstlänge der Funktion (Abstand zur nächsten Methode) oder None."""
        import bisect
        i = bisect.bisect_right(self.rvas, rva)
        return self.rvas[i] - rva if i < len(self.rvas) else None

    # --- Aufrufkonvention (System V) ---
    def params_of(self, m):
        res = []
        for p in split_top(m.params):
            p = re.split(r"\s=\s", p, maxsplit=1)[0].strip()
            mod = ""
            mm = re.match(r"^(ref|out|in|params)\s+(.*)$", p)
            if mm:
                mod, p = mm.group(1), mm.group(2)
            if " " not in p:
                continue
            typ, name = p.rsplit(" ", 1)
            res.append(Param(mod, typ.strip(), name, self.resolve(typ.strip())))
        return res

    def slots_of(self, m):
        """(Parameter, Slots): Slot = Register des Arguments oder None (nicht abbildbar)."""
        params = self.params_of(m)
        ret = self.resolve(m.ret)
        ok = ret.kind not in ("struct", "unknown")
        ints = 0 if m.static else 1
        floats = 0
        slots = []
        for p in params:
            if not ok:
                slots.append(None)
            elif p.mod or p.info.kind in ("int", "ref"):
                if ints >= 6:
                    ok = False
                    slots.append(None)
                else:
                    slots.append(Slot("int", ints, INT_REG64[ints]))
                    ints += 1
            elif p.info.kind == "float":
                if floats >= 8:
                    ok = False
                    slots.append(None)
                else:
                    slots.append(Slot("xmm", floats, f"xmm{floats}"))
                    floats += 1
            else:
                ok = False
                slots.append(None)
        return params, slots

    def hookable(self, m):
        """(ok, Grund) - kann man an den Anfang dieser Methode einen Hook setzen?"""
        if not m.rva:
            return False, "keine Adresse im Dump"
        if "<" in m.cls.name:
            return False, "generische Klasse (geteilter Code)"
        if "<" in m.name or m.name in (".cctor",):
            return False, "vom Compiler erzeugt"
        n = self.rva_users.get(m.rva, 1)
        if n > 1:
            return False, f"Code wird von {n} Methoden geteilt"
        b = self.bound(m.rva)
        if b is not None and b < 8:
            return False, "Funktion kürzer als der Hook (8 Byte)"
        return True, ""

    # --- Kandidaten ---
    def candidates(self, include_libs=False):
        if include_libs in self._cands:
            return self._cands[include_libs]
        out = []
        for c in self.classes:
            if c.kind == "enum" or "<" in c.name or D.is_generated(c):
                continue
            if not include_libs and not c.image.startswith("Assembly-CSharp"):
                continue
            ctoks = set(tokens(c.name.rsplit(".", 1)[-1]))
            for m in c.methods:
                if not m.rva or "<" in m.name:
                    continue
                if not self.can_set_value(m):
                    continue                      # nichts, wo man einen Wert setzen koennte
                out.append(self._cand_method(c, m, ctoks))
            for f in c.fields:
                if f.const_value is not None or (not f.static and f.offset < 0):
                    continue
                if D.is_generated(c, f):
                    continue
                ti = self.resolve(f.type)
                if not self.can_set_field(c, f, ti):
                    continue
                out.append(self._cand_field(c, f, ti, ctoks))
        out.sort(key=lambda x: (-x.score, x.label.lower()))
        self._cands[include_libs] = out
        return out

    def _score(self, name, ctoks, bonus):
        toks = tokens(name)
        best, cat = 0, "Sonstige"
        for cname, words in CATS:
            # Treffer nur auf ganzen Wort-Bausteinen des Namens (oder Plural/Endung bei >= 4 Buchstaben):
            # 'coin' trifft CoinValue / Coins, aber nicht 'decoIndex'.
            hits = sum(1 for w in words
                       if any(t == w or (len(w) >= 4 and t.startswith(w) and len(t) <= len(w) + 2) for t in toks))
            if hits == 0:
                continue                           # ohne Treffer im Namen zaehlt die Klasse allein nicht
            s = 3 * hits + len(words & ctoks)
            if s > best:
                best, cat = s, cname
        if best:
            best += bonus
        return best, cat

    def _cand_method(self, c, m, ctoks):
        first = (tokens(m.name) or [""])[0]
        bonus = 0
        params = m.params.strip()
        ret = m.ret
        if first in V_CHANGE and params:
            bonus += 2
        if first in V_QUERY and ret == "bool":
            bonus += 2
        score, cat = self._score(m.name, ctoks, bonus)
        label = f"{c.name}.{m.name}"
        sig = f"{m.ret} {m.name}({m.params})"
        return Cand("method", c, m, score, cat, label, sig, make_hay(label, sig, cat))

    def _cand_field(self, c, f, ti, ctoks):
        score, cat = self._score(f.name, ctoks, 1)
        name = clean_name(f.name)
        label = f"{c.name}.{name}"
        sig = f"{'static ' if f.static else ''}{f.type} {name}" + (f" @ {f.offset:#x}" if not f.static else "")
        return Cand("field", c, f, score, cat, label, sig, make_hay(label, sig, cat))


def make_hay(label, sig, cat):
    """Suchtext: Wort-Bausteine (CamelCase aufgeteilt) + Kleinschreibung des Labels."""
    toks = " ".join(tokens(label) + tokens(re.sub(r"\(.*", "", sig)))
    return f" {toks} {cat.lower()} |{label.lower()}"


def hay_match(hay, w):
    head, _, label = hay.partition("|")
    return f" {w}" in head or (len(w) >= 5 and w in label)


def filter_cands(cands, text="", cat="Alle", kind="Alle", only_scored=True, limit=3000):
    words = text.lower().split()
    out = []
    total = 0
    for c in cands:
        if cat != "Alle" and c.cat != cat:
            continue
        if kind == "Statisch (live)":
            if not is_static_field(c):
                continue
        elif kind != "Alle" and KIND_NAMES[c.kind] != kind:
            continue
        if only_scored and not words and c.score <= 0:   # mit Suchtext wird alles Setzbare durchsucht
            continue
        if words and not all(hay_match(c.hay, w) for w in words):
            continue
        total += 1
        if len(out) < limit:
            out.append(c)
    return out, total


# ======================================================================
# Aktionen (was man mit einer Auswahl machen kann)
# ======================================================================
@dataclass
class Action:
    key: str                   # ret | void | param | obj | inst | static
    label: str
    method: object = None      # Hook-Methode (bei inst/static: wird gewaehlt)
    owner: object = None       # Klasse des Zielfelds
    param_i: int = -1
    field: object = None
    ti: TI = None
    modes: tuple = ("set",)
    note: str = ""
    need_hook: bool = False    # Haken-Methode muss gewaehlt werden


def _modes(ti, base=("set", "mul", "add", "min")):
    if ti.name == "bool" or (ti.kind == "int" and ti.size < 4):
        return ("set",)
    return base


def actions_for_method(model, m):
    acts = []
    ok, why = model.hookable(m)
    if not ok:
        return [], why
    ret = model.resolve(m.ret)
    if ret.kind in ("int", "float"):
        acts.append(Action("ret", f"Rückgabewert festlegen ({m.ret})", m, ti=ret, modes=("set",)))
    if ret.kind in ("void", "int", "float", "ref"):
        acts.append(Action("void", "Methode leer machen (tut nichts)", m))
    params, slots = model.slots_of(m)
    for i, (p, s) in enumerate(zip(params, slots)):
        if s is None or p.mod:
            continue
        if p.info.kind in ("int", "float"):
            acts.append(Action("param", f"Parameter '{p.name}' ({p.type}) ändern", m, param_i=i, ti=p.info,
                               modes=_modes(p.info, ("set", "mul", "add"))))
        elif p.info.kind == "ref":
            cls = model.find_class(p.type)
            if cls is None or cls.kind != "class":
                continue
            fl = model.chain_fields(cls)
            # sinnvolle Felder (Wert/Menge/Betrag) zuerst, Flags wie NoLerp zuletzt
            fl = sorted(fl, key=lambda x: (-model._score(x[1].name, set(), 0)[0], x[1].offset))
            for owner, f, ti in fl:
                acts.append(Action("obj", f"Objekt '{p.name}' ({p.type}) -> {clean_name(f.name)} ({f.type})",
                                   m, owner=owner, param_i=i, field=f, ti=ti, modes=_modes(ti)))
    # 'leer machen' setzt keinen Wert -> nur als letzte Option
    acts.sort(key=lambda a: a.key == "void")
    return acts, ""


def actions_for_field(model, cls, f):
    ti = model.resolve(f.type)
    if ti.kind not in ("int", "float"):
        return [], "Typ nicht änderbar"
    modes = ("set",) if (ti.name == "bool" or ti.size < 4) else ("set", "min")
    if f.static:
        if cls.full not in model.typeinfo:
            return [], "Statisches Feld: script.json fehlt (TypeInfo-Zeiger) - neben dump.cs legen und neu laden"
        return [Action("static", f"Statisches Feld festhalten ({f.type})", None, owner=cls, field=f, ti=ti,
                       modes=modes, need_hook=True,
                       note="Die Cave läuft in einer Methode, die oft aufgerufen wird (z. B. Update).")], ""
    return [Action("inst", f"Feld von 'this' festhalten ({f.type})", None, owner=cls, field=f, ti=ti,
                   modes=modes, need_hook=True,
                   note="Die Cave läuft in einer Instanz-Methode derselben Klasse (z. B. Update).")], ""


UPDATE_NAMES = ("update", "lateupdate", "fixedupdate", "tick", "ongui", "process", "onupdate", "step")


def hook_choices(model, act):
    """Methoden, in die eine Feld-Cave gehängt werden kann: [(Anzeige, Method)]."""
    out = []
    if act.key == "inst":
        for k in model.chain(act.owner):
            for m in k.methods:
                if not m.static and model.hookable(m)[0]:
                    out.append(m)
    else:
        for m in act.owner.methods:
            if model.hookable(m)[0]:
                out.append(m)
        seen = {m.rva for m in out}
        extra = 0
        for c in model.classes:
            if extra >= 300 or c.kind != "class" or not c.image.startswith("Assembly-CSharp"):
                continue
            for m in c.methods:
                if m.name.lower() in UPDATE_NAMES and not m.static and m.rva not in seen and model.hookable(m)[0]:
                    out.append(m)
                    seen.add(m.rva)
                    extra += 1
    # Reihenfolge: Methoden, die JEDEN Frame laufen (Update & Co.), kommen zuerst - nur dort wirkt ein
    # 'Wert setzen' dauerhaft. Methoden wie OnAddCoin laufen nur bei einem Ereignis (Muenzen verdienen); ein
    # Cheat dort scheint beim Einschalten 'nichts zu tun'. Innerhalb der Gruppen: Klasse des Feldes bzw. Klassen,
    # deren Name zu Feld/Klasse passt, zuerst.
    ft = {t for t in tokens(act.field.name) + tokens(act.owner.name) if len(t) >= 3} if act.owner else set()
    boost = {"manager", "controller", "game", "instance", "main", "player"}

    def crel(m):
        ct = set(tokens(m.cls.name))
        return (3 if m.cls is act.owner else 0) + len(ft & ct) + (1 if boost & ct else 0)

    def rel(m):
        return len(ft & set(tokens(m.name)))

    out.sort(key=lambda m: (m.name.lower() not in UPDATE_NAMES, -crel(m), -rel(m), m.key))
    return [(f"{m.cls.name}.{m.name}({m.params})", m) for m in out]


def is_per_frame(m):
    return m.name.lower() in UPDATE_NAMES


# ======================================================================
# Patch bauen
# ======================================================================
@dataclass
class PatchDef:
    name: str
    offset: int
    hook_addr: int
    simple: bool
    default: str
    new: str
    ret_len: int = 0
    blocks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    summary: str = ""
    aob: str = ""
    hook_len: int = 8

    def preview(self):
        if self.simple:
            return f"; einfacher Patch @ {self.hook_addr:#x}\n; Original: {self.default}\n{self.new}\n"
        out = [f"; Cave-Hook @ {self.hook_addr:#x}  (OriginReturn = {self.ret_len} Byte)",
               f"; Original: {self.default}", ""]
        for i, (lbl, code) in enumerate(self.blocks):
            if i:
                out.append(f"{lbl}:")
            out.append(code)
        return "\n".join(out) + "\n"

    def to_json(self, author=""):
        src = {"label": "OriginSource", "offset": self.offset, "defaultValue": self.default, "newValue": self.new}
        if self.aob:
            src["aob"], src["aobOffset"] = self.aob, 0
        variables = [src]
        if not self.simple:
            variables.append({"label": "OriginReturn", "offset": self.ret_len})
            for lbl, code in self.blocks:
                variables.append({"label": lbl, "defaultValue": code})
        return {"name": self.name, "author": author, "Variables": variables}


class Ctx:
    """Zugriff auf die Konsole für das Bauen (read / assemble)."""

    def __init__(self, backend, module_base, image_base):
        self.backend, self.module_base, self.image_base = backend, module_base, image_base

    def read(self, addr, n):
        data = self.backend.read(addr, n)
        if data is None:
            raise RuntimeError(f"{addr:#x} nicht lesbar")
        return bytes(data)

    def asm(self, text, addr):
        return PE.asm_to_bytes(self.backend, text, addr)


RIP_RE = re.compile(r"\[\s*rip\s*\+\s*@hook\s*([+-])\s*(0x[0-9a-fA-F]+)\s*\]", re.I)
CALL_RE = re.compile(r"^call\s+@hook\s*([+-])\s*(0x[0-9a-fA-F]+)\s*$", re.I)


def relocate_far(body, hook_addr):
    """Die aus dem Hook kopierten Befehle dürfen keine rip-relativen Zugriffe auf weit entfernte Adressen
    enthalten (die Cave liegt in einer Lücke ganz vorn im Image, > 2 GB weg). Solche Zugriffe werden hier auf
    absolute Adressen umgestellt:  mov rax,[rip+X]  ->  movabs r11,ABS / mov rax,[r11]  (r10 falls r11 benutzt)."""
    out = []
    for ln in body:
        s = ln.strip()
        m = CALL_RE.match(s)
        if m:
            tgt = hook_addr + (int(m.group(2), 16) if m.group(1) == "+" else -int(m.group(2), 16))
            out += [f"movabs r11, {tgt & MASK64:#x}", "call r11"]
            continue
        ms = RIP_RE.findall(s)
        if len(ms) == 1:
            sign, hexd = ms[0]
            tgt = hook_addr + (int(hexd, 16) if sign == "+" else -int(hexd, 16))
            reg = next((r for r in ("r11", "r10") if not re.search(rf"\b{r}[dwb]?\b", s, re.I)), None)
            if reg is None:
                raise ValueError(f"Befehl am Anfang der Methode nicht verlagerbar (benutzt r10 und r11): '{s}'")
            out += [f"movabs {reg}, {tgt & MASK64:#x}", RIP_RE.sub(f"[{reg}]", s)]
            continue
        if "@hook" in s or re.search(r"\[\s*rip", s, re.I):
            raise ValueError(f"Befehl am Anfang der Methode nicht verlagerbar: '{s}' - "
                             f"bitte eine andere Haken-Methode nehmen")
        out.append(ln)
    return out


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


def build_patch(model, ctx, act, mode, value, hook_method=None, name=None):
    """Aktion + Modus + Wert -> PatchDef (liest die Original-Bytes live von der Konsole)."""
    hm = act.method if act.method is not None else hook_method
    if hm is None:
        raise ValueError("Haken-Methode fehlt")
    ok, why = model.hookable(hm)
    if not ok:
        raise ValueError(f"{hm.key}: {why}")
    if act.key == "inst" and hm.static:
        raise ValueError("Für ein Instanzfeld braucht es eine Instanz-Methode")
    if mode not in act.modes:
        raise ValueError(f"Modus '{MODE_NAMES.get(mode, mode)}' geht hier nicht")
    v = norm_value(act.ti, value, mode) if act.ti is not None and act.key not in ("void",) else None
    hook_addr = ctx.module_base + hm.rva
    offset = hook_addr - ctx.image_base
    first = ctx.read(hook_addr, 1)
    if first == b"\xE9":
        raise ValueError("Am Hook steht schon ein jmp (E9) - ist hier noch ein Patch aktiv? Erst TEST AUS.")
    warnings = []
    bound = model.bound(hm.rva)

    if act.key in ("ret", "void"):
        if act.key == "ret":
            lines = ret_asm(act.ti, v)
            what = f"gibt {value} zurück"
        else:
            lines = void_asm(model.resolve(hm.ret))
            what = "leer"
        asm = "\n".join(lines)
        raw = ctx.asm(asm, hook_addr)
        if bound is not None and len(raw) > bound:
            raise ValueError(f"Patch ({len(raw)} Byte) länger als die Funktion ({bound} Byte)")
        default = hexs(ctx.read(hook_addr, len(raw)))
        nm = name or f"{hm.cls.name}.{clean_name(hm.name)} {what}"
        return PatchDef(nm, offset, hook_addr, True, default, asm, hook_len=len(raw),
                        summary=f"Einfacher Patch: {len(raw)} Byte", warnings=warnings)

    # --- Cave ---
    scaffold = AT.build_cave_hook(ctx.read(hook_addr, 48), hook_addr)
    warnings += list(scaffold.get("warnings") or [])
    body = [ln for ln in scaffold["cave"].splitlines() if ln.strip() and not ln.strip().startswith(";")]
    body = relocate_far(body, hook_addr)
    needs_label = False
    if act.key == "param":
        params, slots = model.slots_of(hm)
        slot = slots[act.param_i]
        if slot is None:
            raise ValueError("Dieses Argument lässt sich nicht abbilden")
        pre = prelude_param(act.ti, slot, mode, v)
        what = f"{clean_name(params[act.param_i].name)} {MODE_NAMES[mode].split()[0]} {value}"
    elif act.key == "obj":
        params, slots = model.slots_of(hm)
        slot = slots[act.param_i]
        if slot is None or slot.kind != "int":
            raise ValueError("Dieses Argument lässt sich nicht abbilden")
        pre = null_checked(slot.reg, prelude_mem(slot.reg, act.field.offset, act.ti, mode, v))
        needs_label = True
        what = f"{clean_name(act.field.name)} {MODE_NAMES[mode].split()[0]} {value}"
    elif act.key == "inst":
        pre = null_checked("rdi", prelude_mem("rdi", act.field.offset, act.ti, mode, v))
        needs_label = True
        what = f"{clean_name(act.field.name)} {MODE_NAMES[mode].split()[0]} {value}"
    elif act.key == "static":
        slot_rva = model.typeinfo.get(act.owner.full)
        if slot_rva is None:
            raise ValueError("Kein TypeInfo-Zeiger (script.json) für diese Klasse")
        pre = prelude_static(slot_rva, hm.rva, act.field.offset if act.field.offset >= 0 else 0, act.ti, mode, v,
                             abs_slot=ctx.module_base + slot_rva)
        warnings.append("Statisches Feld: feste Adresse im Code (wie der Hook selbst) - gilt für diese "
                        "Modul-Basis, auf der gleichen Spiel-Version also immer.")
        needs_label = True
        what = f"{clean_name(act.field.name)} {MODE_NAMES[mode].split()[0]} {value}"
    else:
        raise ValueError(f"Unbekannte Aktion {act.key}")
    if act.key == "static" and act.field.offset < 0:
        raise ValueError("Statisches Feld ohne Offset im Dump")
    if needs_label:
        blocks = [("OriginTarget", "\n".join(pre)), (LABEL, "\n".join(body))]
    else:
        blocks = [("OriginTarget", "\n".join(pre + body))]
    owner = act.owner.name if act.owner is not None else hm.cls.name
    nm = name or f"{owner}.{clean_name(act.field.name) if act.field else clean_name(hm.name)} - {what}"
    return PatchDef(nm, offset, hook_addr, False, scaffold["default"], "jmp OriginTarget", scaffold["size"],
                    blocks, warnings, f"Code-Cave: Hook an {hm.cls.name}.{hm.name}", hook_len=8)


# ======================================================================
# Dump laden
# ======================================================================
def value_reached(ti, mode, cur, target):
    """Hat das Feld den Zielwert (set) bzw. mindestens den Zielwert (min)?"""
    if mode == "min":
        return cur >= target
    return encode_value(ti, cur) == encode_value(ti, target)


def different_value(ti, target):
    """Ein Wert, der sicher nicht der Zielwert ist (damit man eine Wirkung sehen kann)."""
    if ti.kind == "float":
        return target * 0.5 if target else 1.0
    lo = -(1 << (ti.size * 8 - 1)) if ti.signed else 0
    return target - 1 if target > lo else target + 1


def find_working_hook(model, ctx, act, mode, value, hooks, name, log, author="", wait=1.5, rearm=1.5):
    """Probiert Haken-Methoden live durch: Patch an, kurz warten, Wert lesen. Dann ein zweiter Test: Wert
    absichtlich verändern - setzt der Haken ihn wieder, läuft die Methode REGELMAESSIG (z. B. jeden Frame) und
    der Cheat wirkt dauerhaft. Läuft sie nur ab und zu (Ereignis-Methode), wird sie nur als Notlösung gemerkt.
    Liefert (PatchDef, ReapPatch, Zustand, Methode, regelmäßig:bool) oder None."""
    import time
    ti = act.ti
    target = norm_value(ti, value, mode)
    addr = static_addr(model, ctx, act.owner, act.field)

    def cur():
        return decode_value(ti, ctx.read(addr, ti.size))

    def load_rp(pd):
        fd, path = tempfile.mkstemp(suffix=".reapproj")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(pd.to_json(author), f)
        try:
            return RP.ReapPatch.load(path)
        finally:
            os.remove(path)

    def reached_within(sec):
        t0 = time.time()
        while time.time() - t0 < sec:
            time.sleep(0.2)
            if value_reached(ti, mode, cur(), target):
                return True
        return False

    def finish(pd, rp):
        """Patch mit Signatur versehen und (wieder) einschalten."""
        try:
            pat, _hits = AOB.make_signature(ctx.backend.client, ctx.backend.get_maps(), pd.hook_addr, pd.hook_len)
            pd.aob = pat
        except Exception as e:  # noqa: BLE001
            pd.warnings.append(f"Keine eindeutige Signatur ({e}) - Patch gilt nur für diese Basis")
        return PE.apply_patch(ctx.backend, rp, pd.hook_addr)

    weak = None                      # erster Haken, der nur ab und zu laeuft
    for k, hm in enumerate(hooks):
        log(f"[{k + 1}/{len(hooks)}] probiere {hm.cls.name}.{hm.name} ...")
        st = rp = pd = None
        try:
            if value_reached(ti, mode, cur(), target):
                write_mem(ctx.backend, addr, encode_value(ti, different_value(ti, target)))
            pd = build_patch(model, ctx, act, mode, value, hm, name)
            rp = load_rp(pd)
            st = PE.apply_patch(ctx.backend, rp, pd.hook_addr)
            if reached_within(wait):
                # Zweiter Test: Wert wieder veraendern - kommt der Haken regelmaessig vorbei?
                write_mem(ctx.backend, addr, encode_value(ti, different_value(ti, target)))
                regular = reached_within(rearm)
                PE.deactivate_patch(ctx.backend, rp, st)
                st = None
                if regular:
                    log("    läuft regelmäßig - das ist der richtige Haken.")
                    return pd, rp, finish(pd, rp), hm, True
                log("    läuft nur ab und zu (Ereignis-Methode) - merke ich mir als Notlösung, suche weiter.")
                if weak is None:
                    weak = (hm,)
        except Exception as e:  # noqa: BLE001
            log(f"    übersprungen: {e}")
        if st is not None and rp is not None:
            try:
                PE.deactivate_patch(ctx.backend, rp, st)
            except Exception as e:  # noqa: BLE001
                log(f"    Zurücksetzen fehlgeschlagen: {e}")
    if weak is not None:
        hm = weak[0]
        pd = build_patch(model, ctx, act, mode, value, hm, name)
        rp = load_rp(pd)
        return pd, rp, finish(pd, rp), hm, False
    return None


def live_key(c):
    return f"{c.cls.full}.{c.mem.name}"


def is_static_field(c):
    return c.kind == "field" and bool(c.mem.static)


def fmt_value(ti, raw):
    """Rohbytes -> lesbarer Text."""
    if ti.kind == "float":
        v = struct.unpack("<f" if ti.size == 4 else "<d", raw)[0]
        return f"{v:.6g}"
    v = int.from_bytes(raw, "little", signed=ti.signed)
    if ti.name == "bool":
        return "True" if v else "False"
    return str(v)


def read_static_values(model, ctx, cands):
    """Aktuelle Werte statischer Felder live von der Konsole lesen: {live_key: Text}."""
    out, sf_cache = {}, {}
    for c in cands:
        if not is_static_field(c):
            continue
        key = live_key(c)
        slot = model.typeinfo.get(c.cls.full)
        if slot is None or c.mem.offset < 0:
            out[key] = "-"
            continue
        if c.cls.full not in sf_cache:
            sf = 0
            try:
                klass = struct.unpack("<Q", ctx.read(ctx.module_base + slot, 8))[0]
                if klass:
                    sf = struct.unpack("<Q", ctx.read(klass + STATIC_OFF, 8))[0]
            except Exception:  # noqa: BLE001
                sf = 0
            sf_cache[c.cls.full] = sf
        sf = sf_cache[c.cls.full]
        if not sf:
            out[key] = "(nicht geladen)"
            continue
        ti = model.resolve(c.mem.type)
        try:
            out[key] = fmt_value(ti, ctx.read(sf + c.mem.offset, ti.size))
        except Exception:  # noqa: BLE001
            out[key] = "?"
    return out


ZERO_TEXTS = {"0", "False", "-", "?", "(nicht geladen)"}


# ---------- Direkt in den Speicher schreiben (ohne Code-Cave) ----------
def encode_value(ti, v):
    if ti.kind == "float":
        return struct.pack("<f" if ti.size == 4 else "<d", float(v))
    return (int(v) & ((1 << (8 * ti.size)) - 1)).to_bytes(ti.size, "little")


def decode_value(ti, raw):
    if ti.kind == "float":
        return struct.unpack("<f" if ti.size == 4 else "<d", raw)[0]
    return int.from_bytes(raw, "little", signed=ti.signed)


def write_mem(backend, addr, data):
    """Schreibt Bytes über das ps5-Backend. Welche Methode es gibt, wird ausprobiert."""
    for obj in (backend, getattr(backend, "client", None)):
        if obj is None:
            continue
        for name in ("write", "write_memory", "write_bytes", "write_mem"):
            fn = getattr(obj, name, None)
            if callable(fn):
                fn(addr, bytes(data))
                return
    raise RuntimeError("Das Backend hat keine Schreib-Funktion, die ich kenne (ps5_backend.py)")


def static_addr(model, ctx, cls, field):
    """Adresse eines statischen Feldes: TypeInfo-Slot -> Klasse -> static_fields -> Feld."""
    slot = model.typeinfo.get(cls.full)
    if slot is None:
        raise ValueError("script.json fehlt für diese Klasse")
    if field.offset is None or field.offset < 0:
        raise ValueError("Feld ohne Offset im Dump")
    klass = struct.unpack("<Q", ctx.read(ctx.module_base + slot, 8))[0]
    sf = struct.unpack("<Q", ctx.read(klass + STATIC_OFF, 8))[0] if klass else 0
    if not klass or not sf:
        raise ValueError("Die Klasse ist im Spiel noch nicht geladen - erst im Spiel dorthin gehen "
                         "(z. B. Spielstand laden) und nochmal versuchen")
    return sf + field.offset


def write_static_value(model, ctx, cls, field, ti, mode, value):
    """Wert jetzt setzen. Liefert (alt, neu, ok) - ok = nach dem Schreiben zurückgelesen und stimmt."""
    addr = static_addr(model, ctx, cls, field)
    v = norm_value(ti, value, mode)
    cur = decode_value(ti, ctx.read(addr, ti.size))
    new = {"set": v, "min": max(cur, v), "mul": cur * v, "add": cur + v}[mode]
    if ti.kind == "int":
        bits = ti.size * 8
        lo, hi = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if ti.signed else (0, (1 << bits) - 1)
        new = min(max(int(new), lo), hi)
    data = encode_value(ti, new)
    write_mem(ctx.backend, addr, data)
    return cur, new, ctx.read(addr, ti.size) == data


def load_model(dump_path, log=print):
    classes = D.parse_dump_cs(dump_path, log)
    typeinfo = {}
    script = os.path.join(os.path.dirname(dump_path), "script.json")
    if os.path.isfile(script):
        try:
            typeinfo = D.parse_typeinfo(script)
            log(f"script.json gelesen: {len(typeinfo)} TypeInfo-Zeiger (statische Felder möglich)")
        except Exception as e:  # noqa: BLE001
            log(f"script.json nicht lesbar: {e}")
    else:
        log("script.json nicht gefunden - statische Felder sind nicht möglich (Methoden und Instanzfelder gehen)")
    return Model(classes, typeinfo, log)


if __name__ == "__main__":
    print("cavemaker.py ist die Logik des Tabs UNITY > CAVEMAKER in ReaperPy (kein eigenes Fenster mehr). "
          "Starte ReaperPy -> Werkzeuge -> UNITY -> CAVEMAKER.")
