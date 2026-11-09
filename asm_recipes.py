"""asm_recipes.py - fertige "Presets" statt selbst Assembler tippen (ohne tkinter).

Ein Preset bekommt die Bytes ab der gewaehlten Adresse und erzeugt Patch oder Cave-Code:

    plan = make_plan("set_value", data, addr, "999")
    plan["kind"]         'patch' (Bytes einfach ersetzen) oder 'cave'
    plan["new"]          Patch: Assembler-Text, der an die Stelle geschrieben wird
    plan["cheat"]        Cave: Zeilen, die statt der Originalbefehle laufen (ohne 'jmp OriginReturn')
    plan["body"]         Cave: die Originalbefehle (unveraendert)
    plan["size"]         so viele Original-Bytes werden ersetzt

cave_text(plan) macht daraus den Text fuer das Cave-Feld des Cheat-Editors.
"""
import re
import struct

import asm_explain as AX
import asm_tools as AT

RECIPES = (
    # id, Titel (de, en), Beschreibung (de, en), braucht Wert?, Art
    ("disable",
     ("Befehl abschalten (der Wert aendert sich nicht mehr)", "Switch the instruction off (the value stops changing)"),
     ("Ersetzt den Befehl durch NOPs (Platzhalter, die nichts tun). Gut gegen 'Leben sinkt' oder 'Munition sinkt'.",
      "Replaces the instruction with NOPs (placeholders that do nothing). Good against 'health drops' or 'ammo drops'."),
     False, "patch"),
    ("set_value",
     ("Wert immer auf eine Zahl setzen", "Always set the value to a number"),
     ("Der Befehl laeuft normal, danach wird das Ergebnis mit deiner Zahl ueberschrieben (z. B. Leben immer 999).",
      "The instruction runs as usual, then the result is overwritten with your number (e.g. health always 999)."),
     True, "cave"),
    ("return_now",
     ("Funktion sofort beenden", "End the function right away"),
     ("Springt sofort aus der Funktion zurueck. Nur sinnvoll, wenn die Adresse der ANFANG einer Funktion ist.",
      "Returns from the function immediately. Only useful if the address is the START of a function."),
     False, "patch"),
)
IDS = tuple(r[0] for r in RECIPES)


def recipe(rid):
    for r in RECIPES:
        if r[0] == rid:
            return r
    raise KeyError(rid)


def title(rid, lang="de"):
    return recipe(rid)[1][1 if lang == "en" else 0]


def describe(rid, lang="de"):
    return recipe(rid)[2][1 if lang == "en" else 0]


def needs_value(rid):
    return recipe(rid)[3]


def parse_value(text, float_ok=False):
    """'999', '0x3E7', '-1' -> int;  '9.5' -> float (nur wenn float_ok)."""
    t = (text or "").strip().replace(",", ".")
    if not t:
        raise ValueError("Zahl fehlt")
    try:
        return int(t, 0)
    except ValueError:
        pass
    try:
        f = float(t)
    except ValueError:
        raise ValueError("Keine Zahl")
    if not float_ok:
        raise ValueError("Keine ganze Zahl")
    return f


_SIZE_MOV = {"byte": 1, "word": 2, "dword": 4, "qword": 8}
_REG_SIZE = {}
for _n in ("ax", "bx", "cx", "dx", "si", "di", "bp", "sp"):
    _REG_SIZE["e" + _n] = 4
    _REG_SIZE["r" + _n] = 8
    _REG_SIZE[_n] = 2
for _i in range(8, 16):
    _REG_SIZE[f"r{_i}"] = 8
    _REG_SIZE[f"r{_i}d"] = 4
    _REG_SIZE[f"r{_i}w"] = 2
    _REG_SIZE[f"r{_i}b"] = 1
for _n in ("al", "bl", "cl", "dl", "sil", "dil", "bpl", "spl"):
    _REG_SIZE[_n] = 1


def _first_insn(data, addr):
    lines = AT.disassemble_lines(data, addr, max_insn=1)
    if not lines or lines[0]["mnemonic"] == "db":
        raise ValueError("An dieser Adresse steht kein gueltiger Befehl")
    return lines[0]


