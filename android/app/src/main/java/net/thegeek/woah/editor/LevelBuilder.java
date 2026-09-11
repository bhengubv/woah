package net.thegeek.woah.editor;

import android.content.Context;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * Compiles a level card on the phone into a PWAD the game can load with -file.
 * The IWAD's texture and flat names come from the freedoom2.wad the activity
 * extracted; the tile catalogue from assets/tiles.json; the output is
 * files/level.wad (rewritten every time).
 */
public final class LevelBuilder {

    public static File build(Context ctx, String cardJson) throws Exception {
        File files = ctx.getFilesDir();
        Wad iwad = new Wad(readAll(new FileInputStream(new File(files, "freedoom2.wad"))));
        Tiles tiles = new Tiles(new String(readAll(ctx.getAssets().open("tiles.json")), StandardCharsets.UTF_8));
        LevelCompiler c = new LevelCompiler(tiles, iwad.textureNames(), iwad.flatNames());
        byte[] wad = c.compile(cardJson);
        File out = new File(files, "level.wad");
        try (FileOutputStream fos = new FileOutputStream(out)) {
            fos.write(wad);
        }
        return out;
    }

    public static String readText(File f) throws IOException {
        return new String(readAll(new FileInputStream(f)), StandardCharsets.UTF_8);
    }

    static byte[] readAll(InputStream in) throws IOException {
        try (InputStream s = in) {
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[65536];
            int n;
            while ((n = s.read(buf)) > 0) bos.write(buf, 0, n);
            return bos.toByteArray();
        }
    }
}
