#!/usr/bin/env python3
# tools/tiles/compile.py
"""Reference compiler: a Woah! level card -> a playable PWAD (MAP01).

Places tiles from tiles.py on the grid, joins them at declared doors, emits the
map lumps, builds NODES/SSECTORS/SEGS by axis-aligned splits over the sector
rectangles, rasterises the BLOCKMAP and writes an all-zero REJECT. Texture and
flat names are checked against the IWAD before anything is written.

usage: compile.py <card.json> <out.wad> [--iwad freedoom2.wad]
"""
import json, math, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "prefab"))
import wadlib
from tiles import TILES, CELL, ROLE_THINGS, resolve_thing

DRESS = {  # from tools/prefab palettes.json (Freedoom, BSD): the commonest pairings
    "tech": dict(floor="CEIL5_2", ceil="CEIL5_2", wall="METAL", light=160),
    "base": dict(floor="FLOOR5_4", ceil="FLOOR5_4", wall="BRICK6", light=144),
    "hell": dict(floor="FLOOR7_2", ceil="FLOOR7_2", wall="SUPPORT3", light=128),
}
EXIT_SWITCH = ["SW1EXIT", "SW1BRCOM", "SW1COMM"]     # first that the IWAD knows
ML_BLOCKING, ML_TWOSIDED = 1, 4
SPECIAL_EXIT = 11                                     # S1: exit level


# ---------- IWAD names, so a typo cannot reach the phone ----------
def iwad_names(path):
    w = wadlib.WAD(path)
    textures, flats = set(), set()
    names = [l.name for l in w.lumps]
    for tl in ("TEXTURE1", "TEXTURE2"):
        if tl in names:
            b = w.lump_bytes(names.index(tl))
            n = struct.unpack_from("<i", b, 0)[0]
            for i in range(n):
                off = struct.unpack_from("<i", b, 4 + 4 * i)[0]
                textures.add(b[off:off + 8].rstrip(b"\0").decode("ascii", "replace"))
    inside = False
    for l in w.lumps:
        if l.name in ("F_START", "FF_START"):
            inside = True
        elif l.name in ("F_END", "FF_END"):
            inside = False
        elif inside and l.size == 4096:
            flats.add(l.name)
    return textures, flats


# ---------- geometry ----------
def spans_subtract(span, cuts):
    """Remove closed intervals `cuts` from `span`; return the remaining open pieces."""
    out, a, b = [], span[0], span[1]
    for c0, c1 in sorted(cuts):
        c0, c1 = max(c0, a), min(c1, b)
        if c1 <= a:
            continue
        if c0 > a:
            out.append((a, c0))
        a = max(a, c1)
        if a >= b:
            break
    if a < b:
        out.append((a, b))
    return out


