package net.thegeek.woah.editor;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.MotionEvent;
import android.view.View;

import java.util.List;

/**
 * The top-down grid. One cell = one grid unit of the card (64 map units). Drag pans;
 * a tap places the brush tile (min corner at the tapped cell) or selects the tile there.
 * Doors are drawn where sockets are joined; every touch stays coarse on purpose.
 */
public final class LevelCanvasView extends View {

    public interface Listener {
        void onChanged();
        void onMessage(String text);
    }

    private Card card;
    private Tiles tiles;
    private Listener listener;
    private float cellPx = 28f, originX = 200f, originY = 600f;
    private int selected = -1;
    private String brush;
    private float downX, downY, lastX, lastY;
    private boolean panned;

    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint stroke = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);

    public LevelCanvasView(Context ctx) {
        super(ctx);
        stroke.setStyle(Paint.Style.STROKE);
        text.setColor(Color.WHITE);
        text.setTextSize(22f);
    }

    public void setModel(Card card, Tiles tiles, Listener l) {
        this.card = card; this.tiles = tiles; this.listener = l; selected = -1; brush = null;
        fit();
    }

    public void setCard(Card card) { this.card = card; selected = -1; fit(); }
    public void setBrush(String id) { brush = id; selected = -1; invalidate(); }
    public String brush() { return brush; }
    public int selected() { return selected; }
    public Card.Placed selectedTile() { return selected >= 0 && selected < card.tiles.size() ? card.tiles.get(selected) : null; }

    public void deleteSelected() {
        if (selectedTile() == null) return;
        card.tiles.remove(selected);
        selected = -1;
        changed();
    }

    public void cycleDress() {
        Card.Placed p = selectedTile();
        if (p == null) return;
        p.dress = p.dress.equals("tech") ? "base" : p.dress.equals("base") ? "hell" : "tech";
        changed();
    }

    public void raiseSelected(int dz) {
        Card.Placed p = selectedTile();
        if (p == null) return;
        p.z += dz;
        changed();
    }

    /** Centre the card on screen. */
    public void fit() {
        if (card == null || card.tiles.isEmpty() || getWidth() == 0) { originX = 200f; originY = getHeight() > 0 ? getHeight() - 200f : 600f; invalidate(); return; }
        int x0 = Integer.MAX_VALUE, y0 = Integer.MAX_VALUE, x1 = Integer.MIN_VALUE, y1 = Integer.MIN_VALUE;
        for (Card.Placed p : card.tiles) {
            int[] f = card.footprint(tiles, p);
            x0 = Math.min(x0, f[0]); y0 = Math.min(y0, f[1]); x1 = Math.max(x1, f[2]); y1 = Math.max(y1, f[3]);
        }
        cellPx = Math.max(10f, Math.min(40f, Math.min((getWidth() - 80f) / (x1 - x0), (getHeight() - 80f) / (y1 - y0))));
        originX = (getWidth() - (x1 - x0) * cellPx) / 2f - x0 * cellPx;
        originY = (getHeight() + (y1 - y0) * cellPx) / 2f + y0 * cellPx;
        invalidate();
    }

    @Override
    protected void onSizeChanged(int w, int h, int ow, int oh) { fit(); }

    private void changed() {
        card.autoDoors(tiles);
        invalidate();
        if (listener != null) listener.onChanged();
    }

    // world cell -> screen
    private float sx(float cx) { return originX + cx * cellPx; }
    private float sy(float cy) { return originY - cy * cellPx; }

    static int dressColor(String dress) {
        switch (dress) {
            case "base": return Color.rgb(96, 72, 48);
            case "hell": return Color.rgb(112, 32, 32);
            default: return Color.rgb(44, 62, 80);
        }
    }

    @Override
    protected void onDraw(Canvas c) {
        c.drawColor(Color.rgb(18, 18, 22));
        if (card == null) return;
        // grid
        stroke.setColor(Color.rgb(34, 34, 44)); stroke.setStrokeWidth(1f);
        int cx0 = (int) Math.floor(-originX / cellPx) - 1, cx1 = (int) Math.ceil((getWidth() - originX) / cellPx) + 1;
        int cy0 = (int) Math.floor((originY - getHeight()) / cellPx) - 1, cy1 = (int) Math.ceil(originY / cellPx) + 1;
        for (int cx = cx0; cx <= cx1; cx++) c.drawLine(sx(cx), 0, sx(cx), getHeight(), stroke);
        for (int cy = cy0; cy <= cy1; cy++) c.drawLine(0, sy(cy), getWidth(), sy(cy), stroke);
        // tiles
        for (int i = 0; i < card.tiles.size(); i++) {
            Card.Placed p = card.tiles.get(i);
            Tiles.Tile t = tiles.tiles.get(p.t);
            fill.setStyle(Paint.Style.FILL); fill.setColor(dressColor(p.dress));
            for (Tiles.Sector sec : t.sectors) {
                for (int[] r : sec.rects) {
                    c.drawRect(sx(p.x + r[0]), sy(p.y + r[3]), sx(p.x + r[2]), sy(p.y + r[1]), fill);
                }
            }
            for (Tiles.Sector sec : t.sectors) {
                stroke.setColor(Color.rgb(200, 200, 210)); stroke.setStrokeWidth(2f);
                for (int[] r : sec.rects) c.drawRect(sx(p.x + r[0]), sy(p.y + r[3]), sx(p.x + r[2]), sy(p.y + r[1]), stroke);
            }
            // sockets: green when joined, grey otherwise
            List<int[]> spans = card.socketSpans(tiles, i);
            for (int k = 0; k < spans.size(); k++) {
                int[] s = spans.get(k);
                boolean joined = false;
                for (int j = 0; j < card.tiles.size(); j++) if (j != i && card.isDoor(i, j) && touches(spans.get(k), card.socketSpans(tiles, j))) joined = true;
                fill.setColor(joined ? Color.rgb(60, 220, 90) : Color.rgb(120, 120, 130));
                float th = Math.max(3f, cellPx * 0.18f);
                if (s[0] == 0 || s[0] == 2) c.drawRect(sx(s[2]) + 2, sy(s[1]) - th / 2, sx(s[3]) - 2, sy(s[1]) + th / 2, fill);
                else c.drawRect(sx(s[1]) - th / 2, sy(s[3]) + 2, sx(s[1]) + th / 2, sy(s[2]) - 2, fill);
            }
            // slots
            for (Tiles.Slot sl : t.slots) {
                fill.setColor(sl.role.equals("player") ? Color.rgb(33, 150, 243) : sl.role.startsWith("monster") ? Color.rgb(230, 60, 60) : Color.rgb(240, 210, 60));
                c.drawCircle(sx(p.x + (float) sl.x), sy(p.y + (float) sl.y), Math.max(3f, cellPx * 0.16f), fill);
            }
            if (t.exitEdge != null) c.drawText("EXIT", sx(p.x) + 6, sy(p.y + t.h) + 24, text);
            if (p.z != 0) c.drawText("z" + p.z, sx(p.x) + 6, sy(p.y) - 6, text);
            if (i == selected) {
                stroke.setColor(Color.rgb(33, 150, 243)); stroke.setStrokeWidth(5f);
                c.drawRect(sx(p.x), sy(p.y + t.h), sx(p.x + t.w), sy(p.y), stroke);
            }
        }
        text.setColor(Color.rgb(180, 180, 190));
        c.drawText(brush != null ? "tap a cell to place: " + brush : selected >= 0 ? card.tiles.get(selected).t + " selected" : card.name, 12, 30, text);
        text.setColor(Color.WHITE);
    }

    private static boolean touches(int[] a, List<int[]> others) {
        int[] opp = {2, 3, 0, 1};
        for (int[] b : others) if (b[0] == opp[a[0]] && a[1] == b[1] && a[2] == b[2] && a[3] == b[3]) return true;
        return false;
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                downX = lastX = e.getX(); downY = lastY = e.getY(); panned = false;
                return true;
            case MotionEvent.ACTION_MOVE:
                if (Math.abs(e.getX() - downX) > 14 || Math.abs(e.getY() - downY) > 14) panned = true;
                if (panned) { originX += e.getX() - lastX; originY += e.getY() - lastY; invalidate(); }
                lastX = e.getX(); lastY = e.getY();
                return true;
            case MotionEvent.ACTION_UP:
                if (!panned) tap(e.getX(), e.getY());
                return true;
        }
        return super.onTouchEvent(e);
    }

    private void tap(float x, float y) {
        int cx = (int) Math.floor((x - originX) / cellPx), cy = (int) Math.floor((originY - y) / cellPx);
        if (brush != null) {
            Card.Placed p = new Card.Placed(brush, cx, cy);
            if (card.overlaps(tiles, p, -1)) { if (listener != null) listener.onMessage("That overlaps a tile"); return; }
            card.tiles.add(p);
            selected = card.tiles.size() - 1;
            brush = null;
            changed();
        } else {
            selected = card.tileAt(tiles, cx, cy);
            invalidate();
            if (listener != null) listener.onChanged();
        }
    }
}
