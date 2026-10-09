"""Rendering for the clock saver: pure maths first, pygame drawing below.

Look: a deep green-black vignette, a large soft clock, and a few dozen slow
"fireflies" (additive glows) drifting like the lights in Kokiri Forest. Nothing
moves fast; the aim is something comfortable to leave up on a streamed display.

Performance: the background is baked once into one surface. Every frame only the
areas that changed are restored from it and redrawn, and only those rectangles
are pushed to the screen. That keeps CPU low over an 8-hour run, even when the
window spans several large monitors.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, NamedTuple, Sequence

from config import ClockConfig, Colors, Config

# ---------------------------------------------------------------------------
# Pure helpers (no pygame): these are what the unit tests exercise.
# ---------------------------------------------------------------------------

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip


def format_clock(now: datetime, clock: ClockConfig) -> tuple[str, str]:
    """Return (time_text, date_text). Locale-independent on purpose, so the
    saver looks the same on every machine. date_text is "" when disabled."""
    if clock.format_24h:
        time_text = f"{now.hour:02d}:{now.minute:02d}"
        suffix = ""
    else:
        hour12 = now.hour % 12 or 12
        time_text = f"{hour12}:{now.minute:02d}"
        suffix = " AM" if now.hour < 12 else " PM"
    if clock.show_seconds:
        time_text += f":{now.second:02d}"
    time_text += suffix
    date_text = f"{_WEEKDAYS[now.weekday()]}, {now.day} {_MONTHS[now.month - 1]}" if clock.show_date else ""
    return time_text, date_text


class Cell(NamedTuple):
    """One slot of the clock's fixed grid."""

    text: str
    x: int  # left edge of the slot, in pixels from the left of the clock
    width: int
    centered: bool  # glyphs sit centred in their slot; the AM/PM suffix is left-aligned


def split_suffix(time_text: str) -> tuple[str, str]:
    for suffix in (" AM", " PM"):
        if time_text.endswith(suffix):
            return time_text[: -len(suffix)], suffix
    return time_text, ""


def clock_cells(time_text: str, advance: Callable[[str], int]) -> tuple[list[Cell], int]:
    """Lay the clock out on a fixed grid, so it has the same width and every
    character the same position whatever the time is.

    Centring the rendered string instead makes the clock breathe: digits have
    different widths and kerning changes between pairs ("11", "47"), so the string
    is wider or narrower from one tick to the next and every glyph slides to
    re-centre it. Here each digit gets a slot as wide as the widest digit
    (`advance` is the pixel width of a string in the clock's font). A 12-hour
    time with a one-digit hour keeps an empty tens slot, and the AM/PM suffix
    reserves room for the wider of "AM" and "PM".
    """
    body, suffix = split_suffix(time_text)
    digit_width = max(advance(d) for d in "0123456789")
    cells: list[Cell] = []
    x = 0
    if len(body.split(":")[0]) == 1:
        cells.append(Cell(" ", 0, digit_width, True))
        x = digit_width
    for char in body:
        width = digit_width if char.isdigit() else advance(char)
        cells.append(Cell(char, x, width, True))
        x += width
    if suffix:
        width = max(advance(" AM"), advance(" PM"))
        cells.append(Cell(suffix, x, width, False))
        x += width
    return cells, x


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Layout:
    """Where the window goes and where each monitor sits inside it."""

    window: Rect  # in virtual-desktop pixels (may have negative x/y)
    monitors: tuple[Rect, ...]  # relative to the window's top-left corner


def plan_layout(monitors: Sequence[tuple[int, int, int, int, bool]], which: str) -> Layout:
    """Work out one borderless window that covers the wanted monitors.

    `monitors` is (x, y, width, height, is_primary) per display in virtual
    desktop pixels. "primary" covers just the primary one (or the first if none
    is flagged); "all" covers the bounding box of every monitor, so a monitor at
    negative coordinates works too.
    """
    if not monitors:
        raise ValueError("no monitors to cover")
    if which == "primary":
        chosen = [next((m for m in monitors if m[4]), monitors[0])]
    else:
        chosen = list(monitors)
    left = min(m[0] for m in chosen)
    top = min(m[1] for m in chosen)
    right = max(m[0] + m[2] for m in chosen)
    bottom = max(m[1] + m[3] for m in chosen)
    rel = tuple(Rect(m[0] - left, m[1] - top, m[2], m[3]) for m in chosen)
    return Layout(Rect(left, top, right - left, bottom - top), rel)


