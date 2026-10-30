"""cave_trainer.py - Item-Trainer als ReaperPy-Projekt (STATISCHE Cave, laeuft ohne dieses Tool im Spiel).

Prinzip (ProcessEvent-Haken im vtable, dauerhaft und ohne Briefkasten-Schnittstelle):
  * Der ProcessEvent-Zeiger im vtable des PlayerControllers / der Spielfigur liegt im Spiel-Image (base+RVA).  Ein
    Trainer schreibt dort 8 Byte hin: den Einsprung der Cave.  Es wird kein Spiel-Code verschoben.
  * Die Cave liegt in Padding-Luecken des Images (Code), die Schalter (1 Byte je Trainer-Eintrag) in beschreibbarem
    Image-Leerraum.  Die Cave selbst schreibt NIE in ihren eigenen (r-x) Bereich - nur in die Schalter.
  * Beim naechsten ProcessEvent prueft die Cave die Schalter.  Ist einer 1, wird er ATOMAR auf 0 gesetzt (xchg - bei
    zwei Spiel-Threads gewinnt genau einer), dann ruft die Cave die Item-Funktion des Spiels
    (impl(rdi=0, rsi=FName, edx=Menge, ecx=1, r8d=0)) einmal je Zeile des Eintrags auf und springt weiter zum
    echten ProcessEvent.  Alle Register des Originalaufrufs bleiben erhalten.

Ausgabe: ein Ordner = ein ReaperPy-Projekt.
    00_BASIS - Item-Cave.reapproj        Cave schreiben + vtable-Zeiger umbiegen (ZUERST aktivieren)
    01_<Eintrag>.reapproj ...            je Trainer-Eintrag ein Schalter-Byte (00 -> 01), Cave setzt es zurueck
    _trainer_spec.json                   Beschreibung (zum Erweitern des Projekts und fuer FNAMES PRUEFEN)
    LIESMICH_TRAINER.txt
Die Dateien sind ganz normale Simple-Patches (nur Hex-Bytes): ReaperPy braucht dafuer weder Keystone noch eine
Verbindung ausser dem Schreiben, und export_goldhen.py kann sie unveraendert in eine GoldHEN/etaHEN-JSON umwandeln.

Annahmen (am echten Spiel NICHT getestet - die Cave selbst schon, auf einem echten x86-64-Prozessor):
  * Image-Basis und alle Adressen gelten nur fuer DIESE Spielversion.
  * FName-Werte (Item-Namen) muessen bei jedem Spielstart gleich sein -> nach dem Export das Spiel neu starten und
    FNAMES PRUEFEN druecken.  Sind sie nicht stabil, funktioniert der Trainer nur bis zum naechsten Neustart.
  * Der Schalter-Bereich ist ein Null-Stueck am Ende der letzten beschreibbaren Image-Region.  Das ist eine
    Heuristik (die Konsole kann nicht sehen, ob das Spiel dort schreibt).
"""
import json
import os
import re
import struct
import time

SPEC_FILE = "_trainer_spec.json"
README_FILE = "LIESMICH_TRAINER.txt"
BASE_FILE = "00_BASIS - Item-Cave.reapproj"
MAX_OPTIONS = 64                    # 8 Schalter-Qwords
MAX_ROWS = 400                      # Zeilen (Items) insgesamt: haelt die Cave klein
FLAG_ALIGN = 8
FLAG_MIN_RUN = 0x100                # so viel Null-Bytes muessen am Region-Ende frei sein
FILL = (0x00, 0xCC)
INNER_MIN_RUN = 0x40                # Ausweichplatz: so lang muss ein CC-Stueck (Padding zwischen Funktionen) mindestens sein
INNER_TRIGGER = 0x1000              # nur wenn am Region-Ende weniger als das frei ist, wird mitten im Code gesucht
INNER_SCAN_MAX = 96 << 20           # hoechstens so viel Code wird dafuer gelesen
INNER_BLOCK = 1 << 20
INNER_KEEP = 256                    # die groessten Luecken genuegen
LIMIT = 0x7F000000                  # rel32-Reichweite mit Sicherheitsabstand
NAME_MAX = 60
ANCHOR_LEN = 16                     # so viele Byte je Funktionsanfang fuer die Versionspruefung
PACK_SIZE = 14                      # so viele Items hoechstens in einem Paket-Eintrag
PAD_WINDOW = 0x10000                # so viel vom Region-Ende wird nach freien Null-/CC-Stuecken durchsucht (nicht nur ganz am Ende)
PAD_MIN_RUN = 0x40
_PAD_RUN = re.compile(b"\\x00{%d,}|\\xcc{%d,}" % (PAD_MIN_RUN, PAD_MIN_RUN))
REMNANT_SCAN = 0x20000              # so viel vom Region-Ende wird nach Resten einer frueheren ReaperPy-Cave durchsucht
_FILL_RUN = re.compile(b"[\x00\xcc]{32,}")
# Anfang einer ReaperPy-Cave (build_cave): xor eax,eax / (or rax,[rip+d32])+ / jnz +5 / jmp orig_pe
_CAVE_HEAD = re.compile(rb"\x31\xc0(?:\x48\x0b\x05....)+\x0f\x85\x05\x00\x00\x00\xe9....", re.DOTALL)


class TrainerError(Exception):
    pass


# ======================================================================
# Datenmodell
# ======================================================================
class Row:
    """Eine Item-Zeile: Alias, 8-Byte-FName, Menge."""
    __slots__ = ("alias", "fname", "amount")

    def __init__(self, alias, fname, amount):
        fname = bytes(fname)
        if len(fname) != 8:
            raise TrainerError(f"{alias}: FName hat nicht 8 Byte")
        if not 1 <= int(amount) <= 0xFFFFFFFF:
            raise TrainerError(f"{alias}: Menge {amount} ausserhalb 1..4294967295")
        self.alias, self.fname, self.amount = alias, fname, int(amount)

    def to_json(self):
        return {"alias": self.alias, "fname": self.fname.hex(), "amount": self.amount}

    @classmethod
    def from_json(cls, d):
        if "call" in d:                                     # allgemeiner Funktionsaufruf (ue_cavegen)
            import ue_cavegen
            return ue_cavegen.CallRow.from_json(d)
        return cls(d["alias"], bytes.fromhex(d["fname"]), d["amount"])

    call_impl_rva = None                                    # nur CallRow: eigene Funktion (RVA)

    def emit(self, e, impl, base):
        """Standard-Form (Item geben): impl(rdi=0, rsi=FName, edx=Menge, ecx=1, r8d=0)"""
        e.raw("48BE" + self.fname.hex())                    # movabs rsi,FName
        e.raw("BA" + struct.pack("<I", self.amount).hex())  # mov edx,Menge
        e.raw("B901000000")                                 # mov ecx,1
        e.raw("4531C0")                                     # xor r8d,r8d
        e.raw("31FF")                                       # xor edi,edi
        e.raw("E8")                                         # call impl
        e.rel32(impl)


