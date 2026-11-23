"""smart_find.py - INTELLIGENTES Finden nuetzlicher Dinge (Leben, Geld, Munition, Items, Cheat-Schalter ...) in Unity UND Unreal.

Warum es das gibt:  Die bisherigen Erkennungen vergleichen Namen mit festen ENGLISCHEN Woertern (``take|receive...damage``,
``money|gold|coins``).  Das scheitert bei vielen Spielen:

  * andere Sprache / Romaji / Pinyin    (``Kinsen``, ``Okane``, ``Vida``, ``Munition``, ``Zidan``, ``Xueliang``)
  * Abkuerzungen                        (``m_Hp``, ``curMp``, ``Gld``, ``Stam``, ``Mny``)
  * Tippfehler / Schreibweisen          (``Immotal``, ``Ammunitions``, ``Healt``)
  * der Name steckt in der KLASSE       (``Wallet.Pay(int)``, ``Purse.Take(int)``, ``Vitals.Hit(float)``)
  * die Methode ist nur an ihrer Form erkennbar (Geschwister: ``Remove(ItemID,int)`` + ``Xyz(ItemID,int)`` -> Xyz gibt wohl)
  * verschleierte Namen                 (dann sagt das Modul ehrlich: Namenssuche geht nicht - und was stattdessen hilft)

Was hier steht (alles rein rechnerisch, ohne Konsole und ohne Oberflaeche - tests/test_smart_find.py):

  tokens(name)                 'm_curHP' / 'PlayerHealthMax' / 'kinsen_2' -> ['cur','hp'] ...  (camelCase, snake_case, Praefixe weg)
  concepts_of(name)            Name -> [Treffer(Konzept, Rolle, Sicherheit, Grund)]   (mehrsprachig, Abkuerzung, unscharf)
  fuzzy_hits(woerter, keywords) Ersatz fuer ``x in keywords``: findet auch Abkuerzungen / Tippfehler / andere Sprachen
  verb_role(name)              Methodenname -> 'spend' | 'add' | 'check' | 'set' | 'get' | None
  obfuscation(namen)           Anteil unlesbarer Namen -> (Anteil, verschleiert?)
  unity_methods(game)          Methoden mit Konzept + Rolle (Name, Klasse, Felder der Klasse, Form der Parameter)
  unity_fields(game)           Felder mit Konzept (inkl. Paar-Erkennung  cur/max  und Stat-Klassen)
  give_by_shape(game, ...)     Geben-Methoden ohne passenden Namen (Geschwister-Logik + Parameter-Form)
  report(game)                 alles zusammen als Klartext-Bericht (de / en) mit Begruendungen

Jeder Treffer nennt seine Gruende.  Nichts wird geraten, was sich nicht erklaeren laesst; die Sicherheit (0..1) sagt, wie stark.
"""
import re
from collections import namedtuple

# ----------------------------------------------------------------------------------------------------------------
# Konzepte: Kategorie (wie in values_auto.CATEGORY_ORDER) -> Woerter in vielen Sprachen
# ----------------------------------------------------------------------------------------------------------------
LEBEN, AUSDAUER, MANA, SCHILD = "Leben", "Ausdauer", "Mana/Energie", "Schild/Rüstung"
MUNITION, GELD, XP, HUNGER = "Munition", "Geld", "Erfahrung/Level", "Hunger/Durst"
SCHALTER, ITEM = "Schalter", "Item"

# je Konzept: STARK = eindeutig, SCHWACH = nur zusammen mit passender Klasse/Typ/Paar ein Hinweis
_V = {
    LEBEN: ("health hp hitpoints hitpoint hitpts life lives vitality vida salud vie sante leben gesundheit lebenspunkte "
            "saude vita salute zdorov zdorovie hlth healt xueliang shengming hpmax kenko taikyuryoku "
            "tairyoku inochi seimei"),
    AUSDAUER: ("stamina endurance vigor vigour sprint breath oxygen fatigue stam stm ausdauer atem resistencia "
               "souffle fadiga tiryoku kiryoku staminas"),
    MANA: ("mana magic mp energy focus power magica magia mahou maryoku"),
    SCHILD: ("shield armor armour defense defence barrier guard block armadura armure bouclier schild ruestung "
             "rustung panzer escudo scudo bougu fangyu hujia"),
    MUNITION: ("ammo ammunition bullet bullets rounds clip magazine arrows arrow bolts shells cartridge cartucho "
               "municion munition muni balas balles patronen patrone zidan danyao"),
    GELD: ("money gold coin coins cash currency credits credit gems gem silver wallet purse funds dollars bucks "
           "geldbeutel geldboerse portemonnaie monedero cartera bourse dinero oro monedas plata argent pieces geld muenzen munzen taler kohle soldi moneta moedas dinheiro "
           "kinsen okane zeni gil jinbi yinzi jinqian ruby rupee rupees souls zeny mny gld "
           "balance tokens token crystals shards essence diamonds diamond"),
    XP: ("xp exp experience level lvl nivel niveau stufe erfahrung experiencia skillpoints skillpoint talentpoints "
         "keiken jingyan dengji rank prestige reputation mastery"),
    HUNGER: ("hunger thirst food water satiety hydration sanity stress temperature warmth radiation toxicity "
             "hambre faim soif durst nahrung wasser onaka"),
    SCHALTER: ("godmode god invincible invincibility invulnerable immortal immune muteki nodamage infinite unlimited "
               "cheat nocost noreload freecraft inmortal invencible unverwundbar unsterblich unendlich wudi"),
}
# Item-Woerter (fuer Item-Listen / Klassen): mehrsprachig
_ITEM_WORDS = ("item items inventory inventar objeto objetos objet objets gegenstand gegenstaende gegenstände oggetto "
               "oggetti itens loot equipment equip gear bag backpack pack stash storage chest tool tools weapon weapons "
               "waffe waffen arma armas arme armes buki dougu douguya bougu wuqi daoju beibao ingredient material "
               "materials resource resources consumable consumables mochimono ititem")
