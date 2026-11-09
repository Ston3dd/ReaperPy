"""whois.py - Spieler oder Gegner?  (ohne tkinter)

Problem: Spieler und Gegner teilen sich denselben Code zum Veraendern des Lebens.  Wer dort nur "Leben sinkt nicht"
patcht, macht ALLE unsterblich.  Dieses Modul findet heraus, woran man den Spieler erkennt:

  1. Ein Logger-Hook (Code-Cave, Ringpuffer) schreibt bei jedem Durchlauf der Stelle alle Register und 40 Stack-Werte
     (Aufrufer-Kette) in den Speicher - das Spiel wird nie angehalten.
  2. Phase A: nur der SPIELER wird getroffen.  Phase B: nur GEGNER werden getroffen.
  3. analyze() sucht Merkmale, die in A immer anders sind als in B:
       caller  - eine Rueckkehradresse an einer festen Stack-Position (stabil nach Neustart!)
       field   - ein fester Wert im Objekt (z. B. Team-Nummer), das ein Register anzeigt (stabil nach Neustart)
       object  - die Objekt-Adresse selbst (nur bis zum Spielende gueltig)
  4. guard_cave() baut den Cave-Code, der den Cheat nur fuer Spieler (oder nur fuer Gegner) ausfuehrt.

Ringpuffer (Anfang des Datenblocks)  +0x00 u32 Schreibindex, +0x40 Eintrag[N], je 512 Byte
Eintrag  +0x00 seq (zuletzt geschrieben)  +0x08 rax +0x10 rbx +0x18 rcx +0x20 rdx +0x28 rsi +0x30 rdi +0x38 rbp
         +0x40 r8 ... +0x78 r15  +0x80 rsp beim Eintritt  +0x88 Stack[0..39]
"""
import re
import struct
import time
from collections import Counter

REC = 512
HEADER = 0x40
NSTACK = 40
REGS = ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15")
_REG_OFF = {r: 8 + 8 * i for i, r in enumerate(REGS)}            # rax +8 ... r15 +0x78
_RSP_OFF = 0x80
_STACK_OFF = 0x88
RED_ZONE = 0x80


def stub_asm(data_addr, ring_entries=512):
    """Logging-Teil der Cave (Intel-Syntax); erhaelt alle Register, Flags und die Red Zone."""
    if ring_entries & (ring_entries - 1) or ring_entries < 2:
        raise ValueError("ring_entries muss eine Zweierpotenz sein")
    L = [f"lea rsp, [rsp - {RED_ZONE:#x}]", "pushfq", "push rax", "push rdx", "sub rsp, 8",
         f"mov rdx, {data_addr:#x}", "mov eax, 1", "lock xadd dword ptr [rdx], eax",
         "mov dword ptr [rsp], eax", f"and eax, {ring_entries - 1:#x}", "shl eax, 9",
         f"lea rdx, [rdx + rax + {HEADER:#x}]"]
    for r in REGS:
        if r in ("rax", "rdx"):
            continue
        L.append(f"mov qword ptr [rdx + {_REG_OFF[r]:#x}], {r}")
    orig_rsp = 0x20 + RED_ZONE                                  # rsp + dies = rsp beim Eintritt
    L += ["mov rax, qword ptr [rsp + 0x10]", f"mov qword ptr [rdx + {_REG_OFF['rax']:#x}], rax",
          "mov rax, qword ptr [rsp + 8]", f"mov qword ptr [rdx + {_REG_OFF['rdx']:#x}], rax",
          f"lea rax, [rsp + {orig_rsp:#x}]", f"mov qword ptr [rdx + {_RSP_OFF:#x}], rax"]
    for i in range(NSTACK):
        L += [f"mov rax, qword ptr [rsp + {orig_rsp + 8 * i:#x}]", f"mov qword ptr [rdx + {_STACK_OFF + 8 * i:#x}], rax"]
    L += ["mov eax, dword ptr [rsp]", "add eax, 1", "mov qword ptr [rdx], rax",
          "add rsp, 8", "pop rdx", "pop rax", "popfq", f"lea rsp, [rsp + {RED_ZONE:#x}]"]
    return L


