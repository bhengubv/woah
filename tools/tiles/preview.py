#!/usr/bin/env python3
# tools/tiles/preview.py
"""Top-down render of a compiled map (MAP01 in a PWAD): walls white, two-sided
lines grey, exit switch green, things as dots (player blue, monsters red, pickups
yellow), subsector rectangles faint. A picture of the geometry before it reaches
a phone. usage: preview.py <map.wad> <out.png> [scale]"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "prefab"))
import wadlib
from PIL import Image, ImageDraw


def records(b, fmt):
    n = struct.calcsize(fmt)
    return [struct.unpack_from(fmt, b, o) for o in range(0, len(b) - len(b) % n, n)]


def main(path, out, scale=0.5):
    w = wadlib.WAD(path)
    names = [l.name for l in w.lumps]
    get = lambda n: w.lump_bytes(names.index(n))
    verts = records(get("VERTEXES"), "<hh")
    lines = records(get("LINEDEFS"), "<HHHHHHH")
    things = records(get("THINGS"), "<hhHHH")
    segs = records(get("SEGS"), "<HHHHHH")
    ssecs = records(get("SSECTORS"), "<HH")
    xs = [v[0] for v in verts]; ys = [v[1] for v in verts]
    pad = 64
    x0, y0, x1, y1 = min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
    W, H = int((x1 - x0) * scale), int((y1 - y0) * scale)
    img = Image.new("RGB", (W, H), (18, 18, 22))
    d = ImageDraw.Draw(img)
    P = lambda x, y: ((x - x0) * scale, (y1 - y) * scale)   # DOOM y is up
    # subsectors: faint boxes from their segs' extents
    for n, first in ssecs:
        pts = []
        for s in segs[first:first + n]:
            pts += [verts[s[0]], verts[s[1]]]
        if pts:
            bx = [p[0] for p in pts]; by = [p[1] for p in pts]
            d.rectangle([P(min(bx), max(by)), P(max(bx), min(by))], outline=(40, 40, 60))
    for v1, v2, flags, special, tag, s0, s1 in lines:
        col = (110, 110, 120) if s1 != 0xFFFF else (235, 235, 235)
        if special == 11:
            col = (60, 220, 90)
        d.line([P(*verts[v1]), P(*verts[v2])], fill=col, width=2 if s1 == 0xFFFF else 1)
    for x, y, angle, t, flags in things:
        col = (33, 150, 243) if t == 1 else (230, 60, 60) if t in (3001, 3002, 3004, 3005, 9, 65) else (240, 210, 60)
        cx, cy = P(x, y)
        r = 4
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    d.text((6, 6), "%s  %d lines, %d things, %d subsectors" % (os.path.basename(path), len(lines), len(things), len(ssecs)),
           fill=(200, 200, 200))
    img.save(out)
    print("preview", out, img.size)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.5)