@dataclass(frozen=True)
class FireflySpec:
    # Everything is in unit coordinates (0..1 of the monitor) or radians/second.
    base_x: float
    base_y: float
    amp_x: float
    amp_y: float
    freq_x: float
    freq_y: float
    phase_x: float
    phase_y: float
    size_class: int  # 0 small, 1 medium, 2 large
    pulse_freq: float
    pulse_phase: float


MARGIN = 0.07  # fireflies stay this far inside the monitor edges


def make_fireflies(seed: int, count: int) -> list[FireflySpec]:
    rng = random.Random(seed)
    specs = []
    for _ in range(count):
        amp_x = rng.uniform(0.03, 0.10)
        amp_y = rng.uniform(0.03, 0.09)
        specs.append(
            FireflySpec(
                base_x=rng.uniform(MARGIN + amp_x, 1 - MARGIN - amp_x),
                base_y=rng.uniform(MARGIN + amp_y, 1 - MARGIN - amp_y),
                amp_x=amp_x,
                amp_y=amp_y,
                freq_x=rng.uniform(0.02, 0.07),  # periods of roughly 1.5 to 5 minutes
                freq_y=rng.uniform(0.02, 0.07),
                phase_x=rng.uniform(0, math.tau),
                phase_y=rng.uniform(0, math.tau),
                size_class=rng.choices((0, 1, 2), weights=(5, 3, 1))[0],
                pulse_freq=rng.uniform(0.15, 0.5),  # "breathing" every 12 to 40 seconds
                pulse_phase=rng.uniform(0, math.tau),
            )
        )
    return specs


def firefly_state(spec: FireflySpec, t: float) -> tuple[float, float, float]:
    """Position (unit coordinates) and brightness (0..1) of one firefly at time t seconds."""
    # A small quicker wobble on top of the slow drift keeps it feeling alive.
    x = spec.base_x + spec.amp_x * math.sin(spec.freq_x * t + spec.phase_x) + 0.003 * math.sin(0.9 * t + spec.phase_y)
    y = spec.base_y + spec.amp_y * math.sin(spec.freq_y * t + spec.phase_y) + 0.003 * math.sin(0.7 * t + spec.phase_x)
    pulse = 0.5 + 0.5 * math.sin(spec.pulse_freq * t + spec.pulse_phase)
    return x, y, 0.2 + 0.8 * pulse


def clock_drift(t: float, width: int, height: int) -> tuple[int, int]:
    """Tiny, very slow wander of the clock so no pixel stays lit for hours (burn-in)."""
    reach = 0.012 * min(width, height)
    return round(reach * math.sin(t / 61.0)), round(reach * math.cos(t / 83.0))


def count_fireflies(width: int, height: int) -> int:
    return max(14, min(40, round(width * height / 90_000)))


def vignette_amount(nx: float, ny: float) -> float:
    """0 in the (slightly high) centre, rising smoothly to 1 at the corners.
    nx, ny are -1..1 across the monitor."""
    d = math.hypot(nx, ny + 0.12) / 1.3
    u = min(max((d - 0.15) / 0.85, 0.0), 1.0)
    return u * u * (3 - 2 * u)  # smoothstep


# ---------------------------------------------------------------------------
# pygame drawing
# ---------------------------------------------------------------------------

BRIGHTNESS_LEVELS = 10
GLOW_PEAK = 0.55  # brightest a firefly gets, as a fraction of the accent colour
# The clock's halo is a soft bloom: two Gaussian blurs of the text, each given as
# (sigma as a fraction of the font height, weight). The tight one makes a close
# glow, the wide one a faint wash around it.
HALO_LAYERS = ((0.03, 0.6), (0.10, 0.4))
HALO_STRENGTH = 0.5  # bloom brightness relative to the accent colour
HALO_SHRINK = 4  # blurs run at 1/4 size: smooth fields do not need full resolution
FPS = 30


def load_font(names: str, size: int, log=None):
    """First installed font from a comma-separated list, else pygame's built-in one."""
    import pygame

    for name in (n.strip() for n in names.split(",")):
        if not name:
            continue
        path = pygame.font.match_font(name)
        if path:
            if log:
                log.info("font: %s -> %s", name, path)
            return pygame.font.Font(path, size)
    if log:
        log.warning("font: none of %r found, using pygame's default", names)
    return pygame.font.Font(None, size)


