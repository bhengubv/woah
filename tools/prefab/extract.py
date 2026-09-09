# tools/prefab/extract.py
# First-cut prefab extractor: per-sector "cells" from a WAD, with contained
# things and per-prefab BSD provenance. Off-device. Room-grouping is a later pass.
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wadlib

LICENSE = "Freedoom (BSD 3-Clause) - see android/deps/freedoom-0.13.0/COPYING.txt"

def sector_lines(m, sec_idx):
    out = []
    nsides = len(m['sides'])
    for L in m['lines']:
        s0, s1 = L['s0'], L['s1']
        sec0 = m['sides'][s0]['sector'] if (s0 != 0xFFFF and s0 < nsides) else -1
        sec1 = m['sides'][s1]['sector'] if (s1 != 0xFFFF and s1 < nsides) else -1
        if sec0 == sec_idx or sec1 == sec_idx:
            out.append(L)
    return out

def extract_cells(w, marker_idx, mapname, wadname):
    m = wadlib.parse_map(w, marker_idx)
    nv = len(m['verts'])
    cells = []
    for si, sec in enumerate(m['sectors']):
        lines = sector_lines(m, si)
        if not lines:
            continue
        vids = set()
        for L in lines:
            vids.add(L['v1']); vids.add(L['v2'])
        vs = [m['verts'][v] for v in vids if v < nv]
        if not vs:
            continue
        xs = [v[0] for v in vs]; ys = [v[1] for v in vs]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        things = [t for t in m['things'] if bbox[0] <= t['x'] <= bbox[2] and bbox[1] <= t['y'] <= bbox[3]]
        cells.append(dict(
            source="%s/%s/sector%d" % (wadname, mapname, si),
            license=LICENSE,
            floor=sec['floor'], ceil=sec['ceil'],
            floortex=sec['floortex'], ceiltex=sec['ceiltex'],
            nlines=len(lines), nverts=len(vs), bbox=bbox, things=things))
    return cells

if __name__ == '__main__':
    wadpath = sys.argv[1]
    wadname = os.path.basename(wadpath)
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
    os.makedirs(outdir, exist_ok=True)
    w = wadlib.WAD(wadpath)
    total = 0
    for idx, name in w.maps():
        cells = extract_cells(w, idx, name, wadname)
        total += len(cells)
        with open(os.path.join(outdir, "%s_%s.cells.json" % (wadname, name)), 'w') as f:
            json.dump(cells, f)
    print("extracted %d cell-prefabs across %d maps -> %s" % (total, len(w.maps()), outdir))
    import glob
    g = glob.glob(os.path.join(outdir, "*MAP01.cells.json"))
    if g:
        c = json.load(open(g[0]))
        print("MAP01: %d cells; example cell:" % len(c))
        print(json.dumps(c[0], indent=1)[:700] if c else "none")
