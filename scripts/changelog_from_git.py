"""CHANGELOG-Entwurf aus den Commit-Nachrichten erzeugen (halbautomatisch: Ergebnis kurz lesen, dann einfuegen).

    python scripts/changelog_from_git.py              # seit dem letzten Tag bis HEAD
    python scripts/changelog_from_git.py v5.9.0       # seit diesem Tag/Commit
    python scripts/changelog_from_git.py v5.9.0 5.9.1 # Ueberschrift '## 5.9.1 - <Datum>' statt 'Unreleased'

Erwartet den Stil, den das Projekt schon benutzt: im Commit-Text stehen Zeilen 'Added', 'Changed' oder 'Fixed',
darunter '- Punkt'-Zeilen.  Commits ohne solche Abschnitte kommen mit ihrer Betreffzeile unter 'Changed'.
'Tests: ...'-Zeilen werden uebersprungen.
"""
import datetime
import re
import subprocess
import sys

SECTIONS = ("Added", "Changed", "Fixed")
_SKIP = re.compile(r"^(tests?|files?):", re.I)


def parse_commit(message):
    """Commit-Text -> {'Added': [...], 'Changed': [...], 'Fixed': [...]}."""
    lines = [ln.rstrip() for ln in message.strip().splitlines()]
    out = {k: [] for k in SECTIONS}
    cur, seen = None, False
    for ln in lines[1:]:
        head = ln.strip().rstrip(":")
        if head in SECTIONS:
            cur, seen = head, True
        elif cur and ln.lstrip().startswith(("- ", "* ")):
            out[cur].append(ln.lstrip()[2:].strip())
        elif cur and ln.startswith("  ") and out[cur]:
            out[cur][-1] += " " + ln.strip()                      # eingerueckte Fortsetzungszeile
        elif _SKIP.match(ln.strip()):
            cur = None
    if not seen and lines and lines[0].strip():
        out["Changed"].append(lines[0].strip())
    return out


def build(messages, title="Unreleased"):
    merged = {k: [] for k in SECTIONS}
    for m in messages:
        for k, items in parse_commit(m).items():
            for it in items:
                if it not in merged[k]:
                    merged[k].append(it)
    parts = [f"## {title}", ""]
    for k in SECTIONS:
        if merged[k]:
            parts += [f"### {k}"] + [f"- {i}" for i in merged[k]] + [""]
    return "\n".join(parts).rstrip() + "\n"


def git_messages(since=None):
    if since is None:
        r = subprocess.run(["git", "describe", "--tags", "--abbrev=0"], capture_output=True, text=True, encoding="utf-8")
        since = r.stdout.strip() or None
    rng = f"{since}..HEAD" if since else "HEAD"
    out = subprocess.run(["git", "log", "--no-merges", "--reverse", "--format=%B%x00", rng], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    return [m for m in out.split("\x00") if m.strip()]


def main(argv):
    since = argv[1] if len(argv) > 1 else None
    title = f"{argv[2]} - {datetime.date.today().isoformat()}" if len(argv) > 2 else "Unreleased"
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(build(git_messages(since), title))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
