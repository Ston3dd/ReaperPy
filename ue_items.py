"""ue_items.py - Items finden und als Trainer bauen, fuer JEDES Unreal-Spiel in drei Klicks (Logik ohne Oberflaeche).

Der Weg im Tab ITEMS:  Spiel laden  ->  ITEMS FINDEN  ->  TRAINER SPEICHERN
  * ITEMS FINDEN   waehlt selbst die beste Geben-Funktion (die der Cave-Trainer bauen kann) und die passende Item-Tabelle,
                   liest die Tabelle live und teilt die Items nach Kategorie ein.
  * TRAINER        alle gehakten Items, je Kategorie in 14er-Paketen ("Fische 1", "Fische 2" ...); sind es mehr als in ein
                   Projekt passen (cave_trainer.MAX_ROWS), entstehen mehrere Projekte.

Alles hier ist rein rechnerisch bzw. bekommt read()/Live-Objekte uebergeben -> ohne Konsole testbar (tests/test_ue_items.py).
Die Cave selbst baut cave_trainer.py / ue_cavegen.py, die Tabelle liest ue_profile.py.
"""
import re
from collections import OrderedDict

import cave_trainer as TR
import ue_cavegen as CG
import ue_profile as P

OTHER = "Sonstiges"                 # Sammelkategorie fuer Items ohne erkennbare Gruppe
ALL = "Alle"                        # wenn gar keine Einteilung gefunden wird
MAX_CATEGORIES = 60
SKIP_WORDS = {"item", "items", "dt", "row", "rows", "data", "it", "itm", "id", "none", "default", "new", "the"}
CAT_COLUMN = re.compile(r"(?i)categor|item.?type|item.?kind|item.?class|item.?group|inventory.?type|bag.?type|"
                        r"^(type|kind|group|class|family)$")


# ----------------------------------------------------------------------------------------------------------------
# 1) Welche Funktion / welche Tabelle?
# ----------------------------------------------------------------------------------------------------------------
def id_param(suggestion, sdk):
    """Der ID-Parameter einer Geben-Funktion ('fname' | 'int') oder None."""
    cls = CG.classify_params(suggestion.data["params"], sdk)
    for a in cls:
        if a["role"] == "id":
            return a
    return None


def give_candidates(prof, sdk):
    """Geben-Funktionen -> (baubar, [(Vorschlag, Grund)]).  baubar: nach Wert sortiert, nur mit ID-Parameter
    (eine Funktion ohne Item-ID taugt nicht fuer eine Item-Liste)."""
    ok, bad = [], []
    for s in prof.of("give_function"):
        try:
            cls = CG.classify_params(s.data["params"], sdk)
            CG.check_return(s.data.get("ret"))
        except (TR.TrainerError, KeyError, TypeError) as e:
            bad.append((s, str(e)))
            continue
        if any(a["role"] == "id" for a in cls):
            ok.append(s)
        else:
            bad.append((s, "hat keinen Parameter fuer die Item-ID"))
    ok.sort(key=lambda s: -s.score)
    return ok, bad


def table_candidates(prof):
    return sorted(prof.of("table"), key=lambda s: -s.score)


ITEM_WORDS = re.compile(r"(?i)item|inventor|loot|weapon|consum|equip|material|resource|gear|armo|tool|food|ingredient")


def choose_table(cands, live_tables):
    """Tabellen-Vorschlaege -> [(Vorschlag, (addr, name))], beste zuerst; nur Tabellen, die es im laufenden Spiel gibt.
    Namen mit Item/Inventory/Loot/Weapon ... werden bevorzugt (Gegner-/Level-Tabellen sind meist nicht gemeint)."""
    ranked, seen = [], set()
    for s in cands:
        pick = P.best_table_for(s, live_tables)
        if not pick or pick[1] in seen:
            continue
        seen.add(pick[1])
        bonus = 3 if ITEM_WORDS.search(f"{pick[1]} {s.data.get('row_struct') or s.title}") else 0
        ranked.append((s.score + bonus, s, pick))
    ranked.sort(key=lambda x: -x[0])
    return [(s, pick) for _score, s, pick in ranked]


def order_tables(live_tables):
    """Alle Tabellen des Spiels fuer die Auswahlliste: Item-artige Namen zuerst."""
    return sorted(live_tables, key=lambda t: (not ITEM_WORDS.search(t[1]), t[1].lower()))


def row_number_id(row):
    """Zahlen-ID aus einer Tabellenzeile (erste ID-artige Ganzzahl-Spalte) oder None."""
    for k, v in row.get("values", {}).items():
        if P.ID_NAME.search(str(k)) and isinstance(v, int) and not isinstance(v, bool):
            return v
    return None


