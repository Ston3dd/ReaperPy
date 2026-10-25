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
LIMIT = 0x7F000000                  # rel32-Reichweite mit Sicherheitsabstand
NAME_MAX = 60
PACK_SIZE = 14                      # so viele Items hoechstens in einem Paket-Eintrag


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


class Slots:
    """Freie Stuecke: Code-Padding (r-x) und Daten-Padding (rw-), jeweils am Region-Ende, von hinten nach vorn."""

    def __init__(self, read, span, log=print):
        self.read, self.span, self.log = read, span, log
        self._code, self._data = None, None

    def _scan_code(self):
        runs = []
        for s, e, p in self.span:
            if not p & 4:
                continue
            cnt, _b = _tail_run(self.read, e, s)
            if cnt >= 0x20:
                runs.append([e - cnt, e])
        runs.sort(key=lambda r: -(r[1] - r[0]))
        self.log(f"[trainer] {len(runs)} Code-Padding-Luecke(n) am Region-Ende")
        return runs

    def _scan_data(self):
        runs = []
        for s, e, p in self.span:
            if not (p & 2) or (p & 4):
                continue
            cnt, b = _tail_run(self.read, e, s)
            if b == 0 and cnt >= FLAG_MIN_RUN:
                runs.append([e - cnt, e])
        runs.sort(key=lambda r: -(r[1] - r[0]))
        self.log(f"[trainer] {len(runs)} Daten-Leerstelle(n) am Ende beschreibbarer Regionen")
        return runs

    def alloc_code(self, need, near):
        if self._code is None:
            self._code = self._scan_code()
        need = (need + 15) & ~15
        for r in self._code:
            cave = (r[1] - need) & ~0xF
            if cave < r[0] or abs(cave - near) > LIMIT:
                continue
            r[1] = cave
            return cave, need
        raise TrainerError("Kein freier Code-Platz (Padding am Ende einer ausfuehrbaren Image-Region) fuer die Cave gefunden")

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

    def rva(self, addr):
        return addr - self.base


def plan(read, maps, base, options, impl, orig_pe, slots, log=print, settle=0.4):
    """Alles was gebraucht wird, nur LESEND: read(addr,n)->bytes, maps=[(start,end,prot)], base = Image-Basis.
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
    slots_alloc = Slots(read, span, log)

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
    p.cave_orig = bytes(read(cave, len(code)))
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
    return {"name": "00 BASIS - Item-Cave (zuerst aktivieren)", "author": author,
            "ImageBase": hex(p.base), "Variables": variables}


def option_patch(p, i, author=""):
    opt = p.options[i]
    what = ", ".join(f"{r.alias} x{r.amount}" for r in opt.rows[:3]) + (" ..." if len(opt.rows) > 3 else "")
    return {"name": f"{i + 1:02d} {opt.name}", "author": author, "ImageBase": hex(p.base),
            "Info": f"Schalter-Byte {i} (base+{p.flag_addr + i - p.base:#x}); Cave setzt es nach dem Geben zurueck. {what}",
            "Variables": [_var("OriginSource", p.rva(p.flag_addr + i), "00", "01")]}


def spec_document(p, game="", title_id=""):
    return {
        "format": "reaperpy-item-trainer", "version": 1,
        "game": game, "title_id": title_id,
        "image_base": hex(p.base),
        "impl_rva": hex(p.impl - p.base), "process_event_rva": hex(p.orig_pe - p.base),
        "slot_rvas": [hex(s - p.base) for s in p.slots],
        "cave_rva": hex(p.cave - p.base), "cave_size": len(p.cave_bytes),
        "flag_rva": hex(p.flag_addr - p.base), "flag_size": p.flag_size,
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
