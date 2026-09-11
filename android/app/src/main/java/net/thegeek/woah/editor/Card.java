package net.thegeek.woah.editor;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/**
 * A level card - the thing the editor edits, saves, shares and compiles. Same JSON shape
 * as docs/editor/cards/*.json, so a card made here compiles with either compiler.
 */
public final class Card {

    public static final class Placed {
        public String t;
        public int x, y, z;
        public String dress = "tech";

        public Placed(String t, int x, int y) { this.t = t; this.x = x; this.y = y; }
    }

    public String name = "Untitled";
    public String author = "";
    public int grid = 64;
    public final List<Placed> tiles = new ArrayList<>();
    public final List<int[]> doors = new ArrayList<>();

    public static Card fromJson(String json) throws JSONException {
        JSONObject o = new JSONObject(json);
        Card c = new Card();
        c.name = o.optString("name", "Untitled");
        c.author = o.optString("author", "");
        c.grid = o.optInt("grid", 64);
        JSONArray ts = o.getJSONArray("tiles");
        for (int i = 0; i < ts.length(); i++) {
            JSONObject t = ts.getJSONObject(i);
            Placed p = new Placed(t.getString("t"), t.getInt("x"), t.getInt("y"));
            p.z = t.optInt("z", 0);
            p.dress = t.optString("dress", "tech");
            c.tiles.add(p);
        }
        JSONArray ds = o.optJSONArray("doors");
        if (ds != null) {
            for (int i = 0; i < ds.length(); i++) {
                c.doors.add(new int[]{ds.getJSONArray(i).getInt(0), ds.getJSONArray(i).getInt(1)});
            }
        }
        return c;
    }

    public String toJson() throws JSONException {
        JSONObject o = new JSONObject();
        o.put("woah", 1);
        o.put("name", name);
        o.put("author", author);
        o.put("based_on", JSONObject.NULL);
        o.put("grid", grid);
        JSONArray ts = new JSONArray();
        for (Placed p : tiles) {
            JSONObject t = new JSONObject();
            t.put("t", p.t);
            t.put("x", p.x);
            t.put("y", p.y);
            if (p.z != 0) t.put("z", p.z);
            t.put("dress", p.dress);
            ts.put(t);
        }
        o.put("tiles", ts);
        JSONArray ds = new JSONArray();
        for (int[] d : doors) ds.put(new JSONArray().put(d[0]).put(d[1]));
        o.put("doors", ds);
        o.put("pop", new JSONObject().put("preset", "normal"));
        return o.toString(1);
    }

    /** Footprint of a placed tile in cells: x0, y0, x1, y1. */
    public int[] footprint(Tiles tiles, Placed p) {
        Tiles.Tile t = tiles.tiles.get(p.t);
        return new int[]{p.x, p.y, p.x + t.w, p.y + t.h};
    }

    public boolean overlaps(Tiles tiles, Placed candidate, int ignoreIndex) {
        int[] a = footprint(tiles, candidate);
        for (int i = 0; i < this.tiles.size(); i++) {
            if (i == ignoreIndex) continue;
            int[] b = footprint(tiles, this.tiles.get(i));
            if (a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]) return true;
        }
        return false;
    }

    /** Index of the tile whose footprint holds cell (cx, cy), or -1. */
    public int tileAt(Tiles tiles, int cx, int cy) {
        for (int i = 0; i < this.tiles.size(); i++) {
            int[] f = footprint(tiles, this.tiles.get(i));
            if (cx >= f[0] && cx < f[2] && cy >= f[1] && cy < f[3]) return i;
        }
        return -1;
    }

    /** Absolute socket spans of placed tile i: edge, fixed, lo, hi (in cells). */
    List<int[]> socketSpans(Tiles tiles, int i) {
        Placed p = this.tiles.get(i);
        Tiles.Tile t = tiles.tiles.get(p.t);
        List<int[]> out = new ArrayList<>();
        for (Tiles.Socket k : t.sockets) {
            int edge = "NESW".indexOf(k.edge);
            if (edge == 0 || edge == 2) out.add(new int[]{edge, p.y + (edge == 0 ? t.h : 0), p.x + k.pos, p.x + k.pos + k.width});
            else out.add(new int[]{edge, p.x + (edge == 1 ? t.w : 0), p.y + k.pos, p.y + k.pos + k.width});
        }
        return out;
    }

    /** v1 rule: every pair of touching sockets with the same span is a door. */
    public void autoDoors(Tiles tiles) {
        doors.clear();
        int[] opp = {2, 3, 0, 1};
        for (int a = 0; a < this.tiles.size(); a++) {
            for (int b = a + 1; b < this.tiles.size(); b++) {
                boolean joined = false;
                for (int[] sa : socketSpans(tiles, a)) {
                    for (int[] sb : socketSpans(tiles, b)) {
                        if (sb[0] == opp[sa[0]] && sa[1] == sb[1] && sa[2] == sb[2] && sa[3] == sb[3]) joined = true;
                    }
                }
                if (joined) doors.add(new int[]{a, b});
            }
        }
    }

    public boolean isDoor(int a, int b) {
        for (int[] d : doors) if ((d[0] == a && d[1] == b) || (d[0] == b && d[1] == a)) return true;
        return false;
    }
}
