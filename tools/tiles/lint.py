#!/usr/bin/env python3
# tools/tiles/lint.py
"""Structural lint for a compiled MAP01 - what the engine would trip over, checked
before the WAD ever reaches a phone: every index in range, two-sided flags agree
with sidedefs, the BSP walked from the root reaches every subsector exactly once
with no cycles, subsector seg ranges are inside SEGS, the BLOCKMAP is well-formed,
REJECT has the right size, and there is exactly one player 1 start.

usage: lint.py <map.wad>
"""
import math, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "prefab"))
import wadlib


def records(b, fmt):
    n = struct.calcsize(fmt)
    return [struct.unpack_from(fmt, b, o) for o in range(0, len(b) - len(b) % n, n)]


def main(path):
    w = wadlib.WAD(path)
    names = [l.name for l in w.lumps]
    need = ["MAP01", "THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SEGS", "SSECTORS", "NODES", "SECTORS", "REJECT", "BLOCKMAP"]
    errors, warnings = [], []
    for n in need:
        if n not in names:
            errors.append("missing lump " + n)
    if errors:
        return report(path, errors, warnings)
    get = lambda n: w.lump_bytes(names.index(n))
    things = records(get("THINGS"), "<hhHHH")
    lines = records(get("LINEDEFS"), "<HHHHHHH")
    sides = records(get("SIDEDEFS"), "<hh8s8s8sH")
    verts = records(get("VERTEXES"), "<hh")
    segs = records(get("SEGS"), "<HHHHHH")
    ssecs = records(get("SSECTORS"), "<HH")
    nodes = records(get("NODES"), "<hhhh" + "hhhh" * 2 + "HH")
    sectors = records(get("SECTORS"), "<hh8s8sHHH")
    for i, (v1, v2, flags, special, tag, s0, s1) in enumerate(lines):
        if v1 >= len(verts) or v2 >= len(verts):
            errors.append("line %d: vertex out of range" % i)
        if v1 == v2:
            errors.append("line %d: zero length" % i)
        if s0 >= len(sides):
            errors.append("line %d: front sidedef out of range" % i)
        if s1 != 0xFFFF and s1 >= len(sides):
            errors.append("line %d: back sidedef out of range" % i)
        if bool(flags & 4) != (s1 != 0xFFFF):
            errors.append("line %d: two-sided flag disagrees with sidedefs" % i)
    for i, s in enumerate(sides):
        if s[5] >= len(sectors):
            errors.append("sidedef %d: sector out of range" % i)
    for i, (v1, v2, angle, line, side, offset) in enumerate(segs):
        if v1 >= len(verts) or v2 >= len(verts):
            errors.append("seg %d: vertex out of range" % i)
        if line >= len(lines):
            errors.append("seg %d: linedef out of range" % i)
        elif side == 1 and lines[line][6] == 0xFFFF:
            errors.append("seg %d: back side of a one-sided line" % i)
        if side not in (0, 1):
            errors.append("seg %d: bad side %d" % (i, side))
    for i, (n, first) in enumerate(ssecs):
        if first + n > len(segs):
            errors.append("subsector %d: seg range past SEGS" % i)
        if n == 0:
            warnings.append("subsector %d has no segs" % i)
    # walk the tree
    visited_ss, visited_nodes = {}, set()
    stack = [len(nodes) - 1] if nodes else []
    if not nodes and len(ssecs) != 1:
        errors.append("no nodes but %d subsectors" % len(ssecs))
    while stack:
        ni = stack.pop()
        if ni in visited_nodes:
            errors.append("node %d reached twice (cycle)" % ni); break
        visited_nodes.add(ni)
        for child in nodes[ni][12:14]:
            if child & 0x8000:
                ssi = child & 0x7FFF
                if ssi >= len(ssecs):
                    errors.append("node %d: subsector %d out of range" % (ni, ssi))
                visited_ss[ssi] = visited_ss.get(ssi, 0) + 1
            else:
                if child >= len(nodes):
                    errors.append("node %d: child node %d out of range" % (ni, child))
                else:
                    stack.append(child)
    for ssi in range(len(ssecs)):
        c = visited_ss.get(ssi, 0)
        if c != 1:
            errors.append("subsector %d visited %d times from the root" % (ssi, c))
    if nodes and len(visited_nodes) != len(nodes):
        warnings.append("%d of %d nodes unreachable from the root" % (len(nodes) - len(visited_nodes), len(nodes)))
    # blockmap
    bm = get("BLOCKMAP")
    ox, oy, bw, bh = struct.unpack_from("<hhhh", bm, 0)
    nshorts = len(bm) // 2
    if 4 + bw * bh > nshorts:
        errors.append("blockmap: offset table past the lump")
    else:
        for k in range(bw * bh):
            off = struct.unpack_from("<H", bm, 8 + 2 * k)[0]
            if off >= nshorts:
                errors.append("blockmap: block %d offset past the lump" % k); break
            if struct.unpack_from("<h", bm, 2 * off)[0] != 0:
                errors.append("blockmap: block %d does not start with 0" % k); break
            j = off + 1
            while j < nshorts and struct.unpack_from("<H", bm, 2 * j)[0] != 0xFFFF:
                li = struct.unpack_from("<H", bm, 2 * j)[0]
                if li >= len(lines):
                    errors.append("blockmap: block %d references line %d" % (k, li)); break
                j += 1
            if j >= nshorts:
                errors.append("blockmap: block %d not terminated" % k); break
    if len(get("REJECT")) != (len(sectors) ** 2 + 7) // 8:
        errors.append("reject: %d bytes, expected %d" % (len(get("REJECT")), (len(sectors) ** 2 + 7) // 8))
    if sum(1 for t in things if t[3] == 1) != 1:
        errors.append("things: need exactly one player 1 start")
    print("%s: %d things, %d lines, %d sides, %d verts, %d sectors, %d segs, %d subsectors, %d nodes, blockmap %dx%d"
          % (os.path.basename(path), len(things), len(lines), len(sides), len(verts), len(sectors), len(segs), len(ssecs),
             len(nodes), bw, bh))
    return report(path, errors, warnings)


def report(path, errors, warnings):
    for w_ in warnings:
        print("  warning:", w_)
    for e in errors:
        print("  ERROR:", e)
    print("  lint:", "FAIL" if errors else "OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