def make_glow_sprites(radius: int, color: tuple[int, int, int], rng: random.Random | None = None):
    """Brightness ladder of one soft round glow, for additive blending.

    The falloff, (1 - distance/radius) ** 2.2, is computed per pixel in floating
    point and dithered before rounding (see make_background). Drawing it as 1 px
    rings in 8 bits, as an earlier version did, left faint concentric contours
    and radial spokes that a contrasty panel shows. Outside the circle the value
    is exactly 0, so the square sprite never shows an edge when added.
    """
    import pygame
    from PIL import Image, ImageMath

    rng = rng or random.Random(radius)
    size = radius * 2
    middle = radius - 0.5  # centre of the sprite, in pixel-centre coordinates
    falloff = Image.new("F", (size, size))
    falloff.putdata(
        [max(0.0, 1.0 - math.hypot(x - middle, y - middle) / radius) ** 2.2 for y in range(size) for x in range(size)]
    )
    noise = Image.frombytes("L", (size, size), rng.randbytes(size * size)).convert("F")
    noise = noise.point(lambda x: x / 256.0)  # uniform in [0, 1), shared by every level and channel

    sprites = []
    for level in range(BRIGHTNESS_LEVELS):
        gain = GLOW_PEAK * (level + 1) / BRIGHTNESS_LEVELS
        planes = []
        for channel in color:
            value = falloff.point(lambda x, k=channel * gain: x * k)  # float colour level
            planes.append(ImageMath.lambda_eval(lambda a: a["v"] + a["n"], v=value, n=noise).convert("L"))
        image = Image.merge("RGB", planes)
        sprites.append(pygame.image.frombytes(image.tobytes(), image.size, "RGB"))
    return sprites


