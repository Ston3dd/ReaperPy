"""updater.py - self-update from GitHub Releases (no GUI code, fully testable).

Flow:  latest_release() -> pick_asset() -> download() -> extract_zip() -> install() -> "restart required".

Safety rules
  * only https and only GitHub hosts (api.github.com, github.com, codeload..., objects/release-assets...),
    every redirect target is checked again
  * size limits for the release JSON, the download and the unpacked archive (zip bombs)
  * SHA-256 check when GitHub reports a digest for the asset
  * zip-slip protection: no absolute paths, no "..", nothing outside the staging folder
  * the archive is unpacked into a staging folder FIRST; live files are only touched after that worked
  * replaced files are moved to a backup folder and restored if anything fails (rollback)
  * a running Windows EXE can be renamed but not overwritten - moving it to the backup folder handles that
  * a file that is still open in the running program (e.g. `_internal/base_library.zip`) cannot even be renamed: it is
    retried a few times (virus scanner, OneDrive), then the new file is stored next to it as `<name>.update_new` and put
    in place by a small helper script after ReaperPy has closed (or at the next start) - see apply_pending()
  * user data (config, profiles, logs, library ...) is never overwritten
  * a git checkout is never overwritten (that is a developer copy: use `git pull`)
"""
import hashlib
import json
import os
import re
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field

import update_check

REPO_DEFAULT = "Ston3dd/ReaperPy"
API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
ALLOWED_HOSTS = (
    "api.github.com", "github.com", "codeload.github.com",
    "objects.githubusercontent.com", "release-assets.githubusercontent.com",
)
USER_AGENT = "ReaperPy-updater"
TIMEOUT = 15
MAX_JSON = 1 << 20                  # 1 MB release description
MAX_DOWNLOAD = 400 << 20            # 400 MB archive
MAX_UNPACKED = 1200 << 20           # 1.2 GB unpacked
MAX_FILES = 20000
STAGING = ".update_tmp"
BACKUP = ".update_backup"
PENDING_SUFFIX = ".update_new"           # new version of a file that was locked while updating
PENDING_FILE = ".update_pending.json"    # {"files": [relative path, ...], "tries": n}
LOCK_RETRIES = 5                          # a locked file is tried this many times ...
LOCK_DELAY = 0.4                          # ... with this many seconds in between
MAX_APPLY_TRIES = 3                       # then the pending files are given up (old version stays)

# never overwritten if they exist (data files)
KEEP_FILES = {"reaperpy_config.json", "applied.json", "scan_filter.json"}
# folders: existing files are kept, missing ones are added (shipped defaults)
KEEP_DIRS_MERGE = {"profiles"}
# folders: not touched at all
SKIP_DIRS = {"logs", "library", "dumps", ".git", STAGING, BACKUP}


class UpdateError(Exception):
    pass


class Cancelled(UpdateError):
    pass


@dataclass
class Release:
    tag: str = ""
    version: str = ""
    notes: str = ""
    html_url: str = ""
    zipball_url: str = ""
    assets: list = field(default_factory=list)      # [{name, url, size, digest}]


# ======================================================================
# Network
# ======================================================================
def allowed_url(url):
    u = urllib.parse.urlparse(str(url))
    return u.scheme == "https" and (u.hostname or "").lower() in ALLOWED_HOSTS


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise UpdateError(f"redirect to a non-GitHub address blocked: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    return urllib.request.build_opener(_SafeRedirect())


def _request(url, accept):
    if not allowed_url(url):
        raise UpdateError(f"address not allowed (https + GitHub only): {url}")
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})


def fetch_json(url, opener=None, timeout=TIMEOUT):
    op = opener or _opener()
    with op.open(_request(url, "application/vnd.github+json"), timeout=timeout) as r:
        raw = r.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise UpdateError("release description too large")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise UpdateError("release description is not a JSON object")
    return data


def parse_release(data):
    tag = str(data.get("tag_name", "")).strip()
    if not tag:
        raise UpdateError("release has no tag")
    update_check.parse_version(tag)                             # ValueError for non-version tags
    rel = Release(tag=tag, version=tag.lstrip("vV"), notes=str(data.get("body") or "")[:4000],
                  html_url=str(data.get("html_url") or ""), zipball_url=str(data.get("zipball_url") or ""))
    for a in data.get("assets") or []:
        name, url = str(a.get("name", "")), str(a.get("browser_download_url", ""))
        if name and allowed_url(url):
            rel.assets.append({"name": name, "url": url, "size": int(a.get("size") or 0),
                               "digest": str(a.get("digest") or "")})
    return rel


