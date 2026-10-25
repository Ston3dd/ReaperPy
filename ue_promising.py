"""ue_promising.py - die vielversprechendsten Cheat-Werte fuer JEDES Unreal-Engine-Spiel, live gefiltert.

Idee: Statt tausende Member zu listen, bei denen es im Spiel kein Objekt gibt, wird die lebende Objektwelt
(GObjects) gelesen und nur behalten, was wirklich existiert:

  1. Kandidaten aus dem SDK (Namens-Heuristik von uecheat: Leben, Munition, Geld, Ausdauer, XP, Cheat-Schalter ...)
     plus universelle Engine-Werte, die JEDES UE-Spiel hat (Laufgeschwindigkeit, Sprunghoehe, Schwerkraft,
     Zeitdilatation, bCanBeDamaged ...).
  2. Nur Klassen mit mindestens einer echten Instanz (Default__-Objekte zaehlen nicht, Unterklassen schon).
  3. Offsets live aus dem Spiel (Property-Kette), sonst Header.
  4. Stichprobe: Wert der ersten Instanzen lesen; unplausible Werte (NaN, riesig) fliegen raus,
     Werte != 0 und einzelne Instanzen (Spieler/GameState) bekommen Bonus.

Keine Oberflaeche, kein Netzwerk-Code: live-Objekt und read-Funktion werden uebergeben (testbar).
"""

import math
import re
from dataclasses import dataclass, field

import ue_quick as Q
import uecheat

# (SDK-Klasse, Member, Kategorie, Gewicht, Beschreibung) - Werte, die jedes UE-Spiel hat
UNIVERSAL = [
    ("UCharacterMovementComponent", "MaxWalkSpeed", "Bewegung", 11.0, "Lauftempo"),
    ("UCharacterMovementComponent", "MaxWalkSpeedCrouched", "Bewegung", 7.0, "Tempo geduckt"),
    ("UCharacterMovementComponent", "MaxSwimSpeed", "Bewegung", 7.0, "Schwimmtempo"),
    ("UCharacterMovementComponent", "MaxFlySpeed", "Bewegung", 7.0, "Flugtempo"),
    ("UCharacterMovementComponent", "MaxAcceleration", "Bewegung", 6.0, "Beschleunigung"),
    ("UCharacterMovementComponent", "JumpZVelocity", "Bewegung", 10.0, "Sprunghoehe"),
    ("UCharacterMovementComponent", "GravityScale", "Bewegung", 9.0, "Schwerkraft"),
    ("UCharacterMovementComponent", "AirControl", "Bewegung", 5.0, "Luftkontrolle"),
    ("ACharacter", "JumpMaxCount", "Bewegung", 8.0, "Mehrfachsprung (Anzahl)"),
    ("AActor", "CustomTimeDilation", "Zeit", 8.0, "Eigene Zeit des Actors"),
    ("AWorldSettings", "TimeDilation", "Zeit", 9.0, "Spielgeschwindigkeit (Zeitlupe/Turbo)"),
    ("AActor", "bCanBeDamaged", "Cheat-Schalter", 10.0, "Unverwundbar (0 = kein Schaden)"),
    ("UCameraComponent", "FieldOfView", "Kamera", 4.0, "Sichtfeld"),
    ("USpringArmComponent", "TargetArmLength", "Kamera", 4.0, "Kameraabstand"),
]


