"""il2cpp_dump.py - Unity-(IL2CPP)-Spiele: Ausgabe von Il2CppDumper lesen und im laufenden Spiel benutzen.

Das ist das Gegenstueck zu uesdk.py/ue_live.py für Unreal.  Keine Oberflaeche, kein Netzwerk-Code: alles
bekommt read/write-Funktionen übergeben und ist deshalb ohne Konsole testbar.

Eingabe ist ein Spiel-Ordner mit der Ausgabe von Il2CppDumper (Fork TetzkatLipHoka):
    dump.cs          Klassen, Felder (mit Offsets), Methoden (mit RVA), Enums           <- wichtig
    script.json      Methodennamen mit Adresse + TypeInfo-Zeiger der Klassen             <- für Live-Zugriff
    DummyDll/        (optional) dieselben Daten als .NET-DLLs für dnSpy/ILSpy - wird hier nicht gebraucht
Die Ordner duerfen verschachtelt liegen (z. B. entpackte ZIPs): find_game_files() sucht darin.

  GameDump         geladen: .classes, .methods, .typeinfo_rva; Suche, Zahlen-Felder, Enum-Namen
  find_module_base Basisadresse des IL2CPP-Moduls im laufenden Spiel (per Klassennamen-Pruefung, nicht raten)
  Il2CppLive       Instanzen einer Klasse im Heap finden, statische Felder lesen
  patch_*          Bytes für einfache Methoden-Patches (Rückgabewert festlegen / Methode leer machen)
"""

import json
import os
import re
import struct
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Typen: IL2CPP/C#-Typname -> Name, den ue_quick.Target kennt
# ---------------------------------------------------------------------------
PRIMS = {
    "bool": "bool", "byte": "uint8", "sbyte": "int8", "char": "uint16",
    "short": "int16", "ushort": "uint16", "int": "int32", "uint": "uint32",
    "long": "int64", "ulong": "uint64", "float": "float", "double": "double",
    "int8": "int8", "uint8": "uint8", "int16": "int16", "uint16": "uint16",
    "int32": "int32", "uint32": "uint32", "int64": "int64", "uint64": "uint64",
    "intptr": "uint64", "uintptr": "uint64",
}
# Wert-Groesse in Bytes (für Enum-Felder: Standard int32)
SIZES = {"bool": 1, "uint8": 1, "int8": 1, "int16": 2, "uint16": 2, "int32": 4, "uint32": 4,
         "int64": 8, "uint64": 8, "float": 4, "double": 8}


def _split_name(full):
    """'Namespace.Outer.Inner' laesst sich nicht sicher trennen - dump.cs liefert Namespace getrennt."""
    return full


@dataclass
class Field:
    name: str
    type: str
    offset: int          # -1: statisch/Konstante ohne Instanz-Offset
    static: bool = False
    const_value: str = None

    @property
    def prim(self):
        return PRIMS.get(self.type)


@dataclass
class Method:
    name: str
    ret: str
    params: str
    rva: int
    static: bool
    cls: "Class" = None

    @property
    def sig(self):
        return f"{self.ret} {self.name}({self.params})"

    @property
    def key(self):
        return f"{self.cls.full if self.cls else '?'}.{self.name}"

    @property
    def n_params(self):
        p = self.params.strip()
        if not p:
            return 0
        depth, n = 0, 1
        for ch in p:
            if ch in "<[(":
                depth += 1
            elif ch in ">])":
                depth -= 1
            elif ch == "," and depth == 0:
                n += 1
        return n


@dataclass
class Class:
    namespace: str
    name: str            # inkl. Aussen-Klassen: 'UIMoneyHeld.CounterAnimInfo'
    kind: str            # class | struct | enum | interface
    base: str = ""
    typedef: int = -1
    fields: list = field(default_factory=list)
    methods: list = field(default_factory=list)
    image: str = ""
    enum_values: list = field(default_factory=list)   # [(Name, Wert)]
    enum_underlying: str = "int32"

    @property
    def full(self):
        return f"{self.namespace}.{self.name}" if self.namespace else self.name

    def find_field(self, name):
        for f in self.fields:
            if f.name == name:
                return f
        return None


class DumpError(Exception):
    pass


# ---------------------------------------------------------------------------
# Spiel-Ordner finden
# ---------------------------------------------------------------------------
def find_game_files(folder, max_depth=4):
    """Sucht dump.cs, script.json, stringliteral.json, DummyDll und Il2CppDumper.exe in einem (verschachtelten) Ordner.
    -> dict mit Pfaden oder None.  Nimmt den ersten (flachsten) Treffer."""
    want = {"dump_cs": "dump.cs", "script": "script.json", "strings": "stringliteral.json"}
    found = {k: None for k in list(want) + ["dummydll", "dumper"]}
    base_depth = os.path.normpath(folder).count(os.sep)
    for root, dirs, files in os.walk(folder):
        if root.count(os.sep) - base_depth >= max_depth:
            dirs[:] = []
        low = {f.lower(): f for f in files}
        for key, fn in want.items():
            if found[key] is None and fn in low:
                found[key] = os.path.join(root, low[fn])
        if found["dumper"] is None and "il2cppdumper.exe" in low:
            found["dumper"] = os.path.join(root, low["il2cppdumper.exe"])
        for d in list(dirs):
            if d.lower() == "dummydll" and found["dummydll"] is None:
                found["dummydll"] = os.path.join(root, d)
        # DummyDll ohne eigenen Unterordner: viele .dll mit Assembly-CSharp.dll
        if found["dummydll"] is None and "assembly-csharp.dll" in low:
            found["dummydll"] = root
    return found