class Option:
    """Ein Trainer-Eintrag (= eine Datei im Projekt): Name + 1..n Zeilen."""

    def __init__(self, name, rows):
        self.name = clean_name(name)
        self.rows = list(rows)
        if not self.rows:
            raise TrainerError(f"Eintrag '{name}' hat keine Zeilen")

    def to_json(self):
        return {"name": self.name, "rows": [r.to_json() for r in self.rows]}

    @classmethod
    def from_json(cls, d):
        return cls(d["name"], [Row.from_json(r) for r in d["rows"]])


def split_package(name, rows, size=PACK_SIZE):
    """Paket in 14er-Stuecke teilen: bis 14 Zeilen -> ein Eintrag 'name', sonst 'name 1', 'name 2', ... -> [Option]"""
    rows = list(rows)
    if len(rows) <= size:
        return [Option(name, rows)]
    return [Option(f"{name} {k + 1}", rows[i:i + size]) for k, i in enumerate(range(0, len(rows), size))]


def clean_name(name):
    s = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", str(name)).strip()
    s = re.sub(r"\s+", " ", s)
    return (s or "Eintrag")[:NAME_MAX]


# ======================================================================
# Maschinencode der Cave (von Hand kodiert, in tests/test_cave_trainer.py mit GNU as + objdump gegengeprueft
# und auf dem echten Prozessor ausgefuehrt)
# ======================================================================
class _Emit:
    """Minimaler Emitter: Bytes + rel32-Fixups gegen absolute Ziele oder Labels."""

    def __init__(self, base):
        self.base = base
        self.buf = bytearray()
        self.labels = {}
        self.fix = []                   # (Position des disp32, Ziel: int absolut | str Label)
        self.pools = []                 # [(Label, Bytes)] Konstanten hinter dem Code (read-only genuegt)
        self.n = 0                      # Zaehler fuer eindeutige Label

    def uniq(self, prefix):
        self.n += 1
        return f"{prefix}{self.n}"

    def pool(self, data):
        name = self.uniq("pool")
        self.pools.append((name, bytes(data)))
        return name

    @property
    def here(self):
        return self.base + len(self.buf)

    def raw(self, hexstr):
        self.buf += bytes.fromhex(hexstr)

    def rel32(self, target):
        self.fix.append((len(self.buf), target))
        self.buf += b"\0\0\0\0"

    def label(self, name):
        self.labels[name] = len(self.buf)

    def finish(self):
        for name, data in self.pools:
            while len(self.buf) % 8:
                self.buf.append(0xCC)
            self.labels[name] = len(self.buf)
            self.buf += data
        for pos, tgt in self.fix:
            dest = self.base + self.labels[tgt] if isinstance(tgt, str) else tgt
            rel = dest - (self.base + pos + 4)
            if not -2**31 <= rel < 2**31:
                raise TrainerError(f"Ziel {dest:#x} ist zu weit von der Cave {self.base:#x} entfernt (rel32)")
            self.buf[pos:pos + 4] = struct.pack("<i", rel)
        return bytes(self.buf)


def n_flag_qwords(n_options):
    return (n_options + 7) // 8


def flag_bytes_needed(n_options):
    return n_flag_qwords(n_options) * 8


def build_cave(cave_addr, flag_addr, orig_pe, impl, options, base=0):
    """-> Cave-Bytes.  Einsprung = cave_addr (ProcessEvent-Ersatz).

        xor eax,eax / or rax,[Schalter+8k] ...   ; irgendein Schalter gesetzt?
        jnz slow
        jmp orig_pe                              ; Normalfall: kaum Kosten
      slow:
        push rdi / rsi / rdx                     ; Originalargumente retten (rsp: 8 + 24 = 0 mod 16 -> am call ausgerichtet)
        je Eintrag:  xor eax,eax ; xchg [Schalter+i],al ; test al,al ; jz naechster
                     je Zeile:  movabs rsi,FName ; mov edx,Menge ; mov ecx,1 ; xor r8d,r8d ; xor edi,edi ; call impl
        pop rdx / rsi / rdi
        jmp orig_pe
    """
    if not options:
        raise TrainerError("Keine Eintraege")
    if impl is None and any(getattr(r, "call_impl_rva", None) is None for o in options for r in o.rows):
        raise TrainerError("Keine Item-Funktion angegeben")
    if len(options) > MAX_OPTIONS:
        raise TrainerError(f"Hoechstens {MAX_OPTIONS} Eintraege (hier {len(options)})")
    if flag_addr % FLAG_ALIGN:
        raise TrainerError("Schalter-Bereich nicht 8-Byte-ausgerichtet")
    e = _Emit(cave_addr)
    e.raw("31C0")                                           # xor eax,eax
    for k in range(n_flag_qwords(len(options))):
        e.raw("480B05")                                     # or rax,[rip+disp32]
        e.rel32(flag_addr + 8 * k)
    e.raw("0F85")                                           # jnz slow
    e.rel32("slow")
    e.raw("E9")                                             # jmp orig_pe
    e.rel32(orig_pe)
    e.label("slow")
    e.raw("57" "56" "52")                                   # push rdi, rsi, rdx
    for i, opt in enumerate(options):
        e.raw("31C0")                                       # xor eax,eax
        e.raw("8605")                                       # xchg [rip+disp32],al   (implizit atomar)
        e.rel32(flag_addr + i)
        e.raw("84C0")                                       # test al,al
        e.raw("0F84")                                       # jz next_i
        e.rel32(f"next{i}")
        for row in opt.rows:
            row.emit(e, impl, base)
        e.label(f"next{i}")
    e.raw("5A" "5E" "5F")                                   # pop rdx, rsi, rdi
    e.raw("E9")                                             # jmp orig_pe
    e.rel32(orig_pe)
    return e.finish()


def cave_size(options):
    """Laenge der Cave (unabhaengig von den Adressen: jedes rel32 ist immer 4 Byte)."""
    return len(build_cave(0, 0, 0, 0, options, 0))


# ======================================================================
# Platz im Image finden
# ======================================================================
def image_span(maps, base, max_gap=0x100000):
    """Regionen ab `base`, jeweils hoechstens `max_gap` Byte Luecke dazwischen (Segmente des Images) ->
    Liste (start, end, prot).  Nur was zum Image gehoert: Heap/Bibliotheken liegen weit weg."""
    regs = sorted((int(s), int(e), int(p)) for s, e, p in maps)
    out, cur = [], None
    for s, e, p in regs:
        if cur is None:
            if s <= base < e:
                out.append((s, e, p))
                cur = e
        elif s - cur <= max_gap and s >= cur:
            out.append((s, e, p))
            cur = e
        elif s < cur:                       # ueberlappend (sollte nicht vorkommen): mitnehmen
            out.append((s, e, p))
            cur = max(cur, e)
        else:
            break
    return out


def in_span(span, addr):
    return any(s <= addr < e for s, e, _p in span)


def _tail_run(read, end, start, cap=0x8000):
    """Laenge des Null-/CC-Stuecks am Ende [start,end) -> (laenge, fuellbyte)."""
    n = min(cap, end - start)
    data = bytes(read(end - n, n))
    if len(data) < n or not data:
        return 0, 0
    last = data[-1]
    if last not in FILL:
        return 0, 0
    cnt = len(data) - len(data.rstrip(bytes([last])))
    return cnt, last


