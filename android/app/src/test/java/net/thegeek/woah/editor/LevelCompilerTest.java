package net.thegeek.woah.editor;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

/**
 * Golden test: the Java compiler must produce exactly the bytes tools/tiles/compile.py
 * produced for the same card (docs/editor/cards/first-light.wad). Byte equality is the
 * whole point - any divergence in placement, line order, BSP choice or packing shows here,
 * on the JVM, before a WAD ever reaches a phone.
 */
public class LevelCompilerTest {

    static File repoRoot() {
        File d = new File(System.getProperty("user.dir")).getAbsoluteFile();
        for (int i = 0; i < 6 && d != null; i++) {
            if (new File(d, "docs/editor/cards/first-light.json").exists()) return d;
            d = d.getParentFile();
        }
        throw new IllegalStateException("repo root not found from " + System.getProperty("user.dir"));
    }

    static String text(File root, String rel) throws Exception {
        return new String(Files.readAllBytes(new File(root, rel).toPath()), StandardCharsets.UTF_8);
    }

    static void assertGolden(String card) throws Exception {
        File root = repoRoot();
        Wad iwad = new Wad(Files.readAllBytes(new File(root, "android/app/src/main/assets/freedoom2.wad").toPath()));
        Tiles tiles = new Tiles(text(root, "android/app/src/main/assets/tiles.json"));
        LevelCompiler c = new LevelCompiler(tiles, iwad.textureNames(), iwad.flatNames());
        byte[] out = c.compile(text(root, "docs/editor/cards/" + card + ".json"));
        byte[] golden = Files.readAllBytes(new File(root, "docs/editor/cards/" + card + ".wad").toPath());
        assertTrue("compiler warnings: " + c.warnings, c.warnings.isEmpty());
        assertArrayEquals("Java and Python compilers disagree on " + card, golden, out);
    }

    @Test
    public void firstLightMatchesTheReferenceCompiler() throws Exception {
        assertGolden("first-light");
    }

    @Test
    public void hardPresetAndSlotOverridesMatchTheReferenceCompiler() throws Exception {
        assertGolden("first-light-hard");
    }
}
