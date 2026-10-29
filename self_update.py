"""self_update.py - Neue ReaperPy-Version von GitHub-Releases laden und neben dem laufenden Programm entpacken.

Ablauf (alles ausser dem Aufruf von `check` laeuft erst nach ausdruecklicher Zustimmung in der GUI):

  1. check():   fragt https://api.github.com/repos/<repo>/releases/latest  (nur lesen, keine Daten werden gesendet)
  2. download(): laedt das Asset `ReaperPy_v<ver>_win64.zip` (nur https, nur GitHub-Hosts, Groessenlimit)
  3. SHA-256 gegen die Datei `<asset>.sha256` des Releases pruefen - ohne Pruefsumme wird NICHT automatisch installiert
  4. install(): Zip pruefen (kein Pfad ausserhalb des Zielordners), alles als `*.rpnew` neben die Ziele schreiben, dann
     jede Zieldatei nach `*.old` umbenennen und die neue an ihren Platz stellen.  Schlaegt etwas fehl, wird alles
     zurueckgedreht.  Umbenennen funktioniert auch bei der laufenden EXE/DLL unter Windows (ueberschreiben nicht);
     was nicht sofort geloescht werden kann, steht in `.reaperpy_old.json` und wird beim naechsten Start entfernt.

Eigene Daten (Konfiguration, Profile, Bibliothek, Logs ...) werden nie angefasst (PROTECTED).
Ausserhalb der gepackten EXE (python gui.py) wird nichts ueberschrieben - dort bleibt es beim Hinweis + Release-Seite.
"""
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass

import update_check as U

