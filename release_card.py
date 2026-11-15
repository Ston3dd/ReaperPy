#!/usr/bin/env python3
"""release_card.py - ReaperPy-Release-Karte (1920x1080 PNG): dunkel-mystisches 'Reaper'-Design.

Wird beim Export (GoldHEN / etaHEN / SHN / MC4) gleich mit erzeugt: Titel, Titel-ID, Version, alle Schalter und die Credits
stehen schon im Export - dazu kommt nur das Cover.  Es wird in der Bibliothek gesucht (PPSA12345.png, PPSA12345_icon0.jpg ...);
ohne Cover zeichnet die Karte ein Portal in der Farbe des Spiels.

Aufbau: das Cover steht als Portal (Torbogen) rechts, verschwommen und abgedunkelt liegt es zugleich als Stimmung hinter allem.
Die Akzentfarbe wird aus dem Cover gezogen (jede Karte bekommt so die Farben ihres Spiels), Nebel steigt vom Boden (Muster je
Spiel-ID anders), die Cheats stehen wie in einem Grimoire mit römischen Nummern, ein Siegel-Ring trägt die Anzahl.

Von Hand (ohne ReaperPy):
    python release_card.py --json PPSA16096_01.003.000.json --art cover.png --author "DeinName"
    python release_card.py --patches <Ordner> --title "Spielname" --id PPSA16096 --version 01.003.000
    python release_card.py --names "Inf HP, Max MP, EXP" --title "Spielname"
"""
import argparse
import colorsys
import json
import math
import os
import random
import re
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from theme import ACCENT as DEFAULT_ACCENT

W, H = 1920, 1080
BG = (5, 9, 13)
WHITE = (238, 244, 246)
DIM = (128, 150, 156)
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
PATCH_EXT = (".reapproj", ".reappatch", ".json", ".shnext", ".shn", ".mc4")
IGNORED = ("reaperpy_config.json", "applied.json", "pointer_paths.json", "cavemaker_config.json")
GENERIC_ART = ("icon0", "cover", "icon", "logo", "folder")

TEXTS = {
    "en": {"cheats": "CHEATS", "by": "BY", "brand": "REAPED WITH", "release": "TRAINER RELEASE", "more": "+ {n} MORE"},
    "de": {"cheats": "CHEATS", "by": "VON", "brand": "GEERNTET MIT", "release": "TRAINER-RELEASE", "more": "+ {n} WEITERE"},
}
FORMAT_TAGS = {"json": "GOLDHEN · ETAHEN", "shn": "SHN", "mc4": "MC4"}

