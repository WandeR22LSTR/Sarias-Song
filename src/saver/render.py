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
from typing import Sequence

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
CLOCK_GLOW_STRENGTH = 0.2
FPS = 30


def _scaled(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(min(255, max(0, round(c * factor))) for c in color)  # type: ignore[return-value]


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


def make_glow_sprites(radius: int, color: tuple[int, int, int]):
    """Brightness ladder of one soft round glow, for additive blending."""
    import pygame

    size = radius * 2
    base = pygame.Surface((size, size))
    base.fill((0, 0, 0))
    # Draw rings from the outside in, each brighter than the last. Cheap, and
    # smooth enough at these low intensities. falloff^2.2 gives a soft halo.
    for r in range(radius, 0, -1):
        k = (1 - r / radius) ** 2.2
        pygame.draw.circle(base, _scaled(color, k * GLOW_PEAK), (radius, radius), r)
    sprites = []
    for level in range(BRIGHTNESS_LEVELS):
        s = base.copy()
        v = round(255 * (level + 1) / BRIGHTNESS_LEVELS)
        s.fill((v, v, v), special_flags=pygame.BLEND_RGB_MULT)
        sprites.append(s)
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
        self.sprites = [make_glow_sprites(r, cfg.colors.accent) for r in radii]
        self.fireflies = make_fireflies(seed, count_fireflies(area.w, area.h))
        self._text_key: tuple[str, str] | None = None
        self._time_surf = self._date_surf = self._glow_surf = None
        self.background = make_background(area.w, area.h, cfg.colors, random.Random(seed))

    # -- clock text ---------------------------------------------------------
    def _refresh_text(self, time_text: str, date_text: str) -> None:
        import pygame

        if self._text_key == (time_text, date_text):
            return
        self._text_key = (time_text, date_text)
        colors = self.cfg.colors
        self._time_surf = self.time_font.render(time_text, True, colors.text)
        self._date_surf = self.date_font.render(date_text, True, colors.dim) if date_text else None
        # Soft halo: render the time on black, shrink and re-enlarge to blur it.
        m = self.time_font.get_height() // 2
        tw, th = self._time_surf.get_size()
        halo = pygame.Surface((tw + 2 * m, th + 2 * m))
        halo.fill((0, 0, 0))
        halo.blit(self.time_font.render(time_text, True, colors.accent), (m, m))
        small = pygame.transform.smoothscale(halo, (max(1, halo.get_width() // 8), max(1, halo.get_height() // 8)))
        glow = pygame.transform.smoothscale(small, halo.get_size())
        v = round(255 * CLOCK_GLOW_STRENGTH * 3)  # blur spreads energy, so lift it back
        glow.fill((min(v, 255),) * 3, special_flags=pygame.BLEND_RGB_MULT)
        self._glow_surf = glow
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
