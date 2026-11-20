"""debug_guide.py - Einsteiger-Hilfe fuer den Debugger: sagt in einfachen Worten, was als Naechstes zu tun ist,
und erklaert einen Treffer in Klartext (inkl. Vorschlag fuer den Cheat).  Reine Logik, keine Oberflaeche."""
import asm_explain as AX

try:
    from tools_i18n import translate as _tr
except Exception:  # noqa: BLE001
    def _tr(text):
        return text

STEP_ATTACH = "SCHRITT 1 von 4: Spiel starten, dann oben ATTACH druecken."
STEP_ARM = "SCHRITT 2 von 4: Du brauchst einen WATCHPOINT. Gib bei WATCHPOINT @ die Adresse des Werts ein (z.B. deine HP aus einer Suche), Typ 'schreiben', dann ADD. Er meldet, wer den Wert aendert."
STEP_WAIT = "SCHRITT 3 von 4: Warten. Mach im Spiel etwas, das den Wert aendert (Schaden nehmen, Geld ausgeben). Das Spiel haelt dann an und unten erscheint ein TREFFER."
STEP_HIT = "SCHRITT 4 von 4: Treffer! Die gruene Zeile im KONTEXT ist der Befehl, der deinen Wert aendert. Rechtsklick darauf -> IM DISASSEMBLER OEFFNEN, dort die Zeile markieren und CHEAT BAUEN druecken. Danach ▶ WEITER."
STEP_TARGETS = "TIPP: Trifft derselbe Befehl viele Objekte (Spieler UND Gegner)? Dann in der Tabelle ZIELE die Zeile waehlen, deren Wert zu dir passt, und DAS BIN ICH druecken."


def next_step(attached, n_bp=0, n_wp=0, n_hits=0, n_targets=0):
    """-> Text fuer die Hilfezeile ganz oben."""
    if not attached:
        return _tr(STEP_ATTACH)
    if n_hits:
        text = _tr(STEP_HIT)
        if n_targets > 1:
            text += "  " + _tr(STEP_TARGETS)
        return text
    if not (n_bp or n_wp):
        return _tr(STEP_ARM)
    return _tr(STEP_WAIT)


E_HEAD = "Dieser Befehl ({addr}  {insn}):"
E_DOWN = "  Cheat-Idee: mit NOP ausschalten -> der Wert sinkt nicht mehr (z.B. unendlich Leben/Munition)."
E_SET = "  Cheat-Idee: NOP = Wert wird nicht mehr geschrieben; oder CAVE = du setzt den Wert selbst."
E_NEXT = "  Naechster Schritt: Rechtsklick -> IM DISASSEMBLER OEFFNEN, Zeile markieren, CHEAT BAUEN."


WRITERS = ("mov", "movss", "movaps", "movsd", "add", "addss", "xor", "and", "or", "imul", "mulss", "cvttss2si", "cvtsi2ss")


def explain_hit(ctx, lang=None):
    """Treffer-Kontext (hit_context.build_context) -> mehrzeiliger Klartext: was der Befehl tut und was man damit machen kann."""
    w = (ctx or {}).get("writer") or (ctx or {}).get("insn")
    if not w:
        return ""
    what = AX.explain(w["mnemonic"], w["op_str"], "en" if lang == "en" else "de")
    mn = w["mnemonic"].lower()
    out = [_tr(E_HEAD).format(addr=f"{w['addr']:#x}", insn=f"{w['mnemonic']} {w['op_str']}".strip())]
    if what:
        out.append("  " + what)
    if mn in ("sub", "dec", "subss", "subsd"):
        out.append(_tr(E_DOWN))
    elif mn in WRITERS or mn.startswith("v"):
        out.append(_tr(E_SET))
    out.append(_tr(E_NEXT))
    return "\n".join(out)
