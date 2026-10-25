"""uesdk.py - liest Unreal-Engine-SDK-Dumps (Dumper-7 CppSDK, UE4SS-Header, Offsets.json, GObjects-Dump).

Erkannte Eingaben
  * SDK-Header  : Ordner oder einzelne .hpp/.h/.txt  (Dumper-7 `CppSDK/SDK/*_classes.hpp`,
                  `*_structs.hpp`; UE4SS `CXXHeaderDump`)
        class UHealthComponent : public UActorComponent { float Health; // 0x00E0(0x0004)(...) ... }
        float Health;   // 0x00E0 (size: 0x4)                       <- UE4SS-Stil
  * Offsets     : Offsets.json (beliebig verschachtelt, Schluessel wie OFFSET_GOBJECTS / GObjects) oder
                  `namespace Offsets { constexpr int32 GObjects = 0x...; }` aus Basic.hpp
  * GObjects    : GObjects-Dump.txt  ("[00001234] {0x...} Class Engine.Actor")

Das Format der Dumper ist nicht streng standardisiert und aendert sich je Version: der Parser ist
bewusst tolerant (unbekannte Zeilen werden uebersprungen) und zaehlt, was er nicht verstanden hat.
"""

import json
import os
import pathlib
import re
from dataclasses import dataclass, field

_HDR_EXT = (".hpp", ".h", ".txt", ".hxx")

_MEMBER_D7 = re.compile(
    r"^\s*(?P<type>[A-Za-z_][^;()]*?)\s+(?P<name>[A-Za-z_]\w*)(?P<arr>\[[^\]]*\])?(?:\s*:\s*(?P<bits>\d+))?\s*;"
    r"\s*//\s*0x(?P<off>[0-9A-Fa-f]+)\s*\(0x(?P<size>[0-9A-Fa-f]+)\)(?P<rest>.*)$"
)
_MEMBER_UE4SS = re.compile(
    r"^\s*(?P<type>[A-Za-z_][^;()]*?)\s+(?P<name>[A-Za-z_]\w*)(?P<arr>\[[^\]]*\])?(?:\s*:\s*(?P<bits>\d+))?\s*;"
    r"\s*//\s*0x(?P<off>[0-9A-Fa-f]+)\s*\(size:\s*0x(?P<size>[0-9A-Fa-f]+)\)(?P<rest>.*)$"
)
_CLASS = re.compile(
    r"^\s*(?P<kind>class|struct)\s+(?:alignas\(\w+\)\s+)?(?P<name>[A-Za-z_]\w*)"
    r"(?:\s+final)?(?:\s*:\s*(?:public|private|protected)?\s*(?P<parent>[A-Za-z_][\w:<>]*))?\s*$"
)
_CLASS_SIZE = re.compile(r"//\s*0x[0-9A-Fa-f]+\s*\(0x(?P<total>[0-9A-Fa-f]+)\s*-\s*0x(?P<par>[0-9A-Fa-f]+)\)")
_CLASS_PATH = re.compile(r"^\s*//\s*(?:Class|ScriptStruct)\s+(?P<path>[\w./:]+)")
_FUNC = re.compile(
    r"^\s*(?:static\s+)?(?P<ret>[A-Za-z_][\w:<>\*&,\s]*?)\s+(?P<name>[A-Za-z_]\w*)\((?P<args>[^;]*)\)\s*(?:const\s*)?;\s*(?://.*)?$"
)
_FUNC_COMMENT = re.compile(
    r"^\s*//\s*(?P<ret>[A-Za-z_][^()]*?)\s+(?P<name>[A-Za-z_]\w*)\((?P<args>[^)]*)\)\s*;\s*"
    r"//\s*flags\s+0x(?P<fl>[0-9A-Fa-f]+)(?:\s+native\s+0x(?P<nat>[0-9A-Fa-f]+))?"
)
_PROP = re.compile(r"\[0x(?P<pf>[0-9A-Fa-f]+)\]\s*(?P<pt>\w+)")
_ENUM_PATH = re.compile(r"^\s*//\s*Enum\s+(?P<path>[\w./:]+)")
_ENUM_HEAD = re.compile(r"^\s*enum\s+(?:class\s+|struct\s+)?(?P<name>[A-Za-z_]\w*)\s*(?::\s*(?P<under>[\w:]+))?\s*\{?\s*$")
_ENUM_VAL = re.compile(r"^\s*(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<val>-?(?:0[xX][0-9A-Fa-f]+|\d+))\s*,?\s*(?://.*)?$")
_SKIP_FUNCS = {"StaticClass", "GetDefaultObj", "GetDefaultObject", "StaticStruct", "GetDefaultObj"}
_DEFINE_CONST = re.compile(r"^\s*#\s*define\s+(\w+)\s+(0x[0-9A-Fa-f]+|\d+)\s*(?://.*)?$")  # GameDefines.hpp (ps4-unreal-dumper)
_OFFSET_CONST = re.compile(r"constexpr\s+(?:u?int(?:32|64)(?:_t)?|auto|size_t)\s+(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*;")


