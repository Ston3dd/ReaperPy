"""values_auto.py - Leben, Ausdauer, Gold, Erfahrung, Munition ... als DIREKTE Patches (ohne GUI, testbar).

Unreal Engine: Die Eintraege kommen aus dem Cheat-Menue (cheatmenu.CheatMenu: Kandidaten aus dem SDK, an der Spielfigur
               geprueft).  Fuer jeden gehakten Eintrag wird der Spiel-Code nach den schreibenden Instruktionen durchsucht und
               die passende Cave gebaut (cheatmenu_cave): Zahlen 'kann nicht sinken', Erfahrung 'festschreiben' (hoher Wert).
Unity (IL2CPP): Aus dump.cs werden Methoden nach ihrem Namen erkannt (TakeDamage, SpendMoney, UseStamina, UseAmmo,
               ExpToNextLevel ...) und mit einem festen Rueckgabewert bzw. leer gepatcht (il2cpp_dump.make_patch).

Die Namenserkennung ist eine Heuristik: jede Zeile zeigt in einfachen Worten, WAS passiert; gepatcht wird nur, was
angehakt ist.  Patches gelten fuer alle Objekte, die diesen Code benutzen (auch Gegner) - bei Unity wird das pro Zeile
angezeigt, wenn der Klassenname nach Gegner aussieht.
"""
import re
from collections import OrderedDict, namedtuple

import cheatmenu_cave as CV
import il2cpp_dump as D

XP_CATEGORY = "Erfahrung/Level"
XP_DEFAULT = "99999"
UNITY_PER_CAT = 6
CATEGORY_ORDER = ["Leben", "Ausdauer", "Mana/Energie", "Schild/Rüstung", "Munition", "Geld", XP_CATEGORY, "Schalter",
                  "Cooldown", "Sonstiges"]

# ------------------------------------------------------------------------------------------------------------------
# Unity: Methoden nach Namen erkennen
# ------------------------------------------------------------------------------------------------------------------
Rule = namedtuple("Rule", "cat pattern void_noop bool_value int_value")
_CUR = r"(money|gold|coins?|cash|currency|gems?|credits?|souls?|funds|bolts|silver|diamonds?)"
_SPEND = r"(spend|remove|subtract|deduct|pay|consume|use|take|lose|withdraw|decrease|reduce)"
RULES = [
    Rule("Leben", r"(take|receive|apply|deal|inflict|suffer)?damage(taken)?|(on)?(take|receive|get)(hit|damage)|hurt|"
                  r"(lose|reduce|decrease|subtract|remove|deplete)(health|hp|life|lives)", True, None, None),
    Rule("Leben", r"is(dead|dying|knockedout|downed)", False, "false", None),
    Rule("Leben", r"is(alive|invincible|invulnerable|immortal)|godmode", False, "true", None),
    Rule("Geld", _SPEND + _CUR, True, "true", None),
    Rule("Geld", r"(can|has)(afford|enough" + _CUR + r"?|money|gold)|canbuy|canpay", False, "true", None),
    Rule("Ausdauer", r"(use|consume|drain|reduce|spend|decrease|deplete|lose)(stamina|sprint|focus|fuel|oxygen|breath)",
         True, "true", None),
    Rule("Ausdauer", r"(has|can)(stamina|enoughstamina|sprint|run)", False, "true", None),
    Rule("Mana/Energie", r"(use|consume|drain|reduce|spend|decrease|deplete|lose)(mana|energy|magic|power)", True, "true", None),
    Rule("Munition", r"(use|consume|reduce|decrease|spend|remove|deplete)(ammo|ammunition|bullets?|arrows?|rounds?|"
                     r"charges?|clip)", True, "true", None),
    Rule("Munition", r"(has|have)(ammo|ammunition|bullets?)|canshoot|canfire", False, "true", None),
    Rule(XP_CATEGORY, r"(required|needed|next|nextlevel)(level)?(exp|experience|xp)(tolevel|tonext|fornext|forlevel)?|"
                      r"(exp|experience|xp)(to|for|needed|required)(next)?(level|levelup)?|"
                      r"(getexp|getxp)(for|to)(next)?level", False, None, 1),
]
_COMPILED = [(r, re.compile(r"^(?:" + r.pattern + r")$")) for r in RULES]
PLAYERISH = re.compile(r"(?i)player|hero|character|avatar|local|protagonist|main|vitals|stats|wallet|inventory")
ENEMYISH = re.compile(r"(?i)enemy|enemies|monster|boss|npc|mob\b|ai\b|zombie|minion|creep|hostile|foe")

