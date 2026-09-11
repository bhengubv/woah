package net.thegeek.woah.editor;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Minimal WAD reading (directory, lumps, the IWAD's texture and flat names) and PWAD writing. */
public final class Wad {

    public static final class Lump {
        public final String name;
        public final int pos, size;
        Lump(String name, int pos, int size) { this.name = name; this.pos = pos; this.size = size; }
    }

    public final byte[] data;
    public final List<Lump> lumps = new ArrayList<>();

    public Wad(byte[] data) {
        this.data = data;
        ByteBuffer b = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN);
        int n = b.getInt(4), dir = b.getInt(8);
        for (int i = 0; i < n; i++) {
            int o = dir + 16 * i;
            lumps.add(new Lump(name8(data, o + 8), b.getInt(o), b.getInt(o + 4)));
        }
    }

    public byte[] lump(String name) {
        for (Lump l : lumps) {
            if (l.name.equals(name)) {
                byte[] out = new byte[l.size];
                System.arraycopy(data, l.pos, out, 0, l.size);
                return out;
            }
        }
        return null;
    }

    /** Names in TEXTURE1/TEXTURE2. */
    public Set<String> textureNames() {
        Set<String> out = new HashSet<>();
        for (String tl : new String[]{"TEXTURE1", "TEXTURE2"}) {
            byte[] t = lump(tl);
            if (t == null) continue;
            ByteBuffer b = ByteBuffer.wrap(t).order(ByteOrder.LITTLE_ENDIAN);
            int n = b.getInt(0);
            for (int i = 0; i < n; i++) out.add(name8(t, b.getInt(4 + 4 * i)));
        }
        return out;
    }

    /** 4096-byte lumps between F_START and F_END. */
    public Set<String> flatNames() {
        Set<String> out = new HashSet<>();
        boolean inside = false;
        for (Lump l : lumps) {
            if (l.name.equals("F_START") || l.name.equals("FF_START")) inside = true;
            else if (l.name.equals("F_END") || l.name.equals("FF_END")) inside = false;
            else if (inside && l.size == 4096) out.add(l.name);
        }
        return out;
    }

    public static byte[] pwad(List<String> names, List<byte[]> lumps) {
        int total = 12;
        for (byte[] d : lumps) total += d.length;
        ByteBuffer b = ByteBuffer.allocate(total + 16 * lumps.size()).order(ByteOrder.LITTLE_ENDIAN);
        b.put("PWAD".getBytes(StandardCharsets.US_ASCII)).putInt(lumps.size()).putInt(total);
        int[] pos = new int[lumps.size()];
        int p = 12;
        for (int i = 0; i < lumps.size(); i++) { pos[i] = p; b.put(lumps.get(i)); p += lumps.get(i).length; }
        for (int i = 0; i < lumps.size(); i++) { b.putInt(pos[i]).putInt(lumps.get(i).length); putName8(b, names.get(i)); }
        return b.array();
    }

    static String name8(byte[] d, int off) {
        int n = 0;
        while (n < 8 && d[off + n] != 0) n++;
        return new String(d, off, n, StandardCharsets.ISO_8859_1);
    }

    static void putName8(ByteBuffer b, String s) {
        byte[] raw = s.getBytes(StandardCharsets.US_ASCII);
        for (int i = 0; i < 8; i++) b.put(i < raw.length ? raw[i] : 0);
    }
}