@dataclass
class Member:
    name: str
    type: str
    offset: int
    size: int
    owner: str = ""
    bit: int = -1  # Bitfeld-Index oder -1
    flags: str = ""
    ptype: str = ""  # z.B. "FloatProperty" (Header mit [0x..] Typ-Angabe)
    pflags: int = 0  # CPF_*-Flags, 0 = unbekannt


@dataclass
class Function:
    name: str
    ret: str = ""
    args: str = ""
    flags: int = 0  # FUNC_*-Flags (falls im Header)
    native: int = None  # ExecFunction laut Header (RVA oder VA - siehe dumpmem.native_convention)
    owner: str = ""

    @property
    def signature(self):
        return f"{self.ret} {self.name}({self.args})".strip()


@dataclass
class FuncParams:
    path: str  # /Script/Engine.GameplayStatics.SetGlobalTimeDilation
    size: int = 0
    params: list = field(default_factory=list)  # [Member] - pflags: 0x80 Parm, 0x100 Out, 0x400 Return


CPF_PARM, CPF_OUT, CPF_RETURN = 0x80, 0x100, 0x400


@dataclass
class UEnum:
    name: str
    underlying: str = ""
    path: str = ""
    values: list = field(default_factory=list)  # [(Name, Wert)] in Header-Reihenfolge

    def by_value(self):
        """{Wert: Name} (bei doppelten Werten gewinnt der erste Name)."""
        out = {}
        for k, v in self.values:
            out.setdefault(v, k)
        return out

    def by_name(self):
        return dict(self.values)


@dataclass
class UClass:
    name: str
    kind: str = "class"
    parent: str = ""
    size: int = 0
    path: str = ""
    members: list = field(default_factory=list)
    functions: list = field(default_factory=list)  # (name, signature)
    funcs: list = field(default_factory=list)  # [Function] inkl. native Adresse, wenn vorhanden


