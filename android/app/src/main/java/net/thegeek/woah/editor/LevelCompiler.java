package net.thegeek.woah.editor;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * A level card -> a playable PWAD (MAP01). A line-for-line port of tools/tiles/compile.py:
 * same placement, same line generation, same axis-aligned BSP, same lump packing - the
 * golden test asserts the two produce identical bytes for the same card.
 */
public final class LevelCompiler {

    static final int ML_BLOCKING = 1, ML_TWOSIDED = 4, SPECIAL_EXIT = 11;
    static final String[] EXIT_SWITCH = {"SW1EXIT", "SW1BRCOM", "SW1COMM"};
    static final Map<String, String[]> DRESS = new HashMap<>();   // floor, ceil, wall, light
    static {
        DRESS.put("tech", new String[]{"CEIL5_2", "CEIL5_2", "METAL", "160"});
        DRESS.put("base", new String[]{"FLOOR5_4", "FLOOR5_4", "BRICK6", "144"});
        DRESS.put("hell", new String[]{"FLOOR7_2", "FLOOR7_2", "SUPPORT3", "128"});
    }

    static final class Sector { int floor, ceil, light, tile; String floortex, ceiltex, wall; }
    static final class Rect { int x0, y0, x1, y1, sector, tile; Rect copy() { Rect r = new Rect(); r.x0 = x0; r.y0 = y0; r.x1 = x1; r.y1 = y1; r.sector = sector; r.tile = tile; return r; } }
    static final class Line { int v1, v2, flags, special, s0, s1, front, back; int[] p, q; }
    static final class Side { String upper, lower, mid; int sector; }
    static final class Thing { int x, y, type; }
    static final class Seg { int v1, v2, angle, line, side, offset; }
    static final class Node { int x, y, dx, dy; int[][] bbox; int[] children; }
    static final class Door { boolean horiz; int coord, lo, hi; }

    final Tiles tiles;
    final Set<String> textures, flats;
    final String exitSwitch;

    JSONArray cardTiles;
    int grid;
    final List<Sector> sectors = new ArrayList<>();
    final List<Rect> rects = new ArrayList<>();
    final Map<String, Door> doors = new HashMap<>();
    final List<int[]> verts = new ArrayList<>();
    final Map<Long, Integer> vindex = new LinkedHashMap<>();
    final List<Line> lines = new ArrayList<>();
    final List<Side> sides = new ArrayList<>();
    final List<Thing> things = new ArrayList<>();
    final List<Seg> segs = new ArrayList<>();
    final List<int[]> ssectors = new ArrayList<>();
    final List<Node> nodes = new ArrayList<>();
    public final List<String> warnings = new ArrayList<>();
    int root;

    public LevelCompiler(Tiles tiles, Set<String> textures, Set<String> flats) {
        this.tiles = tiles;
        this.textures = textures;
        this.flats = flats;
        String sw = EXIT_SWITCH[EXIT_SWITCH.length - 1];
        for (String t : EXIT_SWITCH) if (textures.contains(t)) { sw = t; break; }
        exitSwitch = sw;
    }

    public byte[] compile(String cardJson) throws JSONException {
        JSONObject card = new JSONObject(cardJson);
        place(card);
        buildLines(card);
        buildBsp();
        check();
        return pwad();
    }

