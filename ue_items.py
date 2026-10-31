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


def _extra_params(cls):
    return sum(1 for a in cls if a["role"] == "other")


def give_candidates(prof, sdk):
    """Geben-Funktionen -> (baubar, [(Vorschlag, Grund)]).  baubar: nur Item-Geben mit ID-Parameter
    (XP/Geld ohne Item-ID und Funktionen mit wildfremden Parametern bleiben draussen)."""
    ok, bad = [], []
    for s in prof.of("give_function"):
        title = f"{s.data.get('owner', '')}.{s.data.get('name', s.title)}"
        try:
            cls = CG.classify_params(s.data["params"], sdk)
            CG.check_return(s.data.get("ret"))
        except (TR.TrainerError, KeyError, TypeError) as e:
            bad.append((s, str(e)))
            continue
        if not any(a["role"] == "id" for a in cls):
            bad.append((s, "hat keinen Parameter fuer die Item-ID"))
            continue
        if not ITEM_GIVE.search(title):
            bad.append((s, "kein Item-Geben (Name ohne Item/Inventar/Loot)"))
            continue
        ok.append(s)
    ok.sort(key=lambda s: (_extra_params(CG.classify_params(s.data["params"], sdk)), -s.score))
    return ok, bad


def table_candidates(prof):
    return sorted(prof.of("table"), key=lambda s: -s.score)


ITEM_WORDS = re.compile(r"(?i)item|inventor|loot|weapon|consum|equip|material|resource|gear|armo|tool|food|ingredient|"
                        r"goods|ware|shop|recipe|craft")
TABLE_JUNK = re.compile(r"(?i)enemy|enemies|monster|npc|curve|anim|sound|dialog|dialogue|navmesh|particle|"
                        r"widget|subtitle|levelcurve|expcurve")
ITEM_GIVE = re.compile(r"(?i)item|inventor|loot|pickup|equip|consum|material|resource|weapon|gear")


# ----------------------------------------------------------------------------------------------------------------
# Welche Tabellen / Funktionen sind fuer Items ueberhaupt relevant?  (fuer JEDES Spiel gleich, rein nach Namen + SDK)
# ----------------------------------------------------------------------------------------------------------------
# Wort -> Gewicht.  Gewertet werden die CamelCase-Woerter des Tabellennamens ("DT_ItemParam" -> dt, item, param).
TABLE_PRIMARY = {"item": 6, "weapon": 5, "armor": 5, "armour": 5, "equip": 5, "equipment": 5, "consumable": 5, "goods": 5,
                 "ingredient": 5, "food": 4, "ammo": 4, "accessory": 4, "gear": 4, "resource": 4, "currency": 4,
                 "inventory": 4, "pickup": 4, "artifact": 4, "relic": 4, "potion": 4, "material": 3, "tool": 3, "money": 3,
                 "coin": 3, "gold": 3, "outfit": 3, "costume": 3, "gem": 3, "ware": 3}
TABLE_RELATION = {"loot": 3, "shop": 3, "store": 3, "reward": 3, "recipe": 3, "craft": 3, "treasure": 3, "chest": 3,
                  "merchant": 3, "vendor": 3, "drop": 2.5, "trade": 2, "price": 2}
# Diese Woerter heissen "ist KEINE Item-Liste" (Effekte, Oberflaeche, Sound, Gegner-KI ...)
TABLE_NEGATIVE = {"fx", "vfx", "sfx", "effect", "ui", "hud", "sound", "audio", "bgm", "voice", "text", "string", "locali",
                  "localization", "dialog", "dialogue", "subtitle", "camera", "anim", "animation", "ai", "behavior",
                  "behaviour", "zombie", "enemy", "monster", "npc", "boss", "creature", "character", "quest", "mission",
                  "map", "minimap", "stage", "area", "input", "trigger", "particle", "niagara", "post", "process",
                  "sequence", "cutscene", "movie", "tutorial", "achievement", "trophy", "difficulty", "icon", "image",
                  "texture", "font", "style", "widget", "menu", "model", "view", "skill", "talent", "perk", "spell",
                  "build", "curve", "navmesh", "damage", "hit", "physics", "collision", "weather", "sky", "light", "network", "online",
                  "save", "option", "controller", "gamepad", "haptic", "vibration", "rumble", "tag", "motion", "emote"}
