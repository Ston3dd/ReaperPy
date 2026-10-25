"""icon_art.py - das ReaperPy-Icon, rein in Python gerendert (kein PIL noetig): PNG + Windows-ICO.

Motiv: dunkles Rundquadrat (Nachtblau -> Violett), leuchtender Ring (Tuerkis -> Blau) mit drei Knoten,
darin ein "R" und eine Sense-Klinge.  `python icon_art.py` schreibt assets/reaperpy.png (256) und assets/reaperpy.ico
und erneuert icon_data.py (eingebettet, damit das Programm ohne Zusatzdateien ein Icon hat).
"""
import base64
import math
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))


def _sdf_round_rect(x, y, hw, hh, r):
    qx, qy = abs(x) - hw + r, abs(y) - hh + r
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def _sdf_capsule(x, y, ax, ay, bx, by, r):
    pax, pay, bax, bay = x - ax, y - ay, bx - ax, by - ay
    h = max(0.0, min(1.0, (pax * bax + pay * bay) / (bax * bax + bay * bay)))
    return math.hypot(pax - bax * h, pay - bay * h) - r


def _mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(c1[i] + (c2[i] - c1[i]) * t for i in range(3))


def _over(dst, src, a):
    """src (r,g,b) mit Deckkraft a ueber dst (r,g,b,A) legen"""
    a = max(0.0, min(1.0, a))
    if a <= 0:
        return dst
    da = dst[3]
    oa = a + da * (1 - a)
    if oa <= 0:
        return dst
    return tuple((src[i] * a + dst[i] * da * (1 - a)) / oa for i in range(3)) + (oa,)


# Bogenstuecke des "R"-Bauches (Halbkreis) als Kapsel-Kette
def _r_segments():
    cx, cy, rad = -0.015, -0.085, 0.115
    pts = [(cx + rad * math.sin(math.radians(a)), cy - rad * math.cos(math.radians(a))) for a in range(0, 181, 15)]
    return list(zip(pts, pts[1:]))


R_SEGS = _r_segments()
STEM = (-0.125, -0.205, -0.125, 0.205)
LEG = (-0.02, 0.035, 0.145, 0.205)


def _sdf_tri(x, y, a, b, c):
    def side(p, q):
        return (x - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (y - q[1])
    d1, d2, d3 = side(a, b), side(b, c), side(c, a)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    inside = not (neg and pos)
    d = min(_sdf_capsule(x, y, *a, *b, 0), _sdf_capsule(x, y, *b, *c, 0), _sdf_capsule(x, y, *c, *a, 0))
    return -d if inside else d


def pixel(u, v):
    """u,v in [-0.5,0.5] -> (r,g,b,a) 0..255-Skala als Floats"""
    out = (0.0, 0.0, 0.0, 0.0)
    d = _sdf_round_rect(u, v, 0.47, 0.47, 0.20)
    if d > 0.004:
        return out
    t = (u + v) / 2 + 0.5
    bg = _mix((10, 14, 32), (62, 24, 112), t)
    out = bg + (1.0,)
    # Lichtfleck oben links
    out = _over(out, (90, 130, 255), 0.22 * math.exp(-((u + 0.22) ** 2 + (v + 0.26) ** 2) / 0.05))
    # Rand-Glanz
    out = _over(out, (150, 190, 255), 0.55 * math.exp(-max(0.0, -d) / 0.012) * (0.5 + 0.5 * (-v - u)))
    # Sensenklinge: Sichel ausserhalb des Rings (Kreis A minus Kreis B), nur oben rechts
    ang = math.degrees(math.atan2(v, u))
    if -85 <= ang <= 5:
        da = math.hypot(u, v) - 0.445
        db = math.hypot(u + 0.06, v - 0.04) - 0.41
        bd = max(da, -db)
        edge = 1.0 if bd < 0 else max(0.0, 1.0 - bd / 0.004)
        fade = min(1.0, (ang + 85) / 18.0, (5 - ang) / 10.0)
        out = _over(out, (235, 242, 255), edge * max(0.0, fade))
    # Ring + Glow
    rd = abs(math.hypot(u, v) - 0.345) - 0.026
    ring_c = _mix((34, 230, 196), (59, 130, 246), (v + 0.4) / 0.8)
    out = _over(out, ring_c, 0.35 * math.exp(-max(0.0, rd) / 0.035))
    out = _over(out, ring_c, 1.0 if rd < 0 else max(0.0, 1.0 - rd / 0.004))
    # Knoten auf dem Ring
    for ang in (30, 150, 270):
        nx, ny = 0.345 * math.cos(math.radians(ang)), 0.345 * math.sin(math.radians(ang))
        nd = math.hypot(u - nx, v - ny) - 0.032
        out = _over(out, (230, 255, 250), 1.0 if nd < 0 else max(0.0, 1.0 - nd / 0.004))
        out = _over(out, ring_c, 0.45 * math.exp(-max(0.0, nd) / 0.03))
    # "R"
    w = 0.036
    dr = min(_sdf_capsule(u, v, *STEM[:2], *STEM[2:], w), _sdf_capsule(u, v, *LEG[:2], *LEG[2:], w),
             *[_sdf_capsule(u, v, a[0], a[1], b[0], b[1], w) for a, b in R_SEGS],
             _sdf_capsule(u, v, STEM[0], STEM[1], R_SEGS[0][0][0], R_SEGS[0][0][1], w),
             _sdf_capsule(u, v, STEM[0], 0.03, R_SEGS[-1][1][0], R_SEGS[-1][1][1], w))
    rc = _mix((255, 255, 255), (190, 215, 255), (v + 0.2) / 0.4)
    out = _over(out, (0, 0, 0), 0.30 * math.exp(-max(0.0, dr - 0.01) / 0.02) * 0.6)
    out = _over(out, rc, 1.0 if dr < 0 else max(0.0, 1.0 - dr / 0.004))
    return out


def render(size=256, ss=2):
    """RGBA-Bytes (size*size*4), ss x ss Supersampling"""
    rows = []
    inv = 1.0 / (size * ss)
    for py in range(size):
        row = bytearray()
        for px in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    u = ((px * ss + sx + 0.5) * inv) - 0.5
                    v = ((py * ss + sy + 0.5) * inv) - 0.5
                    r, g, b, a = pixel(u, v)
                    acc[0] += r * a
                    acc[1] += g * a
                    acc[2] += b * a
                    acc[3] += a
            n = ss * ss
            a = acc[3] / n
            if a > 0:
                row += bytes((int(min(255, acc[0] / acc[3])), int(min(255, acc[1] / acc[3])), int(min(255, acc[2] / acc[3])),
                              int(min(255, a * 255 + 0.5))))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))
    return rows


