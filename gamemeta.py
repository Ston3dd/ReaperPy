"""gamemeta.py - Cover (pic0.png) und exakten Spielnamen (param.json) des laufenden Spiels von der Konsole holen.

Wie Reaper Studio: per FTP (ftpsrv / etaHEN / GoldHEN, anonym) aus dem sce_sys-Ordner des Spiels
  pic0.png   Hintergrundbild  (Fallback: icon0.png)
  param.json localizedParameters.<Sprache>.titleName  = der exakte Titel, wie ihn die Konsole zeigt

Ablauf (ohne GUI, testbar):
  fetch()      holt beides (mit Cache im Ordner covers/), wirft nie - Fehler stehen in Meta.error / Meta.tried
  pick_name()  waehlt den besten Namen: param.json > Name vom Vordergrund-Prozess > Bibliothek > Titel-ID

Einstellungen (config.json, alle optional):
  ftp_ports   [2121, 1337]   Ports, die der Reihe nach probiert werden
  meta_dirs   ["/pfad/{id}"] zusaetzliche Ordner, die zuerst durchsucht werden ({id} = Titel-ID)
  ftp_timeout 4              Sekunden je Verbindungsversuch
  game_meta   true           auf false: komplett aus
"""
import ftplib
import io
import json
import os
import re
import time
from dataclasses import dataclass, field

import paths

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE = 12 * 1024 * 1024
MAX_JSON = 512 * 1024
DEFAULT_PORTS = (2121, 1337)
# Wo liegt sce_sys des Spiels?  Laufendes Spiel (Sandbox-Mount) zuerst, dann installierte Daten.
SEARCH_DIRS = (
    "/mnt/sandbox/pfsmnt/{id}-app0/sce_sys",
    "/mnt/sandbox/{id}_000/app0/sce_sys",
    "/user/app/{id}/sce_sys",
    "/system_data/priv/appmeta/{id}",
    "/user/appmeta/{id}",
    "/mnt/ext0/user/app/{id}/sce_sys",
    "/mnt/ext1/user/app/{id}/sce_sys",
)
ID_RE = re.compile(r"^[A-Z]{4}\d{5}$")
BAD_NAME_EXT = (".bin", ".elf", ".self", ".prx", ".exe")
_DOWN = {}                      # host -> Zeitpunkt, bis zu dem wir FTP nicht erneut versuchen (kein Dauer-Haenger)
DOWN_SECONDS = 45


@dataclass
class Meta:
    title_id: str = ""
    name: str = ""              # exakter Titel aus param.json ('' = nicht gefunden)
    cover: str = ""             # lokaler Pfad der pic0.png (oder icon0.png)
    cover_kind: str = ""        # "pic0" | "icon0" | ""
    source: str = ""            # FTP-Ordner, aus dem die Daten kamen ("cache" bei reinem Cache-Treffer)
    error: str = ""
    tried: list = field(default_factory=list)       # [(pfad, ergebnis)] fuer das Protokoll


# ---------------------------------------------------------------------------- Namen
def parse_param_json(raw, prefer=("en-US", "en-GB")):
    """param.json -> exakter Titel oder ''.  defaultLanguage gewinnt, dann englisch, dann irgendeine Sprache."""
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw).decode("utf-8-sig", "replace")
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    loc = data.get("localizedParameters")
    if isinstance(loc, dict):
        order = [loc.get("defaultLanguage")] + list(prefer)
        for lang in order:
            e = loc.get(lang) if isinstance(lang, str) else None
            if isinstance(e, dict) and clean_name(e.get("titleName")):
                return clean_name(e["titleName"])
        for k, e in loc.items():
            if isinstance(e, dict) and k != "defaultLanguage" and clean_name(e.get("titleName")):
                return clean_name(e["titleName"])
    return clean_name(data.get("titleName"))


def clean_name(s):
    """Namen saeubern; Prozessnamen (eboot.bin) und Titel-IDs sind keine Spielnamen."""
    if not isinstance(s, str):
        return ""
    s = re.sub(r"\s+", " ", s.replace("\x00", " ")).strip()
    if not s or ID_RE.match(s.upper()) or s.lower().endswith(BAD_NAME_EXT) or s.lower() in ("eboot", "default"):
        return ""
    return s


def pick_name(title_id="", meta_name="", fg_name="", entry_title=""):
    """-> (name, quelle).  Quelle: 'param.json' | 'konsole' | 'bibliothek' | 'id'."""
    for val, src in ((meta_name, "param.json"), (fg_name, "konsole"), (entry_title, "bibliothek")):
        n = clean_name(val)
        if n and n.upper() != (title_id or "").upper():
            return n, src
    return (title_id or ""), "id"


# ---------------------------------------------------------------------------- Cache
def cache_dir():
    return paths.sub_dir("covers")


def _cache_paths(tid, directory=None):
    d = directory or cache_dir()
    return (os.path.join(d, f"{tid}_pic0.png"), os.path.join(d, f"{tid}_icon0.png"),
            os.path.join(d, f"{tid}.json"))