def tail_map(read, end, n=0x4000, step=0x100):
    """Grobe Karte des Region-Endes fuer das Log: je `step` Byte ein Zeichen - '.' nur 00, 'c' nur CC, '#' sonst, '?' nicht lesbar."""
    try:
        buf = bytes(read(end - n, n))
    except Exception:  # noqa: BLE001
        return "?"
    if len(buf) != n:
        return "?"
    out = []
    for i in range(0, n, step):
        blk = buf[i:i + step]
        out.append("." if not any(blk) else "c" if blk.count(0xCC) == len(blk) else "#")
    return "".join(out)


def find_remnant(read, span, s, e):
    """Reste einer frueheren ReaperPy-Cave am Ende der Code-Region [s,e)?

    Die Cave bleibt nach dem Abschalten absichtlich stehen (Nullen koennte einen Thread im Code abstuerzen lassen)
    und liegt genau dort, wo sonst der freie Platz waere.  Ohne diese Erkennung sieht ein zweiter Export (oder eine
    Konsole, auf der der Trainer schon einmal aktiv war / ueber GoldHEN geladen wurde) 'keinen Platz' (0 Byte).
    Erkannt wird der Cave-Anfang (genau die Bytefolge von build_cave, Spruenge zeigen ins Image), mehrere
    Caves hintereinander (mehrere Projekte) werden zu einer Kette zusammengefasst.
    -> (Start, Fuellbyte) des wiederverwendbaren Stuecks [Start, e) oder None."""
    n = min(REMNANT_SCAN, e - s)
    if n < 32:
        return None
    try:
        buf = bytes(read(e - n, n))
    except Exception:  # noqa: BLE001
        return None
    if len(buf) != n:
        return None
    base = e - n
    cands = []
    for off in range((-base) % 16, n, 16):
        m = _CAVE_HEAD.match(buf, off)
        if not m:
            continue
        d1 = struct.unpack_from("<i", buf, off + 5)[0]                   # or rax,[rip+d1] -> Schalter
        d2 = struct.unpack_from("<i", buf, m.end() - 4)[0]                # jmp orig_pe
        if in_span(span, base + off + 9 + d1) and in_span(span, base + m.end() + d2):
            cands.append(off)
    start, limit = None, n
    for off in sorted(cands, reverse=True):                               # vom Ende her: lueckenlose Kette
        if _FILL_RUN.search(buf, off, limit):
            break
        start, limit = off, off
    if start is None:
        return None
    cnt, fill = _tail_run(read, base + start, s)                          # freier Platz direkt davor gehoert dazu
    if not cnt:
        fill = buf[-1] if buf[-1] in FILL else 0xCC
    return base + start - cnt, fill


