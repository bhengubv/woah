package net.thegeek.woah.editor;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/** The tile catalogue, loaded from assets/tiles.json (exported by tools/tiles/tiles.py). */
public final class Tiles {

    public static final class Sector {
        public final List<int[]> rects = new ArrayList<>();
        public int floor, ceil;
        public String kind;
    }

    public static final class Socket {
        public String edge;
        public int pos, width;
    }

    public static final class Slot {
        public double x, y;
        public String role;
    }

    public static final class Tile {
        public String id, exitEdge;
        public int w, h;
        public final List<Sector> sectors = new ArrayList<>();
        public final List<Socket> sockets = new ArrayList<>();
        public final List<Slot> slots = new ArrayList<>();
    }

    public final int cell;
    public final Map<String, Tile> tiles = new HashMap<>();
    public final Map<String, Integer> roles = new HashMap<>();

    public Tiles(String json) throws JSONException {   // checked on Android's org.json
        JSONObject root = new JSONObject(json);
        cell = root.getInt("cell");
        JSONObject ts = root.getJSONObject("tiles");
        for (Iterator<String> it = ts.keys(); it.hasNext(); ) {
            String id = it.next();
            JSONObject t = ts.getJSONObject(id);
            Tile tile = new Tile();
            tile.id = t.getString("id");
            tile.w = t.getInt("w");
            tile.h = t.getInt("h");
            tile.exitEdge = t.isNull("exit_edge") ? null : t.getString("exit_edge");
            JSONArray secs = t.getJSONArray("sectors");
            for (int i = 0; i < secs.length(); i++) {
                JSONObject s = secs.getJSONObject(i);
                Sector sec = new Sector();
                sec.floor = s.getInt("floor");
                sec.ceil = s.getInt("ceil");
                sec.kind = s.getString("kind");
                JSONArray rs = s.getJSONArray("rects");
                for (int j = 0; j < rs.length(); j++) {
                    JSONArray r = rs.getJSONArray(j);
                    sec.rects.add(new int[]{r.getInt(0), r.getInt(1), r.getInt(2), r.getInt(3)});
                }
                tile.sectors.add(sec);
            }
            JSONArray ks = t.getJSONArray("sockets");
            for (int i = 0; i < ks.length(); i++) {
                JSONObject k = ks.getJSONObject(i);
                Socket so = new Socket();
                so.edge = k.getString("edge");
                so.pos = k.getInt("pos");
                so.width = k.getInt("width");
                tile.sockets.add(so);
            }
            JSONArray ls = t.getJSONArray("slots");
            for (int i = 0; i < ls.length(); i++) {
                JSONObject l = ls.getJSONObject(i);
                Slot sl = new Slot();
                sl.x = l.getDouble("x");
                sl.y = l.getDouble("y");
                sl.role = l.getString("role");
                tile.slots.add(sl);
            }
            tiles.put(id, tile);
        }
        JSONObject rs = root.getJSONObject("roles");
        for (Iterator<String> it = rs.keys(); it.hasNext(); ) {
            String k = it.next();
            roles.put(k, rs.getInt(k));
        }
    }
}
