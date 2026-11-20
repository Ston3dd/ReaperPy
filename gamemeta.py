"""gamemeta.py - Cover (pic0.png) und exakten Spielnamen (param.json) des laufenden Spiels von der Konsole holen.

Wie Reaper Studio: per FTP (ftpsrv / etaHEN / GoldHEN, anonym) aus dem sce_sys-Ordner des Spiels
  pic0.png   Hintergrundbild  (Fallback: icon0.png)
  param.json localizedParameters.<Sprache>.titleName  = der exakte Titel, wie ihn die Konsole zeigt

Ablauf (ohne GUI, testbar):
  fetch()      holt beides (mit Cache im Ordner covers/), wirft nie - Fehler stehen in Meta.error / Meta.tried
  pick_name()  waehlt den besten Namen: param.json > Name vom Vordergrund-Prozess > Bibliothek > Titel-ID

Ordner-Dumps (z. B. /data/homebrew/<beliebiger Name>/sce_sys/param.json): ReaperPy liest die Titel-ID aus der param.json
jedes Dump-Ordners - der Ordnername ist egal.  Die Zuordnung Ordner -> Titel-ID wird in covers/dumps.json gemerkt.

Einstellungen (config.json, alle optional):
  dump_roots  ["/data/homebrew"]  Ordner, in denen die Spiele-Dumps liegen
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
    icon: str = ""              # lokaler Pfad der icon0.png (quadratisch, fuer die Bibliothek) oder ''
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


def parse_param_id(raw):
    """param.json -> Titel-ID (titleId) oder ''."""
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw).decode("utf-8-sig", "replace")
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    t = str(data.get("titleId") or "").strip().upper() if isinstance(data, dict) else ""
    return t if ID_RE.match(t) else ""


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
    if os.path.isfile(ico) and os.path.getsize(ico) > 0:
        m.icon = ico
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


# ---------------------------------------------------------------------------- Ordner-Dumps
DUMP_ROOTS = ("/data/homebrew",)


def _dump_index_path(directory=None):
    return os.path.join(directory or cache_dir(), "dumps.json")


def _list_here(ftp, why):
    """Inhalt des aktuellen FTP-Ordners (ohne Pfad-Argument): NLST, dann MLSD, dann LIST."""
    try:
        names = [str(n) for n in ftp.nlst()]
        if names:
            return names
    except (ftplib.Error, OSError, EOFError) as e:
        why.append("NLST " + str(e)[:50])
    if hasattr(ftp, "mlsd"):
        try:
            names = [n for n, _facts in ftp.mlsd() if n not in (".", "..")]
            if names:
                return names
        except (ftplib.Error, OSError, EOFError, AttributeError) as e:
            why.append("MLSD " + str(e)[:50])
    rows, names = [], []
    try:
        ftp.retrlines("LIST", rows.append)
    except (ftplib.Error, OSError, EOFError, AttributeError) as e:
        why.append("LIST " + str(e)[:50])
        return names
    for r in rows:
        parts = r.split(None, 8)
        nm = parts[8] if len(parts) >= 9 else (parts[-1] if parts else "")
        if nm and nm not in (".", ".."):
            names.append(nm)
    return names


def listdir(ftp, path, diag=None):
    """Namen im FTP-Ordner.  Wie FileZilla: erst in den Ordner wechseln (CWD), dann listen - manche Server (ps5-ftpsrv)
    ignorieren den Pfad bei NLST/LIST und liefern dann das Hauptverzeichnis.  Existiert der Ordner nicht (CWD
    scheitert), ist die Liste leer.  diag: Liste, in die (Pfad, Ergebnis) geschrieben wird."""
    diag = diag if diag is not None else []
    why = []
    if hasattr(ftp, "cwd"):
        try:
            ftp.cwd(path)
        except (ftplib.Error, OSError, EOFError) as e:
            diag.append((path, "no such folder (" + str(e)[:40] + ")"))
            return []
        try:
            names = _list_here(ftp, why)
        finally:
            try:
                ftp.cwd("/")
            except (ftplib.Error, OSError, EOFError):
                pass
    else:                                                   # Notfall: Pfad als Argument
        names = []
        try:
            names = [str(n) for n in ftp.nlst(path)]
        except (ftplib.Error, OSError, EOFError) as e:
            why.append("NLST " + str(e)[:50])
    diag.append((path, f"{len(names)} entries" if names else ("empty/" + ", ".join(why) if why else "empty")))
    return names


def index_dumps(ftp, cfg, directory=None, m=None):
    """{Titel-ID: [sce_sys-Ordner]} aus den Dump-Ordnern.  Schon gelesene Ordner kommen aus dem Cache
    (covers/dumps.json); nur neue/umbenannte Ordner werden per FTP gelesen."""
    path = _dump_index_path(directory)
    try:
        with open(path, "r", encoding="utf-8") as f:
            known = json.load(f)
        if not isinstance(known, dict):
            known = {}
    except (OSError, ValueError):
        known = {}
    changed = False
    out = {}
    roots = list(cfg.get("dump_roots") or DUMP_ROOTS)
    for root in roots:
        root = str(root).rstrip("/") or "/"
        names = listdir(ftp, root, m.tried if m is not None else None)
        for n in names:
            base = os.path.basename(str(n).rstrip("/"))
            if not base or base.startswith("."):
                continue
            folder = f"{root}/{base}"
            tid = known.get(folder)
            if not tid:                                 # unbekannt oder frueher ohne Ergebnis: neu lesen
                tid = ""
                for sub in ("sce_sys/param.json", "param.json"):
                    raw = _try(ftp, f"{folder}/{sub}", MAX_JSON, m or Meta())
                    if raw:
                        tid = parse_param_id(raw)
                        if tid:
                            break
                if not tid:
                    mt = TITLE_RE.search(base)          # Notnagel: ID steht im Ordnernamen
                    tid = mt.group(1) if mt else ""
                if tid:                                 # nur Treffer merken (leere Ergebnisse jedes Mal neu versuchen)
                    known[folder] = tid
                    changed = True
            if tid:
                out.setdefault(tid, []).append(folder)
    if changed:
        try:
            _write_atomic(path, json.dumps(known, ensure_ascii=False, indent=0).encode("utf-8"))
        except OSError:
            pass
    return out


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
            _scan(ftp, tid, cfg, m, directory, dumps=index_dumps(ftp, cfg, directory, m))
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


def _scan(ftp, tid, cfg, m, directory, dumps=None):
    pic, ico, js = _cache_paths(tid, directory)
    dirs = [f"{f}/sce_sys" for f in (dumps or {}).get(tid, [])] + [f for f in (dumps or {}).get(tid, [])]
    dirs += [str(d).replace("{id}", tid) for d in (cfg.get("meta_dirs") or [])]
    dirs += [d.format(id=tid) for d in SEARCH_DIRS]
    need_name = not m.name
    need_pic = m.cover_kind != "pic0"
    found_dir = ""
    for d in dirs:
        if not (need_name or need_pic):
            break
        if need_name:
            raw = _try(ftp, f"{d}/param.json", MAX_JSON, m)
            if raw:
                name = parse_param_json(raw)
                if name:
                    m.name, need_name = name, False
                    found_dir = found_dir or d
                    _write_atomic(js, json.dumps({"name": name, "dir": d, "ts": int(time.time())},
                                                 ensure_ascii=False).encode("utf-8"))
        if need_pic:
            img = _try(ftp, f"{d}/pic0.png", MAX_IMAGE, m)
            if img and img.startswith(PNG_MAGIC):
                _write_atomic(pic, img)
                m.cover, m.cover_kind, need_pic = pic, "pic0", False
                found_dir = d
    # icon0.png (quadratisch): fuer die Bibliothek; zugleich Ersatz-Cover, falls es kein pic0.png gibt
    if not m.icon:
        for d in dict.fromkeys(([found_dir] if found_dir else []) + dirs):
            ic = _try(ftp, f"{d}/icon0.png", MAX_IMAGE, m)
            if ic and ic.startswith(PNG_MAGIC):
                _write_atomic(ico, ic)
                m.icon, found_dir = ico, found_dir or d
                break
    if not m.cover and m.icon:
        m.cover, m.cover_kind = m.icon, "icon0"
    if found_dir:
        m.source = found_dir


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


# ---------------------------------------------------------------------------- alle installierten Spiele
TITLE_ROOTS = ("/user/app", "/mnt/ext0/user/app", "/mnt/ext1/user/app",
               "/system_data/priv/appmeta", "/user/appmeta")
TITLE_RE = re.compile(r"(?<![A-Za-z])((?:PPSA|CUSA)\d{5})(?!\d)")


def list_titles(host, cfg=None, ftp_factory=None, directory=None):
    """Titel-IDs aller Spiele, die per FTP in den bekannten App-Ordnern liegen -> (sortierte Liste, Fehlertext)."""
    cfg = cfg or {}
    ftp, _port, err = _connect(host, list(cfg.get("ftp_ports") or DEFAULT_PORTS),
                               float(cfg.get("ftp_timeout", 4)), ftp_factory or ftplib.FTP)
    if ftp is None:
        return [], "FTP nicht erreichbar: " + err
    found = set()
    dm = Meta()
    try:
        found.update(index_dumps(ftp, cfg, directory, dm).keys())
        for root in TITLE_ROOTS:
            names = listdir(ftp, root, dm.tried)
            for n in names:
                mt = TITLE_RE.search(os.path.basename(str(n).rstrip("/")))
                if mt:
                    found.add(mt.group(1))
    finally:
        try:
            ftp.quit()
        except Exception:                                   # noqa: BLE001
            pass
    detail = "; ".join(f"{p}: {r}" for p, r in dm.tried[:14])
    return sorted(found), ("" if found else "no game folders found - " + detail)


def fetch_all(host, cfg=None, progress=None, ftp_factory=None, directory=None, stop=None):
    """Cover + Namen aller gefundenen Spiele holen.  progress(i, n, meta).  -> (Liste von Meta, Fehlertext)."""
    ids, err = list_titles(host, cfg, ftp_factory, directory)
    out = []
    for i, tid in enumerate(ids, 1):
        if stop is not None and stop():
            break
        m = fetch(host, tid, cfg, ftp_factory=ftp_factory, directory=directory)
        out.append(m)
        if progress:
            progress(i, len(ids), m)
    return out, err


def cached(directory=None):
    """Alles, was im Cache liegt: [Meta] (fuer die Bibliothek, auch ohne Verbindung)."""
    d = directory or cache_dir()
    ids = set()
    try:
        for f in os.listdir(d):
            mt = TITLE_RE.match(f)
            if mt:
                ids.add(mt.group(1))
    except OSError:
        return []
    return [_read_cache(t, d) for t in sorted(ids)]