class Slots:
    """Freie Stuecke: Code-Padding (r-x) und Daten-Padding (rw-), jeweils am Region-Ende, von hinten nach vorn."""

    def __init__(self, read, span, log=print):
        self.read, self.span, self.log = read, span, log
        self._code, self._data = None, None
        self.reclaimed = []             # [(start, ende, fuellbyte)]: Reste einer frueheren ReaperPy-Cave, die ueberschrieben werden duerfen
        self.last_reclaim = None        # Fuellbyte, wenn die zuletzt vergebene Cave in so einem Rest liegt, sonst None

    def _scan_code(self):
        runs = []
        for s, e, p in self.span:
            if not p & 4:
                continue
            cnt, _b = _tail_run(self.read, e, s)
            if cnt >= 0x20:
                runs.append([e - cnt, e])
                continue
            rem = find_remnant(self.read, self.span, s, e)
            if rem:
                runs.append([rem[0], e])
                self.reclaimed.append((rem[0], e, rem[1]))
                self.log(f"[trainer] Reste einer frueheren ReaperPy-Cave am Ende der Region {s:#x}-{e:#x} "
                         f"({e - rem[0]} Byte) - der Platz wird wiederverwendet")
        for r in self._scan_pad_window(runs):                       # freie Stuecke NICHT ganz am Ende (fremde Cave dahinter)
            runs.append(r)
        runs.sort(key=lambda r: -(r[1] - r[0]))
        self.log(f"[trainer] {len(runs)} Code-Padding-Luecke(n) am Region-Ende")
        if max(((r[1] - r[0]) & ~0xF for r in runs), default=0) < INNER_TRIGGER:
            inner = self._scan_inner(runs)
            if inner:
                self.log(f"[trainer] {len(inner)} Code-Luecke(n) mitten im Code (kein Padding am Region-Ende)")
                runs = sorted(runs + inner, key=lambda r: -(r[1] - r[0]))
        return runs

    def _scan_pad_window(self, known):
        """Ein anderer Cheat/Plugin kann seine Cave ans Region-Ende gelegt haben (dort liegt das Seiten-Padding hinter dem
        Code).  Der freie Rest davor ist dann kein 'Tail-Stueck' mehr.  Darum werden die letzten PAD_WINDOW Byte jeder
        ausfuehrbaren Region nach reinen Null- oder CC-Stuecken durchsucht.  Nur Lesen."""
        out = []
        busy = [(r[0], r[1]) for r in known]
        for s, e, p in self.span:
            if not p & 4:
                continue
            n = min(PAD_WINDOW, e - s)
            try:
                buf = bytes(self.read(e - n, n))
            except Exception:  # noqa: BLE001
                continue
            if len(buf) != n:
                continue
            for m in _PAD_RUN.finditer(buf):
                a, b = e - n + m.start(), e - n + m.end()
                if any(a < y and x < b for x, y in busy):
                    continue
                out.append([a, b])
        return out

    def _scan_inner(self, tail_runs):
        """Ausweichplatz: lange 0xCC-Stuecke (Padding zwischen Funktionen) mitten in ausfuehrbaren Regionen.
        Liest hoechstens INNER_SCAN_MAX Byte, blockweise; nur Lesen."""
        pat = re.compile(b"\xcc{%d,}" % INNER_MIN_RUN)
        found, scanned = [], 0
        for s, e, p in self.span:
            if not p & 4:
                continue
            region, pos = [], s
            while pos < e and scanned < INNER_SCAN_MAX:
                n = min(INNER_BLOCK, e - pos)
                try:
                    buf = bytes(self.read(pos, n))
                except Exception:  # noqa: BLE001 - nicht lesbare Seiten: diese Region nicht weiter durchsuchen
                    break
                if len(buf) != n:
                    break
                scanned += n
                for m in pat.finditer(buf):
                    a, b = pos + m.start(), pos + m.end()
                    if region and region[-1][1] == a:          # Stueck ueber die Blockgrenze hinweg
                        region[-1][1] = b
                    else:
                        region.append([a, b])
                pos += n
            found += region
        busy = [(r[0], r[1]) for r in tail_runs]
        found = [r for r in found if not any(r[0] < b and a < r[1] for a, b in busy)]
        found.sort(key=lambda r: -(r[1] - r[0]))
        return found[:INNER_KEEP]

    def _scan_data(self):
        runs = []
        for s, e, p in self.span:
            if not (p & 2) or (p & 4):
                continue
            cnt, b = _tail_run(self.read, e, s)
            if b == 0 and cnt >= FLAG_MIN_RUN:
                runs.append([e - cnt, e])
            elif self.reclaimed:                                  # alte Schalter (Bytes 0/1) der frueheren Cave: ueberspringen
                skip = self._old_flags(e, s)
                if skip:
                    runs.append([e - skip[0], e - skip[1]])
        runs.sort(key=lambda r: -(r[1] - r[0]))
        self.log(f"[trainer] {len(runs)} Daten-Leerstelle(n) am Ende beschreibbarer Regionen")
        return runs

    def _old_flags(self, end, start, cap=0x8000):
        """Die Schalter einer frueheren ReaperPy-Cave (hoechstens 64 Byte, nur 0/1) liegen am Region-Ende; ein Eintrag, der
        geklickt wurde ohne dass der Haken aktiv war, bleibt dort auf 1.  Sie bleiben unberuehrt (die neue Cave bekommt
        frische Schalter DAVOR, damit nichts Altes ausgeloest wird).  -> (Laenge mit Schaltern, Laenge der Schalter) oder None."""
        n = min(cap, end - start)
        data = bytes(self.read(end - n, n))
        if len(data) != n or n <= 64 or not set(data[-64:]) <= {0, 1}:
            return None
        rest = data[:-64]
        free = len(rest) - len(rest.rstrip(b"\x00"))
        return (64 + free, 64) if free + 64 >= FLAG_MIN_RUN else None

    def code_capacity(self):
        """Groesse (Byte) der laengsten freien Code-Luecke - so gross darf eine Cave hoechstens sein."""
        if self._code is None:
            self._code = self._scan_code()
        return max(((r[1] - r[0]) & ~0xF for r in self._code), default=0)

    def explain(self, need):
        """Klartext, warum kein Platz gefunden wurde (Zahlen aus dem laufenden Spiel) - fuer Fehlermeldung und Bericht."""
        if self._code is None:
            self._code = self._scan_code()
        execs = [(s, e) for s, e, p in self.span if p & 4]
        lines = [f"Gebraucht: {need} Byte; groesste freie Luecke: {self.code_capacity()} Byte "
                 f"({len(self._code)} Luecke(n) in {len(execs)} ausfuehrbaren Region(en) des Images).",
                 f"Image-Bereich: {self.span[0][0]:#x}-{self.span[-1][1]:#x}."]
        busy = []
        for s, e, p in self.span:
            if p & 4:
                cnt, _b = _tail_run(self.read, e, s)
                if cnt < 0x20:
                    try:
                        busy.append(f"{e:#x}: endet mit {bytes(self.read(e - 8, 8)).hex(' ')}")
                    except Exception:  # noqa: BLE001
                        pass
        if self.reclaimed:
            lines.append(f"{len(self.reclaimed)} Rest(e) einer frueheren ReaperPy-Cave erkannt (werden wiederverwendet).")
        if busy:
            lines.append("Das Ende dieser Regionen ist NICHT leer (ein anderer Cheat/ein Plugin oder eine noch aktive "
                         "ReaperPy-Cave belegt es - erst BASIS deaktivieren oder das Spiel neu starten): " + "; ".join(busy[:4]) + ".")
        for s, e, p in self.span:
            if p & 4:
                lines.append(f"Ende {e:#x} (letzte {0x4000:#x} Byte, je 256 Byte ein Zeichen, '.'=00 'c'=CC '#'=Daten): "
                             f"{tail_map(self.read, e, min(0x4000, e - s))}")
        lines.append("Wenn der Trainer sehr gross ist: weniger Items je Projekt waehlen (der Tab ITEMS teilt automatisch "
                     "nach dem freien Platz auf).")
        return " ".join(lines)

    def alloc_code(self, need, near):
        if self._code is None:
            self._code = self._scan_code()
        need = (need + 15) & ~15
        for r in self._code:
            cave = (r[1] - need) & ~0xF
            if cave < r[0] or abs(cave - near) > LIMIT:
                continue
            r[1] = cave
            self.last_reclaim = next((f for rs, re_, f in self.reclaimed if rs <= cave < re_), None)
            return cave, need
        raise TrainerError("Kein freier Code-Platz (Padding am Ende einer ausfuehrbaren Image-Region) fuer die Cave "
                           f"gefunden. {self.explain(need)}")

    def alloc_data(self, need, near):
        if self._data is None:
            self._data = self._scan_data()
        need = (need + FLAG_ALIGN - 1) & ~(FLAG_ALIGN - 1)
        for r in self._data:
            addr = (r[1] - need) & ~(FLAG_ALIGN - 1)
            if addr < r[0] or abs(addr - near) > LIMIT:
                continue
            r[1] = addr
            return addr, need
        raise TrainerError("Kein beschreibbarer Leerraum im Spiel-Image fuer die Schalter gefunden "
                           "(Null-Stueck am Ende der letzten beschreibbaren Region, mind. 0x100 Byte)")


def capacity(read, maps, base, log=lambda _m: None):
    """Wie gross darf eine Cave in diesem Spiel hoechstens sein? -> dict(code=Byte, data=Byte).  Nur Lesen."""
    span = image_span(maps, base)
    if not span:
        raise TrainerError(f"Die Image-Basis {base:#x} liegt in keiner Speicherregion")
    sl = Slots(read, span, log)
    code = sl.code_capacity()                          # zuerst: erkennt Reste einer frueheren Cave (wichtig fuer die Daten-Suche)
    if sl._data is None:
        sl._data = sl._scan_data()
    if code == 0:                                      # Ursache ins Log, damit "0 Byte" nicht ratselhaft bleibt
        log("[trainer] KEIN freier Code-Platz gefunden. " + sl.explain(0))
    return {"code": code, "data": max(((r[1] - r[0]) & ~7 for r in sl._data), default=0)}


def fit_options(options, code_capacity, max_options=None, max_rows=None):
    """Eintraege der Reihe nach auf Projekte verteilen, bis die Cave (cave_size) nicht mehr in `code_capacity` passt
    (oder MAX_OPTIONS / MAX_ROWS erreicht sind) -> [[Option]].  Passt schon ein einzelner Eintrag nicht -> TrainerError."""
    max_options = max_options or MAX_OPTIONS
    max_rows = max_rows or MAX_ROWS
    out, cur, rows = [], [], 0
    if code_capacity <= 0:
        raise TrainerError("Im laufenden Spiel ist KEIN freier Code-Platz fuer die Cave da (0 Byte). Meist liegt am Ende der "
                           "Code-Region noch etwas: ein Cheat/Plugin (z. B. GoldHEN/etaHEN) oder eine Cave von ReaperPy, die "
                           "noch aktiv ist. Erst die BASIS bzw. den Cheat ausschalten oder das Spiel neu starten; Details "
                           "stehen im Log (Zeilen mit [trainer]).")
    for o in options:
        if cave_size([o]) > code_capacity:
            raise TrainerError(f"Schon der Eintrag '{o.name}' ({len(o.rows)} Zeilen, {cave_size([o])} Byte) passt nicht in "
                               f"die groesste freie Code-Luecke des Spiels ({code_capacity} Byte)")
        if cur and (len(cur) + 1 > max_options or rows + len(o.rows) > max_rows or cave_size(cur + [o]) > code_capacity):
            out.append(cur)
            cur, rows = [], 0
        cur.append(o)
        rows += len(o.rows)
    if cur:
        out.append(cur)
    return out