def _plain(s):
    return str(s or "").lower().translate(_UMLAUT)


_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "á": "a", "à": "a", "é": "e", "è": "e", "í": "i",
                         "ó": "o", "ú": "u", "ñ": "n", "ç": "c", "â": "a", "ê": "e", "î": "i", "ô": "o", "û": "u"})
_ACCENTS = {**_UMLAUT, **{ord(chr(k).upper()): v.capitalize() for k, v in _UMLAUT.items() if chr(k) != "ß"}}
_CONCEPT_WORDS = {k: frozenset(_plain(w) for w in v.split()) for k, v in _V.items()}
ITEM_VOCAB = frozenset(_plain(w) for w in _ITEM_WORDS.split())
# Woerter, die in den ZEILEN von Item-Listen vorkommen (zusaetzlich zu item_finder.ROW_ITEM_WORDS): andere Sprachen
ITEM_ROW_WORDS = frozenset("""
espada pocion hierba escudo hacha arco flecha anillo llave pergamino oro madera piedra hierro cuero carne pescado pan manzana
schwert trank kraut schild axt bogen pfeil ring schluessel schriftrolle holz stein eisen leder fleisch fisch brot apfel erz
epee potion herbe bouclier hache arc fleche anneau cle parchemin bois pierre fer cuir viande poisson pain pomme
spada pozione erba scudo ascia freccia anello chiave pergamena legno pietra ferro cuoio carne pesce pane mela
espadas pocoes ervas escudo machado flecha anel chave madeira pedra ferro couro carne peixe pao maca
katana yari yumi kusuri yakusou tate yoroi kabuto kaburi tsurugi ken tachi ya mizu kome niku sakana kinoko ishi ki tetsu
jian dao gong jiu yao cao dun jia qiang shi mu tie
""".split())


# Abkuerzungen, die allein zu kurz fuer Unscharfsuche sind  ->  Konzept (nur als ganzes Wort)
ABBREV = {"hp": LEBEN, "hlt": LEBEN, "hlth": LEBEN, "mp": MANA, "stm": AUSDAUER, "stam": AUSDAUER, "xp": XP,
          "exp": XP, "lvl": XP, "gp": GELD, "gld": GELD, "mny": GELD, "ammo": MUNITION}
# Woerter, die in mehreren Konzepten stehen -> nicht eindeutig (zaehlt nur schwach)
_AMBIG = frozenset({"power", "focus", "energy", "level", "rank", "block", "guard", "food", "water", "life", "lives",
                    "pack", "tool", "tools", "bag", "gear", "chest", "equip", "token", "tokens", "essence", "balance",
                    "ruby", "shards", "crystals", "stam", "reputation", "mastery", "prestige", "clip", "pieces", "gil",
                    "cheat", "unlimited", "infinite", "magic"})

