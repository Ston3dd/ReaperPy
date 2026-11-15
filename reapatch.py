"""reapatch.py – Patch-Dateien parsen (ReapProj, Shnext, JSON, SHN, MC4)."""
import json, os, re

# Alle bekannten Patch-Erweiterungen (case-insensitive)
PATCH_EXTENSIONS = (
    ".reapproj", ".ReapProj", ".REAPROJ",
    ".reapatch", ".ReapPatch", ".REAPATCH",
    ".shnext", ".Shnext", ".SHNEXT",
    ".shn", ".SHN", ".shnxml",
    ".mc4", ".MC4",
    ".json", ".JSON",
    ".reap", ".Reap",
    ".rpe", ".RPE",
)

# Dateien, die zwar eine Patch-Endung haben (z.B. .json), aber KEINE Patches
# sind (Config des Programms usw.). Kleingeschrieben eintragen.
IGNORED_FILES = {
    "reaperpy_config.json",
    "applied.json",            # Zustandsdatei von ReaperPy (liegt im Patch-Ordner!)
    "pointer_paths.json",
}
IGNORED_SUFFIXES = (".cheatsession.json",)


def is_patch_file(name: str) -> bool:
    """Prüft ob eine Datei eine bekannte Patch-Datei ist."""
    low = os.path.basename(name).lower()
    if low in IGNORED_FILES or low.endswith(IGNORED_SUFFIXES):
        return False
    return any(low.endswith(ext.lower()) for ext in PATCH_EXTENSIONS)


