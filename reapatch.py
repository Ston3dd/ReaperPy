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
        """Wenn nur Zusatz-Stellen existieren, die erste zur Haupt-Stelle machen."""
        if self.origin_source is None and self.extra_sources:
            self.origin_source = self.extra_sources.pop(0)

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
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
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

        for v in variables:
            if not isinstance(v, dict):
                continue
            self._parse_variable(v)

        # Falls OriginSource direkt im Root liegt (manche Formate)
        if self.origin_source is None:
            self._parse_root_source(data)

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

        off = v.get("offset", v.get("Offset", 0))
        if isinstance(off, str):
            try:
                off = int(off, 0)
            except Exception:
                off = 0

        low = str(label).lower().replace("_", "")
        if low.startswith("originsource"):
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
        elif low == "originreturn":
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
        with open(path, encoding="utf-8", errors="replace") as f:
            raw = f.read().strip()

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