# ---------------------------------------------------------------------------
# dump.cs lesen
# ---------------------------------------------------------------------------
_RE_NS = re.compile(r"^// Namespace: (.*)$")
_RE_IMG_FULL = re.compile(r"^// Image \d+: (.+?) - (\d+)$")
_RE_TYPE = re.compile(
    r"^(?:\[[^\]]*\]\s*)*(?:(?:public|private|protected|internal|sealed|abstract|static|unsafe|partial|readonly|new)\s+)*"
    r"(class|struct|enum|interface)\s+(\S+?)(?:\s*:\s*(.+?))?\s*(?://\s*TypeDefIndex:\s*(\d+))?\s*$"
)
_RE_RVA = re.compile(r"^\s*// RVA: 0x([0-9A-Fa-f]+) Offset: 0x[0-9A-Fa-f]+ VA: 0x[0-9A-Fa-f]+")
_RE_FIELD = re.compile(r"^\t(?:(?:public|private|protected|internal|static|readonly|const|volatile|new)\s+)+(.+?)\s+(\S+?)(?:\s*=\s*(.+?))?;(?:\s*//\s*(0x[0-9A-Fa-f]+))?\s*$")
_RE_METHOD = re.compile(r"^\t((?:(?:public|private|protected|internal|static|virtual|override|abstract|sealed|extern|new|unsafe)\s+)*)(.+?)\s+([^\s(]+)\((.*)\)\s*\{")


def _norm_type(t):
    t = t.strip()
    if t.startswith("ref "):
        t = t[4:]
    return t


def parse_dump_cs(path, log=None):
    """dump.cs -> [Class].  Zeilenweise (die Datei ist leicht 50+ MB gross)."""
    classes = []
    images = []
    ns = ""
    cur = None
    pending_rva = None
    in_enum = False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            c0 = line[0]
            if c0 == "/":                                  # Kommentarzeilen auf oberster Ebene
                m = _RE_IMG_FULL.match(line)
                if m:
                    images.append((int(m.group(2)), m.group(1)))
                    continue
                m = _RE_NS.match(line)
                if m:
                    ns = m.group(1).strip()
                continue
            if c0 not in "\t{} ":
                if line.startswith("["):                   # Attribut vor einem Typ
                    continue
                m = _RE_TYPE.match(line)
                if m:
                    kind, name, base, td = m.groups()
                    cur = Class(ns, name, kind, (base or "").strip(), int(td) if td else -1)
                    classes.append(cur)
                    in_enum = kind == "enum"
                    pending_rva = None
                continue
            if cur is None or c0 != "\t":
                continue
            if line.startswith("\t//"):
                m = _RE_RVA.match(line)
                if m:
                    pending_rva = int(m.group(1), 16)
                continue
            if line.startswith("\t["):
                continue
            if "(" in line and line.rstrip().endswith("}") and pending_rva is not None:
                m = _RE_METHOD.match(line)
                if m:
                    mods, ret, name, params = m.groups()
                    cur.methods.append(Method(name, _norm_type(ret), params.strip(), pending_rva, "static" in mods.split(), cur))
                pending_rva = None
                continue
            m = _RE_FIELD.match(line)
            if m:
                ftype, fname, const, off = m.groups()
                is_static = bool(re.match(r"^\t(?:\w+\s+)*static\s", line))
                is_const = bool(re.match(r"^\t(?:\w+\s+)*const\s", line))
                if in_enum and fname != "value__":
                    try:
                        cur.enum_values.append((fname, int(const, 0) if const else 0))
                    except ValueError:
                        pass
                    continue
                if fname == "value__":
                    cur.enum_underlying = PRIMS.get(ftype.strip(), "int32")
                    continue
                cur.fields.append(Field(fname, _norm_type(ftype), int(off, 16) if off and not is_const else -1,
                                        is_static or is_const, const if is_const else None))
    images.sort()
    starts = [a for a, _n in images]
    import bisect
    for c in classes:
        if c.typedef >= 0 and images:
            c.image = images[max(0, bisect.bisect_right(starts, c.typedef) - 1)][1]
    if log:
        log(f"dump.cs gelesen: {len(classes)} Klassen")
    return classes


# ---------------------------------------------------------------------------
# script.json: TypeInfo-Zeiger (RVA des Zeigers auf Il2CppClass)
# ---------------------------------------------------------------------------
_RE_TI = re.compile(r'"Address":\s*(\d+),\s*"Name":\s*"((?:[^"\\]|\\.)*?)_TypeInfo",\s*"Signature":\s*"Il2CppClass\*|'
                    r'"Address":\s*(\d+),\s*"Name":\s*"((?:[^"\\]|\\.)*?)_TypeInfo",\s*"Signature":\s*"[A-Za-z0-9_]+_c\*"')


def _unescape(s):
    s = s.replace("\\\\u003C", "<").replace("\\\\u003E", ">").replace("\\u003C", "<").replace("\\u003E", ">")
    return s.replace("\\\\", "\\")