# Rollen von Methoden-Verben (mehrsprachig).  spend = verringert, add = erhoeht, check = bool-Pruefung, set = setzen
_ROLE_WORDS = {
    "spend": ("spend remove subtract deduct pay consume use take lose withdraw decrease reduce drain deplete cost sub dec "
              "decrement burn expend charge gastar usar quitar restar pagar consumir perder verbrauchen ausgeben abziehen "
              "bezahlen verlieren zahlen depenser utiliser payer retirer perdre consommer spendere usare pagare togliere "
              "perdere gastos tsukau harau herasu xiaohao koukou"),
    "add": ("add give grant gain obtain receive earn reward collect pickup pick acquire award heal restore recover "
            "refill refund increase raise inc increment put insert store deposit credit regain recharge agregar "
            "anadir dar ganar recibir recuperar curar hinzufuegen geben erhalten bekommen heilen "
            "ajouter donner gagner recevoir soigner aggiungere dare guadagnare ricevere ataeru fukasu zengjia "
            "jiaxue huode obtener"),
    "check": ("can has have is are enough afford check contains need needs requires tiene puede hay ist hat kann "
              "ya est peut possede puo ha"),
    "set": "set change update assign write modify apply festlegen setzen cambiar establecer definir",
    "get": "get read fetch current holen lire",
}
_ROLE = {role: frozenset(_plain(x) for x in w.split()) for role, w in _ROLE_WORDS.items()}
# 'Hit' / 'Damage' = Leben verringern (Methode, die Schaden annimmt)
DAMAGE_WORDS = frozenset("damage dmg hurt wound danio dano schaden blessure degats danno shanghai sunshang".split())
DAMAGE_WEAK = frozenset("hit strike harm injure colpo golpe treffer".split())          # nur mit passender Klasse (Leben / Spieler)
DEATH_WORDS = frozenset("dead dying death die kill knockedout downed muerto tot gestorben mort morto shibou siwang".split())
ALIVE_WORDS = frozenset("alive invincible invulnerable immortal godmode vivo lebendig vivant".split())
# Woerter, die ein Zahlenfeld klar als "kein Spielwert" markieren (Zeiten, Raten, Grafik ...)
NOT_VALUE = frozenset(("time timer delay duration interval rate ratio percent pct speed regen regeneration cooldown "
                       "color colour size scale offset index id idx min "
                       "threshold multiplier modifier factor curve sprite icon texture sound audio anim animation "
                       "fx vfx ui hud text label").split())
MAXISH = frozenset("max maximum limit cap capacity base default initial full".split())
CURISH = frozenset("cur current now value amount remaining left actual".split())
ENEMYISH = re.compile(r"(?i)enemy|enemies|monster|boss|npc|mob\b|zombie|minion|creep|hostile|foe|feind|gegner|ennemi|enemigo|nemico|monstruo")
PLAYERISH = re.compile(r"(?i)player|hero|character|avatar|local|protagonist|main|vitals|stats|wallet|inventory|jugador|"
                       r"spieler|joueur|giocatore|heroe|held|pc\b")
UIISH = re.compile(r"(?i)^(ui|hud|view|panel|widget|menu|button|label|slot|icon|bar|gauge|display|text|popup|window|"
                   r"screen|canvas|tooltip|tutorial)|(ui|hud|view|panel|widget|button|label|icon|bar|gauge|text|popup|"
                   r"window|screen|canvas|tooltip)$")

def _t(lang, de, en):
    return en if lang == "en" else de


Hit = namedtuple("Hit", "concept role conf why")


# ----------------------------------------------------------------------------------------------------------------
# Namen zerlegen
# ----------------------------------------------------------------------------------------------------------------
_TOK = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_PREFIX = re.compile(r"^(?:m_|s_|k_|_+|b(?=[A-Z])|get_|set_|add_|remove_|on(?=[A-Z]))")
_BACKING = re.compile(r"^<(.+)>k__BackingField$")
_DICT = None


def tokens(name):
    """'m_curHP' -> ['cur','hp'];  '<Gold>k__BackingField' -> ['gold'];  'get_PlayerHealthMax' -> ['player','health','max'];
    'playerhealth' (alles klein) wird mit dem Konzept-Woerterbuch zerlegt -> ['player','health']."""
    n = str(name or "").translate(_ACCENTS)              # Akzente weg, Gross-/Kleinschreibung bleibt (fuer camelCase)
    m = _BACKING.match(n)
    if m:
        n = m.group(1)
    n = n.split(".")[-1]
    for _ in range(2):                                   # 'm_' und danach evtl. 'get_'
        n2 = _PREFIX.sub("", n, count=1)
        if n2 == n or not n2:
            break
        n = n2
    out = [t.lower() for t in _TOK.findall(n)]
    res = []
    for t in out:
        if t.isalpha() and len(t) >= 7 and t == t.lower():
            res.extend(_segment(t))
        else:
            res.append(t)
    return [_plain(t) for t in res if t]


def _dictionary():
    global _DICT
    if _DICT is None:
        d = set()
        for ws in _CONCEPT_WORDS.values():
            d |= {_plain(w) for w in ws if len(w) >= 3}
        for ws in _ROLE.values():
            d |= {_plain(w) for w in ws if len(w) >= 3}
        d |= {_plain(w) for w in ITEM_VOCAB if len(w) >= 3}
        d |= {"player", "enemy", "max", "current", "cur", "value", "amount", "level", "count", "total", "base", "stats",
              "hero", "character", "spieler", "jugador", "joueur", "manager", "data", "info", "state"}
        _DICT = d
    return _DICT


