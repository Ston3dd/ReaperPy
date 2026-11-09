"""asm_explain.py - Assembler-Zeilen in Klartext erklaeren (fuer Einsteiger, ohne tkinter).

    explain("sub", "dword ptr [rbx + 0x10], 1")  ->  "Zieht 1 von dem 4-Byte-Wert in rbx+0x10 ab. ..."

Deutsch und Englisch stehen hier direkt im Modul (kein Eintrag in tools_i18n_en.py noetig); die Sprache kommt aus
`tools_i18n.lang()` oder dem Parameter `lang`.  Unbekannte Befehle liefern "".
"""
import re

_SIZES = {"byte": (1, "1-Byte", "1-byte"), "word": (2, "2-Byte", "2-byte"), "dword": (4, "4-Byte", "4-byte"),
          "qword": (8, "8-Byte", "8-byte"), "xmmword": (16, "16-Byte", "16-byte"), "tbyte": (10, "10-Byte", "10-byte")}
_MEM = re.compile(r"^(?:(byte|word|dword|qword|xmmword|tbyte)\s+ptr\s+)?(?:[a-z]s:)?\[(.*)\]$", re.I)
_REG = re.compile(r"^(?:[re]?[abcd]x|[abcd][lh]|[re]?[sd]il?|[re]?[sb]pl?|[re]?[sb]p|r(?:8|9|1[0-5])[dwb]?|[xy]mm\d+|[re]?ip)$",
                  re.I)
_NUM = re.compile(r"^-?(?:0x[0-9a-f]+|\d+)$", re.I)

JCC = {  # Bedingung (de, en)
    "je": ("beide Werte gleich waren", "both values were equal"), "jz": ("das Ergebnis 0 war", "the result was 0"),
    "jne": ("die Werte verschieden waren", "the values were different"), "jnz": ("das Ergebnis nicht 0 war", "the result was not 0"),
    "jg": ("der erste Wert groesser war (mit Vorzeichen)", "the first value was greater (signed)"),
    "jge": ("der erste Wert groesser oder gleich war (mit Vorzeichen)", "the first value was greater or equal (signed)"),
    "jl": ("der erste Wert kleiner war (mit Vorzeichen)", "the first value was smaller (signed)"),
    "jle": ("der erste Wert kleiner oder gleich war (mit Vorzeichen)", "the first value was smaller or equal (signed)"),
    "ja": ("der erste Wert groesser war (ohne Vorzeichen)", "the first value was greater (unsigned)"),
    "jae": ("der erste Wert groesser oder gleich war (ohne Vorzeichen)", "the first value was greater or equal (unsigned)"),
    "jb": ("der erste Wert kleiner war (ohne Vorzeichen)", "the first value was smaller (unsigned)"),
    "jbe": ("der erste Wert kleiner oder gleich war (ohne Vorzeichen)", "the first value was smaller or equal (unsigned)"),
    "js": ("das Ergebnis negativ war", "the result was negative"), "jns": ("das Ergebnis nicht negativ war", "the result was not negative"),
    "jp": ("das Paritaetsbit gesetzt war (Kommazahl-Vergleich unordentlich)", "the parity flag was set (unordered float compare)"),
    "jnp": ("das Paritaetsbit nicht gesetzt war", "the parity flag was not set"),
    "jo": ("ein Ueberlauf vorlag", "there was an overflow"), "jno": ("kein Ueberlauf vorlag", "there was no overflow"),
}
JCC["jnae"], JCC["jc"], JCC["jnb"], JCC["jnc"] = JCC["jb"], JCC["jb"], JCC["jae"], JCC["jae"]
JCC["jna"], JCC["jnbe"], JCC["jng"], JCC["jnge"] = JCC["jbe"], JCC["ja"], JCC["jle"], JCC["jl"]
JCC["jnl"], JCC["jnle"], JCC["jpe"], JCC["jpo"] = JCC["jge"], JCC["jg"], JCC["jp"], JCC["jnp"]


def split_ops(op_str):
    """'dword ptr [rbx + 0x10], 1' -> ['dword ptr [rbx + 0x10]', '1'] (Komma in [] zaehlt nicht)."""
    out, cur, depth = [], "", 0
    for ch in op_str or "":
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


def kind(op):
    """'reg' | 'mem' | 'imm' | 'other'"""
    o = (op or "").strip()
    if _REG.match(o):
        return "reg"
    if _MEM.match(o):
        return "mem"
    if _NUM.match(o):
        return "imm"
    return "other"


