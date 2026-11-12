"""item_finder.py - Item-Listen finden, OHNE sich auf den Namen der Tabelle / des Enums zu verlassen (ohne Oberflaeche).

Die Tabs UNREAL -> ITEMS und UNITY -> ITEMS erkennen die Item-Liste zuerst am NAMEN ("DT_ItemParam", "ItemID").  Heisst sie
anders ("Mst_Buki", "E_Obj", "DT_Param001"), fanden Einsteiger bisher nichts und konnten auch nicht von Hand waehlen.  Hier steht,
was dann hilft:

  content_score(namen)            Sieht eine Liste von Zeilen-/Enum-Namen nach Items aus?  (Anzahl, Namensmuster wie sword_01 /
                                  sword_02, Item-Woerter wie potion / armor, Gegenteil wie anim / sound)  -> (Wert, Gruende)
  probe_tables(...)               viele Listen lesen und nach Inhalt bewerten (mit Zeitlimit und Fortschritt)
  search(frage, probes)           "Ich sehe im Spiel ein Item namens X": in welcher Liste steht es?
  msg_*                           Klartext-Meldungen (de / en) fuer die Oberflaeche

Alles hier ist rein rechnerisch: gelesen wird ueber eine uebergebene Funktion -> ohne Konsole testbar (tests/test_item_finder.py).
"""
import re
import time
from dataclasses import dataclass, field

CONTENT_OK = 5.5            # ab hier gilt eine Liste "am Inhalt" als Item-Liste
CONTENT_MAYBE = 4.0         # darunter: nur als Kandidat zeigen
PROBE_ROWS = 400            # so viele Zeilen je Liste werden zum Bewerten / Suchen gelesen
PROBE_BUDGET_S = 45.0       # so lange darf das Durchsehen aller Listen hoechstens dauern

_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


def words(name):
    """'Potion_Small' / 'PotionSmall' / 'POTION_SMALL_02' -> ['potion', 'small', '02']"""
    return [w.lower() for w in _WORD.findall(str(name or ""))]


def norm(name):
    """Nur Buchstaben und Ziffern, klein: 'Health Potion_S' -> 'healthpotions'"""
    return re.sub(r"[^0-9a-z]", "", str(name or "").lower())


def _t(lang, de, en):
    return en if lang == "en" else de


# Woerter, die in den Zeilennamen von Item-Listen vorkommen
ROW_ITEM_WORDS = frozenset("""
potion elixir ether tonic antidote herb food meat fish bread apple berry fruit vegetable mushroom egg milk water meal drink ale wine
sword blade dagger knife axe mace hammer spear lance bow crossbow arrow bolt staff wand rod shield helmet helm armor armour cuirass
chest gauntlet glove boots boot shoes greave ring amulet necklace pendant cloak cape robe hat cap mask belt bracelet charm talisman
key scroll book note map tome letter coin gold silver copper gem jewel crystal ore ingot bar wood plank log stone brick iron steel
leather cloth thread bone fang claw hide fur scale feather bead powder dust essence shard fragment core part gear tool pickaxe shovel
torch rope bomb grenade ammo bullet magazine rifle pistol gun shotgun sniper medkit bandage syringe battery fuel scrap seed flower
orb relic artifact rune token ticket badge trophy potion_hp hp mp
""".split())
# Woerter, die nach "keine Item-Liste" klingen (Effekte, Oberflaeche, Sound, Animation ...)
ROW_JUNK_WORDS = frozenset("""
anim animation montage sound sfx vfx fx audio bgm voice music particle niagara widget button icon texture font style camera
dialog dialogue subtitle cutscene sequence level map stage trigger input key_binding keybinding localization string text
curve spline navmesh collision physics weather sky light shader material_instance socket bone skeleton
""".split())
GENERIC_FIRST = frozenset({"item", "items", "dt", "row", "data", "id", "e", "i", "t", "mst", "tbl"})


def _group_fraction(names):
    """-> (Anteil, Anzahl Gruppen).  Gruppen = Namen mit gleichem ersten Wort, mindestens 3 Stueck: sword_01, sword_02, potion_s ...
    Beginnen (fast) alle gleich ('Item_...'), zaehlt das zweite Wort.  Nur EINE Gruppe oder reine Nummern ('Item_0001')
    ist keine Aussage ueber den Inhalt: dann (0.0, 0) bzw. (0.5, 1) fuer 'durchnummeriert'."""
    toks = [words(n) for n in names]
    toks = [t for t in toks if t]
    if not toks:
        return 0.0, 0
    numbered = sum(1 for t in toks if t[-1].isdigit()) >= 0.9 * len(toks)
    for level in (0, 1):
        keys = ["#" if len(t) > level and t[level].isdigit() else (t[level] if len(t) > level else "") for t in toks]
        counts = {}
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
        top_key = max(counts, key=counts.get)
        if level == 0 and counts[top_key] >= 0.9 * len(keys):
            continue                                 # alle beginnen gleich -> beim zweiten Wort weiterschauen
        if counts[top_key] >= 0.9 * len(keys):
            return (0.5, 1) if (top_key == "#" or numbered) else (0.0, 0)
        groups = {k: c for k, c in counts.items() if c >= 3 and k and k != "#"}
        return sum(groups.values()) / len(keys), len(groups)
    return 0.0, 0