    // ---- placement
    void place(JSONObject card) throws JSONException {
        grid = card.optInt("grid", tiles.cell);
        cardTiles = card.getJSONArray("tiles");
        for (int ti = 0; ti < cardTiles.length(); ti++) {
            JSONObject t = cardTiles.getJSONObject(ti);
            Tiles.Tile tile = tiles.tiles.get(t.getString("t"));
            if (tile == null) throw new IllegalArgumentException("unknown tile " + t.getString("t"));
            String[] dress = DRESS.get(t.optString("dress", "tech"));
            int ox = t.getInt("x") * grid, oy = t.getInt("y") * grid, z = t.optInt("z", 0);
            for (Tiles.Sector sec : tile.sectors) {
                int si = sectors.size();
                Sector s = new Sector();
                s.floor = sec.floor + z; s.ceil = sec.ceil + z;
                s.floortex = dress[0]; s.ceiltex = dress[1]; s.wall = dress[2]; s.light = Integer.parseInt(dress[3]);
                s.tile = ti;
                sectors.add(s);
                for (int[] r : sec.rects) {
                    Rect rc = new Rect();
                    rc.x0 = ox + r[0] * grid; rc.y0 = oy + r[1] * grid; rc.x1 = ox + r[2] * grid; rc.y1 = oy + r[3] * grid;
                    rc.sector = si; rc.tile = ti;
                    rects.add(rc);
                }
            }
            for (Tiles.Slot sl : tile.slots) {
                Thing th = new Thing();
                th.x = (int) (ox + sl.x * grid); th.y = (int) (oy + sl.y * grid);
                th.type = tiles.roles.get(sl.role);
                things.add(th);
            }
        }
        JSONArray ds = card.optJSONArray("doors");
        if (ds != null) {
            for (int i = 0; i < ds.length(); i++) {
                int a = ds.getJSONArray(i).getInt(0), b = ds.getJSONArray(i).getInt(1);
                Door d = doorSpan(a, b);
                if (d == null) throw new IllegalArgumentException("door " + a + "-" + b + ": sockets do not touch with equal span");
                doors.put(a + "," + b, d);
                doors.put(b + "," + a, d);
            }
        }
    }

    /** [edge, fixed, lo, hi] per socket of placed tile ti, in absolute units. */
    List<Object[]> socketSpans(int ti) throws JSONException {
        JSONObject t = cardTiles.getJSONObject(ti);
        Tiles.Tile tile = tiles.tiles.get(t.getString("t"));
        int ox = t.getInt("x") * grid, oy = t.getInt("y") * grid;
        List<Object[]> out = new ArrayList<>();
        for (Tiles.Socket k : tile.sockets) {
            if (k.edge.equals("N") || k.edge.equals("S")) {
                int y = oy + (k.edge.equals("N") ? tile.h : 0) * grid;
                out.add(new Object[]{k.edge, y, ox + k.pos * grid, ox + (k.pos + k.width) * grid});
            } else {
                int x = ox + (k.edge.equals("E") ? tile.w : 0) * grid;
                out.add(new Object[]{k.edge, x, oy + k.pos * grid, oy + (k.pos + k.width) * grid});
            }
        }
        return out;
    }

    static String opposite(String e) {
        switch (e) { case "N": return "S"; case "S": return "N"; case "E": return "W"; default: return "E"; }
    }

    Door doorSpan(int a, int b) throws JSONException {
        for (Object[] sa : socketSpans(a)) {
            for (Object[] sb : socketSpans(b)) {
                if (sb[0].equals(opposite((String) sa[0])) && sa[1].equals(sb[1]) && sa[2].equals(sb[2]) && sa[3].equals(sb[3])) {
                    Door d = new Door();
                    String e = (String) sa[0];
                    d.horiz = e.equals("N") || e.equals("S");
                    d.coord = (Integer) sa[1]; d.lo = (Integer) sa[2]; d.hi = (Integer) sa[3];
                    return d;
                }
            }
        }
        return null;
    }

    // ---- lines
    int vertex(int x, int y) {
        long k = ((long) x << 32) | (y & 0xffffffffL);
        Integer i = vindex.get(k);
        if (i == null) {
            i = verts.size();
            vindex.put(k, i);
            verts.add(new int[]{x, y});
        }
        return i;
    }

    int addSide(int sector, String upper, String lower, String mid) {
        Side s = new Side();
        s.upper = upper; s.lower = lower; s.mid = mid; s.sector = sector;
        sides.add(s);
        return sides.size() - 1;
    }

    void addLine(int[] p, int[] q, int front, int back, int special, boolean exitFace) {
        Sector fs = sectors.get(front);
        Line L = new Line();
        L.v1 = vertex(p[0], p[1]); L.v2 = vertex(q[0], q[1]);
        L.p = p; L.q = q; L.front = front; L.back = back;
        if (back < 0) {
            L.s0 = addSide(front, "-", "-", exitFace ? exitSwitch : fs.wall);
            L.s1 = 0xFFFF; L.flags = ML_BLOCKING; L.special = special;
        } else {
            Sector bs = sectors.get(back);
            L.s0 = addSide(front, fs.wall, fs.wall, "-");
            L.s1 = addSide(back, bs.wall, bs.wall, "-");
            L.flags = ML_TWOSIDED; L.special = 0;
        }
        lines.add(L);
    }

