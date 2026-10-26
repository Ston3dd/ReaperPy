"""cheatmenu_cave.py - aus einem Cheat-Menue-Eintrag direkt die passende Code Cave bauen (Rechtsklick im Tab CHEAT-MENUE).

Das Cheat-Menue schreibt nur Speicherwerte der Figur (Freezer) - laeuft nur, solange ReaperPy verbunden ist.  Eine Code Cave
dagegen aendert den Spiel-CODE, der diesen Wert schreibt, und wirkt dauerhaft (auch exportiert als GoldHEN/etaHEN-Cheat).

Ablauf (ohne Oberflaeche und ohne Konsole testbar):
  1. Offset des Members: live aus dem Spiel (menu._off), sonst aus dem SDK
  2. Code holen: dump.bin des Spielordners, sonst live von der Konsole gelesen (Code-Bereich des Hauptmoduls)
  3. ue_instr.scan: alle Instruktionen, die [reg+Offset] schreiben, nach Score sortiert
  4. je Treffer pruefen, welche Cave sich bauen laesst:
       keep   'Wert kann nicht sinken'  (nur Zahlen-Eintraege: Leben, Ausdauer, Munition, Geld ...)
       force  'Wert festschreiben'      (Zahlen und Schalter; die Original-Instruktion laeuft, danach wird der Wert gesetzt)
       nop    'Schreibzugriff aus'      (Instruktion wird zu NOP)
  5. .reapproj in den Patch-Ordner des Projekts schreiben (ReaperPy-Format, wie der UE-Tab)
Hinweis: die Cave gilt fuer ALLE Objekte, die diesen Code benutzen (auch Gegner) - der Aufrufer zeigt das an.
"""
import json
import os
import struct

import ue_auto
import ue_instr as U

MODES = ("keep", "force", "nop")
MODE_TEXT = {
    "keep": "Wert kann nicht sinken",
    "force": "Wert festschreiben",
    "nop": "Schreibzugriff abschalten (NOP)",
}
MIN_OFFSET = 0x80            # darunter ist die Byte-Suche zu unspezifisch (ue_instr.scan)
LIVE_MAX = 0x1000_0000       # hoechstens so viele Byte Code live von der Konsole lesen
LIVE_CHUNK = 0x100000
CODE_PROT = 4
AUTO_TEXT = ("", "auto", "max")   # Eingaben, die bei einer festen Cave keinen Wert ergeben


class CaveError(ValueError):
    pass


def mode_text(mode):
    """Anzeigename der Cave-Art in der Sprache des Hauptfensters (im EN-Modus Englisch, sonst Deutsch)."""
    text = MODE_TEXT[mode]
    try:
        import tools_i18n
        return tools_i18n.translate(text)
    except Exception:  # noqa: BLE001
        return text


# --------------------------------------------------------------------------------------------------
# Eintrag -> Offset / Wert
# --------------------------------------------------------------------------------------------------
def entry_offset(menu, e):
    """Offset des Members im Objekt: live aus dem Spiel, sonst aus dem SDK."""
    off = None
    if e.source != "spiel" and menu is not None:
        try:
            off = menu._off(e.cls, e.member)
        except Exception:  # noqa: BLE001
            off = None
    if off is None:
        off = e.target.offset if getattr(e, "target", None) is not None else e.offset
    if off is None or off < 0:
        raise CaveError(f"Der Offset von {e.cls}.{e.member} ist unbekannt - SDK laden / Menü neu aufbauen")
    if off < MIN_OFFSET:
        raise CaveError(f"{e.cls}.{e.member} liegt bei +{off:#x} - so kleine Offsets kommen im Code tausendfach vor, "
                        "eine zuverlässige Suche ist nicht möglich (nimm AN/AUS im Menü).")
    return off


def entry_value(e, text=None):
    """Der Wert, der festgeschrieben werden soll: Eingabe, sonst AN-Wert (Schalter) bzw. Vorgabe (Zahl)."""
    if text is not None and str(text).strip():
        return str(text).strip()
    if e.kind == "toggle":
        return "1" if e.on in (True, None) else str(int(e.on))
    return str(e.default)