Candidate = namedtuple("Candidate", "key cat label method mode value effect score warn default_on")


def _core(name):
    """'get_ExpToNextLevel' -> 'exptonextlevel' (Property-Getter ohne get_, klein, ohne Unterstriche)."""
    n = name[4:] if name.startswith("get_") else name
    return n.replace("_", "").lower()


def _effect(mode, value):
    return {"noop": "Methode leer machen (tut nichts)", "true": "liefert immer 'ja'", "false": "liefert immer 'nein'",
            "value": f"liefert immer {value}"}[mode]


def _action(rule, m):
    """-> (mode, value) oder None, je nach Rueckgabetyp der Methode."""
    prim = D.PRIMS.get(m.ret)
    if m.ret == "void":
        return ("noop", None) if rule.void_noop else None
    if prim == "bool":
        return (rule.bool_value, None) if rule.bool_value else None
    if prim in ("int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64") and rule.int_value is not None:
        return "value", rule.int_value
    return None


def find_unity_candidates(game, per_cat=UNITY_PER_CAT):
    """Wichtige Methoden des Spiels -> [Candidate], je Kategorie die besten zuerst."""
    found = {}
    for m in game.all_methods():
        if m.rva <= 0 or m.name.startswith((".", "<")) or m.name in ("MoveNext", "Finalize") or m.cls is None:
            continue
        if D.is_generated(m.cls):
            continue
        core = _core(m.name)
        for rule, rx in _COMPILED:
            if not rx.match(core):
                continue
            act = _action(rule, m)
            if act is None:
                break
            mode, value = act
            try:
                D.make_patch(m, mode, value)
            except (ValueError, TypeError):
                break
            cls = m.cls.full
            enemy = bool(ENEMYISH.search(cls))
            score = 10 + (5 if (m.cls.image or "").startswith("Assembly-CSharp") else 0) \
                + (4 if PLAYERISH.search(cls) else 0) - (6 if enemy else 0) - min(m.n_params, 3) + (1 if not m.static else 0)
            warn = "Klassenname sieht nach Gegner aus - würde auch Gegner betreffen" if enemy else ""
            key = f"{cls}.{m.name}@{m.rva:x}"
            found.setdefault(rule.cat, []).append(
                Candidate(key, rule.cat, f"{cls}.{m.name}", m, mode, value, _effect(mode, value), score, warn, False))
            break
    out = []
    for cat in CATEGORY_ORDER:
        lst = sorted(found.get(cat, []), key=lambda c: (-c.score, c.label))[:per_cat]
        for i, c in enumerate(lst):
            out.append(c._replace(default_on=i < 2 and not c.warn and c.score >= 14))
    return out


def unity_patch_doc(c, module_base, read, author="ReaperPy Werte"):
    """Candidate -> Patch-Dokument (.reapproj).  Liest die Original-Bytes LIVE; "Verify": true schuetzt vor anderen Versionen.
    Wirft ValueError mit verstaendlichem Grund."""
    m = c.method
    new = D.make_patch(m, c.mode, c.value)
    orig = bytes(read(module_base + m.rva, len(new)))
    if orig == new or orig[:1] == b"\xc3":
        raise ValueError(f"{c.label}: Die Methode ist im Spiel schon gepatcht/leer (erst alle Patches ausschalten, dann "
                         "neu bauen - sonst sind die Original-Bytes unbekannt)")
    doc = D.reapproj_for_patch(f"{c.cat}: {m.cls.name}.{m.name} - {c.effect}", m.rva, orig, new, author=author,
                               info=f"Unity/IL2CPP: {m.sig}  RVA {m.rva:#x} im IL2CPP-Modul. Image-Basis = IL2CPP-Modul-Basis "
                                    f"({module_base:#x}).")
    doc["Verify"] = True
    return doc