    static List<int[]> spansSubtract(int a, int b, List<int[]> cuts) {
        List<int[]> sorted = new ArrayList<>(cuts);
        // Collections.sort, not List.sort: the latter is API 24+ and minSdk is 21
        java.util.Collections.sort(sorted, (u, v) -> u[0] != v[0] ? Integer.compare(u[0], v[0]) : Integer.compare(u[1], v[1]));
        List<int[]> out = new ArrayList<>();
        for (int[] c : sorted) {
            int c0 = Math.max(c[0], a), c1 = Math.min(c[1], b);
            if (c1 <= a) continue;
            if (c0 > a) out.add(new int[]{a, c0});
            a = Math.max(a, c1);
            if (a >= b) break;
        }
        if (a < b) out.add(new int[]{a, b});
        return out;
    }

    static int[][] edgePoints(String edge, int fixed, int lo, int hi) {
        switch (edge) {
            case "N": return new int[][]{{lo, fixed}, {hi, fixed}};
            case "S": return new int[][]{{hi, fixed}, {lo, fixed}};
            case "E": return new int[][]{{fixed, hi}, {fixed, lo}};
            default:  return new int[][]{{fixed, lo}, {fixed, hi}};
        }
    }

    void wall(String edge, int fixed, int lo, int hi, int sector, boolean exitFace) {
        int[][] pq = edgePoints(edge, fixed, lo, hi);
        addLine(pq[0], pq[1], sector, -1, exitFace ? SPECIAL_EXIT : 0, exitFace);
    }

    void buildLines(JSONObject card) throws JSONException {
        Map<Integer, Object[]> exitEdges = new HashMap<>();
        for (int ti = 0; ti < cardTiles.length(); ti++) {
            JSONObject t = cardTiles.getJSONObject(ti);
            Tiles.Tile tile = tiles.tiles.get(t.getString("t"));
            if (tile.exitEdge != null) {
                int ox = t.getInt("x") * grid, oy = t.getInt("y") * grid;
                int coord;
                switch (tile.exitEdge) {
                    case "N": coord = oy + tile.h * grid; break;
                    case "S": coord = oy; break;
                    case "E": coord = ox + tile.w * grid; break;
                    default: coord = ox;
                }
                exitEdges.put(ti, new Object[]{tile.exitEdge, coord});
            }
        }
        String[] EDGES = {"N", "S", "E", "W"};
        for (int ri = 0; ri < rects.size(); ri++) {
            Rect r = rects.get(ri);
            for (String edge : EDGES) {
                boolean horiz = edge.equals("N") || edge.equals("S");
                int fixed = edge.equals("N") ? r.y1 : edge.equals("S") ? r.y0 : edge.equals("E") ? r.x1 : r.x0;
                int sp0 = horiz ? r.x0 : r.y0, sp1 = horiz ? r.x1 : r.y1;
                List<int[]> openCuts = new ArrayList<>();
                List<int[]> twoSided = new ArrayList<>();      // lo, hi, rj
                for (int rj = 0; rj < rects.size(); rj++) {
                    if (rj == ri) continue;
                    Rect o = rects.get(rj);
                    int ofixed = edge.equals("N") ? o.y0 : edge.equals("S") ? o.y1 : edge.equals("E") ? o.x0 : o.x1;
                    if (ofixed != fixed) continue;
                    int os0 = horiz ? o.x0 : o.y0, os1 = horiz ? o.x1 : o.y1;
                    int lo = Math.max(sp0, os0), hi = Math.min(sp1, os1);
                    if (hi <= lo) continue;
                    if (o.sector == r.sector) openCuts.add(new int[]{lo, hi});
                    else if (o.tile == r.tile) twoSided.add(new int[]{lo, hi, rj});
                    else {
                        Door d = doors.get(r.tile + "," + o.tile);
                        if (d != null && d.horiz == horiz && d.coord == fixed) {
                            int dlo = Math.max(lo, d.lo), dhi = Math.min(hi, d.hi);
                            if (dhi > dlo) twoSided.add(new int[]{dlo, dhi, rj});
                        }
                    }
                }
                List<int[]> cuts = new ArrayList<>(openCuts);
                for (int[] ts : twoSided) cuts.add(new int[]{ts[0], ts[1]});
                Object[] ex = exitEdges.get(r.tile);
                boolean exitFace = ex != null && ex[0].equals(edge) && (Integer) ex[1] == fixed;
                for (int[] w : spansSubtract(sp0, sp1, cuts)) {
                    int lo = w[0], hi = w[1];
                    if (exitFace && hi - lo > 128) {
                        int mid = (lo + hi) / 2;
                        wall(edge, fixed, lo, mid - 32, r.sector, false);
                        wall(edge, fixed, mid - 32, mid + 32, r.sector, true);
                        wall(edge, fixed, mid + 32, hi, r.sector, false);
                    } else {
                        wall(edge, fixed, lo, hi, r.sector, exitFace);
                    }
                }
                if (edge.equals("N") || edge.equals("E")) {
                    for (int[] ts : twoSided) {
                        int[][] pq = edgePoints(edge, fixed, ts[0], ts[1]);
                        addLine(pq[0], pq[1], r.sector, rects.get(ts[2]).sector, 0, false);
                    }
                }
            }
        }
    }