def latest_release(repo=REPO_DEFAULT, fetch=None):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or ""):
        raise UpdateError(f"invalid repository name: {repo!r}")
    return parse_release((fetch or fetch_json)(API_LATEST.format(repo=repo)))


@dataclass
class Check:
    status: str = "off"             # off | uptodate | newer | error
    local: str = ""
    release: Release = None
    error: str = ""


def check(repo, current, fetch=None):
    res = Check(local=str(current))
    try:
        res.release = latest_release(repo, fetch)
        res.status = "newer" if update_check.is_newer(res.release.version, current) else "uptodate"
    except urllib.error.HTTPError as e:
        res.status = "error"
        res.error = "no release published yet" if e.code == 404 else f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - network, JSON, SSL ... all become an error result
        res.status, res.error = "error", f"{e.__class__.__name__}: {e}"
    return res


def sidecar_digest(rel, asset_name, opener=None):
    """Pruefsumme aus der Release-Datei `<asset>.sha256` ("sha256:<hex>") oder "" (nicht vorhanden / nicht lesbar)."""
    side = next((a for a in rel.assets if a["name"] == asset_name + ".sha256"), None)
    if not side:
        return ""
    try:
        with (opener or _opener()).open(_request(side["url"], "application/octet-stream"), timeout=TIMEOUT) as r:
            raw = r.read(4097)
        m = re.search(r"\b([0-9a-fA-F]{64})\b", raw[:4096].decode("utf-8", "replace"))
        return f"sha256:{m.group(1).lower()}" if m else ""
    except Exception:  # noqa: BLE001 - Pruefsumme ist eine Zusatzsicherung, kein Grund den Dialog zu sprengen
        return ""


def pick_asset(rel, frozen):
    """-> (url, name, size, digest).  EXE build: the *win64*.zip asset.  Source run: a non-win64 .zip asset
    (e.g. a source package) or GitHub's automatic source archive of the tag."""
    zips = [a for a in rel.assets if a["name"].lower().endswith(".zip")]
    if frozen:
        for a in zips:
            if "win64" in a["name"].lower():
                return a["url"], a["name"], a["size"], a["digest"]
        raise UpdateError("this release has no Windows build (*win64*.zip) attached")
    for a in zips:
        if "win64" not in a["name"].lower():
            return a["url"], a["name"], a["size"], a["digest"]
    if rel.zipball_url and allowed_url(rel.zipball_url):
        return rel.zipball_url, f"{rel.tag}-source.zip", 0, ""
    raise UpdateError("this release has no downloadable source archive")


def download(url, dest, progress=None, cancel=None, expected_size=0, digest="", opener=None, max_bytes=MAX_DOWNLOAD):
    """Stream to `dest`.  progress(done, total).  cancel: threading.Event-like.  Verifies size and sha256 (if given)."""
    op = opener or _opener()
    sha = hashlib.sha256()
    done = 0
    with op.open(_request(url, "application/octet-stream"), timeout=TIMEOUT) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or expected_size or 0) if getattr(r, "headers", None) else expected_size
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled("cancelled")
            chunk = r.read(1 << 16)
            if not chunk:
                break
            done += len(chunk)
            if done > max_bytes:
                raise UpdateError("download larger than the allowed maximum")
            sha.update(chunk)
            f.write(chunk)
            if progress:
                progress(done, total)
    if expected_size and done != expected_size:
        raise UpdateError(f"download incomplete ({done} of {expected_size} bytes)")
    m = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", digest or "")
    if m and sha.hexdigest().lower() != m.group(1).lower():
        raise UpdateError("checksum (SHA-256) does not match the release")
    return done


# ======================================================================
# Unpack
# ======================================================================
def _inside(base, path):
    base, path = os.path.realpath(base), os.path.realpath(path)
    return path == base or path.startswith(base + os.sep)


def extract_zip(zip_path, dest):
    """Unpack safely into `dest` (must be empty/new).  -> number of files."""
    os.makedirs(dest, exist_ok=True)
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise UpdateError(f"not a valid zip archive: {e}") from e
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES:
            raise UpdateError("archive contains too many files")
        if sum(i.file_size for i in infos) > MAX_UNPACKED:
            raise UpdateError("archive is too large when unpacked")
        bad = zf.testzip()
        if bad:
            raise UpdateError(f"archive is damaged ({bad})")
        n = 0
        for info in infos:
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/"):
                raise UpdateError(f"unsafe path in archive: {info.filename}")
            target = os.path.join(dest, *[p for p in name.split("/") if p])
            if not _inside(dest, target):
                raise UpdateError(f"unsafe path in archive: {info.filename}")
            if info.is_dir() or name.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            n += 1
    return n


