"""cheat_from_disasm.py - aus markierten Disassembler-Zeilen einen Cheat vorbereiten (ohne Oberflaeche, testbar).

Zwei Wege, beide enden im Cheat-Editor (dort: TEST AN/AUS, SPEICHERN mit automatischer Signatur):

  NOP    Die markierten Befehle werden mit NOP (90) ueberschrieben - z. B. den Schaden-Abzug abschalten.
         Mehrere getrennte Stellen gehen in EINEM Cheat: die erste ist die Haupt-Stelle (Offset), jede weitere steht in
         ORIGINAL und NEU als Zeile '+0xOFFSET: Bytes' (patch_engine.parse_segments: "fusionierter Patch").
  CAVE   Die markierten Befehle werden in eine Code-Cave kopiert; dort kann man sie aendern oder weglassen.  Die Cave deckt die
         GANZE erste Stelle ab, mindestens aber HOOK_MIN Byte (jmp rel32 + NOPs).

Eine Markierung besteht aus ganzen Befehlen; getrennte Stellen werden NICHT zusammengezogen (sonst wuerden die Befehle
dazwischen mitueberschrieben).
"""
HOOK_MIN = 5             # ein Cave-Hook (jmp rel32 + NOPs) ueberschreibt mindestens so viele Byte
HOOK_LONG = 15           # ab hier wird gewarnt: sehr lange ueberschriebene Folge
FAR = 0x1000             # weitere NOP-Stellen weiter weg als das: nur die erste hat eine Signatur, die anderen folgen mit
                         # demselben Abstand - nach einem Update kann der Abstand ein anderer sein


def runs(lines):
    """Markierte Zeilen -> zusammenhaengende Stellen [{'addr', 'size', 'lines'}], nach Adresse sortiert."""
    out = []
    for ln in sorted(lines, key=lambda x: x["addr"]):
        if out and out[-1]["addr"] + out[-1]["size"] == ln["addr"]:
            out[-1]["size"] += ln["size"]
            out[-1]["lines"].append(ln)
        else:
            out.append({"addr": ln["addr"], "size": ln["size"], "lines": [ln]})
    return out


def run_hex(run):
    """Originalbytes einer Stelle als 'AA BB CC'."""
    return " ".join(f"{b:02X}" for ln in run["lines"] for b in ln["bytes"])


def nop_hex(n):
    return " ".join(["90"] * n)


def _segment(run, base, text):
    """Zeile fuer eine WEITERE Stelle: '+0xOFFSET: text' (unterhalb der Image-Base: absolute Adresse)."""
    a = run["addr"]
    return f"+0x{a - base:X}: {text}" if a >= base else f"0x{a:X}: {text}"


def nop_draft(rs, base, name=""):
    """Vorbelegung fuer den Cheat-Editor (einfacher Patch): {'addr', 'default', 'new', 'name', 'type'}."""
    default, new = [], []
    for i, r in enumerate(rs):
        d, n = run_hex(r), nop_hex(r["size"])
        default.append(d if i == 0 else _segment(r, base, d))
        new.append(n if i == 0 else _segment(r, base, n))
    return {"addr": rs[0]["addr"], "default": "\n".join(default), "new": "\n".join(new),
            "name": name or default_name("nop", rs, base), "type": "patch"}


def cave_plan(rs):
    """Cave-Hook an der ersten Stelle: {'start', 'min_len', 'ignored'}.  min_len deckt die ganze Stelle ab (mindestens HOOK_MIN)."""
    return {"start": rs[0]["addr"], "min_len": max(HOOK_MIN, rs[0]["size"]), "ignored": len(rs) - 1}


def default_name(mode, rs, base):
    off = rs[0]["addr"] - base
    return f"{'NOP' if mode == 'nop' else 'Hook'}_{off:X}" if off >= 0 else f"{'NOP' if mode == 'nop' else 'Hook'}_{rs[0]['addr']:X}"


def warnings(mode, rs):
    """Hinweise zur Auswahl: [(schluessel, wert)] - die Oberflaeche macht daraus Text."""
    out = []
    if mode == "nop" and len(rs) > 1 and rs[-1]["addr"] - rs[0]["addr"] > FAR:
        out.append(("far", rs[-1]["addr"] - rs[0]["addr"]))
    if mode == "cave":
        if rs[0]["size"] < HOOK_MIN:
            out.append(("short", HOOK_MIN))
        if len(rs) > 1:
            out.append(("ignored", len(rs) - 1))
        if rs[0]["size"] > HOOK_LONG:
            out.append(("long", rs[0]["size"]))
    return out


def summary(rs):
    """(Zeilen, Stellen, Byte) der Auswahl."""
    return sum(len(r["lines"]) for r in rs), len(rs), sum(r["size"] for r in rs)