_WHY = {
    "few": ("zu wenige Einträge", "too few entries"),
    "count": ("{n} Einträge", "{n} entries"),
    "pattern": ("Namen mit gemeinsamem Muster (z. B. sword_01, sword_02)", "names with a common pattern (e.g. sword_01, sword_02)"),
    "numbered": ("durchnummerierte Namen", "numbered names"),
    "words": ("{n} Namen mit Item-Wörtern (Potion, Sword, Armor ...)", "{n} names with item words (potion, sword, armor ...)"),
    "junk": ("{n} Namen klingen nach Effekt / Oberfläche / Sound", "{n} names sound like effects / UI / sound"),
}


def _why(key, lang="de", **kw):
    de, en = _WHY[key]
    return (en if lang == "en" else de).format(**kw)


def content_score(names, lang="de"):
    """Sieht diese Liste von Namen nach Items aus?  -> (Wert 0..~10, [Gruende in Klartext]).  >= CONTENT_OK: ja."""
    names = [str(n) for n in names if str(n).strip()]
    n = len(names)
    if n < 4:
        return 0.0, [_why("few", lang)]
    reasons, score = [], 0.0
    size = (1 if n >= 8 else 0) + (1 if n >= 30 else 0) + (1 if n >= 100 else 0)
    score += size
    if n > 6000:
        score -= 1
    frac, ngroups = _group_fraction(names)
    if ngroups >= 2 and frac >= 0.3:
        score += 3 * min(1.0, frac)
        reasons += [_why("pattern", lang)]
    elif ngroups == 1 and frac == 0.5:
        score += 1.0
        reasons += [_why("numbered", lang)]
    toks = [set(words(x)) for x in names]
    item_hits = sum(1 for t in toks if t & ROW_ITEM_WORDS)
    junk_hits = sum(1 for t in toks if t & ROW_JUNK_WORDS)
    if item_hits:
        score += 3 * min(1.0, 3.0 * item_hits / n)
        reasons += [_why("words", lang, n=item_hits)]
    if junk_hits:
        score -= 4 * min(1.0, 3.0 * junk_hits / n)
        reasons += [_why("junk", lang, n=junk_hits)]
    if n >= 8:
        reasons.insert(0, _why("count", lang, n=n))
    return round(score, 1), reasons


def preview(names, n=4):
    """'sword_01, sword_02, potion_small, gold …' - zum Wiedererkennen."""
    seen, out = set(), []
    # erst Abwechslung (verschiedene erste Woerter), dann auffuellen
    for x in names:
        w = words(x)
        k = w[0] if w else str(x)
        if k not in seen:
            seen.add(k)
            out.append(str(x))
        if len(out) >= n:
            break
    for x in names:
        if len(out) >= n:
            break
        if str(x) not in out:
            out.append(str(x))
    return ", ".join(out) + (" …" if len(names) > len(out) else "")


# ----------------------------------------------------------------------------------------------------------------
# Viele Listen lesen und bewerten
# ----------------------------------------------------------------------------------------------------------------
@dataclass
class Probe:
    key: object                  # was der Aufrufer braucht, um die Liste wieder zu finden (z. B. (Adresse, Name) / Enum-Name)
    name: str
    names: list = field(default_factory=list)
    score: float = 0.0
    reasons: list = field(default_factory=list)

    @property
    def count(self):
        return len(self.names)

    def label(self, lang="de"):
        return _t(lang, f"{self.name}  -  {self.count} Einträge  -  z. B. {preview(self.names)}",
                  f"{self.name}  -  {self.count} entries  -  e.g. {preview(self.names)}")


@dataclass
class ProbeResult:
    probes: list
    total: int
    checked: int
    timed_out: bool = False

    def ranked(self, min_score=CONTENT_MAYBE):
        out = [p for p in self.probes if p.score >= min_score]
        out.sort(key=lambda p: (-p.score, -p.count, p.name.lower()))
        return out

    def best(self):
        r = self.ranked(CONTENT_OK)
        return r[0] if r else None


def probe_tables(tables, read_names, budget_s=PROBE_BUDGET_S, progress=None, clock=time.monotonic, cache=None):
    """tables = [(key, name)] in der Reihenfolge, in der gelesen werden soll; read_names(key) -> [Namen] (darf scheitern).
    cache: dict key -> Probe; schon gelesene Listen werden nicht noch einmal gelesen."""
    cache = cache if cache is not None else {}
    start, probes, checked, timed_out = clock(), [], 0, False
    for i, (key, name) in enumerate(tables):
        if key in cache:
            probes.append(cache[key])
            checked += 1
            continue
        if clock() - start > budget_s:
            timed_out = True
            break
        try:
            names = [str(x) for x in read_names(key)]
        except Exception:  # noqa: BLE001 - eine kaputte Liste darf die anderen nicht aufhalten
            names = []
        score, reasons = content_score(names)
        p = Probe(key, name, names, score, reasons)
        cache[key] = p
        probes.append(p)
        checked += 1
        if progress is not None and (i + 1) % 25 == 0:
            progress(i + 1, len(tables))
    return ProbeResult(probes, len(tables), checked, timed_out)


