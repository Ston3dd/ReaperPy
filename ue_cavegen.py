"""ue_cavegen.py - allgemeiner Code-Cave-Baustein: JEDE native UFunction (Item geben, Geld, XP ...) als Trainer-Eintrag.

Baut auf cave_trainer.py auf (gleiche statische Cave: ProcessEvent-Haken im vtable, Schalter-Bytes, ein Aufruf je Klick).
Statt der fest verdrahteten Standard-Form (Item geben) wird der Aufruf aus den Parametern der Funktion zusammengesetzt
(System-V-ABI, wie die Exec-Thunks der Spiele sie aufrufen):

    rdi = this           (nichts / das gehookte Objekt / ein Zeiger-Member des gehookten Objekts, z. B. CheatManager)
    rsi, rdx, rcx, r8, r9 = Ganzzahl-/Zeiger-/FName-Parameter in Deklarationsreihenfolge
    xmm0..xmm7           = float/double-Parameter
    FName / Zahl per ZEIGER ('ref', const T&): die Cave legt den Wert hinter ihren Code und uebergibt die Adresse

Nicht unterstuetzt (klare Fehlermeldung statt Raten): Out-Parameter, Structs/Strings/Arrays als Parameter, mehr als 5
Ganzzahl- bzw. 8 Gleitkomma-Parameter, Rueckgabe-Structs.  Alles am echten Spiel NICHT getestet - die erzeugte Cave
selbst wird in tests/test_ue_cavegen.py auf einem echten x86-64-Prozessor ausgefuehrt.
"""
import re
import struct

import cave_trainer as T
import ue_profile as P

INT_REGS = [  # (mov r32,imm32 | movabs r64,imm64 | lea r64,[rip+disp32])
    ("BE", "48BE", "488D35"),     # rsi
    ("BA", "48BA", "488D15"),     # rdx
    ("B9", "48B9", "488D0D"),     # rcx
    ("41B8", "49B8", "4C8D05"),   # r8
    ("41B9", "49B9", "4C8D0D"),   # r9
]
MAX_FLOAT_REGS = 8
SIZES = {"bool": 1, "int8": 1, "uint8": 1, "int16": 2, "uint16": 2, "int32": 4, "uint32": 4, "int": 4, "int64": 8,
         "uint64": 8, "int8_t": 1, "uint8_t": 1, "int16_t": 2, "uint16_t": 2, "int32_t": 4, "uint32_t": 4,
         "int64_t": 8, "uint64_t": 8}
SIGNED = {"int8", "int16", "int32", "int", "int64", "int8_t", "int16_t", "int32_t", "int64_t"}
THIS_MODES = ("zero", "hooked", "member")


# --------------------------------------------------------------------------------------------------
# Parameter klassifizieren
# --------------------------------------------------------------------------------------------------
def param_kind(ptype, sdk=None):
    """-> (kind, size, signed) mit kind 'int'|'float'|'double'|'fname'|'ptr'|'enum', oder None (nicht unterstuetzt)."""
    raw = str(ptype)
    b = P.base_name(raw)
    if "*" in raw:
        return "ptr", 8, False
    if b == "FName":
        return "fname", 8, False
    if b in SIZES:
        return "int", SIZES[b], b in SIGNED
    if b == "float":
        return "float", 4, True
    if b == "double":
        return "double", 8, True
    if re.search(r"\benum\b", raw) or (sdk is not None and b in sdk.enums):
        return "enum", 1, False
    return None


def classify_params(params, sdk=None):
    """[(type, name)] -> [{'name','type','kind','size','signed','role','out'}]; wirft TrainerError bei Nicht-Unterstuetztem.
    role: 'id' (FName/ID-Zahl), 'count' (Menge) oder 'other'."""
    out = []
    for t, n in params:
        raw = str(t)
        if "&" in raw and "const" not in raw:
            raise T.TrainerError(f"Parameter '{n}' ({raw}) ist ein Out-Parameter - nicht unterstuetzt")
        k = param_kind(raw, sdk)
        if k is None:
            raise T.TrainerError(f"Parameter '{n}' hat den Typ '{raw}' - nur Zahlen, Bool, Enum, FName, float/double und "
                                 "Zeiger werden unterstuetzt")
        kind, size, signed = k
        role = "other"
        simple = str(n).split(".")[0]                           # SDK schreibt oft 'Item.param' statt 'Item'
        if kind == "fname" or (kind == "int" and P.ID_NAME.search(simple) and not P.COUNT_NAME.search(simple)):
            role = "id"
        elif kind in ("int", "float", "double") and P.COUNT_NAME.search(simple) and not P.COUNT_BAD.search(simple):
            role = "count"
        out.append({"name": n, "type": raw, "kind": kind, "size": size, "signed": signed, "role": role,
                    "ref": "const" in raw and "&" in raw})
    n_int = sum(1 for a in out if a["kind"] in ("int", "ptr", "fname", "enum"))
    n_flt = sum(1 for a in out if a["kind"] in ("float", "double"))
    if n_int > len(INT_REGS):
        raise T.TrainerError(f"Zu viele Ganzzahl-Parameter ({n_int} > {len(INT_REGS)}) - der Rest laege auf dem Stack")
    if n_flt > MAX_FLOAT_REGS:
        raise T.TrainerError(f"Zu viele Gleitkomma-Parameter ({n_flt} > {MAX_FLOAT_REGS})")
    return out


