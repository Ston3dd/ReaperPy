"""projects.py – Projektverwaltung für ReaperPy."""
import copy, json, os

import paths
from reapatch import is_patch_file

CONFIG_FILE = os.path.join(paths.data_dir(), "reaperpy_config.json")

DEFAULTS = {
    "projects_root": "",
    "last_project": "",
    "ps5_ip": "192.168.178.25",
    "language": "de",
    "ps5_port": 744,
    "cave_size": 0x4000,
    "image_base": "0x400000",
    "projects": {},
    "library_dir": os.path.join(paths.data_dir(), "library"),
    "auto_reconnect": False,
}


# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
def load_config() -> dict:
    if not os.path.isfile(CONFIG_FILE):
        return copy.deepcopy(DEFAULTS)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULTS.items():
            data.setdefault(k, copy.deepcopy(v))
        return data
    except Exception:
        return copy.deepcopy(DEFAULTS)


def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
    except Exception:
        pass


# ------------------------------------------------------------------
# Ordner-Erkennung
# ------------------------------------------------------------------
def _has_patches(folder: str) -> bool:
    if not folder or not os.path.isdir(folder):
        return False
    for f in os.listdir(folder):
        if is_patch_file(f):
            return True
    return False


def has_patches(folder: str):
    """Sucht Patch-Dateien – erst direkt, dann in Unterordnern."""
    if not folder or not os.path.isdir(folder):
        return False, None

    # Direkt im Ordner
    if _has_patches(folder):
        return True, folder

    # Häufige Unterordner-Namen
    sub_names = ("Patches", "patches", "Trainers", "trainers",
                 "Cheats", "cheats", "ShnExt", "shnext")
    for sub in sub_names:
        sub_path = os.path.join(folder, sub)
        if _has_patches(sub_path):
            return True, sub_path

    # Rekursiv eine Ebene tiefer suchen
    for entry in sorted(os.listdir(folder)):
        sub_path = os.path.join(folder, entry)
        if os.path.isdir(sub_path) and _has_patches(sub_path):
            return True, sub_path

    return False, None


def list_projects(root: str):
    """Listet alle Projekte im Root-Ordner, die Patch-Dateien enthalten."""
    if not root or not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        ok, patches_dir = has_patches(p)
        if ok:
            out.append((name, p, patches_dir))
    return out


# ------------------------------------------------------------------
# Image-Base pro Projekt
# ------------------------------------------------------------------
def get_image_base(cfg: dict, project_name: str, patches_dir: str) -> int:
    key = patches_dir or project_name
    p = cfg.get("projects", {}).get(key, {})
    v = p.get("image_base", cfg.get("image_base", "0x400000"))
    try:
        return int(v, 16) if isinstance(v, str) else int(v)
    except Exception:
        return 0x400000


def set_image_base(cfg: dict, project_name: str, patches_dir: str, value: int):
    key = patches_dir or project_name
    cfg.setdefault("projects", {}).setdefault(key, {})
    cfg["projects"][key]["image_base"] = hex(value)
    save_config(cfg)