TABLE_FILLER = {"dt", "table", "data", "param", "params", "parameter", "info", "master", "list", "def", "definition",
                "row", "setting", "settings", "common", "base", "datatable", "tbl", "mst", "cfg", "config", "new"}
ROLE_BONUS = {"Items": 4, "Waehrung": 3, "Shop/Preise": 1, "Loot/Drops": 1, "Rezepte/Craft": 1, "Charaktere/Gegner": -3,
              "Skills/Talente": -3, "Quests": -3, "Dialog/Text": -4}
COLUMN_HINT = re.compile(r"(?i)price|cost|stack|weight|rarity|sell|buy|quantity|maxcount|maxnum|durab")
REL_MIN = 3.0                       # ab diesem Wert gilt eine Tabelle als "Item-Tabelle" (und wird angezeigt)


def _tokens(name):
    return [P._stem(w) for w in P.words(name)]


def table_relevance(name, role="", columns=()):
    """Wie sehr sieht diese Tabelle nach einer ITEM-Liste aus?  -> Zahl (>= REL_MIN: ja).  Nur Namen + Zeilenstruct,
    keine spielspezifischen Namen.  'DT_ItemParam' ~ 9, 'DT_FxParam_Player' ~ -8, 'DT_UIMapParam' ~ -8."""
    toks = _tokens(name)
    low = str(name).lower()
    prim = [TABLE_PRIMARY[t] for t in toks if t in TABLE_PRIMARY]
    if not prim:                                    # GROSSGESCHRIEBEN ohne Wortgrenzen ("DT_ITEMPARAM"): Teilwort >= 4 Zeichen
        prim = [w for k, w in TABLE_PRIMARY.items() if len(k) >= 4 and k in low and not [t for t in toks if t in TABLE_NEGATIVE]]
        prim = prim[:1]
    rel = [TABLE_RELATION[t] for t in toks if t in TABLE_RELATION]
    neg = sum(1 for t in toks if t in TABLE_NEGATIVE)
    score = 0.0
    if prim:
        score += max(prim) + 0.5 * (len(prim) - 1)
        if rel:
            score -= 2                              # 'ItemShop', 'ItemDrop': verweist auf Items, ist aber keine Item-Liste
    elif rel:
        score += max(rel)
    rest = [t for t in toks if t not in TABLE_FILLER]
    if len(rest) == 1 and rest[0] in TABLE_PRIMARY:
        score += 3                                  # genau "DT_Item" / "DT_ItemParam" / "DT_Weapon"
    score -= 8 * min(neg, 2)
    score += ROLE_BONUS.get(role, 0)
    cols = [c[0] for c in columns or []]
    score += min(1.5, 0.5 * sum(1 for c in cols if COLUMN_HINT.search(str(c))))
    return round(score, 1)


def rate_tables(cands, live_tables):
    """ALLE Tabellen des laufenden Spiels bewerten -> [{'addr','name','score','relevant','role','sug'}], beste zuerst.
    'sug' ist der passende Zeilenstruct-Vorschlag aus dem SDK (oder None)."""
    best = {}
    for s in cands:
        pick = P.best_table_for(s, live_tables)
        if pick and (pick not in best or s.score > best[pick].score):
            best[pick] = s
    out = []
    for t in live_tables:
        s = best.get(t)
        role = s.data.get("role", "") if s is not None else ""
        score = table_relevance(t[1], role, s.data.get("columns", []) if s is not None else [])
        out.append({"addr": t[0], "name": t[1], "score": score, "relevant": score >= REL_MIN, "role": role, "sug": s})
    out.sort(key=lambda r: (-r["score"], r["name"].lower()))
    return out


def choose_table(cands, live_tables):
    """Tabellen-Vorschlaege -> [(Vorschlag, (addr, name))], beste zuerst; nur Tabellen, die es im laufenden Spiel gibt.
    Nur Item-artige Tabellen (siehe table_relevance); gibt es keine, dann alle nach SDK-Wert (Notlösung)."""
    rated = [r for r in rate_tables(cands, live_tables) if r["sug"] is not None]
    good = [r for r in rated if r["relevant"]]
    if good:
        return [(r["sug"], (r["addr"], r["name"])) for r in good]
    ranked, seen = [], set()
    for s in cands:
        pick = P.best_table_for(s, live_tables)
        if not pick or pick[1] in seen:
            continue
        seen.add(pick[1])
        ranked.append((s.score, s, pick))
    ranked.sort(key=lambda x: -x[0])
    return [(s, pick) for _score, s, pick in ranked]