FONTS = {
    "serif": ["georgiab.ttf", "timesbd.ttf", "LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf"],
    "display": ["bahnschrift.ttf", "impact.ttf", "LiberationSansNarrow-Bold.ttf", "DejaVuSansCondensed-Bold.ttf",
                "DejaVuSans-Bold.ttf"],
    "text": ["segoeuib.ttf", "bahnschrift.ttf", "arialbd.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "mono": ["consolab.ttf", "consola.ttf", "DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf"],
}
FONT_DIRS = ["", "C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/liberation/",
             "/usr/share/fonts/truetype/liberation2/", "/System/Library/Fonts/Supplemental/", "/Library/Fonts/"]
_font_override = None


# ----------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------
def load_font(size, role="text"):
    names = list(FONTS[role])
    if _font_override:
        names.insert(0, _font_override)
    for n in names:
        for d in ([""] if os.path.isabs(n) else FONT_DIRS):
            try:
                f = ImageFont.truetype(n if os.path.isabs(n) else d + n, size)
            except OSError:
                continue
            if "bahnschrift" in n.lower():
                for var in ("Bold Condensed", "SemiBold Condensed", "Bold"):
                    try:
                        f.set_variation_by_name(var)
                        break
                    except Exception:  # noqa: BLE001
                        continue
            return f
    return ImageFont.load_default()


def hex_rgb(s):
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def rgb_hex(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


def text_w(font, text, tracking=0):
    return font.getlength(text) + tracking * max(len(text) - 1, 0)


def draw_tracked(d, xy, text, font, fill, tracking=0, anchor="ls"):
    x, y = xy
    if tracking == 0:
        d.text((x, y), text, font=font, fill=fill, anchor=anchor)
        return
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill, anchor=anchor)
        x += font.getlength(ch) + tracking


def fit_font(text, size, max_w, role, min_size=30, tracking=0):
    while size > min_size:
        f = load_font(size, role)
        if text_w(f, text, tracking) <= max_w:
            return f
        size -= 2
    return load_font(min_size, role)


def ellipsize(text, font, max_w):
    if font.getlength(text) <= max_w:
        return text
    while len(text) > 1 and font.getlength(text + "...") > max_w:
        text = text[:-1]
    return text.rstrip() + "..."


def roman(n):
    out = ""
    for v, s in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
                 (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += s
            n -= v
    return out


def aa_layer(size, fn, scale=3):
    """Mit Kantenglättung zeichnen: große Ebene zeichnen, herunterrechnen."""
    big = Image.new("RGBA", (size[0] * scale, size[1] * scale), (0, 0, 0, 0))
    fn(ImageDraw.Draw(big), scale)
    return big.resize(size, Image.LANCZOS)


def glow(layer, radius, boost=1.0):
    g = layer.filter(ImageFilter.GaussianBlur(radius))
    if boost != 1.0:
        a = g.getchannel("A").point(lambda v: min(255, int(v * boost)))
        g.putalpha(a)
    return g


def split_title(text, font_size, max_w, role="serif", tracking=5):
    """Titel auf höchstens zwei Zeilen verteilen, wenn er in einer zu klein würde. -> [Zeile, ...]"""
    one = fit_font(text, font_size, max_w, role, 30, tracking)
    if one.size >= 76 or " " not in text:
        return [text]
    words = text.split()
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        f = fit_font(max(a, b, key=len), 96, max_w, role, 30, tracking)
        if best is None or f.size > best[0] or (f.size == best[0] and abs(len(a) - len(b)) < best[3]):
            best = (f.size, a, b, abs(len(a) - len(b)))
    return [best[1], best[2]] if best and best[0] > one.size else [text]


# ----------------------------------------------------------------------
# Eingaben
# ----------------------------------------------------------------------
def clean_name(n):
    n = os.path.splitext(n)[0] if n.lower().endswith(PATCH_EXT) else n
    n = re.sub(r"^\s*\d{1,3}[a-z]?\s*[-_.:)]*\s+", "", n)
    n = n.replace("_", " ").strip()
    return re.sub(r"\s{2,}", " ", n)


def names_from_doc(doc):
    """Cheat-Namen aus einem Export-Dokument (build_document): ohne Doppelte, in Export-Reihenfolge."""
    names = []
    for m in doc.get("mods", []) or []:
        nm = clean_name(str(m.get("name", "")))
        if nm and nm not in names:
            names.append(nm)
    return names


def from_json(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    credits = doc.get("credits") or []
    return {"title": doc.get("name") or doc.get("id", ""), "id": doc.get("id", ""), "version": doc.get("version", ""),
            "names": names_from_doc(doc), "author": ", ".join(str(c) for c in credits if c)}


def from_folder(folder):
    names = []
    for fn in sorted(os.listdir(folder)):
        low = fn.lower()
        if low.endswith(PATCH_EXT) and low not in IGNORED and not low.endswith(".cheatsession.json"):
            nm = clean_name(fn)
            if nm and nm not in names:
                names.append(nm)
    return names


def find_art(game_id, dirs):
    """Cover zur Titel-ID: exakter Name (PPSA12345.png) vor 'ID irgendwo im Namen', sonst icon0/cover im Ordner selbst."""
    best, generic = "", ""
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        base = os.path.abspath(d).rstrip(os.sep).count(os.sep)
        for root, subdirs, files in os.walk(d):
            if os.path.abspath(root).count(os.sep) - base >= 3:
                subdirs[:] = []
            subdirs[:] = [s for s in subdirs if not s.startswith(".") and s.lower() not in ("__pycache__", "$recycle.bin")]
            for fn in sorted(files):
                stem, ext = os.path.splitext(fn)
                if ext.lower() not in IMAGE_EXT:
                    continue
                p = os.path.join(root, fn)
                if game_id and game_id.lower() in fn.lower():
                    if stem.lower() == game_id.lower():
                        return p
                    best = best or p
                elif root == d and stem.lower() in GENERIC_ART:
                    generic = generic or p
    return best or generic


def accent_from_art(art, fallback=DEFAULT_ACCENT):
    """Leuchtende Akzentfarbe aus dem Cover: der kräftigste, hellste Farbton (Kreis-Mittel nach Sättigung x Helligkeit)."""
    try:
        small = art.convert("RGB").resize((64, 64), Image.BILINEAR)
    except Exception:  # noqa: BLE001
        return fallback
    sx = sy = wt = 0.0
    pixels = small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata()
    for r, g, b in pixels:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s < 0.30 or v < 0.30:
            continue
        w = (s * v) ** 2
        sx += math.cos(h * 2 * math.pi) * w
        sy += math.sin(h * 2 * math.pi) * w
        wt += w
    if wt < 1.5:                                                 # Cover (fast) grau: bei der Standardfarbe bleiben
        return fallback
    hue = (math.atan2(sy, sx) / (2 * math.pi)) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.78, 1.0)
    return rgb_hex((r * 255, g * 255, b * 255))


# ----------------------------------------------------------------------
# Bausteine der Karte
# ----------------------------------------------------------------------
def placeholder_art(accent, seed):
    rnd = random.Random(seed)
    a = hex_rgb(accent)
    img = Image.new("RGB", (900, 1200), (8, 16, 24))
    d = ImageDraw.Draw(img)
    for y in range(1200):
        t = y / 1200
        d.line([(0, y), (900, y)], fill=(int(8 + 30 * t), int(18 + 36 * t), int(28 + 40 * t)))
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    for _ in range(8):
        x, y, r = rnd.randint(100, 800), rnd.randint(200, 1100), rnd.randint(110, 300)
        ld.ellipse([x - r, y - r, x + r, y + r], fill=a + (rnd.randint(16, 44),))
    lay = lay.filter(ImageFilter.GaussianBlur(60))
    out = Image.alpha_composite(img.convert("RGBA"), lay)
    moon = Image.new("RGBA", img.size, (0, 0, 0, 0))
    md = ImageDraw.Draw(moon)
    md.ellipse([450 - 190, 400 - 190, 450 + 190, 400 + 190], fill=a + (70,))
    moon = moon.filter(ImageFilter.GaussianBlur(40))
    out = Image.alpha_composite(out, moon)
    ring = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([450 - 120, 400 - 120, 450 + 120, 400 + 120], fill=a + (200,))
    out = Image.alpha_composite(out, ring.filter(ImageFilter.GaussianBlur(1.5)))
    sc = aa_layer(img.size, lambda dd, k: draw_scythe(dd, 470, 620, 900, (3, 8, 12, 245), k), 2)
    return Image.alpha_composite(out, sc).convert("RGB")


def background(art, accent):
    """Cover als Stimmung: groß, verschwommen, tief abgedunkelt, Richtung Akzent getönt, Vignette."""
    bg = ImageOps.fit(art.convert("RGB"), (W, H), Image.LANCZOS, centering=(0.5, 0.35))
    bg = bg.filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", (W, H), BG), 0.80)
    tint = Image.new("RGB", (W, H), tuple(int(c * 0.18) for c in hex_rgb(accent)))
    bg = ImageChops.add(bg, tint)
    vig = Image.radial_gradient("L").resize((W, H), Image.BICUBIC).point(lambda v: int(min(255, (v / 255) ** 1.7 * 330)))
    black = Image.new("RGB", (W, H), (2, 4, 6))
    return Image.composite(black, bg, vig)


def fog(accent, seed):
    rnd = random.Random(f"fog-{seed}")
    total = Image.new("L", (W, H), 0)
    for gw, gh, wt in ((5, 3, 0.50), (12, 7, 0.32), (30, 17, 0.18)):
        data = bytes(rnd.randint(0, 255) for _ in range(gw * gh))
        n = Image.frombytes("L", (gw, gh), data).resize((W, H), Image.BICUBIC)
        total = ImageChops.add(total, n.point(lambda v, wt=wt: int(v * wt)))
    total = ImageOps.autocontrast(total.filter(ImageFilter.GaussianBlur(36)), cutoff=3)
    grad = Image.linear_gradient("L").resize((W, H)).point(lambda v: int((v / 255) ** 1.6 * 255))
    mask = ImageChops.multiply(total, grad).point(lambda v: int(v * 0.5))
    lay = Image.new("RGBA", (W, H), hex_rgb(accent) + (0,))
    lay.putalpha(mask)
    return lay


def particles(accent, seed):
    rnd = random.Random(f"p-{seed}")
    a = hex_rgb(accent)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for _ in range(70):
        x = rnd.randint(0, W)
        y = int(H * (rnd.random() ** 0.7))
        r = rnd.choice((1, 1, 2, 2, 3, 4))
        d.ellipse([x - r, y - r, x + r, y + r], fill=a + (rnd.randint(70, 210),))
    big = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(big)
    for _ in range(14):
        x, y, r = rnd.randint(0, W), rnd.randint(150, H), rnd.randint(5, 11)
        bd.ellipse([x - r, y - r, x + r, y + r], fill=a + (rnd.randint(60, 120),))
    big = big.filter(ImageFilter.GaussianBlur(5))
    return Image.alpha_composite(big, lay.filter(ImageFilter.GaussianBlur(0.8)))


def grain(seed, strength=0.055):
    """Feines Filmkorn über der ganzen Karte - nimmt dem Verlauf das Digitale."""
    n = Image.frombytes("L", (W, H), random.Random(f"grain-{seed}").randbytes(W * H))
    lay = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    lay.putalpha(n.point(lambda v: int(abs(v - 128) * 2 * strength)))
    return lay


def bezier(p0, p1, p2, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0], u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


def draw_scythe(d, cx, cy, size, color, scale=1, line=1.0):
    """Sense: schräger Stiel, Klinge als Halbmond.  size = Höhe in Pixeln, Mittelpunkt (cx, cy)."""
    s = size * scale
    cx, cy = cx * scale, cy * scale
    top = (cx + 0.20 * s, cy - 0.46 * s)
    bot = (cx - 0.22 * s, cy + 0.50 * s)
    d.line([bot, top], fill=color, width=max(int(0.022 * s * line), 1))
    p0, p1, p2 = (top[0] + 0.03 * s, top[1] + 0.03 * s), (cx - 0.28 * s, cy - 0.86 * s), (cx - 0.66 * s, cy - 0.10 * s)
    outer, inner = [], []
    steps = 40
    for i in range(steps + 1):
        t = i / steps
        x, y = bezier(p0, p1, p2, t)
        x2, y2 = bezier(p0, p1, p2, min(t + 0.01, 1.0))
        x1, y1 = bezier(p0, p1, p2, max(t - 0.01, 0.0))
        dx, dy = x2 - x1, y2 - y1
        ln = math.hypot(dx, dy) or 1
        nx, ny = dy / ln, -dx / ln                       # Normale (nach außen/oben)
        w = 0.15 * s * (1 - t) ** 0.8
        outer.append((x, y))
        inner.append((x - nx * w * -1, y - ny * w * -1))
    d.polygon(outer + inner[::-1], fill=color)


def sigil(accent, number, label):
    """Siegel-Ring mit der Anzahl in der Mitte -> RGBA-Ebene (D x D)."""
    a = hex_rgb(accent)
    R = 150
    D = R * 2 + 70
    c = D // 2

    def paint(d, k):
        def circ(r, fill=None, outline=None, width=1):
            d.ellipse([(c - r) * k, (c - r) * k, (c + r) * k, (c + r) * k], fill=fill, outline=outline,
                      width=max(int(width * k), 1))
        circ(R - 34, fill=(5, 11, 15, 232))
        circ(R, outline=a + (235,), width=2)
        circ(R - 34, outline=a + (110,), width=1)
        for i in range(96):
            ang = math.radians(i * 360 / 96)
            ln = 17 if i % 8 == 0 else (11 if i % 4 == 0 else 6)
            r0, r1 = R - 3, R - 3 - ln
            d.line([((c + r0 * math.cos(ang)) * k, (c + r0 * math.sin(ang)) * k),
                    ((c + r1 * math.cos(ang)) * k, (c + r1 * math.sin(ang)) * k)],
                   fill=a + ((200 if i % 8 == 0 else 120),), width=max(int(1.4 * k), 1))
        r_arc = R - 50
        for start in (200, 292, 20, 112):
            d.arc([(c - r_arc) * k, (c - r_arc) * k, (c + r_arc) * k, (c + r_arc) * k], start, start + 54,
                  fill=a + (230,), width=max(int(3 * k), 1))
        for ang_deg in (0, 90, 180, 270):
            ang = math.radians(ang_deg)
            px, py = c + (R + 14) * math.cos(ang), c + (R + 14) * math.sin(ang)
            s = 8
            d.polygon([(px * k, (py - s) * k), ((px + s) * k, py * k), (px * k, (py + s) * k), ((px - s) * k, py * k)],
                      fill=a + (255,))
    base = aa_layer((D, D), paint, 3)
    gl = glow(base, 7, 1.4)
    out = Image.alpha_composite(gl, base)
    nf = fit_font(number, 120, 165, "display", 50)
    num_lay = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    ImageDraw.Draw(num_lay).text((c, c - 16), number, font=nf, fill=a + (255,), anchor="mm")
    out = Image.alpha_composite(out, glow(num_lay, 12, 1.6))
    out = Image.alpha_composite(out, num_lay)
    d = ImageDraw.Draw(out)
    lf = load_font(24, "mono")
    draw_tracked(d, (c - text_w(lf, label, 8) / 2, c + 74), label, lf, WHITE + (235,), 8)
    return out


def portal_art(art, aw, ah):
    """Cover im Torbogen-Format.  Hochformat: ausfüllen.  Quadrat/Querformat (z. B. icon0): ganz zeigen, der Rest wird mit
    dem eigenen, verschwommenen Cover aufgefüllt - nichts wird abgeschnitten."""
    art = art.convert("RGB")
    ratio = art.width / art.height
    if 0.55 <= ratio <= 0.85:
        return ImageOps.fit(art, (aw, ah), Image.LANCZOS, centering=(0.5, 0.3)).convert("RGBA")
    back = ImageOps.fit(art, (aw, ah), Image.LANCZOS, centering=(0.5, 0.5)).filter(ImageFilter.GaussianBlur(26))
    back = Image.blend(back, Image.new("RGB", (aw, ah), BG), 0.45)
    fw = aw
    fh = max(int(aw / ratio), 1)
    if fh > ah * 0.8:                                                      # sehr hohes/breites Bild: Höhe begrenzen
        fh = int(ah * 0.8)
        fw = int(fh * ratio)
    front = art.resize((fw, fh), Image.LANCZOS)
    out = back.convert("RGBA")
    y = int(ah * 0.40 - fh / 2)
    y = max(24, min(y, ah - fh - 24))
    m = Image.new("L", (fw, fh), 255)
    ImageDraw.Draw(m).rectangle([0, 0, fw - 1, fh - 1], outline=0, width=1)
    soft = Image.new("L", (fw, fh), 0)
    ImageDraw.Draw(soft).rounded_rectangle([6, 6, fw - 7, fh - 7], radius=10, fill=255)
    out.paste(front.convert("RGBA"), ((aw - fw) // 2, y), soft.filter(ImageFilter.GaussianBlur(4)))
    return out


def portal(art, accent):
    """Torbogen mit Cover, Doppelrahmen, Leuchten und Bodenspiegelung -> (Ebene, Position)."""
    aw, ah = 520, 760
    ax, ay = 1230, 120
    a = hex_rgb(accent)
    img = portal_art(art, aw, ah)
    shade = Image.new("RGBA", (aw, ah), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(ah):
        t = y / ah
        sd.line([(0, y), (aw, y)], fill=(2, 6, 9, int(20 + 190 * max(t - 0.45, 0) / 0.55)))
    img = Image.alpha_composite(img, shade)

    def arch_mask(inset, scale=3):
        m = Image.new("L", (aw * scale, ah * scale), 0)
        md = ImageDraw.Draw(m)
        r = (aw / 2 - inset) * scale
        cx = aw / 2 * scale
        md.ellipse([cx - r, inset * scale, cx + r, inset * scale + 2 * r], fill=255)
        md.rectangle([cx - r, inset * scale + r, cx + r, (ah - inset) * scale], fill=255)
        return m.resize((aw, ah), Image.LANCZOS)

    img.putalpha(arch_mask(0))
    pad = 40
    refl_h = 110
    layer = Image.new("RGBA", (aw + 2 * pad, ah + 2 * pad + refl_h), (0, 0, 0, 0))

    def frames(d, k):
        def arch_outline(inset, alpha, width):
            r = (aw / 2 - inset) * k
            cx = (pad + aw / 2) * k
            top = (pad + inset) * k
            d.arc([cx - r, top, cx + r, top + 2 * r], 180, 360, fill=a + (alpha,), width=int(width * k))
            d.line([(cx - r, top + r), (cx - r, (pad + ah - inset) * k)], fill=a + (alpha,), width=int(width * k))
            d.line([(cx + r, top + r), (cx + r, (pad + ah - inset) * k)], fill=a + (alpha,), width=int(width * k))
            d.line([(cx - r, (pad + ah - inset) * k), (cx + r, (pad + ah - inset) * k)], fill=a + (alpha,),
                   width=int(width * k))
        arch_outline(0, 255, 3)
        arch_outline(-14, 90, 1.5)

    # weiche Aura hinter dem Tor
    aura = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(aura).ellipse([pad - 30, pad + 40, pad + aw + 30, pad + ah - 10], fill=a + (70,))
    layer = Image.alpha_composite(layer, aura.filter(ImageFilter.GaussianBlur(46)))
    fr = aa_layer(layer.size, frames, 3)
    layer = Image.alpha_composite(layer, glow(fr, 14, 1.8))
    # Spiegelung auf dem Boden: Cover kopfüber, schnell ausblendend
    refl = ImageOps.flip(img).crop((0, 0, aw, refl_h)).filter(ImageFilter.GaussianBlur(3))
    fade = Image.linear_gradient("L").resize((aw, refl_h)).transpose(Image.FLIP_TOP_BOTTOM).point(lambda v: int(v * 0.30))
    refl.putalpha(ImageChops.multiply(refl.getchannel("A"), fade))
    layer.alpha_composite(refl, (pad, pad + ah + 6))
    layer.alpha_composite(img, (pad, pad))
    layer = Image.alpha_composite(layer, fr)
    return layer, (ax - pad, ay - pad)


def chip(text, accent, font):
    """Kleine umrandete Kennzeichnung (z. B. GOLDHEN · ETAHEN) -> RGBA-Ebene."""
    a = hex_rgb(accent)
    tw = int(text_w(font, text, 3))
    w, h = tw + 36, 40
    lay = aa_layer((w, h), lambda d, k: d.rounded_rectangle([1 * k, 1 * k, (w - 2) * k, (h - 2) * k], radius=10 * k,
                                                            fill=a + (26,), outline=a + (150,), width=int(1.5 * k)), 3)
    draw_tracked(ImageDraw.Draw(lay), (18, h - 12), text, font, a + (255,), 3)
    return lay


# ----------------------------------------------------------------------
# Karte
# ----------------------------------------------------------------------
def platform_of(game_id, default="PS5"):
    gid = (game_id or "").upper()
    if gid.startswith("CUSA"):
        return "PS4"
    if gid.startswith("PPSA"):
        return "PS5"
    return default


def render_card(title, game_id, version, names, author="", art_path="", accent=None, lang="en", upper_names=False,
                out_path="card.png", tags=(), platform=None):
    """Karte zeichnen und als PNG speichern.  accent=None: aus dem Cover ziehen (sonst Standardfarbe)."""
    tx = TEXTS.get(lang, TEXTS["en"])
    names = [n for n in names if n]
    count = len(names)
    seed = game_id or title

    art = None
    if art_path and os.path.isfile(art_path):
        try:
            with Image.open(art_path) as im:       # Datei sofort wieder schliessen (Windows sperrt sie sonst)
                art = im.copy()
        except Exception:  # noqa: BLE001
            art = None
    if accent is None:
        accent = accent_from_art(art) if art is not None else DEFAULT_ACCENT
    acc = hex_rgb(accent)
    if art is None:
        art = placeholder_art(accent, seed)

    img = background(art, accent).convert("RGBA")

    # große, ganz blasse Sense als Wasserzeichen
    wm = aa_layer((W, H), lambda d, k: draw_scythe(d, 800, 540, 1500, acc + (18,), k), 2)
    img.alpha_composite(wm)

    # Torbogen mit Cover
    p_layer, p_pos = portal(art, accent)
    img.alpha_composite(p_layer, p_pos)

    # Nebel und Funken
    img.alpha_composite(fog(accent, seed))
    img.alpha_composite(particles(accent, seed))
    d = ImageDraw.Draw(img)

    # ---- Kopfzeile ----
    ico = aa_layer((120, 90), lambda dd, k: draw_scythe(dd, 70, 46, 76, acc + (255,), k), 3)
    img.alpha_composite(glow(ico, 5, 1.5), (60, 56))
    img.alpha_composite(ico, (60, 56))
    d = ImageDraw.Draw(img)
    kicker = f"{platform or platform_of(game_id)}  ·  {tx['release']}"
    draw_tracked(d, (186, 112), kicker, load_font(27, "mono"), acc + (255,), tracking=7)

    # ---- Titel (eine oder zwei Zeilen) ----
    ttl = title.upper()
    lines = split_title(ttl, 112, 1040)
    if len(lines) == 1:
        tf = fit_font(ttl, 112, 1040, "serif", 40, tracking=5)
        base_y, step = 262, 0
    else:
        tf = fit_font(max(lines, key=len), 96, 1040, "serif", 40, tracking=5)
        base_y, step = 232, int(tf.size * 1.02)
    tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for i, ln in enumerate(lines):
        draw_tracked(ImageDraw.Draw(tl), (96, base_y + i * step), ln, tf, acc + (255,), tracking=5)
    img.alpha_composite(glow(tl, 16, 0.55))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        draw_tracked(d, (96, base_y + i * step), ln, tf, WHITE + (255,), tracking=5)
    shift = step * (len(lines) - 1)

    # Zierlinie mit Raute
    ly = 296 + shift
    d.line([(96, ly), (336, ly)], fill=acc + (255,), width=3)
    d.polygon([(352, ly), (362, ly - 10), (372, ly), (362, ly + 10)], fill=acc + (255,))
    d.line([(388, ly), (1110, ly)], fill=acc + (70,), width=1)

    # ---- Meta ----
    mf = load_font(27, "mono")
    x = 96
    my = 352 + shift
    parts = [version if (not version or version.lower().startswith("v")) else f"v{version}", game_id]
    for i, t in enumerate([p for p in parts if p]):
        if i:
            d.polygon([(x + 12, my - 10), (x + 20, my - 18), (x + 28, my - 10), (x + 20, my - 2)], fill=acc + (255,))
            x += 52
        d.text((x, my), t, font=mf, fill=DIM + (255,), anchor="ls")
        x += mf.getlength(t)
    cx_ = 96
    cf = load_font(20, "mono")
    for t in tags:
        c = chip(t, accent, cf)
        img.alpha_composite(c, (cx_, my + 22))
        cx_ += c.width + 12
    d = ImageDraw.Draw(img)

    # ---- Cheat-Grimoire ----
    p_left, p_top, pad = 96, 392 + shift + (46 if tags else 0), 34
    avail = 940 - p_top - 2 * pad
    cols = 1 if count <= 6 else (2 if count <= 14 else (3 if count <= 33 else 4))
    min_row = 36.0
    capacity = cols * max(int(avail // min_row), 1)
    shown = names
    if count > capacity:                                          # zu viele: lesbar kürzen statt winzig schreiben
        shown = names[:capacity - 1] + [tx["more"].format(n=count - capacity + 1)]
    n_show = len(shown)
    rows = max(math.ceil(n_show / cols), 1)
    p_right = min(1130, p_left + 2 * pad + cols * 360)
    row_h = min(58.0, avail / rows)
    fs = max(int(row_h * (0.55 if cols == 3 else 0.46)), 15)
    panel_h = int(rows * row_h + 2 * pad)
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle([p_left, p_top, p_right, p_top + panel_h], radius=16, fill=(6, 12, 17, 182),
                         outline=acc + (52,), width=1)
    pw = p_right - p_left
    grad = Image.linear_gradient("L").resize((pw, panel_h)).transpose(Image.FLIP_TOP_BOTTOM).point(lambda v: int(v * 0.07))
    inside = Image.new("L", (pw, panel_h), 0)
    ImageDraw.Draw(inside).rounded_rectangle([1, 1, pw - 2, panel_h - 2], radius=15, fill=255)
    tint = Image.new("RGBA", (pw, panel_h), acc + (0,))
    tint.putalpha(ImageChops.multiply(grad, inside))
    panel.alpha_composite(tint, (p_left, p_top))
    pd.line([(p_left + 24, p_top), (p_left + 24 + 150, p_top)], fill=acc + (255,), width=3)
    img.alpha_composite(panel)
    d = ImageDraw.Draw(img)
    nf = load_font(fs, "text")
    rf = load_font(max(int(fs * 0.70), 12), "serif")
    col_w = (p_right - p_left - 2 * pad) / cols
    col_rom = []
    for c in range(cols):
        idx = range(c * rows, min((c + 1) * rows, n_show))
        col_rom.append(max((rf.getlength(roman(i + 1)) for i in idx), default=0) + 20)
    for i, nm in enumerate(shown):
        c, r = divmod(i, rows)
        x = p_left + pad + c * col_w
        y = p_top + pad + r * row_h + row_h * 0.64
        if r:                                                       # feine Trennlinie über jeder Zeile
            ly = int(p_top + pad + r * row_h + 2)
            d.line([(x, ly), (x + col_w - 18, ly)], fill=acc + (26,), width=1)
        is_more = count > capacity and i == n_show - 1
        if not is_more:
            d.text((x, y), roman(i + 1), font=rf, fill=acc + (190,), anchor="ls")
        label = nm.upper() if (upper_names or is_more) else nm
        off = 0 if is_more else col_rom[c]
        d.text((x + off, y), ellipsize(label, nf, col_w - off - 18), font=nf,
               fill=(acc + (230,)) if is_more else (WHITE + (255,)), anchor="ls")

    # ---- Siegel mit Anzahl ----
    sg = sigil(accent, str(count), tx["cheats"])
    img.alpha_composite(sg, (1690 - sg.width // 2, 800 - sg.height // 2 + 20))
    d = ImageDraw.Draw(img)

    # ---- Fußzeile ----
    d.line([(96, 1004), (W - 96, 1004)], fill=acc + (60,), width=1)
    d.polygon([(W // 2 - 9, 1004), (W // 2, 995), (W // 2 + 9, 1004), (W // 2, 1013)], fill=acc + (255,))
    ff = load_font(28, "mono")
    if author:
        draw_tracked(d, (96, 1050), f"{tx['by']}  {author.upper()}", ff, WHITE + (255,), tracking=6)
    brand = f"{tx['brand']}  REAPERPY"
    bw = text_w(ff, brand, 6)
    draw_tracked(d, (W - 96 - bw, 1050), brand, ff, WHITE + (255,), tracking=6)
    mini = aa_layer((90, 60), lambda dd, k: draw_scythe(dd, 52, 31, 50, acc + (255,), k), 3)
    img.alpha_composite(mini, (int(W - 96 - bw - 90), 1014))

    img.alpha_composite(grain(seed))
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


# ----------------------------------------------------------------------
# Anbindung an den Export (export_goldhen.ExportDialog)
# ----------------------------------------------------------------------
def card_path_for(export_path):
    """PPSA12345_01.000.000.json -> PPSA12345_01.000.000_release.png (neben dem Export)."""
    base, _ext = os.path.splitext(export_path)
    return base + "_release.png"


def card_for_export(doc, export_path, art_dirs=(), art_path="", author="", accent=None, lang="en", upper_names=False,
                    fmt="json", out_path=""):
    """Release-Karte zu einem fertigen Export-Dokument (export_goldhen.build_document) neben die Export-Datei legen.
    Wirft nie: -> (Pfad oder '', Meldung).  Ein Fehler hier darf den Export nicht gefährden."""
    try:
        names = names_from_doc(doc)
        if not names:
            return "", "Keine Cheats für die Karte."
        gid = doc.get("id", "")
        art = art_path if (art_path and os.path.isfile(art_path)) else find_art(
            gid, [d for d in art_dirs if d] + [os.path.dirname(os.path.abspath(export_path))])
        credits = doc.get("credits") or []
        who = author or ", ".join(str(c) for c in credits if c)
        out = render_card(doc.get("name") or gid or "TRAINER", gid, doc.get("version", ""), names, who, art, accent, lang,
                          upper_names, out_path or card_path_for(export_path), tags=[FORMAT_TAGS.get(fmt, fmt.upper())])
        return out, ("Cover: " + art) if art else "kein Cover gefunden - Portal-Verlauf"
    except Exception as e:  # noqa: BLE001
        return "", f"Release-Karte nicht erstellt: {e}"


# ----------------------------------------------------------------------
# Start (Kommandozeile)
# ----------------------------------------------------------------------
def main(argv=None):
    global _font_override
    ap = argparse.ArgumentParser(description="ReaperPy-Release-Karte erzeugen")
    ap.add_argument("--json", help="GoldHEN/etaHEN-Export von ReaperPy")
    ap.add_argument("--patches", help="Ordner mit Patch-Dateien")
    ap.add_argument("--names", help="Cheat-Namen, mit Komma getrennt")
    ap.add_argument("--title")
    ap.add_argument("--id", help="Titel-ID, z. B. PPSA16096")
    ap.add_argument("--version", help="Spiel-Version, z. B. 01.003.000")
    ap.add_argument("--art", help="Cover")
    ap.add_argument("--art-dir", action="append", default=[], help="Ordner, in dem nach <ID>*.png gesucht wird")
    ap.add_argument("--author", default="")
    ap.add_argument("--accent", default="", help="Akzentfarbe, z. B. ff5d38 (leer = aus dem Cover)")
    ap.add_argument("--lang", default="en", choices=sorted(TEXTS), help="Sprache der Beschriftung")
    ap.add_argument("--upper", action="store_true", help="Cheat-Namen in GROSSBUCHSTABEN")
    ap.add_argument("--font", help="eigene .ttf-Schrift")
    ap.add_argument("--out", help="Ausgabedatei (.png)")
    a = ap.parse_args(argv)
    _font_override = a.font
    info = {"title": "", "id": "", "version": "", "names": [], "author": ""}
    if a.json:
        info.update(from_json(a.json))
    if a.patches:
        info["names"] += [n for n in from_folder(a.patches) if n not in info["names"]]
    if a.names:
        info["names"] += [clean_name(n) for n in a.names.split(",") if n.strip()]
    for k in ("title", "id", "version"):
        if getattr(a, k):
            info[k] = getattr(a, k)
    if not info["names"]:
        ap.error("Keine Cheats: --json, --patches oder --names angeben")
    art = a.art or find_art(info["id"], a.art_dir + [os.getcwd(), os.path.dirname(os.path.abspath(__file__))])
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.json)) if a.json else os.getcwd(),
                                f"{info['id'] or 'trainer'}_release.png")
    render_card(info["title"] or info["id"] or "TRAINER", info["id"], info["version"], info["names"],
                a.author or info["author"], art, a.accent or None, a.lang, a.upper, out)
    print("Gespeichert:", out, f"({len(info['names'])} Cheats)", "| Cover:", art or "Portal-Verlauf")


if __name__ == "__main__":
    sys.exit(main())