# ----------------------------------------------------------------------------------------------------------------
# 2) Items aus den Tabellenzeilen + Kategorien
# ----------------------------------------------------------------------------------------------------------------
def _camel_words(token):
    return re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", token)


def _tidy(label):
    s = str(label).split("::")[-1].strip().replace("_", " ")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return (s[:1].upper() + s[1:])[:30] or OTHER


def name_prefix(name):
    """'Item_Fish_Trout' -> 'Fish', 'DT_Weapon_Sword' -> 'Weapon', 'FishTrout' -> 'Fish', sonst None."""
    toks = [t for t in re.split(r"[_.\-\s]+", str(name)) if t]
    while toks and toks[0].lower() in SKIP_WORDS:
        toks.pop(0)
    if len(toks) < 2:                               # nur ein Wort uebrig: CamelCase pruefen ('FishTrout')
        words = _camel_words(toks[0]) if toks else []
        words = [w for w in words if w.lower() not in SKIP_WORDS]
        if len(words) < 2:
            return None
        toks = words
    first = toks[0]
    if first.isdigit() or len(first) < 2:
        return None
    return _tidy(first)


def _category_column(rows, cols):
    """Spalte, die die Items in 2..MAX_CATEGORIES Gruppen teilt (Kategorie/Typ) -> Spaltenname oder None."""
    best = None
    for c in cols or []:
        name = c[0]
        if not CAT_COLUMN.search(str(name)):
            continue
        vals = [r["values"].get(name) for r in rows if name in r.get("values", {})]
        vals = [v for v in vals if v not in (None, "", "?") and not isinstance(v, bool)]
        distinct = len(set(vals))
        if len(vals) >= max(2, len(rows) // 2) and 2 <= distinct <= MAX_CATEGORIES:
            if best is None or distinct > best[1]:
                best = (name, distinct)
    return best[0] if best else None


def _item(row, category):
    return {"name": row["name"], "fname": bytes.fromhex(row["fname_hex"]), "id": row_number_id(row),
            "category": category}


def build_items(rows, cols=None):
    """Tabellenzeilen -> [Item], jedes mit 'category'.  Einteilung: Kategorie-Spalte, sonst Namens-Vorsilbe, sonst alle in 'Alle'."""
    rows = [r for r in rows if str(r.get("name", "")).strip() and str(r["name"]).lower() not in ("none", "null")]
    col = _category_column(rows, cols)
    if col:
        out = []
        for r in rows:
            v = r["values"].get(col)
            if isinstance(v, int) and not isinstance(v, bool):
                lab = f"{_tidy(col)} {v}"
            else:
                lab = _tidy(v) if v not in (None, "", "?") else OTHER
            out.append(_item(r, lab))
        return out
    pref = [name_prefix(r["name"]) for r in rows]
    counts = {}
    for p in pref:
        if p:
            counts[p] = counts.get(p, 0) + 1
    groups = {p for p, n in counts.items() if n >= 2}
    covered = sum(n for p, n in counts.items() if p in groups)
    if 2 <= len(groups) <= MAX_CATEGORIES and rows and covered >= 0.6 * len(rows):
        return [_item(r, p if p in groups else OTHER) for r, p in zip(rows, pref)]
    return [_item(r, ALL) for r in rows]


def group_items(items):
    """-> OrderedDict {Kategorie: [Item]} (alphabetisch, 'Sonstiges' zuletzt)."""
    g = {}
    for it in items:
        g.setdefault(it["category"], []).append(it)
    keys = sorted(g, key=lambda k: (k == OTHER, k.lower()))
    return OrderedDict((k, g[k]) for k in keys)


# ----------------------------------------------------------------------------------------------------------------
# 3) Pakete und Projekte
# ----------------------------------------------------------------------------------------------------------------
def packages(groups, size=TR.PACK_SIZE):
    """{Kategorie: [Item]} -> [(Eintragsname, [Item])]; Namen wie cave_trainer.split_package ('Fische' oder 'Fische 1', 'Fische 2')."""
    out, used = [], set()
    for cat, items in groups.items():
        base = TR.clean_name(cat)
        n = 2
        while base.lower() in used or (len(items) > size and f"{base} 1".lower() in used):
            base = f"{TR.clean_name(cat)} ({n})"
            n += 1
        used.add(base.lower())
        if len(items) <= size:
            out.append((base, list(items)))
            continue
        for k, i in enumerate(range(0, len(items), size)):
            used.add(f"{base} {k + 1}".lower())
            out.append((f"{base} {k + 1}", items[i:i + size]))
    return out


ROW_COST = 48                       # Schaetzung: so viele Byte Cave je Item-Zeile (fuer die Vorschau; gebaut wird exakt)


def rows_per_project(code_capacity):
    """Wie viele Items passen ungefaehr in eine Cave dieser Groesse (Vorschau; die echte Aufteilung nutzt cave_size)."""
    if not code_capacity:
        return TR.MAX_ROWS
    return max(1, min(TR.MAX_ROWS, (code_capacity - 160) // ROW_COST))


def split_projects(pkgs, max_rows=TR.MAX_ROWS, max_options=TR.MAX_OPTIONS):
    """Pakete der Reihe nach auf Projekte verteilen: keins ueberschreitet max_rows Items oder max_options Eintraege."""
    projects, cur, rows = [], [], 0
    for name, items in pkgs:
        if cur and (rows + len(items) > max_rows or len(cur) + 1 > max_options):
            projects.append(cur)
            cur, rows = [], 0
        cur.append((name, items))
        rows += len(items)
    if cur:
        projects.append(cur)
    return projects


# ----------------------------------------------------------------------------------------------------------------
# 4) Trainer bauen
# ----------------------------------------------------------------------------------------------------------------
def usable(items, id_kind):
    """Items, fuer die der ID-Parameter einen Wert hat -> (brauchbar, uebersprungen).  FName: immer (8 Byte aus der Tabelle);
    Zahlen-ID: nur Zeilen mit ID-Spalte."""
    if id_kind == "fname":
        return list(items), []
    ok = [i for i in items if i["id"] is not None]
    return ok, [i for i in items if i["id"] is None]


def hook_targets(sdk, live, read, base):
    """Nur LESEN: ProcessEvent-Adresse + vtable-Slots der PlayerController -> (pe, slots, notizen)."""
    import ue_call
    import ue_hook as HK
    pidx = sdk.offset("process_event_index", "processeventindex", default=77)
    prva = sdk.offset("process_event")
    objs = []
    try:
        objs = [i["addr"] for i in live.instances("APlayerController") if "Default__" not in i["name"]]
    except Exception:  # noqa: BLE001
        pass
    if not objs:
        raise ValueError("Kein PlayerController gefunden - Spielstand laden (nicht im Hauptmenue)")
    pe = ue_call.process_event_addr(read, objs[0], pidx, fallback=(base + prva) if prva else None)
    slots, notes = HK.find_slots(read, objs, pidx, pe)
    return pe, slots, notes


def make_options(pkgs, func, sdk, live, read, base, amount, log=lambda _m: None):
    """Pakete -> [Option] mit je einer Aufruf-Zeile je Item (Geben-Funktion aus dem Spiel)."""
    d = func.data
    cls = CG.classify_params(d["params"], sdk)
    CG.check_return(d.get("ret"))
    ida = next(a for a in cls if a["role"] == "id")
    fl = any(a["role"] == "count" and a["kind"] in ("float", "double") for a in cls)
    amount = float(amount) if fl else int(amount)
    ent = live.function_entry(d["owner"], d["name"])
    if not ent:
        raise ValueError(f"{d['owner']}.{d['name']} wurde im laufenden Spiel nicht gefunden")
    impl = CG.find_impl(read, base, ent[0])
    if impl is None:
        raise ValueError("Die native Implementierung der Geben-Funktion wurde nicht erkannt (Blueprint-Funktion oder "
                         "ungewohnter Thunk) - dafuer laesst sich keine feste Cave bauen.")
    mode, off, note = CG.choose_this(sdk, d["owner"])
    log("this: " + note)
    byref = [a["name"] for a in cls if a["kind"] == "fname" and a.get("ref")]
    fname_of = f"{d['owner']}.{d['name']}"
    options, skipped = [], 0
    for name, items in pkgs:
        ok, bad = usable(items, ida["kind"])
        skipped += len(bad)
        if not ok:
            continue
        rows = [CG.build_row(TR.clean_name(i["name"]), impl - base, d["params"], d.get("ret"), sdk, (mode, off),
                             id_value=(i["fname"] if ida["kind"] == "fname" else i["id"]), count_value=amount,
                             byref=byref, function=fname_of) for i in ok]
        options.append(TR.Option(name, rows))
    return options, skipped


def project_dirs(base_dir, n, name="Items"):
    """Ordnernamen der Projekte: eins -> '<name>', mehrere -> '<name> 1', '<name> 2' ..."""
    import os
    if n <= 1:
        return [os.path.join(base_dir, name)]
    return [os.path.join(base_dir, f"{name} {k + 1}") for k in range(n)]
