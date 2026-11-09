"""assist.py - Logik fuer den ASSISTENT-Tab (ohne tkinter): vom gesuchten Wert bis zum schreibenden Befehl.

    value_plan("100")            -> Suchart fuer den Scanner (Zahl -> Int32 / Float ...)
    advice(count, lang)          -> (art, Satz): wie geht es weiter, je nach Trefferzahl
    find_writer(rip, before, regs, watch, size, disasm)
                                 -> der Befehl, der den beobachteten Speicherplatz geschrieben hat
    Writers                      -> sammelt Treffer zu einer Liste "welcher Befehl wie oft"

Ein Hardware-Watchpoint meldet erst NACH der schreibenden Anweisung; deren Adresse ist nicht direkt bekannt.  find_writer
probiert alle Startpunkte vor dem gemeldeten RIP, behaelt die, deren Befehlskette genau auf RIP endet, und waehlt dann
den Befehl, dessen Speicheroperand (mit den Registern des Treffers) wirklich auf den beobachteten Platz zeigt.
"""
import re

import asm_explain as AX

STEP_COUNT_GOOD = 30            # so wenige Treffer: Liste anzeigen, direkt weiter
STEP_COUNT_TOO_MANY = 5000      # darueber: deutlich auffordern, den Wert zu aendern


def value_plan(text, unknown=False):
    """Eingegebene Zahl -> {'vname','ctype','text'} fuer ScanTab/Scanner.  unknown=True: Zahl unbekannt (Anzeige ist nur eine Leiste)."""
    if unknown:
        return {"vname": "Int32", "ctype": "Unbekannter Startwert", "text": ""}
    t = (text or "").strip().replace(",", ".")
    if not t:
        raise ValueError("Zahl fehlt")
    try:
        v = int(t, 0)
    except ValueError:
        try:
            float(t)
        except ValueError:
            raise ValueError("Keine Zahl") from None
        return {"vname": "Float", "ctype": "Ungefähr (Float)", "text": t}
    if -0x80000000 <= v <= 0x7FFFFFFF:
        vname = "Int32"
    elif 0 <= v <= 0xFFFFFFFF:
        vname = "UInt32"
    else:
        vname = "Int64"
    return {"vname": vname, "ctype": "Genau", "text": str(v)}


def advice(count, lang="de", first=False):
    """(art, Satz).  art: none | many | some | good."""
    de = lang != "en"
    if count == 0:
        return ("none",
                "Nichts gefunden. Wurde die Zahl richtig abgelesen? Mit NEU STARTEN anfangen, oder die Zahl als Kommazahl (mit Punkt) versuchen."
                if de else "Nothing found. Was the number read correctly? Start again with RESTART, or try the number as a decimal (with a dot).")
    if count > STEP_COUNT_TOO_MANY:
        return ("many",
                f"{count} Treffer - noch viel zu viele. Aendere den Wert im Spiel (zum Beispiel Leben verlieren) und grenze ein."
                if de else f"{count} hits - far too many. Change the value in the game (for example lose health) and narrow down.")
    if count > STEP_COUNT_GOOD:
        return ("some",
                f"{count} Treffer. Aendere den Wert im Spiel noch einmal und grenze erneut ein."
                if de else f"{count} hits. Change the value in the game once more and narrow down again.")
    if first:
        return ("good",
                f"{count} Treffer - sehr wenige. Du kannst gleich weiter, oder noch einmal eingrenzen, um sicher zu sein."
                if de else f"{count} hits - very few. You can continue now, or narrow down once more to be sure.")
    return ("good",
            f"{count} Treffer - das reicht. Markiere die Zeile, deren Wert im Spiel mitgeht, und gehe zu Schritt 3."
            if de else f"{count} hits - that is enough. Select the row whose value follows the game, then go to step 3.")


def watch_size(vname):
    """Breite des Watchpoints in Byte (1, 2, 4 oder 8)."""
    return {"UInt8": 1, "Int8": 1, "UInt16": 2, "Int16": 2, "UInt64": 8, "Int64": 8, "Double": 8}.get(vname, 4)


# ---------------------------------------------------------------- Adresse eines Speicheroperanden
_R64 = ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp")
_REGS = {}
for _r in _R64:
    _REGS[_r] = (_r, 0xFFFFFFFFFFFFFFFF)
    _REGS["e" + _r[1:]] = (_r, 0xFFFFFFFF)
for _i in range(8, 16):
    _REGS[f"r{_i}"] = (f"r{_i}", 0xFFFFFFFFFFFFFFFF)
    _REGS[f"r{_i}d"] = (f"r{_i}", 0xFFFFFFFF)


def mem_operand(op_str):
    """Der erste Speicheroperand '[...]' eines Befehls als (Text, ist_erster_Operand) oder None."""
    m = re.search(r"\[([^\]]*)\]", op_str or "")
    if not m:
        return None
    before = op_str[:m.start()]
    return m.group(1), "," not in before


