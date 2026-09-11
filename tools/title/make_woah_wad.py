#!/usr/bin/env python3
"""Build woah.wad - the Woah! title screen as a PWAD (TITLEPIC + M_DOOM).

Keeps the Freedoom title art (BSD). The FREEDOOM logo is painted out with sky
cloned from the same rows, and "Woah!" is set straight on that sky as chunky,
pixel-crisp chrome lettering (silver, blue "!", dark outline, drop shadow, dark
aura) so it sits IN the painting rather than on top of it. M_DOOM is that
lettering cropped and offset so M_DrawMainMenu's (94,2) lands it exactly where
it is on the title. The app loads the result with -file: engine untouched.

usage: make_woah_wad.py <freedoom2.wad> <out.wad> [preview_dir] [--style=upright|italic]
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "prefab"))
import wadlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BRAND_BLUE = (33, 150, 243)   # #2196F3 - the one blue

STYLES = {  # first font that exists wins; (path, variation axes by name - wide, so the
    # lettering spans the old logo's footprint instead of leaving its edges peeking out)
    "upright": [("/usr/share/fonts/truetype/ubuntu/Ubuntu[wdth,wght].ttf", {"wght": 800, "wdth": 125}),
                ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None)],
    "italic": [("/usr/share/fonts/truetype/ubuntu/Ubuntu-Italic[wdth,wght].ttf", {"wght": 800, "wdth": 125}),
               ("/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf", None)],
}


def lump_by_name(w, name):
    for i, l in enumerate(w.lumps):
        n = l.name.decode() if isinstance(l.name, bytes) else l.name
        if n.rstrip("\0") == name:
            return w.lump_bytes(i)
    raise KeyError(name)


# --- DOOM patch format: header, column offsets, posts {top, len, pad, pixels, pad}, 0xFF ---
def decode_patch(data):
    wd, ht, lo, to = struct.unpack_from("<hhhh", data, 0)
    colofs = struct.unpack_from("<%di" % wd, data, 8)
    px = [[None] * wd for _ in range(ht)]
    for x in range(wd):
        p = colofs[x]
        while data[p] != 0xFF:
            top, length = data[p], data[p + 1]
            p += 3
            for i in range(length):
                y = top + i
                if y < ht:
                    px[y][x] = data[p + i]
            p += length + 1
    return wd, ht, lo, to, px


def encode_patch(wd, ht, lo, to, px):
    cols = []
    for x in range(wd):
        col = bytearray()
        y = 0
        while y < ht:
            if px[y][x] is None:
                y += 1
                continue
            start = y
            while y < ht and px[y][x] is not None and y - start < 254:
                y += 1
            run = bytes(px[r][x] for r in range(start, y))
            col += bytes((start, len(run), run[0])) + run + bytes((run[-1],))
        col.append(0xFF)
        cols.append(bytes(col))
    ofs, colofs = 8 + 4 * wd, []
    for c in cols:
        colofs.append(ofs)
        ofs += len(c)
    return struct.pack("<hhhh", wd, ht, lo, to) + struct.pack("<%di" % wd, *colofs) + b"".join(cols)


def write_pwad(path, lumps):
    body, entries, pos = b"", [], 12
    for name, data in lumps:
        entries.append((pos, len(data), name))
        body += data
        pos += len(data)
    out = struct.pack("<4sii", b"PWAD", len(lumps), pos) + body
    for p, s, n in entries:
        out += struct.pack("<ii8s", p, s, n.encode("ascii"))
    with open(path, "wb") as f:
        f.write(out)


class Palette:
    def __init__(self, playpal):
        self.rgb = np.frombuffer(playpal[:768], dtype=np.uint8).reshape(256, 3).astype(np.int32)

    def nearest(self, rgb):
        d = ((self.rgb - np.array(rgb, dtype=np.int32)) ** 2).sum(axis=1)
        return int(d.argmin())

    def to_image(self, px, wd, ht, bg=(0, 0, 0)):
        img = Image.new("RGB", (wd, ht), bg)
        put = img.load()
        for y in range(ht):
            for x in range(wd):
                k = px[y][x]
                if k is not None:
                    put[x, y] = tuple(int(c) for c in self.rgb[k])
        return img


def _axis_key(a):
    """Pillow names variable-font axes by their human name (Weight/Width), not the tag."""
    n = a["name"].decode() if isinstance(a["name"], bytes) else str(a["name"])
    n = n.lower()
    if n.startswith("wid") or n == "wdth":
        return "wdth"
    if n.startswith("wei") or n == "wght":
        return "wght"
    return n


def load_font(size, style):
    for path, axes in STYLES[style]:
        if not os.path.exists(path):
            continue
        f = ImageFont.truetype(path, size)
        if axes:
            try:
                ax = f.get_variation_axes()
                f.set_variation_by_axes([min(max(axes.get(_axis_key(a), a["default"]), a["minimum"]), a["maximum"])
                                         for a in ax])
            except Exception as e:  # static fallback still renders
                print("  variation axes unavailable:", e)
        return f
    raise SystemExit("no usable TTF for style " + style)


def fit_font(text, box_w, box_h, style):
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    for size in range(120, 8, -1):
        f = load_font(size, style)
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        if r - l <= box_w and b - t <= box_h:
            return f
    return load_font(8, style)


def dilate(m):
    p = np.pad(m, 1)
    out = np.zeros_like(m)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= p[1 + dy:1 + dy + m.shape[0], 1 + dx:1 + dx + m.shape[1]]
    return out


def chrome(f, blue):
    """Vertical chrome ramp: bright top, dark band just below the middle, lighter bottom."""
    def lerp(a, b, k):
        return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))
    if blue:
        top, hi, band, lo, bot = (175, 218, 255), BRAND_BLUE, (10, 70, 140), BRAND_BLUE, (8, 78, 168)
    else:
        top, hi, band, lo, bot = (252, 252, 255), (186, 191, 201), (92, 97, 108), (176, 181, 191), (116, 121, 132)
    if f < 0.45:
        return lerp(top, hi, f / 0.45)
    if f < 0.55:
        return band
    return lerp(lo, bot, (f - 0.55) / 0.45)


def lettering(wd, ht, cx, cy, box_w, box_h, style):
    """Pixel-crisp chrome 'Woah!' (blue '!') with a 1px dark outline, a 2px drop
    shadow and a 3px dark aura, as an RGBA array. No antialiasing on purpose:
    at 320x200 it has to look painted, not rendered."""
    f = fit_font("Woah!", box_w, box_h, style)
    print("  font:", getattr(f, "path", "?"), "size", f.size)
    try:  # prove the variation actually applied
        print("  axes:", [(_axis_key(a), a["minimum"], a["default"], a["maximum"]) for a in f.get_variation_axes()],
              "set:", STYLES[style][0][1])
    except Exception:
        pass
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    probe.fontmode = "1"
    l, t, r, b = probe.textbbox((0, 0), "Woah!", font=f)
    x0 = int(round(cx - (r - l) / 2 - l))
    y0 = int(round(cy - (b - t) / 2 - t))

    def mask(txt, x):
        img = Image.new("L", (wd, ht), 0)
        d = ImageDraw.Draw(img)
        d.fontmode = "1"
        d.text((x, y0), txt, font=f, fill=255)
        return np.asarray(img) > 0

    m_word = mask("Woah", x0)
    m_bang = mask("!", x0 + int(round(probe.textlength("Woah", font=f))))
    m = m_word | m_bang
    edge = dilate(m) & ~m
    body = m | edge
    shadow = np.zeros_like(m)
    shadow[2:, 2:] = body[:-2, :-2]
    shadow &= ~body
    aura = body | shadow
    for _ in range(3):
        aura = dilate(aura)
    aura &= ~(body | shadow)
    layer = np.zeros((ht, wd, 4), np.uint8)
    layer[aura] = (34, 2, 2, 255)
    layer[shadow] = (16, 0, 0, 255)
    layer[edge] = (20, 8, 8, 255)
    ty, by = y0 + t, y0 + b
    for y, x in zip(*np.where(m)):
        fr = min(1.0, max(0.0, (y - ty) / max(1, by - ty)))
        layer[y, x] = chrome(fr, bool(m_bang[y, x])) + (255,)
    return layer


def logo_mask(img, y0=4, y1=62, x0=40, x1=280):
    """The FREEDOOM logo's own pixels - silver letters (bright, near-neutral) plus
    the orange infinity - grown 3px to swallow bevel and shadow. The horizontal
    span is taken from the RIGHT half and mirrored (the creature on the left has
    bright beige highlights that fool colour tests); Freedoom centres the logo."""
    a = np.asarray(img).astype(np.int32)
    lum = (a[..., 0] * 299 + a[..., 1] * 587 + a[..., 2] * 114) // 1000
    chroma = a.max(axis=2) - a.min(axis=2)
    silver = (lum >= 150) & (chroma <= 25)
    orange = (a[..., 0] >= 180) & (a[..., 1] >= 80) & (a[..., 1] <= 200) & (a[..., 2] <= 90)
    band = np.zeros_like(silver)
    band[y0:y1, x0:x1] = True
    right = silver & band
    right[:, :img.width // 2] = False
    ys, xs = np.where(right)
    if len(xs) == 0:
        raise SystemExit("logo not found - thresholds need a look")
    rx = int(xs.max())
    lx = img.width - 1 - rx
    ty, by = int(ys.min()), int(ys.max())
    span = np.zeros_like(silver)
    span[max(0, ty - 6):by + 7, max(0, lx - 6):rx + 7] = True
    # creature zone (left): anything NEUTRAL is logo - chrome highlights, dark bevel and
    # shadow alike - because the creature is tan/blue and the sky is red; grown 4px
    loose = (lum >= 20) & (chroma <= 30)
    m = (loose | orange) & span
    for _ in range(4):
        m = dilate(m)
    m &= span
    # right of the creature the logo sits on plain sky: take the whole strip - no residue
    m[max(0, ty - 6):by + 7, 118:rx + 7] = True
    return m, (lx, ty, rx, by)


def paint_out(px, m, src_x0=238, src_x1=288):
    """Replace masked pixels with sky cloned from the same row further right, where
    the title art is plain sky; ping-pong tiled so no seam repeats."""
    n = src_x1 - src_x0 + 1
    for y, x in zip(*np.where(m)):
        k = int(x) % (2 * n)
        sx = src_x0 + (k if k < n else 2 * n - 1 - k)
        px[y][x] = px[y][sx]


def make_titlepic(pal, data, style):
    """Returns (patch tuple, lettering alpha mask)."""
    wd, ht, lo, to, px = decode_patch(data)
    base = pal.to_image(px, wd, ht)
    m, (lx, ty, rx, by) = logo_mask(base)
    print("  logo bbox: (%d,%d)-(%d,%d); painting out %d px" % (lx, ty, rx, by, int(m.sum())))
    paint_out(px, m)
    cx, cy = (lx + rx) / 2.0, (ty + by) / 2.0
    layer = lettering(wd, ht, cx, cy, (rx - lx + 1) + 24, 40, style)
    alpha = layer[..., 3]
    for y, x in zip(*np.where(alpha > 0)):   # only painted pixels get re-quantised
        px[y][x] = pal.nearest(tuple(int(c) for c in layer[y, x, :3]))
    return (wd, ht, lo, to, px), alpha


def make_mdoom(t, alpha):
    """The lettering cropped out of the finished TITLEPIC, transparent elsewhere;
    offsets make M_DrawMainMenu's (94,2) land it at its own title position."""
    wd, ht, lo, to, px = t
    ys, xs = np.where(alpha > 0)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    crop = [[px[y][x] if alpha[y][x] > 0 else None for x in range(x0, x1 + 1)] for y in range(y0, y1 + 1)]
    return x1 - x0 + 1, y1 - y0 + 1, 94 - x0, 2 - y0, crop