class SDK:
    def __init__(self):
        self.classes = {}
        self.enums = {}  # {Enum-Name: UEnum}  (z. B. ESBActorStatType)
        self.offsets = {}
        self.gobjects = []  # [(index, addr, typename, fullname)]
        self.stats = {"files": 0, "classes": 0, "members": 0, "skipped_lines": 0}
        self.meta = {}  # Text-Werte aus offsets.json (title, ...)
        self.func_params = {}  # {Funktionspfad: FuncParams}  (erst nach load_params)
        self.params_dirs = []

    def chain(self, name):
        """Klasse und alle Eltern (nahe -> fern)."""
        out, seen = [], set()
        while name and name in self.classes and name not in seen:
            seen.add(name)
            out.append(self.classes[name])
            name = self.classes[name].parent
        return out

    def all_members(self, name):
        """Alle Member der Klasse inkl. geerbter (Offsets sind im Dumper absolut)."""
        res = []
        for c in reversed(self.chain(name)):
            res += c.members
        return res

    def find_member(self, cls, member):
        for m in self.all_members(cls):
            if m.name == member:
                return m
        return None

    def load_params(self, sdk_dir=None):
        """Parameter-Layouts aller Funktionen laden (9000+ Structs je Spiel -> erst bei Bedarf)."""
        base = sdk_dir or (self.params_dirs[0] if self.params_dirs else None)
        if not base or self.func_params:
            return self.func_params
        for root, _d, names in os.walk(base):
            for n in sorted(names):
                if n.lower().endswith("_parameters.hpp"):
                    with open(os.path.join(root, n), encoding="utf-8", errors="replace") as handle:
                        parse_params_text(handle.read(), self.func_params)
        return self.func_params

    def params_for(self, cls_name, func_name):
        """FuncParams zu SDK-Klassenname + Funktion (Klassenpfad aus dem Header-Kommentar)."""
        c = self.classes.get(cls_name)
        if c is not None and c.path:
            fp = self.func_params.get(f"{c.path}.{func_name}")
            if fp:
                return fp
        suffix = f".{cls_name[1:] if cls_name[:1] in 'UAF' else cls_name}.{func_name}"
        for k, value in self.func_params.items():
            if k.endswith(suffix):
                return value
        return None

    def offset(self, *names, default=None):
        """Offsets.json/Basic.hpp-Wert nach Teilnamen (ohne Gross/Klein, ohne OFFSET_/Praefix)."""
        for n in names:
            k = _norm(n)
            if k in self.offsets:
                return self.offsets[k]
        return default


def _norm(s):
    s = re.sub(r"[^a-z0-9]", "", str(s).lower())
    return s[6:] if s.startswith("offset") and len(s) > 6 else s


