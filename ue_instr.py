"""ue_instr.py - findet im Spiel-Dump (Dump.bin) die Instruktionen, die einen SDK-Member lesen/schreiben,
und baut daraus Patches (NOP / "nur erhoehen"-Cave) im ReaperPy-Format.

Ablauf
  1. Byte-Suche nach dem 32-Bit-Displacement jedes gesuchten Offsets (schnell, ohne den ganzen Dump
     zu disassemblieren)
  2. je Treffer die Funktion bestimmen (Heuristik: 16-Byte-Grenze hinter CC/C3) und linear
     disassemblieren; nur Instruktionen mit passendem [reg+offset] zaehlen
  3. Ranking: schreibt die Instruktion? stehen in derselben Funktion weitere Member derselben Klasse
     (-> es ist wirklich Code dieser Klasse)? steht ein SUB davor (Schaden)? ist der Offset ueberall
     im Spiel (mehrdeutig)?

Disassembler: Capstone (pip install capstone) - Ausweichloesung `objdump`, falls Capstone fehlt.
Offsets im Dump sind Dateipositionen; RVA = Position + dump_rva.  Patches enthalten RVAs
(= Offset relativ zur Modul-Basis, wie in .reapproj ueblich).
"""
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field

import aob as AOB

_BRANCH = re.compile(r"^(j\w+|call|loop\w*|ret\w*|syscall|int3?)$")
_WRITE_PREFIX = ("mov", "vmov", "add", "sub", "adc", "sbb", "and", "or", "xor", "inc", "dec", "neg", "not", "shl",
                 "shr", "sar", "rol", "ror", "bts", "btr", "btc", "xchg", "xadd", "cmpxchg", "set", "pop", "stos")
_WRITE_EXCL = ("movsx", "movzx", "movsxd", "movmsk", "movsb", "movsw", "movsq", "movsl")   # Reg-Ziel / String-Ops


@dataclass
class Mem:
    base: str = None
    index: str = None
    scale: int = 1
    disp: int = 0


@dataclass
class Insn:
    addr: int
    size: int
    raw: bytes
    mnem: str
    ops: str
    mem: Mem = None
    reads: bool = False
    writes: bool = False
    wild: list = field(default_factory=list)      # [(offset_in_insn, laenge)] - Adressen/Displacements

    @property
    def branch(self):
        return bool(_BRANCH.match(self.mnem))

    @property
    def text(self):
        return f"{self.mnem} {self.ops}".strip()


def split_ops(ops):
    """'dword ptr [rbx + 0x8], xmm0' -> ['dword ptr [rbx + 0x8]', 'xmm0'] (Komma in [] ignorieren)."""
    out, depth, cur = [], 0, ""
    for ch in ops:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


# ==================================================================
# Backend 1: Capstone
# ==================================================================
class CapstoneDisasm:
    name = "capstone"

    def __init__(self):
        import capstone as cs
        self.cs = cs
        self.md = cs.Cs(cs.CS_ARCH_X86, cs.CS_MODE_64)
        self.md.detail = True

    def sweep(self, buf, off, length, addr):
        return [self._conv(i) for i in self.md.disasm(bytes(buf[off:off + length]), addr)]

    def _conv(self, i):
        cs = self.cs
        mem, reads, writes = None, False, False
        for op in i.operands:
            if op.type == cs.x86.X86_OP_MEM:
                def reg(r):
                    return i.reg_name(r) if r else None
                mem = Mem(reg(op.mem.base), reg(op.mem.index), op.mem.scale, op.mem.disp)
                if op.access & cs.CS_AC_READ:
                    reads = True
                if op.access & cs.CS_AC_WRITE:
                    writes = True
        wild = []
        try:
            is_jump = i.group(cs.CS_GRP_JUMP) or i.group(cs.CS_GRP_CALL)
            if i.disp_size == 4 and mem and mem.base == "rip":
                wild.append((i.disp_offset, 4))
            elif i.imm_size == 4 and is_jump:
                wild.append((i.imm_offset, 4))
            elif i.disp_size == 4 and not is_jump:
                wild.append((i.disp_offset, 4))
        except Exception:
            pass
        return Insn(i.address, i.size, bytes(i.bytes), i.mnemonic, i.op_str, mem, reads, writes, wild)