def check_return(ret):
    r = str(ret or "").strip()
    if not r or r == "void":
        return
    if param_kind(r) is None and "*" not in r:
        raise T.TrainerError(f"Rueckgabetyp '{r}' (Struct/String?) wird nicht unterstuetzt - der Aufruf waere falsch")


WALK_PTR = re.compile(
    r"(?i)cheatmanager|acknowledgedpawn|^pawn$|character$|playerstate|inventory|backpack|^bag$|itemcomp|"
    r"itemmanager|equipment|storage"
)
MAX_THIS_DEPTH = 4


def _ptr_class(m):
    """SDK-Member -> Klassenname, wenn es ein Objekt-Zeiger ist, sonst None."""
    raw = str(m.type)
    if "*" not in raw and "TObjectPtr" not in raw:
        return None
    t = P.clean_type(raw)
    return t.split()[-1] if t else None


def _is_owner(sdk, got, owner):
    """Passt der Zeiger-Typ zur Geben-Klasse (auch Unter-/Oberklasse: UCheatManager* -> PalCheatManager)."""
    return got == owner or P.derives_from(sdk, owner, got) or P.derives_from(sdk, got, owner)


def _this_path(sdk, start, owner, depth=0, path=(), seen=None):
    """Kette von Zeiger-Offsets start -> owner.  Nur uebliche Player-Felder, kein Blindflug durch alle UObject*."""
    if P.derives_from(sdk, start, owner) or start == owner:
        return list(path)
    if depth >= MAX_THIS_DEPTH or start in (seen or ()):
        return None
    seen = (seen or set()) | {start}
    members = list(sdk.all_members(start)) if start in sdk.classes else []
    ranked = []
    for m in members:
        tgt = _ptr_class(m)
        if not tgt:
            continue
        if _is_owner(sdk, tgt, owner):
            ranked.append((0, m.offset, tgt, m.name))
        elif WALK_PTR.search(m.name) or WALK_PTR.search(tgt):
            ranked.append((1, m.offset, tgt, m.name))
    ranked.sort()
    for _pri, off, tgt, name in ranked:
        step = path + ((off, f"{start}.{name}"),)
        if _pri == 0:
            return list(step)
        found = _this_path(sdk, tgt, owner, depth + 1, step, seen)
        if found is not None:
            return found
    return None


def choose_this(sdk, owner, hooked="APlayerController", static=False):
    """Woher kommt `this`?  -> (modus, offset_oder_kette, hinweis).
    offset_oder_kette: 0 (hooked/zero), eine Zahl (ein Zeiger) oder ein Tupel von Offsets (Pawn -> Inventar)."""
    if static:
        return "zero", 0, "statische Funktion: this wird nicht gebraucht"
    if P.derives_from(sdk, hooked, owner) or hooked == owner:
        return "hooked", 0, f"{owner} ist Elternklasse von {hooked}: this = das gehookte Objekt"
    found = _this_path(sdk, hooked, owner)
    if found:
        offs = tuple(p[0] for p in found)
        note = "this = " + " -> ".join(f"{n} @+{o:#x}" for o, n in found)
        note += "; ist ein Zeiger 0, wird der Aufruf uebersprungen"
        return "member", (offs[0] if len(offs) == 1 else offs), note
    return "zero", 0, (f"Keine Instanz von {owner} ueber {hooked} erreichbar - this = 0.  Funktioniert nur, wenn die Funktion "
                       "this nicht benutzt; sonst Absturz moeglich!")