# ======================================================================
# Planen: Adressen waehlen, Bytes bauen, pruefen
# ======================================================================
class Plan:
    def __init__(self):
        self.base = 0
        self.cave = 0
        self.cave_bytes = b""
        self.cave_orig = b""
        self.flag_addr = 0
        self.flag_size = 0
        self.orig_pe = 0
        self.impl = 0
        self.slots = []                 # absolute vtable-Slot-Adressen
        self.options = []
        self.warnings = []
        self.anchors = []               # [(rva, hex)] Funktionsanfaenge zur Versionspruefung (check_project)
        self.verify_also = []           # weitere erlaubte Ist-Inhalte der Cave-Stelle (Reste einer alten Cave, anderes Padding)

    def rva(self, addr):
        return addr - self.base


def anchor_names(base, impl, orig_pe, row_impls):
    """{Adresse: Name} der Funktionen, deren Anfang als Versions-Fingerabdruck gespeichert wird."""
    names = {impl: "item_function", orig_pe: "process_event"}
    for a in sorted(row_impls):
        names.setdefault(a, f"row_function_{a - base:x}")
    return names


def signature_anchors(client, maps, base, names, read, log=print):
    """-> {name: (rva, aob)}.  Eindeutige Signatur ab Funktionsanfang (Adress-/Offset-Bytes als ??); gelingt das nicht
    (Capstone fehlt, kein eindeutiges Muster), faellt dieser eine Anker auf feste Bytes zurueck."""
    import aob
    out = {}
    for addr, name in names.items():
        try:
            sig, _hits = aob.make_signature(client, maps, addr, hook_len=0, wildcard_hook=False,
                                            min_len=ANCHOR_LEN, max_len=64, log=log)
        except Exception as e:  # noqa: BLE001 - ein Anker darf den Export nicht verhindern
            log(f"Signatur fuer {name} nicht moeglich ({e}) - feste Bytes")
            try:
                sig = " ".join(f"{b:02X}" for b in bytes(read(addr, ANCHOR_LEN)))
            except Exception:  # noqa: BLE001
                continue
        out[name] = (addr - base, sig)
    return out


def plan(read, maps, base, options, impl, orig_pe, slots, log=print, settle=0.4, client=None):
    """Alles was gebraucht wird, nur LESEND: read(addr,n)->bytes, maps=[(start,end,prot)], base = Image-Basis.
    Mit `client` (hat read_memory, optional Server-Scan) bekommen die Versions-Anker AOB-Signaturen mit Wildcards
    (ueberleben kleine Spiel-Updates und verschobene Funktionen); ohne client feste Bytes wie frueher.
    -> Plan.  Wirft TrainerError mit klarer Meldung."""
    options = list(options)
    if not options:
        raise TrainerError("Nichts zu exportieren: keine Eintraege")
    if len(options) > MAX_OPTIONS:
        raise TrainerError(f"Zu viele Eintraege ({len(options)} > {MAX_OPTIONS})")
    rows = sum(len(o.rows) for o in options)
    if rows > MAX_ROWS:
        raise TrainerError(f"Zu viele Items insgesamt ({rows} > {MAX_ROWS}) - auf mehrere Projekte aufteilen")
    names = [o.name.lower() for o in options]
    if len(set(names)) != len(names):
        raise TrainerError("Zwei Eintraege heissen gleich - Namen muessen verschieden sein")
    if not slots:
        raise TrainerError("Keine vtable-Slots (kein PlayerController / keine Spielfigur gefunden?)")

    span = image_span(maps, base)
    if not span:
        raise TrainerError(f"Die Image-Basis {base:#x} liegt in keiner Speicherregion")
    row_impls = sorted({base + r.call_impl_rva for o in options for r in o.rows if getattr(r, "call_impl_rva", None) is not None})
    if impl is None:
        if not row_impls:
            raise TrainerError("Keine Item-Funktion angegeben")
        impl = row_impls[0]
    checks = [("Item-Funktion", impl), ("ProcessEvent", orig_pe)] + [(f"Funktion {a:#x}", a) for a in row_impls]
    for what, a in checks + [(f"vtable-Slot {s:#x}", s) for s in slots]:
        if not in_span(span, a):
            raise TrainerError(f"{what} ({a:#x}) liegt nicht im Spiel-Image ({span[0][0]:#x}-{span[-1][1]:#x}) - "
                               "eine statische Adresse waere nach dem Neustart ungueltig")
    for s in slots:
        if struct.unpack("<Q", bytes(read(s, 8)))[0] != orig_pe:
            raise TrainerError(f"vtable-Slot {s:#x} zeigt nicht auf ProcessEvent {orig_pe:#x} "
                               "(ist schon ein Haken gesetzt? Erst die Haken des Tools entfernen / Spiel neu starten)")

    p = Plan()
    p.base, p.impl, p.orig_pe, p.slots, p.options = base, impl, orig_pe, sorted(set(slots)), options
    if client is not None:                                           # Fingerabdruck als Signaturen mit Wildcards
        p.anchors = signature_anchors(client, maps, base, anchor_names(base, impl, orig_pe, row_impls), read, log)
    else:
        for a in sorted({impl, orig_pe, *row_impls}):                # Fingerabdruck dieser Spielversion (feste Bytes)
            try:
                p.anchors.append((a - base, bytes(read(a, ANCHOR_LEN)).hex()))
            except Exception:  # noqa: BLE001
                pass
    slots_alloc = Slots(read, span, log)
    slots_alloc.code_capacity()                                      # Code-Platz zuerst suchen (erkennt Reste einer frueheren Cave)

    need_flags = flag_bytes_needed(len(options))
    p.flag_addr, p.flag_size = slots_alloc.alloc_data(need_flags, impl)
    first = bytes(read(p.flag_addr, p.flag_size))
    if any(first):
        raise TrainerError(f"Schalter-Bereich {p.flag_addr:#x} ist nicht leer - das Spiel nutzt ihn")
    if settle:
        time.sleep(settle)
        if bytes(read(p.flag_addr, p.flag_size)) != first:
            raise TrainerError(f"Schalter-Bereich {p.flag_addr:#x} aendert sich - das Spiel schreibt dort")
    p.warnings.append(f"Schalter @ base+{p.flag_addr - base:#x} ({p.flag_size} Byte): Null-Stueck am Ende einer "
                      "beschreibbaren Image-Region (Heuristik, mehrere Sekunden lang unveraendert gelesen)")

    size = cave_size(options)
    cave, reserved = slots_alloc.alloc_code(size, impl)
    code = build_cave(cave, p.flag_addr, orig_pe, impl, options, base)
    if len(code) > reserved:
        raise TrainerError(f"Cave-Groesse stimmt nicht ({len(code)} > {reserved}) - Programmfehler")
    p.cave, p.cave_bytes = cave, code
    live = bytes(read(cave, len(code)))
    if slots_alloc.last_reclaim is not None:                         # Rest einer frueheren ReaperPy-Cave: gilt als frei
        n = len(code)
        p.cave_orig = bytes([slots_alloc.last_reclaim]) * n          # "Original" = Padding, so bleibt der Trainer auf einer frischen Konsole gueltig
        p.verify_also = [x for x in dict.fromkeys((live, bytes([0xCC]) * n, bytes(n))) if x not in (p.cave_orig, code)]
        p.warnings.append("Die Cave liegt auf den Resten einer frueheren ReaperPy-Cave (Trainer war auf dieser Konsole schon "
                          "einmal aktiv / ueber GoldHEN geladen). Zuerst die alte BASIS bzw. den GoldHEN-Cheat AUSschalten.")
    else:
        p.cave_orig = live
        if len(set(p.cave_orig)) != 1 or p.cave_orig[0] not in FILL:
            raise TrainerError(f"Cave-Platz {cave:#x} ist nicht leer (das Spiel hat dort Daten)")
    for what, a in (("Cave", cave), ("Schalter", p.flag_addr)):
        if a < base:
            raise TrainerError(f"{what}-Adresse {a:#x} liegt unter der Basis {base:#x}")
    return p


