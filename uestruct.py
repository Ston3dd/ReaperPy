"""uestruct.py - erkennt in jedem UE-SDK automatisch Struct-Wrapper um Zahlenwerte.

Viele Spiele packen Leben/Ausdauer/Mana nicht in ein nacktes float, sondern in einen kleinen Struct:
  GAS:        FGameplayAttributeData { BaseValue, CurrentValue }
  Palworld:   FFixedPoint64 { Value }
  Eigene:     FStatValue { Current, Max }, FFloatStat { Value, Min, Max } ...
Statt jeden Typ von Hand einzutragen, gilt die Regel: ein Struct, dessen Felder (ohne Pads) alle einfache
Zahlen/Bools sind, hoechstens 4 Felder, hoechstens 0x20 Byte, und der nicht nach Engine-Mathe/Handles/IDs aussieht,
ist ein Wrapper.  Die Felder werden einzeln anklickbar (Member.Feld), das wichtigste (CurrentValue/Value ...) zuerst.
Keine Abhaengigkeiten, deshalb von ue_quick und uecheat nutzbar.
"""

import re

NUM = {
    "float", "double", "int32", "int", "int64", "uint32", "uint64", "int16", "uint16", "uint8", "int8",
    "int32_t", "int64_t", "uint32_t", "uint64_t", "int16_t", "uint16_t", "uint8_t", "int8_t", "bool",
}
# bekannte Wrapper mit fester Reihenfolge (Offsets werden trotzdem aus dem SDK gelesen, wenn dort vorhanden)
KNOWN = {
    "fgameplayattributedata": [("CurrentValue", 0xC, "float"), ("BaseValue", 0x8, "float")],
}
# Engine-Mathe, Zeit, Handles, IDs ... : Zahlen, aber keine Spielwerte
SKIP_STRUCT = re.compile(
    r"^F(Vector|Vector2D|Vector2f|Vector3|Vector4|Rotator|Quat|Transform|LinearColor|Color|Plane|Matrix|Box|Sphere|"
    r"Guid|DateTime|Timespan|IntPoint|IntVector|IntRect|Margin|Geometry|FrameNumber|FrameRate|FrameTime|Timecode|"
    r"HitResult|RandomStream|Int\d*|Float(Range|Interval)|Range|Interval|Bounds|Extent|Rect|Key|Rand)|"
    r"(Handle|Id|ID|Index|Serial|Flags|Hash|Mask|Tag|Version|Bounds|Range|Seed|Key|Token|Coord|Scale|Angle|Axis|UV)$"
)
# Struct-Namen aus Animation, Rendering, Audio, Physik, UI ... : nie Spielwerte, auch wenn sie "Value" heissen
NOISE_STRUCT = re.compile(
    r"Anim|Pose|Cloth|Niagara|Rig|Platform|Blend|Camera|Slate|Filter|Solver|Metasound|Submix|MovieScene|Dataflow|"
    r"Perlin|Gizmo|PCG|Media|Virtual|Lighting|Index|Identifier|Crc|Version|Orbit|Fade|Input|Mvvm|Registry|Audio|"
    r"Acoustics|Collision|Skin|Material|Mesh|Texture|Light|Spline|Curve|Particle|Emitter|Sound|Volume|Reverb|"
    r"Keyboard|Widget|Brush|Style|Font|Margin|Timing|Statistics$|Chaos|Physics|Render|Shader|Cache|Bias|Scale|"
    r"Noise|Sensor|Lod|Streaming|Network|Replication|Debug|Editor|Tunables?$",
    re.I,
)
FIXED = {"ffixedpoint64", "ffixedpoint", "ffixedpoint32"}  # ue_quick kennt sie als eigenen Typ (Anzeige x1000)
# Mindestens eines dieser Felder muss vorkommen, sonst ist es kein Spielwert-Wrapper
VALUE_FIELDS = {"value", "current", "currentvalue", "cur", "now", "amount", "points", "quantity", "level", "stack"}
SKIP_FIELD = {"handle", "index", "id", "serial", "key", "hash", "seed", "version", "token", "tag", "type", "mask"}
PRIORITY = ("currentvalue", "current", "cur", "value", "now", "amount", "count", "basevalue", "base")


def norm_type(t):
    return (t or "").replace("struct ", "").replace("class ", "").replace(" ", "").lower()


def _is_pad(name):
    return name.startswith(("Pad_", "UnknownData", "Padding", "Unk_"))


def wrapper_fields(sdk, mtype):
    """Struct-Typname -> [(Feldname, Offset im Struct, Typ)], wichtigstes Feld zuerst; [] = kein Wrapper."""
    if sdk is None or not mtype:
        return []
    cache = sdk.__dict__.setdefault("_wrapper_cache", {})
    key = norm_type(mtype)
    if key in cache:
        return cache[key]
    cache[key] = result = _detect(sdk, mtype, key)
    return result


def _detect(sdk, mtype, key):
    name = mtype.replace("struct ", "").replace("class ", "").strip()
    cls = sdk.classes.get(name)
    known = KNOWN.get(key)
    if known:
        have = {m.name: m for m in cls.members} if cls else {}
        return [(n, have[n].offset if n in have else off, have[n].type if n in have else typ) for n, off, typ in known]
    if key in FIXED or cls is None or getattr(cls, "kind", "struct") != "struct":
        return []
    if SKIP_STRUCT.search(name) or NOISE_STRUCT.search(name):
        return []
    try:
        members = sdk.all_members(name)
    except Exception:
        members = cls.members
    real = [m for m in members if not _is_pad(m.name)]
    if not (1 <= len(real) <= 4):
        return []
    if any(m.name.lower() in SKIP_FIELD for m in real):
        return []
    if not any(m.name.lower() in VALUE_FIELDS for m in real):
        return []
    if any(norm_type(m.type) not in NUM or getattr(m, "ptype", "") == "StructProperty" for m in real):
        return []
    span = max(m.offset + m.size for m in real) - min(m.offset for m in real)
    if span > 0x20:
        return []
    order = {n: i for i, n in enumerate(PRIORITY)}
    real.sort(key=lambda m: (order.get(m.name.lower(), 99), 0 if norm_type(m.type) in ("float", "double") else 1, m.offset))
    return [(m.name, m.offset, m.type) for m in real]


def representative_type(sdk, mtype):
    """Typ des wichtigsten Felds (fuer die Cheat-Bewertung) oder None."""
    fields = wrapper_fields(sdk, mtype)
    return fields[0][2] if fields else None
