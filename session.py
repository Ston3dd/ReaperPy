"""session.py – Sitzung speichern/laden (.cheatsession.json).

Enthält: Projekt (Name, Patch-Ordner, Image-Base), aktive Patches + 'gewollte' Patches (für
Auto-Reconnect), Cheat-Liste inkl. Freeze-Werte und Pointer-Pfade, Pointer-Scanner-Ergebnis.
Es werden NIE Patches ohne ausdrückliche Aktion (SESSION LADEN) auf der Konsole aktiviert.
"""
import glob
import json
import os
import time

SESSION_VERSION = 1
EXT = ".cheatsession.json"


# ------------------------------------------------------------------
# Pfade
# ------------------------------------------------------------------
def default_path(patch_dir, project):
    safe = "".join(c if c.isalnum() or c in " ._-" else "_" for c in (project or "session")).strip()
    return os.path.join(patch_dir or ".", f"{safe or 'session'}{EXT}")


def find_auto(patch_dir):
    """Neueste *.cheatsession.json im Patch-Ordner, sonst im Ordner daneben (Elternordner)."""
    for folder in (patch_dir, os.path.dirname(os.path.abspath(patch_dir or ""))):
        if not folder or not os.path.isdir(folder):
            continue
        files = glob.glob(os.path.join(folder, "*" + EXT))
        if files:
            return max(files, key=os.path.getmtime)
    return None


def _rel(patch_dir, path):
    try:
        return os.path.relpath(path, patch_dir).replace("\\", "/")
    except ValueError:                       # anderes Laufwerk
        return path


def _abs(patch_dir, rel):
    return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(patch_dir, rel))


# ------------------------------------------------------------------
# Tools-Zustand (Cheat-Liste / Pointer)
# ------------------------------------------------------------------
def collect_tools(tools):
    """Zustand der Werkzeug-Tabs -> dict (tools = ToolsWindow)."""
    cheats, pointer = [], {}
    st = getattr(tools, "scan_tab", None)
    if st is not None:
        for e in st.entries:
            ptr = e.get("ptr")
            cheats.append({
                "addr": int(e.get("addr") or 0), "vname": e["vname"], "desc": e.get("desc", ""),
                "frozen": bool(e.get("frozen")),
                "freeze": bytes(e["freeze"]).hex() if e.get("freeze") is not None else None,
                "ptr": [ptr[0], list(ptr[1])] if ptr else None})
    pt = getattr(tools, "ptr_tab", None)
    if pt is not None:
        pointer = {"type": pt.v_type.get(), "target": pt.v_target.get(),
                   "paths": [{"root": r, "offsets": list(o)} for r, o in pt.paths]}
    return {"cheats": cheats, "pointer": pointer}


def apply_tools(tools, data):
    """Gespeicherten Zustand in die Werkzeug-Tabs einsetzen."""
    st = getattr(tools, "scan_tab", None)
    if st is not None and data.get("cheats") is not None:
        st.entries = []
        for c in data["cheats"]:
            ptr = c.get("ptr")
            st.entries.append({
                "addr": int(c.get("addr") or 0), "vname": c.get("vname", "Int32"),
                "desc": c.get("desc", ""), "frozen": bool(c.get("frozen")),
                "freeze": bytes.fromhex(c["freeze"]) if c.get("freeze") else None,
                "cur": "?", "ptr": (int(ptr[0]), tuple(int(x) for x in ptr[1])) if ptr else None})
        st._refresh_list()
    pt = getattr(tools, "ptr_tab", None)
    pd = data.get("pointer") or {}
    if pt is not None and pd:
        pt.paths = [(int(p["root"]), tuple(int(x) for x in p["offsets"])) for p in pd.get("paths", [])]
        if pd.get("type"):
            pt.v_type.set(pd["type"])
        if pd.get("target"):
            pt.v_target.set(pd["target"])
        pt._fill()


# ------------------------------------------------------------------
# Gesamt-Sitzung
# ------------------------------------------------------------------
def collect(app):
    pd = app.PATCH_DIR or ""
    tools = _live_tools(app)
    tstate = collect_tools(tools) if tools else (getattr(app, "tools_stash", None) or {})
    return {
        "app": "ReaperPy", "version": SESSION_VERSION,
        "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
        "project": {"name": app.current_project or "", "patches_dir": pd,
                    "image_base": hex(app.IMAGE_BASE)},
        "connection": {"ip": app.backend.host, "port": app.backend.port},
        "patches": {"active": sorted(_rel(pd, p) for p in app.applied),
                    "wanted": sorted(_rel(pd, p) for p in app.wanted)},
        "cheats": tstate.get("cheats", []),
        "pointer": tstate.get("pointer", {}),
    }


def _live_tools(app):
    w = getattr(app, "_tools", None)
    try:
        return w if w is not None and w.winfo_exists() else None
    except Exception:
        return None


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or data.get("app") != "ReaperPy":
        raise ValueError("Keine ReaperPy-Sitzung")
    if int(data.get("version", 0)) > SESSION_VERSION:
        raise ValueError(f"Sitzung stammt aus einer neueren Version ({data.get('version')})")
    return data


def apply(app, data, activate=False):
    """Sitzung übernehmen. Rückgabe: dict mit Zählern.

    activate=False (Auto-Load): nur Merkliste ('wanted'), Cheat-Liste, Pointer - nichts wird auf der
    Konsole verändert.  activate=True (SESSION LADEN): die gespeicherten aktiven Patches werden
    zusätzlich eingeschaltet (nur wenn verbunden)."""
    pd = app.PATCH_DIR or ""
    info = {"patches": 0, "missing": 0, "cheats": len(data.get("cheats") or []),
            "project_mismatch": False, "activated": 0}
    pj = data.get("project") or {}
    if pj.get("name") and app.current_project and pj["name"] != app.current_project:
        info["project_mismatch"] = True

    wanted = set()
    for rel in (data.get("patches") or {}).get("wanted", []) + (data.get("patches") or {}).get("active", []):
        path = _abs(pd, rel)
        if path in app.patches:
            wanted.add(path)
        else:
            # Fallback: gleicher Dateiname im aktuellen Patch-Ordner
            alt = os.path.join(pd, os.path.basename(rel))
            if alt in app.patches:
                wanted.add(alt)
            else:
                info["missing"] += 1
    app.wanted |= wanted
    info["patches"] = len(wanted)

    tstate = {"cheats": data.get("cheats", []), "pointer": data.get("pointer", {})}
    app.tools_stash = tstate
    tools = _live_tools(app)
    if tools:
        apply_tools(tools, tstate)

    if activate:
        todo = []
        for rel in (data.get("patches") or {}).get("active", []):
            path = _abs(pd, rel)
            if path not in app.patches:
                path = os.path.join(pd, os.path.basename(rel))
            if path in app.patches and path not in app.applied:
                todo.append(path)
        info["activated"] = len(todo)
        if todo:
            app.activate_paths(todo)
    return info
