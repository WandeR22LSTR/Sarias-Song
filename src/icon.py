"""The Saria's Song icon: a Kokiri-green eighth note, drawn with Pillow.

No external asset is needed. Run this file to (re)generate the `.ico` that the
PyInstaller build embeds:

    python src/icon.py            # writes assets/saria-song.ico and .png
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

KOKIRI_GREEN = (88, 204, 102, 255)
OUTLINE_GREEN = (18, 74, 34, 255)  # keeps the note readable on a light taskbar

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
_SUPERSAMPLE = 8


def _ellipse_points(cx: float, cy: float, rx: float, ry: float, angle_deg: float, n: int = 72) -> list[tuple[float, float]]:
    """Points of an ellipse rotated by `angle_deg` (counter-clockwise on screen)."""
    a = math.radians(-angle_deg)
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    return pts


def _bezier(p0, p1, p2, p3, n: int = 24) -> list[tuple[float, float]]:
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append(
            (
                u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
            )
        )
    return pts


def _note_shapes() -> list[list[tuple[float, float]]]:
    """Eighth-note geometry in unit coordinates (0..1), drawn bottom to top."""
    head = _ellipse_points(0.37, 0.77, 0.185, 0.135, 24)
    stem_x, stem_w, stem_top, stem_bottom = 0.525, 0.075, 0.13, 0.76
    stem = [
        (stem_x - stem_w / 2, stem_top),
        (stem_x + stem_w / 2, stem_top),
        (stem_x + stem_w / 2, stem_bottom),
        (stem_x - stem_w / 2, stem_bottom),
    ]
    # Flag: a swoosh leaving the top of the stem, curling right then down to a
    # single tip. Both curves share the tip so the outline has no sliver there,
    # and the flag starts inside the stem so the two shapes merge cleanly.
    tip = (0.80, 0.60)
    outer = _bezier((stem_x, stem_top), (0.68, 0.20), (0.90, 0.34), tip)
    inner = _bezier(tip, (0.80, 0.42), (0.70, 0.36), (stem_x, 0.33))
    flag = outer + inner
    return [stem, flag, head]


def make_icon_image(size: int = 256) -> Image.Image:
    """Return the icon as an RGBA image of `size` x `size` pixels."""
    big = size * _SUPERSAMPLE
    outline_w = max(1.0, 0.035 * big)

    def scaled(poly):
        return [(x * big, y * big) for x, y in poly]

    # Outline pass: the same shapes, grown, in dark green; then the fill on top.
    mask_outline = Image.new("L", (big, big), 0)
    mask_fill = Image.new("L", (big, big), 0)
    d_out, d_fill = ImageDraw.Draw(mask_outline), ImageDraw.Draw(mask_fill)
    for poly in _note_shapes():
        pts = scaled(poly)
        d_fill.polygon(pts, fill=255)
        d_out.polygon(pts, fill=255)
        d_out.line(pts + [pts[0]], fill=255, width=round(outline_w * 2), joint="curve")

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (big, big), OUTLINE_GREEN), mask=mask_outline)
    img.paste(Image.new("RGBA", (big, big), KOKIRI_GREEN), mask=mask_fill)
    return img.resize((size, size), Image.LANCZOS)


def write_ico(path: Path) -> Path:
    """Write a multi-size .ico (Windows picks the right size per context)."""
    make_icon_image(256).save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    return path


if __name__ == "__main__":
    assets = Path(__file__).resolve().parent.parent / "assets"
    assets.mkdir(exist_ok=True)
    print("wrote", write_ico(assets / "saria-song.ico"))
    make_icon_image(256).save(assets / "saria-song.png")
    print("wrote", assets / "saria-song.png")