def effective_address(inner, regs, next_ip):
    """'rbx + rax*4 + 0x10' -> Adresse (oder None, wenn nicht berechenbar)."""
    s = inner.replace(" ", "").lower()
    if ":" in s:
        return None
    total = 0
    for term in re.findall(r"[+-]?[^+-]+", s):
        sign = -1 if term.startswith("-") else 1
        t = term.lstrip("+-")
        if "*" in t:
            reg, _x, scale = t.partition("*")
            if reg not in _REGS or not scale.isdigit():
                return None
            name, mask = _REGS[reg]
            if name not in regs:
                return None
            total += sign * (regs[name] & mask) * int(scale)
        elif t == "rip":
            total += sign * next_ip
        elif t in _REGS:
            name, mask = _REGS[t]
            if name not in regs:
                return None
            total += sign * (regs[name] & mask)
        else:
            try:
                total += sign * int(t, 0)
            except ValueError:
                return None
    return total & 0xFFFFFFFFFFFFFFFF


# ---------------------------------------------------------------- schreibender Befehl
_WRITES_FIRST = ("mov", "add", "sub", "and", "or", "xor", "inc", "dec", "neg", "not", "adc", "sbb", "shl", "shr", "sar",
                 "sal", "rol", "ror", "xchg", "xadd", "cmpxchg", "bts", "btr", "btc", "set", "cmov", "movs", "stos",
                 "vmov", "movd", "movq", "movaps", "movups", "movdqa", "movdqu", "movss", "movsd", "movapd", "movupd",
                 "pop")


def _writes_memory(line):
    m = (line["mnemonic"] or "").lower()
    if m.startswith(("lock ", "rep")):
        m = m.split()[-1]
    if m in ("cmp", "test", "lea", "nop", "push", "call", "jmp"):
        return False
    mo = mem_operand(line["op_str"])
    return bool(mo and mo[1] and m.startswith(_WRITES_FIRST))


def _chain(before, rip, k, disasm):
    """Befehlskette, die bei rip-k beginnt und genau auf rip endet (sonst None)."""
    data = bytes(before[-k:])
    try:
        lines = disasm(data, rip - k)
    except Exception:  # noqa: BLE001
        return None
    pos = rip - k
    for ln in lines:
        if ln["mnemonic"] == "db" or ln["addr"] != pos:
            return None
        pos += ln["size"]
    return lines if pos == rip and lines else None


def find_writer(rip, before, regs, watch, size, disasm):
    """Der Befehl, der direkt vor `rip` stand und den Platz `watch` (Breite `size`) geschrieben hat.

    before = die (mindestens 16) Bytes unmittelbar vor rip; regs = Register des Treffers; disasm(data, addr) -> Zeilen.
    -> {'addr','size','mnemonic','op_str','how': 'address'|'writes'|'guess'} oder None."""
    cands = {}
    for k in range(1, min(15, len(before)) + 1):
        lines = _chain(before, rip, k, disasm)
        if lines:
            last = lines[-1]
            cands.setdefault(last["addr"], {"line": last, "support": 0})["support"] += 1
    if not cands:
        return None
    exact = []
    for c in cands.values():
        ln = c["line"]
        mo = mem_operand(ln["op_str"])
        if not mo:
            continue
        ea = effective_address(mo[0], regs, rip)
        if ea is not None and watch - 16 < ea < watch + size:
            exact.append(c)
    how, pool = "address", exact
    if not pool:
        how, pool = "writes", [c for c in cands.values() if _writes_memory(c["line"])]
    if not pool:
        how, pool = "guess", list(cands.values())
    best = sorted(pool, key=lambda c: (-c["support"], c["line"]["size"]))[0]["line"]
    return {"addr": best["addr"], "size": best["size"], "mnemonic": best["mnemonic"], "op_str": best["op_str"], "how": how}


class Writers:
    """Sammelt, welche Befehle den beobachteten Platz geschrieben haben (Adresse -> Anzahl)."""

    def __init__(self):
        self.items = {}
        self.unknown = 0

    def add(self, writer, rip=None):
        if writer is None:
            self.unknown += 1
            return None
        e = self.items.setdefault(writer["addr"], {"writer": writer, "count": 0})
        e["count"] += 1
        return e

    def rows(self, lang="de"):
        out = []
        for addr, e in sorted(self.items.items(), key=lambda kv: -kv[1]["count"]):
            w = e["writer"]
            out.append({"addr": addr, "count": e["count"], "how": w["how"],
                        "insn": f"{w['mnemonic']} {w['op_str']}".strip(),
                        "text": AX.explain(w["mnemonic"], w["op_str"], lang)})
        return out
