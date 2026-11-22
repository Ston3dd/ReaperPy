"""hit_targets.py - Ziele eines Debugger-Treffers: gleicher Befehl, verschiedene Objekte (ohne Oberflaeche, testbar).

Problem: Ein Befehl wie  `movss dword ptr [rbx + 0x278], xmm0`  schreibt die HP von JEDEM Objekt, das ihn ausfuehrt -
Spieler, Gegner, Widgets.  Ein Watchpoint auf eine Adresse zeigt nur ein Objekt, ein Breakpoint auf den Befehl alle.
Hier wird aus Befehl + Registern die Adresse errechnet, die der Befehl anfasst (das ZIEL).  Jedes Ziel bekommt einen
Buchstaben (A, B, C ...).  Wer seinen eigenen Wert kennt (z. B. die HP, die im Spiel steht), findet so das eigene Objekt.

target_of(insn, regs) -> {ea, width, base, writer, value} | None
    insn   Zeile des Disassemblers (addr, size, mnemonic, op_str)
    regs   Register des Treffers {"rax": ..., "rip": ...}
    ea     Adresse des Speicheroperanden, width 1/2/4/8 Byte, base = Wert des Basisregisters (= das Objekt) oder None
    value  bleibt None - den Wert liest build_context nach (hier wird kein Speicher gelesen)
TargetBook   sammelt die Ziele (eine Gruppe pro Adresse)
format_value / delta_text   Anzeige der rohen Werte (ganze Zahl, bei 4 Byte zusaetzlich als Kommazahl, wenn sie so aussieht)
"""
import math
import re
import struct

# ---------------------------------------------------------------- Register

_R64 = ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp")
_ALIASES = {}
for _full, _d, _w, _b in (("rax", "eax", "ax", "al"), ("rbx", "ebx", "bx", "bl"), ("rcx", "ecx", "cx", "cl"),
                          ("rdx", "edx", "dx", "dl"), ("rsi", "esi", "si", "sil"), ("rdi", "edi", "di", "dil"),
                          ("rbp", "ebp", "bp", "bpl"), ("rsp", "esp", "sp", "spl")):
    _ALIASES[_full] = (_full, 8)
    _ALIASES[_d] = (_full, 4)
    _ALIASES[_w] = (_full, 2)
    _ALIASES[_b] = (_full, 1)
for _n in range(8, 16):
    _ALIASES[f"r{_n}"] = (f"r{_n}", 8)
    _ALIASES[f"r{_n}d"] = (f"r{_n}", 4)
    _ALIASES[f"r{_n}w"] = (f"r{_n}", 2)
    _ALIASES[f"r{_n}b"] = (f"r{_n}", 1)
_ALIASES["rip"] = ("rip", 8)

_MASK64 = 0xFFFFFFFFFFFFFFFF
_MEM = re.compile(r"(?:(byte|word|dword|qword|xmmword|ymmword|zmmword|tbyte|fword)\s+ptr\s+)?"
                  r"(?:([a-z]{2}):)?\[([^\]]*)\]", re.I)
_SIZES = {"byte": 1, "word": 2, "dword": 4, "qword": 8, "xmmword": 16, "ymmword": 32, "zmmword": 64, "tbyte": 10,
          "fword": 6}
_NO_ACCESS = ("lea", "nop", "prefetch", "prefetcht0", "prefetcht1", "prefetcht2", "prefetchnta", "prefetchw", "invlpg")
_SCALAR_FLOAT = ("movss", "addss", "subss", "mulss", "divss", "cvtsi2ss", "movd")
_SCALAR_DOUBLE = ("movsd", "addsd", "subsd", "mulsd", "divsd", "cvtsi2sd", "movq")


def _reg(regs, name):
    """(Wert, Name des 64-Bit-Registers) oder None."""
    name = name.lower().strip()
    if name not in _ALIASES:
        return None
    full, size = _ALIASES[name]
    if full not in regs:
        return None
    val = int(regs[full]) & _MASK64
    return (val & ((1 << (size * 8)) - 1)), full


