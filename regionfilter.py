"""regionfilter.py - Speicherbereiche des Spiels einteilen (eboot.bin, Spiel-Module, Systembibliotheken, Heap ...)
und ausfiltern.  Reine Logik ohne Konsole und ohne GUI -> testbar (tests/test_regionfilter.py).

Wozu: Ein Scan mit "Unbekannter Startwert" liest und vergleicht jeden Speicherplatz der gewaehlten Regionen.  Die Spiel-
Werte (Leben, Munition, Geld ...) liegen fast immer in der eboot.bin (Daten) oder im Heap - nicht in den Systembibliotheken
(libSce*, libc, libkernel ...).  Wer diese Regionen auslaesst, scannt weniger Gigabyte und ist entsprechend schneller.

Eingabe ist die benannte Prozess-Karte, entweder als Tupel (start, end, prot, name) (ps5_client.get_maps_named) oder als
dicts {'name', 'start', 'end', 'prot'} (ps5_ext.maps_named).

Aufbau
  build_sections(maps)  -> {Kategorie: [Section]}   (eboot.bin aufgesplittet, Libs je Modul, grosse Heap-Regionen einzeln,
                                                    kleine Regionen je Kategorie zusammengefasst)
  FilterState           Haken pro Bereich + Ausblend-Regeln (Voreinstellungen und eigene Muster)
  included_starts(...)  Startadressen der Regionen, die tatsaechlich gescannt werden (Scanner.regions(pick=...))
  stats(...)            Zaehler/Groesse fuer die Anzeige ("Ausgewaehlt: ...") - nutzt dieselbe Auswahl wie der Scan
"""
import fnmatch
import json
import os
import re
from collections import OrderedDict, namedtuple

from regionreport import prot_text

MB = 1048576
Region = namedtuple("Region", "start end prot name")

# Kategorien in Anzeigereihenfolge (Schluessel -> Anzeigename)
CATS = OrderedDict([
    ("eboot", "eboot.bin (Spiel-Code und -Daten)"),
    ("gamemod", "Spiel-Module (.prx, kein System)"),
    ("syslib", "Systembibliotheken (libSce*, libc ...)"),
    ("heap", "Heap / anonymer Speicher"),
    ("shm", "Shared Memory / Geräte (/Sce...)"),
    ("stack", "Stacks"),
    ("other", "Sonstiges"),
])
MAIN_NAMES = ("eboot.bin",)
MODULE_EXT = (".prx", ".sprx", ".elf", ".bin", ".self")
SYSTEM_PREFIXES = ("libsce", "libc.", "libc_", "libkernel", "libm.", "libpthread", "libz.", "libsys", "sce")
SMALL_LABEL = "kleine Regionen (< 1 MB)"
INDIV_MIN = 1 * MB                 # ab dieser Groesse bekommt eine Heap-/Shm-Region eine eigene Zeile
MIN_REGION = 0x1000                # wie Scanner.regions: kleinere Regionen werden nie gescannt

_HEX = re.compile(r"^[0-9a-fA-F]{6,}$")


# ------------------------------------------------------------------------------------------------------------------
# Einlesen / Einordnen
# ------------------------------------------------------------------------------------------------------------------
def normalize(maps):
    """Tupel oder dicts -> sortierte Liste von Region(start, end, prot, name)."""
    out = []
    for m in maps or ():
        if isinstance(m, dict):
            out.append(Region(int(m["start"]), int(m["end"]), int(m.get("prot", 0)), str(m.get("name") or "")))
        else:
            name = m[3] if len(m) > 3 else ""
            out.append(Region(int(m[0]), int(m[1]), int(m[2]), str(name or "")))
    out.sort()
    return out


def is_module_name(low):
    return low.endswith(MODULE_EXT)


def is_system_lib(low):
    return low.startswith(SYSTEM_PREFIXES)


def classify(name, main_names=MAIN_NAMES):
    """Name einer Region -> Kategorie-Schluessel (siehe CATS)."""
    n = (name or "").strip()
    low = n.lower()
    if low in main_names:
        return "eboot"
    if not n or low.startswith("anon") or _HEX.match(n):
        return "heap"
    if low.startswith("/"):
        return "shm"
    if is_module_name(low):
        return "syslib" if is_system_lib(low) else "gamemod"
    if "stack" in low:
        return "stack"
    return "other"


def kind_label(prot):
    """Abschnitt der eboot.bin nach den Rechten: x = Code, w = Daten, sonst Konstanten."""
    if prot & 4:
        return "Code-Bereich"
    if prot & 2:
        return "Daten-Bereich"
    return "Nur-Lesen-Bereich"


def in_scope(prot, scope):
    """Gleiche Regel wie Scanner.regions: data = rw ohne Code, rw = alles Schreibbare, sonst alles Lesbare."""
    if not prot & 1:
        return False
    if scope == "data":
        return bool(prot & 2) and not prot & 4
    if scope == "rw":
        return bool(prot & 2)
    return True