def preview(pal, name, patch, out_dir, scale=3, over=None):
    wd, ht, lo, to, px = decode_patch(patch)   # decode what we ENCODED: a second round-trip check
    if over is None:
        img = pal.to_image(px, wd, ht, bg=(40, 40, 40))
    else:  # draw the way the engine does: at (94,2) minus the patch offsets
        img = over.copy()
        put = img.load()
        ox, oy = 94 - lo, 2 - to
        for y in range(ht):
            for x in range(wd):
                if px[y][x] is not None and 0 <= ox + x < img.width and 0 <= oy + y < img.height:
                    put[ox + x, oy + y] = tuple(int(c) for c in pal.rgb[px[y][x]])
    img.resize((img.width * scale, img.height * scale), Image.NEAREST).save(os.path.join(out_dir, name + ".png"))
    return px


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    style = "upright"
    for a in sys.argv[1:]:
        if a.startswith("--style="):
            style = a.split("=", 1)[1]
    if len(args) < 2 or style not in STYLES:
        raise SystemExit(__doc__)
    iwad, out_wad = args[0], args[1]
    prev = args[2] if len(args) > 2 else None
    w = wadlib.WAD(iwad)
    pal = Palette(lump_by_name(w, "PLAYPAL"))
    print("TITLEPIC (%s)" % style)
    t, alpha = make_titlepic(pal, lump_by_name(w, "TITLEPIC"), style)
    print("M_DOOM")
    m = make_mdoom(t, alpha)
    print("  M_DOOM: %dx%d offsets (%d,%d)" % m[:4])
    t_bytes, m_bytes = encode_patch(*t), encode_patch(*m)
    assert decode_patch(t_bytes)[4] == t[4] and decode_patch(m_bytes)[4] == m[4], "patch round-trip mismatch"
    write_pwad(out_wad, [("TITLEPIC", t_bytes), ("M_DOOM", m_bytes)])
    print("wrote", out_wad, os.path.getsize(out_wad), "bytes")
    if prev:
        os.makedirs(prev, exist_ok=True)
        preview(pal, "titlepic", t_bytes, prev)
        # menu preview over the ORIGINAL art: a mismatch between title and M_DOOM would show
        orig = pal.to_image(decode_patch(lump_by_name(w, "TITLEPIC"))[4], t[0], t[1])
        preview(pal, "mainmenu", m_bytes, prev, over=orig)
        print("previews in", prev)


if __name__ == "__main__":
    main()