def find_root(staging):
    """GitHub source archives wrap everything in one folder; the Windows build zip does not."""
    entries = [e for e in os.listdir(staging)]
    if len(entries) == 1 and os.path.isdir(os.path.join(staging, entries[0])):
        return os.path.join(staging, entries[0])
    return staging


def validate_root(root, frozen):
    need = ["ReaperPy.exe"] if frozen else ["gui.py", "version.py"]
    missing = [n for n in need if not os.path.isfile(os.path.join(root, n))]
    if missing:
        raise UpdateError(f"the archive does not look like a ReaperPy package ({', '.join(missing)} missing)")


# ======================================================================
# Install with backup and rollback
# ======================================================================
def _plan(root, target):
    """[(relative path)] of files to install, honouring the data-protection rules."""
    out = []
    for d, dirs, files in os.walk(root):
        rel_dir = os.path.relpath(d, root)
        parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        if parts and parts[0] in SKIP_DIRS:
            dirs[:] = []
            continue
        dirs[:] = [x for x in dirs if not (not parts and x in SKIP_DIRS)]
        for f in files:
            rel = os.path.join(*parts, f) if parts else f
            top = parts[0] if parts else ""
            dst = os.path.join(target, rel)
            if not parts and f in KEEP_FILES and os.path.exists(dst):
                continue
            if top in KEEP_DIRS_MERGE and os.path.exists(dst):
                continue
            out.append(rel)
    return sorted(out)


def _locked(e):
    """True for 'file is in use' / 'access denied' (Windows: WinError 32 / 5)."""
    return isinstance(e, PermissionError) or getattr(e, "winerror", 0) in (5, 32)


def _move_aside(dst, bak):
    """dst -> bak.  A file that is only briefly locked (virus scanner, OneDrive sync) is retried a few times;
    raises the last OSError if it stays locked."""
    for n in range(max(1, LOCK_RETRIES)):
        try:
            os.replace(dst, bak)
            return
        except OSError as e:
            if not _locked(e) or n == max(1, LOCK_RETRIES) - 1:
                raise
            time.sleep(LOCK_DELAY)


def _pending_path(target):
    return os.path.join(target, PENDING_FILE)


def pending(target):
    """Relative paths whose new version is waiting as `<name>.update_new` (empty list if none)."""
    try:
        with open(_pending_path(target), encoding="utf-8") as f:
            data = json.load(f)
        names = [str(x) for x in data.get("files", [])]
    except (OSError, ValueError, AttributeError):
        return []
    return [r for r in names if os.path.isfile(os.path.join(target, r + PENDING_SUFFIX)) and _inside(target, os.path.join(target, r))]


def _save_pending(target, files, tries=0):
    p = _pending_path(target)
    if not files:
        try:
            os.remove(p)
        except OSError:
            pass
        return
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"files": sorted(files), "tries": int(tries)}, f)


