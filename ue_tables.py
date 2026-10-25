"""ue_tables.py - DataTables im laufenden Spiel lesen (Zeilennamen + 8-Byte-FNames), fuer JEDES Unreal-Spiel (UE 4.23+/5).

Die RowMap (TMap<FName, uint8*>) ist im SDK nicht deklariert: der Offset wird gesucht - TArray-Header (ptr, num, max),
dessen erstes Element (FName, gueltiger Zeiger) einen lesbaren Namen hat.  Nur Lesen.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

U32 = struct.Struct("<I")
U64 = struct.Struct("<Q")


def valid_ptr(p):
    return 0x10000 <= p < 0x0000_8000_0000_0000 and p % 8 == 0


ROW_STRIDE = 24  # TSetElement<TTuple<FName, uint8*>>: FName(8) + Zeiger(8) + HashNext(4) + HashIdx(4)


@dataclass
class TableRow:
    name: str
    fname: bytes   # 8 Byte (Index+Number) - direkt als 'hex:..' in Funktionsaufrufen nutzbar
    row_ptr: int

    @property
    def hex(self):
        return "hex:" + self.fname.hex()


def read_datatable_rows(read, fname_str, table_obj, scan_from=0x28, scan_to=0x280, limit=100000):
    """Liest die RowMap einer UDataTable.  Die Map ist im SDK nicht deklariert -> der Offset wird gesucht:
    TArray-Header (ptr, num, max), dessen erstes Element (FName, gueltiger Zeiger) einen lesbaren Namen hat."""
    blob = read(table_obj, scan_to + 16)
    for off in range(scan_from, scan_to, 8):
        ptr = U64.unpack_from(blob, off)[0]
        num, mx = struct.unpack_from("<ii", blob, off + 8)
        if not valid_ptr(ptr) or not (0 < num <= limit) or mx < num:
            continue
        try:
            first = read(ptr, ROW_STRIDE)
            idx, number = U32.unpack_from(first, 0)[0], U32.unpack_from(first, 4)[0]
            if not valid_ptr(U64.unpack_from(first, 8)[0]):
                continue
            nm = fname_str(idx, number)
            if not nm or nm.startswith("<name") or len(nm) > 120:
                continue
            raw = read(ptr, num * ROW_STRIDE)
        except Exception:
            continue
        rows = []
        for i in range(num):
            e = raw[i * ROW_STRIDE:(i + 1) * ROW_STRIDE]
            ix, nb = U32.unpack_from(e, 0)[0], U32.unpack_from(e, 4)[0]
            rp = U64.unpack_from(e, 8)[0]
            if not valid_ptr(rp):
                continue
            try:
                name = fname_str(ix, nb)
            except Exception:
                continue
            if not name or name.startswith("<name"):
                continue
            rows.append(TableRow(name, bytes(e[:8]), rp))
        if rows:
            return rows
    return []
