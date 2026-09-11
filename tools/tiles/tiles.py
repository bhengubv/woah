# tools/tiles/tiles.py
"""The v1 tile catalogue: authored, axis-aligned, socketed.

One cell = 64 map units. A tile is a set of sectors, each a union of rectangles in
cell coordinates; sockets on its outer edges where a door may join a neighbour; and
typed thing slots. Everything is a rectangle on purpose: the compiler builds the BSP
with axis-aligned splits, so every level it emits is loadable by construction.

Sockets: (edge, pos, width) - edge N/E/S/W, pos in cells along that edge from the
tile's min corner, width in cells. A door joins two touching sockets of equal span.
"""
CELL = 64


def T(id, w, h, sectors, sockets, slots=(), exit_edge=None):
    return dict(id=id, w=w, h=h, sectors=list(sectors), sockets=list(sockets),
                slots=list(slots), exit_edge=exit_edge)


def S(rects, floor=0, ceil=128, kind="room"):
    """A sector made of one or more cell rectangles (x0, y0, x1, y1)."""
    if isinstance(rects, tuple):
        rects = [rects]
    return dict(rects=list(rects), floor=floor, ceil=ceil, kind=kind)


def K(edge, pos, width=2):
    return dict(edge=edge, pos=pos, width=width)


def L(x, y, role):
    return dict(x=x, y=y, role=role)


TILES = {
    "start": T("start", 4, 4, [S((0, 0, 4, 4))], [K("E", 1), K("S", 1)],
               [L(2, 2, "player")]),
    "exit": T("exit", 4, 4, [S((0, 0, 4, 4))], [K("W", 1), K("N", 1)], [], exit_edge="E"),
    "hall_ew": T("hall_ew", 4, 2, [S((0, 0, 4, 2), ceil=96, kind="hall")], [K("W", 0), K("E", 0)]),
    "hall_ns": T("hall_ns", 2, 4, [S((0, 0, 2, 4), ceil=96, kind="hall")], [K("N", 0), K("S", 0)]),
    # an L: west opening to the south leg, north opening at the top of the east leg
    "corner_sw_ne": T("corner_sw_ne", 4, 4, [S([(0, 0, 4, 2), (2, 2, 4, 4)], ceil=96, kind="hall")],
                      [K("W", 0), K("N", 2)]),
    "room_s": T("room_s", 4, 4, [S((0, 0, 4, 4))], [K("N", 1), K("E", 1), K("S", 1), K("W", 1)],
                [L(2, 2, "monster_s"), L(1, 1, "ammo")]),
    "room_m": T("room_m", 6, 6, [S((0, 0, 6, 6), ceil=160)], [K("N", 2), K("E", 2), K("S", 2), K("W", 2)],
                [L(1.5, 1.5, "monster_s"), L(4.5, 4.5, "monster_s"), L(3, 3, "health"), L(1.5, 4.5, "ammo")]),
    "room_l": T("room_l", 8, 8, [S((0, 0, 8, 8), ceil=192)], [K("N", 3), K("E", 3), K("S", 3), K("W", 3)],
                [L(2, 2, "monster_m"), L(6, 6, "monster_m"), L(2, 6, "monster_s"), L(6, 2, "monster_s"),
                 L(4, 4, "armor")]),
    # four rectangles of ONE sector around a 2x2 pillar; the pillar faces become walls by construction
    "pillar_room": T("pillar_room", 6, 6, [S([(0, 0, 6, 2), (0, 4, 6, 6), (0, 2, 2, 4), (4, 2, 6, 4)], ceil=160)],
                     [K("N", 2), K("E", 2), K("S", 2), K("W", 2)],
                     [L(1, 1, "monster_s"), L(5, 5, "monster_s"), L(1, 5, "ammo"), L(5, 1, "health")]),
    # four 16-unit steps west to east; place the next tile with "z": 64
    "steps_ew": T("steps_ew", 4, 2, [S((0, 0, 1, 2), floor=0, kind="step"), S((1, 0, 2, 2), floor=16, kind="step"),
                                     S((2, 0, 3, 2), floor=32, kind="step"), S((3, 0, 4, 2), floor=48, kind="step")],
                  [K("W", 0), K("E", 0)]),
}

# Slot roles -> DOOM thing types (Freedoom keeps the doednums). flags 7 = every skill.
ROLE_THINGS = {
    "player": 1, "monster_s": 3001, "monster_m": 3002, "monster_l": 3005,
    "ammo": 2007, "health": 2012, "armor": 2018, "key": 5, "secret": 2013,
}


if __name__ == "__main__":
    # Export the catalogue for the on-device compiler: python3 tiles.py <out.json>
    import json, sys
    out = sys.argv[1] if len(sys.argv) > 1 else "tiles.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"cell": CELL, "tiles": TILES, "roles": ROLE_THINGS}, f, indent=1)
    print("wrote", out, len(TILES), "tiles")