def _read_text(path: str) -> str:
    """Datei als Text lesen: UTF-8 mit/ohne BOM, Notfalls UTF-16 / cp1252."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("utf-8-sig", errors="replace")


def _to_int(v, default=0):
    """Zahl tolerant lesen (int, float, '0x..', '123', None)."""
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v.strip(), 0)
        except Exception:
            return default
    return default


class ShnExtEncrypted(ValueError):
    """ShnExt-Container mit verschlüsselten Patch-Einträgen (wird nicht entschlüsselt)."""


def read_shnext_container(path):
    """Liest nur die äußere Hülle einer .ShnExt (Raw-Deflate -> JSON).
    Rückgabe: dict mit Metadaten oder None, wenn die Datei kein solcher Container ist."""
    import zlib
    try:
        with open(path, "rb") as f:
            raw = f.read()
        data = json.loads(zlib.decompress(raw, -15).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or "patchEntries" not in data:
        return None
    return {
        "modder": ", ".join(data.get("Modder") or []),
        "game": data.get("Game", ""),
        "cusa": data.get("Cusa", ""),
        "version": data.get("Version", ""),
        "entries": len(data.get("patchEntries") or []),
    }


class ReapPatch:
    """Repräsentiert eine geladene Patch-Datei (ReapProj/Shnext/JSON)."""

    def __init__(self, path: str):
        self.path = path
        self.name = os.path.basename(path)
        self.author = ""
        self.origin_source = None          # (offset:int, default_asm:str, new_asm:str)
        self.origin_return_offset = 8
        self.extra_sources = []            # weitere Patch-Stellen: [(offset, default_asm, new_asm), ...]
        self.origin_aob = ""               # optionale Signatur ("48 8B ?? ...") für Auto-Update
        self.origin_aob_offset = 0         # Hook = Treffer + origin_aob_offset
        self.labels = []                   # [(label:str, asm:str), ...]
        self.raw = {}                      # originale JSON-Daten
        self.native = False                # Reaper-Originalformat: jede Quelle hat eine eigene Signatur (offsetFinder)
        self.src_info = []                 # parallel zu sites(): {"label", "aob", "aob_offset"}
        self.native_returns = {}           # Return-Name -> (Quell-Label, Abstand)
        self.variables = []                # [(name, typ, default, new)] - Schalter/Werte, liegen in der Cave
        self.var_meta = {}                 # name -> {"display", "comment"} (Anzeige im Werte-Dialog)
        self.var_values = {}               # name -> vom Nutzer gewaehlter Wert (ueberschreibt newValue)
        self.nohook_info = ""              # Diagnose, falls keine Patch-Stelle gefunden wurde
        self.file_type = "unknown"         # 'reapproj', 'shnext', 'json', 'shn'

    @classmethod
    def load(cls, path: str):
        """Lädt eine Patch-Datei, erkennt das Format automatisch."""
        p = cls(path)
        ext = os.path.splitext(path)[1].lower()

        # --- Shnext / SHN (XML-artig oder JSON) ---
        if ext in (".shnext", ".shn", ".shnxml", ".mc4"):
            p.file_type = "shnext"
            meta = read_shnext_container(path)
            if meta:
                raise ShnExtEncrypted(
                    f"ShnExt von {meta['modder'] or '?'} ({meta['cusa']} v{meta['version']}): "
                    f"{meta['entries']} Patch-Einträge sind verschlüsselt und werden nicht unterstützt. "
                    f"Klartext-Patches (.reapproj/.json) verwenden.")
            try:
                p._load_shnext(path)
            except Exception:
                # Fallback: als JSON probieren
                p._load_json(path)
            p._finalize()
            return p

        # --- Alles andere als JSON laden ---
        p.file_type = "reapproj" if "reap" in ext or "proj" in ext else "json"
        p._load_json(path)
        p._finalize()
        return p

    def _finalize(self):
        """Wenn nur Zusatz-Stellen existieren, die erste zur Haupt-Stelle machen.
        Fehlt jede OriginSource, wird aus beliebigen Eintraegen mit Adresse/Signatur + newValue eine Stelle gebaut."""
        if self.origin_source is None and not self.extra_sources:
            self._adopt_generic()
        if self.origin_source is None and self.extra_sources:
            self.origin_source = self.extra_sources.pop(0)
        if self.origin_source is None:
            self.nohook_info = self._describe_nohook()

    def _describe_nohook(self):
        """Kurze Beschreibung, was in der Datei steht (fuers Log, damit man das Format erkennt)."""
        data = self.raw if isinstance(self.raw, dict) else {}
        vs = data.get("Variables") or data.get("variables") or []
        rows = []
        for v in vs[:12] if isinstance(vs, list) else []:
            if isinstance(v, dict):
                rows.append("%s(type=%s,off=%s,static=%s,nv=%s)" % (
                    v.get("label"), v.get("type"), v.get("offset"), v.get("isStatic"),
                    "ja" if str(v.get("newValue") or "").strip() else "leer"))
        return "Eintraege: " + "; ".join(rows) if rows else "keine 'Variables' gefunden, Schluessel: " + ", ".join(map(str, list(data)[:12]))

    def _adopt_generic(self):
        """Patches ohne 'OriginSource' (andere Reaper-Varianten): jeder Eintrag mit Adresse (offset) oder
        Signatur (offsetFinder) und einem Text-newValue ist eine Patch-Stelle."""
        data = self.raw if isinstance(self.raw, dict) else {}
        variables = (data.get("Variables") or data.get("variables") or data.get("cheats") or
                     data.get("Cheats") or data.get("items") or data.get("codes") or data.get("Codes") or [])
        if not isinstance(variables, list):
            return
        for v in variables:
            if not isinstance(v, dict):
                continue
            nv = v.get("newValue", v.get("NewValue"))
            if not isinstance(nv, str) or not nv.strip():
                continue
            dv = v.get("defaultValue", v.get("DefaultValue"))
            dv = dv if isinstance(dv, str) else ""
            off = _to_int(v.get("offset", v.get("Offset", 0)))
            finder = v.get("offsetFinder") or v.get("OffsetFinder")
            if not off and not (isinstance(finder, str) and finder.strip()):
                continue
            if self.origin_source is None and not self.extra_sources and isinstance(finder, str) and finder.strip():
                self.origin_aob = finder.strip()
                self.origin_aob_offset = 0
            self.extra_sources.append((off, dv, nv))

    @property
    def has_hook(self) -> bool:
        """True, wenn der Patch eine anwendbare Stelle hat (sonst wird er nur angezeigt)."""
        return self.origin_source is not None

    def sites(self):
        """Alle Patch-Stellen: [(offset, default_asm, new_asm), ...]."""
        out = []
        if self.origin_source:
            out.append(self.origin_source)
        out.extend(self.extra_sources)
        return out

    # ------------------------------------------------------------------
    # JSON-basierte Formate (ReapProj, Reapatch, reines JSON)
    # ------------------------------------------------------------------
    def _load_json(self, path: str):
        data = json.loads(_read_text(path))
        if isinstance(data, list):                      # manche Dateien sind direkt eine Variablen-Liste
            data = {"Variables": data}
        if not isinstance(data, dict):
            data = {}
        self.raw = data

        # Meta
        self.name = (data.get("name") or data.get("Name") or
                     data.get("title") or data.get("Title") or
                     os.path.basename(path))
        self.author = (data.get("author") or data.get("Author") or
                       data.get("creator") or data.get("Creator") or "")

        # Variablen-Array (unterstützt "Variables", "variables", "cheats", "items")
        variables = (data.get("Variables") or data.get("variables") or
                     data.get("cheats") or data.get("Cheats") or
                     data.get("items") or [])
        if not isinstance(variables, list):
            variables = []

        if self._is_native(variables):                  # Reaper-Originalformat (XSource/XReturn + Signatur)
            self._parse_native(variables)
            return

        for v in variables:
            if not isinstance(v, dict):
                continue
            self._parse_variable(v)

        # Falls OriginSource direkt im Root liegt (manche Formate)
        if self.origin_source is None:
            self._parse_root_source(data)

    # ------------------------------------------------------------------
    # Reaper-Originalformat
    # ------------------------------------------------------------------
    @staticmethod
    def _finder_aob(of):
        """offsetFinder {'UniqueAOB': base64, 'Mask': base64} -> '55 48 89 ?? ...' oder ''."""
        import base64
        if not isinstance(of, dict) or not of.get("UniqueAOB"):
            return ""
        try:
            pat = base64.b64decode(of["UniqueAOB"])
            m = of.get("Mask")
            mask = base64.b64decode(m) if m else b"\x01" * len(pat)
        except Exception:
            return ""
        if not pat:
            return ""
        if len(mask) != len(pat):
            mask = (mask + b"\x01" * len(pat))[:len(pat)]
        return " ".join("%02X" % b if k else "??" for b, k in zip(pat, mask))

    @classmethod
    def _is_native(cls, variables):
        return any(isinstance(v, dict) and cls._finder_aob(v.get("offsetFinder")) for v in variables)

    def _parse_native(self, variables):
        """Eintraege: type 11 + offsetFinder = Patch-Stelle ('XSource'), type 11 ohne Signatur = Cave-Label,
        type 6 = Rueckkehr ('XReturn', baseId = Quelle), sonst (2, 7, ...) = Variable in der Cave."""
        sources, labels, returns = [], [], {}
        for v in variables:
            if not isinstance(v, dict):
                continue
            label = str(v.get("label") or "")
            typ = _to_int(v.get("type"), -1)
            dv, nv = v.get("defaultValue"), v.get("newValue")
            aob = self._finder_aob(v.get("offsetFinder"))
            if typ == 6:
                returns[str(v.get("baseId") or "")] = (label, _to_int(v.get("offset"), 0))
            elif typ == 11 and aob:
                sources.append({"label": label, "aob": aob, "off": 0,
                                "dv": dv if isinstance(dv, str) else "", "nv": nv if isinstance(nv, str) else ""})
            elif typ == 11 and isinstance(nv, str) and nv.strip() and _to_int(v.get("offset")):
                sources.append({"label": label, "aob": "", "off": _to_int(v.get("offset")),
                                "dv": dv if isinstance(dv, str) else "", "nv": nv})
            elif typ == 11:
                labels.append((label, dv if isinstance(dv, str) else ""))
            elif label:
                self.variables.append((label, typ, dv, nv))
                self.var_meta[label] = {"display": str(v.get("DisplayName") or label),
                                        "comment": str(v.get("comment") or "")}
        if not sources:
            return
        names = {n for n, _ in labels}

        def is_cave(src):
            return any(m in names for m in re.findall(r"\b(?:jmp|call)\s+([A-Za-z_]\w*)", src["nv"]))
        main = next((x for x in sources if is_cave(x)), sources[0])
        order = [main] + [x for x in sources if x is not main]
        self.native = True
        self.labels = labels
        self.origin_source = (main["off"], main["dv"], main["nv"])
        self.extra_sources = [(x["off"], x["dv"], x["nv"]) for x in order[1:]]
        self.origin_aob, self.origin_aob_offset = main["aob"], 0
        self.src_info = [{"label": x["label"], "aob": x["aob"], "aob_offset": 0} for x in order]
        self.native_returns = {r[0]: (src, r[1]) for src, r in returns.items()}
        ret = returns.get(main["label"])
        self.origin_return_offset = (ret[1] if ret else 0) or 8

    def _parse_variable(self, v: dict):
        label = (v.get("label") or v.get("Label") or
                 v.get("name") or v.get("Name") or
                 v.get("id") or v.get("Id") or "")

        dv = (v.get("defaultValue") or v.get("DefaultValue") or
              v.get("default") or v.get("Default") or
              v.get("original") or v.get("Original") or "")
        nv = (v.get("newValue") or v.get("NewValue") or
              v.get("new") or v.get("New") or
              v.get("patched") or v.get("Patched") or
              v.get("value") or v.get("Value") or "")

        off = _to_int(v.get("offset", v.get("Offset", 0)))

        low = re.sub(r"[\s_\-.]+", "", str(label).lower())       # "Origin Source", "origin-source" ...
        is_static = v.get("isStatic", v.get("IsStatic")) is True
        typ = _to_int(v.get("type", v.get("Type")), -1)
        has_text = isinstance(nv, str) and nv.strip() != ""
        if (low.startswith(("originsource", "hookaddress", "hooksource", "patchaddress", "hook"))
                or (is_static and typ == 11 and off and has_text)):
            entry = (off, dv or "", nv or "")
            if self.origin_source is None:
                self.origin_source = entry
                aob = (v.get("aob") or v.get("AOB") or v.get("signature") or
                       v.get("Signature") or "")
                if isinstance(aob, str):
                    self.origin_aob = aob.strip()
                ao = v.get("aobOffset", v.get("AobOffset", 0))
                try:
                    self.origin_aob_offset = int(ao, 0) if isinstance(ao, str) else int(ao or 0)
                except Exception:
                    self.origin_aob_offset = 0
            else:
                # Zweite/dritte OriginSource = zusätzliche Patch-Stelle ("fusionierter" Patch)
                self.extra_sources.append(entry)
        elif low in ("originreturn", "hookreturn", "returnoffset"):
            self.origin_return_offset = off or 8
        else:
            if isinstance(dv, str) and dv.strip():
                self.labels.append((str(label), dv))
            # Variable mit eigener Adresse + newValue = weitere Patch-Stelle
            if off and isinstance(nv, str) and nv.strip():
                self.extra_sources.append((off, dv if isinstance(dv, str) else "", nv))

    def _parse_root_source(self, data: dict):
        """Fallback: OriginSource direkt im Root."""
        src = data.get("OriginSource") or data.get("originSource")
        if isinstance(src, dict):
            self.origin_source = (
                src.get("offset", 0),
                src.get("defaultValue", ""),
                src.get("newValue", ""),
            )
        elif isinstance(src, list) and len(src) >= 3:
            self.origin_source = (src[0], src[1] or "", src[2] or "")

    # ------------------------------------------------------------------
    # Shnext / SHN (XML-Text oder JSON-Struktur)
    # ------------------------------------------------------------------
    def _load_shnext(self, path: str):
        raw = _read_text(path).strip()

        # Erst als JSON versuchen
        if raw.startswith("{") or raw.startswith("["):
            data = json.loads(raw)
            self.raw = data
            self._parse_shnext_json(data)
            return

        # Sonst: XML-artiger Text – nach Blöcken parsen
        self.raw = {"_raw": raw}
        self._parse_shnext_text(raw)

    def _parse_shnext_json(self, data):
        """Shnext als JSON – typische Felder: name, author, codes/cheats."""
        self.name = data.get("name") or data.get("Name") or self.name
        self.author = data.get("author") or data.get("Author") or self.author

        codes = data.get("codes") or data.get("Codes") or data.get("cheats") or []
        for c in codes:
            if not isinstance(c, dict):
                continue
            self._parse_variable(c)

        # Fallback: gleiche Struktur wie ReapProj
        if not self.labels and not self.origin_source:
            variables = data.get("Variables") or data.get("variables") or []
            for v in variables:
                if isinstance(v, dict):
                    self._parse_variable(v)

    def _parse_shnext_text(self, text: str):
        """Parst XML-artige Shnext-Dateien (vereinfacht)."""
        # Name / Author aus Tags
        m = re.search(r"<name[^>]*>([^<]*)</name>", text, re.I)
        if m:
            self.name = m.group(1).strip()
        m = re.search(r"<author[^>]*>([^<]*)</author>", text, re.I)
        if m:
            self.author = m.group(1).strip()

        # OriginSource-Block
        m = re.search(
            r"<OriginSource[^>]*offset=[\"']?([^\"'\s>]+)[\"']?[^>]*>"
            r"(.*?)</OriginSource>",
            text, re.I | re.S,
        )
        if m:
            try:
                off = int(m.group(1), 0)
            except Exception:
                off = 0
            inner = m.group(2)
            dv = re.search(r"<default(?:Value)?[^>]*>(.*?)</default(?:Value)?>",
                           inner, re.I | re.S)
            nv = re.search(r"<new(?:Value)?[^>]*>(.*?)</new(?:Value)?>",
                           inner, re.I | re.S)
            self.origin_source = (
                off,
                dv.group(1).strip() if dv else "",
                nv.group(1).strip() if nv else "",
            )

        # Weitere Labels als Blöcke
        for m in re.finditer(
            r"<(\w+)[^>]*>(.*?)</\1>", text, re.I | re.S
        ):
            tag, content = m.group(1), m.group(2).strip()
            if tag.lower() in ("originsource", "originreturn", "name", "author"):
                continue
            if content and not content.startswith("<"):
                self.labels.append((tag, content))

    def __repr__(self):
        return (f"<ReapPatch {self.name}: {len(self.labels)} Labels, "
                f"type={self.file_type}>")