def _set_line(body_line, value):
    """Zeile, die nach dem Original-Befehl den Wert ueberschreibt (oder ValueError)."""
    mnem, _s, ops_txt = body_line.partition(" ")
    ops = AX.split_ops(ops_txt)
    if not ops:
        raise ValueError("Dieser Befehl hat kein Ziel, das man setzen koennte")
    dst = ops[0]
    floaty = mnem.lower() in ("movss", "addss", "subss", "mulss", "divss", "cvtsi2ss", "maxss", "minss", "sqrtss")
    dbl = mnem.lower() in ("movsd", "addsd", "subsd", "mulsd", "divsd", "cvtsi2sd")
    k = AX.kind(dst)
    if k == "mem":
        m = re.match(r"^(?:(byte|word|dword|qword)\s+ptr\s+)?(.*)$", dst, re.I)
        size = _SIZE_MOV.get((m.group(1) or "").lower(), 0)
        if floaty:
            size = 4
            val = struct.unpack("<I", struct.pack("<f", float(parse_value(str(value), True))))[0]
        elif dbl:
            raise ValueError("Doppelt genaue Kommazahlen (movsd) kann das Preset noch nicht setzen - "
                             "bitte 'Befehl abschalten' benutzen")
        else:
            if not size:
                raise ValueError("Die Groesse des Speicherplatzes ist unklar (kein 'dword ptr' o. ae.)")
            val = int(parse_value(str(value)))
        if size == 8 and not -0x80000000 <= val <= 0x7FFFFFFF:
            raise ValueError("Der Wert ist fuer eine 8-Byte-Speicherstelle zu gross (max. 2147483647)")
        val &= (1 << (8 * size)) - 1
        if size == 8:
            val = val if val < 0x80000000 else val - (1 << 64)
        name = {1: "byte", 2: "word", 4: "dword", 8: "qword"}[size]
        return f"mov {name} ptr {m.group(2)}, {val:#x}" if val >= 0 else f"mov {name} ptr {m.group(2)}, {val}"
    if k == "reg":
        r = dst.lower()
        if r.startswith(("xmm", "ymm")):
            raise ValueError("Das Ziel ist ein Kommazahl-Register - bitte 'Befehl abschalten' benutzen")
        size = _REG_SIZE.get(r)
        if not size:
            raise ValueError(f"Register {dst} kenne ich nicht")
        val = int(parse_value(str(value)))
        return f"mov {dst}, {val}"
    raise ValueError("Dieser Befehl hat kein Ziel, das man setzen koennte")


def make_plan(rid, data, addr, value="", guarded=False):
    """Preset auf den Befehl bei `addr` anwenden (`data` = mindestens 16 Byte ab addr).
    guarded=True: immer als Cave bauen (damit eine Pruefung 'nur Spieler' davor passt)."""
    recipe(rid)
    ins = _first_insn(data, addr)
    plan = {"id": rid, "addr": addr, "insn": f"{ins['mnemonic']} {ins['op_str']}".strip(), "warnings": []}
    if rid == "disable" and not guarded:
        plan.update(kind="patch", size=ins["size"], new="\n".join(["nop"] * ins["size"]))
        return plan
    if rid == "return_now" and not guarded:
        plan.update(kind="patch", size=max(ins["size"], 1), new="ret")
        if ins["size"] > 1:
            plan["new"] = "ret\n" + "\n".join(["nop"] * (ins["size"] - 1))
        plan["warnings"].append("Nur am ANFANG einer Funktion sinnvoll")
        return plan
    # set_value -> Cave
    info = AT.build_cave_hook(data, addr, 8)
    body = [ln.strip() for ln in info["cave"].splitlines() if ln.strip() and not ln.strip().startswith(";")]
    body = [ln for ln in body if ln != "jmp OriginReturn"]
    if rid == "disable":
        cheat = body[1:]                                   # der erste Befehl (der Schreibzugriff) entfaellt
    elif rid == "return_now":
        cheat = ["ret"]
        plan["warnings"].append("Nur am ANFANG einer Funktion sinnvoll")
    else:
        cheat = [body[0], _set_line(body[0], value)] + body[1:]
    plan.update(kind="cave", size=info["size"], default=info["default"], body=body,
                cheat=cheat, warnings=plan["warnings"] + list(info["warnings"]), ret=info["size"])
    return plan


def cave_text(plan, guard=None):
    """Text fuer das Cave-Feld.  guard = Ergebnis von whois.guard_blocks() (nur Spieler / nur Gegner)."""
    if plan["kind"] != "cave":
        raise ValueError("Dieses Preset braucht keine Cave")
    if guard is None:
        return ("; Preset: " + plan["id"] + "\n" + "\n".join(plan["cheat"]) + "\njmp OriginReturn\n")
    head, normal_label = guard["head"], guard["normal_label"]
    out = ["; Preset: " + plan["id"] + " - nur wenn die Pruefung zutrifft"]
    out += head
    out += guard["on_match"] + plan["cheat"] + ["jmp OriginReturn", f"{normal_label}:"]
    out += guard["on_normal"] + plan["body"] + ["jmp OriginReturn"]
    return "\n".join(out) + "\n"