def _segment(tok):
    """'playerhealth' -> ['player','health'] (nur wenn sich das Wort vollstaendig in bekannte Woerter teilen laesst)."""
    d = _dictionary()
    if tok in d:
        return [tok]
    best = None
    n = len(tok)
    memo = {}

    def rec(i):
        if i == n:
            return []
        if i in memo:
            return memo[i]
        res = None
        for j in range(n, i + 2, -1):                    # laengstes Wort zuerst, mindestens 3 Buchstaben
            if tok[i:j] in d:
                rest = rec(j)
                if rest is not None:
                    res = [tok[i:j]] + rest
                    break
        memo[i] = res
        return res
    best = rec(0)
    return best if best and len(best) >= 2 else [tok]


# ----------------------------------------------------------------------------------------------------------------
# Unscharf vergleichen
# ----------------------------------------------------------------------------------------------------------------
def _edit1(a, b):
    """Hoechstens EIN Unterschied (Einfuegen, Loeschen, Ersetzen, Tausch zweier Buchstaben)?"""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _stem(w):
    for suf in ("ies", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)] + ("y" if suf == "ies" else "")
    return w


def match_word(word, vocab):
    """-> (Staerke, Woerterbuch-Wort) oder (0, None).  1.0 genau | .9 Mehrzahl | .8 Tippfehler | .7 Anfang eines laengeren Worts."""
    w = _plain(word)
    if not w or w.isdigit():
        return 0.0, None
    if w in vocab:
        return 1.0, w
    s = _stem(w)
    if s in vocab:
        return 0.9, s
    if len(w) >= 5:
        for v in vocab:
            if len(v) >= 5 and _edit1(w, v):
                return 0.8, v
    if len(w) >= 4:
        for v in vocab:
            if len(v) >= 6 and v.startswith(w):              # 'ammu' -> 'ammunition'  (nur lange Zielwoerter)
                return 0.7, v
    return 0.0, None


def fuzzy_hits(words, keywords):
    """Ersatz fuer ``[x for x in words if x in keywords]`` -> Liste der Woerter, die (unscharf) zu `keywords` passen."""
    vocab = {_plain(k) for k in keywords}
    return [w for w in words if match_word(w, vocab)[0] >= 0.7]


# ----------------------------------------------------------------------------------------------------------------
# Namen -> Konzepte / Rolle
# ----------------------------------------------------------------------------------------------------------------
def concepts_of(name, extra_words=()):
    """Name -> [Hit(concept, role, conf, why)], beste zuerst.  role = 'value' (Zahlenfeld) / 'max' (Maximum/Basis) / 'flag'.
    extra_words: weitere Woerter (z. B. aus dem Klassennamen) - zaehlen nur halb so stark."""
    toks = tokens(name)
    out = {}

    def add(cat, conf, why, role):
        if cat not in out or out[cat].conf < conf:
            out[cat] = Hit(cat, role, round(min(conf, 1.0), 2), why)

    maxish = any(t in MAXISH for t in toks)
    for src, scale in ((toks, 1.0), ([_plain(w) for w in extra_words], 0.5)):
        for t in src:
            if t in ABBREV:
                cat = ABBREV[t]
                add(cat, (0.75 if t not in _AMBIG else 0.55) * scale, f"Abkürzung '{t}'", "max" if maxish and scale == 1 else "value")
                continue
            for cat, vocab in _CONCEPT_WORDS.items():
                strength, hit = match_word(t, vocab)
                if not strength:
                    continue
                conf = strength * (0.55 if hit in _AMBIG else 0.9) * scale
                how = "Name enthält" if strength == 1.0 else ("ähnlich wie" if strength >= 0.8 else "beginnt wie")
                add(cat, conf, f"{how} '{hit}'" + (f" (Wort '{t}')" if t != hit else ""),
                    "flag" if cat == SCHALTER else ("max" if maxish and scale == 1 else "value"))
    return sorted(out.values(), key=lambda h: -h.conf)


def verb_role(name):
    """Methodenname -> 'spend' | 'add' | 'check' | 'set' | 'get' | 'damage' | 'hit' | None.
    Das Verb steht vorn (PaySomething, TakeCoins, ConsumeAmmo); 'damage' = nimmt Schaden an, 'hit' = nur ein schwacher Hinweis
    (HitEnemy ...), den der Aufrufer mit der Klasse bestaetigen muss.  GetDamage / CanTakeDamage sind KEIN Schaden-Annehmen."""
    raw = str(name or "")
    if raw.startswith("get_"):
        return "get"
    if raw.startswith("set_"):
        return "set"
    toks = tokens(raw)
    if not toks:
        return None
    first = toks[0]
    if first in _ROLE["get"]:
        return "get"
    if first in _ROLE["check"]:
        return "check"
    if any(t in DAMAGE_WORDS for t in toks):
        return "damage"
    for t in toks[:2]:
        for role in ("spend", "add", "set"):
            if match_word(t, _ROLE[role])[0] >= 0.8:
                return role
    if any(t in DAMAGE_WEAK for t in toks):
        return "hit"
    for t in toks[2:]:
        for role in ("spend", "add"):
            if t in _ROLE[role]:
                return role
    return None


