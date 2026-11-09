"""asm_help.py - verstaendliche Assembler-Fehler und eine Groessen-Vorschau (ohne tkinter).

friendly_error(meldung, text)   Keystone-/Payload-Meldung -> Satz in Klartext, mit der Zeile und einem Beispiel
fit_preview(text, platz, assemble)   Wie gross wird der Code, passt er in `platz` Byte?  -> (art, text)
"""
import re

EXAMPLES = ("mov eax, 999", "nop", "add dword ptr [rbx+0x10], 5", "jmp OriginReturn")


def _lang(lang):
    if lang is None:
        try:
            import tools_i18n
            lang = tools_i18n.lang()
        except Exception:  # noqa: BLE001
            lang = "de"
    return "en" if lang == "en" else "de"


def _bad_line(text, msg):
    """Die Zeile, die der Assembler meint (er nennt sie selten) - nur wenn es genau eine erkennbare gibt."""
    m = re.search(r"\bline\s+(\d+)\b", msg, re.I)
    lines = [ln for ln in (text or "").splitlines()]
    if m:
        n = int(m.group(1))
        if 1 <= n <= len(lines):
            return n, lines[n - 1].strip()
    if len([ln for ln in lines if ln.strip()]) == 1:
        return 1, lines[0].strip() if lines else ""
    return None, ""


def friendly_error(msg, text="", lang=None):
    """Meldung des Assemblers -> verstaendlicher Satz (die Originalmeldung steht in Klammern dahinter)."""
    lang = _lang(lang)
    de = lang == "de"
    raw = str(msg).strip()
    low = raw.lower()
    n, line = _bad_line(text, raw)
    where = ""
    if line:
        where = (f"In Zeile {n}: '{line}'. " if de else f"In line {n}: '{line}'. ")
    if "mnemonicfail" in low or "invalid mnemonic" in low or "unknown mnemonic" in low:
        body = ("Diesen Befehl kenne ich nicht. Vielleicht ein Tippfehler? Beispiele: " if de
                else "I do not know this instruction. Maybe a typo? Examples: ") + ", ".join(EXAMPLES[:3])
    elif "invalidoperand" in low or "invalid operand" in low:
        body = ("Mit diesen Angaben passt der Befehl nicht: Register und Groesse muessen zusammenpassen "
                "(zum Beispiel 'eax' mit 'dword ptr', 'rax' mit 'qword ptr'). Beispiel: " if de
                else "The instruction does not fit these operands: the register and the size must match "
                     "(for example 'eax' with 'dword ptr', 'rax' with 'qword ptr'). Example: ") + EXAMPLES[2]
    elif "symbol" in low or "undefined" in low or "label" in low:
        body = ("Eine Bezeichnung ist unbekannt. Erlaubt sind OriginReturn, OriginTarget und eigene Marken, die du mit "
                "'Name:' in eine eigene Zeile schreibst." if de
                else "A name is unknown. Allowed are OriginReturn, OriginTarget and your own labels written as "
                     "'Name:' on a line of their own.")
    elif "fixup" in low or "out of range" in low or "relocation" in low:
        body = ("Das Sprungziel ist zu weit weg fuer diesen Befehl." if de
                else "The jump target is too far away for this instruction.")
    elif "keine zahl" in low or "number" in low or "expr" in low or "immediate" in low:
        body = ("Hier wird eine Zahl erwartet, zum Beispiel 999 oder 0x3E7." if de
                else "A number is expected here, for example 999 or 0x3E7.")
    elif "kein assembler" in low or "no assembler" in low or "keystone" in low and "install" in low:
        body = ("Es ist kein Assembler vorhanden. Installiere ihn mit:  pip install keystone-engine" if de
                else "No assembler is available. Install it with:  pip install keystone-engine")
    else:
        body = ("Das konnte ich nicht in Maschinencode umsetzen. Pruefe die Schreibweise: ein Befehl pro Zeile, "
                "zum Beispiel " if de else "I could not turn this into machine code. Check the spelling: one "
                                          "instruction per line, for example ") + EXAMPLES[0]
    return f"{where}{body}  [{raw}]"


def fit_preview(text, space, assemble, addr=0):
    """Wie gross wird der Code?  assemble(text, addr) -> bytes.  Gibt (art, meldung) zurueck:
    art = 'empty' | 'ok' | 'pad' | 'big' | 'err'."""
    lang = _lang(None)
    de = lang == "de"
    lines = [ln for ln in (text or "").splitlines() if ln.strip() and not ln.strip().startswith((";", "#", "//"))]
    if not lines:
        return "empty", ""
    try:
        size = len(assemble("\n".join(lines), addr))
    except Exception as e:  # noqa: BLE001
        return "err", friendly_error(str(e), text, lang)
    if not space:
        return "ok", (f"{size} Byte" if de else f"{size} bytes")
    if size > space:
        return "big", (f"{size} Byte - zu gross, es sind nur {space} Byte Platz ({size - space} zu viel)." if de
                       else f"{size} bytes - too big, there is room for {space} bytes only ({size - space} too many).")
    if size == space:
        return "ok", (f"{size} Byte - passt genau." if de else f"{size} bytes - fits exactly.")
    return "pad", (f"{size} Byte - passt, die restlichen {space - size} Byte werden mit NOP aufgefuellt." if de
                   else f"{size} bytes - fits, the remaining {space - size} bytes are filled with NOP.")