# --------------------------------------------------------------------------------------------------
# Aufruf-Beschreibung + Maschinencode
# --------------------------------------------------------------------------------------------------
class CallSpec:
    """impl_rva = native Implementierung (RVA); this_mode zero|hooked|member (+this_off / this_path); args = Liste von Dicts
    {name, kind, size, signed, value, mode} mit mode 'val' | 'ref'; value: int/float oder 8 Byte (FName)."""

    def __init__(self, impl_rva, args, this_mode="zero", this_off=0, function="", this_path=None):
        if this_mode not in THIS_MODES:
            raise T.TrainerError(f"this-Modus '{this_mode}' unbekannt")
        path = [int(x) for x in this_path] if this_path else []
        off = int(this_off or 0)
        if this_mode == "member" and not path:
            path = [off]
        self.impl_rva, self.this_mode, self.this_off = int(impl_rva), this_mode, (path[0] if path else off)
        self.this_path, self.function = path, function
        self.args = [dict(a) for a in args]
        for a in self.args:
            a.setdefault("mode", "val")
            v = a["value"]
            if isinstance(v, str):
                a["value"] = bytes.fromhex(v)
            if a["kind"] == "fname" and (not isinstance(a["value"], (bytes, bytearray)) or len(a["value"]) != 8):
                raise T.TrainerError(f"FName-Parameter '{a['name']}' braucht 8 Byte")

    def to_json(self):
        d = {"function": self.function, "impl_rva": hex(self.impl_rva), "this": self.this_mode, "this_off": hex(self.this_off),
             "args": [dict(a, value=a["value"].hex() if isinstance(a["value"], (bytes, bytearray)) else a["value"])
                      for a in self.args]}
        if len(self.this_path) > 1:
            d["this_path"] = [hex(x) for x in self.this_path]
        return d

    @classmethod
    def from_json(cls, d):
        path = [int(x, 16) if isinstance(x, str) else int(x) for x in d["this_path"]] if d.get("this_path") else None
        return cls(int(d["impl_rva"], 16), d["args"], d.get("this", "zero"), int(d.get("this_off", "0"), 16),
                   d.get("function", ""), path)


def _raw_value(a):
    """Wert -> Bytes in Parametergroesse (Ganzzahl little endian, float/double IEEE)."""
    v, k, sz = a["value"], a["kind"], a["size"]
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    if k == "float":
        return struct.pack("<f", float(v))
    if k == "double":
        return struct.pack("<d", float(v))
    iv = int(v)
    if not -(1 << (8 * sz - 1)) <= iv < (1 << (8 * sz)):
        raise T.TrainerError(f"Wert {iv} passt nicht in Parameter '{a['name']}' ({sz} Byte)")
    return (iv & ((1 << (8 * sz)) - 1)).to_bytes(sz, "little")


def emit_call(e, spec, base):
    """Ein kompletter Aufruf: this, Parameter, call.  Benutzt nur rax (Float-Laden) und die Argumentregister; die
    Originalargumente liegen auf dem Stack: [rsp]=rdx, [rsp+8]=rsi, [rsp+16]=rdi (die Cave hat sie gerettet)."""
    skip = None
    if spec.this_mode == "zero":
        e.raw("31FF")                                           # xor edi,edi
    else:
        e.raw("488B7C2410")                                     # mov rdi,[rsp+0x10]   (gehooktes Objekt)
        hops = spec.this_path if spec.this_mode == "member" else []
        for off in hops:
            e.raw("488BBF" + struct.pack("<i", int(off)).hex())  # mov rdi,[rdi+off]
            e.raw("4885FF")                                     # test rdi,rdi
            if skip is None:
                skip = e.uniq("skip")
            e.raw("0F84")                                       # jz skip
            e.rel32(skip)
    ireg = freg = 0
    for a in spec.args:
        raw = _raw_value(a)
        k = a["kind"]
        if k in ("float", "double") and a["mode"] == "val":
            if k == "float":
                e.raw("B8" + raw.hex())                         # mov eax,imm32
                e.raw("660F6E" + f"{0xC0 + 8 * freg:02X}")      # movd xmmN,eax
            else:
                e.raw("48B8" + raw.hex())                       # mov rax,imm64
                e.raw("66480F6E" + f"{0xC0 + 8 * freg:02X}")    # movq xmmN,rax
            freg += 1
            continue
        mov32, mov64, lea = INT_REGS[ireg]
        ireg += 1
        if a["mode"] == "ref":
            lab = e.pool(raw.ljust(8, b"\0"))
            e.raw(lea)                                          # lea reg,[rip+pool]
            e.rel32(lab)
        elif a["size"] == 8 or k in ("fname", "ptr"):
            e.raw(mov64 + raw.ljust(8, b"\0").hex())            # movabs reg,imm64
        else:
            iv = int.from_bytes(raw, "little")
            e.raw(mov32 + struct.pack("<I", iv & 0xFFFFFFFF).hex())   # mov reg32,imm32 (Null-Erweiterung)
    e.raw("E8")                                                 # call impl
    e.rel32(base + spec.impl_rva)
    if skip:
        e.label(skip)


