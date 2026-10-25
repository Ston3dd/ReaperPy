"""update_check.py - Prueft, ob es eine neuere ReaperPy-Version gibt.  Laedt NIE etwas herunter und sendet keine Daten.

Es wird nur eine kleine JSON-Datei gelesen, deren Adresse du selbst in der Konfiguration einstellst ("update_url"):
    {"version": "5.8.0", "url": "https://.../download", "notes": "Was ist neu"}
Ohne "update_url" ist die Pruefung aus.  Nur https (http nur fuer localhost); Antwort hoechstens 64 KB.
"""
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

MAX_BYTES = 65536
TIMEOUT = 6


def parse_version(v):
    """'v5.7.0-beta1' -> ((5, 7, 0), 0, 'beta1');  Release sortiert ueber Vorabversion gleicher Nummer."""
    m = re.match(r"^(\d+(?:\.\d+)*)(?:[-+](.+))?$", str(v).strip().lstrip("vV"))
    if not m:
        raise ValueError(f"keine Versionsnummer: {v!r}")
    nums = [int(x) for x in m.group(1).split(".")][:4]
    nums += [0] * (3 - len(nums))
    pre = m.group(2) or ""
    return tuple(nums), (0 if pre else 1), pre


def is_newer(remote, local):
    return parse_version(remote) > parse_version(local)


def _allowed_url(url, allow_local_http=True):
    u = urllib.parse.urlparse(str(url))
    if u.scheme == "https" and u.netloc:
        return True
    return allow_local_http and u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1")


def fetch_json(url, timeout=TIMEOUT, opener=None):
    if not _allowed_url(url):
        raise ValueError("Update-Adresse muss mit https:// beginnen")
    req = urllib.request.Request(url, headers={"User-Agent": "ReaperPy-update-check", "Accept": "application/json"})
    op = opener or urllib.request.build_opener()
    with op.open(req, timeout=timeout) as r:
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Antwort zu gross")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Antwort ist kein JSON-Objekt")
    return data


@dataclass
class Result:
    status: str = "off"          # off | uptodate | newer | error
    local: str = ""
    remote: str = ""
    url: str = ""
    notes: str = ""
    error: str = ""


def check(url, current, fetch=None):
    res = Result(local=str(current))
    if not url:
        return res
    try:
        data = (fetch or fetch_json)(url)
        res.remote = str(data["version"]).strip()
        dl = str(data.get("url", "")).strip()
        res.url = dl if dl and _allowed_url(dl, allow_local_http=False) else ""      # nur https-Links weitergeben
        res.notes = str(data.get("notes", ""))[:500]
        res.status = "newer" if is_newer(res.remote, current) else "uptodate"
    except (KeyError, ValueError, TypeError, OSError, json.JSONDecodeError) as e:
        res.status, res.error = "error", f"{e.__class__.__name__}: {e}"
    except Exception as e:  # noqa: BLE001 - urllib wirft viele Arten (URLError, timeout, ssl)
        res.status, res.error = "error", f"{e.__class__.__name__}: {e}"
    return res