    // ---- BSP by axis-aligned splits over rectangles
    void buildBsp() {
        List<Rect> leaves = new ArrayList<>();
        for (Rect r : rects) leaves.add(r.copy());
        root = split(leaves);
    }

    int split(List<Rect> rs) {
        if (rs.size() == 1) return 0x8000 | leaf(rs.get(0));
        TreeSet<Integer> xs = new TreeSet<>(), ys = new TreeSet<>();
        for (Rect r : rs) { xs.add(r.x0); xs.add(r.x1); ys.add(r.y0); ys.add(r.y1); }
        Integer[] xa = xs.toArray(new Integer[0]), ya = ys.toArray(new Integer[0]);
        int bestScore = Integer.MAX_VALUE, bestC = 0;
        boolean bestX = true, found = false;
        for (int axis = 0; axis < 2; axis++) {
            Integer[] cands = axis == 0 ? xa : ya;
            for (int i = 1; i < cands.length - 1; i++) {
                int c = cands[i], cut = 0, left = 0, right = 0;
                for (Rect r : rs) {
                    int lo = axis == 0 ? r.x0 : r.y0, hi = axis == 0 ? r.x1 : r.y1;
                    if (lo < c && c < hi) cut++;
                    if (hi <= c) left++;
                    if (lo >= c) right++;
                }
                if (cut == 0 && (left == 0 || right == 0)) continue;
                int score = cut * 10 + Math.abs(left - right);
                if (!found || score < bestScore) { found = true; bestScore = score; bestX = axis == 0; bestC = c; }
            }
        }
        if (!found) throw new IllegalStateException("bsp: cannot split " + rs.size() + " rectangles");
        List<Rect> loSet = new ArrayList<>(), hiSet = new ArrayList<>();
        for (Rect r : rs) {
            int lo = bestX ? r.x0 : r.y0, hi = bestX ? r.x1 : r.y1;
            if (hi <= bestC) loSet.add(r);
            else if (lo >= bestC) hiSet.add(r);
            else {
                Rect a = r.copy(), b = r.copy();
                if (bestX) { a.x1 = bestC; b.x0 = bestC; } else { a.y1 = bestC; b.y0 = bestC; }
                loSet.add(a); hiSet.add(b);
            }
        }
        Node n = new Node();
        List<Rect> right, left;
        if (bestX) {
            int miny = Integer.MAX_VALUE; for (Rect r : rs) miny = Math.min(miny, r.y0);
            n.x = bestC; n.y = miny; n.dx = 0; n.dy = 1;          // points +y: right side is +x
            right = hiSet; left = loSet;
        } else {
            int minx = Integer.MAX_VALUE; for (Rect r : rs) minx = Math.min(minx, r.x0);
            n.x = minx; n.y = bestC; n.dx = 1; n.dy = 0;          // points +x: right side is -y
            right = loSet; left = hiSet;
        }
        int c0 = split(right), c1 = split(left);
        n.bbox = new int[][]{bbox(right), bbox(left)};
        n.children = new int[]{c0, c1};
        nodes.add(n);
        return nodes.size() - 1;
    }

    static int[] bbox(List<Rect> rs) {   // top, bottom, left, right
        int top = Integer.MIN_VALUE, bottom = Integer.MAX_VALUE, left = Integer.MAX_VALUE, right = Integer.MIN_VALUE;
        for (Rect r : rs) { top = Math.max(top, r.y1); bottom = Math.min(bottom, r.y0); left = Math.min(left, r.x0); right = Math.max(right, r.x1); }
        return new int[]{top, bottom, left, right};
    }

