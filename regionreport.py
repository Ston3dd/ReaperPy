"""regionreport.py - Speicherregionen des laufenden Spiels auflisten (Name, Groesse, Rechte), zusammengefasst und einzeln.

Zweck: sehen, WO die 11 GB 'Alles Schreibbare' liegen, damit ein Scan-Bereich gezielt gewaehlt werden kann.
Reine Auswertung (ohne Konsole testbar): maps = [{'name','start','end','prot'}] wie ps5_ext.maps_named().
"""
import collections

PROT = ((1, "r"), (2, "w"), (4, "x"))


def prot_text(p):
    return "".join(c if p & b else "-" for b, c in PROT)


def summarize(maps):
    """-> [(name, prot_text, anzahl, MB)] nach Groesse absteigend (nur lesbare Regionen)."""
    agg = collections.OrderedDict()
    for m in maps:
        if not m["prot"] & 1:
            continue
        key = (m.get("name") or "(ohne Name)", prot_text(m["prot"]))
        n, size = agg.get(key, (0, 0))
        agg[key] = (n + 1, size + m["end"] - m["start"])
    rows = [(k[0], k[1], n, s / 1048576) for k, (n, s) in agg.items()]
    rows.sort(key=lambda r: -r[3])
    return rows


def report(maps, top=40):
    rows = summarize(maps)
    rw = sum(r[3] for r in rows if r[1][1] == "w")
    total = sum(r[3] for r in rows)
    out = [f"Lesbar: {total:.0f} MB in {sum(r[2] for r in rows)} Regionen; davon schreibbar: {rw:.0f} MB", "",
           f"{'NAME':<34}{'RECHTE':<8}{'ANZAHL':>8}{'MB':>10}"]
    out += [f"{n[:33]:<34}{p:<8}{c:>8}{mb:>10.1f}" for n, p, c, mb in rows]
    big = sorted((m for m in maps if m["prot"] & 3 == 3 or (m["prot"] & 1 and m["prot"] & 2)),
                 key=lambda m: m["start"] - m["end"])[:top]
    out += ["", f"Die {len(big)} groessten schreibbaren Regionen:", f"{'START':<18}{'ENDE':<18}{'MB':>9}  RECHTE  NAME"]
    out += [f"{m['start']:#018x}  {m['end']:#018x}{(m['end'] - m['start']) / 1048576:>9.1f}  {prot_text(m['prot'])}     "
            f"{m.get('name', '')}" for m in big]
    return "\n".join(out) + "\n"