# ======================================================================
# ReaperPy-Projekt schreiben
# ======================================================================
def _spaced(b):
    return " ".join(f"{x:02X}" for x in bytes(b))


def _var(label, offset, default="", new=""):
    return {"label": label, "offset": hex(offset), "defaultValue": default, "newValue": new}


def base_patch(p, author=""):
    """Cave schreiben, DANN vtable-Slots umbiegen (Reihenfolge = Schreibreihenfolge; Abbau macht patch_engine
    in umgekehrter Reihenfolge)."""
    entry = struct.pack("<Q", p.cave)
    orig = struct.pack("<Q", p.orig_pe)
    variables = [_var("OriginSource", p.rva(p.cave), _spaced(p.cave_orig), _spaced(p.cave_bytes))]
    for k, s in enumerate(p.slots):
        variables.append(_var(f"Haken {k + 1} (vtable)", p.rva(s), _spaced(orig), _spaced(entry)))
    doc = {"name": "00 BASIS - Item-Cave (zuerst aktivieren)", "author": author,
           "ImageBase": hex(p.base), "Verify": True, "Variables": variables}
    if p.verify_also:                                    # patch_engine akzeptiert diese Inhalte zusaetzlich zum Original
        doc["VerifyAlso"] = [_spaced(x) for x in p.verify_also]
    return doc


def option_patch(p, i, author=""):
    opt = p.options[i]
    what = ", ".join(f"{r.alias} x{r.amount}" for r in opt.rows[:3]) + (" ..." if len(opt.rows) > 3 else "")
    return {"name": f"{i + 1:02d} {opt.name}", "author": author, "ImageBase": hex(p.base), "Verify": True,
            "Info": f"Schalter-Byte {i} (base+{p.flag_addr + i - p.base:#x}); Cave setzt es nach dem Geben zurueck. {what}",
            "Variables": [_var("OriginSource", p.rva(p.flag_addr + i), "00", "01")]}


def _anchors_json(anchors):
    """Plan.anchors -> JSON.  Zwei Formen:
    dict {name: (rva, aob)}      -> {name: {"rva", "aob"}}   (Signatur mit Wildcards, ueberlebt verschobene Funktionen)
    Liste [(rva, hex)]            -> [{"rva", "bytes"}]       (feste Bytes, check_project)"""
    if isinstance(anchors, dict):
        return {n: {"rva": hex(r), "aob": a} for n, (r, a) in anchors.items()}
    return [{"rva": hex(r), "bytes": b} for r, b in anchors]


def spec_document(p, game="", title_id=""):
    return {
        "format": "reaperpy-item-trainer", "version": 1,
        "game": game, "title_id": title_id,
        "image_base": hex(p.base),
        "impl_rva": hex(p.impl - p.base), "process_event_rva": hex(p.orig_pe - p.base),
        "slot_rvas": [hex(s - p.base) for s in p.slots],
        "cave_rva": hex(p.cave - p.base), "cave_size": len(p.cave_bytes),
        "flag_rva": hex(p.flag_addr - p.base), "flag_size": p.flag_size,
        "anchors": _anchors_json(p.anchors),
        "options": [o.to_json() for o in p.options],
    }


def file_name_for(i, opt):
    return f"{i + 1:02d}_{clean_name(opt.name)}.reapproj"


def readme_text(p, project_name):
    lines = [
        f"ReaperPy Item-Trainer: {project_name}",
        "=" * (len(project_name) + 22),
        "",
        "BENUTZUNG",
        "  1. Spiel starten, Spielstand LADEN, in ReaperPy verbinden, diesen Ordner als Projekt waehlen.",
        "  2. '00 BASIS - Item-Cave' EINMAL aktivieren (schreibt die Cave und biegt den ProcessEvent-Zeiger um).",
        "  3. Danach ein Eintrag = ein Klick: Er setzt sein Schalter-Byte auf 1, das Spiel legt beim naechsten",
        "     ProcessEvent die Items ins Inventar und setzt den Schalter selbst zurueck. Im Spiel bleiben (nicht",
        "     pausieren), Inventar danach neu oeffnen. Zeigt die Karte noch 'AN': einmal aus- und wieder anklicken.",
        "  4. Zum Beenden BASIS deaktivieren (stellt den Zeiger und die Padding-Bytes zurueck).",
        "  5. BASIS und der Spiel-Thread-Haken des Tools (ITEMS EINFACH -> GEBEN) schliessen sich aus: fuer GEBEN im",
        "     Tool vorher BASIS deaktivieren (der Export entfernt den Haken des Tools selbst).",
        "",
        "EINTRAEGE",
    ]
    for i, o in enumerate(p.options):
        lines.append(f"  {i + 1:02d} {o.name}: " + ", ".join(f"{r.alias} x{r.amount}" for r in o.rows[:6])
                     + (f" ... (+{len(o.rows) - 6})" if len(o.rows) > 6 else ""))
    lines += [
        "",
        "TECHNIK (Offsets = RVA, Basis " + hex(p.base) + ")",
        f"  Cave        base+{p.cave - p.base:#x}  ({len(p.cave_bytes)} Byte, Code-Padding am Region-Ende)",
        f"  Schalter    base+{p.flag_addr - p.base:#x}  ({p.flag_size} Byte, 1 Byte je Eintrag, Reihenfolge wie oben)",
        "  Haken       vtable-Slot(s): " + ", ".join(f"base+{s - p.base:#x}" for s in p.slots),
        f"  Item-Funktion base+{p.impl - p.base:#x}   ProcessEvent base+{p.orig_pe - p.base:#x}",
        "",
        "WICHTIG / NICHT GETESTET",
        "  * Nur fuer diese Spielversion (Patch). Nach einem Spiel-Update neu exportieren.",
        "  * FName-Werte muessen bei jedem Spielstart gleich sein. Spiel NEU STARTEN und im Tool 'FNAMES PRUEFEN'",
        "    druecken. Meldet es Abweichungen, tun die betroffenen Eintraege nach dem Neustart das Falsche.",
        "  * Am echten Spiel/PS5 nicht getestet. Die Cave wurde auf einem x86-64-Prozessor ausgefuehrt (Register,",
        "    Stack, Schalter, Weiterleitung), aber nicht im Spiel. Vorher speichern.",
        "  * Schalter-Bereich = Null-Stueck am Ende der letzten beschreibbaren Image-Region (Heuristik).",
        "  * GoldHEN/etaHEN: Die Dateien sind einfache Hex-Patches; der vorhandene Export 'alle geladenen Patches ->",
        "    GoldHEN-JSON' wandelt sie um (BASIS + Eintraege als Checkboxen).",
    ]
    for w in p.warnings:
        lines.append("  * " + w)
    return "\n".join(lines) + "\n"