def fmt_size(nbytes):
    mb = nbytes / MB
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    if mb >= 1:
        return f"{mb:.1f} MB"
    return f"{nbytes / 1024:.0f} KB"


# ------------------------------------------------------------------------------------------------------------------
# Bereiche (Sections)
# ------------------------------------------------------------------------------------------------------------------
class Section:
    """Eine Zeile der Bereichsliste: eine oder mehrere Regionen mit stabilem Schluessel."""
    __slots__ = ("key", "cat", "label", "regions", "module", "size", "prot")

    def __init__(self, key, cat, label, regions, module=""):
        self.key, self.cat, self.label, self.regions, self.module = key, cat, label, regions, module
        self.size = sum(r.end - r.start for r in regions)
        self.prot = 0
        for r in regions:
            self.prot |= r.prot

    @property
    def start(self):
        return min(r.start for r in self.regions)

    @property
    def rights(self):
        return prot_text(self.prot)


def build_sections(maps, indiv_min=INDIV_MIN, main_names=MAIN_NAMES):
    """-> OrderedDict {Kategorie: [Section]} (leere Kategorien entfallen).

    eboot.bin: jede Region einzeln (Code / nur lesen / Daten).  Module: eine Zeile je Bibliothek.  Heap, Shared Memory,
    Stacks: Regionen ab 1 MB einzeln (nach Groesse), der Rest je Kategorie als eine Sammelzeile - so bleibt die Liste auch
    bei 17000 Regionen uebersichtlich."""
    secs = OrderedDict((c, []) for c in CATS)
    modules, small = {}, {}
    for r in normalize(maps):
        if not r.prot & 1:                      # nicht lesbar -> nie scanbar
            continue
        cat = classify(r.name, main_names)
        if cat == "eboot":
            secs[cat].append(Section(f"mod:{r.name}@{r.start:x}", cat, f"{kind_label(r.prot)}  0x{r.start:X}",
                                     [r], r.name))
        elif cat in ("gamemod", "syslib"):
            modules.setdefault((cat, r.name), []).append(r)
        elif r.end - r.start >= indiv_min:
            shown = (r.name or "anonym")[:26]
            secs[cat].append(Section(f"reg:{r.start:x}", cat, f"{shown}  0x{r.start:X}", [r], r.name))
        else:
            small.setdefault(cat, []).append(r)
    for (cat, name), regs in modules.items():
        secs[cat].append(Section(f"lib:{name}", cat, name, regs, name))
    for cat, regs in small.items():
        secs[cat].append(Section(f"small:{cat}", cat, SMALL_LABEL, regs, ""))
    for cat, lst in secs.items():
        if cat == "eboot":
            lst.sort(key=lambda s: s.start)
        else:                                   # gross zuerst, die Sammelzeile ganz unten
            lst.sort(key=lambda s: (s.key.startswith("small:"), -s.size, s.start))
    return OrderedDict((c, l) for c, l in secs.items() if l)


# ------------------------------------------------------------------------------------------------------------------
# Filter
# ------------------------------------------------------------------------------------------------------------------
# Ausblend-Voreinstellungen: Schluessel -> (Anzeigename, Test(name, kategorie, groesse, rechte))
PRESETS = OrderedDict([
    ("syslib", ("alle Systembibliotheken", lambda n, c, size, p: c == "syslib")),
    ("libsce", ("libSce*  (Sony-Bibliotheken)", lambda n, c, size, p: n.lower().startswith("libsce"))),
    ("libc", ("libc / libkernel / libm",
              lambda n, c, size, p: n.lower().startswith(("libc.", "libc_", "libkernel", "libm.")))),
    ("shm", ("Shared Memory (/Sce...)", lambda n, c, size, p: c == "shm")),
    ("stack", ("Stacks", lambda n, c, size, p: c == "stack")),
])
DEFAULT_HIDE = ("syslib",)
CUSTOM_LABEL = "eigener Filter"
_WILD = re.compile(r"[*?\[]")


def split_patterns(text):
    return [p.strip().lower() for p in re.split(r"[,;\n]", text or "") if p.strip()]