def _mem_inner(op):
    m = _MEM.match(op.strip())
    return re.sub(r"\s+", "", m.group(2)) if m else op


def _mem_size(op):
    m = _MEM.match(op.strip())
    return (m.group(1) or "").lower() if m else ""


def describe(op, lang="de"):
    """Einen Operanden in Worten."""
    de = lang != "en"
    k = kind(op)
    if k == "reg":
        return ("Register " if de else "register ") + op.strip()
    if k == "imm":
        return op.strip()
    if k == "mem":
        inner = _mem_inner(op)
        size = _mem_size(op)
        sz = ""
        if size in _SIZES:
            sz = " (" + (_SIZES[size][1] if de else _SIZES[size][2]) + ")"
        if inner.startswith("rip"):
            return ("Programm-Speicherstelle " if de else "fixed program memory location ") + f"[{inner}]" + sz
        return ("Speicherstelle " if de else "memory location ") + f"[{inner}]" + sz
    return op.strip()


def _target(op, lang):
    o = op.strip()
    if kind(o) == "mem":
        return describe(o, lang)
    if kind(o) == "reg":
        return ("die Adresse in " if lang != "en" else "the address in ") + o
    return o


def _hint_write(dst, lang, floaty=False):
    """Zusatz, wenn in den Speicher geschrieben wird."""
    if kind(dst) != "mem":
        return ""
    if lang == "en":
        return " This writes to game memory - typical for health, ammo or money." + (" (floating point)" if floaty else "")
    return " Das schreibt in den Spielspeicher - typisch fuer Leben, Munition oder Geld." + (" (Kommazahl)" if floaty else "")


def _simple(de, en, hint=False, floaty=False):
    return (de, en, hint, floaty)


