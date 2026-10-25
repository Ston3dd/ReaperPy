"""cheatfmt.py - Cheat-Dateiformate der Konsolen-Menues: GoldHEN/etaHEN .json, .shn und .mc4.

Alle Formate beschreiben dasselbe: "schreibe diese Bytes an diesen Offset des Spiel-Executables,
wenn der Cheat an ist - und diese Bytes, wenn er aus ist".  Intern arbeitet ReaperPy mit dem
GoldHEN-Dokument (dict), die anderen Formate werden darauf abgebildet:

    {"name", "id", "version", "process", "credits": [..],
     "mods": [{"name", "type": "checkbox"|"button", "memory": [{"offset": "HEX", "on": "HEX",
                                                                  "off": "HEX", "section": 0}]}]}

  .shn   XML   <Trainer Game Moder Cusa Version Process><Cheat Text><Cheatline>
                 <Offset/><Section/><ValueOn/><ValueOff/></Cheatline></Cheat></Trainer>
  .mc4   dasselbe SHN, PKCS#7-aufgefuellt, AES-256-CBC, base64
  .json  GoldHEN / etaHEN (siehe export_goldhen.py)

Formatwissen (SHN-Aufbau, mc4-Schluessel/IV, Dateinamen TITELID_VERSION.ext) nach PS5Debug-studio
von alfizari (Apache-2.0, https://github.com/alfizari/PS5Debug-studio); der Code hier ist eine
eigene Umsetzung.  Der mc4-Schluessel ist der oeffentlich bekannte, den alle mc4-Werkzeuge nutzen.
"""
import base64
import json
import os
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

from aes_cbc import cbc_decrypt, cbc_encrypt, pkcs7_pad, pkcs7_unpad

MC4_KEY = b"304c6528f659c766110239a51cl5dd9c"      # 32 Byte -> AES-256
MC4_IV = b"u@}kzW2u[u(8DWar"                          # 16 Byte

FORMATS = {
    "json": ("GoldHEN / etaHEN JSON (.json)", ".json"),
    "shn": ("SHN-Cheat (.shn)", ".shn"),
    "mc4": ("MC4-Cheat (.mc4, verschluesseltes SHN)", ".mc4"),
}

TITLE_RE = re.compile(r"^(CUSA|PPSA)\d{5}$")


class FormatError(ValueError):
    pass


# ------------------------------------------------------------------ Hilfen
def _hex_clean(text):
    h = re.sub(r"[^0-9A-Fa-f]", "", str(text or "").replace("0x", "").replace("0X", ""))
    if len(h) % 2:
        raise FormatError(f"ungerade Anzahl Hex-Ziffern in '{text}'")
    return h.upper()


def _dash(hexstr):
    return "-".join(hexstr[i:i + 2] for i in range(0, len(hexstr), 2))


def _int_hex(text):
    t = str(text or "0").strip()
    try:
        return int(t, 16)
    except ValueError:
        raise FormatError(f"ungueltiger Offset '{text}'") from None


def new_doc(name="", title_id="", version="", process="eboot.bin", credits=None, mods=None):
    return {"name": name or title_id, "id": title_id, "version": version,
            "process": process or "eboot.bin", "mods": list(mods or []), "credits": list(credits or [])}


def default_filename(doc, fmt):
    tid = (doc.get("id") or "GAME").strip().upper()
    ver = (doc.get("version") or "00.00").strip()
    return f"{tid}_{ver}{FORMATS[fmt][1]}"


# ------------------------------------------------------------------ Pruefung vor dem Schreiben
def check(doc, fmt):
    """-> (fehler, warnungen).  Fehler verhindern das Schreiben, Warnungen nicht."""
    errors, warnings = [], []
    tid = (doc.get("id") or "").strip().upper()
    ver = (doc.get("version") or "").strip()
    if not TITLE_RE.match(tid):
        errors.append(f"Titel-ID '{tid or '(leer)'}' muss CUSA##### oder PPSA##### sein "
                      "(das Cheat-Menue findet die Datei daran)")
    if not re.fullmatch(r"\d{2}\.\d{2,3}(\.\d{3})?", ver):
        errors.append(f"Version '{ver or '(leer)'}' muss die App-Version sein, z.B. 01.05 (PS4) "
                      "oder 01.000.000 (PS5)")
    if not (doc.get("name") or "").strip():
        errors.append("Spielname fehlt")
    if not doc.get("mods"):
        errors.append("keine Mods enthalten")
    if not doc.get("credits"):
        warnings.append("keine Credits/Autor - das Feld 'Moder' bleibt leer")
    for m in doc.get("mods", []):
        nm = m.get("name", "?")
        if not m.get("memory"):
            errors.append(f"'{nm}': keine memory-Eintraege")
        if fmt != "json" and str(m.get("type", "checkbox")).lower() == "button":
            warnings.append(f"'{nm}': Button (einmalig) - {fmt.upper()} kennt nur An/Aus, wird als "
                            "Schalter exportiert")
        for e in m.get("memory", []):
            on, off = _hex_clean(e.get("on", "")), _hex_clean(e.get("off", ""))
            if not on:
                errors.append(f"'{nm}' @ {e.get('offset')}: leerer on-Wert")
            if len(on) != len(off):
                errors.append(f"'{nm}' @ {e.get('offset')}: on/off verschieden lang")
            if fmt == "json" and int(e.get("section", 0) or 0):
                errors.append(f"'{nm}' @ {e.get('offset')}: GoldHEN-JSON kennt nur Section 0 "
                              "(als .shn/.mc4 exportieren)")
    return errors, warnings


