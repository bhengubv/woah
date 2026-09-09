# tools/prefab/wadlib.py
# Off-device WAD/map reader for the Circle OS DOOM prefab pipeline.
# Reads Freedoom (BSD) maps into raw source geometry + things for prefab extraction.
# Runs on .201/desktop only; the phone never parses WADs.
import struct, sys, os

class Lump:
    __slots__ = ('name', 'pos', 'size')
    def __init__(s, name, pos, size):
        s.name, s.pos, s.size = name, pos, size

class WAD:
    def __init__(s, path):
        s.path = path
        with open(path, 'rb') as f:
            s.data = f.read()
        magic, n, dirofs = struct.unpack_from('<4sii', s.data, 0)
        s.magic = magic.decode('ascii', 'replace')
        s.lumps = []
        o = dirofs
        for i in range(n):
            pos, size, name = struct.unpack_from('<ii8s', s.data, o)
            o += 16
            s.lumps.append(Lump(name.rstrip(b'\0').decode('ascii', 'replace'), pos, size))

    def lump_bytes(s, idx):
        L = s.lumps[idx]
        return s.data[L.pos:L.pos + L.size]

    def maps(s):
        out = []
        for i in range(len(s.lumps) - 1):
            if s.lumps[i + 1].name == 'THINGS':
                out.append((i, s.lumps[i].name))
        return out

    def after(s, marker_idx, name):
        for j in range(marker_idx + 1, min(marker_idx + 11, len(s.lumps))):
            if s.lumps[j].name == name:
                return j
        return None

def _str8(b):
    return b.rstrip(b'\0').decode('ascii', 'replace')

def parse_map(w, marker_idx):
    def lb(name):
        j = w.after(marker_idx, name)
        return w.lump_bytes(j) if j is not None else b''
    b = lb('VERTEXES')
    verts = [struct.unpack_from('<hh', b, o) for o in range(0, len(b), 4)]
    b = lb('THINGS'); things = []
    for o in range(0, len(b), 10):
        x, y, a, t, fl = struct.unpack_from('<hhHHH', b, o)
        things.append(dict(x=x, y=y, angle=a, type=t, flags=fl))
    b = lb('LINEDEFS'); lines = []
    for o in range(0, len(b), 14):
        v1, v2, flags, spec, tag, s0, s1 = struct.unpack_from('<HHHHHHH', b, o)
        lines.append(dict(v1=v1, v2=v2, flags=flags, special=spec, tag=tag, s0=s0, s1=s1))
    b = lb('SIDEDEFS'); sides = []
    for o in range(0, len(b), 30):
        xo, yo, up, lo, mid, sec = struct.unpack_from('<hh8s8s8sH', b, o)
        sides.append(dict(xoff=xo, yoff=yo, upper=_str8(up), lower=_str8(lo), mid=_str8(mid), sector=sec))
    b = lb('SECTORS'); secs = []
    for o in range(0, len(b), 26):
        fh, ch, ft, ct, li, sp, tg = struct.unpack_from('<hh8s8sHHH', b, o)
        secs.append(dict(floor=fh, ceil=ch, floortex=_str8(ft), ceiltex=_str8(ct), light=li, special=sp, tag=tg))
    return dict(verts=verts, things=things, lines=lines, sides=sides, sectors=secs)

if __name__ == '__main__':
    path = sys.argv[1]
    w = WAD(path)
    ms = w.maps()
    print("WAD %s  magic=%s  lumps=%d  maps=%d" % (os.path.basename(path), w.magic, len(w.lumps), len(ms)))
    print("maps: " + ", ".join(n for _, n in ms))
    if ms:
        idx, name = ms[0]
        m = parse_map(w, idx)
        xs = [v[0] for v in m['verts']]; ys = [v[1] for v in m['verts']]
        two_sided = sum(1 for L in m['lines'] if L['s1'] != 0xFFFF)
        print("%s: verts=%d lines=%d (2-sided=%d) sides=%d sectors=%d things=%d bbox=(%d,%d)-(%d,%d)" % (
            name, len(m['verts']), len(m['lines']), two_sided, len(m['sides']),
            len(m['sectors']), len(m['things']), min(xs), min(ys), max(xs), max(ys)))