def order_tables(live_tables):
    """Tabellen fuer die Auswahlliste: nur Item-/Loot-/Shop-Namen; Junk (Gegner, UI, Kurven) raus.
    Gibt es keine Treffer, bleiben alle Tabellen (sortiert, Item-artig zuerst) - sonst waere die Liste leer."""
    hit = [t for t in live_tables if ITEM_WORDS.search(t[1]) and not TABLE_JUNK.search(t[1])]
    src = hit or list(live_tables)
    return sorted(src, key=lambda t: (not ITEM_WORDS.search(t[1]), t[1].lower()))


# --- Geben-Funktionen -------------------------------------------------------------------------------------------
# Wort in Funktionsname -> kein normales "Item geben"
FUNC_NOT_GIVE = {"remove", "delete", "sub", "subtract", "consume", "use", "discard", "sell", "select", "preset", "preview",
                 "show", "display", "can", "check", "has", "is", "get", "find", "query", "try", "on", "when", "update",
                 "refresh", "request", "notify", "register", "clear"}
FUNC_SPECIAL = {"important", "key", "quest", "mission", "story", "event", "tutorial", "mail", "present"}
OWNER_NOT_GAME = {"view", "model", "widget", "ui", "hud", "preview", "display", "viewer", "menu", "window", "slate",
                  "actor"}
BAG_WORDS = {"inventory", "backpack", "bag", "storage", "warehouse", "stash", "pouch"}
SHAPE_TEXT = {"name+menge": "Name + Menge", "id+menge": "Nummer + Menge", "klasse+menge": "Klasse + Menge",
              "name": "nur Name", "id": "nur Nummer", "name+zahl": "Name + Zahl"}


def func_key(sug):
    """Schluessel einer Geben-Funktion fuer 'getestet' (Klasse.Funktion)."""
    d = sug.data
    return f"{d.get('owner', '')}.{d.get('name', sug.title)}"


def rate_functions(prof, sdk, verified=None):
    """Baubare Geben-Funktionen bewerten -> [{'sug','score','reach','relevant','reasons'}], beste zuerst.
    reach: 'hooked' | 'member' | 'zero' - woher die Cave das Objekt (this) nimmt.  'zero' = die Funktion gehoert zu einer
    Klasse, deren Instanz der Trainer nicht erreicht (z. B. Subsystem): sie wird mit this=0 gerufen -> meist wirkungslos.
    relevant: erreichbar UND sieht nach 'Item geben' aus (kein Entfernen/Auswaehlen/Vorschau/Schluessel-Item).
    verified: {Klasse.Funktion: 'ok' | 'fail'} - Ergebnis des Tests '1 Item geben' (ok: +4, fail: -8)."""
    verified = verified or {}
    ok, _bad = give_candidates(prof, sdk)
    out = []
    for s in ok:
        d = s.data
        fw, ow = set(_tokens(d.get("name", ""))), set(_tokens(d.get("owner", "")))
        mode, _off, _note = CG.choose_this(sdk, d.get("owner", ""))
        score, reasons = float(s.score), []
        if mode == "zero":
            score -= 5
            reasons.append("Objekt nicht erreichbar")
        else:
            score += 3 if mode == "hooked" else 2.5
        bad_name = bool(fw & FUNC_NOT_GIVE)
        bad_owner = bool(ow & OWNER_NOT_GAME)
        special = bool(fw & FUNC_SPECIAL)
        if (fw | ow) & BAG_WORDS:
            score += 1.5                                # BackPack/Inventory/Bag im Namen: das ist das Inventar
        if bad_name:
            score -= 10
            reasons.append("kein normales Item-Geben")
        if bad_owner:
            score -= 8
            reasons.append("gehoert zur Anzeige")
        if special:
            score -= 3
            reasons.append("Spezial-Items")
        state = verified.get(func_key(s), "")
        if state == "ok":
            score += 4
        elif state == "fail":
            score -= 8
            reasons.append("Test fehlgeschlagen")
        out.append({"sug": s, "score": round(score, 1), "reach": mode, "reasons": reasons, "verified": state,
                    "relevant": mode != "zero" and not (bad_name or bad_owner or special or state == "fail")})
    out.sort(key=lambda r: -r["score"])
    return out


