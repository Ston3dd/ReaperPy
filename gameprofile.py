"""gameprofile.py - Profil je Spiel: Notizen, Favoriten, Gruppen, Hotkeys, Ansichts-Einstellungen, Analyse-Zwischenspeicher.

Gespeichert wird je Spiel eine JSON-Datei im Profilordner (paths.profiles_dir()), benannt nach der Titel-ID (PPSA01234 /
CUSA01234); ohne erkennbare Titel-ID nach dem Projektnamen.  Cheats werden ueber ihren DATEINAMEN gekennzeichnet (stabil,
solange die Patch-Datei ihren Namen behaelt).  Alles ist abgesichert: eine kaputte Profildatei wird uebersprungen
(und als .bad aufgehoben), nie ueberschrieben ohne Sicherung.
"""
import json
import os
import re
import time

import paths

KEY_RE = re.compile(r"^(?:CUSA|PPSA)\d{5}$")
VERSION = 1


def key_for(title_id="", project=""):
    tid = (title_id or "").strip().upper()
    if KEY_RE.match(tid):
        return tid
    slug = re.sub(r"[^\w\-. ]+", "_", str(project or "")).strip(" ._")[:60]
    return slug or "default"


class GameProfile:
    def __init__(self, key, directory=None):
        self.key = key
        self.dir = directory
        self.title = ""
        self.notes = ""
        self.favorites = set()
        self.groups = {}            # Dateiname -> Gruppe
        self.hotkeys = {}           # Dateiname -> "Ctrl+F5"
        self.ui = {}                # z. B. {"group": "...", "only_fav": False}
        self.discover = None        # {"sig": ..., "json": ...} - zuletzt analysiertes SDK (Entdecker)
        self.updated = 0.0

    # ---- Favoriten / Gruppen / Hotkeys ---------------------------------------------------------
    def toggle_favorite(self, name):
        if name in self.favorites:
            self.favorites.discard(name)
            return False
        self.favorites.add(name)
        return True

    def set_group(self, name, group):
        group = (group or "").strip()
        if group:
            self.groups[name] = group[:40]
        else:
            self.groups.pop(name, None)

    def group_names(self):
        return sorted(set(self.groups.values()), key=str.lower)

    def hotkey_owner(self, spec, ignore=None):
        for n, s in self.hotkeys.items():
            if s == spec and n != ignore:
                return n
        return None

    def set_hotkey(self, name, spec):
        """-> Name des Cheats, der die Kombination schon hat (dann wird NICHTS gesetzt), sonst None."""
        owner = self.hotkey_owner(spec, ignore=name)
        if owner:
            return owner
        self.hotkeys[name] = spec
        return None

    def clear_hotkey(self, name):
        self.hotkeys.pop(name, None)

    def forget_missing(self, existing_names):
        """Eintraege zu Cheats entfernen, deren Datei es nicht mehr gibt (nur bei vollstaendiger Liste aufrufen!)."""
        keep = set(existing_names)
        self.favorites &= keep
        self.groups = {k: v for k, v in self.groups.items() if k in keep}
        self.hotkeys = {k: v for k, v in self.hotkeys.items() if k in keep}

    # ---- Speichern / Laden -----------------------------------------------------------------------
    def path(self):
        return os.path.join(self.dir or paths.profiles_dir(), f"{self.key}.json")

    def to_json(self):
        return {"version": VERSION, "key": self.key, "title": self.title, "notes": self.notes,
                "favorites": sorted(self.favorites), "groups": self.groups, "hotkeys": self.hotkeys, "ui": self.ui,
                "discover": self.discover, "updated": self.updated}

    def save(self):
        """Atomar schreiben.  -> True/False (Fehler stoeren das Programm nicht)."""
        try:
            self.updated = time.time()
            p = self.path()
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.to_json(), f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
            return True
        except OSError:
            return False


def load(key, directory=None):
    """Profil laden; fehlt die Datei oder ist sie kaputt: leeres Profil (kaputte Datei -> .bad)."""
    gp = GameProfile(key, directory)
    p = gp.path()
    if not os.path.isfile(p):
        return gp
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("kein Objekt")
    except (OSError, ValueError):
        try:
            os.replace(p, p + ".bad")
        except OSError:
            pass
        return gp
    gp.title = str(d.get("title", ""))
    gp.notes = str(d.get("notes", ""))
    gp.favorites = {str(x) for x in d.get("favorites", []) if isinstance(x, str)}
    gp.groups = {str(k): str(v) for k, v in (d.get("groups") or {}).items()}
    gp.hotkeys = {str(k): str(v) for k, v in (d.get("hotkeys") or {}).items()}
    gp.ui = dict(d.get("ui") or {})
    disc = d.get("discover")
    gp.discover = disc if isinstance(disc, dict) and "sig" in disc and "json" in disc else None
    gp.updated = float(d.get("updated") or 0)
    return gp
