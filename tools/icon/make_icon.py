#!/usr/bin/env python3
"""Launcher icon from the title lettering, so the launcher matches the title screen:
an adaptive icon (API 26+: chrome Woah! foreground on a navy background) plus
legacy PNGs (navy rounded tile with a brand-blue ring). Off-device.
usage: make_icon.py <res dir> [preview.png] [--style=upright|italic]"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "title"))
from PIL import Image, ImageDraw
import make_woah_wad as T

NAVY = (44, 62, 80)      # #2c3e50
BLUE = (33, 150, 243)    # #2196F3
LEGACY = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
FOREGROUND = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}


def big_fit_font(text, box_w, box_h, style):
    """The title tool fits fonts up to 120 px; icons need far larger."""
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    for size in range(600, 8, -4):
        f = T.load_font(size, style)
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        if r - l <= box_w and b - t <= box_h:
            return f
    return T.load_font(8, style)


T.fit_font = big_fit_font


def wordmark(canvas, box_w, box_h, style):
    """Chrome Woah! rendered at 2x without antialiasing, then downsampled: the
    chrome stays crisp, the edges come out smooth."""
    big = canvas * 2
    layer = T.lettering(big, big, big / 2.0, big / 2.0, box_w * 2, box_h * 2, style, aura_px=max(2, big // 100))
    return Image.fromarray(layer, "RGBA").resize((canvas, canvas), Image.LANCZOS)


def foreground(size, style):
    safe = int(size * 0.66)   # the adaptive-icon safe zone is the inner 66 dp of 108
    return wordmark(size, safe, int(safe * 0.6), style)


def legacy(size, style):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * 0.2)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=NAVY + (255,))
    ring = max(1, size // 32)
    d.rounded_rectangle((ring // 2, ring // 2, size - 1 - ring // 2, size - 1 - ring // 2),
                        radius=r, outline=BLUE + (255,), width=ring)
    return Image.alpha_composite(img, wordmark(size, int(size * 0.84), int(size * 0.5), style))


def write_all(res, style):
    for dpi, px in LEGACY.items():
        legacy(px, style).save(os.path.join(res, "mipmap-" + dpi, "ic_launcher.png"))
    for dpi, px in FOREGROUND.items():
        foreground(px, style).save(os.path.join(res, "mipmap-" + dpi, "ic_launcher_foreground.png"))
    os.makedirs(os.path.join(res, "mipmap-anydpi-v26"), exist_ok=True)
    with open(os.path.join(res, "mipmap-anydpi-v26", "ic_launcher.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                '    <background android:drawable="@color/ic_launcher_background"/>\n'
                '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n'
                '</adaptive-icon>\n')
    with open(os.path.join(res, "values", "ic_launcher_background.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                '    <color name="ic_launcher_background">#2C3E50</color>\n</resources>\n')


def preview(res, out):
    """Adaptive icon under a circular launcher mask, the legacy tile, and the 48 px legacy tile."""
    fg = Image.open(os.path.join(res, "mipmap-xxxhdpi", "ic_launcher_foreground.png")).convert("RGBA")
    s = fg.width
    ad = Image.alpha_composite(Image.new("RGBA", (s, s), NAVY + (255,)), fg)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, s - 1, s - 1), fill=255)
    circ = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    circ.paste(ad, (0, 0), mask)
    leg = Image.open(os.path.join(res, "mipmap-xxxhdpi", "ic_launcher.png")).convert("RGBA").resize((s, s), Image.LANCZOS)
    small = Image.open(os.path.join(res, "mipmap-mdpi", "ic_launcher.png")).convert("RGBA")
    sheet = Image.new("RGBA", (2 * s + small.width + 64, s + 32), (24, 24, 28, 255))
    sheet.paste(circ, (16, 16), circ)
    sheet.paste(leg, (s + 32, 16), leg)
    sheet.paste(small, (2 * s + 48, 16), small)
    sheet.save(out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    style = "upright"
    for a in sys.argv[1:]:
        if a.startswith("--style="):
            style = a.split("=", 1)[1]
    res = args[0]
    write_all(res, style)
    if len(args) > 1:
        preview(res, args[1])
        print("preview", args[1])
    print("icons written to", res)