def parse_header_text(text, sdk=None, source=""):
    """Ein Header-Text -> SDK (ergaenzt `sdk`)."""
    sdk = sdk or SDK()
    cur, pending_path, pending_size, depth = None, "", 0, 0
    cur_enum, pending_enum_path = None, ""
    in_offsets = False
    for line in text.splitlines():
        if cur_enum is not None:  # innerhalb eines enum-Blocks
            if line.lstrip().startswith("}"):
                sdk.enums[cur_enum.name] = cur_enum
                cur_enum = None
                continue
            me = _ENUM_VAL.match(line)
            if me:
                cur_enum.values.append((me.group("name"), int(me.group("val"), 0)))
            continue
        if cur is None:
            mep = _ENUM_PATH.match(line)
            if mep:
                pending_enum_path = mep.group("path")
                continue
            meh = _ENUM_HEAD.match(line)
            if meh:
                cur_enum = UEnum(meh.group("name"), meh.group("under") or "", pending_enum_path)
                pending_enum_path = ""
                continue
        if "namespace Offsets" in line:
            in_offsets = True
        if in_offsets:
            match = _OFFSET_CONST.search(line)
            if match:
                sdk.offsets[_norm(match.group(1))] = int(match.group(2), 0)
        md = _DEFINE_CONST.match(line)
        if md and cur is None:
            dname, dval = md.group(1), int(md.group(2), 0)
            if dname.startswith("OFF_"):  # OFF_UObject_Class -> UObject_Class
                dname = dname[4:]
            elif dname.endswith("_Offset"):  # GObjects_Offset -> GObjects
                dname = dname[: -len("_Offset")]
            sdk.offsets.setdefault(_norm(dname), dval)
            continue
        mp = _CLASS_PATH.match(line)
        if mp:
            pending_path = mp.group("path")
            continue
        ms = _CLASS_SIZE.search(line)
        if ms and cur is None:
            pending_size = max(
                int(ms.group("total"), 16), int(ms.group("par"), 16)
            )  # (gesamt - eltern) oder (start - ende)
            continue
        mc = _CLASS.match(line)
        if mc and cur is None and not line.rstrip().endswith(";"):
            name = mc.group("name")
            if name.endswith("_Params"):  # Funktions-Parameterbloecke, keine echten Klassen
                cur = UClass(name)  # (wird nicht in sdk.classes eingetragen)
                pending_path, pending_size, depth = "", 0, 0
                continue
            cur = sdk.classes.get(name) or UClass(name)
            cur.kind, cur.parent = mc.group("kind"), (mc.group("parent") or "").split("::")[-1]
            cur.size = pending_size or cur.size
            cur.path = pending_path or cur.path
            sdk.classes[name] = cur
            pending_path, pending_size, depth = "", 0, 0
            continue
        if cur is None:
            continue
        depth += line.count("{") - line.count("}")
        if "};" in line and depth <= 0 and "{" not in line:
            cur = None
            continue
        mm = _MEMBER_D7.match(line) or _MEMBER_UE4SS.match(line)
        if mm:
            name, rest = mm.group("name"), mm.group("rest") or ""
            if name.startswith(("Pad_", "pad_", "UnknownData", "Unk_")):
                continue
            bit = -1
            mb = re.search(r"BitIndex:\s*0x([0-9A-Fa-f]+)", rest)
            if mb:
                bit = int(mb.group(1), 16)
            elif mm.group("bits"):
                bit = 0
            mp2 = _PROP.search(rest)
            cur.members.append(
                Member(
                    name,
                    mm.group("type").strip(),
                    int(mm.group("off"), 16),
                    int(mm.group("size"), 16),
                    cur.name,
                    bit,
                    rest.strip(" ()"),
                    mp2.group("pt") if mp2 else "",
                    int(mp2.group("pf"), 16) if mp2 else 0,
                )
            )
            sdk.stats["members"] += 1
            continue
        mfc = _FUNC_COMMENT.match(line)
        if mfc and mfc.group("name") not in _SKIP_FUNCS:
            fn = Function(
                mfc.group("name"),
                mfc.group("ret").strip(),
                mfc.group("args").strip(),
                int(mfc.group("fl"), 16),
                int(mfc.group("nat"), 16) if mfc.group("nat") else None,
                cur.name,
            )
            cur.funcs.append(fn)
            cur.functions.append((fn.name, fn.signature))
            continue
        mf = _FUNC.match(line)
        if mf and mf.group("name") not in _SKIP_FUNCS and "=" not in mf.group("ret"):
            cur.functions.append((mf.group("name"), line.strip()))
            continue
        if line.strip() and not line.strip().startswith(("//", "public:", "private:", "protected:", "{", "}")):
            sdk.stats["skipped_lines"] += 1
    sdk.stats["classes"] = len(sdk.classes)
    return sdk


def parse_offsets_json(data, sdk=None):
    """Offsets.json -> sdk.offsets {normalisierter_name: int}.  Verschachtelte Objekte werden
    mit '.' verbunden; Werte duerfen int oder '0x..'-Text sein."""
    sdk = sdk or SDK()
    if isinstance(data, (str, bytes)):
        data = json.loads(data)

    def walk(node, prefix=""):
        if isinstance(node, dict):
            for k, value in node.items():
                walk(value, f"{prefix}{k}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{prefix}{i}")
        else:
            value = node
            if isinstance(value, str):
                try:
                    value = int(value, 0)
                except ValueError:
                    sdk.meta[str(prefix).lower()] = value
                    return
            if isinstance(value, bool) or not isinstance(value, int):
                return
            sdk.offsets[_norm(prefix)] = value

    walk(data)
    # auch die Kurzform ohne Eltern-Schluessel (z.B. {"Offsets": {"GObjects": ..}} -> gobjects)
    if isinstance(data, dict):

        def short(node):
            if isinstance(node, dict):
                for k, value in node.items():
                    if isinstance(value, (int, str)) and not isinstance(value, bool):
                        try:
                            iv = int(value, 0) if isinstance(value, str) else value
                        except ValueError:
                            continue
                        sdk.offsets.setdefault(_norm(k), iv)
                    else:
                        short(value)

        short(data)
    return sdk


