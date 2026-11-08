"""howto.py - Anleitungen fuer Einsteiger: Dateien finden, lesen, durchsuchen und fuer die Anzeige zerlegen (ohne tkinter).

Die Texte liegen als Markdown-Dateien in  docs/howto/de/  und  docs/howto/en/  (Dateiname  NN-name.md,  NN = Reihenfolge).
Das Fenster ANLEITUNGEN (tools_howto_gui.py, Knopf im Hauptfenster) zeigt sie in der Sprache des Programms (DE / EN), auf GitHub sind es dieselben Dateien.

Unterstuetztes Markdown (bewusst klein):
  # / ## / ###        Ueberschriften            **fett**   *kursiv*   `Code`
  - Punkt / 1. Punkt  Listen                     ```        Codeblock
  > **Tipp:** ...     Hinweis-Kasten (Tipp / Hinweis / Achtung bzw. Tip / Note / Warning)
  [Text](howto:name)  Verweis auf eine andere Anleitung (name = Dateiname ohne Nummer und .md)
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "docs", "howto")
LANGS = ("de", "en")

# interner Tab-Name (wie im Code von tools_gui.py) -> Anleitung.  Die "?"-Taste oeffnet die Anleitung des gerade offenen Tabs.
TAB_TOPICS = {
    "START": "first-steps",
    "WERT SUCHEN": "find-value",
    "CHEATS BEARBEITEN": "edit-cheats",
    "DISASSEMBLER": "assembler-basics",
    "KONVERTER": "assembler-basics",
    "★ UNREAL": "items-unreal", "★ ITEMS": "items-unreal",
    "★ UNITY": "items-unity", "★ UNITY ITEMS": "items-unity",
    "★ WERTE": "values-and-live", "★ UE-LIVE": "values-and-live", "★ CHEAT-MENÜ": "values-and-live",
    "★ UE-ENTDECKER": "values-and-live", "UE-AUTO": "values-and-live",
    "★ WERTE UNITY": "values-and-live", "★ UNITY MANUELL": "values-and-live",
    "POINTER": "pointers", "AOB / UPDATE": "pointers",
    "DEBUGGER": "debugger", "KERNEL-LOG": "debugger", "FUNKTIONS-LOGGER": "debugger",
    "FORTGESCHRITTEN": "advanced-tools", "SPEICHER": "advanced-tools", "PYTHON-SKRIPT": "advanced-tools",
    "FUNKTION AUFRUFEN": "advanced-tools", "JOURNAL / UNDO": "advanced-tools",
}
TOPIC_FILES = re.compile(r"^(\d+)-([a-z0-9][a-z0-9-]*)\.md$")


def folder(lang, root=None):
    return os.path.join(root or ROOT, lang if lang in LANGS else "de")


def articles(lang="de", root=None):
    """Alle Anleitungen einer Sprache in Leserichtung: [{slug, title, path, order}]"""
    out = []
    d = folder(lang, root)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for fn in names:
        m = TOPIC_FILES.match(fn)
        if not m:
            continue
        path = os.path.join(d, fn)
        out.append({"slug": m.group(2), "title": _title(path) or m.group(2), "path": path, "order": int(m.group(1))})
    return out


def _title(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("# "):
                    return line[2:].strip()
    except OSError:
        pass
    return ""


def find(slug, lang="de", root=None):
    """Eintrag zu slug; fehlt die Sprache, wird die andere genommen.  KeyError, wenn es die Anleitung gar nicht gibt."""
    for lg in (lang, "en" if lang == "de" else "de"):
        for a in articles(lg, root):
            if a["slug"] == slug:
                return dict(a, lang=lg)
    raise KeyError(slug)


def load(slug, lang="de", root=None):
    a = find(slug, lang, root)
    with open(a["path"], encoding="utf-8") as f:
        return f.read()


def topic_for(tab_name):
    return TAB_TOPICS.get(tab_name)


# ----------------------------------------------------------------------------------------------------------
# Markdown -> Bloecke
# ----------------------------------------------------------------------------------------------------------
_INLINE = re.compile(r"(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\(howto:[a-z0-9-]+\)|(?<![\w*])\*[^*\s][^*\n]*?\*(?![\w*]))")
_CALLOUT = re.compile(r"^\*\*(Tip|Tipp|Note|Hinweis|Warning|Achtung|Warnung)[:.]?\*\*\s*", re.I)
_KINDS = {"tip": "tip", "tipp": "tip", "note": "note", "hinweis": "note", "warning": "warn", "achtung": "warn", "warnung": "warn"}


def spans(text):
    """Zeile -> [(Text, Stil)] mit Stil '', 'b', 'i', 'code' oder 'link:<slug>'."""
    out = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], ""))
        tok = m.group(0)
        if tok.startswith("**"):
            out.append((tok[2:-2], "b"))
        elif tok.startswith("`"):
            out.append((tok[1:-1], "code"))
        elif tok.startswith("["):
            label, slug = re.match(r"\[([^\]]+)\]\(howto:([a-z0-9-]+)\)", tok).groups()
            out.append((label, "link:" + slug))
        else:
            out.append((tok[1:-1], "i"))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], ""))
    return out


def parse(md):
    """Markdown -> Liste von Bloecken: (art, inhalt).  art: h1 h2 h3 p ul ol code tip note warn hr;  inhalt: Spans bzw. Liste von Spans."""
    blocks = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    para = []

    def flush():
        if para:
            blocks.append(("p", spans(" ".join(s.strip() for s in para))))
            para.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            flush()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            blocks.append(("code", "\n".join(code)))
        elif not s:
            flush()
        elif s == "---":
            flush()
            blocks.append(("hr", None))
        elif s.startswith("#"):
            flush()
            n = len(s) - len(s.lstrip("#"))
            if 1 <= n <= 3 and s[n:n + 1] == " ":
                blocks.append((f"h{n}", spans(s[n + 1:].strip())))
            else:
                para.append(s)
        elif s.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            i -= 1
            text = " ".join(q for q in quote if q)
            m = _CALLOUT.match(text)
            kind = _KINDS[m.group(1).lower()] if m else "note"
            blocks.append((kind, spans(text)))
        elif re.match(r"^[-*] ", s) or re.match(r"^\d+[.)] ", s):
            flush()
            ordered = bool(re.match(r"^\d+[.)] ", s))
            items = []
            while i < len(lines):
                t = lines[i].strip()
                m = re.match(r"^\d+[.)] (.*)", t) if ordered else re.match(r"^[-*] (.*)", t)
                if m:
                    items.append([m.group(1)])
                elif t and lines[i].startswith((" ", "\t")) and items:          # Fortsetzungszeile
                    items[-1].append(t)
                else:
                    break
                i += 1
            i -= 1
            blocks.append(("ol" if ordered else "ul", [spans(" ".join(it)) for it in items]))
        else:
            para.append(s)
        i += 1
    flush()
    return blocks


def plain(md):
    """Nur der lesbare Text (fuer die Suche): Markdown-Zeichen entfernt."""
    t = re.sub(r"```", "", md)
    t = re.sub(r"\[([^\]]+)\]\(howto:[a-z0-9-]+\)", r"\1", t)
    t = re.sub(r"\*\*|`", "", t)
    t = re.sub(r"(?m)^\s*(#{1,3}|>|[-*]|\d+[.)])\s+", "", t)
    return t


# ----------------------------------------------------------------------------------------------------------
# Suche
# ----------------------------------------------------------------------------------------------------------
def search(query, lang="de", root=None, limit=30):
    """Alle Woerter der Suche muessen vorkommen (Gross/Klein egal).  Treffer im Titel zaehlen am meisten, dann Ueberschriften, dann Text.
    -> [{slug, title, snippet, score}] absteigend sortiert."""
    words = [w for w in re.split(r"\s+", query.strip().lower()) if w]
    if not words:
        return []
    res = []
    for a in articles(lang, root):
        try:
            with open(a["path"], encoding="utf-8") as f:
                md = f.read()
        except OSError:
            continue
        body = plain(md)
        low = body.lower()
        title = a["title"].lower()
        heads = " ".join(re.findall(r"(?m)^#{2,3}\s+(.*)$", md)).lower()
        if not all(w in low or w in title for w in words):
            continue
        score = sum(10 for w in words if w in title) + sum(4 for w in words if w in heads) + sum(min(low.count(w), 5) for w in words)
        res.append({"slug": a["slug"], "title": a["title"], "snippet": _snippet(body, words[0]), "score": score})
    res.sort(key=lambda r: (-r["score"], r["title"]))
    return res[:limit]


def _snippet(body, word, width=90):
    flat = re.sub(r"\s+", " ", body)
    i = flat.lower().find(word)
    if i < 0:
        return flat[:width].strip()
    a = max(0, i - width // 3)
    return ("…" if a else "") + flat[a:a + width].strip() + ("…" if a + width < len(flat) else "")