def parse_record(raw):
    v = struct.unpack("<64Q", raw[:REC])
    regs = {r: v[1 + i] for i, r in enumerate(REGS)}
    return {"seq": v[0], "regs": regs, "rsp": v[_RSP_OFF // 8], "stack": list(v[_STACK_OFF // 8:_STACK_OFF // 8 + NSTACK])}


def collect(read, data_addr, ring_entries, last):
    """Neue Eintraege seit `last` -> (eintraege, neuer_index, verloren)."""
    cur = struct.unpack("<I", read(data_addr, 4))[0]
    new = (cur - last) & 0xFFFFFFFF
    if new == 0 or new > 0x80000000:
        return [], last, 0
    lost = 0
    if new > ring_entries:
        lost = new - ring_entries
        last = (last + lost) & 0xFFFFFFFF
        new = ring_entries
    first = last & (ring_entries - 1)
    n1 = min(new, ring_entries - first)
    raw = read(data_addr + HEADER + first * REC, n1 * REC)
    if new > n1:
        raw += read(data_addr + HEADER, (new - n1) * REC)
    out, idx = [], last
    for i in range(new):
        rec = parse_record(raw[i * REC:(i + 1) * REC])
        if rec["seq"] != ((idx + 1) & 0xFFFFFFFF):
            break
        rec["index"] = idx
        out.append(rec)
        idx = (idx + 1) & 0xFFFFFFFF
    return out, idx, lost


class ProbeSession:
    """Hook an einer Adresse (mitten in einer Funktion ist ok): Cave = Logging + verschobene Original-Befehle."""

    def __init__(self, backend, hook_addr, ring_entries=512):
        self.b, self.hook, self.ring = backend, hook_addr, ring_entries
        self.data = self.cave = None
        self.original = b""
        self.last = self.lost = 0
        self.active = False

    def start(self):
        import asm_tools
        import patch_engine as pe
        b = self.b
        code = bytes(b.read(self.hook, 32) or b"")
        if len(code) < 16:
            raise RuntimeError(f"{self.hook:#x} nicht lesbar")
        if code[:1] == b"\xE9":
            raise RuntimeError("an der Adresse liegt schon ein JMP (anderer Hook?) - erst entfernen")
        info = asm_tools.build_cave_hook(code, self.hook, 8)
        size = info["size"]
        self.original = code[:size]
        total = HEADER + self.ring * REC
        self.data = b.alloc_mem(total)
        b.write(self.data, bytes(total))
        body = [ln.strip() for ln in info["cave"].splitlines() if ln.strip() and not ln.strip().startswith(";")]
        body = [re.sub(r"\bOriginReturn\b", f"{self.hook + size:#x}", ln) for ln in body]
        lines = stub_asm(self.data, self.ring) + body
        self.cave = b.find_cave(self.hook, 0x1000)
        lines = pe._resolve_rip_tokens(b, lines, self.cave, self.hook)
        cave_bytes = pe._extract_bytes(b.assemble("\n".join(lines) + "\n", self.cave))
        try:
            b.set_rwx(self.cave, 0x1000)
        except Exception:  # noqa: BLE001
            pass
        b.write(self.cave, cave_bytes)
        if bytes(b.read(self.cave, len(cave_bytes)) or b"") != cave_bytes:
            raise RuntimeError("Cave-Write nicht verifiziert")
        hook = pe.build_hook(b, self.hook, self.cave, length=8)
        if size > 8:
            hook = hook + b"\x90" * (size - 8)
        b.write(self.hook, hook)
        time.sleep(0.1)
        self.last, self.lost, self.active = 0, 0, True
        return {"data": self.data, "cave": self.cave, "cave_size": len(cave_bytes), "stolen": size}

    def poll(self):
        recs, self.last, lost = collect(self.b.read, self.data, self.ring, self.last)
        self.lost += lost
        return recs

    def stop(self):
        if self.active:
            self.b.write(self.hook, self.original)
            self.active = False


# ------------------------------------------------------------------
# Auswertung
# ------------------------------------------------------------------
def _trim(values, keep=0.1):
    """Menge der Werte; seltene Ausreisser (nicht mehr als 10 %) fallen weg, wenn es sonst mehrere gibt."""
    c = Counter(values)
    total = sum(c.values())
    if not total:
        return set()
    big = {v for v, n in c.items() if n > keep * total}
    return big or set(c)


def _share(values, ok):
    return sum(1 for v in values if ok(v)) / len(values) if values else 0.0


def _ptr(v):
    return 0x10000 <= v <= 0x7FFFFFFFFFFF


def analyze(a, b, read=None, is_code=None, recheck=None, max_objs=6, min_samples=2):
    """a = Eintraege der Phase 'Spieler', b = Phase 'Gegner'.  -> Liste von Merkmalen, bestes zuerst.

    read(addr, n)->bytes (fuer Objekt-Felder, optional);  is_code(addr)->bool (Aufrufer-Erkennung);
    recheck: Funktion ohne Argumente, die kurz wartet (Felder, die sich zwischendurch aendern, fallen weg)."""
    out = []
    if len(a) < min_samples or len(b) < min_samples:
        return out
    # ---- Aufrufer (Stack-Position) ----
    if is_code is not None:
        for k in range(NSTACK):
            va, vb = [s["stack"][k] for s in a], [s["stack"][k] for s in b]
            if _share(va, is_code) < 0.9 or _share(vb, is_code) < 0.9:
                continue
            sa, sb = _trim(va), _trim(vb)
            if sa and sb and not (sa & sb):
                out.append({"kind": "caller", "slot": k, "player": sorted(sa), "enemy": sorted(sb), "stable": True,
                            "score": 100 - 3 * k - 5 * (len(sa) + len(sb) - 2), "confidence": _conf(a, b)})
    # ---- Objekt-Register und Felder ----
    for reg in REGS:
        if reg in ("rsp", "rbp"):
            continue
        va, vb = [s["regs"][reg] for s in a], [s["regs"][reg] for s in b]
        if _share(va, _ptr) < 0.9 or _share(vb, _ptr) < 0.9:
            continue
        sa, sb = _trim(va), _trim(vb)
        if not sa or not sb or (sa & sb):
            continue
        objs_b = len(sb)
        conf = "high" if objs_b >= 3 else "low"
        out.append({"kind": "object", "reg": reg, "player": sorted(sa), "enemy": sorted(sb), "stable": False,
                    "score": 20 - len(sa) - len(sb), "confidence": conf})
        if read is not None:
            out += _fields(reg, sorted(sa)[:max_objs], sorted(sb)[:max_objs], read, recheck, conf)
    out.sort(key=lambda c: -c["score"])
    return out


def _conf(a, b):
    return "high" if min(len(a), len(b)) >= 5 else "low"


def _snap(read, objs, size=0x200):
    d = {}
    for o in objs:
        try:
            raw = bytes(read(o, size) or b"")
        except Exception:  # noqa: BLE001
            raw = b""
        if len(raw) == size:
            d[o] = raw
    return d


def _fields(reg, objs_a, objs_b, read, recheck, conf):
    sn = _snap(read, objs_a + objs_b)
    if recheck is not None:
        recheck()
        sn2 = _snap(read, objs_a + objs_b)
    else:
        sn2 = sn
    oa = [o for o in objs_a if o in sn and o in sn2]
    ob = [o for o in objs_b if o in sn and o in sn2]
    if not oa or not ob:
        return []
    res = []
    for off in range(0, 0x200 - 3, 4):
        def val(snap, o):
            return struct.unpack_from("<I", snap[o], off)[0]
        if any(val(sn, o) != val(sn2, o) for o in oa + ob):
            continue                                            # aendert sich laufend (Leben, Zeit ...)
        sa, sb = {val(sn, o) for o in oa}, {val(sn, o) for o in ob}
        if sa & sb or len(sa) > 2 or len(sb) > 4:
            continue
        if len(ob) >= 3 and len(sb) == len(ob):
            continue                                            # bei jedem Gegner anders (Leben, ID ...): kein Merkmal
        enum = all(v < 0x10000 for v in sa | sb)
        if not enum and not (all(_ptr(v) or v == 0 for v in sa | sb)):
            continue                                            # Kommazahlen / Zufallswerte nicht
        if not enum:
            continue                                            # 32-Bit-Zeiger haben keine feste Bedeutung
        res.append({"kind": "field", "reg": reg, "off": off, "size": 4, "player": sorted(sa), "enemy": sorted(sb),
                    "stable": True, "score": 80 - 2 * (len(sa) + len(sb)) - off // 64,
                    "confidence": conf if len(ob) >= 2 else "low"})
    return res


def describe(c, base=0, lang="de"):
    """Ein Merkmal in Worten."""
    de = lang != "en"
    def fmt(vs):
        return ", ".join(f"{v:#x}" for v in vs)
    if c["kind"] == "caller":
        offs = ", ".join(f"+{v - base:#x}" for v in c["player"]) if base else fmt(c["player"])
        eo = ", ".join(f"+{v - base:#x}" for v in c["enemy"]) if base else fmt(c["enemy"])
        return (f"Aufrufer (Stack-Position {c['slot']}): Spieler kommt von {offs}, Gegner von {eo}. Bleibt nach einem "
                f"Neustart des Spiels gleich." if de else
                f"Caller (stack position {c['slot']}): the player comes from {offs}, enemies from {eo}. Stays the same "
                f"after restarting the game.")
    if c["kind"] == "field":
        return (f"Feld +{c['off']:#x} im Objekt von {c['reg']}: Spieler hat {fmt(c['player'])}, Gegner haben "
                f"{fmt(c['enemy'])} (z. B. eine Team-Nummer). Bleibt nach einem Neustart gleich." if de else
                f"Field +{c['off']:#x} in the object of {c['reg']}: the player has {fmt(c['player'])}, enemies have "
                f"{fmt(c['enemy'])} (e.g. a team number). Stays the same after restarting the game.")
    return (f"Objekt-Adresse in {c['reg']}: Spieler {fmt(c['player'])}. Gilt nur bis zum Beenden des Spiels - nach jedem "
            f"Start neu ermitteln." if de else
            f"Object address in {c['reg']}: player {fmt(c['player'])}. Only valid until the game is closed - detect again "
            f"after every start.")


# ------------------------------------------------------------------
# Cave mit Pruefung
# ------------------------------------------------------------------
def _hit_lines(c, hook_addr):
    """Pruef-Zeilen: springen nach 'WhoHit', wenn der SPIELER erkannt wurde (Register/Flags setzt der Aufrufer danach
    zurueck).  Gibt (zeilen, hilfsregister oder None) zurueck."""
    lines = []
    if c["kind"] == "caller":
        for v in c["player"]:
            d = v - hook_addr
            lines += [f"lea rax, [rip + @hook{'+' if d >= 0 else '-'}{abs(d):#x}]",
                      f"cmp qword ptr [rsp + {RED_ZONE + 16 + 8 * c['slot']:#x}], rax", "je WhoHit"]
        return lines, "rax"
    if c["kind"] == "field":
        for v in c["player"]:
            lines += [f"cmp dword ptr [{c['reg']} + {c['off']:#x}], {v:#x}", "je WhoHit"]
        return lines, None
    scratch = "rcx" if c["reg"] == "rax" else "rax"
    for v in c["player"]:
        lines += [f"mov {scratch}, {v:#x}", f"cmp {c['reg']}, {scratch}", "je WhoHit"]
    return lines, scratch


def guard_cave(c, hook_addr, cheat, body, apply_to="player", label_prefix=""):
    """Cave-Text: der Cheat (`cheat`-Zeilen) laeuft nur fuer den Spieler (apply_to='player') oder nur fuer Gegner
    ('enemy'); sonst laufen die Original-Befehle (`body`).  Zeilen ohne 'jmp OriginReturn' uebergeben."""
    if apply_to not in ("player", "enemy"):
        raise ValueError("apply_to")
    hit_actions, miss_actions = (cheat, body) if apply_to == "player" else (body, cheat)
    test, scratch = _hit_lines(c, hook_addr)
    hit_l = label_prefix + "WhoHit"
    test = [ln.replace("WhoHit", hit_l) for ln in test]
    out = [f"; Pruefung: {c['kind']} - nur " + ("Spieler" if apply_to == "player" else "Gegner")]
    out += [f"lea rsp, [rsp - {RED_ZONE:#x}]", "pushfq"]
    if scratch:
        out.append(f"push {scratch}")
    out += test
    restore = ([f"pop {scratch}"] if scratch else []) + ["popfq", f"lea rsp, [rsp + {RED_ZONE:#x}]"]
    out += restore + miss_actions + ["jmp OriginReturn", f"{hit_l}:"]
    out += restore + hit_actions + ["jmp OriginReturn"]
    return "\n".join(out) + "\n"