def _split_operands(op_str):
    """'dword ptr [rax + 4], ecx' -> ['dword ptr [rax + 4]', 'ecx'] (Komma innerhalb von [] zaehlt nicht)."""
    out, depth, cur = [], 0, ""
    for ch in op_str:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _guess_width(mnemonic, ptr_size, other_operands):
    """Breite des Zugriffs in Byte (1/2/4/8): aus 'dword ptr', sonst aus dem Register-Operanden, sonst aus dem Befehl."""
    if ptr_size in (1, 2, 4):
        return ptr_size
    if ptr_size > 8:                      # xmmword & Co: ein Watchpoint kann hoechstens 8 Byte
        return 8
    for op in other_operands:
        r = op.strip().lower()
        if r in _ALIASES:
            return _ALIASES[r][1]
        if r.startswith(("xmm", "ymm", "zmm")):
            m = mnemonic.lower()
            return 8 if m in _SCALAR_DOUBLE or m.endswith(("sd", "pd")) else 4
    if ptr_size == 8:
        return 8
    return 8 if mnemonic.lower() in _SCALAR_DOUBLE else 4


def _parse_address(expr, regs, insn):
    """'rbx + rcx*4 + 0x10' -> (ea, Wert des Basisregisters oder None); None, wenn nicht berechenbar."""
    expr = expr.replace(" ", "").lower()
    if not expr:
        return None
    # in Summanden zerlegen (Vorzeichen bleiben dran)
    terms = re.findall(r"[+-]?[^+-]+", expr)
    total, base_val, first_reg = 0, None, True
    for term in terms:
        sign = -1 if term.startswith("-") else 1
        body = term.lstrip("+-")
        if "*" in body:
            reg_name, scale = body.split("*", 1)
            r = _reg(regs, reg_name)
            if r is None:
                return None
            try:
                total += sign * r[0] * int(scale, 0)
            except ValueError:
                return None
        elif re.fullmatch(r"0x[0-9a-f]+|\d+", body):
            total += sign * int(body, 0)
        else:
            r = _reg(regs, body)
            if r is None:
                return None
            if r[1] == "rip":
                if "addr" not in insn or "size" not in insn:
                    return None
                total += sign * (insn["addr"] + insn["size"])         # rip-relativ: ab dem NAECHSTEN Befehl
            else:
                total += sign * r[0]
                if first_reg and sign > 0:
                    base_val = r[0]                                   # erstes Register = Basis (das Objekt)
                first_reg = False
    return total & _MASK64, base_val


def target_of(insn, regs):
    """Welche Speicheradresse fasst der Befehl an?  None, wenn er keinen Speicheroperanden hat oder dieser nicht berechenbar ist."""
    if not insn or not regs:
        return None
    mnem = str(insn.get("mnemonic", "")).lower()
    if not mnem or mnem == "db" or mnem in _NO_ACCESS or mnem.startswith(("j", "call", "ret", "push", "pop")):
        return None
    ops = _split_operands(str(insn.get("op_str", "")))
    for n, op in enumerate(ops):
        m = _MEM.search(op)
        if not m or m.group(2):                                       # kein [..] oder Segment (fs:/gs:) -> weiter
            continue
        parsed = _parse_address(m.group(3), regs, insn)
        if parsed is None:
            return None
        ea, base = parsed
        ptr = _SIZES.get((m.group(1) or "").lower(), 0)
        others = [o for i, o in enumerate(ops) if i != n]
        width = _guess_width(mnem, ptr, others)
        if width not in (1, 2, 4, 8):
            width = 4
        text = f"{insn.get('addr', 0):#x}  {mnem} {insn.get('op_str', '')}".strip()
        return {"ea": ea, "width": width, "base": base, "writer": text, "value": None}
    return None


# ---------------------------------------------------------------- Werte