# ==================================================================
# Backend 2: objdump (Linux/Binutils) - Ausweichloesung und Test
# ==================================================================
_OBJ_LINE = re.compile(r"^\s*([0-9a-f]+):\t((?:[0-9a-f]{2} ?)+)\s*(?:\t(.*))?$")
_MEMRE = re.compile(r"\[([^\]]+)\]")


def _parse_mem(inner):
    m = Mem()
    for sign, tok in re.findall(r"([+-]?)\s*([A-Za-z0-9_*]+)", inner):
        neg = sign == "-"
        if re.fullmatch(r"0x[0-9a-fA-F]+|\d+", tok):
            v = int(tok, 0)
            m.disp += -v if neg else v
        elif "*" in tok:
            r, s = tok.split("*")
            m.index, m.scale = r.lower(), int(s)
        elif m.base is None:
            m.base = tok.lower()
        else:
            m.index = tok.lower()
    return m


class ObjdumpDisasm:
    name = "objdump"

    def __init__(self):
        if not shutil.which("objdump"):
            raise RuntimeError("objdump nicht gefunden")

    def sweep(self, buf, off, length, addr):
        data = bytes(buf[off:off + length])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.bin")
            with open(p, "wb") as f:
                f.write(data)
            r = subprocess.run(["objdump", "-D", "-b", "binary", "-mi386:x86-64", "-M", "intel",
                                f"--adjust-vma={addr:#x}", p], capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = []
        for line in r.stdout.splitlines():
            m = _OBJ_LINE.match(line)
            if not m:
                continue
            a, hx, txt = int(m.group(1), 16), bytes.fromhex(m.group(2).replace(" ", "")), m.group(3)
            if txt is None:                                  # Fortsetzungszeile langer Befehle
                if out:
                    out[-1].raw += hx; out[-1].size += len(hx)
                continue
            if "(bad)" in txt:
                break
            txt = txt.split("#")[0].strip()
            parts = txt.split(None, 1)
            mnem, ops = parts[0].lower(), (parts[1] if len(parts) > 1 else "").lower()
            if mnem in ("rep", "repz", "repnz", "lock", "bnd", "notrack", "data16") and ops:
                p2 = ops.split(None, 1)
                mnem, ops = p2[0], (p2[1] if len(p2) > 1 else "")
            out.append(Insn(a, len(hx), hx, mnem, ops))
        for i in out:
            self._fill(i)
        return out

    @staticmethod
    def _fill(i):
        mm = _MEMRE.search(i.ops)
        parts = split_ops(i.ops)
        if mm:
            i.mem = _parse_mem(mm.group(1))
            dest_mem = bool(parts) and "[" in parts[0]
            m = i.mnem
            writes = dest_mem and m.startswith(_WRITE_PREFIX) and not m.startswith(_WRITE_EXCL) \
                and not m.startswith(("cmp", "test", "bt "))
            if m.startswith(("sub", "add", "mul", "div")) and m[-2:] in ("ss", "sd") and not dest_mem:
                writes = False
            i.writes = bool(writes)
            i.reads = (not dest_mem) or m.startswith(("add", "sub", "adc", "sbb", "and", "or", "xor", "inc",
                                                      "dec", "neg", "not", "xchg", "xadd", "cmp", "test", "shl",
                                                      "shr", "sar"))
        # Wildcards (Naeherung): rel32 bei Spruengen, disp32 bei Speicheroperanden
        raw = i.raw
        if i.branch and len(raw) >= 5 and raw[0] in (0xE8, 0xE9):
            i.wild = [(1, 4)]
        elif i.branch and len(raw) >= 6 and raw[0] == 0x0F and 0x80 <= raw[1] <= 0x8F:
            i.wild = [(2, 4)]
        elif i.mem and (i.mem.disp > 0x7F or i.mem.disp < -0x80 or i.mem.base == "rip"):
            pos = raw.find(struct.pack("<i", i.mem.disp))
            if pos >= 0:
                i.wild = [(pos, 4)]


def get_disasm(prefer=None):
    errs = []
    for cls in ((ObjdumpDisasm, CapstoneDisasm) if prefer == "objdump" else (CapstoneDisasm, ObjdumpDisasm)):
        try:
            return cls()
        except Exception as e:
            errs.append(f"{cls.name}: {e}")
    raise RuntimeError("Kein Disassembler: pip install capstone  (" + "; ".join(errs) + ")")


# ==================================================================
# Scan
# ==================================================================
def byte_hits(dump, offsets, min_disp=0x80, lo=0, hi=None):
    """{offset: [dateipositionen des 32-Bit-Displacements]} - nur im Bereich [lo, hi)"""
    res = {}
    hi = len(dump) if hi is None else hi
    for o in offsets:
        if o < min_disp or o > 0x7FFFFFFF:
            continue
        pat, pos, lst = struct.pack("<I", o), lo, []
        while True:
            pos = dump.find(pat, pos, hi)
            if pos < 0:
                break
            lst.append(pos); pos += 1
        res[o] = lst
    return res


def _boundary(dump, q):
    if q <= 0 or q >= len(dump):
        return False
    prev = dump[q - 1]
    if dump[q] == 0xCC:
        return False
    if prev in (0xCC, 0xC3):
        return True
    if prev == 0x90:                                    # NOP-Auffuellung hinter CC/C3
        k = q - 1
        while k > q - 16 and dump[k] == 0x90:
            k -= 1
        return dump[k] in (0xCC, 0xC3)
    return False


def function_starts(dump, pos, max_back=0x4000, limit=4, floor=1):
    """Kandidaten fuer den Funktionsanfang vor `pos`, nahe zuerst."""
    q, lo, n = pos & ~0xF, max(floor, pos - max_back), 0
    while q >= lo and n < limit:
        if _boundary(dump, q):
            yield q
            n += 1
        q -= 16


def sweep_function(dis, dump, f, base, max_len=0x3000, hi=None):
    if hi is not None:
        max_len = max(0, min(max_len, hi - f))
    ins = dis.sweep(dump, f, max_len, base + f)
    out = []
    for k, i in enumerate(ins):
        out.append(i)
        end = i.addr - base + i.size
        if i.mnem.startswith("ret") and end < len(dump) and dump[end] == 0xCC:
            break
        if i.mnem == "jmp" and not i.mem and end < len(dump) and dump[end] == 0xCC and (end % 16 == 0 or dump[end:end + 1] == b"\xcc"):
            break
    return out


def write_kind(i):
    m = i.mnem
    if m.startswith(("mov", "vmov")):
        return "store"
    if m in ("sub", "dec", "neg", "sbb"):
        return "dec"
    if m in ("add", "inc", "adc"):
        return "inc"
    if m in ("xchg", "xadd", "cmpxchg"):
        return "atomic"
    return "rmw"


@dataclass
class Hit:
    addr: int                    # virtuelle Adresse (base_va + Position)
    pos: int                     # Position im Dump
    rva: int
    func_pos: int
    ins: Insn
    offset: int
    kind: str
    writes: bool
    reads: bool
    coaccess: int = 0
    dec_hint: bool = False
    ambiguity: int = 0           # in wie vielen Funktionen wird dieser Offset geschrieben
    score: float = 0.0
    tags: list = field(default_factory=list)       # z.B. ["UHealthComponent.Health"]
    stolen: list = field(default_factory=list)     # Folge-Instruktionen im 8-Byte-Hook-Bereich


def scan(dump, targets, dis, class_offsets=None, base_va=0, dump_rva=0, include_reads=False,
         min_disp=0x80, progress=None, max_positions=200000, code_range=None):
    """targets: {offset: [tag, ...]} ; class_offsets: Offsets weiterer Member derselben Klassen
    (fuer die Ko-Zugriffs-Wertung).  -> [Hit] (absteigend nach Score)."""
    class_offsets = set(class_offsets or ()) | set(targets)
    want = {o for o in class_offsets if o >= min_disp}
    lo, hi = code_range if code_range else (0, len(dump))
    hits_by_off = byte_hits(dump, want, min_disp, lo, hi)
    total = sum(len(v) for v in hits_by_off.values())
    if total > max_positions:
        raise RuntimeError(f"{total} Byte-Treffer - Offsets zu unspezifisch (Dump zu gross oder Liste zu lang)")
    done = 0
    sweeps = {}                                           # func_pos -> [Insn]
    pos_func = {}
    for o, plist in hits_by_off.items():
        for p in plist:
            done += 1
            if progress and done % 2000 == 0:
                progress(done, total)
            if p in pos_func:
                continue
            for f in function_starts(dump, p, floor=max(1, lo + 1)):
                if f not in sweeps:
                    sweeps[f] = sweep_function(dis, dump, f, base_va, hi=hi)
                if any(i.addr - base_va <= p < i.addr - base_va + i.size and i.mem and i.mem.disp in want
                       for i in sweeps[f]):
                    pos_func[p] = f
                    break
    touch, hits, seen = {}, [], set()
    for f, insns in sweeps.items():
        offs = set()
        for i in insns:
            if i.mem and i.mem.disp in want and i.mem.base not in (None, "rip", "rsp") and i.mem.disp > 0:
                offs.add(i.mem.disp)
        touch[f] = offs
    for f, insns in sweeps.items():
        for k, i in enumerate(insns):
            if not i.mem or i.mem.disp not in targets or i.mem.base in (None, "rip", "rsp") or i.mem.disp <= 0:
                continue
            if not (i.writes or (include_reads and i.reads)):
                continue
            pos = i.addr - base_va
            key = (pos, i.mem.disp)
            if key in seen:
                continue
            seen.add(key)
            h = Hit(i.addr, pos, pos + dump_rva, f, i, i.mem.disp, write_kind(i) if i.writes else "read",
                    i.writes, i.reads, tags=list(targets[i.mem.disp]))
            h.coaccess = len(touch.get(f, set()) - {i.mem.disp})
            if i.writes and i.mnem.startswith(("mov", "vmov")):
                for prev in insns[max(0, k - 12):k]:
                    if prev.mnem.startswith("sub") or prev.mnem in ("dec", "neg"):
                        h.dec_hint = True
                        break
            tot, n = 0, 0
            for j in insns[k:k + 6]:
                tot += j.size
                n += 1
                if tot >= 8:
                    break
            h.stolen = list(insns[k + 1:k + n])
            hits.append(h)
    amb = {}
    for h in hits:
        if h.writes:
            amb.setdefault(h.offset, set()).add(h.func_pos)
    for h in hits:
        h.ambiguity = len(amb.get(h.offset, ()))
        h.score = score_hit(h)
    hits.sort(key=lambda h: -h.score)
    return hits


def score_hit(h):
    s = 0.0
    if h.writes:
        s += 3
    s += min(h.coaccess, 8) * 1.5
    if h.dec_hint:
        s += 4
    if h.kind == "dec":
        s += 3
    if h.ambiguity > 12:
        s -= min(8.0, math.log2(h.ambiguity / 12.0) * 3)
    if h.ins.size < 5:
        s -= 1
    return round(s, 2)


# ==================================================================
# Signatur + Patch-Bau
# ==================================================================
def make_aob(dump, dis, h, base_va=0, hook_len=8, min_len=12, max_len=96, code_range=None):
    return make_aob_at(dump, dis, h.pos, h.addr, hook_len, min_len, max_len, code_range)


def make_aob_at(dump, dis, pos, addr, hook_len=8, min_len=12, max_len=96, code_range=None):
    """Muster im ReaperPy-Stil: hook_len Wildcards, dann Folge-Bytes (Displacements/Spruenge als ??),
    muss im Dump (Code-Bereich) eindeutig sein.  -> (text|None, treffer)"""
    lo, hi = code_range if code_range else (0, len(dump))
    ins = dis.sweep(dump, pos, hook_len + max_len + 16, addr)
    flags = bytearray()
    raw = bytearray()
    for i in ins:
        f = bytearray(i.size)
        for o, n in i.wild:
            for k in range(o, min(o + n, i.size)):
                f[k] = 1
        raw += i.raw; flags += f
    if len(raw) <= hook_len + min_len:
        return None, 0
    tail, tflags = bytes(raw[hook_len:]), bytes(flags[hook_len:])
    last = 0
    for n in range(min_len, len(tail) + 1, 4):
        body = tail[:n]
        mask = bytes(0 if tflags[k] else 1 for k in range(n))
        if sum(mask) < 6:
            continue
        pat = b"\x00" * hook_len + body
        m = b"\x00" * hook_len + mask
        rx = AOB._regex(pat, m)
        found = _all_matches(rx, dump, limit=3, lo=lo, hi=hi)
        last = len(found)
        if len(found) == 1 and found[0] == pos:
            return AOB.format_pattern(pat, m), 1
        if len(found) == 0:
            return None, 0
    return None, last


def _all_matches(rx, dump, limit=3, lo=0, hi=None):
    res, pos = [], lo
    hi = len(dump) if hi is None else hi
    while len(res) < limit:
        m = rx.search(dump, pos, hi)
        if not m:
            break
        res.append(m.start()); pos = m.start() + 1
    return res


def _spaced(b):
    return " ".join(f"{x:02X}" for x in b)


def _src_dest(ins):
    p = split_ops(ins.ops)
    return (p[0], p[1]) if len(p) == 2 else (None, None)


def can_cave(h):
    """Kann fuer den Treffer eine 'nur erhoehen'-Cave gebaut werden? -> (ok, grund)"""
    i = h.ins
    if i.size < 5:
        return False, "Instruktion kürzer als 5 Byte"
    dest, src = _src_dest(i)
    if not dest or "[" not in dest:
        return False, "kein einfacher Store"
    is_xmm = src.startswith("xmm") and i.mnem in ("movss", "movsd")
    is_gpr = i.mnem == "mov" and re.fullmatch(r"(e[a-ds][xip]|r(?:[a-ds][xip]|\d+[dwb]?)|[a-ds][xil]|e?[sd]i|r[sd]i)", src or "")
    if not (is_xmm or is_gpr):
        return False, "Quelle ist weder xmm noch Register"
    if i.mem.base == "rip":
        return False, "RIP-relativ"
    total = i.size + sum(j.size for j in h.stolen)
    if total < 8:
        return False, "Folge-Instruktionen fehlen für den 8-Byte-Hook"
    for j in h.stolen:
        if j.branch or (j.mem and j.mem.base == "rip"):
            return False, f"Folge-Instruktion '{j.text}' ist nicht verschiebbar"
    return True, ""


def nop_patch(dump, h, aob_text=None, name=None, author=""):
    i = h.ins
    name = name or f"{'+'.join(h.tags) or hex(h.offset)} - Schreiben aus ({i.text})"
    v = {"label": "OriginSource", "offset": hex(h.rva), "defaultValue": _spaced(dump[h.pos:h.pos + i.size]),
         "newValue": _spaced(b"\x90" * i.size)}
    if aob_text:
        v["aob"], v["aobOffset"] = aob_text, 0
    return {"name": name, "author": author, "Variables": [v]}


def keep_cave_patch(dump, h, aob_text=None, name=None, author=""):
    """'Wert kann nicht sinken': Store nur ausfuehren, wenn der neue Wert >= alter Wert."""
    ok, why = can_cave(h)
    if not ok:
        raise ValueError(why)
    i = h.ins
    dest, src = _src_dest(i)
    if i.mnem in ("movss", "movsd"):
        cmp_ = "comiss" if i.mnem == "movss" else "comisd"
        lines = [f"{cmp_} {src}, {dest}", "jb NoDecreaseSkip", f"{i.mnem} {dest}, {src}"]
    else:
        lines = [f"cmp {dest}, {src}", "jg NoDecreaseSkip", f"mov {dest}, {src}"]
    lines.append("NoDecreaseSkip:")
    lines += [j.text for j in h.stolen]
    lines.append("jmp OriginReturn")
    total = i.size + sum(j.size for j in h.stolen)
    name = name or f"{'+'.join(h.tags) or hex(h.offset)} - kann nicht sinken ({i.text})"
    first8 = dump[h.pos:h.pos + 8]
    src_v = {"label": "OriginSource", "offset": hex(h.rva), "defaultValue": _spaced(first8),
             "newValue": "jmp OriginTarget"}
    if aob_text:
        src_v["aob"], src_v["aobOffset"] = aob_text, 0
    return {"name": name, "author": author, "Variables": [
        src_v,
        {"label": "OriginReturn", "offset": hex(total), "defaultValue": "", "newValue": ""},
        {"label": "OriginTarget", "offset": "0x0", "defaultValue": "\n".join(lines), "newValue": ""}]}


_SIZE_WORDS = {"byte": 1, "word": 2, "dword": 4, "qword": 8}
_PTR_PREFIX = re.compile(r"^\s*(byte|word|dword|qword)\s+ptr\s+", re.I)
_FORCE_MNEM = ("mov", "add", "sub", "adc", "sbb", "and", "or", "xor", "inc", "dec", "neg", "not", "movss", "movsd")


def store_operand(h):
    """Speicher-Ziel der schreibenden Instruktion als (Text ohne Groessen-Praefix, Groesse in Byte) oder (None, 0)."""
    i = h.ins
    ops = split_ops(i.ops)
    if not ops or "[" not in ops[0] or ":" in ops[0].split("[")[0]:      # kein Segment-/String-Ziel
        return None, 0
    m = _PTR_PREFIX.match(ops[0])
    if not m:
        return None, 0
    return ops[0][m.end():].strip(), _SIZE_WORDS[m.group(1).lower()]


def can_force(h):
    """Kann hinter dem Schreibzugriff ein fester Wert in dasselbe Ziel geschrieben werden? -> (ok, grund, groesse)"""
    i = h.ins
    if not i.writes:
        return False, "die Instruktion schreibt nicht", 0
    if i.mnem not in _FORCE_MNEM:
        return False, f"'{i.mnem}' wird nicht unterstützt", 0
    if i.size < 5:
        return False, "Instruktion kürzer als 5 Byte", 0
    if i.mem is None or i.mem.base in (None, "rip"):
        return False, "RIP-relativ oder ohne Basisregister", 0
    dest, size = store_operand(h)
    if dest is None:
        return False, "Ziel ist kein einfacher Speicher-Operand mit Größenangabe", 0
    if i.mnem.startswith("mov") and i.mnem in ("movss", "movsd") and size not in (4, 8):
        return False, "Ziel hat keine 4/8 Byte", 0
    total = i.size + sum(j.size for j in h.stolen)
    if total < 8:
        return False, "Folge-Instruktionen fehlen für den 8-Byte-Hook", 0
    for j in h.stolen:
        if j.branch or (j.mem and j.mem.base == "rip"):
            return False, f"Folge-Instruktion '{j.text}' ist nicht verschiebbar", 0
    return True, "", size


def force_cave_patch(dump, h, bits, aob_text=None, name=None, author=""):
    """'Wert festschreiben': die Original-Instruktion laeuft, danach wird `bits` (Rohbits, Groesse = Store-Groesse) in
    dasselbe Ziel geschrieben.  Fuer Zahlen und Schalter; fuer 8-Byte-Ziele muss der Wert als vorzeichenerweiterter
    32-Bit-Wert passen."""
    ok, why, size = can_force(h)
    if not ok:
        raise ValueError(why)
    if not 0 <= bits < (1 << (8 * size)):
        raise ValueError(f"Wert passt nicht in {size} Byte")
    imm = bits
    if size == 8:
        if bits >= 1 << 63:
            bits -= 1 << 64
        if not -(1 << 31) <= bits < (1 << 31):
            raise ValueError("Wert passt nicht in einen 32-Bit-Direktwert (8-Byte-Ziel)")
        imm = bits
    i = h.ins
    dest, _ = store_operand(h)
    word = {1: "byte", 2: "word", 4: "dword", 8: "qword"}[size]
    lines = [i.text, f"mov {word} ptr {dest}, {imm:#x}" if imm >= 0 else f"mov {word} ptr {dest}, -{-imm:#x}"]
    lines += [j.text for j in h.stolen]
    lines.append("jmp OriginReturn")
    total = i.size + sum(j.size for j in h.stolen)
    name = name or f"{'+'.join(h.tags) or hex(h.offset)} - Wert festgeschrieben ({i.text})"
    src_v = {"label": "OriginSource", "offset": hex(h.rva), "defaultValue": _spaced(dump[h.pos:h.pos + 8]),
             "newValue": "jmp OriginTarget"}
    if aob_text:
        src_v["aob"], src_v["aobOffset"] = aob_text, 0
    return {"name": name, "author": author, "Variables": [
        src_v,
        {"label": "OriginReturn", "offset": hex(total), "defaultValue": "", "newValue": ""},
        {"label": "OriginTarget", "offset": "0x0", "defaultValue": "\n".join(lines), "newValue": ""}]}


# ==================================================================
# Funktionen: sofort zurueckkehren / Implementierung hinter dem Exec-Thunk finden
# ==================================================================
RET_MODES = {
    "ret":    (b"\xC3", "Funktion sofort beenden (void)"),
    "false":  (b"\x31\xC0\xC3", "gibt 0 / false zurück"),
    "true":   (b"\xB0\x01\xC3", "gibt true zurück"),
    "one":    (b"\xB8\x01\x00\x00\x00\xC3", "gibt 1 zurück"),
    "float0": (b"\x0F\x57\xC0\xC3", "gibt 0.0 (float/double) zurück"),
}


def func_ret_patch(dump, pos, rva, mode, name, aob_text=None, author=""):
    """Patch, der eine Funktion am Anfang sofort zurueckkehren laesst (Werte werden nie veraendert)."""
    new, desc = RET_MODES[mode]
    v = {"label": "OriginSource", "offset": hex(rva), "defaultValue": _spaced(dump[pos:pos + len(new)]),
         "newValue": _spaced(new)}
    if aob_text:
        v["aob"], v["aobOffset"] = aob_text, 0
    return {"name": f"{name} - {desc}", "author": author, "Variables": [v]}


def branch_targets(insns):
    """Direkte CALL/JMP-rel32-Ziele einer Instruktionsliste -> [(art, ziel, adresse)]"""
    out = []
    for i in insns:
        if len(i.raw) == 5 and i.raw[0] in (0xE8, 0xE9):
            rel = struct.unpack("<i", i.raw[1:5])[0]
            out.append(("call" if i.raw[0] == 0xE8 else "jmp", i.addr + 5 + rel, i.addr))
        elif len(i.raw) == 2 and i.raw[0] == 0xEB:                   # kurzer JMP (nahes Tail-Ziel)
            out.append(("jmp", i.addr + 2 + struct.unpack("<b", i.raw[1:2])[0], i.addr))
    return out


def _thunk_insns(dis, dump, pos, base_va, hi, max_len=0x400):
    ins = dis.sweep(dump, pos, min(max_len, max(0, hi - pos)), base_va + pos)
    out = []
    for i in ins:
        out.append(i)
        if i.mnem.startswith("ret"):
            break
        end = i.addr - base_va + i.size
        if i.raw[:1] in (b"\xE9", b"\xEB") and end < len(dump) and dump[end] == 0xCC:
            break                                                    # Tail-Jump, danach nur Auffuellung
    return out


def common_callees(dump, dis, thunk_vas, base_va, lo, hi, sample=300, min_count=5, min_frac=0.05):
    """Aufrufziele, die in vielen Exec-Thunks vorkommen (FFrame-Helfer, memcpy ...) -> set(ziel)"""
    from collections import Counter
    vas = sorted(set(thunk_vas))
    step = max(1, len(vas) // sample)
    vas = vas[::step][:sample]
    cnt = Counter()
    for va in vas:
        pos = va - base_va
        if not (lo <= pos < hi):
            continue
        for kind, tgt, _a in branch_targets(_thunk_insns(dis, dump, pos, base_va, hi)):
            if kind == "call":
                cnt[tgt] += 1
    need = max(min_count, int(min_frac * max(1, len(vas))))
    return {t for t, c in cnt.items() if c >= need}


def resolve_impl(dump, dis, native_va, base_va, lo, hi, common=frozenset()):
    """Die C++-Implementierung hinter dem Exec-Thunk: Aufrufziele des Thunks ohne die gemeinsamen
    Helfer.  -> [VA] (der letzte verbleibende Aufruf zuerst - das ist meist `this->Funktion(...)`)"""
    pos = native_va - base_va
    if not (lo <= pos < hi):
        return []
    ins = _thunk_insns(dis, dump, pos, base_va, hi)
    tg = branch_targets(ins)
    cands = [t for k, t, _a in tg if t not in common and base_va + lo <= t < base_va + hi]
    if not cands and tg and tg[-1][0] == "jmp":            # reiner Tail-Jump
        cands = [tg[-1][1]]
    seen, out = set(), []
    for t in reversed(cands):
        if t not in seen and t != native_va:
            seen.add(t); out.append(t)
    return out