# ----------------------------------------------------------------------------------------------------------------
# Verschleierung erkennen
# ----------------------------------------------------------------------------------------------------------------
def _readable(name):
    n = _BACKING.sub(r"\1", str(name or ""))
    if not n or not n.isascii() or not re.search(r"[A-Za-z]", n):
        return False
    letters = re.sub(r"[^A-Za-z]", "", n)
    if len(letters) <= 2:
        return False
    if len(letters) >= 4 and not re.search(r"[aeiouAEIOU]", letters):
        return False                                     # 'Qxzv'
    return True


def obfuscation(names):
    """-> (Anteil unlesbarer Namen 0..1, verschleiert?).  Ab ~60 % unlesbar bringt jede Namenssuche nichts."""
    names = [n for n in names if n]
    if len(names) < 20:
        return 0.0, False
    bad = sum(1 for n in names if not _readable(n))
    frac = bad / len(names)
    return round(frac, 2), frac >= 0.6


# ----------------------------------------------------------------------------------------------------------------
# Unity: Methoden und Felder mit Konzept
# ----------------------------------------------------------------------------------------------------------------
UMethod = namedtuple("UMethod", "method concept role conf why cls_concept")
UField = namedtuple("UField", "cls field concept conf why paired")


def _game_classes(game, only_game_code=True):
    for c in getattr(game, "classes", None) or ():          # Attrappen ohne Klassenliste (Tests): nichts zu tun
        if c.kind in ("enum", "interface"):
            continue
        if only_game_code and c.image and not c.image.startswith("Assembly-CSharp"):
            continue
        if c.name.rsplit(".", 1)[-1].startswith("<") or "__DisplayClass" in c.name:
            continue
        yield c


def class_concept(cls):
    """Was IST diese Klasse?  Aus dem Klassennamen UND den Namen ihrer Felder: 'Wallet' / 'Purse' -> Geld;
    eine Klasse mit nur einem Zahlenfeld 'coins' ebenso.  -> Hit oder None."""
    own = concepts_of(cls.name.rsplit(".", 1)[-1])
    own = [h for h in own if h.role != "flag"]
    if own and own[0].conf >= 0.7:
        h = own[0]
        return Hit(h.concept, "class", h.conf, f"Klassenname: {h.why}")
    nums = [f for f in cls.fields if not f.static and f.offset >= 0 and f.prim in _NUMERIC]
    if 1 <= len(nums) <= 3:
        hs = [(concepts_of(f.name), f) for f in nums]
        hs = [(h[0], f) for h, f in hs if h and h[0].role != "flag" and h[0].conf >= 0.7]
        cats = {h.concept for h, _f in hs}
        if len(cats) == 1 and hs:
            h = hs[0][0]
            return Hit(h.concept, "class", round(h.conf * 0.85, 2), f"die Klasse besteht fast nur aus '{hs[0][1].name}'")
    return None


_NUMERIC = {"int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64", "float", "double"}


# Felder mit diesen Woertern sind NIE der Wert selbst (Regeneration, Rate, Dauer ...) - wie bei der Namenssuche in unity_cheatmenu
HARD_NOT_VALUE = frozenset("regen regeneration rate ratio percent pct multiplier mult delay timer time duration interval "
                           "cooldown speed cost".split())
GENERIC_VALUE = frozenset("value amount current cur count total balance points quantity number".split())


def unity_methods(game, min_conf=0.5):
    """Alle Methoden des Spiel-Codes, die zu einem Konzept gehoeren -> [UMethod].
    Das Konzept kommt aus dem Methodennamen ODER (wenn der nichts sagt) aus der Klasse (Name / Felder); die Rolle aus dem Verb
    des Namens.  Ohne erkennbares Verb wird nur gemeldet, wenn der Name das Konzept ZIEMLICH sicher nennt (nie automatisch gepatcht)."""
    out = []
    for c in _game_classes(game):
        cc = class_concept(c)
        cl = c.name.rsplit(".", 1)[-1]
        for m in c.methods:
            if m.rva <= 0 or m.name.startswith((".", "<")) or m.name in ("MoveNext", "Finalize", "Update", "LateUpdate",
                                                                         "FixedUpdate", "Awake", "Start", "OnDestroy"):
                continue
            role = verb_role(m.name)
            if role == "hit":                                  # 'HitEnemy' allein beweist nichts: Klasse muss Leben / Spieler sagen
                if (cc and cc.concept == LEBEN) or PLAYERISH.search(cl):
                    role = "damage"
                else:
                    continue
            name_hits = [h for h in concepts_of(m.name) if h.role != "flag" or m.ret == "bool"]
            concept, conf, why = None, 0.0, ""
            if role == "damage":
                concept, conf, why = LEBEN, 0.8, "Methode nimmt Schaden an"
            elif name_hits and name_hits[0].conf >= min_conf:
                h = name_hits[0]
                if role is None and h.conf < 0.8:
                    continue
                concept, conf, why = h.concept, h.conf, f"Methodenname: {h.why}"
                if cc and cc.concept == h.concept:
                    conf = min(1.0, conf + 0.1)
                    why += " + passende Klasse"
            elif cc and role in ("spend", "add", "check"):
                concept, conf, why = cc.concept, round(cc.conf * 0.85, 2), f"Verb im Namen + {cc.why}"
            if concept is None:
                continue
            if UIISH.search(cl):
                conf *= 0.6
                why += " (UI-Klasse)"
            if ENEMYISH.search(cl):
                conf *= 0.8
                why += " (Gegner-Klasse)"
            out.append(UMethod(m, concept, role, round(conf, 2), why, cc))
    out.sort(key=lambda x: (-x.conf, x.method.key))
    return out