def _read_cache(tid, directory=None):
    pic, ico, js = _cache_paths(tid, directory)
    m = Meta(title_id=tid)
    try:
        with open(js, "r", encoding="utf-8") as f:
            m.name = clean_name(json.load(f).get("name"))
    except (OSError, ValueError, AttributeError):
        pass
    for p, kind in ((pic, "pic0"), (ico, "icon0")):
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            m.cover, m.cover_kind = p, kind
            break
    if m.name or m.cover:
        m.source = "cache"
    return m


def _write_atomic(path, data):
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------- FTP
class _Capped(Exception):
    pass


def _download(ftp, path, limit):
    buf = io.BytesIO()

    def cb(chunk):
        buf.write(chunk)
        if buf.tell() > limit:
            raise _Capped()
    try:
        ftp.retrbinary("RETR " + path, cb)
    except _Capped:
        try:
            ftp.abort()
        except Exception:                                   # noqa: BLE001
            pass
        return None
    return buf.getvalue()


def _connect(host, ports, timeout, factory):
    last = ""
    for port in ports:
        try:
            ftp = factory()
            ftp.connect(host, int(port), timeout=timeout)
            try:
                ftp.login()                                 # anonym (ftpsrv/etaHEN/GoldHEN)
            except ftplib.error_perm:
                ftp.login("anonymous", "reaperpy@")
            ftp.set_pasv(True)
            return ftp, port, ""
        except Exception as e:                              # noqa: BLE001
            last = f"{host}:{port} {type(e).__name__}: {e}"
    return None, 0, last


def fetch(host, title_id, cfg=None, ftp_factory=None, directory=None, now=None):
    """Cover + Namen holen.  Cache zuerst; fehlt etwas, wird per FTP nachgeladen.  Wirft nie."""
    cfg = cfg or {}
    tid = (title_id or "").strip().upper()
    m = Meta(title_id=tid)
    if not ID_RE.match(tid):
        m.error = "keine gueltige Titel-ID"
        return m
    if cfg.get("game_meta", True) is False:
        m.error = "abgeschaltet (game_meta=false)"
        return m
    try:
        os.makedirs(directory or cache_dir(), exist_ok=True)
        m = _read_cache(tid, directory)
        have_pic = m.cover_kind == "pic0"
        if m.name and have_pic:
            return m
        t = (now or time.time)()
        if _DOWN.get(host, 0) > t:
            m.error = "FTP vorhin nicht erreichbar - naechster Versuch spaeter"
            return m
        ports = [p for p in (cfg.get("ftp_ports") or DEFAULT_PORTS)]
        ftp, port, err = _connect(host, ports, float(cfg.get("ftp_timeout", 4)), ftp_factory or ftplib.FTP)
        if ftp is None:
            _DOWN[host] = t + DOWN_SECONDS
            m.error = "FTP nicht erreichbar: " + err
            return m
        _DOWN.pop(host, None)
        try:
            _scan(ftp, tid, cfg, m, directory)
        finally:
            try:
                ftp.quit()
            except Exception:                               # noqa: BLE001
                try:
                    ftp.close()
                except Exception:                           # noqa: BLE001
                    pass
        if not m.name and not m.cover:
            m.error = "weder param.json noch pic0.png gefunden (siehe Protokoll)"
    except Exception as e:                                  # noqa: BLE001
        m.error = f"{type(e).__name__}: {e}"
    return m


def _scan(ftp, tid, cfg, m, directory):
    pic, ico, js = _cache_paths(tid, directory)
    dirs = [str(d).replace("{id}", tid) for d in (cfg.get("meta_dirs") or [])]
    dirs += [d.format(id=tid) for d in SEARCH_DIRS]
    need_name = not m.name
    need_pic = m.cover_kind != "pic0"
    icon_data = None
    for d in dirs:
        if not (need_name or need_pic):
            break
        if need_name:
            raw = _try(ftp, f"{d}/param.json", MAX_JSON, m)
            if raw:
                name = parse_param_json(raw)
                if name:
                    m.name, need_name = name, False
                    m.source = m.source if m.source not in ("", "cache") else d
                    _write_atomic(js, json.dumps({"name": name, "dir": d, "ts": int(time.time())},
                                                 ensure_ascii=False).encode("utf-8"))
        if need_pic:
            img = _try(ftp, f"{d}/pic0.png", MAX_IMAGE, m)
            if img and img.startswith(PNG_MAGIC):
                _write_atomic(pic, img)
                m.cover, m.cover_kind, need_pic = pic, "pic0", False
                m.source = d
            elif icon_data is None and not m.cover:
                ic = _try(ftp, f"{d}/icon0.png", MAX_IMAGE, m)
                if ic and ic.startswith(PNG_MAGIC):
                    icon_data = (ic, d)
    if need_pic and icon_data and not m.cover:                # pic0 gibt es nirgends -> icon0 als Ersatz
        _write_atomic(ico, icon_data[0])
        m.cover, m.cover_kind, m.source = ico, "icon0", icon_data[1]


def _try(ftp, path, limit, m):
    try:
        data = _download(ftp, path, limit)
        m.tried.append((path, "ok" if data else "leer/zu gross"))
        return data
    except ftplib.error_perm as e:                          # 550 = gibt es dort nicht
        m.tried.append((path, str(e)[:40]))
    except (ftplib.Error, OSError, EOFError) as e:
        m.tried.append((path, f"{type(e).__name__}"))
    return None