# Klassen, die zwar Objekte haben, aber nie Spielwerte (Grafik, Engine-Interna, Sky/Wetter-Plugins, Netzwerk)
NOISE_CLASS = re.compile(
    r"^[AUF]?(Canvas|Engine$|GeometryCollection|MediaPlate|MediaPlayer|Paper|ReverbEffect|SceneCapture|"
    r"CineCamera|Ultra_?Dynamic|UDS|Player$|NetDriver|NetConnection|Channel|Niagara|Landscape|Foliage|"
    r"Material|Texture|PostProcess|Sound|Audio|Widget|UMG|Slate|StaticMesh|SkeletalMesh|Particle|Decal|"
    r"ExponentialHeightFog|AtmosphericFog|SkyAtmosphere|SkyLight|DirectionalLight|PointLight|SpotLight|"
    r"Lumen|Nanite|Chaos|Physics|Console|GameViewport|LocalPlayer|Cheat\w*Manager$|VolumetricCloud|"
    r"CameraComponent|SaveGame|PatrolPath|RootMotion|Landmass|Water|Spline|Brush|Volume$|WBP_|Rig|"
    r"[A-Za-z0-9_]*Action_C$|[A-Za-z0-9_]*Skill\d+|"
    r"[A-Za-z]*PlayerCameraManager|[A-Za-z]*CameraModifier|[A-Za-z]*Notify|[A-Za-z]*NotifyState)"
)
# Namensbestandteile, die bei Heuristik-Treffern fast immer Fehlalarm sind (ClipX, MipLevel, SegmentOverlapAmount ...)
NOISE_WORDS = {
    "clipx", "clipy", "nearclip", "farclip", "clipplane", "mip", "blend", "absorption", "setid", "overlap",
    "focus", "density", "exponent", "spacing", "brightness", "wisps", "sun", "balance", "netspeed", "seamless",
    "travel", "reverb", "follow", "pitch", "yaw", "roll", "interp", "smooth", "replication", "abandon",
    "interaction", "upscale", "queue", "push", "knockback", "decrease", "threshold", "cone", "collision",
    "crafting", "dead", "deadcount", "completed", "last", "direction", "preview", "debug", "editor",
    "count", "counter", "cost", "ortho", "sample", "reflection", "variation", "weight", "avoidance", "setid",
    "notifystate", "patch", "correction", "range", "scaling", "timer",
}


def is_noise(live, sdk, cls, member):
    if NOISE_CLASS.search(cls):
        return True
    low = member.lower()
    from uecheat import words

    toks = set(words(member)) | {low}
    return bool(toks & NOISE_WORDS) or any(w in low for w in ("clipx", "clipy", "miplevel", "overlapamount"))


@dataclass
class Promising:
    target: object  # ue_quick.Target
    count: int  # Instanzen im Spiel
    score: float
    category: str
    reasons: list = field(default_factory=list)
    sample: str = ""  # Anzeige des ersten gelesenen Werts
    universal: bool = False

    @property
    def key(self):
        return self.target.key


def class_counts(live, per_name_addrs=6):
    """-> (counts, addrs): Instanzen je Klassenname (inkl. Unterklassen, ohne Default__-Objekte) und je Name
    die ersten Adressen.  Ein Durchgang ueber den Index, Ahnenketten werden je Klasse nur einmal gebaut."""
    if live.index is None:
        live.build_index()
    by_class = {}
    for addr, (_i, cl, nm) in live.index.items():
        if nm.startswith("Default__") or not cl:
            continue
        if getattr(live, "is_template", None) and live.is_template(addr):
            continue  # Blueprint-Vorlagen und ihre Unterobjekte sind keine Spielobjekte
        bucket = by_class.setdefault(cl, [0, []])
        bucket[0] += 1
        if len(bucket[1]) < per_name_addrs:
            bucket[1].append(addr)
    counts, addrs = {}, {}
    for cl, (n, sample) in by_class.items():
        for anc in live.ancestors(cl):
            name = live.index.get(anc, (0, 0, ""))[2]
            if not name:
                continue
            counts[name] = counts.get(name, 0) + n
            lst = addrs.setdefault(name, [])
            for a in sample:
                if len(lst) < per_name_addrs:
                    lst.append(a)
    return counts, addrs


def _count_for(live, counts, sdk_name):
    names = set(live._name_variants(sdk_name))
    names |= {n + "_C" for n in list(names)}
    return max((counts.get(n, 0) for n in names), default=0)


def _addrs_for(live, addrs, sdk_name):
    names = set(live._name_variants(sdk_name))
    names |= {n + "_C" for n in list(names)}
    out = []
    for n in sorted(names):
        for a in addrs.get(n, []):
            if a not in out:
                out.append(a)
    return out


