"""fuzzy.py - Fuzzy-Wertsuche (ohne tkinter): "ungefaehr 75, plus/minus 5" statt einer exakten Zahl.

Spiele zeigen Werte oft gerundet (Leben 75 von 75.4, Prozentbalken) - eine exakte Suche findet dann nichts.  Die Fuzzy-Suche wird auf
den Bereichs-Vergleich ("Zwischen") des Scanners abgebildet, der Server braucht dafuer nichts Neues:

    parse_approx("75~5%")      -> ("75", "5%")      Eingabeformen: 75~5  75±5  75+-5  75 ~ 5%  ~75  ca. 75  75~
    to_range("Int32", "75", "5%") -> ("72", "78")   (Grenzen passend zum Typ, bei Ganzzahlen mindestens +-1)
    describe(...)                  -> "72 bis 78"   fuer die Anzeige
Standard-Toleranz ohne Angabe: 5 Prozent.
"""
import re

DEFAULT_PCT = 5.0
MIN_ABS_INT = 1.0           # Ganzzahlen: wenigstens +-1, sonst waere "ca. 10 +-5%" = genau 10
MIN_ABS_FLOAT = 0.01        # Kommazahlen um 0 herum
_INT_BITS = {"UInt8": (8, False), "Int8": (8, True), "UInt16": (16, False), "Int16": (16, True),
             "UInt32": (32, False), "Int32": (32, True), "UInt64": (64, False), "Int64": (64, True)}
_SEP = re.compile(r"\s*(?:±|\+/-|\+-|~)\s*")
_NUM = r"[-+]?(?:0[xX][0-9a-fA-F]+|\d+(?:[.,]\d*)?|[.,]\d+)"


class FuzzyError(ValueError):
    pass


def parse_tolerance(text):
    """'5' -> ('abs', 5.0) | '5%' -> ('pct', 5.0) | '' -> ('pct', 5.0)."""
    t = (text or "").strip().replace(",", ".")
    if not t:
        return "pct", DEFAULT_PCT
    pct = t.endswith("%")
    t = t.rstrip("%").strip()
    try:
        v = abs(float(t))
    except ValueError:
        raise FuzzyError(f"'{text}' ist keine Toleranz (Beispiele: 5 oder 5%)") from None
    return ("pct" if pct else "abs"), v


def parse_approx(text):
    """Freitext -> (Zahl-Text, Toleranz-Text oder None).  None = es war keine Fuzzy-Eingabe (also gewoehnliche Zahl)."""
    t = (text or "").strip()
    if not t:
        return None
    prefixed = False
    m = re.match(r"(?i)\s*(?:ca\.?|etwa|circa|~)\s*(?=[-+.,\d])", t)
    if m:
        t, prefixed = t[m.end():].strip(), True
    if not _SEP.search(t):
        if prefixed:
            if not re.fullmatch(_NUM, t):
                raise FuzzyError(f"'{text}': nach 'ca.' muss eine Zahl stehen")
            return t, None
        return None
    parts = [p for p in _SEP.split(t, maxsplit=1)]
    if len(parts) != 2 or not re.fullmatch(_NUM, parts[0].strip()):
        raise FuzzyError(f"'{text}': links muss eine Zahl stehen (Beispiel: 75~5)")
    tol = parts[1].strip()
    if tol and not re.fullmatch(_NUM + "%?", tol):
        raise FuzzyError(f"'{text}': rechts muss eine Toleranz stehen (Beispiel: 75~5 oder 75~5%)")
    return parts[0].strip(), tol or None


def is_approx(text):
    try:
        return parse_approx(text) is not None
    except FuzzyError:
        return True


def _num(text, vname):
    t = text.strip().replace(",", ".")
    try:
        if vname in _INT_BITS and re.fullmatch(r"[-+]?0[xX][0-9a-fA-F]+", t):
            return float(int(t, 16))
        return float(t)
    except ValueError:
        raise FuzzyError(f"'{text}' ist keine Zahl") from None


def to_range(vname, center_text, tol_text):
    """Zielwert + Toleranz -> (untere, obere Grenze) als Text, passend fuer scanner.encode_value(vname, ...)."""
    c = _num(center_text, vname)
    kind, amount = parse_tolerance(tol_text)
    tol = abs(c) * amount / 100.0 if kind == "pct" else amount
    if vname in _INT_BITS:
        tol = max(tol, MIN_ABS_INT)
        bits, signed = _INT_BITS[vname]
        lo_lim, hi_lim = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)
        import math
        lo, hi = int(math.floor(c - tol)), int(math.ceil(c + tol))
        lo, hi = max(lo, lo_lim), min(hi, hi_lim)
        if lo > hi:
            raise FuzzyError(f"{center_text} liegt ausserhalb des Bereichs von {vname}")
        return str(lo), str(hi)
    if tol <= 0:
        tol = MIN_ABS_FLOAT
    if c == 0 and kind == "pct":
        tol = MIN_ABS_FLOAT
    return f"{c - tol:.9g}", f"{c + tol:.9g}"


def describe(vname, center_text, tol_text):
    lo, hi = to_range(vname, center_text, tol_text)
    return f"{lo} bis {hi}"
