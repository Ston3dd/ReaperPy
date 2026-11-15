"""library.py – Spiele-Bibliothek: ordnet Icons und Patch-Dateien über die Spiel-ID zu.

Spiel-ID  = [A-Z]{4}\\d{5}  (PPSA01234, CUSA12345 ...), irgendwo im Datei- oder Ordnernamen.

Icons    : PPSA01234.png (exakt) hat Vorrang vor Dateien, die die ID nur irgendwo im Namen tragen
           (PPSA01234_icon0.jpg).  Gesucht wird im Bibliotheks-Ordner (bis 3 Ebenen tief).
Patches  : jede Patch-Datei (reapatch.is_patch_file) im Bibliotheks-Ordner, im Projekte-Ordner und in
           den bekannten Projekt-Ordnern.  Zuordnung per Dateiname, sonst per Ordnerpfad.
           Ohne ID wird nach Ordner gruppiert, damit nichts versteckt bleibt.
Ordner   : fuer jedes Spiel mit ID (Cover/Icon/Patch) legt die Bibliothek im Bibliotheks-Ordner einen Ordner
           'Spielname - PPSA01234' an.  Patches aus anderen Quellen einfach dort hineinschieben - die ID im
           Ordnernamen ordnet sie dem Spiel zu.
"""
import os
import re
from dataclasses import dataclass, field

from reapatch import is_patch_file

ID_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]{4}\d{5})(?!\d)")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
GENERIC_ICON_NAMES = ("icon0", "icon", "cover", "logo", "folder")
SKIP_DIRS = {".git", "__pycache__", "node_modules", "$recycle.bin"}
MAX_DEPTH = 3


def extract_id(*texts):
    """Erste Spiel-ID aus den Texten (in der Reihenfolge der Argumente); '' wenn keine."""
    for t in texts:
        if not t:
            continue
        m = ID_RE.search(str(t))
        if m:
            return m.group(1).upper()
    return ""


_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def folder_name(title, game_id):
    """'Super Game', 'PPSA01234' -> 'Super Game - PPSA01234' (windows-tauglich, ID im Namen)."""
    t = _BAD_CHARS.sub(" ", title or "")
    t = re.sub(r"\s{2,}", " ", t).strip(" .-")
    if t.upper() == (game_id or "").upper():
        t = ""
    t = t[:80].strip(" .-")
    return f"{t} - {game_id}" if t else game_id


def clean_title(name, game_id=""):
    """'PPSA01234 - Super_Game (v1.02)' -> 'Super Game (v1.02)'."""
    base = os.path.splitext(name)[0] if os.path.splitext(name)[1].lower() in (
        IMAGE_EXT + (".reapproj", ".json", ".shnext", ".reapatch")) else name
    if game_id:
        base = re.sub(game_id, "", base, flags=re.I)
    base = re.sub(r"[_\.]+", " ", base)
    base = re.sub(r"\s*[-–]\s*", " - ", base).strip(" -")
    base = re.sub(r"\s{2,}", " ", base)
    return base or game_id


@dataclass
class GameEntry:
    id: str = ""
    title: str = ""
    icon: str = ""
    patches: list = field(default_factory=list)       # Pfade der Patch-Dateien
    project_dir: str = ""                              # Ordner, der die Patches enthält

    @property
    def key(self):
        return self.id or f"dir:{self.project_dir}"

    def matches(self, text):
        t = (text or "").strip().lower()
        return not t or t in self.title.lower() or t in self.id.lower()


def _walk(root, depth=MAX_DEPTH):
    """(ordner, [dateien]) bis `depth` Ebenen, ohne versteckte/Systemordner."""
    if not root or not os.path.isdir(root):
        return
    root = os.path.abspath(root)
    base_level = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        level = dirpath.rstrip(os.sep).count(os.sep) - base_level
        dirnames[:] = [d for d in dirnames
                       if d.lower() not in SKIP_DIRS and not d.startswith(".")] if level < depth else []
        yield dirpath, filenames