class CallRow(T.Row):
    """Eine Trainer-Zeile = ein beliebiger Funktionsaufruf.  fname/amount dienen nur Anzeige und FNAMES PRUEFEN."""

    def __init__(self, alias, spec, fname=None, amount=1):
        self.alias, self.spec, self.amount = alias, spec, max(1, int(amount))
        self.fname = bytes(fname) if fname is not None else None
        self.call_impl_rva = spec.impl_rva

    def emit(self, e, impl, base):
        emit_call(e, self.spec, base)

    def to_json(self):
        return {"alias": self.alias, "fname": self.fname.hex() if self.fname else None, "amount": self.amount,
                "call": self.spec.to_json()}

    @classmethod
    def from_json(cls, d):
        f = d.get("fname")
        return cls(d["alias"], CallSpec.from_json(d["call"]), bytes.fromhex(f) if f else None, d.get("amount", 1))


def extra_value(extra, name):
    """Wert aus extra fuer den SDK-Parameter `name`.  Akzeptiert 'Item', 'Item.param', Gross/Klein - oder None."""
    if not extra:
        return None
    if name in extra:
        return extra[name]
    want = {name.lower(), name.lower().split(".")[0]}
    for k, v in extra.items():
        kn = str(k).lower().replace(" ", "")
        if kn in want or kn.split(".")[0] in want:
            return v
    return None


def _this_spec(this):
    """(modus, offset_oder_kette) -> (modus, this_off, this_path)."""
    mode, off = this[0], this[1]
    if isinstance(off, (list, tuple)):
        path = [int(x) for x in off]
        return mode, (path[0] if path else 0), path
    return mode, int(off or 0), None


def build_row(alias, impl_rva, params, ret, sdk, this, id_value=None, count_value=1, extra=None, byref=(), function=""):
    """Eine Zeile aus den SDK-Parametern der Funktion.
      id_value   FName-Bytes (8) oder ID-Zahl fuer den Parameter der Rolle 'id'
      count_value Menge fuer die Rolle 'count'
      extra      {Parametername: Wert} fuer alle uebrigen (Standard 0); 'Item.param' zaehlt als 'Item'
      byref      Namen der Parameter, die per Zeiger uebergeben werden (const T&)
      this       (modus, offset) oder (modus, (off1, off2, ...))"""
    check_return(ret)
    cls = classify_params(params, sdk)
    extra = dict(extra or {})
    args, fname, amount = [], None, count_value
    used_id = used_cnt = False
    byref_set = {str(x).lower() for x in byref} | {str(x).split(".")[0].lower() for x in byref}
    for a in cls:
        n, k = a["name"], a["kind"]
        got = extra_value(extra, n)
        if got is not None:
            val = got
        elif a["role"] == "id" and not used_id and id_value is not None:
            val, used_id = id_value, True
        elif a["role"] == "count" and not used_cnt:
            val, used_cnt = count_value, True
        elif k == "fname":
            raise T.TrainerError(f"Fuer den FName-Parameter '{n}' fehlt der 8-Byte-FName (Tabellenzeile waehlen)")
        else:
            val = 0.0 if k in ("float", "double") else 0
        if k == "fname":
            if not isinstance(val, (bytes, bytearray)) or len(val) != 8:
                raise T.TrainerError(f"Fuer den FName-Parameter '{n}' fehlt der 8-Byte-FName (Tabellenzeile waehlen)")
            if any(val) and fname is None:
                fname = bytes(val)
        mode = "ref" if n.lower() in byref_set or n.split(".")[0].lower() in byref_set else "val"
        args.append({"name": n, "kind": k, "size": a["size"], "signed": a["signed"], "value": val, "mode": mode})
    mode, off, path = _this_spec(this)
    spec = CallSpec(impl_rva, args, mode, off, function, path)
    for a in spec.args:                 # Wert-Pruefung jetzt, nicht erst beim Bauen
        _raw_value(a)
    return CallRow(alias, spec, fname, int(amount) if isinstance(amount, (int, float)) and amount >= 1 else 1)


def find_impl(read, base, thunk):
    """Native Implementierung hinter einem Exec-Thunk = letzter Aufruf des Thunks (Stack-Rahmen `push rbp; mov rbp,rsp`)
    -> Adresse oder None (nur Lesen, braucht Capstone)."""
    import asm_tools

    try:
        ins = asm_tools.disassemble_lines(read(thunk, 0x500), thunk, 160)
    except Exception:  # noqa: BLE001
        return None
    calls = []
    for i in ins:
        if i["mnemonic"] == "call" and i["op_str"].startswith("0x"):
            t = int(i["op_str"], 16)
            if t != thunk and base <= t < base + 0x2000_0000 and t not in calls:
                calls.append(t)
        if i["mnemonic"].startswith("ret"):
            break
    if not calls:
        return None
    try:
        return calls[-1] if read(calls[-1], 4) == b"\x55\x48\x89\xE5" else None
    except Exception:  # noqa: BLE001
        return None