# Vorlagen: {a} = erster Operand, {b} = zweiter Operand (beschrieben), {A}/{B} = roh
_T = {
    "mov": _simple("Kopiert {b} nach {a}.", "Copies {b} to {a}.", True),
    "movabs": _simple("Kopiert die grosse Zahl {b} nach {a}.", "Copies the large number {b} to {a}.", True),
    "movzx": _simple("Kopiert {b} nach {a} und fuellt vorne mit Nullen auf.", "Copies {b} to {a}, padded with zeros.", False),
    "movsx": _simple("Kopiert {b} nach {a} und behaelt das Vorzeichen.", "Copies {b} to {a}, keeping the sign.", False),
    "movsxd": _simple("Kopiert {b} nach {a} und behaelt das Vorzeichen.", "Copies {b} to {a}, keeping the sign.", False),
    "movss": _simple("Kopiert die Kommazahl {b} nach {a}.", "Copies the decimal number {b} to {a}.", True, True),
    "movsd": _simple("Kopiert die (doppelt genaue) Kommazahl {b} nach {a}.", "Copies the double-precision number {b} to {a}.",
                     True, True),
    "movaps": _simple("Kopiert 16 Byte ({b}) nach {a}.", "Copies 16 bytes ({b}) to {a}.", True),
    "movups": _simple("Kopiert 16 Byte ({b}) nach {a}.", "Copies 16 bytes ({b}) to {a}.", True),
    "movdqa": _simple("Kopiert 16 Byte ({b}) nach {a}.", "Copies 16 bytes ({b}) to {a}.", True),
    "movdqu": _simple("Kopiert 16 Byte ({b}) nach {a}.", "Copies 16 bytes ({b}) to {a}.", True),
    "movq": _simple("Kopiert 8 Byte ({b}) nach {a}.", "Copies 8 bytes ({b}) to {a}.", True),
    "movd": _simple("Kopiert 4 Byte ({b}) nach {a}.", "Copies 4 bytes ({b}) to {a}.", True),
    "lea": _simple("Rechnet die Adresse {B} aus und legt sie in {a} ab - es wird nichts aus dem Speicher gelesen.",
                   "Calculates the address {B} and stores it in {a} - nothing is read from memory."),
    "add": _simple("Zaehlt {b} zu {a} dazu.", "Adds {b} to {a}.", True),
    "sub": _simple("Zieht {b} von {a} ab. Bei Leben oder Munition ist das oft der Schaden / Verbrauch.",
                   "Subtracts {b} from {a}. For health or ammo this is often the damage / usage.", True),
    "inc": _simple("Erhoeht {a} um 1.", "Increases {a} by 1.", True),
    "dec": _simple("Verringert {a} um 1.", "Decreases {a} by 1.", True),
    "neg": _simple("Dreht das Vorzeichen von {a} um.", "Flips the sign of {a}."),
    "imul": _simple("Multipliziert (mit Vorzeichen) - Ergebnis nach {a}.", "Multiplies (signed) - the result goes to {a}."),
    "mul": _simple("Multipliziert (ohne Vorzeichen).", "Multiplies (unsigned)."),
    "idiv": _simple("Teilt mit Vorzeichen (rax durch {a}).", "Divides signed (rax by {a})."),
    "div": _simple("Teilt ohne Vorzeichen (rax durch {a}).", "Divides unsigned (rax by {a})."),
    "and": _simple("Behaelt in {a} nur die Bits, die auch in {b} gesetzt sind.", "Keeps only the bits in {a} that are also set in {b}.", True),
    "or": _simple("Setzt in {a} zusaetzlich die Bits aus {b}.", "Also sets the bits from {b} in {a}.", True),
    "xor": _simple("Kippt in {a} die Bits, die in {b} gesetzt sind.", "Flips the bits in {a} that are set in {b}.", True),
    "not": _simple("Kippt alle Bits in {a}.", "Flips all bits in {a}."),
    "shl": _simple("Schiebt {a} um {b} Bit nach links (mal 2 je Bit).", "Shifts {a} left by {b} bits (times 2 per bit)."),
    "sal": _simple("Schiebt {a} um {b} Bit nach links (mal 2 je Bit).", "Shifts {a} left by {b} bits (times 2 per bit)."),
    "shr": _simple("Schiebt {a} um {b} Bit nach rechts (durch 2 je Bit).", "Shifts {a} right by {b} bits (divided by 2 per bit)."),
    "sar": _simple("Schiebt {a} um {b} Bit nach rechts, mit Vorzeichen.", "Shifts {a} right by {b} bits, keeping the sign."),
    "cmp": _simple("Vergleicht {a} mit {b}. Das Ergebnis wertet der naechste Sprung (je/jne/jg ...) aus.",
                   "Compares {a} with {b}. The next jump (je/jne/jg ...) uses the result."),
    "test": _simple("Prueft {a} gegen {b} (z. B. ob ein Wert 0 ist). Das Ergebnis wertet der naechste Sprung aus.",
                    "Tests {a} against {b} (e.g. whether a value is 0). The next jump uses the result."),
    "push": _simple("Legt {a} auf den Stapel (Zwischenspeicher).", "Puts {a} on the stack (temporary storage)."),
    "pop": _simple("Holt den obersten Wert vom Stapel nach {a}.", "Takes the top value from the stack into {a}."),
    "pushfq": _simple("Merkt sich die Vergleichs-Ergebnisse (Flags) auf dem Stapel.", "Saves the compare results (flags) on the stack."),
    "popfq": _simple("Holt die gemerkten Vergleichs-Ergebnisse (Flags) vom Stapel zurueck.", "Restores the saved flags from the stack."),
    "xchg": _simple("Tauscht {a} und {b}.", "Swaps {a} and {b}."),
    "xadd": _simple("Tauscht {a} und {b} und zaehlt sie zusammen (meist mit 'lock' als Zaehler).",
                    "Swaps {a} and {b} and adds them (usually with 'lock' as a counter)."),
    "cmpxchg": _simple("Ersetzt {a} durch {b}, aber nur wenn {a} den erwarteten Wert hat (Sperre / Zaehler).",
                       "Replaces {a} with {b}, but only if {a} holds the expected value (lock / counter)."),
    "nop": _simple("Tut nichts (Platzhalter).", "Does nothing (placeholder)."),
    "ret": _simple("Kehrt aus der Funktion zurueck zu der Stelle, die sie aufgerufen hat.",
                   "Returns from the function to where it was called."),
    "leave": _simple("Raeumt den Stapel der Funktion auf (vor dem Zurueckkehren).", "Cleans up the function's stack (before returning)."),
    "int3": _simple("Haltepunkt - haelt das Programm an (Debugger).", "Breakpoint - stops the program (debugger)."),
    "syscall": _simple("Ruft das Betriebssystem auf.", "Calls the operating system."),
    "cdq": _simple("Bereitet eine Division vor (erweitert eax auf edx:eax).", "Prepares a division (extends eax to edx:eax)."),
    "cqo": _simple("Bereitet eine Division vor (erweitert rax auf rdx:rax).", "Prepares a division (extends rax to rdx:rax)."),
    "cdqe": _simple("Macht aus dem 4-Byte-Wert in eax einen 8-Byte-Wert in rax.", "Turns the 4-byte value in eax into an 8-byte value in rax."),
    "addss": _simple("Zaehlt die Kommazahl {b} zu {a} dazu.", "Adds the decimal number {b} to {a}.", True, True),
    "subss": _simple("Zieht die Kommazahl {b} von {a} ab. Bei Leben oder Ausdauer oft der Schaden / Verbrauch.",
                     "Subtracts the decimal number {b} from {a}. For health or stamina often the damage / usage.", True, True),
    "mulss": _simple("Multipliziert {a} mit der Kommazahl {b}.", "Multiplies {a} by the decimal number {b}.", True, True),
    "divss": _simple("Teilt {a} durch die Kommazahl {b}.", "Divides {a} by the decimal number {b}.", True, True),
    "addsd": _simple("Zaehlt die (doppelt genaue) Kommazahl {b} zu {a} dazu.", "Adds the double-precision number {b} to {a}.", True, True),
    "subsd": _simple("Zieht die (doppelt genaue) Kommazahl {b} von {a} ab.", "Subtracts the double-precision number {b} from {a}.", True, True),
    "mulsd": _simple("Multipliziert {a} mit der (doppelt genauen) Kommazahl {b}.", "Multiplies {a} by the double-precision number {b}.", True, True),
    "divsd": _simple("Teilt {a} durch die (doppelt genaue) Kommazahl {b}.", "Divides {a} by the double-precision number {b}.", True, True),
    "comiss": _simple("Vergleicht zwei Kommazahlen ({a} und {b}). Der naechste Sprung wertet das aus.",
                      "Compares two decimal numbers ({a} and {b}). The next jump uses the result."),
    "ucomiss": _simple("Vergleicht zwei Kommazahlen ({a} und {b}). Der naechste Sprung wertet das aus.",
                       "Compares two decimal numbers ({a} and {b}). The next jump uses the result."),
    "comisd": _simple("Vergleicht zwei Kommazahlen ({a} und {b}). Der naechste Sprung wertet das aus.",
                      "Compares two decimal numbers ({a} and {b}). The next jump uses the result."),
    "ucomisd": _simple("Vergleicht zwei Kommazahlen ({a} und {b}). Der naechste Sprung wertet das aus.",
                       "Compares two decimal numbers ({a} and {b}). The next jump uses the result."),
    "cvtsi2ss": _simple("Macht aus der ganzen Zahl {b} eine Kommazahl in {a}.", "Turns the whole number {b} into a decimal number in {a}."),
    "cvtsi2sd": _simple("Macht aus der ganzen Zahl {b} eine Kommazahl in {a}.", "Turns the whole number {b} into a decimal number in {a}."),
    "cvttss2si": _simple("Macht aus der Kommazahl {b} eine ganze Zahl in {a} (Nachkommastellen fallen weg).",
                         "Turns the decimal number {b} into a whole number in {a} (decimals are dropped)."),
    "cvttsd2si": _simple("Macht aus der Kommazahl {b} eine ganze Zahl in {a} (Nachkommastellen fallen weg).",
                         "Turns the decimal number {b} into a whole number in {a} (decimals are dropped)."),
    "cvtss2sd": _simple("Wandelt die Kommazahl {b} in doppelte Genauigkeit um.", "Converts the decimal number {b} to double precision."),
    "cvtsd2ss": _simple("Wandelt die Kommazahl {b} in einfache Genauigkeit um.", "Converts the decimal number {b} to single precision."),
    "xorps": _simple("Kippt Bits in {a}; mit sich selbst gibt das 0.", "Flips bits in {a}; with itself this gives 0."),
    "pxor": _simple("Kippt Bits in {a}; mit sich selbst gibt das 0.", "Flips bits in {a}; with itself this gives 0."),
    "sqrtss": _simple("Zieht die Wurzel aus {b}.", "Takes the square root of {b}."),
    "maxss": _simple("Nimmt den groesseren der beiden Kommawerte {a} und {b}.", "Takes the larger of the two decimal values {a} and {b}."),
    "minss": _simple("Nimmt den kleineren der beiden Kommawerte {a} und {b}.", "Takes the smaller of the two decimal values {a} and {b}."),
}