def write_project(out_dir, p, project_name=None, game="", title_id="", author="", set_image_base=None):
    """Schreibt Projekt-Ordner.  Entfernt alte Eintrag-Dateien dieses Trainers (anhand der Spec), damit nichts
    Veraltetes (falsche Schalter-Nummern) liegen bleibt.  -> Liste der geschriebenen Dateien."""
    os.makedirs(out_dir, exist_ok=True)
    project_name = project_name or os.path.basename(os.path.normpath(out_dir))
    old = _load_spec_raw(out_dir)
    if old:
        for i, o in enumerate(Option.from_json(x) for x in old.get("options", [])):
            f = os.path.join(out_dir, file_name_for(i, o))
            if os.path.isfile(f):
                os.remove(f)
    written = []

    def put(name, doc):
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        written.append(path)

    put(BASE_FILE, base_patch(p, author))
    for i, o in enumerate(p.options):
        put(file_name_for(i, o), option_patch(p, i, author))
    put(SPEC_FILE, spec_document(p, game, title_id))
    path = os.path.join(out_dir, README_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(readme_text(p, project_name))
    written.append(path)
    if set_image_base:
        try:
            set_image_base(p.base)
        except Exception:  # noqa: BLE001 - nur Komfort
            pass
    return written


def _load_spec_raw(out_dir):
    try:
        with open(os.path.join(out_dir, SPEC_FILE), encoding="utf-8") as f:
            d = json.load(f)
        return d if d.get("format") == "reaperpy-item-trainer" else None
    except (OSError, ValueError):
        return None


def load_options(out_dir):
    """Eintraege eines bestehenden Trainer-Projekts (zum Erweitern) -> [Option]; [] wenn keins da ist."""
    d = _load_spec_raw(out_dir)
    return [Option.from_json(x) for x in d.get("options", [])] if d else []


def merge_options(old, new):
    """Gleicher Name (ohne Gross/Klein) -> der neue ersetzt den alten, sonst wird angehaengt."""
    out = list(old)
    for o in new:
        for k, x in enumerate(out):
            if x.name.lower() == o.name.lower():
                out[k] = o
                break
        else:
            out.append(o)
    return out


# ======================================================================
# Passt ein fertiger Trainer zu DIESEM Spiel?  (andere Version / andere Item-Nummern)
# ======================================================================
def check_project(out_dir, read, base):
    """Liest `_trainer_spec.json` und vergleicht mit dem laufenden Spiel (nur Lesen).
    -> dict(ok_version, problems[list], anchors_checked, base_active)
    ok_version False = der Trainer wurde fuer eine andere Spielversion/Basis gebaut: NICHT aktivieren."""
    d = _load_spec_raw(out_dir)
    if not d:
        raise TrainerError(f"Kein Trainer-Projekt in {out_dir} ({SPEC_FILE} fehlt)")
    problems, checked = [], 0
    spec_base = int(d.get("image_base", "0x0"), 16)
    if spec_base != base:
        problems.append(f"Image-Basis: Trainer {spec_base:#x}, Spiel {base:#x}")
    anchors = d.get("anchors", [])
    if isinstance(anchors, dict):                      # Signaturen: nur Lesen an der gespeicherten Stelle
        import aob
        for name, a in anchors.items():
            rva = int(a["rva"], 16) if isinstance(a["rva"], str) else int(a["rva"])
            pat, mask = aob.parse_pattern(a["aob"])
            try:
                got = bytes(read(base + rva, len(pat)))
            except Exception as e:  # noqa: BLE001
                problems.append(f"{name}: +{rva:#x} nicht lesbar ({e})")
                continue
            checked += 1
            if len(got) != len(pat) or any(m and g != b for g, b, m in zip(got, pat, mask)):
                problems.append(f"{name}: Signatur passt bei +{rva:#x} nicht (Funktion verschoben oder geaendert)")
        anchors = []
    for a in anchors:
        rva, want = int(a["rva"], 16), a["bytes"]
        try:
            got = bytes(read(base + rva, len(want) // 2)).hex()
        except Exception as e:  # noqa: BLE001
            problems.append(f"+{rva:#x} nicht lesbar ({e})")
            continue
        checked += 1
        if got != want:
            problems.append(f"+{rva:#x}: Spiel hat {got}, Trainer erwartet {want}")
    if not d.get("anchors"):
        problems.append("Der Trainer enthaelt keinen Versions-Fingerabdruck (aelter) - mit ITEMS neu bauen")
    base_active = False
    try:
        cave = base + int(d["cave_rva"], 16)
        n = int(d.get("cave_size", 0))
        if n:
            raw = bytes(read(cave, min(n, 64)))
            base_active = len(set(raw)) > 2
    except Exception:  # noqa: BLE001
        pass
    return {"ok_version": not problems, "problems": problems, "anchors_checked": checked, "base_active": base_active}


def check_anchors(client, maps, base, spec):
    """Vergleicht die Signaturen aus `_trainer_spec.json` mit dem laufenden Spiel (nur Lesen).
    -> [(name, status, addr)]  status: "ok" (an der erwarteten Stelle), "moved" (genau ein Treffer woanders, addr),
    "missing" (kein Treffer), "ambiguous" (mehrere Treffer), "unreadable".  Ohne Anchors -> [].
    Alte Specs (Liste mit festen Bytes) werden byteweise verglichen: "ok" / "changed"."""
    import aob
    anchors = (spec or {}).get("anchors") or {}
    out = []
    if isinstance(anchors, list):
        for a in anchors:
            rva, want = int(a["rva"], 16), bytes.fromhex(a["bytes"])
            try:
                got = bytes(client.read_memory(base + rva, len(want)))
            except Exception:  # noqa: BLE001
                got = b""
            out.append((f"+{rva:#x}", "ok" if got == want else ("changed" if got else "unreadable"), base + rva))
        return out
    regions = aob.exec_regions(maps)
    for name, a in anchors.items():
        rva = int(a["rva"], 16) if isinstance(a["rva"], str) else int(a["rva"])
        pat, mask = aob.parse_pattern(a["aob"])
        addr = base + rva
        try:
            got = bytes(client.read_memory(addr, len(pat)))
        except Exception:  # noqa: BLE001
            got = b""
        if len(got) == len(pat) and all(g == b for g, b, m in zip(got, pat, mask) if m):
            out.append((name, "ok", addr))
            continue
        hits = aob.find_matches(client, regions, pat, mask, limit=3)
        if len(hits) == 1:
            out.append((name, "moved", hits[0]))
        elif hits:
            out.append((name, "ambiguous", hits[0]))
        else:
            out.append((name, "missing", 0))
    return out


def anchor_problem(res, base):
    """Ergebnis von check_anchors -> None (alles passt / nichts zu pruefen) oder eine Meldung fuer den Benutzer."""
    bad = []
    for name, status, addr in res:
        if status == "ok":
            continue
        if status == "moved":
            bad.append(f"{name}: liegt im laufenden Spiel bei +{addr - base:#x}")
        elif status == "changed":
            bad.append(f"{name}: Bytes weichen ab")
        elif status == "ambiguous":
            bad.append(f"{name}: Signatur nicht eindeutig")
        else:
            bad.append(f"{name}: nicht gefunden")
    if not bad:
        return None
    return ("Der Trainer passt nicht zum laufenden Spiel (andere Version/Build?) - nicht aktiviert: "
            + "; ".join(bad))


def refresh_fnames(options, live_by_alias):
    """FNames (die Item-Nummern aus dem Spiel) in den Zeilen durch die des laufenden Spiels ersetzen.
    live_by_alias: {alias: 8-Byte-FName}.  -> (neue Optionen, geaendert[alias], fehlt[alias]).  Zeilen ohne FName bleiben."""
    import ue_cavegen
    out, changed, missing = [], [], []
    for o in options:
        rows = []
        for r in o.rows:
            new = live_by_alias.get(r.alias)
            if getattr(r, "fname", None) is None:
                rows.append(r)
                continue
            if new is None:
                missing.append(r.alias)
                rows.append(r)
                continue
            new = bytes(new)
            if new != bytes(r.fname):
                changed.append(r.alias)
            if isinstance(r, ue_cavegen.CallRow):
                d = r.to_json()
                old_hex = bytes(r.fname).hex()
                d["fname"] = new.hex()
                for a in d["call"]["args"]:
                    if a["kind"] == "fname" and a["value"] == old_hex:
                        a["value"] = new.hex()
                rows.append(ue_cavegen.CallRow.from_json(d))
            else:
                rows.append(Row(r.alias, new, r.amount))
        out.append(Option(o.name, rows))
    return out, changed, missing


# ======================================================================
# FName-Pruefung (stabil ueber Neustarts?)
# ======================================================================
def compare_fnames(out_dir, live_alias_map):
    """Vergleicht die im Projekt gespeicherten FNames mit denen des laufenden Spiels.
    -> (ok:[alias], geaendert:[(alias, gespeichert_hex, live_hex)], fehlt:[alias])"""
    d = _load_spec_raw(out_dir)
    if not d:
        raise TrainerError(f"Kein Trainer-Projekt in {out_dir} ({SPEC_FILE} fehlt)")
    ok, changed, missing = [], [], []
    seen = set()
    for o in d["options"]:
        for r in o["rows"]:
            a = r["alias"]
            if not r.get("fname") or a in seen:
                continue
            seen.add(a)
            live = live_alias_map.get(a)
            if live is None:
                missing.append(a)
            elif bytes(live).hex() == r.get("fname"):
                ok.append(a)
            else:
                changed.append((a, r["fname"], bytes(live).hex()))
    return ok, changed, missing


def moved_rvas(spec, res, base):
    """check_anchors-Ergebnis -> (verschoben {alte_rva: neue_rva}, Rest [(name, status)]).
    Nur Anker mit genau einem Treffer an anderer Stelle ("moved") lassen sich automatisch korrigieren; alles andere
    (missing / ambiguous / changed / unreadable) steht in `Rest` und bedeutet: Trainer neu bauen."""
    anchors = (spec or {}).get("anchors") or {}
    moved, rest = {}, []
    for name, status, addr in res:
        if status == "ok":
            continue
        a = anchors.get(name) if isinstance(anchors, dict) else None
        if status == "moved" and a is not None:
            old = int(a["rva"], 16) if isinstance(a["rva"], str) else int(a["rva"])
            moved[old] = addr - base
        else:
            rest.append((name, status))
    return moved, rest


def remap_options(options, rva_map):
    """Funktions-RVAs der Zeilen nach `rva_map` {alt: neu} ersetzen.  -> (neue Optionen, Anzahl geaenderter Zeilen)."""
    import ue_cavegen
    out, n = [], 0
    for o in options:
        rows = []
        for r in o.rows:
            old = getattr(r, "call_impl_rva", None)
            if old in rva_map and isinstance(r, ue_cavegen.CallRow):
                d = r.to_json()
                d["call"]["impl_rva"] = hex(rva_map[old])
                rows.append(ue_cavegen.CallRow.from_json(d))
                n += 1
            else:
                rows.append(r)
        out.append(Option(o.name, rows))
    return out, n
# ======================================================================
# Vorschau (Dry-Run): wo wuerde was landen?  Nur Anzeige, nichts wird geschrieben
# ======================================================================
def prot_text(prot):
    """Schutzbits (1=r, 2=w, 4=x) -> 'r-x' / 'rw-' / 'rwx'."""
    return ("r" if prot & 1 else "-") + ("w" if prot & 2 else "-") + ("x" if prot & 4 else "-")


def region_info(maps, addr):
    """-> (start, ende, 'r-x') der Region, in der addr liegt; None wenn keine."""
    for start, end, prot in maps:
        if start <= addr < end:
            return start, end, prot_text(prot)
    return None


def preview(p, maps):
    """Alles Wesentliche eines Plans fuer eine Rueckfrage vor dem Schreiben.  -> dict"""
    cave_r, flag_r = region_info(maps, p.cave), region_info(maps, p.flag_addr)
    sig = sum(1 for v in (p.anchors.values() if isinstance(p.anchors, dict) else ()) if "?" in v[1])
    return {
        "cave": p.cave, "cave_rva": p.rva(p.cave), "cave_size": len(p.cave_bytes), "cave_region": cave_r,
        "cave_writable": bool(cave_r and "w" in cave_r[2]),
        "flag": p.flag_addr, "flag_rva": p.rva(p.flag_addr), "flag_size": p.flag_size, "flag_region": flag_r,
        "hooks": len(p.slots), "options": len(p.options), "rows": sum(len(o.rows) for o in p.options),
        "anchors": len(p.anchors), "anchors_with_wildcards": sig, "warnings": list(p.warnings),
    }


def preview_lines(pv):
    """preview() -> Textzeilen fuer den Rueckfrage-Dialog."""
    def where(r):
        return f"Region {r[0]:#x}-{r[1]:#x} ({r[2]})" if r else "ausserhalb bekannter Regionen"
    lines = [f"{pv['options']} Einträge, {pv['rows']} Items, {pv['hooks']} Haken (vtable-Slots)",
             f"Cave: base+{pv['cave_rva']:#x} ({pv['cave']:#x}), {pv['cave_size']} Byte - {where(pv['cave_region'])}",
             f"Schalter: base+{pv['flag_rva']:#x} ({pv['flag']:#x}), {pv['flag_size']} Byte - {where(pv['flag_region'])}"]
    if pv["cave_writable"]:
        lines.append("WARNUNG: Die Cave liegt in einer beschreibbaren Region (rwx) - nur Ausweichplatz, bitte testen.")
    if pv["anchors"]:
        lines.append(f"Versions-Prüfung: {pv['anchors']} Funktions-Anker, davon {pv['anchors_with_wildcards']} als Signatur mit Wildcards")
    return lines
