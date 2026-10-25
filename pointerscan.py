"""pointerscan.py – Pointer-Scanner: stabile Pfade zu Adressen finden, die sich bei
jedem Spielstart ändern.

Verfahren
  1. Zeigerkarte: ein schneller Turbo-Scan  (UInt64 zwischen Min..Max der Speicher-
     karte)  liefert alle 8-Byte-Werte, die wie Zeiger aussehen, samt Adresse.
  2. Rückwärtssuche: ab der Zieladresse werden Ebene für Ebene alle Zeiger gesucht,
     die höchstens `max_off` vor dem Ziel liegen.  Endet eine Kette in einer
     statischen Region (z.B. .data/.bss der eboot.bin) ist das ein stabiler Pfad.
  3. Prüfen: Pfade nach Neustart gegen die neue Zieladresse auflösen - nur die
     überlebenden sind brauchbar.

Pfad-Auflösung:   cur = Basis + root_offset
                  für jedes off in offsets:  cur = lese_u64(cur) + off
                  -> cur ist die Zieladresse
"""
import json
import struct
from array import array
from bisect import bisect_left, bisect_right

import scanner as SC


class PointerError(RuntimeError):
    pass


class PointerMap:
    def __init__(self, addrs, vals, regions_ok):
        n = len(addrs)
        order = sorted(range(n), key=vals.__getitem__)
        self.svals = array("Q", (vals[i] for i in order))
        self.saddr = array("Q", (addrs[i] for i in order))
        self.count = n
        self.regions_ok = regions_ok

    # ------------------------------------------------------------------
    def find_paths(self, target, static_ranges, max_depth=4, max_off=0x400,
                   max_results=2000, max_nodes=400000, per_node=48, progress=None, cancelled=None):
        """Gibt (pfade, abgeschnitten) zurück.  pfad = (root_adresse, (off1, off2, ...))."""
        starts = [s for s, _ in static_ranges]
        ends = [e for _, e in static_ranges]

        def is_static(a):
            i = bisect_right(starts, a) - 1
            return i >= 0 and a < ends[i]

        sv, sa = self.svals, self.saddr
        results = []
        seen = {target}
        frontier = [(target, ())]
        truncated = False
        for depth in range(1, max_depth + 1):
            nxt = []
            for idx, (x, chain) in enumerate(frontier):
                if cancelled and cancelled():
                    raise SC.Cancelled("abgebrochen")
                i = bisect_left(sv, max(0, x - max_off))
                j = bisect_right(sv, x)
                if j - i > per_node:            # sehr "beliebte" Ziele -> nur die nächsten
                    i = j - per_node
                    truncated = True
                for k in range(i, j):
                    a = sa[k]
                    new_chain = (x - sv[k],) + chain
                    if is_static(a):
                        results.append((a, new_chain))
                        if len(results) >= max_results * 4:
                            break
                    elif a not in seen:
                        seen.add(a)
                        nxt.append((a, new_chain))
                if idx % 2000 == 0 and progress:
                    progress(depth, idx, len(frontier), len(results))
            if len(nxt) > max_nodes:
                nxt = nxt[:max_nodes]
                truncated = True
            frontier = nxt
            if progress:
                progress(depth, len(frontier), len(frontier), len(results))
            if not frontier:
                break
        results.sort(key=lambda r: (len(r[1]), sum(r[1])))
        if len(results) > max_results:
            results = results[:max_results]
            truncated = True
        return results, truncated


# ------------------------------------------------------------------
# Karte bauen
# ------------------------------------------------------------------
def build_map(scanner, regions, maps_range, progress=None, cap=8_000_000):
    """Zeigerkarte per Turbo-Scan. `regions`: zu durchsuchende (start,end)."""
    lo, hi = maps_range
    n = scanner.first_scan("UInt64", "Zwischen", str(lo), str(hi), regions, {}, progress)
    if n > cap:
        raise PointerError(f"{n} Zeiger-Kandidaten (> {cap}) - Bereich einschränken "
                           f"(z.B. nur Heap/.data) oder Range verkleinern")
    addrs, vals = scanner.dump_u64(progress=progress, cap=cap)
    # nur Werte behalten, die in einer bekannten Region liegen
    ok = sorted(regions_union(scanner.client.get_maps()))
    starts = [s for s, _ in ok]
    keepA, keepV = array("Q"), array("Q")
    for a, v in zip(addrs, vals):
        i = bisect_right(starts, v) - 1
        if i >= 0 and v < ok[i][1]:
            keepA.append(a)
            keepV.append(v)
    return PointerMap(keepA, keepV, ok)


def regions_union(maps):
    return [(s, e) for s, e, p in maps if p & 1]


def static_ranges(named_maps, name_filter, image_base):
    """Statische Bereiche: schreibbare Regionen, deren Name den Filter enthält.
    Ohne Treffer: schreibbare Regionen ab image_base innerhalb 256 MB."""
    flt = [f.strip().lower() for f in name_filter.split(",") if f.strip()]
    out = []
    for m in named_maps:
        if not (m["prot"] & 2):
            continue
        if flt and any(f in m["name"].lower() for f in flt):
            out.append((m["start"], m["end"]))
    if not out:
        out = [(m["start"], m["end"]) for m in named_maps
               if (m["prot"] & 2) and image_base <= m["start"] < image_base + 0x10000000]
    return sorted(out)


# ------------------------------------------------------------------
# Auflösen / Prüfen
# ------------------------------------------------------------------
def resolve(client, root, offsets):
    """Pfad ab absoluter Root-Adresse auflösen. Rückgabe: Zieladresse oder None."""
    cur = root
    for off in offsets:
        try:
            data = client.read_memory(cur, 8)
        except Exception:
            return None
        if data is None or len(data) < 8:
            return None
        cur = struct.unpack("<Q", bytes(data))[0] + off
        if cur < 0x1000 or cur >= (1 << 47):
            return None
    return cur


def verify(client, paths, expect, image_base, progress=None):
    """Behält Pfade [(root_off, offsets)], die auf `expect` auflösen."""
    keep = []
    for i, (root_off, offs) in enumerate(paths):
        if resolve(client, image_base + root_off, offs) == expect:
            keep.append((root_off, offs))
        if progress and i % 50 == 0:
            progress(i / max(len(paths), 1), f"Prüfe {i}/{len(paths)}")
    return keep


def fmt_path(root_off, offs, module="base"):
    return f"{module}+{root_off:X}  →  " + " → ".join(f"+{o:X}" if o >= 0 else f"-{-o:X}" for o in offs)


def save_paths(path, paths, target_info=None):
    data = {"target": target_info or {},
            "paths": [{"root": r, "offsets": list(o)} for r, o in paths]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)


def load_paths(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return [(int(p["root"]), tuple(int(x) for x in p["offsets"])) for p in d.get("paths", [])], d.get("target", {})
