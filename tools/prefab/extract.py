# tools/prefab/extract.py
# Prefab pipeline, pass 2 (off-device). Per-sector "cells" from Freedoom maps with:
#  - things assigned ONCE, to the smallest cell whose box holds them (pass 1 used
#    plain box containment, so big rooms swallowed everything inside them);
#  - map-level things (player/deathmatch starts, teleport landings) kept OUT of
#    cells - they belong to the map, and leaked into cells in pass 1;
#  - a dressing palette across the WAD: floor/ceiling pairings, wall textures per
#    floor, light levels, room heights, monster mixes by room size. This is what
#    the tile editor draws on: Freedoom (BSD) supplies the look, not the geometry.
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wadlib

LICENSE = "Freedoom (BSD 3-Clause) - see android/deps/freedoom-0.13.0/COPYING.txt"
MAP_LEVEL_THINGS = {1, 2, 3, 4, 11, 14}   # player starts, deathmatch start, teleport landing
MONSTERS = {3004: "zombieman", 9: "shotgunner", 65: "chaingunner", 3001: "imp", 3002: "demon",
            58: "spectre", 3006: "lost soul", 3005: "cacodemon", 69: "hell knight", 3003: "baron",
            68: "arachnotron", 71: "pain elemental", 66: "revenant", 67: "mancubus", 64: "arch-vile",
            7: "spider mastermind", 16: "cyberdemon", 84: "ss", 72: "keen"}

def sector_lines(m, sec_idx):
    out, nsides = [], len(m['sides'])
    for L in m['lines']:
        s0, s1 = L['s0'], L['s1']
        sec0 = m['sides'][s0]['sector'] if (s0 != 0xFFFF and s0 < nsides) else -1
        sec1 = m['sides'][s1]['sector'] if (s1 != 0xFFFF and s1 < nsides) else -1
        if sec0 == sec_idx or sec1 == sec_idx:
            out.append(L)
    return out

def size_bucket(area):
    return 'S' if area < 128 * 128 else 'M' if area < 512 * 512 else 'L'

def cells_for_map(w, marker_idx, mapname, wadname):
    m = wadlib.parse_map(w, marker_idx)
    nv, nsides = len(m['verts']), len(m['sides'])
    cells = []
    for si, sec in enumerate(m['sectors']):
        lines = sector_lines(m, si)
        if not lines:
            continue
        vids = {L['v1'] for L in lines} | {L['v2'] for L in lines}
        vs = [m['verts'][v] for v in vids if v < nv]
        if not vs:
            continue
        xs = [v[0] for v in vs]; ys = [v[1] for v in vs]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        walls = collections.Counter()
        for L in lines:
            if L['s1'] == 0xFFFF and L['s0'] != 0xFFFF and L['s0'] < nsides:   # one-sided = a wall
                t = m['sides'][L['s0']]['mid']
                if t and t != '-':
                    walls[t] += 1
        cells.append(dict(
            source="%s/%s/sector%d" % (wadname, mapname, si), license=LICENSE,
            floor=sec['floor'], ceil=sec['ceil'], height=sec['ceil'] - sec['floor'],
            floortex=sec['floortex'], ceiltex=sec['ceiltex'], light=sec['light'], special=sec['special'],
            walls=[t for t, _ in walls.most_common(4)], nlines=len(lines), nverts=len(vs),
            bbox=bbox, area=(bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), things=[]))
    map_things, unplaced = [], 0
    for t in m['things']:
        if t['type'] in MAP_LEVEL_THINGS:
            map_things.append(t)
            continue
        best = None
        for c in cells:
            b = c['bbox']
            if b[0] <= t['x'] <= b[2] and b[1] <= t['y'] <= b[3] and (best is None or c['area'] < best['area']):
                best = c
        if best is None:
            unplaced += 1
        else:
            best['things'].append(t)
    return cells, map_things, unplaced

def add_to_palette(pal, cells):
    for c in cells:
        pal['floor_ceil'][(c['floortex'], c['ceiltex'])] += 1
        for wtex in c['walls']:
            pal['wall_for_floor'][(c['floortex'], wtex)] += 1
        pal['light'][c['light']] += 1
        pal['height'][c['height']] += 1
        mons = sorted({MONSTERS[t['type']] for t in c['things'] if t['type'] in MONSTERS})
        if mons:
            pal['monsters_by_size'][size_bucket(c['area'])][tuple(mons)] += 1

def top(counter, n):
    return [[list(k) if isinstance(k, tuple) else k, v] for k, v in counter.most_common(n)]

if __name__ == '__main__':
    wadpath = sys.argv[1]
    wadname = os.path.basename(wadpath)
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
    os.makedirs(outdir, exist_ok=True)
    w = wadlib.WAD(wadpath)
    pal = dict(floor_ceil=collections.Counter(), wall_for_floor=collections.Counter(),
               light=collections.Counter(), height=collections.Counter(),
               monsters_by_size={'S': collections.Counter(), 'M': collections.Counter(), 'L': collections.Counter()})
    total_cells = total_things = total_map = total_unplaced = 0
    for idx, name in w.maps():
        cells, map_things, unplaced = cells_for_map(w, idx, name, wadname)
        add_to_palette(pal, cells)
        total_cells += len(cells); total_map += len(map_things); total_unplaced += unplaced
        total_things += sum(len(c['things']) for c in cells)
        with open(os.path.join(outdir, "%s_%s.cells.json" % (wadname, name)), 'w') as f:
            json.dump(cells, f)
        with open(os.path.join(outdir, "%s_%s.map.json" % (wadname, name)), 'w') as f:
            json.dump(dict(source="%s/%s" % (wadname, name), license=LICENSE, things=map_things), f)
    out = dict(source=wadname, license=LICENSE,
               floor_ceil=top(pal['floor_ceil'], 40), wall_for_floor=top(pal['wall_for_floor'], 60),
               light=top(pal['light'], 20), height=top(pal['height'], 20),
               monsters_by_size={k: top(v, 15) for k, v in pal['monsters_by_size'].items()})
    with open(os.path.join(outdir, "%s.palettes.json" % wadname), 'w') as f:
        json.dump(out, f, indent=1)
    print("%d cells across %d maps; %d things placed once, %d map-level things kept out of cells, %d things in no cell"
          % (total_cells, len(w.maps()), total_things, total_map, total_unplaced))
    leaked = sum(1 for idx, name in w.maps() for c in json.load(open(os.path.join(outdir, "%s_%s.cells.json" % (wadname, name))))
                 for t in c['things'] if t['type'] in MAP_LEVEL_THINGS)
    print("player/deathmatch starts inside cells now: %d" % leaked)
    print("top floor/ceiling pairs:", out['floor_ceil'][:5])
    print("top wall-for-floor:", out['wall_for_floor'][:5])
    print("light levels:", out['light'][:6])
    print("room heights:", out['height'][:6])
    for k in ('S', 'M', 'L'):
        print("monster mixes (%s):" % k, out['monsters_by_size'][k][:4])