def unity_fields(game, min_conf=0.55):
    """Zahlen-/Bool-Felder mit Konzept -> [UField], beste zuerst.  Paare (Health + MaxHealth) und Stat-Klassen (mehrere
    verschiedene Konzepte in einer Klasse) erhoehen die Sicherheit; UI-/Gegner-Klassen und Raten/Zeiten senken sie.
    Ein Feld ohne eigenen Hinweis ('amount', 'value') erbt das Konzept seiner Klasse (Wallet.amount -> Geld)."""
    out = []
    for c in _game_classes(game):
        cl = c.name.rsplit(".", 1)[-1]
        cc = class_concept(c)
        found = []
        for f in c.fields:
            if f.static or f.offset < 0 or f.prim not in _NUMERIC | {"bool"}:
                continue
            if set(tokens(f.name)) & HARD_NOT_VALUE:
                continue
            hs = [h for h in concepts_of(f.name) if h.conf >= min_conf]
            if not hs and cc and cc.conf >= 0.7 and f.prim != "bool" and set(tokens(f.name)) <= GENERIC_VALUE | MAXISH:
                hs = [Hit(cc.concept, "max" if set(tokens(f.name)) & MAXISH else "value", round(cc.conf * 0.9, 2),
                          f"allgemeines Feld in der Klasse ({cc.why})")]
            if not hs:
                continue
            h = hs[0]
            if (h.concept == SCHALTER) != (f.prim == "bool"):
                continue
            found.append((f, h))
        concepts = {h.concept for _f, h in found if h.role != "max"}
        for f, h in found:
            conf, why, paired = h.conf, [h.why], False
            toks = set(tokens(f.name))
            has_max = any(h2.concept == h.concept and h2.role == "max" and f2 is not f for f2, h2 in found)
            if h.role == "max":
                conf -= 0.35
                why.append("Maximum/Basis-Wert (eher Begleitwert)")
            elif has_max:
                conf += 0.1
                paired = True
                why.append("hat ein passendes Max-Feld daneben")
            if (toks & NOT_VALUE) and not (toks & CURISH) and h.concept != SCHALTER:
                conf -= 0.35
                why.append("sieht nach Rate/Zeit/Anzeige aus, nicht nach dem Wert selbst")
            if len(concepts) >= 3:
                conf += 0.1
                why.append(f"Klasse mit {len(concepts)} Spielwerten (Stat-Klasse)")
            if PLAYERISH.search(cl):
                conf += 0.1
                why.append("Spieler-Klasse")
            if ENEMYISH.search(cl):
                conf -= 0.2
                why.append("Gegner-Klasse")
            if UIISH.search(cl):
                conf -= 0.3
                why.append("UI-Klasse")
            if f.prim in ("float", "int32") and h.concept != SCHALTER:
                conf += 0.05
            if conf >= min_conf:
                out.append(UField(c, f, h.concept, round(min(conf, 1.0), 2), "; ".join(why), paired))
    out.sort(key=lambda x: (-x.conf, x.cls.full, x.field.offset))
    return out


def patch_mode(um):
    """UMethod -> ('noop'|'true'|'false', Begruendung) oder None: was sich an dieser Methode SICHER patchen laesst.
    Verbrauchen / Schaden annehmen + void -> leer; Verbrauchen + bool (TrySpend) und 'kann ich'-Pruefungen -> immer ja;
    'ist tot' -> immer nein.  Alles andere (Zahlen, Setzen, Hinzufuegen) wird nicht automatisch gepatcht."""
    import il2cpp_dump as D
    m = um.method
    prim = D.PRIMS.get(m.ret)
    if um.role in ("spend", "damage") and m.ret == "void" and um.concept in (LEBEN, AUSDAUER, MANA, MUNITION, GELD, HUNGER):
        return "noop", "verbraucht / nimmt Schaden: Methode leer machen"
    if prim == "bool":
        toks = set(tokens(m.name))
        if um.role == "check" and um.concept in (LEBEN, AUSDAUER, MANA, MUNITION, GELD, SCHALTER):
            if toks & DEATH_WORDS:
                return "false", "'ist tot'-Prüfung: immer nein"
            return "true", "Prüfung ('kann ich / habe ich genug'): immer ja"
        if um.role == "spend" and um.concept in (AUSDAUER, MANA, MUNITION, GELD):
            return "true", "Verbrauch gelingt immer"
        if um.concept == SCHALTER and um.role in (None, "get"):
            return "true", "Schalter (z. B. unverwundbar) immer an"
    return None