def function_label(rated):
    """Anzeigetext einer bewerteten Funktion: 'Klasse.Funktion (Name + Menge)'."""
    d = rated["sug"].data
    shape = SHAPE_TEXT.get(d.get("shape", ""), "")
    return (f"{d.get('owner', '')}.{d.get('name', rated['sug'].title)}" + (f"  [{shape}]" if shape else "")
            + ("  ✔ getestet" if rated.get("verified") == "ok" else ""))


# ----------------------------------------------------------------------------------------------------------------
# Test: EIN Item live geben (ProcessEvent auf der echten Instanz) - zeigt, ob die Funktion im Spiel wirkt
# ----------------------------------------------------------------------------------------------------------------
FUNC_STATIC = 0x2000


def test_assignments(func, fp, item, amount, sdk):
    """Parameter fuer ue_call.encode_params: ID-Parameter = das Item, Mengen-Parameter = amount, alles andere 0."""
    cls = CG.classify_params(func.data["params"], sdk)
    names = {p.name for p in fp.params}
    out, used_id = {}, False
    for a in cls:
        if a["name"] not in names:
            continue
        if a["role"] == "id":
            if used_id:
                continue                                       # weitere ID-Parameter (z. B. WorkId) bleiben leer = None / 0
            used_id = True
            if a["kind"] == "fname":
                out[a["name"]] = "hex:" + bytes(item["fname"]).hex()
            elif item.get("id") is None:
                raise ValueError("Dieses Item hat keine Zahlen-ID - mit einem anderen Item testen")
            else:
                out[a["name"]] = str(int(item["id"]))
        elif a["role"] == "count":
            out[a["name"]] = str(amount)
    if not used_id:
        raise ValueError("Die Funktion hat keinen Parameter fuer die Item-ID")
    return out


def call_report(fp, assign, outs, instance, found):
    """Textzeilen fuers Protokoll: was wurde WOHIN gerufen, mit welchen Bytes, was kam zurueck."""
    import ue_call
    buf = ue_call.encode_params(fp, assign)
    lines = [f"   Objekt: {instance.get('name', '?')} @ {instance.get('addr', 0):#x} ({instance.get('class', '?')}), "
             f"{len(found)} Objekt(e) dieser Klasse im Spiel"]
    if len(found) > 1:
        lines.append("   weitere: " + ", ".join(f"{i.get('name', '?')}" for i in found[1:5]))
    for p in fp.params:
        kind = "Rueckgabe" if p.pflags & 0x400 else ("Ausgabe" if p.pflags & 0x100 else "Eingabe")
        raw = bytes(buf[p.offset:p.offset + p.size]).hex(" ")
        lines.append(f"   {kind}: {p.name} ({p.type}) @+{p.offset:#x} = {raw}")
    for k, v in outs:
        lines.append(f"   Ergebnis {k} = {v}")
    return lines


def returned_false(fp, outs):
    """True, wenn die Funktion ein bool zurueckgibt und 'false' meldet (= Spiel hat das Item abgelehnt)."""
    ret = next((p for p in fp.params if p.pflags & 0x400), None)
    if ret is None or P.base_name(ret.type) != "bool":
        return False
    return any(k == "ReturnValue" and str(v).strip() == "0" for k, v in outs)