DEFAULT_REPO = "Ston3dd/ReaperPy"
API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
ALLOWED_HOSTS = {"github.com", "api.github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
USER_AGENT = "ReaperPy-self-update"
ASSET_RE = re.compile(r"^ReaperPy_v[\w.+-]+_win64\.zip$")
MAX_API_BYTES = 1 << 20
MAX_ZIP_BYTES = 400 << 20
MAX_UNPACKED_BYTES = 2 << 30
MAX_FILES = 30000
TIMEOUT = 15
OLD_LIST = ".reaperpy_old.json"
# Oberste Ebene im Programmordner, die ein Update nie ueberschreibt (Benutzerdaten)
PROTECTED = {"reaperpy_config.json", "applied.json", "scan_filter.json", "profiles", "library", "logs", "trainer",
             "dumps", "patches", OLD_LIST}


class UpdateError(Exception):
    pass


@dataclass
class Release:
    tag: str = ""
    version: str = ""
    notes: str = ""
    html_url: str = ""
    asset_name: str = ""
    asset_url: str = ""
    asset_size: int = 0
    sha_url: str = ""


@dataclass
class GhResult(U.Result):
    release: object = None          # Release | None


# ------------------------------------------------------------------ Pruefen
def host_ok(url):
    u = urllib.parse.urlparse(str(url))
    h = (u.hostname or "").lower()
    return u.scheme == "https" and bool(h) and (h in ALLOWED_HOSTS or h.endswith(".githubusercontent.com"))


def valid_repo(repo):
    m = re.fullmatch(r"([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})", str(repo or ""))
    return bool(m) and not any(set(g) == {"."} for g in m.groups())          # kein '.' / '..' als Teil


def _get(url, timeout=TIMEOUT, opener=None, limit=MAX_API_BYTES, accept="application/vnd.github+json"):
    if not host_ok(url):
        raise UpdateError(f"Adresse nicht erlaubt: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with (opener or urllib.request.build_opener()).open(req, timeout=timeout) as r:
        final = getattr(r, "geturl", lambda: url)()
        if not host_ok(final):
            raise UpdateError(f"Weiterleitung auf nicht erlaubten Host: {final}")
        raw = r.read(limit + 1)
    if len(raw) > limit:
        raise UpdateError("Antwort zu gross")
    return raw


def parse_release(data):
    """GitHub-JSON -> Release (None bei Entwurf/Vorabversion/ohne passendes Asset)."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name", "")).strip()
    if not tag:
        return None
    U.parse_version(tag)                                        # ValueError bei Unsinn
    assets = {a.get("name"): a for a in data.get("assets", []) if isinstance(a, dict)}
    rel = Release(tag=tag, version=tag.lstrip("vV"), notes=str(data.get("body") or "")[:4000],
                  html_url=str(data.get("html_url") or ""))
    for name, a in sorted(assets.items(), key=lambda kv: str(kv[0])):
        if isinstance(name, str) and ASSET_RE.match(name) and host_ok(a.get("browser_download_url", "")):
            rel.asset_name, rel.asset_url = name, a["browser_download_url"]
            rel.asset_size = int(a.get("size") or 0)
            sha = assets.get(name + ".sha256")
            if sha and host_ok(sha.get("browser_download_url", "")):
                rel.sha_url = sha["browser_download_url"]
            break
    if not host_ok(rel.html_url):
        rel.html_url = ""
    return rel


def check(repo, current, fetch=None):
    """Neuester Release gegen die laufende Version.  `fetch(url) -> bytes` ist fuer Tests austauschbar."""
    res = GhResult(local=str(current))
    try:
        if not valid_repo(repo):
            raise UpdateError(f"ungueltiges Repository: {repo!r}")
        raw = (fetch or _get)(API_LATEST.format(repo=repo))
        rel = parse_release(json.loads(raw.decode("utf-8")))
        if rel is None:
            res.status = "uptodate"
            return res
        res.remote, res.release, res.url = rel.version, rel, rel.html_url
        res.notes = rel.notes[:500]
        res.status = "newer" if U.is_newer(rel.version, current) else "uptodate"
    except Exception as e:  # noqa: BLE001 - Netzwerk/JSON/SSL: der Start darf daran nie scheitern
        res.status, res.error = "error", f"{e.__class__.__name__}: {e}"
    return res


# ------------------------------------------------------------------ Laden
def parse_sha256(text):
    m = re.search(r"\b([0-9a-fA-F]{64})\b", text or "")
    if not m:
        raise UpdateError("Pruefsumme nicht lesbar")
    return m.group(1).lower()


def download(url, dest, progress=None, opener=None, max_bytes=MAX_ZIP_BYTES, timeout=TIMEOUT):
    """Datei laden und SHA-256 zurueckgeben.  progress(done, total) wird hoechstens ~100x aufgerufen."""
    if not host_ok(url):
        raise UpdateError(f"Adresse nicht erlaubt: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
    h, done, last = hashlib.sha256(), 0, -1
    with (opener or urllib.request.build_opener()).open(req, timeout=timeout) as r:
        final = getattr(r, "geturl", lambda: url)()
        if not host_ok(final):
            raise UpdateError(f"Weiterleitung auf nicht erlaubten Host: {final}")
        total = int(getattr(r, "headers", {}).get("Content-Length", 0) or 0) if hasattr(r, "headers") else 0
        if total > max_bytes:
            raise UpdateError("Download zu gross")
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                done += len(chunk)
                if done > max_bytes:
                    raise UpdateError("Download zu gross")
                h.update(chunk)
                f.write(chunk)
                pct = int(done * 100 / total) if total else -1
                if progress and pct != last:
                    progress(done, total)
                    last = pct
    return h.hexdigest()


# ------------------------------------------------------------------ Installieren
def can_self_update(target_dir, frozen):
    return bool(frozen) and os.path.isdir(target_dir) and os.access(target_dir, os.W_OK)


def _rel_ok(name):
    """Zip-Eintrag -> bereinigter relativer Pfad oder None (abgelehnt)."""
    n = name.replace("\\", "/")
    if not n or n.startswith("/") or re.match(r"^[A-Za-z]:", n) or "\x00" in n:
        return None
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def plan_members(zf, required=None):
    """Liste (Zip-Info, relativer Pfad) der zu installierenden Dateien - wirft UpdateError bei Auffaelligkeiten."""
    out, total = [], 0
    for info in zf.infolist():
        rel = _rel_ok(info.filename)
        if rel is None:
            raise UpdateError(f"Unsicherer Pfad im Archiv: {info.filename!r}")
        if info.is_dir():
            continue
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise UpdateError(f"Symlink im Archiv: {info.filename!r}")
        if rel.split("/")[0] in PROTECTED:
            continue
        total += info.file_size
        out.append((info, rel))
        if len(out) > MAX_FILES or total > MAX_UNPACKED_BYTES:
            raise UpdateError("Archiv zu gross")
    if required and required not in {r for _, r in out}:
        raise UpdateError(f"{required} fehlt im Archiv - falsches Paket?")
    return out


def install(zip_path, target_dir, required=None, progress=None):
    """Zip nach target_dir entpacken (mit Rollback).  Gibt die Anzahl ersetzter/neuer Dateien zurueck."""
    target_dir = os.path.abspath(target_dir)
    staged, swapped, new_files = [], [], []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = plan_members(zf, required)
            for i, (info, rel) in enumerate(members):
                dest = os.path.abspath(os.path.join(target_dir, *rel.split("/")))
                if os.path.commonpath([target_dir, dest]) != target_dir:
                    raise UpdateError(f"Pfad ausserhalb des Programmordners: {rel}")
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                tmp = dest + ".rpnew"
                with zf.open(info) as src, open(tmp, "wb") as out:
                    while True:
                        chunk = src.read(1 << 16)
                        if not chunk:
                            break
                        out.write(chunk)
                staged.append((dest, tmp))
                if progress and (i % 50 == 0 or i == len(members) - 1):
                    progress(i + 1, len(members))
        # Phase 2: umschalten.  Bestehende Datei -> .old (geht auch fuer die laufende EXE), dann neue an die Stelle.
        for dest, tmp in staged:
            old = None
            if os.path.exists(dest):
                old = dest + ".old"
                if os.path.exists(old):
                    try:
                        os.remove(old)
                    except OSError:
                        old = f"{dest}.{os.getpid()}.old"
                os.replace(dest, old)
            swapped.append((dest, old))
            os.replace(tmp, dest)
    except BaseException:
        for dest, old in reversed(swapped):                       # zurueckdrehen
            try:
                if os.path.exists(dest):
                    os.remove(dest)
                if old:
                    os.replace(old, dest)
            except OSError:
                pass
        for _dest, tmp in staged:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
        raise
    leftovers = []
    for _dest, old in swapped:
        if old:
            try:
                os.remove(old)
            except OSError:                                        # Windows: laufende EXE/DLL - spaeter loeschen
                leftovers.append(os.path.relpath(old, target_dir).replace(os.sep, "/"))
    _save_old_list(target_dir, leftovers)
    return len(swapped)


def _save_old_list(target_dir, items):
    p = os.path.join(target_dir, OLD_LIST)
    try:
        if items:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(sorted(set(items)), f)
        elif os.path.exists(p):
            os.remove(p)
    except OSError:
        pass


def cleanup_old(target_dir):
    """Beim Start: `.old`-Dateien eines frueheren Updates entfernen.  Gibt die Zahl der geloeschten zurueck."""
    p = os.path.join(target_dir, OLD_LIST)
    try:
        with open(p, encoding="utf-8") as f:
            items = json.load(f)
    except (OSError, ValueError):
        return 0
    base, n, rest = os.path.abspath(target_dir), 0, []
    for rel in items if isinstance(items, list) else []:
        full = os.path.abspath(os.path.join(base, *str(rel).split("/")))
        if not full.endswith(".old") or os.path.commonpath([base, full]) != base:
            continue                                               # nur eigene .old-Dateien, nie etwas anderes
        try:
            if os.path.exists(full):
                os.remove(full)
            n += 1
        except OSError:
            rest.append(rel)
    _save_old_list(base, rest)
    return n


def run_update(rel, target_dir, progress=None, work_dir=None, opener=None, required="ReaperPy.exe"):
    """Komplettablauf: laden -> Pruefsumme -> installieren.  progress(stage, done, total)."""
    import tempfile
    if not rel.asset_url:
        raise UpdateError("Release enthaelt kein Windows-Paket")
    if not rel.sha_url:
        raise UpdateError("Release enthaelt keine Pruefsumme (.sha256) - nicht automatisch installiert")
    note = progress or (lambda *a: None)
    tmpdir = tempfile.mkdtemp(prefix="reaperpy_update_", dir=work_dir)
    zpath = os.path.join(tmpdir, rel.asset_name)
    try:
        expected = parse_sha256(_get(rel.sha_url, opener=opener, limit=4096, accept="application/octet-stream")
                                .decode("utf-8", "replace"))
        got = download(rel.asset_url, zpath, progress=lambda d, t: note("download", d, t), opener=opener)
        note("verify", 1, 1)
        if got != expected:
            raise UpdateError("Pruefsumme stimmt nicht - Datei verworfen")
        n = install(zpath, target_dir, required=required, progress=lambda d, t: note("install", d, t))
        return n
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