def value_bits(type_name, text, size):
    """Text -> Rohbits fuer einen Store von `size` Byte (Float/Double nach Typ, sonst ganze Zahl)."""
    t = (type_name or "").lower().replace("_t", "")
    s = str(text).strip().lower()
    if s in ("true", "an", "on", "ja"):
        s = "1"
    elif s in ("false", "aus", "off", "nein"):
        s = "0"
    if s in AUTO_TEXT:
        raise CaveError("'auto' geht bei einer Code Cave nicht - eine feste Zahl eintragen")
    try:
        if t in ("float", "float32"):
            if size != 4:
                raise CaveError("Float-Wert, aber die Instruktion schreibt nicht 4 Byte")
            return struct.unpack("<I", struct.pack("<f", float(s)))[0]
        if t == "double":
            if size != 8:
                raise CaveError("Double-Wert, aber die Instruktion schreibt nicht 8 Byte")
            bits = struct.unpack("<Q", struct.pack("<d", float(s)))[0]
            if not (bits < 1 << 31 or bits >= (1 << 64) - (1 << 31)):
                raise CaveError("Dieser Double-Wert passt nicht in einen 32-Bit-Direktwert (nur z. B. 0 geht)")
            return bits
        v = int(s, 0)
    except ValueError as ex:
        raise CaveError(f"'{text}' ist keine Zahl") from ex
    return v & ((1 << (8 * size)) - 1)


# --------------------------------------------------------------------------------------------------
# Code holen
# --------------------------------------------------------------------------------------------------
def code_from_project(proj):
    """GameProject mit dump.bin -> Code-Sicht (dict wie proj.code())."""
    if proj is None or getattr(proj, "dm", None) is None:
        raise CaveError("kein dump.bin geladen")
    return proj.code()


def code_from_console(client, base, progress=None, limit=LIVE_MAX, chunk=LIVE_CHUNK):
    """Code-Bereich des Spiels live von der Konsole lesen (wenn kein dump.bin da ist).
    -> dict(buf, lo, hi, base_va, dump_rva, range) wie GameProject.code()."""
    maps = sorted((m[0], m[1], m[2]) for m in client.get_maps())
    exec_maps = [m for m in maps if m[2] & CODE_PROT]
    first = next((m for m in exec_maps if m[0] <= base < m[1]), None) or next((m for m in exec_maps if m[0] >= base), None)
    if first is None:
        raise CaveError("Kein ausführbarer Speicherbereich ab der Image-Basis gefunden (Image-Base im Hauptfenster prüfen)")
    start, end = first[0], first[1]
    for m in exec_maps:                          # unmittelbar anschliessende ausfuehrbare Bereiche mitnehmen
        if m[0] == end:
            end = m[1]
    end = min(end, start + limit)
    buf = bytearray()
    ok_any = False
    addr = start
    while addr < end:
        n = min(chunk, end - addr)
        try:
            buf += client.read_memory(addr, n)
            ok_any = True
        except Exception:  # noqa: BLE001 - einzelne unlesbare Seiten: mit Nullen auffuellen, Positionen bleiben stimmig
            buf += b"\x00" * n
        addr += n
        if progress:
            progress(addr - start, end - start)
    if not ok_any:
        raise CaveError("Code konnte nicht von der Konsole gelesen werden")
    data = bytes(buf)
    return {"buf": data, "lo": 0, "hi": len(data), "base_va": start, "dump_rva": start - base, "range": (0, len(data))}


# --------------------------------------------------------------------------------------------------
# Treffer suchen und bewerten
# --------------------------------------------------------------------------------------------------
class Option:
    """Ein Treffer plus die Caves, die sich dafuer bauen lassen."""

    def __init__(self, hit, modes):
        self.hit = hit
        self.modes = modes                        # {mode: (ok, grund)}

    @property
    def possible(self):
        return [m for m in MODES if self.modes[m][0]]

    def best(self, prefer):
        for m in prefer:
            if self.modes.get(m, (False, ""))[0]:
                return m
        return None


def modes_for(e, h):
    """{mode: (ok, grund)} fuer einen Treffer und einen Eintrag."""
    out = {}
    is_value = e.kind == "value"
    target = getattr(e, "target", None)
    wrapped = bool(getattr(target, "parent", "")) or bool(getattr(target, "is_fixed", False))
    # keep: nur Zahlen, nur Store aus Register/xmm
    if not is_value:
        out["keep"] = (False, "Schalter haben keinen Wert, der 'nicht sinken' kann")
    else:
        out["keep"] = U.can_cave(h)
    # force
    if wrapped:
        out["force"] = (False, "Struct-/Festkomma-Wert (die Rohbits sind unbekannt) - 'kann nicht sinken' nehmen")
    elif e.bit >= 0:
        out["force"] = (False, "Bit-Feld: ein Byte-Store würde die Nachbar-Bits überschreiben")
    else:
        ok, why, _size = U.can_force(h)
        out["force"] = (ok, why)
    # nop
    i = h.ins
    out["nop"] = (True, "") if h.writes and i.size >= 1 else (False, "schreibt nicht")
    return out