def explain(mnemonic, op_str="", lang=None):
    """Erklaerung in Klartext ("" wenn der Befehl nicht bekannt ist)."""
    if lang is None:
        try:
            import tools_i18n
            lang = tools_i18n.lang()
        except Exception:  # noqa: BLE001
            lang = "de"
    lang = "en" if lang == "en" else "de"
    de = lang == "de"
    full = ((mnemonic or "") + " " + (op_str or "")).strip()
    pref = ""
    while True:                                           # Praefixe (lock / rep ...) stehen je nach Capstone vorne oder im Befehl
        first, _s, rest = full.partition(" ")
        if first.lower() in ("lock", "rep", "repe", "repne", "repz", "repnz", "notrack", "bnd") and rest:
            if first.lower() == "lock":
                pref += "Atomar (thread-sicher): " if de else "Atomic (thread-safe): "
            elif first.lower().startswith("rep"):
                pref += "Wiederholt: " if de else "Repeated: "
            full = rest.strip()
            continue
        break
    m, _s, op_str = full.partition(" ")
    m, op_str = m.lower().strip(), op_str.strip()
    if pref:
        inner = explain(m, op_str, lang)
        return (pref + inner) if inner else ""
    ops = split_ops(op_str)
    a = ops[0] if ops else ""
    b = ops[1] if len(ops) > 1 else ""
    if m == "xor" and len(ops) == 2 and ops[0].lower() == ops[1].lower() and kind(a) == "reg":
        return (f"Setzt {a} auf 0 (schnellster Weg dafuer)." if de else f"Sets {a} to 0 (the fastest way).")
    if m in ("xorps", "pxor") and len(ops) == 2 and ops[0].lower() == ops[1].lower():
        return (f"Setzt {a} auf 0." if de else f"Sets {a} to 0.")
    if m == "call":
        if kind(a) == "imm":
            return (f"Ruft die Funktion bei {a} auf (danach geht es hier weiter)." if de
                    else f"Calls the function at {a} (then continues here).")
        return (f"Ruft die Funktion auf, deren Adresse in {a} steht (danach geht es hier weiter)." if de
                else f"Calls the function whose address is in {a} (then continues here).")
    if m == "jmp":
        return (f"Springt immer zu {a}." if de else f"Always jumps to {a}.")
    if m in JCC:
        cond = JCC[m][0 if de else 1]
        return (f"Springt zu {a}, aber nur wenn {cond} (Ergebnis des Befehls davor)." if de
                else f"Jumps to {a}, but only if {cond} (result of the previous instruction).")
    if m.startswith("cmov") and m[4:] and ("j" + m[4:]) in JCC:
        cond = JCC["j" + m[4:]][0 if de else 1]
        return (f"Kopiert {b} nach {a}, aber nur wenn {cond}." if de else f"Copies {b} to {a}, but only if {cond}.")
    if m.startswith("set") and ("j" + m[3:]) in JCC:
        cond = JCC["j" + m[3:]][0 if de else 1]
        return (f"Setzt {a} auf 1, wenn {cond}, sonst auf 0." if de else f"Sets {a} to 1 if {cond}, otherwise to 0.")
    if m in ("movsb", "movsw", "movsq", "stosb", "stosw", "stosd", "stosq") or (
            m == "movsd" and (not ops or all(kind(o) == "mem" for o in ops))):
        return ("Kopiert / fuellt Speicher Stueck fuer Stueck (meist mit 'rep' davor)." if de
                else "Copies / fills memory piece by piece (usually with 'rep' in front).")
    t = _T.get(m)
    if t is None:
        return ""
    text = t[0] if de else t[1]
    floaty = t[3]
    a_txt, b_txt = describe(a, lang) if a else "", describe(b, lang) if b else ""
    text = text.format(a=a_txt, b=b_txt, A=a, B=b)
    if t[2]:
        text += _hint_write(a, lang, floaty)
    return text


def short_target_hint(op_str):
    """Wenn der Speicherzugriff 'Objekt + Feld' aussieht ([rbx + 0x10]) -> (register, offset) sonst None."""
    m = re.search(r"\[\s*([re]?[a-z0-9]+)\s*\+\s*(0x[0-9a-f]+|\d+)\s*\]", op_str or "", re.I)
    if not m or m.group(1).lower() in ("rip", "rsp", "esp"):
        return None
    return m.group(1).lower(), int(m.group(2), 0)
