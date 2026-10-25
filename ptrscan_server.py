"""ptrscan_server.py - Pointer-Scan, bei dem die Konsole das Suchen uebernimmt.

Rueckwaerts-Breitensuche: Ebene 1 fragt "welche Speicherstellen zeigen auf [Ziel-max_off, Ziel]?",
Ebene 2 "welche zeigen auf diese Stellen?" usw., bis die Stelle in einem statischen Bereich liegt
(Modul-Daten, ueberlebt Neustart/Level).  Die Konsole liefert pro Ebene nur (Stelle, Wert)-Paare;
das spart gegenueber dem Herunterladen des ganzen Heaps sehr viel Zeit.

Kette (static, [o1, .., on]) aufloesen:   p = read64(static); p += o1; p = read64(p); p += o2; ...
Der Wert nach dem letzten Offset ist die Zieladresse.

Verfahren und ptrscan-Protokoll angelehnt an PS5Debug-studio (alfizari, Apache-2.0); die
Ketten-Rekonstruktion hier ist eigene Umsetzung.
"""
import bisect


class Chain:
    __slots__ = ("static", "offsets")

    def __init__(self, static, offsets):
        self.static, self.offsets = static, offsets

    def depth(self):
        return len(self.offsets)

    def text(self, module=None):
        base = f"{module[0]}+{self.static - module[1]:#x}" if module else f"{self.static:#x}"
        return f"[{base}]" + "".join(f" -> +{o:#x}" for o in self.offsets)

    def __repr__(self):
        return f"Chain({self.text()})"

    def __eq__(self, o):
        return isinstance(o, Chain) and (self.static, self.offsets) == (o.static, o.offsets)

    def __hash__(self):
        return hash((self.static, tuple(self.offsets)))


def resolve(read_u64, chain):
    """Kette aktuell auswerten -> Zieladresse oder None."""
    try:
        p = read_u64(chain.static)
        for i, o in enumerate(chain.offsets):
            p += o
            if i < len(chain.offsets) - 1:
                p = read_u64(p)
        return p
    except Exception:
        return None


def in_ranges(addr, ranges):
    return any(a <= addr < b for a, b in ranges)


def scan(level_fn, target, segments, static_ranges, max_off=0x400, max_depth=4,
         max_frontier=200000, max_chains=5000, on_level=None, should_stop=lambda: False):
    """level_fn(frontier_sorted) -> [(slot, value)] (ps5_more.ptrscan_level / Simulation).
    segments: [(addr,len)] zu durchsuchen; static_ranges: [(start,end)] gelten als Wurzel.
    -> (ketten, info)."""
    levels = []                   # je Ebene: {slot: [(frontier_addr, offset)]}
    frontier = [target]
    roots = []                    # (ebene, slot)
    capped = False
    for depth in range(1, max_depth + 1):
        if should_stop():
            break
        fr = sorted(set(frontier))
        hits = level_fn(fr)
        edges = {}
        for slot, value in hits:
            i = bisect.bisect_left(fr, value)
            while i < len(fr) and fr[i] - value <= max_off:
                edges.setdefault(slot, []).append((fr[i], fr[i] - value))
                i += 1
        levels.append(edges)
        nxt = []
        for slot in edges:
            if in_ranges(slot, static_ranges):
                roots.append((depth, slot))
            else:
                nxt.append(slot)
        if on_level:
            on_level(depth, len(edges), len(roots))
        if len(nxt) > max_frontier:
            nxt, capped = nxt[:max_frontier], True
        if not nxt:
            break
        frontier = nxt

    chains, seen = [], set()

    # Rekonstruktion: von der Wurzel (Ebene d, slot) abwaerts bis zum Ziel
    def descend(depth, slot, offs, static):
        if len(chains) >= max_chains:
            return
        for f, off in levels[depth - 1].get(slot, ()):
            o2 = offs + [off]
            if depth == 1:                       # f == target
                c = Chain(static, o2)
                if c not in seen:
                    seen.add(c)
                    chains.append(c)
            else:
                descend(depth - 1, f, o2, static)

    for depth, slot in roots:
        descend(depth, slot, [], slot)
        if len(chains) >= max_chains:
            break
    chains.sort(key=lambda c: (c.depth(), sum(c.offsets)))
    return chains, {"levels": len(levels), "roots": len(roots), "capped": capped or len(chains) >= max_chains}


def server_level_fn(client, segments, max_off, on_progress=None):
    import ps5_more
    def fn(frontier):
        hits, _scanned, status = ps5_more.ptrscan_level(client, segments, frontier, max_off,
                                                        on_progress=on_progress)
        if status == 2:
            raise RuntimeError("Konsole: Treffer-Limit erreicht - max. Offset verkleinern oder Tiefe senken")
        return hits
    return fn


class Simulation:
    """Konsolen-Ersatz fuer Tests: Speicher = {adresse: u64}."""
    def __init__(self, mem, segments, max_off):
        self.mem, self.segments, self.max_off = mem, segments, max_off

    def __call__(self, frontier):
        out = []
        for slot, v in self.mem.items():
            if any(a <= slot < a + n for a, n in self.segments):
                i = bisect.bisect_left(frontier, v)
                if i < len(frontier) and frontier[i] - v <= self.max_off:
                    out.append((slot, v))
        return out
