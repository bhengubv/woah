#!/usr/bin/env python3
"""Build woah.wad - the Woah! title screen as a PWAD (TITLEPIC + M_DOOM).

Keeps the Freedoom title art (BSD) and puts the Woah! nameplate over the
FREEDOOM logo. M_DOOM (the logo drawn above the main menu) is that same
nameplate, cropped and offset so M_DrawMainMenu's (94,2) lands it exactly where
it sits on the title screen - opening the menu changes nothing at the top.
The app loads the result with -file, so the engine is untouched.

usage: make_woah_wad.py <freedoom2.wad> <out.wad> [preview_dir]
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "prefab"))
import wadlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BRAND_BLUE = (33, 150, 243)   # #2196F3 - the one blue
PLATE = (10, 12, 18)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

FONTS = [  # first that exists wins; (path, variation axes by name)
    ("/usr/share/fonts/truetype/ubuntu/Ubuntu-Italic[wdth,wght].ttf", {"wght": 800, "wdth": 100}),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", None),
]


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


def load_font(size):
    for path, axes in FONTS:
        if not os.path.exists(path):
            continue
        f = ImageFont.truetype(path, size)
        if axes:
            try:
                ax = f.get_variation_axes()
                order = [a["name"].decode() if isinstance(a["name"], bytes) else a["name"] for a in ax]
                f.set_variation_by_axes([axes.get(n, a["default"]) for n, a in zip(order, ax)])
            except Exception as e:  # static fallback still renders
                print("  variation axes unavailable:", e)
        return f
    raise SystemExit("no usable TTF found")


def fit_font(text, box_w, box_h, stroke=0):
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(120, 8, -1):
        f = load_font(size)
        l, t, r, b = d.textbbox((0, 0), text, font=f, stroke_width=stroke)
        if r - l <= box_w and b - t <= box_h:
            return f
    return load_font(8)


def draw_wordmark(layer, cx, cy, box_w, box_h, stroke=0):
    """'Woah' in white + '!' in brand blue, centred on (cx, cy)."""
    f = fit_font("Woah!", box_w, box_h, stroke)
    d = ImageDraw.Draw(layer)
    l, t, r, b = d.textbbox((0, 0), "Woah!", font=f, stroke_width=stroke)
    w_word = d.textlength("Woah", font=f)
    x0 = cx - (r - l) / 2 - l
    y0 = cy - (b - t) / 2 - t
    d.text((x0, y0), "Woah", font=f, fill=WHITE, stroke_width=stroke, stroke_fill=BLACK)
    d.text((x0 + w_word, y0), "!", font=f, fill=BRAND_BLUE, stroke_width=stroke, stroke_fill=BLACK)


def logo_bbox(img, y0=4, y1=62, x_mid=160, x1=280, lum_min=140, chroma_max=48):
    """Bounding box of the silver FREEDOOM letters in the top band. Detection
    runs on the RIGHT half only - the creature on the left has bright, low-chroma
    highlights that fool any colour test - and since Freedoom centres the logo,
    the left edge is the right edge mirrored."""
    a = np.asarray(img).astype(np.int32)[y0:y1, x_mid:x1]
    lum = (a[:, :, 0] * 299 + a[:, :, 1] * 587 + a[:, :, 2] * 114) // 1000
    chroma = a.max(axis=2) - a.min(axis=2)
    ys, xs = np.where((lum >= lum_min) & (chroma <= chroma_max))
    if len(xs) == 0:
        raise SystemExit("logo not found - thresholds need a look")
    right = int(xs.max()) + x_mid
    return img.width - 1 - right, int(ys.min()) + y0, right, int(ys.max()) + y0


def make_titlepic(pal, data, pad=5):
    """Returns ((patch tuple), plate rect, plate alpha mask)."""
    wd, ht, lo, to, px = decode_patch(data)
    base = pal.to_image(px, wd, ht)
    x0, y0, x1, y1 = logo_bbox(base)
    print("  logo bbox: (%d,%d)-(%d,%d)" % (x0, y0, x1, y1))
    half = max(wd // 2 - x0, x1 - wd // 2) + pad          # symmetric about the centre line
    # two extra rows at the bottom hide the orange infinity's tail; menu items start at y=64
    plate = (wd // 2 - half, max(0, y0 - pad), wd // 2 + half, min(60, y1 + pad + 2))
    print("  plate: (%d,%d)-(%d,%d)" % plate)
    layer = Image.new("RGBA", (wd, ht), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(plate, radius=5, fill=PLATE + (255,), outline=BRAND_BLUE + (255,), width=2)
    pw, ph = plate[2] - plate[0], plate[3] - plate[1]
    draw_wordmark(layer, (plate[0] + plate[2]) / 2, (plate[1] + plate[3]) / 2, pw - 14, ph - 8)
    out = Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")
    alpha = np.asarray(layer)[:, :, 3]
    rgb = np.asarray(out)
    for y, x in zip(*np.where(alpha > 0)):   # only painted pixels get re-quantised; the art keeps its indices
        px[y][x] = pal.nearest(rgb[y, x])
    return (wd, ht, lo, to, px), plate, alpha


def make_mdoom(t, plate, alpha):
    """The nameplate cropped out of the finished TITLEPIC; rounded-corner gaps
    stay transparent. Offsets make (94,2) land it at the plate's own position."""
    wd, ht, lo, to, px = t
    x0, y0, x1, y1 = plate
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
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    iwad, out_wad = sys.argv[1], sys.argv[2]
    prev = sys.argv[3] if len(sys.argv) > 3 else None
    w = wadlib.WAD(iwad)
    pal = Palette(lump_by_name(w, "PLAYPAL"))
    print("TITLEPIC")
    t, plate, alpha = make_titlepic(pal, lump_by_name(w, "TITLEPIC"))
    print("M_DOOM")
    m = make_mdoom(t, plate, alpha)
    print("  M_DOOM: %dx%d offsets (%d,%d)" % m[:4])
    t_bytes, m_bytes = encode_patch(*t), encode_patch(*m)
    assert decode_patch(t_bytes)[4] == t[4] and decode_patch(m_bytes)[4] == m[4], "patch round-trip mismatch"
    write_pwad(out_wad, [("TITLEPIC", t_bytes), ("M_DOOM", m_bytes)])
    print("wrote", out_wad, os.path.getsize(out_wad), "bytes")
    if prev:
        os.makedirs(prev, exist_ok=True)
        tp = preview(pal, "titlepic", t_bytes, prev)
        # menu preview over the ORIGINAL art, so a mismatch between plate and M_DOOM would show
        orig = pal.to_image(decode_patch(lump_by_name(w, "TITLEPIC"))[4], t[0], t[1])
        preview(pal, "mainmenu", m_bytes, prev, over=orig)
        print("previews in", prev)


if __name__ == "__main__":
    main()