    int leaf(Rect r) {
        int first = segs.size();
        for (int li = 0; li < lines.size(); li++) {
            Line L = lines.get(li);
            for (int side = 0; side < 2; side++) {
                int sec = side == 0 ? L.front : L.back;
                if (sec != r.sector) continue;
                int[] p = L.p, q = L.q;
                boolean horiz = p[1] == q[1];
                int fixed = horiz ? p[1] : p[0];
                boolean onEdge = horiz ? (fixed == r.y0 || fixed == r.y1) : (fixed == r.x0 || fixed == r.x1);
                if (!onEdge) continue;
                int lo = horiz ? Math.min(p[0], q[0]) : Math.min(p[1], q[1]);
                int hi = horiz ? Math.max(p[0], q[0]) : Math.max(p[1], q[1]);
                int rlo = horiz ? r.x0 : r.y0, rhi = horiz ? r.x1 : r.y1;
                int a = Math.max(lo, rlo), b = Math.min(hi, rhi);
                if (b <= a) continue;
                int[] s, e;
                if (horiz) {
                    if (p[0] < q[0]) { s = new int[]{a, fixed}; e = new int[]{b, fixed}; } else { s = new int[]{b, fixed}; e = new int[]{a, fixed}; }
                } else {
                    if (p[1] < q[1]) { s = new int[]{fixed, a}; e = new int[]{fixed, b}; } else { s = new int[]{fixed, b}; e = new int[]{fixed, a}; }
                }
                if (side == 1) { int[] t = s; s = e; e = t; }
                int[] start = side == 0 ? p : q;
                Seg sg = new Seg();
                sg.offset = Math.abs(s[0] - start[0]) + Math.abs(s[1] - start[1]);
                double ang = Math.atan2(e[1] - s[1], e[0] - s[0]);
                sg.angle = ((int) (ang / (2 * Math.PI) * 65536)) & 0xFFFF;
                sg.v1 = vertex(s[0], s[1]); sg.v2 = vertex(e[0], e[1]);
                sg.line = li; sg.side = side;
                segs.add(sg);
            }
        }
        int n = segs.size() - first;
        if (n == 0) warnings.add("subsector with no segs at " + r.x0 + "," + r.y0 + "-" + r.x1 + "," + r.y1);
        ssectors.add(new int[]{n, first});
        return ssectors.size() - 1;
    }

    // ---- blockmap / lumps
    byte[] blockmap() {
        int minx = Integer.MAX_VALUE, miny = Integer.MAX_VALUE, maxx = Integer.MIN_VALUE, maxy = Integer.MIN_VALUE;
        for (int[] v : verts) { minx = Math.min(minx, v[0]); miny = Math.min(miny, v[1]); maxx = Math.max(maxx, v[0]); maxy = Math.max(maxy, v[1]); }
        int ox = minx - 8, oy = miny - 8, w = (maxx - ox) / 128 + 1, h = (maxy - oy) / 128 + 1;
        List<List<Integer>> blocks = new ArrayList<>();
        for (int i = 0; i < w * h; i++) blocks.add(new ArrayList<>());
        for (int li = 0; li < lines.size(); li++) {
            Line L = lines.get(li);
            int bx0 = Math.min((L.p[0] - ox) / 128, (L.q[0] - ox) / 128), bx1 = Math.max((L.p[0] - ox) / 128, (L.q[0] - ox) / 128);
            int by0 = Math.min((L.p[1] - oy) / 128, (L.q[1] - oy) / 128), by1 = Math.max((L.p[1] - oy) / 128, (L.q[1] - oy) / 128);
            for (int by = by0; by <= by1; by++) for (int bx = bx0; bx <= bx1; bx++) blocks.get(by * w + bx).add(li);
        }
        int bodyShorts = 0;
        for (List<Integer> b : blocks) bodyShorts += 2 + b.size();
        ByteBuffer out = ByteBuffer.allocate(2 * (4 + w * h + bodyShorts)).order(ByteOrder.LITTLE_ENDIAN);
        out.putShort((short) ox).putShort((short) oy).putShort((short) w).putShort((short) h);
        int off = 4 + w * h;
        for (List<Integer> b : blocks) { out.putShort((short) off); off += 2 + b.size(); }
        for (List<Integer> b : blocks) {
            out.putShort((short) 0);
            for (int li : b) out.putShort((short) li);
            out.putShort((short) 0xFFFF);
        }
        return out.array();
    }