def msg_obfuscated(frac, lang="de"):
    pct = int(frac * 100)
    return _t(lang,
              f"Die Namen im Spiel sind zu {pct} % verschleiert - eine Namenssuche findet hier nichts. Besser: einen sichtbaren "
              "Wert (z. B. dein Geld) im Speicher suchen, im Spiel ändern und erneut suchen - die Treffer zeigen, welches Feld das ist.",
              f"{pct} % of the names in this game are obfuscated - a search by name finds nothing here. Better: search a visible "
              "value (e.g. your money) in memory, change it in the game and search again - the hits show which field it is.")


def msg_nothing_found(lang="de"):
    return _t(lang, "Nichts Nützliches am Namen erkannt.", "Nothing useful recognised by name.")


def _game_names(game, cap=3000):
    cs = [c for c in getattr(game, "classes", None) or () if (c.image or "").startswith("Assembly-CSharp")]
    return [m.name for c in cs for m in c.methods][:cap] + [f.name for c in cs for f in c.fields][:cap]


def no_result_hint(game, lang="de"):
    """Kurzer Klartext fuer 'es wurde nichts gefunden': Verschleierung, sonst leer."""
    frac, obf = obfuscation(_game_names(game))
    return msg_obfuscated(frac, lang) if obf else ""


# ----------------------------------------------------------------------------------------------------------------
# Geben-Methoden an ihrer FORM erkennen
# ----------------------------------------------------------------------------------------------------------------
_ID_NAME = re.compile(r"(?i)^(id|item_?id|itemid|item|type|kind|key|index|idx|uid|code|what|objeto|gegenstand)$|item")
_CNT_NAME = re.compile(r"(?i)count|amount|num|quantity|qty|stack|number|cantidad|menge|anzahl|n$")


def _params(m, U, enums):
    try:
        return [U.parse_param(p, enums) for p in U.split_params(m.params)]
    except Exception:  # noqa: BLE001
        return None


def give_by_shape(game, item_enum=None, limit=40):
    """Methoden, die ein Item geben koennten, OHNE dass der Name 'Add/Give' sagt.  -> [(Methode, Score, [Gruende], stark)].
    stark = ein echter Beleg (Geschwister einer Entfernen-Methode ODER ein Verb fuer Hinzufuegen), nicht nur 'sieht passend aus'.
    Hinweise: (1) Geschwister:  in derselben Klasse gibt es eine Methode mit gleicher Parameter-Form, die klar ENTFERNT
    (Remove/Use/Drop ...) - dann ist eine andere mit derselben Form wahrscheinlich die zum HINZUFUEGEN.  (2) Form:
    (Item-Enum / ID, Menge) ohne Rueckgabe oder bool.  (3) Klasse klingt nach Inventar (mehrsprachig).  (4) Item-Enum."""
    import unity_items as U
    enums = U.enum_map(game)
    out = []
    for c in _game_classes(game):
        inv_class = bool(fuzzy_hits(tokens(c.name.rsplit(".", 1)[-1]), ITEM_VOCAB))
        shaped = []
        for m in c.methods:
            if m.rva <= 0 or m.name.startswith((".", "<", "get_", "set_", "op_")) or m.cls is None:
                continue
            ps = _params(m, U, enums)
            if not ps or len(ps) > 3 or any(p["ref"] or p["kind"] in ("other", "float", "double") for p in ps):
                continue
            ids = [i for i, p in enumerate(ps) if p["kind"] == "enum" or (p["kind"] == "int" and _ID_NAME.search(p["name"])
                                                                          and not _CNT_NAME.search(p["name"]))]
            cnts = [i for i, p in enumerate(ps) if p["kind"] == "int" and i not in ids]
            if not ids:
                continue
            shaped.append((m, ps, ids, cnts))
        shape_key = lambda ps: tuple((p["kind"], p["type"]) for p in ps)          # noqa: E731
        removers = {shape_key(ps) for m, ps, _i, _c in shaped if verb_role(m.name) == "spend"
                    or re.search(r"(?i)^(remove|delete|drop|discard|destroy|sell|consume|use)", m.name)}
        for m, ps, ids, cnts in shaped:
            role = verb_role(m.name)
            if role in ("spend", "check", "get") or re.search(r"(?i)^(remove|delete|drop|destroy|sell|use|can|has|is|try_?remove)", m.name):
                continue
            s, why, strong = 0.0, [], False
            if role == "add":
                s += 3
                strong = True
                why.append("Verb bedeutet hinzufügen")
            if shape_key(ps) in removers:
                s += 3
                strong = True
                why.append("gleiche Form wie eine Entfernen-Methode in derselben Klasse (Geschwister)")
            if cnts:
                s += 1.5
                why.append("hat eine Menge")
            if item_enum is not None and any(p["type"] in (item_enum.name, item_enum.full) for p in ps):
                s += 3
                why.append("nimmt die erkannte Item-Liste")
            if inv_class:
                s += 2
                why.append("Klasse klingt nach Inventar")
            if m.ret in ("void", "bool"):
                s += 0.5
            if s >= 4.5:
                out.append((m, round(s, 1), why, strong))
    out.sort(key=lambda x: -x[1])
    return out[:limit]