_FUNC_PATH = re.compile(r"^\s*//\s*Function\s+(?P<path>\S+)\s*$")
_SIZE_LINE = re.compile(r"^\s*//\s*0x(?P<sz>[0-9A-Fa-f]+)\s*$")


def parse_params_text(text, out=None):
    """*_parameters.hpp -> {funktionspfad: FuncParams}.  Format:
    // Function /Script/Engine.GameplayStatics.SetGlobalTimeDilation
    // 0x0010
    struct UGameplayStatics_SetGlobalTimeDilation_Params { float TimeDilation; // 0x0008 (0x0004) [0x..] FloatProperty }"""
    out = out if out is not None else {}
    path, size, cur = None, 0, None
    for line in text.splitlines():
        if cur is None:
            match = _FUNC_PATH.match(line)
            if match:
                path, size = match.group("path"), 0
                continue
            match = _SIZE_LINE.match(line)
            if match and path:
                size = int(match.group("sz"), 16)
                continue
            if path and line.startswith("struct ") and "_Params" in line:
                cur = FuncParams(path, size)
            continue
        if line.strip().startswith("};"):
            out[cur.path] = cur
            cur, path = None, None
            continue
        mm = _MEMBER_D7.match(line)
        if mm and not mm.group("name").startswith(("Pad_", "pad_")):
            rest = mm.group("rest") or ""
            mp2 = _PROP.search(rest)
            cur.params.append(
                Member(
                    mm.group("name"),
                    mm.group("type").strip(),
                    int(mm.group("off"), 16),
                    int(mm.group("size"), 16),
                    "",
                    -1,
                    rest.strip(" ()"),
                    mp2.group("pt") if mp2 else "",
                    int(mp2.group("pf"), 16) if mp2 else 0,
                )
            )
    return out


_GOBJ = re.compile(
    r"\[\s*(?P<idx>[0-9A-Fa-f]+)\s*\]\s*\{?\s*(?P<addr>(?:0x)?[0-9A-Fa-f]{6,16})\s*\}?\s+(?P<type>[A-Za-z_]\w*)\s+(?P<full>\S.*?)\s*$"
)


def parse_gobjects_dump(text, sdk=None):
    sdk = sdk or SDK()
    for line in text.splitlines():
        match = _GOBJ.match(line)
        if match:
            sdk.gobjects.append(
                (int(match.group("idx"), 16), int(match.group("addr"), 16), match.group("type"), match.group("full"))
            )
    return sdk


def load(sdk_path=None, offsets_path=None, gobjects_path=None, skip_params=True):
    """Alles laden, was angegeben ist.  sdk_path: Ordner oder Datei."""
    sdk = SDK()
    files = []
    if sdk_path:
        sdk.params_dirs.append(sdk_path if os.path.isdir(sdk_path) else os.path.dirname(sdk_path))
        if os.path.isdir(sdk_path):
            for root, _d, names in os.walk(sdk_path):
                files += [
                    os.path.join(root, n)
                    for n in sorted(names)
                    if n.lower().endswith(_HDR_EXT) and not (skip_params and n.lower().endswith("_parameters.hpp"))
                ]
        else:
            files = [sdk_path]
    for file in files:
        with open(file, encoding="utf-8", errors="replace") as handle:
            parse_header_text(handle.read(), sdk, file)
        sdk.stats["files"] += 1
    if offsets_path:
        txt = pathlib.Path(offsets_path).read_text(encoding="utf-8-sig")
        if txt.lstrip().startswith(("{", "[")):
            parse_offsets_json(txt, sdk)
        else:
            parse_header_text(txt, sdk, offsets_path)
    if gobjects_path:
        with open(gobjects_path, encoding="utf-8", errors="replace") as handle:
            parse_gobjects_dump(handle.read(), sdk)
    return sdk