def _pending_tries(target):
    try:
        with open(_pending_path(target), encoding="utf-8") as f:
            return int(json.load(f).get("tries", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0


def apply_pending(target, log=None):
    """Put every `<name>.update_new` in place of `<name>`.  Works when the file is no longer locked (program closed).
    -> relative paths that are still waiting."""
    log = log or (lambda m: None)
    left = []
    for rel in pending(target):
        dst = os.path.join(target, rel)
        try:
            os.replace(dst + PENDING_SUFFIX, dst)
        except OSError as e:
            left.append(rel)
            log(f"[update] {rel} is still in use ({e})")
    _save_pending(target, left, _pending_tries(target))
    return left


def discard_pending(target):
    """Give up: remove the waiting files (the old version of those files stays)."""
    for rel in pending(target):
        try:
            os.remove(os.path.join(target, rel + PENDING_SUFFIX))
        except OSError:
            pass
    _save_pending(target, [])


def install(root, target, log=None):
    """Copy the staged package over `target`.  Returns the list of installed relative paths.
    Files that stay locked by the running program are stored as `<name>.update_new` (see pending()/apply_pending()).
    Any failure restores every file replaced so far."""
    log = log or (lambda m: None)
    files = _plan(root, target)
    if not files:
        raise UpdateError("nothing to install")
    backup = os.path.join(target, BACKUP)
    shutil.rmtree(backup, ignore_errors=True)
    done = []                                   # (rel, had_old)
    waiting = []                                # locked files: new version stored as <name>.update_new
    try:
        for rel in files:
            src, dst = os.path.join(root, rel), os.path.join(target, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            had = os.path.exists(dst)
            if had:
                bak = os.path.join(backup, rel)
                os.makedirs(os.path.dirname(bak), exist_ok=True)
                try:
                    _move_aside(dst, bak)       # also works for a running EXE on Windows
                except OSError as e:
                    if not _locked(e):
                        raise
                    shutil.copy2(src, dst + PENDING_SUFFIX)      # in use by the running program: apply after it closed
                    waiting.append(rel)
                    log(f"[update] {rel} is in use - the new version is applied when ReaperPy has closed")
                    continue
            done.append((rel, had))
            shutil.copy2(src, dst)
        if waiting:
            _save_pending(target, waiting)
    except Exception as e:  # noqa: BLE001 - roll back, then report
        log(f"[update] error ({e}) - restoring previous files")
        for rel in waiting:
            try:
                os.remove(os.path.join(target, rel + PENDING_SUFFIX))
            except OSError:
                pass
        for rel, had in reversed(done):
            dst = os.path.join(target, rel)
            try:
                if os.path.exists(dst):
                    os.remove(dst)
                if had:
                    os.replace(os.path.join(backup, rel), dst)
            except OSError as e2:
                log(f"[update] could not restore {rel}: {e2}")
        raise UpdateError(f"installation failed and was rolled back: {e}") from e
    return files


def cleanup(target):
    """Remove leftovers of an earlier update (staging, backups).  Best effort, never raises."""
    for name in (STAGING, BACKUP):
        try:
            shutil.rmtree(os.path.join(target, name), ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass


def is_git_checkout(target):
    return os.path.exists(os.path.join(target, ".git"))


# ======================================================================
# Orchestration
# ======================================================================
def run_update(rel, target, frozen, progress=None, cancel=None, stage=None, log=None, opener=None):
    """Download + unpack + install `rel` into `target`.  stage(name) reports 'download' | 'unpack' | 'install'.
    -> list of installed files.  Raises UpdateError (nothing changed unless install() already ran - then rolled back)."""
    stage = stage or (lambda s: None)
    url, name, size, digest = pick_asset(rel, frozen)
    if not digest:                                                # kein GitHub-Digest -> <asset>.sha256 des Releases
        digest = sidecar_digest(rel, name, opener)
        if not digest and log:
            log(f"no checksum available for {name} - integrity is only protected by HTTPS")
    staging = os.path.join(target, STAGING)
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)
    try:
        zpath = os.path.join(staging, "package.zip")
        stage("download")
        download(url, zpath, progress=progress, cancel=cancel, expected_size=size, digest=digest, opener=opener)
        stage("unpack")
        unpacked = os.path.join(staging, "x")
        extract_zip(zpath, unpacked)
        root = find_root(unpacked)
        validate_root(root, frozen)
        if cancel is not None and cancel.is_set():
            raise Cancelled("cancelled")
        stage("install")
        files = install(root, target, log=log)
        shutil.rmtree(os.path.join(target, BACKUP), ignore_errors=True)     # a locked old EXE is removed at the next start
        return files
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# ======================================================================
# Where to install, when to refuse, restart, background job
# ======================================================================
def target_dir(frozen=None):
    """Folder the running program lives in (next to the EXE, or next to the sources)."""
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if frozen:
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def blocked_reason(target, frozen):
    """'' if a self-update is possible here, else 'git' (developer checkout) or 'readonly' (folder not writable)."""
    if not frozen and is_git_checkout(target):
        return "git"
    if not os.access(target, os.W_OK):
        return "readonly"
    return ""


def restart_command(frozen=None, executable=None, argv=None):
    """Command line that starts the program again with the same arguments."""
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    exe = executable or sys.executable
    argv = list(sys.argv if argv is None else argv)
    if frozen:
        return [exe] + argv[1:]
    script = os.path.abspath(argv[0]) if argv and argv[0] else os.path.join(target_dir(False), "gui.py")
    return [exe, script] + argv[1:]


# Windows batch that waits until the old program has ended, moves the waiting files in place and starts the program.
# Paths come from ENVIRONMENT VARIABLES (never pasted into the script text), so &, ^, % or spaces in a folder name are harmless.
HELPER_SCRIPT = r"""@echo off
chcp 65001 >nul
set /a TRIES=0
:wait
tasklist /NH /FI "PID eq %RP_PID%" 2>nul | find "%RP_PID%" >nul
if not errorlevel 1 (
  set /a TRIES+=1
  if %TRIES% GTR 120 goto done
  ping -n 2 127.0.0.1 >nul
  goto wait
)
set /a TRIES=0
:apply
set LEFT=0
for /f "usebackq delims=" %%R in ("%RP_LIST%") do (
  if exist "%RP_TARGET%\%%R%RP_SUFFIX%" (
    move /Y "%RP_TARGET%\%%R%RP_SUFFIX%" "%RP_TARGET%\%%R" >nul 2>nul
    if exist "%RP_TARGET%\%%R%RP_SUFFIX%" set LEFT=1
  )
)
if "%LEFT%"=="1" (
  set /a TRIES+=1
  if %TRIES% LSS 10 (
    ping -n 2 127.0.0.1 >nul
    goto apply
  )
)
:done
del "%RP_LIST%" >nul 2>nul
start "" /D "%RP_TARGET%" "%RP_EXE%"
(goto) 2>nul & del "%~f0"
"""


def _helper_env(target, exe, files, pid=None):
    """Write the file list and return (script path, environment) for HELPER_SCRIPT."""
    fd, lst = tempfile.mkstemp(prefix="reaperpy_update_", suffix=".lst")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(files) + "\n")
    fd, script = tempfile.mkstemp(prefix="reaperpy_update_", suffix=".cmd")
    with os.fdopen(fd, "w", encoding="ascii", newline="\r\n") as f:
        f.write(HELPER_SCRIPT)
    env = dict(os.environ, RP_PID=str(pid or os.getpid()), RP_LIST=lst, RP_TARGET=target, RP_EXE=exe,
               RP_SUFFIX=PENDING_SUFFIX)
    return script, env


def start_helper(target, exe=None, files=None, popen=None):
    """Windows: start the batch that applies the waiting files after THIS process ended and then starts `exe`.
    The caller must close the program right after this."""
    files = pending(target) if files is None else files
    exe = exe or sys.executable
    script, env = _helper_env(target, exe, files)
    flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    (popen or subprocess.Popen)(["cmd.exe", "/c", script], env=env, cwd=tempfile.gettempdir(), close_fds=True,
                                creationflags=flags)
    return script


def finish_pending(target, frozen=None, log=None, helper=None, windows=None):
    """Call at program start.  Applies files left over from an update that were locked.  -> True if a helper was started
    that restarts the program (the caller must exit at once), else False."""
    if not pending(target):
        _save_pending(target, [])
        return False
    log = log or (lambda m: None)
    if not apply_pending(target, log):
        return False
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    windows = (os.name == "nt") if windows is None else windows
    tries = _pending_tries(target) + 1
    if tries > MAX_APPLY_TRIES or not frozen or not windows:
        discard_pending(target)                           # give up: the old files of those entries stay in use
        log("[update] some files could not be replaced - please unpack the release over the folder by hand")
        return False
    _save_pending(target, pending(target), tries)
    try:
        (helper or start_helper)(target)
    except Exception as e:  # noqa: BLE001
        log(f"[update] helper could not be started ({e})")
        return False
    return True


def restart(cmd=None, cwd=None, helper=None, windows=None):
    """Start the new process; the caller closes the old one afterwards.  If files of the update are still waiting
    (they were in use), a helper applies them after this program ended and starts the program."""
    target = cwd or target_dir()
    windows = (os.name == "nt") if windows is None else windows
    if windows and pending(target):
        exe = (cmd or restart_command())[0]
        (helper or start_helper)(target, exe)
        return
    kw = {"cwd": target, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(cmd or restart_command(), **kw)


def should_offer(chk, skipped=""):
    """Offer a dialog only for a newer release the user has not skipped."""
    return bool(chk and chk.status == "newer" and chk.release and chk.release.version != (skipped or "").lstrip("vV"))


class UpdateJob:
    """Runs run_update() in a thread and reports through `events` (no tkinter in here, so it is testable):
    ("stage", name) | ("progress", done, total) | ("log", text) | ("done", files) | ("cancelled",) | ("error", text)"""

    def __init__(self, rel, target, frozen, run=None):
        self.rel, self.target, self.frozen = rel, target, frozen
        self.run = run or run_update
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()
        return self

    def _work(self):
        put = self.events.put
        try:
            files = self.run(self.rel, self.target, self.frozen,
                             progress=lambda d, t: put(("progress", d, t)), cancel=self.cancel,
                             stage=lambda s: put(("stage", s)), log=lambda m: put(("log", m)))
            put(("done", files))
        except Cancelled:
            put(("cancelled",))
        except Exception as e:  # noqa: BLE001 - every failure is shown to the user; install() already rolled back
            put(("error", str(e) or e.__class__.__name__))