# ----------------------------------------------------------------------------------------------------------------
# Item-Listen: mehrsprachiger Namenshinweis fuer Enums / Tabellen
# ----------------------------------------------------------------------------------------------------------------
def name_says_item(name):
    """Klingt der NAME einer Liste / Klasse nach Items (auch 'Objeto', 'Gegenstand', 'Buki' ...)?  -> Sicherheit 0..1"""
    toks = tokens(name)
    best = 0.0
    for t in toks:
        s, hit = match_word(t, ITEM_VOCAB)
        if s:
            best = max(best, s * (0.7 if hit in _AMBIG else 1.0))
    return round(best, 2)


# ----------------------------------------------------------------------------------------------------------------
# Unreal: Ergaenzung fuer uecheat (Members / Funktionen)
# ----------------------------------------------------------------------------------------------------------------
def ue_member_hits(member_words, category, keywords):
    """uecheat.classify_member: Woerter, die woertlich nicht in `keywords` stehen, aber unscharf / mehrsprachig / als
    Abkuerzung passen -> Liste (leer = nichts).  Eine Kategorie wird nur ueber ihr Konzept gefunden, damit z. B. 'Mag'
    nicht in 'Cheat-Schalter' landet."""
    cat = {"Leben": LEBEN, "Ausdauer": AUSDAUER, "Mana/Energie": MANA, "Schild/Rüstung": SCHILD, "Munition": MUNITION,
           "Währung": GELD, "Erfahrung": XP, "Hunger/Durst": HUNGER, "Cheat-Schalter": SCHALTER}.get(category)
    if cat is None:
        return []
    hits = []
    for t in member_words:
        if t in keywords:
            continue
        if t in ABBREV and ABBREV[t] == cat and t not in _AMBIG:
            hits.append(t)
            continue
        strength, w = match_word(t, _CONCEPT_WORDS[cat])
        if strength >= 0.8 and w not in _AMBIG:
            hits.append(t)
    return hits


def ue_function_role(name):
    """Unreal-Funktionsname -> (Konzept oder None, Rolle).  'TakeDamage' -> (Leben,'damage'), 'GastarMunicion' -> (Munition,'spend')."""
    role = verb_role(name)
    hits = [h for h in concepts_of(name) if h.role != "flag"]
    if role == "damage":
        return LEBEN, "damage"
    return (hits[0].concept if hits else None), role


# ----------------------------------------------------------------------------------------------------------------
# Bericht
# ----------------------------------------------------------------------------------------------------------------
def _line(kind, who, role, conf, why):
    return f"   {kind} {who}  [{role or '?'}] ({int(conf * 100)} %)  - {why}"


def report(game, lang="de", per_concept=3):
    """Klartext-Bericht fuer ein Unity-Spiel: Verschleierung, was gefunden wurde (je Konzept die besten) und was dann hilft.
    -> (text, daten-dict)"""
    frac, obf = obfuscation(_game_names(game, 4000))
    fields, methods = unity_fields(game), unity_methods(game)
    lines = [msg_obfuscated(frac, lang)] if obf else []
    by = {}
    for f in fields:
        by.setdefault(f.concept, []).append(f)
    kind_f, kind_m = _t(lang, "Feld   ", "field  "), _t(lang, "Methode", "method ")
    for cat in (LEBEN, AUSDAUER, MANA, SCHILD, MUNITION, GELD, XP, HUNGER, SCHALTER):
        fl = by.get(cat, [])[:per_concept]
        ml = [m for m in methods if m.concept == cat][:per_concept]
        if not fl and not ml:
            continue
        lines.append(f"■ {cat}")
        lines += [_line(kind_f, f"{f.cls.full}.{f.field.name}", None, f.conf, f.why) for f in fl]
        lines += [_line(kind_m, f"{m.method.cls.full}.{m.method.name}({m.method.params})", m.role, m.conf, m.why) for m in ml]
    if not fields and not methods:
        lines.append(msg_nothing_found(lang))
    text = "\n".join(lines)
    return text, {"obfuscated": obf, "obf_fraction": frac, "fields": fields, "methods": methods, "text": text}