# ------------------------------------------------------------------ SHN
def build_shn(doc, declared="utf-8"):
    """GoldHEN-Dokument -> SHN-Text (CRLF wie bei bestehenden Dateien)."""
    nl = "\r\n"
    tid = (doc.get("id") or "").strip().upper()
    mod_by = ", ".join(str(c).strip() for c in doc.get("credits", []) if str(c).strip())
    out = [f'<?xml version="1.0" encoding="{declared}"?>',
           '<Trainer xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
           'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
           f' Game={quoteattr(str(doc.get("name") or tid))} Moder={quoteattr(mod_by)} Cusa={quoteattr(tid)}'
           f' Version={quoteattr(str(doc.get("version", "")).strip())}'
           f' Process={quoteattr(str(doc.get("process") or "eboot.bin"))}>',
           "  <Items />"]
    for m in doc.get("mods", []):
        out.append(f"  <Cheat Text={quoteattr(str(m.get('name', 'Cheat')))}>")
        for e in m.get("memory", []):
            out += ["    <Cheatline>",
                    f"      <Offset>{_int_hex(e.get('offset')):X}</Offset>",
                    f"      <Section>{int(e.get('section', 0) or 0)}</Section>",
                    f"      <ValueOn>{_dash(_hex_clean(e.get('on')))}</ValueOn>",
                    f"      <ValueOff>{_dash(_hex_clean(e.get('off')))}</ValueOff>",
                    "    </Cheatline>"]
        out.append("  </Cheat>")
    out.append("</Trainer>")
    return nl.join(out)


def parse_shn(text):
    """SHN-Text -> GoldHEN-Dokument."""
    m = re.search(r"<Trainer\b.*</Trainer>", text, flags=re.DOTALL)
    body = (m.group(0) if m else text).strip().lstrip("\ufeff")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        # alte mc4-Werkzeuge schreiben die Entities doppelt maskiert -> nur im Notfall aufloesen
        fixed = (body.replace("&lt;", "<").replace("&gt;", ">").replace("\\&quot;", '"')
                 .replace("\\&apos;", "'").replace("&quot;", '"').replace("&apos;", "'"))
        try:
            root = ET.fromstring(fixed)
        except ET.ParseError as e:
            raise FormatError(f"kein gueltiges SHN-XML: {e}") from None
    if root.tag != "Trainer":
        raise FormatError("kein SHN-Trainer (Wurzelelement <Trainer> fehlt)")
    mods = []
    for ch in root.findall("Cheat"):
        memory = []
        for cl in ch.findall("Cheatline"):
            memory.append({"offset": f"{_int_hex(cl.findtext('Offset')):X}",
                           "section": int((cl.findtext("Section") or "0").strip() or 0),
                           "on": _hex_clean(cl.findtext("ValueOn")),
                           "off": _hex_clean(cl.findtext("ValueOff"))})
        if memory:
            mods.append({"name": ch.get("Text") or "Cheat", "type": "checkbox", "memory": memory})
    tid = (root.get("Cusa") or "").strip().upper()
    moder = (root.get("Moder") or "").strip()
    return new_doc(root.get("Game") or tid, tid, (root.get("Version") or "").strip(),
                   root.get("Process") or "eboot.bin",
                   [c.strip() for c in moder.split(",") if c.strip()], mods)


# ------------------------------------------------------------------ MC4
def build_mc4(doc):
    """GoldHEN-Dokument -> .mc4-Bytes.  (Das XML traegt 'utf-16' im Kopf, die Bytes sind utf-8 -
    so sehen die vorhandenen mc4-Dateien aus.)"""
    text = build_shn(_sanitized(doc), declared="utf-16").encode("utf-8")
    return base64.b64encode(cbc_encrypt(MC4_KEY, MC4_IV, pkcs7_pad(text)))