def make_background(width: int, height: int, colors: Colors, rng: random.Random):
    """One monitor's backdrop: a soft vignette with no visible banding.

    This is a dark gradient that spans only ~10 colour levels, so rounding it to
    8 bits leaves contour steps, which show as blocks on a panel that reveals
    dark detail. The cure is to keep the gradient in floating point at full
    resolution and add uniform noise BEFORE rounding: floor(v + u) has expected
    value v, so the steps dissolve into fine grain with no bias. (Adding noise
    to an already-rounded gradient does not remove the steps; an earlier version
    did exactly that.) Pillow does the per-pixel work in C, so this stays fast.
    """
    import pygame
    from PIL import Image, ImageMath

    # The vignette is smooth, so sample it coarsely and let a bicubic float
    # resize fill in the pixels in between.
    sw, sh = max(2, width // 40), max(2, height // 40)
    coarse = Image.new("F", (sw, sh))
    coarse.putdata([vignette_amount((i + 0.5) / sw * 2 - 1, (j + 0.5) / sh * 2 - 1) for j in range(sh) for i in range(sw)])
    amount = coarse.resize((width, height), Image.BICUBIC)

    # Work in strips: full-frame float images (33 MB each at 4K) stream through
    # memory, while a strip stays in CPU cache. One noise field is shared by the
    # three channels, so the grain is neutral grey rather than speckled colour.
    strip_height = 256
    planes = [Image.new("L", (width, height)) for _ in range(3)]
    for top in range(0, height, strip_height):
        rows = min(strip_height, height - top)
        box = (0, top, width, top + rows)
        amount_strip = amount.crop(box)
        noise = Image.frombytes("L", (width, rows), rng.randbytes(width * rows)).convert("F")
        noise = noise.point(lambda x: x / 256.0)  # uniform in [0, 1)
        for c in range(3):
            centre, edge = colors.background[c], colors.background_edge[c]
            value = amount_strip.point(lambda x, a=centre, b=edge: x * (b - a) + a)  # float colour level, e.g. 17.3
            # F -> L truncates, so this is floor(value + noise).
            planes[c].paste(ImageMath.lambda_eval(lambda a: a["v"] + a["n"], v=value, n=noise).convert("L"), (0, top))
    img = Image.merge("RGB", planes)
    return pygame.image.frombytes(img.tobytes(), img.size, "RGB")


def make_halo(coverage, font_height: int, color: tuple[int, int, int], strength: float, rng: random.Random):
    """Soft bloom for the clock text, as an RGB image to be ADDED onto the screen.

    `coverage` is a Pillow "L" image of the text (white on black) whose width and
    height are multiples of HALO_SHRINK. Like the background, the glow is a few
    colour levels high, so it is kept in floating point and dithered before the
    final rounding; otherwise it shows as stair-stepped blocks around the glyphs.
    The earlier version shrank and re-enlarged the text in 8 bits, which did.
    """
    from PIL import Image, ImageFilter, ImageMath

    width, height = coverage.size
    small = coverage.resize((width // HALO_SHRINK, height // HALO_SHRINK), Image.BOX)  # area average
    total = None
    for fraction, weight in HALO_LAYERS:
        sigma = fraction * font_height / HALO_SHRINK
        layer = small.filter(ImageFilter.GaussianBlur(sigma)).convert("F").point(lambda x, w=weight: x * w)
        total = layer if total is None else ImageMath.lambda_eval(lambda a: a["x"] + a["y"], x=total, y=layer)
    field = total.resize((width, height), Image.BICUBIC)  # 0..255 coverage, in float

    noise = Image.frombytes("L", (width, height), rng.randbytes(width * height)).convert("F")
    noise = noise.point(lambda x: x / 256.0)  # uniform in [0, 1)
    planes = []
    for channel in color:
        level = field.point(lambda x, k=channel * strength / 255.0: x * k)  # float colour level
        planes.append(ImageMath.lambda_eval(lambda a: a["v"] + a["n"], v=level, n=noise).convert("L"))
    return Image.merge("RGB", planes)


class MonitorScene:
    """Clock and fireflies for one monitor, drawn into a shared window surface."""

    def __init__(self, area: Rect, cfg: Config, seed: int, log=None):
        import pygame

        self.area = pygame.Rect(area.x, area.y, area.w, area.h)
        self.cfg = cfg
        h = area.h
        self.time_font = load_font(cfg.font, max(24, int(h * 0.22)), log)
        self.date_font = load_font(cfg.font, max(12, int(h * 0.05)), log)
        radii = [max(6, int(h * f)) for f in (0.018, 0.03, 0.045)]
        self.sprites = [make_glow_sprites(r, cfg.colors.accent, random.Random(seed ^ r)) for r in radii]
        self.fireflies = make_fireflies(seed, count_fireflies(area.w, area.h))
        self._text_key: tuple[str, str] | None = None
        self._time_surf = self._date_surf = self._glow_surf = None
        self._glyphs: dict[tuple[str, bool], object] = {}
        self._rng = random.Random(seed ^ 0x5EED)  # dither noise for the halo
        self.background = make_background(area.w, area.h, cfg.colors, random.Random(seed))

    # -- clock text ---------------------------------------------------------
    def _metrics(self, char: str) -> tuple[int, int]:
        """(left ink offset, advance) of one character; the advance is how far the pen moves."""
        found = self.time_font.metrics(char)
        if found and found[0]:
            minx, _maxx, _miny, _maxy, advance = found[0]
            return minx, advance
        return 0, self.time_font.size(char)[0]  # glyph missing from the font

    def _advance(self, text: str) -> int:
        """Pixel width of `text` in the clock font (the pen advance for a single character)."""
        return self._metrics(text)[1] if len(text) == 1 else self.time_font.size(text)[0]

    def _glyph(self, text: str, white: bool):
        """A rendered glyph (or the AM/PM suffix), cached: the clock reuses ~12 of them forever."""
        surface = self._glyphs.get((text, white))
        if surface is None:
            color = (255, 255, 255) if white else self.cfg.colors.text
            surface = self._glyphs[(text, white)] = self.time_font.render(text, True, color)
        return surface

    def _compose_time(self, cells: list[Cell], width: int, white: bool = False):
        """Draw each character centred in its own fixed slot (see clock_cells)."""
        import pygame

        # A little room each side so ink that overhangs the first or last slot is
        # not clipped. The padding is constant, so the width stays constant too.
        pad = self.time_font.get_height() // 10
        surface = pygame.Surface((width + 2 * pad, self.time_font.get_height()), pygame.SRCALPHA)
        for cell in cells:
            if not cell.text.strip():
                continue  # an empty slot
            glyph = self._glyph(cell.text, white)
            if cell.centered:
                # Centre the glyph's advance box in the slot (what the type designer
                # centred the ink in); the rendered surface starts at min(0, left ink offset).
                minx, advance = self._metrics(cell.text)
                x = pad + cell.x + (cell.width - advance) // 2 + min(0, minx)
            else:
                x = pad + cell.x
            surface.blit(glyph, (x, 0))
        return surface

    def _refresh_text(self, time_text: str, date_text: str) -> None:
        import pygame

        if self._text_key == (time_text, date_text):
            return
        self._text_key = (time_text, date_text)
        colors = self.cfg.colors
        cells, time_width = clock_cells(time_text, self._advance)
        self._time_surf = self._compose_time(cells, time_width)
        self._date_surf = self.date_font.render(date_text, True, colors.dim) if date_text else None
        # Soft halo: the text as white-on-black coverage, padded so the wide blur
        # has room, then blurred into a bloom (see make_halo).
        from PIL import Image

        font_height = self.time_font.get_height()
        m = font_height // 2
        tw, th = self._time_surf.get_size()
        pad_w = -(-(tw + 2 * m) // HALO_SHRINK) * HALO_SHRINK  # round up to a multiple
        pad_h = -(-(th + 2 * m) // HALO_SHRINK) * HALO_SHRINK
        canvas = pygame.Surface((pad_w, pad_h))
        canvas.fill((0, 0, 0))
        canvas.blit(self._compose_time(cells, time_width, white=True), (m, m))  # white glyphs: alpha onto black = coverage
        coverage = Image.frombytes("RGB", canvas.get_size(), pygame.image.tobytes(canvas, "RGB")).getchannel("G")
        halo = make_halo(coverage, font_height, colors.accent, HALO_STRENGTH, self._rng)
        self._glow_surf = pygame.image.frombytes(halo.tobytes(), halo.size, "RGB")
        self._glow_margin = m

    # -- one frame ----------------------------------------------------------
    def draw(self, screen, now: datetime, t: float) -> list:
        """Draw this monitor's frame. Returns the rectangles that were touched."""
        import pygame

        time_text, date_text = format_clock(now, self.cfg.clock)
        self._refresh_text(time_text, date_text)
        touched: list[pygame.Rect] = []
        screen.set_clip(self.area)
        ax, ay = self.area.x, self.area.y

        # Layout: time centred slightly above middle, date underneath.
        dx, dy = clock_drift(t, self.area.w, self.area.h)
        tw, th = self._time_surf.get_size()
        tx = ax + (self.area.w - tw) // 2 + dx
        ty = ay + int(self.area.h * 0.46) - th // 2 + dy

        # (Renderer.frame has already restored the background under last frame's
        # rectangles.) Draw back to front: halo, fireflies, then the text.
        touched.append(screen.blit(self._glow_surf, (tx - self._glow_margin, ty - self._glow_margin), special_flags=pygame.BLEND_RGB_ADD))

        for spec in self.fireflies:
            ux, uy, bright = firefly_state(spec, t)
            sprite_set = self.sprites[spec.size_class]
            level = min(BRIGHTNESS_LEVELS - 1, int(bright * BRIGHTNESS_LEVELS))
            sprite = sprite_set[level]
            r = sprite.get_width() // 2
            touched.append(
                screen.blit(sprite, (ax + int(ux * self.area.w) - r, ay + int(uy * self.area.h) - r), special_flags=pygame.BLEND_RGB_ADD)
            )

        touched.append(screen.blit(self._time_surf, (tx, ty)))
        if self._date_surf is not None:
            dw, _ = self._date_surf.get_size()
            touched.append(screen.blit(self._date_surf, (ax + (self.area.w - dw) // 2 + dx, ty + th + int(self.area.h * 0.012))))
        screen.set_clip(None)
        return [r for r in touched if r.width and r.height]


class Renderer:
    """Owns the window-sized background and drives every monitor's scene."""

    def __init__(self, screen, layout: Layout, cfg: Config, seed: int | None = None, log=None):
        import pygame

        self.screen = screen
        self.cfg = cfg
        seed = random.randrange(2**32) if seed is None else seed
        self.scenes = [MonitorScene(area, cfg, seed + i, log) for i, area in enumerate(layout.monitors)]
        # Window-sized backdrop; gaps between monitors (L-shaped layouts) stay dark.
        self.background = pygame.Surface(screen.get_size())
        self.background.fill(cfg.colors.background_edge)
        for scene in self.scenes:
            self.background.blit(scene.background, scene.area.topleft)
            scene.background = None  # now only the window-sized copy is kept
        self._dirty: list = []

    def draw_first_frame(self) -> None:
        self.screen.blit(self.background, (0, 0))

    def frame(self, now: datetime, t: float) -> list:
        """Render one frame; returns the rectangles to push to the display."""
        for r in self._dirty:
            self.screen.blit(self.background, r, r)
        updates = list(self._dirty)
        self._dirty = []
        for scene in self.scenes:
            self._dirty.extend(scene.draw(self.screen, now, t))
        updates.extend(self._dirty)
        return updates
