"""reappatch_fmt.py - Patch-Dokument (ReaperPy-JSON) -> .ReapPatch im Format von Reaper.

Reaper macht daraus selbst eine .ShnExt (dort wird exportiert).  Das Format wurde an einer echten Datei abgelesen:

    Kopf:   info, name, index, author, isMasterCode, isIgnored, Variables
    Eintrag: index, defaultValue, newValue, type, editor, isAlwaysEnabled, isStatic, offsetFinder, offsetFinderPtr,
             option, label, DisplayName, comment, baseId, offset (Dezimalzahl)
    OriginReturn: type 6, defaultValue 0, baseId "OriginSource", offset = Rueckkehr-Abstand
    OriginSource: type 11, isStatic true, baseId "0", offset = Adresse (Dezimalzahl)
    Label/OriginTarget: type 11, baseId "", offset 0, Zeilenende CRLF, Code endet mit CRLF
"""
import json

T_RETURN, T_CODE = 6, 11


def _int(v, default=0):
    if isinstance(v, int):
        return v
    s = str(v if v is not None else "").strip()
    return int(s, 0) if s else default


def _crlf(text):
    return "\r\n".join(str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"))


def _entry(label, default, new, typ, static, base_id, offset):
    return {"index": 0, "defaultValue": default, "newValue": new, "type": typ, "editor": None,
            "isAlwaysEnabled": False, "isStatic": static, "offsetFinder": None, "offsetFinderPtr": None,
            "option": None, "label": label, "DisplayName": None, "comment": None, "baseId": base_id,
            "offset": offset}


def convert(doc):
    """ReaperPy-Dokument (name, author, Variables) -> Reaper-Dokument (dict)."""
    if not isinstance(doc, dict) or not isinstance(doc.get("Variables"), list):
        raise ValueError("Kein Patch-Dokument (Variables fehlt)")
    out = []
    returns, sources, labels = [], [], []
    for v in doc["Variables"]:
        low = str(v.get("label", "")).lower().replace("_", "")
        if low.startswith("originsource"):
            sources.append(v)
        elif low == "originreturn":
            returns.append(v)
        else:
            labels.append(v)
    if not sources:
        raise ValueError("OriginSource fehlt")
    for v in returns[:1]:
        out.append(_entry("OriginReturn", 0, None, T_RETURN, False, "OriginSource", _int(v.get("offset"), 8)))
    for v in sources:
        e = _entry("OriginSource", _crlf(v.get("defaultValue") or ""), _crlf(v.get("newValue") or ""), T_CODE, True,
                   "0", _int(v.get("offset")))
        for k in ("aob", "aobOffset"):
            if k in v:
                e[k] = v[k]
        out.append(e)
    for v in labels:
        code = _crlf(v.get("defaultValue") or "").rstrip("\r\n")
        out.append(_entry(str(v.get("label") or "OriginTarget"), code + "\r\n", None, T_CODE, False, "", 0))
    return {"info": str(doc.get("info") or ""), "name": str(doc.get("name") or ""), "index": 0,
            "author": str(doc.get("author") or ""), "isMasterCode": False, "isIgnored": False, "Variables": out}


def dumps(doc):
    """-> .ReapPatch-Bytes (UTF-8 ohne BOM, kompaktes JSON wie Reaper)."""
    return json.dumps(convert(doc), separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def doc_from_patch(rp):
    """Geladener Patch (reapatch.ReapPatch, egal welches Quellformat) -> ReaperPy-Dokument fuer convert()."""
    if not rp.origin_source:
        raise ValueError("OriginSource fehlt")
    variables = []
    for i, (off, dv, nv) in enumerate(rp.sites()):
        v = {"label": "OriginSource", "offset": off, "defaultValue": dv, "newValue": nv}
        if i == 0 and getattr(rp, "origin_aob", ""):
            v["aob"], v["aobOffset"] = rp.origin_aob, rp.origin_aob_offset
        variables.append(v)
    if rp.labels:
        variables.append({"label": "OriginReturn", "offset": rp.origin_return_offset})
        variables += [{"label": name, "defaultValue": code} for name, code in rp.labels]
    return {"name": rp.name, "author": rp.author, "Variables": variables}


def _safe_name(name):
    s = "".join(c if c.isalnum() or c in " ._-()+" else "_" for c in str(name)).strip(" .")
    return s or "Patch"


def export_patches(patches, dest_dir):
    """Jeden Patch als <Name>.ReapPatch in dest_dir schreiben (nie etwas ueberschreiben).
    -> (geschriebene Dateinamen, [(Patch-Name, Fehlertext)])"""
    import os
    os.makedirs(dest_dir, exist_ok=True)
    written, failed = [], []
    for rp in patches:
        try:
            data = dumps(doc_from_patch(rp))
        except Exception as e:  # noqa: BLE001
            failed.append((getattr(rp, "name", "?"), str(e)))
            continue
        base = _safe_name(rp.name)
        fn, i = base + ".ReapPatch", 2
        while os.path.exists(os.path.join(dest_dir, fn)):
            fn, i = f"{base} ({i}).ReapPatch", i + 1
        with open(os.path.join(dest_dir, fn), "wb") as f:
            f.write(data)
        written.append(fn)
    return written, failed