# ----------------------------------------------------------------------------------------------------------------
# "Ich sehe im Spiel ein Item namens X"
# ----------------------------------------------------------------------------------------------------------------
@dataclass
class Found:
    probe: Probe
    hits: list                  # passende Namen (beste zuerst)
    score: float


def _quality(q_norm, q_words, row):
    """3 = genau der Name, 2 = alle Suchwoerter sind Woerter des Namens, 1 = nur als Teilstueck enthalten, 0 = kein Treffer."""
    rn = norm(row)
    q_words = q_words or [q_norm]
    if not q_norm or (q_norm not in rn and not all(w in rn for w in q_words)):
        return 0
    if rn == q_norm:
        return 3
    if all(w in set(words(row)) for w in q_words):
        return 2
    return 1


def search(query, probes, max_hits=12):
    """Listen, in denen ein Name wie `query` vorkommt -> [Found], beste zuerst (Listen, die wie Item-Listen aussehen, vor Zufallstreffern)."""
    q_norm = norm(query)
    q_words = [w for w in words(query) if len(w) >= 2 or w.isdigit()]
    if len(q_norm) < 2:
        return []
    out = []
    for p in probes:
        scored = []
        for row in p.names:
            q = _quality(q_norm, q_words, row)
            if q:
                scored.append((q, row))
        if not scored:
            continue
        scored.sort(key=lambda x: (-x[0], len(x[1]), x[1].lower()))
        # Trefferqualitaet (die besten 3) + wie sehr die LISTE nach Items aussieht.  Viele Treffer allein zaehlen kaum: eine
        # Effekt-Tabelle mit 40 "Potion_Splash_..." darf die echte Item-Liste mit 3 Tränken nicht schlagen.
        score = sum(q for q, _r in scored[:3]) + max(p.score, -2.0) + min(len(scored), 20) * 0.02
        out.append(Found(p, [r for _q, r in scored[:max_hits]], round(score, 2)))
    out.sort(key=lambda f: (-f.score, f.probe.name.lower()))
    return out


# ----------------------------------------------------------------------------------------------------------------
# Meldungen in Klartext (de / en)
# ----------------------------------------------------------------------------------------------------------------
def msg_content_pick(name, count, names, lang="de"):
    return _t(lang,
              f"{count} Einträge aus „{name}“ - erkannt am Inhalt (Namen wie {preview(names)}). Bitte kurz prüfen, ob das Items sind.",
              f"{count} entries from “{name}” - recognised by content (names like {preview(names)}). Please check that these are items.")


def msg_nothing(n_lists, probed, timed_out, kind="table", lang="de"):
    what_de, what_en = (("Tabellen", "tables") if kind == "table" else ("Listen", "lists"))
    if probed:
        de = (f"Keine Item-Liste erkannt: weder am Namen noch am Inhalt von {probed} von {n_lists} {what_de}"
              + (" (Zeitlimit erreicht)" if timed_out else "") + ".")
        en = (f"No item list recognised: neither by name nor by content of {probed} of {n_lists} {what_en}"
              + (" (time limit reached)" if timed_out else "") + ".")
    else:
        de = f"Keine Item-Liste am Namen erkannt ({n_lists} {what_de} geprüft)."
        en = f"No item list recognised by name ({n_lists} {what_en} checked)."
    return _t(lang, de, en)


def msg_next_step(lang="de"):
    return _t(lang,
              "Tipp: Gib unten den Namen eines Items ein, das du im Spiel siehst - ReaperPy sucht ihn in allen Listen. "
              "Oder drücke ALLE LISTEN PRÜFEN.",
              "Tip: enter the name of an item you can see in the game below - ReaperPy searches for it in all lists. "
              "Or press CHECK ALL LISTS.")


def msg_search_found(query, found, others=0, lang="de"):
    f = found
    more = _t(lang, f" Weitere Listen mit Treffern: {others}.", f" Other lists with hits: {others}.") if others else ""
    return _t(lang,
              f"„{query}“ gefunden: {len(f.hits)} Treffer in „{f.probe.name}“ (z. B. {', '.join(f.hits[:3])}). "
              f"Diese Liste ist jetzt ausgewählt.{more}",
              f"“{query}” found: {len(f.hits)} hits in “{f.probe.name}” (e.g. {', '.join(f.hits[:3])}). "
              f"This list is now selected.{more}")


def msg_search_none(query, checked, total, timed_out, lang="de"):
    lim = _t(lang, f" (nur {checked} von {total} geprüft - Zeitlimit)", f" (only {checked} of {total} checked - time limit)") \
        if timed_out else ""
    return _t(lang,
              f"„{query}“ wurde in {checked} Listen nicht gefunden{lim}. Versuche den englischen Namen oder nur einen Teil davon - "
              f"bei übersetzten Spielen weicht der Anzeigename vom internen Namen ab.",
              f"“{query}” was not found in {checked} lists{lim}. Try the English name or just part of it - "
              f"in translated games the display name differs from the internal name.")