# ------------------------------------------------------------------------------------------------------------------
# Unreal: Cheat-Menue-Eintraege -> Caves
# ------------------------------------------------------------------------------------------------------------------
def ue_entries(menu):
    """Spielspezifische Eintraege, die an der Spielfigur erreichbar sind (Leben, Ausdauer, Geld, Erfahrung ...)."""
    return [e for e in menu.entries if e.source == "spiel" and e.ok and not e.hidden]


# Wert, der bei 'festschreiben' eingesetzt wird, wenn kein 'kann nicht sinken' / NOP moeglich ist (Zahl, nie 'auto')
FORCE_DEFAULTS = {"Leben": "9999", "Ausdauer": "9999", "Mana/Energie": "9999", "Schild/Rüstung": "9999",
                  "Munition": "999", "Geld": "999999"}
SUBTRACT = ("sub", "dec")           # schreibende Abzieh-Befehle: abschalten = 'wird nicht weniger'


def ue_pick(e, opts, xp_value=XP_DEFAULT):
    """Beste baubare Cave -> (Option, mode, value) oder (None, None, None).
    Reihenfolge bei Zahlen: 1. 'Wert kann nicht sinken' (Cave), 2. den Abzieh-Befehl (sub/dec) abschalten (NOP: Munition und
    Gold sinken nicht mehr, Aufnehmen bleibt moeglich), 3. 'festschreiben' mit einer festen Zahl.  Erfahrung: festschreiben
    mit hohem Wert (Level-Up).  Schalter: festschreiben."""
    if e.cat == XP_CATEGORY:
        for o in opts:
            if o.modes.get("force", (False, ""))[0]:
                return o, "force", str(xp_value)
    if e.kind != "value":
        opt, mode = CV.pick_best(e, opts)
        return (opt, mode, CV.entry_value(e)) if opt is not None else (None, None, None)
    for o in opts:
        if o.modes["keep"][0]:
            return o, "keep", ""
    for o in opts:
        if getattr(o.hit.ins, "mnem", "") in SUBTRACT and o.modes["nop"][0]:
            return o, "nop", ""
    for o in opts:
        if o.modes["force"][0]:
            return o, "force", FORCE_DEFAULTS.get(e.cat, "999")
    return None, None, None


def build_ue_patches(menu, entries, code, dis, out_dir, xp_value=XP_DEFAULT, log=lambda _m: None, progress=None):
    """Fuer jeden Eintrag die Cave bauen und als .reapproj in out_dir ablegen.
    -> (gebaut [dict(entry, mode, file, rva, name)], fehlgeschlagen [(entry, Grund)])"""
    done, failed = [], []
    for i, e in enumerate(entries):
        try:
            opts = CV.find_options(menu, e, code, dis, progress=None)
            if not opts:
                failed.append((e, "keine Schreibzugriffe auf diesen Wert im Spiel-Code gefunden"))
                continue
            opt, mode, value = ue_pick(e, opts, xp_value)
            if opt is None:
                failed.append((e, f"{len(opts)} Treffer, aber keine passende Cave baubar"))
                continue
            patch = CV.build_patch(e, opt, mode, code, dis, value=value or None, log=log)
            fn = CV.save_patch(out_dir, patch)
            done.append({"entry": e, "mode": mode, "file": fn, "rva": opt.hit.rva, "name": patch["name"]})
        except Exception as ex:  # noqa: BLE001 - ein Eintrag darf die anderen nicht stoppen
            failed.append((e, str(ex) or ex.__class__.__name__))
        if progress:
            progress(i + 1, len(entries))
    return done, failed


def group_by_category(items, cat_of):
    """Reihenfolge der Kategorien wie in CATEGORY_ORDER, unbekannte danach."""
    g = OrderedDict()
    for it in items:
        g.setdefault(cat_of(it), []).append(it)
    keys = sorted(g, key=lambda k: (CATEGORY_ORDER.index(k) if k in CATEGORY_ORDER else 99, k))
    return OrderedDict((k, g[k]) for k in keys)
