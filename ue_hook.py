"""ue_hook.py - ProcessEvent-Haken im vtable (Slots finden); gemeinsam fuer Cave-Trainer und Entdecker.  Nur Lesen."""
import struct


def find_slots(read, objs, pe_index, pe_addr):
    """vtable-Slots von ProcessEvent der Objekte `objs` -> (slots, notizen).  Nur Slots, die wirklich auf `pe_addr`
    zeigen (sonst waere die Hoehle fuer sie das falsche `orig`).  Jeder vtable nur einmal."""
    slots, notes, seen = [], [], set()
    for obj in objs:
        try:
            vt = struct.unpack("<Q", read(obj, 8))[0]
            if vt < 0x10000 or vt in seen:
                continue
            seen.add(vt)
            slot = vt + 8 * pe_index
            val = struct.unpack("<Q", read(slot, 8))[0]
        except Exception as e:  # noqa: BLE001
            notes.append(f"{obj:#x}: vtable nicht lesbar ({e})")
            continue
        if val == pe_addr:
            slots.append(slot)
        else:
            notes.append(f"vtable {vt:#x}: Slot {pe_index} zeigt auf {val:#x}, nicht auf ProcessEvent - ausgelassen")
    return slots, notes