def decrypt_mc4(data):
    """.mc4-Bytes -> SHN-Text."""
    try:
        raw = base64.b64decode(re.sub(rb"\s+", b"", bytes(data)), validate=False)
    except Exception as e:
        raise FormatError(f"keine mc4-Datei (base64): {e}") from None
    if not raw or len(raw) % 16:
        raise FormatError("keine mc4-Datei (Laenge passt nicht zu AES)")
    text = pkcs7_unpad(cbc_decrypt(MC4_KEY, MC4_IV, raw)).decode("utf-8", "ignore")
    if "<Trainer" not in text:
        raise FormatError("mc4 laesst sich nicht entschluesseln (falsche Datei?)")
    return text


def _sanitized(doc):
    """Aeltere mc4-Leser loesen &quot; &amp; ... blind auf und zerbrechen damit das XML.
    Fuer mc4 deshalb Sonderzeichen aus den Texten nehmen."""
    bad = str.maketrans({"&": "+", "<": "(", ">": ")", '"': "'"})
    d = dict(doc)
    d["name"] = str(doc.get("name", "")).translate(bad)
    d["credits"] = [str(c).translate(bad) for c in doc.get("credits", [])]
    d["mods"] = [dict(m, name=str(m.get("name", "")).translate(bad)) for m in doc.get("mods", [])]
    return d


# ------------------------------------------------------------------ JSON
def build_json(doc):
    d = {"name": doc.get("name"), "id": (doc.get("id") or "").strip().upper(),
         "version": (doc.get("version") or "").strip(), "process": doc.get("process") or "eboot.bin",
         "mods": [{"name": m["name"], "type": m.get("type", "checkbox"),
                   "memory": [{"offset": f"{_int_hex(e['offset']):X}", "on": _hex_clean(e["on"]),
                               "off": _hex_clean(e["off"])} for e in m["memory"]]}
                  for m in doc.get("mods", [])],
         "credits": list(doc.get("credits", []))}
    return json.dumps(d, indent=2, ensure_ascii=False)


def parse_json(text):
    d = json.loads(text.lstrip("\ufeff"))
    if not isinstance(d, dict) or not isinstance(d.get("mods"), list):
        raise FormatError("keine GoldHEN/etaHEN-Cheat-JSON (Feld 'mods' fehlt)")
    mods = []
    for m in d["mods"]:
        mem = [{"offset": f"{_int_hex(e['offset']):X}", "section": 0,
                "on": _hex_clean(e.get("on", "")), "off": _hex_clean(e.get("off", ""))}
               for e in (m.get("memory") or [])]
        mods.append({"name": str(m.get("name") or "Mod"), "type": str(m.get("type") or "checkbox").lower(),
                     "memory": mem})
    return new_doc(str(d.get("name") or d.get("id") or ""), str(d.get("id") or "").upper(),
                   str(d.get("version") or ""), str(d.get("process") or "eboot.bin"),
                   [str(c) for c in d.get("credits", [])], mods)


# ------------------------------------------------------------------ Dateien
def detect(path, data=None):
    """'json' | 'shn' | 'mc4' nach Endung, sonst nach Inhalt."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in FORMATS:
        return ext
    if data is None:
        with open(path, "rb") as f:
            data = f.read(4096)
    head = bytes(data).lstrip(b"\xef\xbb\xbf \r\n\t")
    if head.startswith((b"<?xml", b"<Trainer")):
        return "shn"
    if head.startswith(b"{"):
        return "json"
    return "mc4"


def load_file(path):
    """Beliebige Cheat-Datei (.json/.shn/.mc4) -> GoldHEN-Dokument."""
    with open(path, "rb") as f:
        data = f.read()
    fmt = detect(path, data)
    if fmt == "json":
        return parse_json(data.decode("utf-8-sig"))
    if fmt == "shn":
        return parse_shn(data.decode("utf-8-sig", "replace"))
    return parse_shn(decrypt_mc4(data))


def build(doc, fmt):
    """-> bytes im gewuenschten Format (prueft vorher mit check())."""
    errors, _w = check(doc, fmt)
    if errors:
        raise FormatError("; ".join(errors))
    if fmt == "json":
        return build_json(doc).encode("utf-8")
    if fmt == "shn":
        return build_shn(doc).encode("utf-8")
    if fmt == "mc4":
        return build_mc4(doc)
    raise ValueError(fmt)


def save_file(doc, path, fmt=None):
    fmt = fmt or detect(path, b"")
    data = build(doc, fmt)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def merge_into_docs(a, b):
    """Zwei Dokumente desselben Spiels zusammenfuehren (Mods von b hinten anhaengen, gleiche Namen
    werden uebersprungen)."""
    names = {m["name"] for m in a.get("mods", [])}
    out = dict(a, mods=list(a.get("mods", [])), credits=list(dict.fromkeys(
        list(a.get("credits", [])) + list(b.get("credits", [])))))
    for m in b.get("mods", []):
        if m["name"] not in names:
            out["mods"].append(m)
    return out
