"""hit_context.py - Disassembly rund um einen Debugger-Treffer (ohne Oberflaeche, damit es testbar bleibt).

Warum: Ein Treffer meldet nur RIP.  Bei einem Schreib-/Lese-Watchpoint ist das aber der Befehl HINTER dem Zugriff
(die CPU meldet erst, wenn der Befehl fertig ist).  Wer nur die RIP-Adresse sieht, schaut auf den falschen Befehl.
Hier wird der Zusammenhang gebaut: ein paar Befehle davor, der Befehl bei RIP und ein paar danach - und es wird
markiert, welcher Befehl der Schreiber ist (assist.find_writer) und wo RIP steht.

build_context(read, hit, wp) -> dict:
    lines     Befehle (addr, size, bytes, mnemonic, op_str) in Adressreihenfolge
    marks     {adresse: "writer" | "rip"}
    focus     Adresse, die in der Ansicht in die Mitte soll (Schreiber, sonst RIP)
    writer    Zeile des Schreibers oder None;  how = "address" | "writes" | "guess" | None
    rip       Adresse, an der die CPU steht
    headline  ein Satz in Klartext, was hier passiert ist
"""
import assist as A
import asm_tools as AT

try:                                    # Texte im EN-Modus uebersetzen; ohne Oberflaechen-Umgebung bleibt es Deutsch
    from tools_i18n import translate as _tr
except Exception:  # noqa: BLE001
    def _tr(text):
        return text

BEFORE_BYTES = 64        # so weit zurueck wird gelesen
BEFORE_INSNS = 12        # und so viele Befehle davor werden gezeigt
AFTER_INSNS = 12         # Befehle ab RIP (einschliesslich RIP)
SYNC_SKIP = 2            # die ersten Befehle einer Rueckwaerts-Kette koennen noch "schief" sein (x86 hat keine feste Laenge)


def _ending_at(data, rip, k, disasm):
    """Befehlskette, die bei rip-k beginnt, nur gueltige Befehle enthaelt und genau auf rip endet (sonst None)."""
    chunk = bytes(data[-k:])
    try:
        lines = disasm(chunk, rip - k)
    except Exception:  # noqa: BLE001
        return None
    pos = rip - k
    for ln in lines:
        if ln["mnemonic"] == "db" or ln["addr"] != pos:
            return None
        pos += ln["size"]
    return lines if pos == rip and lines else None


def lines_before(back, rip, disasm=None):
    """Die Befehle direkt vor `rip`.  `back` = die Bytes unmittelbar davor.

    x86 hat Befehle verschiedener Laenge, rueckwaerts ist die Startstelle also nicht eindeutig.  Es wird von hinten nach
    vorn jeder Start probiert; die laengste Kette, die sauber auf rip endet, gewinnt (x86 faengt sich nach wenigen
    Befehlen von selbst, die allerersten werden deshalb weggelassen)."""
    disasm = disasm or AT.disassemble_lines
    for k in range(len(back), 0, -1):
        chain = _ending_at(back, rip, k, disasm)
        if chain:
            if len(chain) > SYNC_SKIP + 3:
                chain = chain[SYNC_SKIP:]
            return chain[-BEFORE_INSNS:]
    return []


def _read_best(read, addr, sizes):
    """Liest `addr` mit der ersten Groesse aus `sizes`, die klappt (Seitengrenzen); sonst b''."""
    for n in sizes:
        if n <= 0:
            return b""
        try:
            data = read(addr, n)
            if data:
                return bytes(data)
        except Exception:  # noqa: BLE001
            continue
    return b""


def _read_before(read, rip, sizes):
    for n in sizes:
        if n <= 0:
            return b""
        try:
            data = read(rip - n, n)
            if data:
                return bytes(data)
        except Exception:  # noqa: BLE001
            continue
    return b""


def build_context(read, hit, wp=None, disasm=None):
    """read(addr, n) -> bytes.  hit = Treffer-Paket des Debuggers.

    wp = None oder {'addr', 'size', 'access'} des ausgeloesten Watchpoints; access: 'write' | 'rw' | 'exec'."""
    disasm = disasm or AT.disassemble_lines
    regs = hit["regs"]
    rip = regs["rip"]
    kind = hit.get("kind")

    fwd_raw = _read_best(read, rip, (AFTER_INSNS * 15 + 16, 128, 64, 32, 16))
    if not fwd_raw:
        raise RuntimeError(_tr("Speicher bei RIP {rip} nicht lesbar").format(rip=f"{rip:#x}"))
    after = disasm(fwd_raw, rip, AFTER_INSNS)
    back = _read_before(read, rip, (BEFORE_BYTES, 32, 16))
    before = lines_before(back, rip, disasm)

    data_trap = kind == "WP" and wp is not None and wp.get("access") != "exec"
    writer, how = None, None
    if data_trap:
        w = A.find_writer(rip, back[-16:], regs, wp["addr"], wp["size"], disasm) if back else None
        if w:
            writer, how = w["addr"], w["how"]
        elif before:
            writer, how = before[-1]["addr"], "guess"

    lines = before + after
    marks = {rip: "rip"}
    writer_line = None
    if writer is not None:
        marks[writer] = "writer"
        writer_line = next((ln for ln in lines if ln["addr"] == writer), None)

    return {"lines": lines, "marks": marks, "focus": writer if writer_line else rip,
            "writer": writer_line, "how": how, "rip": rip,
            "headline": _headline(kind, wp, rip, writer_line, how)}


def _headline(kind, wp, rip, writer, how):
    r = f"{rip:#x}"
    if kind == "WP" and wp is not None:
        what = {"write": _tr("Schreibzugriff"), "rw": _tr("Zugriff (lesen oder schreiben)")}.get(wp.get("access"))
        if what is None:                                                    # Ausfuehrungs-Watchpoint
            return _tr("Ausführung bei {rip} - dieser Befehl wurde noch nicht ausgeführt.").format(rip=r)
        if writer is not None:
            return _tr("{what} auf {watch} durch den Befehl bei {writer}{vague}. RIP steht schon dahinter ({rip}) - "
                       "der Schreiber ist der Befehl davor.").format(
                what=what, watch=f"{wp['addr']:#x}", writer=f"{writer['addr']:#x}", rip=r,
                vague=_tr(" (vermutlich)") if how == "guess" else "")
        return _tr("{what} auf {watch}. RIP steht schon hinter dem Zugriff ({rip}), der Befehl davor war es.").format(
            what=what, watch=f"{wp['addr']:#x}", rip=r)
    if kind == "BP":
        return _tr("Breakpoint bei {rip} - dieser Befehl wurde noch nicht ausgeführt.").format(rip=r)
    if kind == "STEP":
        return _tr("Einzelschritt - der nächste Befehl ist {rip}.").format(rip=r)
    return _tr("Angehalten bei {rip}.").format(rip=r)