def downscale(rows, size):
    """Box-Filter auf size x size (Premultiplied) - fuer die kleinen ICO-Groessen"""
    src = len(rows)
    k = src // size
    out = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            r = g = b = a = 0.0
            for dy in range(k):
                line = rows[y * k + dy]
                for dx in range(k):
                    i = (x * k + dx) * 4
                    al = line[i + 3] / 255
                    r += line[i] * al
                    g += line[i + 1] * al
                    b += line[i + 2] * al
                    a += al
            n = k * k
            if a > 0:
                row += bytes((int(r / a), int(g / a), int(b / a), int(min(255, a / n * 255 + 0.5))))
            else:
                row += b"\x00\x00\x00\x00"
        out.append(bytes(row))
    return out


def png_bytes(rows):
    h, w = len(rows), len(rows[0]) // 4

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico_bytes(pngs):
    """pngs: {groesse: png-bytes} -> ICO mit PNG-Eintraegen (Windows Vista+)"""
    sizes = sorted(pngs)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    entries, data = b"", b""
    for s in sizes:
        p = pngs[s]
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(p), off + len(data))
        data += p
    return head + entries + data


def build_all(out_dir=None):
    out_dir = out_dir or os.path.join(HERE, "assets")
    os.makedirs(out_dir, exist_ok=True)
    big = render(256, 2)
    pngs = {256: png_bytes(big)}
    for s in (128, 64, 48, 32, 16):
        pngs[s] = png_bytes(downscale(big, s))
    with open(os.path.join(out_dir, "reaperpy.png"), "wb") as f:
        f.write(pngs[256])
    with open(os.path.join(out_dir, "reaperpy.ico"), "wb") as f:
        f.write(ico_bytes(pngs))
    with open(os.path.join(HERE, "icon_data.py"), "w", encoding="utf-8") as f:
        f.write('"""Eingebettetes ReaperPy-Icon (erzeugt von icon_art.py) - PNG, base64."""\n')
        f.write(f'PNG_256 = "{base64.b64encode(pngs[256]).decode()}"\n')
        f.write(f'PNG_64 = "{base64.b64encode(pngs[64]).decode()}"\n')
    return pngs


if __name__ == "__main__":
    p = build_all()
    print({k: len(v) for k, v in p.items()})