def _as_float(value, width):
    """Die Kommazahl, die in den rohen Bits stecken koennte - None, wenn sie nicht nach einem Spielwert aussieht."""
    try:
        if width == 4:
            f = struct.unpack("<f", struct.pack("<I", value & 0xFFFFFFFF))[0]
        elif width == 8:
            f = struct.unpack("<d", struct.pack("<Q", value & _MASK64))[0]
        else:
            return None
    except (struct.error, OverflowError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    if f != 0 and not (1e-3 <= abs(f) <= 1e9):
        return None
    return f


def _signed(value, width):
    bits = width * 8
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def _fnum(f):
    return f"{f:.6g}"


def format_value(value, width):
    """Roher Wert als Text: ganze Zahl, bei 4/8 Byte dahinter die Kommazahl, wenn sie wie ein Wert aussieht (HP 74.6)."""
    if value is None:
        return "-"
    width = width if width in (1, 2, 4, 8) else 4
    value = int(value) & ((1 << (width * 8)) - 1)
    ints = str(_signed(value, width))
    f = _as_float(value, width)
    if f is not None and value > 0xFFFF:                              # kleine ganze Zahlen sind selten Kommazahlen
        return f"{ints}  (= {_fnum(f)})"
    return ints


def delta_text(prev, value, width):
    """Aenderung gegenueber dem vorigen Wert: '+5', '-10', '+0.5'; leer ohne Vorgaenger."""
    if prev is None or value is None:
        return ""
    width = width if width in (1, 2, 4, 8) else 4
    mask = (1 << (width * 8)) - 1
    prev, value = int(prev) & mask, int(value) & mask
    if prev == value:
        return "0"
    fp, fv = _as_float(prev, width), _as_float(value, width)
    if fp is not None and fv is not None and prev > 0xFFFF and value > 0xFFFF:
        d = fv - fp
        return f"{d:+.6g}"
    return f"{_signed(value, width) - _signed(prev, width):+d}"


def _parse_number(text):
    """'75' / '0x4B' / '74.6' -> (ganze Zahl oder None, Kommazahl oder None)."""
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None, None
    try:
        return int(text, 0), float(int(text, 0))
    except ValueError:
        pass
    try:
        return None, float(text)
    except ValueError:
        return None, None


# ---------------------------------------------------------------- Sammlung

def _label(n):
    """0 -> A, 25 -> Z, 26 -> AA ..."""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class TargetBook:
    """Eine Gruppe pro Zieladresse: wie oft getroffen, wie oft der Wert sich geaendert hat, letzter und vorletzter Wert."""

    def __init__(self):
        self.groups = {}          # ea -> Gruppe (Reihenfolge = Reihenfolge des ersten Treffers)
        self.skipped = 0          # vom Filter uebersprungene Treffer
        self._n = 0

    def reset(self):
        self.groups.clear()
        self.skipped = 0
        self._n = 0

    def add(self, t, value, insn=None, when=None):
        """Treffer eintragen -> (Gruppe, neu?, Wert hat sich geaendert?)"""
        ea = t["ea"]
        g = self.groups.get(ea)
        is_new = g is None
        if is_new:
            g = {"label": _label(self._n), "ea": ea, "width": t.get("width", 4), "base_val": t.get("base"),
                 "value": None, "prev": None, "hits": 0, "changes": 0, "me": False, "insn": None, "when": None}
            self._n += 1
            self.groups[ea] = g
        changed = False
        if value is not None:
            if g["value"] is not None and value != g["value"]:
                changed = True
                g["changes"] += 1
            if g["value"] is None or value != g["value"]:
                g["prev"] = g["value"]
            g["value"] = value
        g["hits"] += 1
        if insn is not None:
            g["insn"] = insn
        if when is not None:
            g["when"] = when
        return g, is_new, changed

    def rows(self):
        return list(self.groups.values())

    def toggle_me(self, ea):
        """Dieses Ziel als 'ICH' markieren (immer nur eins); nochmal -> Markierung weg."""
        g = self.groups.get(ea)
        if g is None:
            return
        was = g["me"]
        for other in self.groups.values():
            other["me"] = False
        g["me"] = not was

    def find_value(self, text):
        """Ziele, deren aktueller Wert dem Text entspricht (ganze Zahl exakt, oder Kommazahl mit kleiner Toleranz,
        weil Spiele gerundet anzeigen: 75 im Spiel kann 74.6 im Speicher sein)."""
        i, f = _parse_number(text)
        if i is None and f is None:
            return []
        out = []
        for g in self.groups.values():
            v, w = g["value"], g["width"]
            if v is None:
                continue
            raw = int(v) & ((1 << (w * 8)) - 1)
            if i is not None and (raw == i & ((1 << (w * 8)) - 1) or _signed(raw, w) == i):
                out.append(g)
                continue
            fv = _as_float(raw, w)
            if fv is not None and f is not None:
                tol = 0.5 if i is not None else max(0.05, abs(f) * 0.001)
                if abs(fv - f) <= tol:
                    out.append(g)
        return out