def presence_bonus(n):
    if n == 1:
        return 4.0  # genau ein Objekt: Spieler, GameState, Manager
    if n <= 5:
        return 2.0
    if n > 200:
        return -2.0  # Massenobjekte (Foliage, Props)
    return 0.0


def _plausible(t, val):
    if val is None:
        return False
    if isinstance(val, float):
        return math.isfinite(val) and abs(val) < 1e12
    return True


def _nonzero(val):
    return val is not None and not Q.is_zero(val)


def _target(sdk, cls, member):
    m = sdk.find_member(cls, member)  # sucht auch in den Elternklassen
    if m is None:
        return None
    got = Q.expand_member(sdk, cls, member, m.type, m.offset, m.bit)
    return got[0] if got else None  # Wrapper-Struct (GAS): CurrentValue


def find_promising(live, sdk, read=None, min_score=6.0, per_category=10, total=80, preselect=400, progress=None):
    """-> [Promising] absteigend nach Score.  read(addr, n) -> bytes fuer die Wert-Stichprobe (None = ohne)."""
    counts, addrs = class_counts(live)
    pool = []  # (adjusted, candidate/universal tuple)
    seen = set()
    for c in uecheat.find_candidates(sdk, min_score):
        n = _count_for(live, counts, c.cls)
        if n <= 0:
            continue
        pool.append((c.score + presence_bonus(n), "cand", c, n))
        seen.add((c.cls, c.member))
    for cls, member, cat, weight, desc in UNIVERSAL:
        if (cls, member) in seen:
            continue
        n = _count_for(live, counts, cls)
        if n <= 0 or _target(sdk, cls, member) is None:
            continue
        pool.append((weight + presence_bonus(n), "uni", (cls, member, cat, weight, desc), n))
    pool.sort(key=lambda x: -x[0])
    pool = pool[:preselect]

    out = []
    for k, (adj, kind, item, n) in enumerate(pool):
        if progress:
            progress(k, len(pool))
        if kind == "cand" and is_noise(live, sdk, item.cls, item.member):
            continue
        if kind == "cand":
            t = _target(sdk, item.cls, item.member)
            if t is None:
                continue
            t.category, t.score = item.category, item.score
            cat, reasons, universal = item.category, list(item.reasons), False
        else:
            cls, member, cat, weight, desc = item
            t = _target(sdk, cls, member)
            t.category, t.score = cat, weight
            reasons, universal = [f"Standard-Engine-Wert: {desc}"], True
        try:
            live_off = live.member_offset(t.cls, t.parent or t.member)
        except Exception:
            live_off = None
        if live_off is not None:
            t.offset = live_off + t.sub
            reasons.append("Offset live aus dem Spiel gelesen")
        sample, score = "", adj
        if read is not None:
            vals = []
            for a in _addrs_for(live, addrs, t.cls)[:3]:
                try:
                    vals.append(Q.read_value(read, a + t.offset, t))
                except Exception:
                    continue
            if not vals:
                continue  # Speicher nicht lesbar -> Offset/Klasse stimmt nicht
            if not any(_plausible(t, v[0]) for v in vals):
                continue  # NaN/riesig: falscher Offset
            good = [v for v in vals if _plausible(t, v[0])]
            nz = [v for v in good if _nonzero(v[0])]
            sample = (nz or good)[0][1]
            if nz:
                score += 2.0
                reasons.append("Wert != 0 im Spiel")
            elif cat != "Cheat-Schalter":
                score -= 1.0
        out.append(Promising(t, n, round(score, 2), cat, reasons, sample, universal))
    out.sort(key=lambda p: (-p.score, p.target.cls, p.target.offset))
    # je Kategorie begrenzen, damit nicht zehn Leben-Werte der gleichen Klasse alles belegen
    per, picked, fam = {}, [], set()
    for p in out:
        key = (p.target.cls, re.sub(r"\d+", "#", p.target.member))  # Level1..Level6 -> eine Zeile
        if key in fam:
            continue
        fam.add(key)
        if per.get(p.category, 0) >= per_category:
            continue
        per[p.category] = per.get(p.category, 0) + 1
        picked.append(p)
        if len(picked) >= total:
            break
    return picked
