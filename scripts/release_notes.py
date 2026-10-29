"""Release-Notes fuer eine Version aus CHANGELOG.md ziehen (fuer die GitHub-Release-Action).

    python scripts/release_notes.py 5.9.1 > notes.md

Sucht die Ueberschrift '## 5.9.1 - <Datum>' (auch '## [5.9.1]' oder 'v5.9.1') und gibt den Abschnitt bis zur naechsten
'## '-Ueberschrift aus.  Findet er nichts, ist der Exit-Code 1 (die Action faellt dann auf automatische Notes zurueck).
"""
import re
import sys
from pathlib import Path


def extract(changelog_text, version):
    version = str(version).strip().lstrip("vV")
    head = re.compile(r"^##[ \t]+\[?v?" + re.escape(version) + r"\]?(?=[ \t]|$|-)[^\n]*$", re.M)   # ganze Ueberschriftszeile
    m = head.search(changelog_text)
    if not m:
        return ""
    rest = changelog_text[m.end():]
    nxt = re.search(r"^##\s", rest, re.M)
    return (rest[:nxt.start()] if nxt else rest).strip()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = Path(argv[2]) if len(argv) > 2 else Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    text = extract(path.read_text(encoding="utf-8"), argv[1])
    if not text:
        print(f"Kein Abschnitt fuer {argv[1]} in {path}", file=sys.stderr)
        return 1
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