def find_options(menu, e, code, dis, progress=None, limit=60):
    """Alle schreibenden Instruktionen zu diesem Eintrag -> [Option] (beste zuerst: baubar vor nicht baubar)."""
    off = entry_offset(menu, e)
    sdk = getattr(menu, "sdk", None)
    class_offs = set()
    if sdk is not None:
        try:
            class_offs = {m.offset for m in sdk.all_members(e.cls) if m.offset >= MIN_OFFSET}
        except Exception:  # noqa: BLE001
            class_offs = set()
    tag = f"{e.cls}.{e.member}"
    hits = U.scan(code["buf"], {off: [tag]}, dis, class_offs, base_va=code["base_va"], dump_rva=code["dump_rva"],
                  include_reads=False, progress=progress, code_range=code["range"])
    opts = [Option(h, modes_for(e, h)) for h in hits]
    opts.sort(key=lambda o: (-(1 if o.modes["keep"][0] or o.modes["force"][0] else 0), -o.hit.score))
    return opts[:limit]


def default_modes(e):
    """Reihenfolge, in der die passende Cave gewaehlt wird (Zahl: nicht sinken; Schalter: festschreiben)."""
    return ("keep", "force") if e.kind == "value" else ("force",)


def pick_best(e, opts):
    """-> (Option, mode) oder (None, None)."""
    for o in opts:
        m = o.best(default_modes(e))
        if m:
            return o, m
    return None, None


# --------------------------------------------------------------------------------------------------
# Patch bauen und speichern
# --------------------------------------------------------------------------------------------------
def build_patch(e, opt, mode, code, dis, value=None, author="ReaperPy Cheat-Menü", with_aob=True, log=print):
    """-> Patch-Dict (.reapproj-Inhalt).  Wirft CaveError, wenn der Modus fuer den Treffer nicht geht."""
    if mode not in MODES:
        raise CaveError(f"unbekannter Modus: {mode}")
    ok, why = opt.modes[mode]
    if not ok:
        raise CaveError(f"{MODE_TEXT[mode]}: {why}")
    h, dump = opt.hit, code["buf"]
    aob = None
    if with_aob:
        try:
            aob, _n = U.make_aob(dump, dis, h, code["base_va"], code_range=code["range"])
        except Exception as ex:  # noqa: BLE001
            log(f"AOB für {h.rva:#x} fehlgeschlagen: {ex}")
        if not aob:
            log(f"{h.rva:#x}: keine eindeutige Signatur im Code - der Patch nutzt die feste Adresse")
    name = f"{e.label} - {mode_text(mode)}"
    try:
        if mode == "keep":
            return U.keep_cave_patch(dump, h, aob, name=name, author=author)
        if mode == "nop":
            return U.nop_patch(dump, h, aob, name=name, author=author)
        _ok, _why, size = U.can_force(h)
        bits = value_bits(e.type, entry_value(e, value), size)
        text = entry_value(e, value)
        return U.force_cave_patch(dump, h, bits, aob, name=f"{e.label} = {text} (Cave)", author=author)
    except ValueError as ex:
        raise CaveError(str(ex)) from ex


def save_patch(out_dir, patch):
    """.reapproj schreiben (gleiche Namensregeln wie ue_auto.write_patches) -> Dateiname."""
    os.makedirs(out_dir, exist_ok=True)
    base = ue_auto.safe_name(patch["name"])
    fn, k = base + ".reapproj", 2
    while os.path.exists(os.path.join(out_dir, fn)):
        fn, k = f"{base} ({k}).reapproj", k + 1
    with open(os.path.join(out_dir, fn), "w", encoding="utf-8", newline="\n") as f:
        json.dump(patch, f, indent=2, ensure_ascii=False)
    return fn


def describe(opt):
    """Kurzbeschreibung eines Treffers fuer Listen: 'mov dword ptr [rbx+0x348], eax'."""
    h = opt.hit
    note = []
    if h.dec_hint:
        note.append("SUB davor")
    if h.ambiguity > 12:
        note.append(f"mehrdeutig ({h.ambiguity})")
    return h.ins.text, ", ".join(note)