class Library:
    def __init__(self, library_dir, projects_root="", extra_dirs=(), covers=None, make_folders=False):
        self.make_folders = make_folders        # fuer jedes Spiel mit ID einen Patch-Ordner anlegen
        self.created = []                       # dabei neu angelegte Ordner
        self.covers = list(covers or [])        # gamemeta.Meta aus dem Konsolen-Cache (exakte Namen + Cover)
        self.library_dir = library_dir or ""
        self.projects_root = projects_root or ""
        self.extra_dirs = [d for d in extra_dirs if d]
        self.entries = []

    # ------------------------------------------------------------------
    def _scan_icons(self):
        """id -> Pfad.  Exakter Name (PPSA01234.png) schlägt 'ID irgendwo im Namen'."""
        best = {}
        for dirpath, files in _walk(self.library_dir):
            for f in files:
                stem, ext = os.path.splitext(f)
                if ext.lower() not in IMAGE_EXT:
                    continue
                gid = extract_id(stem)
                if not gid:
                    continue
                prio = 0 if stem.upper() == gid else 1
                if gid not in best or prio < best[gid][0]:
                    best[gid] = (prio, os.path.join(dirpath, f))
        return {k: v[1] for k, v in best.items()}

    @staticmethod
    def _generic_icon(folder):
        """Fallback: icon0.png / cover.jpg ... direkt im Projekt-Ordner."""
        try:
            names = {n.lower(): n for n in os.listdir(folder)}
        except OSError:
            return ""
        for g in GENERIC_ICON_NAMES:
            for ext in IMAGE_EXT:
                if g + ext in names:
                    return os.path.join(folder, names[g + ext])
        return ""

    def scan(self):
        icons = self._scan_icons()
        roots, seen_roots = [], set()
        for r in [self.library_dir, self.projects_root] + self.extra_dirs:
            ar = os.path.abspath(r) if r else ""
            if ar and ar not in seen_roots and os.path.isdir(ar):
                seen_roots.add(ar)
                roots.append(ar)

        games = {}            # key -> GameEntry
        seen_files = set()
        for root in roots:
            for dirpath, files in _walk(root):
                for f in sorted(files):
                    if not is_patch_file(f):
                        continue
                    path = os.path.join(dirpath, f)
                    if path in seen_files:
                        continue
                    seen_files.add(path)
                    rel = os.path.relpath(dirpath, root)
                    parts = [] if rel == "." else rel.split(os.sep)
                    # Dateiname zuerst, dann Ordner von innen nach außen
                    gid = extract_id(f, *reversed(parts))
                    if gid:
                        src = f if extract_id(f) else next(
                            (p for p in reversed(parts) if extract_id(p)), f)
                        key = gid
                    elif parts:
                        src, key = parts[-1], f"dir:{dirpath}"
                    else:
                        src, key = f, f"file:{path}"
                    g = games.get(key)
                    if g is None:
                        g = games[key] = GameEntry(id=gid, title=clean_title(src, gid),
                                                   project_dir=dirpath)
                    g.patches.append(path)

        for gid, icon in icons.items():
            g = games.get(gid)
            if g is None:
                g = games[gid] = GameEntry(id=gid, title=gid)
            g.icon = icon
        for g in games.values():
            if not g.icon and g.project_dir:
                g.icon = self._generic_icon(g.project_dir)

        for cm in self.covers:                  # von der Konsole geholt: exakter Name, Icon (icon0 vor pic0)
            g = games.get(cm.title_id)
            if g is None:
                g = games[cm.title_id] = GameEntry(id=cm.title_id, title=cm.name or cm.title_id)
            elif cm.name:
                g.title = cm.name
            if not g.icon or g.icon == self._generic_icon(g.project_dir):
                g.icon = cm.icon or cm.cover or g.icon
        if self.make_folders:
            self._ensure_folders(games.values())
        self.entries = sorted(games.values(), key=lambda g: (g.title.lower(), g.id))
        return self.entries

    # ------------------------------------------------------------------
    def _id_folders(self):
        """id -> Ordner im Bibliotheks-Ordner, dessen Name die Spiel-ID enthaelt."""
        out = {}
        for dirpath, _files in _walk(self.library_dir):
            if os.path.abspath(dirpath) == os.path.abspath(self.library_dir):
                continue
            gid = extract_id(os.path.basename(dirpath))
            if gid and gid not in out:
                out[gid] = dirpath
        return out

    def _ensure_folders(self, games):
        """Fuer jedes Spiel mit ID einen Ordner 'Spielname - ID' anlegen (falls noch keiner mit der ID existiert).
        Spiele ohne Patches bekommen ihn als Projekt-Ordner, damit ein Klick auf die Karte ihn oeffnet."""
        if not self.library_dir:
            return
        try:
            os.makedirs(self.library_dir, exist_ok=True)
        except OSError:
            return
        have = self._id_folders()
        for g in games:
            if not g.id:
                continue
            folder = have.get(g.id)
            if folder is None:
                folder = os.path.join(self.library_dir, folder_name(g.title, g.id))
                try:
                    os.makedirs(folder, exist_ok=True)
                except OSError:
                    continue
                have[g.id] = folder
                self.created.append(folder)
            if not g.project_dir:
                g.project_dir = folder

    def filter(self, text):
        return [g for g in self.entries if g.matches(text)]