class FilterState:
    """Was gescannt wird: Haken je Bereich (`off` = abgewaehlte Schluessel) + Ausblend-Regeln.

    `off` enthaelt Bereichs-Schluessel (siehe build_sections) und 'cat:<kategorie>' fuer komplett abgewaehlte Kategorien.
    Neue Regionen (der Heap waechst) richten sich dadurch automatisch nach dem Haken ihrer Kategorie."""

    def __init__(self, hide=DEFAULT_HIDE, custom="", off=()):
        self.hide = set(hide)
        self.custom = custom or ""
        self.off = set(off)

    def copy(self):
        return FilterState(self.hide, self.custom, self.off)

    # --- Abfragen -------------------------------------------------------------------------------
    def is_on(self, sec):
        return sec.key not in self.off and f"cat:{sec.cat}" not in self.off

    def category_state(self, cat, sections):
        """'on' | 'off' | 'mixed' (nur nach den Haken, Ausblend-Regeln zaehlen hier nicht)."""
        flags = [self.is_on(s) for s in sections]
        if flags and all(flags):
            return "on"
        if not any(flags):
            return "off"
        return "mixed"

    def hidden_reason(self, region, cat):
        """Name der Regel, die diese Region ausblendet - leer, wenn keine zutrifft."""
        size = region.end - region.start
        for key, (label, test) in PRESETS.items():
            if key in self.hide and test(region.name or "", cat, size, region.prot):
                return label
        low = (region.name or "").lower()
        for p in split_patterns(self.custom):
            if (fnmatch.fnmatchcase(low, p) if _WILD.search(p) else p in low):
                return CUSTOM_LABEL
        return ""

    def included(self, region, sec):
        return self.is_on(sec) and not self.hidden_reason(region, sec.cat)

    # --- Haken setzen -----------------------------------------------------------------------------
    def set_section(self, sec, on, siblings):
        catkey = f"cat:{sec.cat}"
        if on:
            if catkey in self.off:              # Kategorie war aus: nur dieser Bereich an, die anderen bleiben aus
                self.off.discard(catkey)
                self.off.update(s.key for s in siblings if s.key != sec.key)
            self.off.discard(sec.key)
        else:
            self.off.add(sec.key)

    def set_category(self, cat, on, siblings):
        self.off.discard(f"cat:{cat}")
        for s in siblings:
            self.off.discard(s.key)
        if not on:
            self.off.add(f"cat:{cat}")

    def only(self, cats):
        """Nur diese Kategorien an, alles andere aus."""
        self.off = {f"cat:{c}" for c in CATS if c not in cats}

    def all_on(self):
        self.off = set()

    def all_off(self):
        self.off = {f"cat:{c}" for c in CATS}

    def hide_pattern(self, pattern):
        """Fuegt ein Muster zu den eigenen Filtern hinzu (kein Doppeleintrag)."""
        have = split_patterns(self.custom)
        if pattern.strip().lower() not in have:
            self.custom = (self.custom.strip().rstrip(",;") + ", " if self.custom.strip() else "") + pattern.strip()


# ------------------------------------------------------------------------------------------------------------------
# Auswahl + Zahlen
# ------------------------------------------------------------------------------------------------------------------
def _scannable(r, scope, min_size):
    return in_scope(r.prot, scope) and (r.end - r.start) >= min_size


def section_stats(sec, state, scope="rw", min_size=MIN_REGION):
    """-> (alle_regionen, alle_bytes, gewaehlte_regionen, gewaehlte_bytes) im gewaehlten Bereich (scope)."""
    n = b = sn = sb = 0
    for r in sec.regions:
        if not _scannable(r, scope, min_size):
            continue
        size = r.end - r.start
        n, b = n + 1, b + size
        if state.included(r, sec):
            sn, sb = sn + 1, sb + size
    return n, b, sn, sb


def stats(sections, state, scope="rw", min_size=MIN_REGION):
    """Gesamtzahlen ueber alle Kategorien -> dict(total_n, total_b, sel_n, sel_b)."""
    t = [0, 0, 0, 0]
    for lst in sections.values():
        for sec in lst:
            for i, v in enumerate(section_stats(sec, state, scope, min_size)):
                t[i] += v
    return {"total_n": t[0], "total_b": t[1], "sel_n": t[2], "sel_b": t[3]}


def included_starts(maps, state, scope="rw", min_size=MIN_REGION, main_names=MAIN_NAMES):
    """Startadressen aller Regionen, die mit diesem Filter gescannt werden (fuer Scanner.regions(pick=...))."""
    out = set()
    for lst in build_sections(maps, main_names=main_names).values():
        for sec in lst:
            for r in sec.regions:
                if _scannable(r, scope, min_size) and state.included(r, sec):
                    out.add(r.start)
    return out


# ------------------------------------------------------------------------------------------------------------------
# Speichern / Laden (Einstellung bleibt zwischen Sitzungen erhalten)
# ------------------------------------------------------------------------------------------------------------------
def save_state(state, path):
    """Adress-abhaengige Schluessel ('reg:') werden nicht gespeichert - nach einem Neustart liegen sie woanders."""
    data = {"hide": sorted(state.hide), "custom": state.custom,
            "off": sorted(k for k in state.off if not k.startswith("reg:"))}
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        return True
    except OSError:
        return False


def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        hide = [k for k in d.get("hide", []) if k in PRESETS]
        return FilterState(hide, str(d.get("custom", "")), [str(k) for k in d.get("off", [])])
    except (OSError, ValueError, AttributeError, TypeError):
        return FilterState()