    byte[] pwad() {
        ByteBuffer b;
        b = ByteBuffer.allocate(10 * things.size()).order(ByteOrder.LITTLE_ENDIAN);
        for (Thing t : things) b.putShort((short) t.x).putShort((short) t.y).putShort((short) 0).putShort((short) t.type).putShort((short) 7);
        byte[] thingsL = b.array();
        b = ByteBuffer.allocate(14 * lines.size()).order(ByteOrder.LITTLE_ENDIAN);
        for (Line L : lines) b.putShort((short) L.v1).putShort((short) L.v2).putShort((short) L.flags).putShort((short) L.special).putShort((short) 0).putShort((short) L.s0).putShort((short) L.s1);
        byte[] linedefs = b.array();
        b = ByteBuffer.allocate(30 * sides.size()).order(ByteOrder.LITTLE_ENDIAN);
        for (Side s : sides) { b.putShort((short) 0).putShort((short) 0); Wad.putName8(b, s.upper); Wad.putName8(b, s.lower); Wad.putName8(b, s.mid); b.putShort((short) s.sector); }
        byte[] sidedefs = b.array();
        b = ByteBuffer.allocate(4 * verts.size()).order(ByteOrder.LITTLE_ENDIAN);
        for (int[] v : verts) b.putShort((short) v[0]).putShort((short) v[1]);
        byte[] vertexes = b.array();
        b = ByteBuffer.allocate(12 * segs.size()).order(ByteOrder.LITTLE_ENDIAN);
        for (Seg s : segs) b.putShort((short) s.v1).putShort((short) s.v2).putShort((short) s.angle).putShort((short) s.line).putShort((short) s.side).putShort((short) s.offset);
        byte[] segsL = b.array();
        b = ByteBuffer.allocate(4 * ssectors.size()).order(ByteOrder.LITTLE_ENDIAN);
        for (int[] s : ssectors) b.putShort((short) s[0]).putShort((short) s[1]);
        byte[] ssectorsL = b.array();
        b = ByteBuffer.allocate(28 * nodes.size()).order(ByteOrder.LITTLE_ENDIAN);
        for (Node n : nodes) {
            b.putShort((short) n.x).putShort((short) n.y).putShort((short) n.dx).putShort((short) n.dy);
            for (int[] bb : n.bbox) for (int v : bb) b.putShort((short) v);
            b.putShort((short) n.children[0]).putShort((short) n.children[1]);
        }
        byte[] nodesL = b.array();
        b = ByteBuffer.allocate(26 * sectors.size()).order(ByteOrder.LITTLE_ENDIAN);
        for (Sector s : sectors) { b.putShort((short) s.floor).putShort((short) s.ceil); Wad.putName8(b, s.floortex); Wad.putName8(b, s.ceiltex); b.putShort((short) s.light).putShort((short) 0).putShort((short) 0); }
        byte[] sectorsL = b.array();
        byte[] reject = new byte[(sectors.size() * sectors.size() + 7) / 8];
        List<String> names = Arrays.asList("MAP01", "THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SEGS", "SSECTORS", "NODES", "SECTORS", "REJECT", "BLOCKMAP");
        List<byte[]> datas = Arrays.asList(new byte[0], thingsL, linedefs, sidedefs, vertexes, segsL, ssectorsL, nodesL, sectorsL, reject, blockmap());
        return Wad.pwad(names, datas);
    }

    void check() {
        List<String> missing = new ArrayList<>();
        for (Side s : sides) for (String t : new String[]{s.mid, s.upper, s.lower}) if (!t.equals("-") && !textures.contains(t) && !missing.contains(t)) missing.add(t);
        for (Sector s : sectors) for (String f : new String[]{s.floortex, s.ceiltex}) if (!flats.contains(f) && !missing.contains(f)) missing.add(f);
        if (!missing.isEmpty()) throw new IllegalStateException("unknown IWAD names: " + missing);
        int starts = 0;
        for (Thing t : things) if (t.type == 1) starts++;
        if (starts != 1) throw new IllegalStateException("a card needs exactly one player start");
        boolean exit = false;
        for (Line L : lines) if (L.special == SPECIAL_EXIT) exit = true;
        if (!exit) warnings.add("no exit switch: the level cannot be finished");
    }
}
