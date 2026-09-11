package net.thegeek.woah.editor;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * The level editor: tiles on a grid, joined where their sockets touch. Opens on a
 * card (the last one saved, else the starter) - never on a blank canvas. Play compiles
 * the card on the phone and launches the game with it; the game process is asked to
 * quit first because DOOM only reads its arguments at startup.
 */
public final class EditorActivity extends Activity implements LevelCanvasView.Listener {

    private static final int BRAND = Color.rgb(33, 150, 243), NAVY = Color.rgb(44, 62, 80);
    private Tiles tiles;
    private Card card;
    private LevelCanvasView canvas;
    private Button dressBtn, deleteBtn, raiseBtn, lowerBtn;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        try {
            tiles = new Tiles(new String(LevelBuilder.readAll(getAssets().open("tiles.json")), StandardCharsets.UTF_8));
            card = loadCurrentOrStarter();
        } catch (Exception e) {
            Toast.makeText(this, "Editor could not start: " + e.getMessage(), Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(18, 18, 22));

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setPadding(8, 8, 8, 8);
        Button play = button("Play", BRAND, v -> play());
        bar.addView(play);
        bar.addView(button("Save", NAVY, v -> save()));
        bar.addView(button("Load", NAVY, v -> load()));
        dressBtn = button("Dress", NAVY, v -> canvas.cycleDress());
        raiseBtn = button("Raise", NAVY, v -> canvas.raiseSelected(16));
        lowerBtn = button("Lower", NAVY, v -> canvas.raiseSelected(-16));
        deleteBtn = button("Delete", Color.rgb(120, 32, 32), v -> canvas.deleteSelected());
        bar.addView(dressBtn); bar.addView(raiseBtn); bar.addView(lowerBtn); bar.addView(deleteBtn);
        bar.addView(button("Fit", NAVY, v -> canvas.fit()));
        HorizontalScrollView barScroll = new HorizontalScrollView(this);
        barScroll.addView(bar);
        root.addView(barScroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        canvas = new LevelCanvasView(this);
        root.addView(canvas, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        LinearLayout palette = new LinearLayout(this);
        palette.setOrientation(LinearLayout.HORIZONTAL);
        palette.setPadding(8, 8, 8, 8);
        List<String> ids = new ArrayList<>(tiles.tiles.keySet());
        java.util.Collections.sort(ids);
        for (String id : ids) palette.addView(button(id, Color.rgb(50, 50, 62), v -> canvas.setBrush(id)));
        HorizontalScrollView palScroll = new HorizontalScrollView(this);
        palScroll.addView(palette);
        root.addView(palScroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        setContentView(root);
        canvas.setModel(card, tiles, this);
        onChanged();
    }

    private Button button(String label, int color, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setBackgroundColor(color);
        b.setOnClickListener(l);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(6, 0, 6, 0);
        lp.gravity = Gravity.CENTER_VERTICAL;
        b.setLayoutParams(lp);
        return b;
    }

    @Override
    public void onChanged() {
        boolean sel = canvas.selectedTile() != null;
        dressBtn.setEnabled(sel); deleteBtn.setEnabled(sel); raiseBtn.setEnabled(sel); lowerBtn.setEnabled(sel);
    }

    @Override
    public void onMessage(String text) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show();
    }

    // ---- cards on disk
    private File cardsDir() {
        File d = new File(getFilesDir(), "cards");
        d.mkdirs();
        return d;
    }

    private Card loadCurrentOrStarter() throws Exception {
        File cur = new File(cardsDir(), "current.json");
        if (cur.exists()) return Card.fromJson(LevelBuilder.readText(cur));
        return Card.fromJson(new String(LevelBuilder.readAll(getAssets().open("cards/first-light.json")), StandardCharsets.UTF_8));
    }

    private void writeCard(File f) throws Exception {
        card.autoDoors(tiles);
        try (FileOutputStream fos = new FileOutputStream(f)) {
            fos.write(card.toJson().getBytes(StandardCharsets.UTF_8));
        }
    }

    private void save() {
        try {
            String safe = card.name.replaceAll("[^A-Za-z0-9 _-]", "").trim();
            if (safe.isEmpty()) safe = "untitled";
            writeCard(new File(cardsDir(), safe + ".json"));
            writeCard(new File(cardsDir(), "current.json"));
            onMessage("Saved " + safe);
        } catch (Exception e) {
            onMessage("Save failed: " + e.getMessage());
        }
    }

    private void load() {
        final List<String> names = new ArrayList<>();
        final List<File> files = new ArrayList<>();
        names.add("Starter: First light"); files.add(null);
        File[] saved = cardsDir().listFiles();
        if (saved != null) for (File f : saved) if (f.getName().endsWith(".json") && !f.getName().equals("current.json")) { names.add(f.getName().replace(".json", "")); files.add(f); }
        new AlertDialog.Builder(this).setTitle("Open a card").setItems(names.toArray(new String[0]), (dlg, which) -> {
            try {
                File f = files.get(which);
                card = f == null
                        ? Card.fromJson(new String(LevelBuilder.readAll(getAssets().open("cards/first-light.json")), StandardCharsets.UTF_8))
                        : Card.fromJson(LevelBuilder.readText(f));
                canvas.setCard(card);
                onChanged();
            } catch (Exception e) {
                onMessage("Load failed: " + e.getMessage());
            }
        }).show();
    }

    // ---- play
    private void play() {
        final File wad;
        try {
            writeCard(new File(cardsDir(), "current.json"));
            wad = LevelBuilder.build(this, card.toJson());
        } catch (Exception e) {
            onMessage(e.getMessage() != null ? e.getMessage() : e.toString());   // the designer is the validator
            return;
        }
        if (gameRunning()) {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("circledoom://quit")));
            waitThenLaunch(wad, 0);
        } else {
            launch(wad);
        }
    }

    private boolean gameRunning() {
        ActivityManager am = (ActivityManager) getSystemService(ACTIVITY_SERVICE);
        if (am == null || am.getRunningAppProcesses() == null) return false;
        for (ActivityManager.RunningAppProcessInfo p : am.getRunningAppProcesses()) if (p.processName.equals(getPackageName())) return true;
        return false;
    }

    private void waitThenLaunch(final File wad, final int tries) {
        new Handler().postDelayed(() -> {
            if (!gameRunning() || tries >= 12) launch(wad);
            else waitThenLaunch(wad, tries + 1);
        }, 250);
    }

    private void launch(File wad) {
        Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse("circledoom://play?map=" + Uri.encode(wad.getAbsolutePath())));
        i.setPackage(getPackageName());
        startActivity(i);
    }
}