def parse_typeinfo(script_path):
    """script.json -> {Klassenname (mit Namespace): RVA des TypeInfo-Zeigers}.  Per Regex über den Text:
    die Datei ist >100 MB, json.load wuerde mehr als 1 GB RAM brauchen."""
    out = {}
    with open(script_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    for m in _RE_TI.finditer(text):
        addr = m.group(1) or m.group(3)
        name = m.group(2) if m.group(1) else m.group(4)
        out.setdefault(_unescape(name), int(addr))
    return out


# ---------------------------------------------------------------------------
# Anzeige: Compiler-Kram ausblenden, Backing-Fields lesbar machen
# ---------------------------------------------------------------------------
_RE_BACKING = re.compile(r"^<(.+)>k__BackingField$")


def clean_field_name(name):
    """'<Reputation>k__BackingField' -> 'Reputation' (Property); sonst unveraendert."""
    m = _RE_BACKING.match(name)
    return m.group(1) if m else name


def is_generated(cls, fld=None):
    """Vom Compiler erzeugt (Lambda-/Closure-Klassen, Iterator-Zustandsautomaten, Hilfsfelder) - für Cheats uninteressant."""
    last = cls.name.rsplit(".", 1)[-1]
    if last.startswith("<") or "__DisplayClass" in last:
        return True
    return fld is not None and fld.name.startswith("<") and not _RE_BACKING.match(fld.name)


# ---------------------------------------------------------------------------
# Das geladene Spiel
# ---------------------------------------------------------------------------
class GameDump:
    def __init__(self, files, log=print):
        self.files = files
        self.log = log
        self.classes = []
        self.by_full = {}
        self.typeinfo_rva = {}
        self.title = ""
        self.stats = {}
        self._methods = None

    def load(self):
        if not self.files.get("dump_cs"):
            hint = ""
            if self.files.get("dummydll"):
                hint = (" Es gibt zwar einen DummyDll-Ordner, aber die Felder-Offsets und Methoden-Adressen stehen in "
                        "dump.cs - Il2CppDumper schreibt beide zusammen; bitte dump.cs mit in den Ordner legen.")
            raise DumpError("dump.cs nicht gefunden." + hint)
        self.classes = parse_dump_cs(self.files["dump_cs"], self.log)
        self.by_full = {}
        for c in self.classes:
            self.by_full.setdefault(c.full, c)
        if self.files.get("script"):
            try:
                self.typeinfo_rva = parse_typeinfo(self.files["script"])
                self.log(f"script.json gelesen: {len(self.typeinfo_rva)} Klassen-Zeiger (darüber werden die Klassen im Spiel gefunden)")
            except Exception as e:  # noqa: BLE001
                self.log(f"script.json nicht lesbar: {e}")
        else:
            self.log("script.json fehlt: Methoden-Patches gehen, aber keine Live-Instanzen (TypeInfo-Zeiger fehlen)")
        asm = [c for c in self.classes if c.image.startswith("Assembly-CSharp")]
        self.title = os.path.basename(os.path.dirname(self.files["dump_cs"])) or "Unity-Spiel"
        self.stats = {
            "classes": len(self.classes), "game": len(asm), "lib": len(self.classes) - len(asm),
            "methods": len(self.all_methods()), "enums": sum(1 for c in self.classes if c.kind == "enum"),
            "pointers": len(self.typeinfo_rva),
        }
        st = self.stats
        self.log(f"Insgesamt {st['classes']} Klassen: {st['game']} Spiel-Code (Assembly-CSharp), "
                 f"{st['lib']} Unity-/System-Bibliotheken; {st['methods']} Methoden, {st['enums']} Enums")
        return self

    # --- Suche -------------------------------------------------------------
    def find_class(self, name):
        if name in self.by_full:
            return self.by_full[name]
        low = name.lower()
        for c in self.classes:
            if c.name.lower() == low or c.full.lower() == low:
                return c
        return None

    def typeinfo_for(self, cls):
        return self.typeinfo_rva.get(cls.full)

    def _build_tree(self):
        by_name = {}
        for c in self.classes:
            by_name.setdefault(c.name, c)
        self._parent, self._children = {}, {}
        for c in self.classes:
            b = (c.base or "").split(",")[0].strip()
            if not b or c.kind != "class":
                continue
            b = b.split("<")[0].strip()
            par = self.by_full.get(b) or self.by_full.get(f"{c.namespace}.{b}" if c.namespace else b) or by_name.get(b)
            if par is not None and par is not c:
                self._parent[c.full] = par
                self._children.setdefault(par.full, []).append(c)

    def parent_of(self, cls):
        if not hasattr(self, "_parent"):
            self._build_tree()
        return self._parent.get(cls.full)

    def family(self, cls, cap=64):
        """Klasse + alle Unterklassen (breit zuerst, max. cap).  Geerbte Felder liegen im Dump nur bei der Basisklasse,
        die Objekte im Speicher tragen aber den Zeiger der Unterklasse."""
        if not hasattr(self, "_parent"):
            self._build_tree()
        out, queue = [cls], [cls]
        while queue and len(out) < cap:
            for ch in self._children.get(queue.pop(0).full, []):
                if ch not in out:
                    out.append(ch)
                    queue.append(ch)
        return out[:cap]

    def value_targets(self, only_game_code=False):
        """Alle Zahlen-/Bool-/Enum-Felder mit Instanz-Offset -> [(Class, Field, prim, size)].
        Enum-Felder gelten als Ganzzahl.  Statische Felder stehen in static_targets()."""
        out = []
        enums = {c.full: c for c in self.classes if c.kind == "enum"}
        enum_short = {c.name: c for c in self.classes if c.kind == "enum"}
        for c in self.classes:
            if c.kind == "enum" or c.kind == "interface":
                continue
            if only_game_code and not c.image.startswith("Assembly-CSharp"):
                continue
            for f in c.fields:
                if f.static or f.offset < 0:
                    continue
                prim = f.prim
                if prim is None:
                    e = enums.get(f.type) or enum_short.get(f.type)
                    if e is None:
                        continue
                    prim = e.enum_underlying
                out.append((c, f, prim, SIZES.get(prim, 4)))
        return out

    def static_targets(self):
        out = []
        for c in self.classes:
            if c.kind in ("enum", "interface"):
                continue
            for f in c.fields:
                if f.static and f.const_value is None and f.prim:
                    out.append((c, f))
        return out

    def all_methods(self):
        if self._methods is None:
            self._methods = [m for c in self.classes for m in c.methods]
        return self._methods

    def search_methods(self, text, limit=3000):
        q = text.lower().strip()
        if not q:
            return []
        parts = q.split()
        out = []
        for m in self.all_methods():
            hay = f"{m.key} {m.params}".lower()
            if all(p in hay for p in parts):
                out.append(m)
                if len(out) >= limit:
                    break
        return out

    def enum_search(self, text, limit=3000):
        """Enum-Eintraege nach Namen suchen: 'Item Apple' -> [(Enum, Name, Wert)]."""
        parts = text.lower().split()
        out = []
        for c in self.classes:
            if c.kind != "enum":
                continue
            for n, v in c.enum_values:
                hay = f"{c.name} {n}".lower()
                if all(p in hay for p in parts):
                    out.append((c, n, v))
                    if len(out) >= limit:
                        return out
        return out


# ---------------------------------------------------------------------------
# Live: Modul-Basis und Instanzen
# ---------------------------------------------------------------------------
# Il2CppClass (64 Bit): image @0x0, gc_desc @0x8, name @0x10, namespace @0x18 - seit Unity 5 unveraendert.
K_NAME, K_NAMESPACE = 0x10, 0x18
K_STATIC_FIELDS = 0xB8        # Unity 2018.3 ... 6; per Ui-Feld aenderbar


def _cstr(read, addr, n=96):
    try:
        raw = read(addr, n)
    except Exception:  # noqa: BLE001
        return None
    z = raw.find(b"\0")
    return raw[: z if z >= 0 else n].decode("utf-8", "replace")


class ChunkStream:
    """Liest viele Bloecke nacheinander, mehrere gleichzeitig ueber getrennte Verbindungen (`readers` = Liste von
    read(addr, n)-Funktionen).  Liefert (pos, n, buf) in der urspruenglichen Reihenfolge; buf ist None, wenn der
    Read fehlschlug.  Mit nur einem Reader laeuft das Lesen trotzdem in einem Hilfsthread weiter, waehrend der
    Aufrufer den vorigen Block auswertet (Netz und CPU ueberlappen)."""

    def __init__(self, readers, jobs, cancel=None):
        self.readers = list(readers)
        self.jobs = list(jobs)                         # [(pos, n, readlen)]
        self.cancel = cancel

    def __iter__(self):
        import queue
        from concurrent.futures import ThreadPoolExecutor
        workers = max(1, len(self.readers))
        free = queue.Queue()
        for r in self.readers:
            free.put(r)

        def work(job):
            pos, _n, rl = job
            r = free.get()
            try:
                return bytes(r(pos, rl))
            except Exception:  # noqa: BLE001 - wie bisher: Block auslassen
                return None
            finally:
                free.put(r)

        window = workers + 1
        pending = []
        it = iter(self.jobs)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            try:
                while True:
                    while len(pending) < window:
                        job = next(it, None)
                        if job is None:
                            break
                        pending.append((job, ex.submit(work, job)))
                    if not pending:
                        return
                    if self.cancel and self.cancel():
                        return
                    job, fut = pending.pop(0)
                    yield job[0], job[1], fut.result()
            finally:
                for _j, f in pending:
                    f.cancel()


def _plan_jobs(regions, chunk, extra=16, align=1):
    """[(start, end)] -> [(pos, n, readlen)]: Bloecke zu `chunk` Byte, jeweils `extra` Byte ueberlappend lesbar."""
    out = []
    for s, e in regions:
        pos = s
        while pos < e:
            n = min(chunk, e - pos)
            if align > 1:
                n = n // align * align
                if n <= 0:
                    break
            out.append((pos, n, min(n + extra, e - pos)))
            pos += n
    return out


def _qword_matcher(kset):
    """-> f(buf, n) = Indizes (in Qwords) der ersten n//8 Qwords von buf, die in kset liegen.
    Mit numpy (falls installiert) ~20x schneller als die reine Python-Schleife: erst grober Bereichsfilter, dann genau."""
    vals = sorted(kset)
    try:
        import numpy as np
    except Exception:  # noqa: BLE001
        np = None
    if np is not None and vals:
        karr = np.array(vals, dtype=np.uint64)
        lo, hi, top = karr[0], karr[-1], len(karr) - 1

        def fast(buf, n):
            arr = np.frombuffer(buf, dtype=np.uint64, count=n // 8)
            cand = np.flatnonzero((arr >= lo) & (arr <= hi))
            if not len(cand):
                return []
            sub = arr[cand]
            pos = np.minimum(np.searchsorted(karr, sub), top)
            return cand[karr[pos] == sub].tolist()
        return fast

    def slow(buf, n):
        mv = memoryview(buf)[: n // 8 * 8].cast("Q")
        present = kset.intersection(mv)                     # in C: viel schneller als jedes Qword einzeln in Python
        if not present:
            return []
        out = []
        for v in present:
            needle = struct.pack("<Q", v)
            i = buf.find(needle, 0, n)
            while i >= 0:
                if i % 8 == 0:
                    out.append(i // 8)
                i = buf.find(needle, i + 1, n)
        return sorted(out)
    return slow


class SafeReader:
    """read() mit lokaler Pruefung gegen die Speicherkarte (jede gemappte Region zaehlt, auch ohne Lese-Bit): Adressen ausserhalb lesbarer Regionen werden gar nicht erst an
    die Konsole geschickt.  Ein fehlgeschlagener Read kostet dort Sekunden (Wiederholung + Warten) - bei hunderten
    Kandidaten-Adressen wuerde die Modulsuche sonst minutenlang haengen."""

    def __init__(self, read, maps):
        self._read = read
        regs = sorted((m[0], m[1]) for m in maps)          # jede gemappte Region: Code ist auf der PS5 oft nur ausfuehrbar
        merged = []
        for s, e in regs:
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        self.regions = merged
        self._starts = [r[0] for r in merged]

    def readable(self, addr, n=1):
        import bisect
        i = bisect.bisect_right(self._starts, addr) - 1
        return i >= 0 and addr + n <= self.regions[i][1]

    def __call__(self, addr, n):
        if addr < 0 or not self.readable(addr, n):
            raise OSError(f"{addr:#x} nicht lesbar (nicht in der Speicherkarte)")
        return self._read(addr, n)


def _safe(read, maps):
    return read if isinstance(read, SafeReader) else SafeReader(read, maps)


def _slots(game):
    """[(rva, Klassenname)] für normale Klassen (keine Generics/Verschachtelten), nach RVA sortiert."""
    out = []
    for c in game.classes:
        rva = game.typeinfo_for(c)
        if rva and c.kind != "interface" and "<" not in c.name and "`" not in c.name and "." not in c.name:
            out.append((rva, c.name, c.namespace))
    out.sort()
    return out


def check_base(read, base, game, samples=12, maps=None):
    """Stimmt base als Modul-Basis?  Die ganze TypeInfo-Tabelle auf einmal lesen, die befüllten Eintraege (IL2CPP
    fuellt sie erst beim ersten Benutzen einer Klasse) gegen Klassennamen im Speicher pruefen.
    -> (Treffer, geprüft).  Mit maps: Adressen ausserhalb der Speicherkarte kosten nichts."""
    if maps is not None:
        read = _safe(read, maps)
    slots = getattr(game, "_slot_cache", None)
    if slots is None:
        slots = game._slot_cache = _slots(game)
    if not slots:
        return 0, 0
    lo, hi = slots[0][0], slots[-1][0] + 8
    try:
        if hi - lo > 0x2000000:                      # unplausibel gross -> nur Stichproben
            raise ValueError
        blob = bytearray()
        pos = base + lo
        while pos < base + hi:
            n = min(0x40000, base + hi - pos)
            blob += read(pos, n)
            pos += n
    except Exception:  # noqa: BLE001
        return 0, 0
    ok = tried = 0
    for rva, name, ns in slots:
        off = rva - lo
        ptr = struct.unpack_from("<Q", blob, off)[0]
        if ptr < 0x10000:
            continue                                  # noch nicht initialisiert
        tried += 1
        try:
            nptr = struct.unpack("<Q", read(ptr + K_NAME, 8))[0]
            got = _cstr(read, nptr)
        except Exception:  # noqa: BLE001
            got = None
        if got == name:
            ok += 1
            if ok >= samples:
                break
        elif tried >= samples * 4 and ok == 0:
            break
    return ok, tried


def _good(ok, tried):
    """Genug Namenstreffer?  Mind. 4, oder (kleine Spiele/frueher Start) mindestens einer und die Haelfte der befüllten Slots."""
    return ok >= 4 or (ok >= 1 and ok * 2 >= tried)


def candidate_bases(maps):
    """Moegliche Modul-Anfaenge: Beginn jeder lesbaren Region (Module liegen oft ohne Luecke hintereinander, deshalb
    reichen Gruppen-Anfaenge nicht).  Ausfuehrbare Regionen zuerst - dort beginnt ein Modul mit seinem Code."""
    regs = sorted({(m[0], m[2]) for m in maps})
    return [s for s, p in regs if p & 4] + [s for s, p in regs if not p & 4]


def named_modules(maps):
    """maps mit Modulnamen (4. Eintrag) -> [(Name, Basis, Ende)], Basis = niedrigste Region des Moduls (so wie il2mem.py).
    IL2CPP-Module zuerst, dann eboot, dann der Rest."""
    mods = {}
    for m in maps:
        if len(m) > 3 and m[3]:
            b, e = mods.get(m[3], (m[0], m[1]))
            mods[m[3]] = (min(b, m[0]), max(e, m[1]))
    def rank(n):
        low = n.lower()
        return (0 if "il2cpp" in low else 1 if low.startswith("eboot") else 2, n)
    return [(n, mods[n][0], mods[n][1]) for n in sorted(mods, key=rank)]


def diagnose(read, base, game, maps, name=""):
    """Textbericht für die Fehlersuche: Ist die TypeInfo-Tabelle lesbar, wie viele Slots sind befüllt, was steht drin?"""
    sread = _safe(read, maps)
    slots = getattr(game, "_slot_cache", None) or _slots(game)
    out = [f"Diagnose {name or '?'} @ {base:#x}: {len(slots)} Klassen-Slots erwartet ab RVA {slots[0][0]:#x}"]
    try:
        blob = sread(base + slots[0][0], slots[-1][0] + 8 - slots[0][0])
    except Exception as e:  # noqa: BLE001
        return out + [f"  Tabelle nicht lesbar: {e}"]
    filled = [(r, n, struct.unpack_from("<Q", blob, r - slots[0][0])[0]) for r, n, _ns in slots]
    filled = [x for x in filled if x[2]]
    out.append(f"  davon befüllt: {len(filled)} (der Rest wird von IL2CPP erst beim ersten Benutzen gesetzt)")
    for r, n, ptr in filled[:3]:
        try:
            got = _cstr(sread, struct.unpack("<Q", sread(ptr + K_NAME, 8))[0])
        except Exception as e:  # noqa: BLE001
            got = f"<{e}>"
        out.append(f"  RVA {r:#x}: erwartet {n!r}, Zeiger {ptr:#x}, im Speicher gelesen {got!r}")
    if not filled:
        out.append("  Alle Slots leer: Spiel noch nicht weit genug gestartet, oder Basis falsch.")
    return out


def find_module_base(read, maps, game, log=print, cancel=None):
    """Basisadresse des IL2CPP-Moduls (PS5: meist Il2CppUserAssemblies.prx, sonst eboot) finden.
    Stufe 1: jede Region als Modul-Anfang pruefen (Klassennamen). Stufe 2: über Klassenzeiger im Speicher rueckwaerts."""
    if not game.typeinfo_rva:
        raise DumpError("script.json fehlt oder enthält keine TypeInfo-Zeiger - Modul-Basis nicht prüfbar")
    sread = _safe(read, maps)
    cands = candidate_bases(maps)
    slots = getattr(game, "_slot_cache", None) or _slots(game)
    game._slot_cache = slots
    lo = slots[0][0] if slots else 0
    best = (0, None)
    named_first = None
    mods = named_modules(maps)
    if mods:
        log("Module im Spiel: " + ", ".join(f"{n} @ {b:#x}" for n, b, _e in mods[:8]) + (" ..." if len(mods) > 8 else ""))
    for n, b, _e in mods:
        if cancel and cancel():
            break
        if not sread.readable(b + lo, 8):
            continue
        ok, t = check_base(sread, b, game, maps=maps)
        if _good(ok, t):
            log(f"IL2CPP-Modul {n} bei {b:#x} ({ok} Klassennamen bestätigt)")
            return b
        if named_first is None and "il2cpp" in n.lower():
            named_first = (n, b)
    log(f"Prüfe {len(cands)} Speicherregionen auf das IL2CPP-Modul ...")
    for i, base in enumerate(cands):
        if cancel and cancel():
            break
        if not sread.readable(base + lo, 8):
            continue
        ok, _t = check_base(sread, base, game, maps=maps)
        if ok > best[0] and _good(ok, _t):
            best = (ok, base)
        if ok >= 4:
            log(f"IL2CPP-Modul bei {base:#x} ({ok} Klassennamen bestätigt)")
            return base
        if i and i % 100 == 0:
            log(f"... {i}/{len(cands)} Regionen geprüft")
    if best[0] >= 1:
        log(f"IL2CPP-Modul bei {best[1]:#x} ({best[0]} Klassennamen bestätigt)")
        return best[1]
    log("Tabelle nicht direkt gefunden - suche über Klassen im Speicher (dauert länger) ...")
    base = _find_base_by_pointer(sread, maps, game, slots, log, cancel)
    if base:
        return base
    if named_first:
        for line in diagnose(read, named_first[1], game, maps, named_first[0]):
            log(line)
    raise DumpError("Kein Modul passt zu den Klassennamen aus dump.cs. Stimmen Spiel-Version und Dump (derselbe Build)? "
                    "Ist das Spiel schon im Menü/Spielstand geladen? Notfalls die Basis von Hand eintragen.")


def _find_base_by_pointer(sread, maps, game, slots, log, cancel):
    """Klasse per Name im Speicher finden -> Zeiger darauf suchen (liegt im TypeInfo-Slot) -> Basis = Fundort - RVA."""
    live = Il2CppLive(sread, game, 0, maps, log=log)
    tried = 0
    rw = live.heap_regions()
    for rva, name, ns in slots[::max(1, len(slots) // 40)]:
        if cancel and cancel():
            return None
        c = game.by_full.get(f"{ns}.{name}" if ns else name)
        if c is None:
            continue
        kp = live.resolve_by_name(c, cancel=cancel)
        if not kp:
            continue
        tried += 1
        for h in live._scan(struct.pack("<Q", kp), rw, limit=16, align=8, cancel=cancel):
            base = h - rva
            ok, _t = check_base(sread, base, game, maps=maps)
            if _good(ok, _t):
                log(f"IL2CPP-Modul bei {base:#x} über {name} gefunden ({ok} Klassennamen bestätigt)")
                return base
        if tried >= 6:
            break
    return None


class Il2CppLive:
    """Zugriff auf das laufende Spiel: Klassenzeiger, Instanzen, statische Felder."""

    def __init__(self, read, game, base, maps, static_off=K_STATIC_FIELDS, log=print, extra_readers=(), closers=()):
        self.read, self.game, self.base, self.maps = _safe(read, maps), game, base, maps
        self.extra_readers = list(extra_readers)       # weitere Verbindungen: lesen grosse Bereiche parallel
        self._closers = list(closers)
        self.static_off = static_off
        self.log = log
        self._klass = {}
        self._kstarts = []
        self.objects = None         # nach census(): {Klasse: [Objekt-Adressen]} - macht instances() sofort
        self.counts = {}            # nach census(): {Klasse: Anzahl}
        self.known = set()          # Klassen, deren Zeiger beim census bekannt waren
        self.last_source = ""
        self._raw = read._read if isinstance(read, SafeReader) else read

    def close_readers(self):
        for c in self._closers:
            try:
                c()
            except Exception:  # noqa: BLE001
                pass
        self._closers, self.extra_readers = [], []

    def _readers(self):
        return [self._raw] + list(self.extra_readers)

    def set_maps(self, maps):
        """Neue Speicherkarte (nach Levelwechsel o. ae.) - Klassenzeiger bleiben gueltig, Heap-Regionen aendern sich."""
        self.maps = maps
        self.read = SafeReader(self._raw, maps)

    def klass_ptr(self, cls, by_name=True, cancel=None):
        """Zeiger auf die Il2CppClass im Spiel.  Erst über den TypeInfo-Zeiger aus script.json; hat die Klasse keinen
        (Il2CppDumper listet nur Klassen, auf die der Code direkt zeigt), dann über ihren Namen im Speicher.
        None = nicht gefunden (Klasse im Spiel noch nie benutzt)."""
        if cls.full in self._klass and (self._klass[cls.full] or not by_name):
            return self._klass[cls.full]
        rva = self.game.typeinfo_for(cls)
        val = None
        if rva:
            try:
                p = struct.unpack("<Q", self.read(self.base + rva, 8))[0]
                if p > 0x10000:
                    val = p
            except Exception:  # noqa: BLE001
                pass
        if val is None and by_name and "." not in cls.name:
            val = self.resolve_by_name(cls, cancel=cancel)
        self._klass[cls.full] = val
        return val

    def _scan(self, needle, regions, limit=16, align=1, chunk=0x400000, cancel=None, stop_after=None):
        hits = []
        for s, e in regions:
            jobs = [(p, n, min(n + len(needle), e - p)) for p, n, _rl in _plan_jobs([(s, e)], chunk, 0)]
            for pos, n, buf in ChunkStream(self._readers(), jobs, cancel):
                if buf is None:
                    continue
                i = buf.find(needle)
                while i >= 0 and len(hits) < limit:
                    if (pos + i) % align == 0 and i < n:       # Treffer im Ueberlapp gehoert zum naechsten Block
                        hits.append(pos + i)
                    i = buf.find(needle, i + 1)
                if len(hits) >= limit:
                    break
            if cancel and cancel():
                return hits
            if len(hits) >= limit or (stop_after and len(hits) >= stop_after):
                break
        return hits

    def resolve_by_name(self, cls, cancel=None):
        """Il2CppClass über Namen finden: Name-String suchen -> Zeiger darauf bei klass+0x10 suchen -> Namespace und
        element_class (zeigt auf sich selbst) pruefen."""
        name = cls.name.encode()
        readable = [(m[0], m[1]) for m in self.maps if (m[2] & 1) and (m[1] - m[0]) >= 0x1000]
        strs = [h + 1 for h in self._scan(b"\0" + name + b"\0", readable, limit=8, cancel=cancel)]
        if not strs:
            return None
        rw = self.heap_regions()
        for sa in strs:
            for h in self._scan(struct.pack("<Q", sa), rw, limit=32, align=8, cancel=cancel):
                k = h - K_NAME
                try:
                    nsp = struct.unpack("<Q", self.read(k + K_NAMESPACE, 8))[0]
                    ns = _cstr(self.read, nsp) if nsp > 0x10000 else ""
                    elem = struct.unpack("<Q", self.read(k + 0x40, 8))[0]
                except Exception:  # noqa: BLE001
                    continue
                if (ns or "") == cls.namespace and elem == k:
                    return k
        return None

    def drop_cache(self):
        self._klass.clear()

    MODULE_SUFFIXES = (".prx", ".sprx", ".bin", ".elf", ".self")

    def heap_regions(self):
        """Lesbar+schreibbar, nicht ausfuehrbar und - wenn die Speicherkarte Namen hat - nicht Teil eines Moduls (.prx,
        eboot.bin: Code/Daten/BSS, dort liegen keine verwalteten Objekte).  Das spart bei der Suche viel Lesezeit."""
        out = []
        for m in self.maps:
            if (m[2] & 3) != 3 or (m[2] & 4) or (m[1] - m[0]) < 0x1000:
                continue
            if len(m) > 3 and m[3] and m[3].lower().endswith(self.MODULE_SUFFIXES):
                continue
            out.append((m[0], m[1]))
        return out

    def _in_class_struct(self, addr, extra=()):
        """Liegt addr in einer bekannten Il2CppClass-Struktur?  (castClass/element_class zeigen dort auf die Klasse selbst
        und waeren sonst Scheinobjekte.)"""
        import bisect
        ks = self._kstarts
        i = bisect.bisect_right(ks, addr) - 1
        if i >= 0 and addr < ks[i] + 0x400:
            return True
        return any(k <= addr < k + 0x400 for k in extra)

    def klass_table(self):
        """{Klassenzeiger: Class} für alle Klassen, deren TypeInfo-Slot schon befüllt ist (ein Block-Read)."""
        slots = getattr(self.game, "_slot_cache", None) or _slots(self.game)
        self.game._slot_cache = slots
        if not slots:
            return {}
        lo, hi = slots[0][0], slots[-1][0] + 8
        blob = bytearray()
        pos = self.base + lo
        while pos < self.base + hi:
            n = min(0x40000, self.base + hi - pos)
            blob += self.read(pos, n)
            pos += n
        out = {}
        for rva, name, ns in slots:
            ptr = struct.unpack_from("<Q", blob, rva - lo)[0]
            c = self.game.by_full.get(f"{ns}.{name}" if ns else name)
            if ptr > 0x10000 and c is not None:
                out[ptr] = c
        self._kstarts = sorted(out)
        return out

    def census(self, progress=None, cancel=None, chunk=0x400000):
        """Ein Durchlauf über den schreibbaren Speicher: wie viele Objekte gibt es von jeder Klasse?
        -> ({Klassenname: Anzahl}, {Klassenname, die schon initialisiert sind}).  Objekt = Klassenzeiger an Offset 0 und
        leeres Monitor-Feld an Offset 8 (schliesst Zeiger in Klassen-Strukturen aus)."""
        from collections import Counter
        table = self.klass_table()
        kset = set(table)
        counts = Counter()
        objs = {}
        keep = 2000                       # pro Klasse max. so viele Adressen merken (Zaehler bleibt exakt)
        regs = self.heap_regions()
        total = sum(e - s for s, e in regs) or 1
        done = 0
        match = _qword_matcher(kset)
        jobs = _plan_jobs(regs, chunk, 8, align=8)
        for pos, n, buf in ChunkStream(self._readers(), jobs, cancel):
            if cancel and cancel():
                return dict(counts), {c.full for c in table.values()}     # abgebrochen: kein Cache
            done += n
            if buf is not None and len(buf) >= n:
                full_len = len(buf) % 8 == 0
                mv = memoryview(buf)[: n].cast("Q")
                nxt = memoryview(buf).cast("Q") if full_len else mv
                for i in match(buf, n):
                    mon = nxt[i + 1] if i + 1 < len(nxt) else 0
                    if mon == 0 and not self._in_class_struct(pos + i * 8):
                        full = table[mv[i]].full
                        counts[full] += 1
                        lst = objs.setdefault(full, [])
                        if len(lst) < keep:
                            lst.append(pos + i * 8)
            if progress:
                progress(done, total)
        self.objects, self.counts = objs, dict(counts)
        self.known = {c.full for c in table.values()}
        return dict(counts), set(self.known)

    def _header_ok(self, addr, kps):
        """Ist an addr noch ein Objekt einer der Klassen (Klassenzeiger + leeres Monitor-Feld)?"""
        try:
            k, mon = struct.unpack("<QQ", self.read(addr, 16))
        except Exception:  # noqa: BLE001
            return False
        return k in kps and mon == 0

    def instances(self, cls, limit=400, chunk=0x800000, progress=None, use_cache=True, cancel=None):
        """Alle Objekte der Klasse (und ihrer Unterklassen): Klassenzeiger an Offset 0, Monitor-Feld an Offset 8 leer.
        Nach census() sofort aus dem Cache (jede Adresse wird kurz geprüft); sonst - oder mit use_cache=False - wird der
        schreibbare Speicher durchsucht und der Cache aktualisiert.  last_source sagt, was passiert ist."""
        if not self._kstarts:
            try:
                self.klass_table()
            except Exception:  # noqa: BLE001
                pass
        fam = self.game.family(cls, cap=24)
        needles = {}                                   # Bytes -> Zeiger
        owner = {}                                     # Zeiger -> Klasse
        for c in fam:
            kp = self.klass_ptr(c, by_name=(c is cls))
            if kp:
                needles[struct.pack("<Q", kp)] = kp
                owner[kp] = c
        if not needles:
            self.last_source = "none"
            return []
        kps = set(needles.values())
        if use_cache and self.objects is not None and any(c.full in self.known for c in fam):
            cached = sorted(a for c in fam for a in self.objects.get(c.full, ()))
            out = []
            for a in cached:
                if len(out) >= limit:
                    break
                if self._header_ok(a, kps):
                    out.append(a)
                else:                                  # Objekt gibt es nicht mehr -> aus dem Cache nehmen
                    for c in fam:
                        lst = self.objects.get(c.full)
                        if lst and a in lst:
                            lst.remove(a)
            self.last_source = "cache"
            return out
        found, per = [], {kp: [] for kp in kps}
        regs = self.heap_regions()
        cancelled = False
        for ri, (s, e) in enumerate(regs):
            jobs = _plan_jobs([(s, e)], chunk, 16)
            for pos, n, buf in ChunkStream(self._readers(), jobs, cancel):
                if buf is None:
                    continue
                for needle, kp in needles.items():
                    i = buf.find(needle, 0, n + 8)
                    while i >= 0 and len(found) < limit:
                        mon = buf[i + 8:i + 16]
                        if i < n and i % 8 == 0 and not self._in_class_struct(pos + i, tuple(kps)) and (len(mon) < 8 or mon == b"\0" * 8):
                            found.append(pos + i)
                            per[kp].append(pos + i)
                        i = buf.find(needle, i + 1, n + 8)
                if len(found) >= limit:
                    break
            if cancel and cancel():
                cancelled = True
                break
            if progress:
                progress(ri + 1, len(regs))
            if len(found) >= limit:
                break
        if self.objects is not None and len(found) < limit and not cancelled:
            for kp, lst in per.items():
                self.objects[owner[kp].full] = lst              # vollstaendiger Lauf: Cache dieser Klassen erneuern
                self.known.add(owner[kp].full)
        self.last_source = "scan"
        return sorted(found)

    def static_base(self, cls):
        """Adresse des Static-Fields-Blocks einer Klasse (statische Felder liegen dort bei ihren Offsets)."""
        kp = self.klass_ptr(cls)
        if not kp:
            return None
        try:
            p = struct.unpack("<Q", self.read(kp + self.static_off, 8))[0]
        except Exception:  # noqa: BLE001
            return None
        return p if p > 0x10000 else None

    def method_addr(self, m):
        return self.base + m.rva


# ---------------------------------------------------------------------------
# Patch-Bytes (x86-64)
# ---------------------------------------------------------------------------
def patch_return_int(value, wide=False):
    """mov eax, imm32 ; ret   (wide: mov rax, imm64).  Fuer bool/int/enum-Rückgaben."""
    if wide:
        return b"\x48\xb8" + struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF) + b"\xc3"
    return b"\xb8" + struct.pack("<I", value & 0xFFFFFFFF) + b"\xc3"


def patch_return_float(value):
    """mov eax, bits ; movd xmm0, eax ; ret"""
    return b"\xb8" + struct.pack("<f", value) + b"\x66\x0f\x6e\xc0\xc3"


def patch_return_double(value):
    """mov rax, bits ; movq xmm0, rax ; ret"""
    return b"\x48\xb8" + struct.pack("<d", value) + b"\x66\x48\x0f\x6e\xc0\xc3"


def patch_ret():
    """ret  (void-Methode tut nichts)"""
    return b"\xc3"


def make_patch(method, mode, value=None):
    """Methode + Modus -> Patch-Bytes.
       mode: 'true' | 'false' | 'value' (Zahl) | 'noop' (Methode überspringen)
       Prueft, ob der Rückgabetyp zu dem Modus passt - sonst ValueError mit verstaendlicher Meldung."""
    ret = method.ret
    prim = PRIMS.get(ret)
    if mode == "noop":
        if ret != "void":
            raise ValueError(f"'{method.name}' gibt {ret} zurück - leer machen geht nur bei void (sonst Absturz). "
                             "Nimm 'Wert zurückgeben'.")
        return patch_ret()
    if ret == "void":
        raise ValueError(f"'{method.name}' ist void und hat keinen Rückgabewert - wähle 'Methode leer machen'.")
    if mode in ("true", "false"):
        if prim != "bool":
            raise ValueError(f"'{method.name}' gibt {ret} zurück, nicht bool. Nimm 'Wert zurückgeben'.")
        return patch_return_int(1 if mode == "true" else 0)
    if mode == "value":
        if prim is None:
            raise ValueError(f"Rückgabetyp {ret} ist kein einfacher Zahlentyp (Objekt/Struct) - nicht patchbar.")
        if prim == "float":
            return patch_return_float(float(value))
        if prim == "double":
            return patch_return_double(float(value))
        if prim == "bool":
            return patch_return_int(1 if value else 0)
        v = int(value)
        return patch_return_int(v, wide=SIZES[prim] == 8)
    raise ValueError(f"unbekannter Modus {mode}")


def reapproj_for_patch(name, rva, original, new, author="", info=""):
    """Eintrag im ReaperPy-Projektformat (.reapproj): Offset = RVA im IL2CPP-Modul.
       ImageBase bleibt 0x0 - in ReaperPy die Image-Basis auf die IL2CPP-Modul-Basis stellen (Unity-Tab zeigt sie)."""
    sp = lambda b: " ".join(f"{x:02X}" for x in bytes(b))  # noqa: E731
    return {
        "name": name, "author": author, "Info": info, "ImageBase": "0x0",
        "Variables": [{"label": "OriginSource", "offset": hex(rva), "defaultValue": sp(original), "newValue": sp(new)}],
    }


def write_reapproj(folder, doc, fname=None):
    os.makedirs(folder, exist_ok=True)
    fname = fname or (re.sub(r"[^A-Za-z0-9_.-]+", "_", doc["name"]).strip("_")[:80] + ".reapproj")
    path = os.path.join(folder, fname)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path
