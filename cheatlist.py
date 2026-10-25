"""cheatlist.py - Anzeigelogik der Cheat-Liste (reine Funktionen, ohne Oberflaeche): Suche, Favoriten, Gruppen, Hotkeys."""
import sys

ALL = "*"                  # Gruppen-Filter: alle
NO_GROUP = "-"             # Gruppen-Filter: Cheats ohne Gruppe

MOD_KEYSYMS = {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Meta_L", "Meta_R", "Super_L", "Super_R",
               "Caps_Lock", "Num_Lock", "Scroll_Lock", "ISO_Level3_Shift", "Mode_switch", "Win_L", "Win_R"}
RESERVED = {"Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+A", "Ctrl+Z", "Ctrl+Y", "Alt+F4", "Ctrl+W", "Ctrl+Q"}
NEEDS_MOD_BLOCKED = {"Escape", "Tab", "Return", "BackSpace", "Delete", "space"}


def visible_order(items, gp, query="", group=ALL, only_fav=False):
    """items = [(pfad, anzeigename)].  -> Pfade in Anzeigereihenfolge: Favoriten zuerst, dann nach Gruppe, dann nach Name.
    Cheats ohne Gruppe kommen nach den Gruppen."""
    q = (query or "").strip().lower()
    rows = []
    for path, name in items:
        fn = _fname(path)
        grp = gp.groups.get(fn, "") if gp else ""
        fav = fn in gp.favorites if gp else False
        if only_fav and not fav:
            continue
        if group == NO_GROUP and grp:
            continue
        if group not in (ALL, NO_GROUP) and grp != group:
            continue
        if q and q not in f"{name} {grp}".lower():
            continue
        rows.append((0 if fav else 1, 1 if not grp else 0, grp.lower(), str(name).lower(), path))
    rows.sort()
    return [r[-1] for r in rows]


def _fname(path):
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------------------------
# Hotkeys
# ---------------------------------------------------------------------------------------------
def _alt_bit(platform):
    return 0x20000 if platform == "win32" else 0x8


def spec_from_event(keysym, state, platform=None):
    """Tk-Tastenereignis -> 'Ctrl+Alt+Shift+F5' (None bei reinen Modifier-Tasten)."""
    if not keysym or keysym in MOD_KEYSYMS:
        return None
    platform = platform or sys.platform
    key = keysym.upper() if len(keysym) == 1 else keysym
    parts = []
    if state & 0x4:
        parts.append("Ctrl")
    if state & _alt_bit(platform):
        parts.append("Alt")
    if state & 0x1 and not (len(keysym) == 1 and keysym.isalpha()):
        parts.append("Shift")                       # bei Buchstaben steckt Shift schon im Zeichen (Grossbuchstabe)
    elif state & 0x1 and len(keysym) == 1 and keysym.isalpha() and (state & 0x4 or state & _alt_bit(platform)):
        parts.append("Shift")
    return "+".join(parts + [key])


def valid_spec(spec):
    """Erlaubt: F-Tasten, oder Ctrl/Alt + Taste.  Nicht: blanke Buchstaben/Zahlen, Escape/Tab/..., Windows-Standard (Ctrl+C ...)."""
    if not spec or spec in RESERVED:
        return False
    *mods, key = spec.split("+")
    if key in NEEDS_MOD_BLOCKED and not mods:
        return False
    if key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return True
    return ("Ctrl" in mods or "Alt" in mods) and key not in NEEDS_MOD_BLOCKED


def pretty(spec):
    return spec or ""


TEXT_CLASSES = {"Entry", "TEntry", "TCombobox", "Text", "Spinbox", "TSpinbox"}


def typing_in_text(widget_class):
    """Hotkeys nicht ausloesen, waehrend in ein Textfeld getippt wird."""
    return widget_class in TEXT_CLASSES