def _prepare_call(live, client, sdk, func, base):
    """Alles, was fuer den Live-Aufruf noetig ist -> (fp, ufunction, [Instanzen], ProcessEvent-Adresse)."""
    import ue_call
    d = func.data
    sdk.load_params()
    fp = sdk.params_for(d["owner"], d["name"])
    if fp is None:
        raise ValueError("Kein Parameter-Layout fuer diese Funktion gefunden (…_parameters.hpp im SDK-Ordner?)")
    if live.index is None:
        live.build_index()
    function = live.find_function(d["owner"], d["name"])
    if not function:
        raise ValueError("Die Funktion wurde im laufenden Spiel nicht gefunden (Klasse nicht geladen?)")
    if d.get("flags", 0) & FUNC_STATIC:
        obj = live.default_object(d["owner"])
        found = [{"addr": obj, "name": "Default__" + d["owner"], "class": d["owner"]}] if obj else []
    else:
        found = [i for i in live.instances(d["owner"]) if "Default__" not in i["name"]]
    if not found:
        raise ValueError(f"Im Spiel gibt es kein Objekt der Klasse {d['owner']} - Spielstand laden (nicht im Hauptmenue) "
                         "und es erneut versuchen")
    pidx = sdk.offset("process_event_index", "processeventindex", default=77)
    prva = sdk.offset("process_event")
    pe = ue_call.process_event_addr(client.read_memory, found[0]["addr"], pidx, fallback=(base + prva) if prva else None)
    return fp, function, found, pe


def try_give(live, client, sdk, func, item, base, amount=1, caller=None):
    """EIN Item ueber die Funktion in einer ECHTEN Instanz des laufenden Spiels geben (nicht ueber die Cave).
    -> {'instance', 'instances', 'outs', 'returned_false', 'reach'}.  Wirft ValueError mit verstaendlichem Text."""
    import ue_call
    d = func.data
    fp, function, found, pe = _prepare_call(live, client, sdk, func, base)
    obj = found[0]["addr"]
    assign = test_assignments(func, fp, item, amount, sdk)
    outs = ue_call.call_ufunction(client, obj, function, fp, assign, pe, caller)
    mode, _off, _note = CG.choose_this(sdk, d["owner"])
    return {"instance": obj, "instances": len(found), "outs": outs, "returned_false": returned_false(fp, outs),
            "reach": mode, "detail": call_report(fp, assign, outs, found[0], found)}


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
    extra = {a["name"]: (1 if a["kind"] == "int" and re.search(r"(?i)notify|show|message|bshow", a["name"]) else 0)
             for a in cls if a["role"] == "other" and a["kind"] != "ptr"}
    options, skipped = [], 0
    first_id = True
    for a in cls:                                   # weitere FName-IDs (z. B. WorkId): leer (None) lassen statt Fehler "FName fehlt"
        if a["role"] == "id":
            if not first_id and a["kind"] == "fname":
                extra.setdefault(a["name"], bytes(8))
            first_id = False
    for name, items in pkgs:
        ok, bad = usable(items, ida["kind"])
        skipped += len(bad)
        if not ok:
            continue
        rows = [CG.build_row(TR.clean_name(i["name"]), impl - base, d["params"], d.get("ret"), sdk, (mode, off),
                             id_value=(i["fname"] if ida["kind"] == "fname" else i["id"]), count_value=amount,
                             extra=extra, byref=byref, function=fname_of) for i in ok]
        options.append(TR.Option(name, rows))
    return options, skipped


def project_dirs(base_dir, n, name="Items"):
    """Ordnernamen der Projekte: eins -> '<name>', mehrere -> '<name> 1', '<name> 2' ..."""
    import os
    if n <= 1:
        return [os.path.join(base_dir, name)]
    return [os.path.join(base_dir, f"{name} {k + 1}") for k in range(n)]


def give_many(live, client, sdk, func, items, base, amount, progress=None, caller=None):
    """Alle `items` hintereinander live geben (ein ProcessEvent-Aufruf je Item, wie try_give; ohne Trainer/Cave).
    -> {'total', 'given', 'rejected': [Name], 'skipped': [Name], 'instance'}.  Bricht bei einem Fehler im Spiel ab (ValueError/OSError)."""
    import ue_call
    fp, function, found, pe = _prepare_call(live, client, sdk, func, base)
    obj = found[0]["addr"]
    given, rejected, skipped = 0, [], []
    for n, item in enumerate(items):
        try:
            assign = test_assignments(func, fp, item, amount, sdk)
        except ValueError:
            skipped.append(item["name"])                           # Item ohne Zahlen-ID
            continue
        outs = ue_call.call_ufunction(client, obj, function, fp, assign, pe, caller)
        if returned_false(fp, outs):
            rejected.append(item["name"])
        else:
            given += 1
        if progress:
            progress(n + 1, len(items))
    return {"total": len(items), "given": given, "rejected": rejected, "skipped": skipped, "instance": obj}