class Level:
    def __init__(self, card, textures, flats):
        self.card, self.textures, self.flats = card, textures, flats
        self.sectors, self.rects, self.doors = [], [], {}
        self.verts, self.vindex = [], {}
        self.lines, self.sides, self.things = [], [], []
        self.warnings = []
        self.exit_switch = next((t for t in EXIT_SWITCH if t in textures), EXIT_SWITCH[-1])

    # -- placement
    def place(self):
        c = self.card
        grid = c.get("grid", CELL)
        pop = c.get("pop") or {}
        preset, overrides = pop.get("preset", "normal"), pop.get("slots") or {}
        for ti, t in enumerate(c["tiles"]):
            tile = TILES[t["t"]]
            dress = DRESS[t.get("dress", "tech")]
            ox, oy, z = t["x"] * grid, t["y"] * grid, t.get("z", 0)
            for sec in tile["sectors"]:
                si = len(self.sectors)
                self.sectors.append(dict(floor=sec["floor"] + z, ceil=sec["ceil"] + z, floortex=dress["floor"],
                                         ceiltex=dress["ceil"], light=dress["light"], special=0, tag=0,
                                         wall=dress["wall"], tile=ti))
                for (x0, y0, x1, y1) in sec["rects"]:
                    self.rects.append(dict(x0=ox + x0 * grid, y0=oy + y0 * grid, x1=ox + x1 * grid,
                                           y1=oy + y1 * grid, sector=si, tile=ti))
            for si, sl in enumerate(tile["slots"]):
                kind = resolve_thing(sl["role"], preset, overrides.get("%d/%d" % (ti, si)))
                if kind is None:
                    continue
                self.things.append(dict(x=int(ox + sl["x"] * grid), y=int(oy + sl["y"] * grid), angle=0,
                                        type=kind, flags=7, tile=ti, role=sl["role"]))
        for a, b in c.get("doors", []):
            span = self.door_span(a, b)
            if span is None:
                raise SystemExit("door %d-%d: sockets do not touch with equal span" % (a, b))
            self.doors[(a, b)] = self.doors[(b, a)] = span

    def socket_spans(self, ti):
        """Absolute (edge, fixed coord, lo, hi) for each socket of placed tile ti."""
        t = self.card["tiles"][ti]
        tile = TILES[t["t"]]
        grid = self.card.get("grid", CELL)
        ox, oy = t["x"] * grid, t["y"] * grid
        out = []
        for k in tile["sockets"]:
            if k["edge"] in ("N", "S"):
                y = oy + (tile["h"] if k["edge"] == "N" else 0) * grid
                out.append((k["edge"], y, ox + k["pos"] * grid, ox + (k["pos"] + k["width"]) * grid))
            else:
                x = ox + (tile["w"] if k["edge"] == "E" else 0) * grid
                out.append((k["edge"], x, oy + k["pos"] * grid, oy + (k["pos"] + k["width"]) * grid))
        return out

    def door_span(self, a, b):
        opp = {"N": "S", "S": "N", "E": "W", "W": "E"}
        for ea, ca, lo, hi in self.socket_spans(a):
            for eb, cb, lo2, hi2 in self.socket_spans(b):
                if eb == opp[ea] and ca == cb and lo == lo2 and hi == hi2:
                    return ("h" if ea in ("N", "S") else "v", ca, lo, hi)
        return None

    # -- lines
    def vertex(self, x, y):
        k = (int(x), int(y))
        if k not in self.vindex:
            self.vindex[k] = len(self.verts)
            self.verts.append(k)
        return self.vindex[k]

    def add_side(self, sector, upper="-", lower="-", mid="-"):
        self.sides.append(dict(xoff=0, yoff=0, upper=upper, lower=lower, mid=mid, sector=sector))
        return len(self.sides) - 1

    def add_line(self, p, q, front, back, special=0, exit_face=False):
        """p->q direction; the front side is the right-hand side of it."""
        fs, bs = self.sectors[front], (self.sectors[back] if back is not None else None)
        if bs is None:
            tex = self.exit_switch if exit_face else fs["wall"]
            s0 = self.add_side(front, mid=tex)
            self.lines.append(dict(v1=self.vertex(*p), v2=self.vertex(*q), flags=ML_BLOCKING, special=special,
                                   tag=0, s0=s0, s1=0xFFFF, p=p, q=q, front=front, back=None))
        else:
            s0 = self.add_side(front, upper=fs["wall"], lower=fs["wall"])
            s1 = self.add_side(back, upper=bs["wall"], lower=bs["wall"])
            self.lines.append(dict(v1=self.vertex(*p), v2=self.vertex(*q), flags=ML_TWOSIDED, special=0, tag=0,
                                   s0=s0, s1=s1, p=p, q=q, front=front, back=back))
        return len(self.lines) - 1

    def build_lines(self):
        """Walk every rectangle edge. Overlaps with a same-sector rectangle are open
        (no line); with another sector of the same tile: two-sided; across tiles:
        two-sided only inside a declared door, walls elsewhere; the rest: walls."""
        exit_edges = {}
        for ti, t in enumerate(self.card["tiles"]):
            tile = TILES[t["t"]]
            if tile["exit_edge"]:
                grid = self.card.get("grid", CELL)
                ox, oy = t["x"] * grid, t["y"] * grid
                e = tile["exit_edge"]
                exit_edges[ti] = (e, {"N": oy + tile["h"] * grid, "S": oy, "E": ox + tile["w"] * grid, "W": ox}[e])
        for ri, r in enumerate(self.rects):
            for edge in ("N", "S", "E", "W"):
                horiz = edge in ("N", "S")
                fixed = {"N": r["y1"], "S": r["y0"], "E": r["x1"], "W": r["x0"]}[edge]
                span = (r["x0"], r["x1"]) if horiz else (r["y0"], r["y1"])
                open_cuts, two_sided = [], []
                for rj, o in enumerate(self.rects):
                    if rj == ri:
                        continue
                    ofixed = {"N": o["y0"], "S": o["y1"], "E": o["x0"], "W": o["x1"]}[edge]
                    if ofixed != fixed:
                        continue
                    ospan = (o["x0"], o["x1"]) if horiz else (o["y0"], o["y1"])
                    lo, hi = max(span[0], ospan[0]), min(span[1], ospan[1])
                    if hi <= lo:
                        continue
                    if o["sector"] == r["sector"]:
                        open_cuts.append((lo, hi))
                    elif o["tile"] == r["tile"]:
                        two_sided.append((lo, hi, rj))
                    else:
                        d = self.doors.get((r["tile"], o["tile"]))
                        if d and d[0] == ("h" if horiz else "v") and d[1] == fixed:
                            dlo, dhi = max(lo, d[2]), min(hi, d[3])
                            if dhi > dlo:
                                two_sided.append((dlo, dhi, rj))
                cuts = open_cuts + [(lo, hi) for lo, hi, _ in two_sided]
                exit_face = r["tile"] in exit_edges and exit_edges[r["tile"]] == (edge, fixed)
                for lo, hi in spans_subtract(span, cuts):
                    if exit_face and hi - lo > 128:
                        # the switch is one 64-unit panel in the middle of the wall, not the whole wall
                        mid = (lo + hi) // 2
                        self.add_line(*self.edge_points(edge, fixed, lo, mid - 32), front=r["sector"], back=None)
                        self.add_line(*self.edge_points(edge, fixed, mid - 32, mid + 32), front=r["sector"], back=None,
                                      special=SPECIAL_EXIT, exit_face=True)
                        self.add_line(*self.edge_points(edge, fixed, mid + 32, hi), front=r["sector"], back=None)
                    else:
                        self.add_line(*self.edge_points(edge, fixed, lo, hi), front=r["sector"], back=None,
                                      special=SPECIAL_EXIT if exit_face else 0, exit_face=exit_face)
                # two-sided lines once: from the N and E owner only
                if edge in ("N", "E"):
                    for lo, hi, rj in two_sided:
                        self.add_line(*self.edge_points(edge, fixed, lo, hi), front=r["sector"],
                                      back=self.rects[rj]["sector"])

    @staticmethod
    def edge_points(edge, fixed, lo, hi):
        """Endpoints in the direction whose right-hand side is the rectangle's inside."""
        if edge == "N":
            return (lo, fixed), (hi, fixed)
        if edge == "S":
            return (hi, fixed), (lo, fixed)
        if edge == "E":
            return (fixed, hi), (fixed, lo)
        return (fixed, lo), (fixed, hi)

    # -- BSP by axis-aligned splits over rectangles
    def build_bsp(self):
        self.segs, self.ssectors, self.nodes = [], [], []
        leaves = [dict(x0=r["x0"], y0=r["y0"], x1=r["x1"], y1=r["y1"], sector=r["sector"]) for r in self.rects]
        self.root = self.split(leaves)

    def split(self, rs):
        if len(rs) == 1:
            return 0x8000 | self.leaf(rs[0])
        xs = sorted({r["x0"] for r in rs} | {r["x1"] for r in rs})
        ys = sorted({r["y0"] for r in rs} | {r["y1"] for r in rs})
        best = None
        for axis, cands in (("x", xs[1:-1]), ("y", ys[1:-1])):
            for c in cands:
                if axis == "x":
                    cut = sum(1 for r in rs if r["x0"] < c < r["x1"])
                else:
                    cut = sum(1 for r in rs if r["y0"] < c < r["y1"])
                left = [r for r in rs if (r["x1"] <= c if axis == "x" else r["y1"] <= c)]
                right = [r for r in rs if (r["x0"] >= c if axis == "x" else r["y0"] >= c)]
                if cut == 0 and (not left or not right):
                    continue   # a non-cutting split must leave something on both sides
                balance = abs(len(left) - len(right))
                score = cut * 10 + balance
                if best is None or score < best[0]:
                    best = (score, axis, c)
        if best is None:  # two identical boxes - cannot happen with disjoint rectangles
            raise SystemExit("bsp: cannot split %r" % rs)
        _, axis, c = best
        lo_set, hi_set = [], []
        for r in rs:
            if axis == "x":
                if r["x1"] <= c:
                    lo_set.append(r)
                elif r["x0"] >= c:
                    hi_set.append(r)
                else:
                    lo_set.append(dict(r, x1=c)); hi_set.append(dict(r, x0=c))
            else:
                if r["y1"] <= c:
                    lo_set.append(r)
                elif r["y0"] >= c:
                    hi_set.append(r)
                else:
                    lo_set.append(dict(r, y1=c)); hi_set.append(dict(r, y0=c))
        # partition direction chosen so DOOM's R_PointOnSide puts hi_set on child 0 (right)
        if axis == "x":
            part = (c, min(r["y0"] for r in rs), 0, 1)          # points +y: right side is +x
            right, left = hi_set, lo_set
        else:
            part = (min(r["x0"] for r in rs), c, 1, 0)          # points +x: right side is -y
            right, left = lo_set, hi_set
        c0, c1 = self.split(right), self.split(left)
        self.nodes.append(dict(x=part[0], y=part[1], dx=part[2], dy=part[3],
                               bbox=[self.bbox(right), self.bbox(left)], children=[c0, c1]))
        return len(self.nodes) - 1

    @staticmethod
    def bbox(rs):  # top, bottom, left, right
        return [max(r["y1"] for r in rs), min(r["y0"] for r in rs), min(r["x0"] for r in rs), max(r["x1"] for r in rs)]

    def leaf(self, r):
        """One subsector per leaf rectangle: its segs are the pieces of linedefs along its edges."""
        first = len(self.segs)
        for li, L in enumerate(self.lines):
            for side, sec in ((0, L["front"]), (1, L["back"])):
                if sec != r["sector"]:
                    continue
                p, q = L["p"], L["q"]
                horiz = p[1] == q[1]
                fixed = p[1] if horiz else p[0]
                on_edge = (horiz and fixed in (r["y0"], r["y1"])) or ((not horiz) and fixed in (r["x0"], r["x1"]))
                if not on_edge:
                    continue
                lo, hi = (min(p[0], q[0]), max(p[0], q[0])) if horiz else (min(p[1], q[1]), max(p[1], q[1]))
                rlo, rhi = (r["x0"], r["x1"]) if horiz else (r["y0"], r["y1"])
                a, b = max(lo, rlo), min(hi, rhi)
                if b <= a:
                    continue
                # seg runs in the line's direction on side 0, reversed on side 1
                if horiz:
                    s, e = ((a, fixed), (b, fixed)) if p[0] < q[0] else ((b, fixed), (a, fixed))
                else:
                    s, e = ((fixed, a), (fixed, b)) if p[1] < q[1] else ((fixed, b), (fixed, a))
                if side == 1:
                    s, e = e, s
                start = p if side == 0 else q
                offset = int(abs(s[0] - start[0]) + abs(s[1] - start[1]))
                ang = math.atan2(e[1] - s[1], e[0] - s[0])
                self.segs.append(dict(v1=self.vertex(*s), v2=self.vertex(*e), angle=int(ang / (2 * math.pi) * 65536) & 0xFFFF,
                                      line=li, side=side, offset=offset))
        n = len(self.segs) - first
        if n == 0:
            self.warnings.append("subsector with no segs at %r" % ((r["x0"], r["y0"], r["x1"], r["y1"]),))
        self.ssectors.append(dict(numsegs=n, firstseg=first))
        return len(self.ssectors) - 1

    # -- blockmap / reject
    def build_blockmap(self):
        xs = [v[0] for v in self.verts]; ys = [v[1] for v in self.verts]
        ox, oy = min(xs) - 8, min(ys) - 8
        w = (max(xs) - ox) // 128 + 1
        h = (max(ys) - oy) // 128 + 1
        blocks = [[] for _ in range(w * h)]
        for li, L in enumerate(self.lines):
            (x0, y0), (x1, y1) = L["p"], L["q"]
            bx0, bx1 = sorted(((x0 - ox) // 128, (x1 - ox) // 128))
            by0, by1 = sorted(((y0 - oy) // 128, (y1 - oy) // 128))
            for by in range(by0, by1 + 1):
                for bx in range(bx0, bx1 + 1):
                    blocks[by * w + bx].append(li)
        body, offsets = b"", []
        base = 4 + w * h
        for b in blocks:
            offsets.append(base + len(body) // 2)
            body += struct.pack("<h", 0) + b"".join(struct.pack("<H", li) for li in b) + struct.pack("<H", 0xFFFF)
        return struct.pack("<hhhh", ox, oy, w, h) + b"".join(struct.pack("<H", o) for o in offsets) + body

    # -- lumps
    def lumps(self):
        things = b"".join(struct.pack("<hhHHH", t["x"], t["y"], t["angle"], t["type"], t["flags"]) for t in self.things)
        linedefs = b"".join(struct.pack("<HHHHHHH", L["v1"], L["v2"], L["flags"], L["special"], L["tag"], L["s0"], L["s1"])
                            for L in self.lines)
        sidedefs = b"".join(struct.pack("<hh8s8s8sH", s["xoff"], s["yoff"], s["upper"].encode(), s["lower"].encode(),
                                        s["mid"].encode(), s["sector"]) for s in self.sides)
        vertexes = b"".join(struct.pack("<hh", x, y) for x, y in self.verts)
        segs = b"".join(struct.pack("<HHHHHH", s["v1"], s["v2"], s["angle"], s["line"], s["side"], s["offset"]) for s in self.segs)
        ssectors = b"".join(struct.pack("<HH", s["numsegs"], s["firstseg"]) for s in self.ssectors)
        nodes = b"".join(struct.pack("<hhhh" + "hhhh" * 2 + "HH", n["x"], n["y"], n["dx"], n["dy"], *n["bbox"][0], *n["bbox"][1],
                                     n["children"][0], n["children"][1]) for n in self.nodes)
        sectors = b"".join(struct.pack("<hh8s8sHHH", s["floor"], s["ceil"], s["floortex"].encode(), s["ceiltex"].encode(),
                                       s["light"], s["special"], s["tag"]) for s in self.sectors)
        reject = bytes((len(self.sectors) ** 2 + 7) // 8)
        return [("MAP01", b""), ("THINGS", things), ("LINEDEFS", linedefs), ("SIDEDEFS", sidedefs),
                ("VERTEXES", vertexes), ("SEGS", segs), ("SSECTORS", ssectors), ("NODES", nodes),
                ("SECTORS", sectors), ("REJECT", reject), ("BLOCKMAP", self.build_blockmap())]

    def check(self):
        used_tex = {s["mid"] for s in self.sides} | {s["upper"] for s in self.sides} | {s["lower"] for s in self.sides}
        used_flat = {s["floortex"] for s in self.sectors} | {s["ceiltex"] for s in self.sectors}
        missing = [t for t in used_tex if t != "-" and t not in self.textures] + [f for f in used_flat if f not in self.flats]
        if missing:
            raise SystemExit("unknown IWAD names: %s" % sorted(set(missing)))
        if sum(1 for t in self.things if t["type"] == 1) != 1:
            raise SystemExit("a card needs exactly one player start")
        if not any(L["special"] == SPECIAL_EXIT for L in self.lines):
            self.warnings.append("no exit switch: the level cannot be finished")
        if len(self.nodes) == 0 and len(self.ssectors) != 1:
            raise SystemExit("bsp: no nodes")


def write_pwad(path, lumps):
    body, entries, pos = b"", [], 12
    for name, data in lumps:
        entries.append((pos, len(data), name)); body += data; pos += len(data)
    out = struct.pack("<4sii", b"PWAD", len(lumps), pos) + body
    for p, s, n in entries:
        out += struct.pack("<ii8s", p, s, n.encode("ascii"))
    with open(path, "wb") as f:
        f.write(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    iwad = os.path.join(HERE, "..", "..", "android", "app", "src", "main", "assets", "freedoom2.wad")
    for a in sys.argv[1:]:
        if a.startswith("--iwad="):
            iwad = a.split("=", 1)[1]
    if len(args) < 2:
        raise SystemExit(__doc__)
    card = json.load(open(args[0], encoding="utf-8"))
    textures, flats = iwad_names(iwad)
    lv = Level(card, textures, flats)
    lv.place(); lv.build_lines(); lv.build_bsp(); lv.check()
    write_pwad(args[1], lv.lumps())
    print("%s -> %s: %d tiles, %d sectors, %d rects, %d verts, %d lines (%d two-sided), %d things, %d segs, %d subsectors, %d nodes, root=%d"
          % (os.path.basename(args[0]), args[1], len(card["tiles"]), len(lv.sectors), len(lv.rects), len(lv.verts), len(lv.lines),
             sum(1 for L in lv.lines if L["back"] is not None), len(lv.things), len(lv.segs), len(lv.ssectors), len(lv.nodes), lv.root))
    for w in lv.warnings:
        print("  warning:", w)


if __name__ == "__main__":
    main()
