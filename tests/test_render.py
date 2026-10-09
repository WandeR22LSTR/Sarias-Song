import math
import random
from datetime import datetime

import pytest

import config
from saver import render
from saver.render import Rect


def clock(**kw):
    base = dict(format_24h=True, show_seconds=False, show_date=True)
    base.update(kw)
    return config.ClockConfig(**base)


# --- clock text ------------------------------------------------------------


def test_clock_24h_with_date():
    assert render.format_clock(datetime(2026, 10, 8, 22, 47, 5), clock()) == ("22:47", "Thursday, 8 October")


def test_clock_24h_pads_hours():
    assert render.format_clock(datetime(2026, 1, 1, 7, 5), clock())[0] == "07:05"


@pytest.mark.parametrize(
    "hour, expected",
    [(0, "12:30 AM"), (1, "1:30 AM"), (11, "11:30 AM"), (12, "12:30 PM"), (13, "1:30 PM"), (23, "11:30 PM")],
)
def test_clock_12h(hour, expected):
    assert render.format_clock(datetime(2026, 1, 1, hour, 30), clock(format_24h=False))[0] == expected


def test_clock_seconds_come_before_am_pm():
    assert render.format_clock(datetime(2026, 1, 1, 15, 4, 9), clock(format_24h=False, show_seconds=True))[0] == "3:04:09 PM"


def test_clock_date_can_be_hidden():
    assert render.format_clock(datetime(2026, 10, 8, 1, 2), clock(show_date=False))[1] == ""


def test_clock_text_ignores_the_locale(monkeypatch):
    import locale

    monkeypatch.setattr(locale, "getlocale", lambda *a: ("de_DE", "UTF-8"))
    assert render.format_clock(datetime(2026, 3, 2, 0, 0), clock())[1] == "Monday, 2 March"


# --- window layout ---------------------------------------------------------


def test_layout_single_monitor():
    layout = render.plan_layout([(0, 0, 1920, 1080, True)], "all")
    assert layout.window == Rect(0, 0, 1920, 1080)
    assert layout.monitors == (Rect(0, 0, 1920, 1080),)


def test_layout_all_spans_both_monitors_with_offsets():
    mons = [(0, 360, 1920, 1080, True), (1920, 0, 2560, 1440, False)]
    layout = render.plan_layout(mons, "all")
    assert layout.window == Rect(0, 0, 4480, 1440)
    assert layout.monitors == (Rect(0, 360, 1920, 1080), Rect(1920, 0, 2560, 1440))


def test_layout_handles_monitor_left_of_primary_with_negative_coordinates():
    mons = [(0, 0, 1920, 1080, True), (-1280, -100, 1280, 1024, False)]
    layout = render.plan_layout(mons, "all")
    assert layout.window == Rect(-1280, -100, 3200, 1180)
    # Positions are relative to the window's own top-left corner.
    assert layout.monitors == (Rect(1280, 100, 1920, 1080), Rect(0, 0, 1280, 1024))


def test_layout_primary_only_picks_the_flagged_monitor():
    mons = [(0, 0, 1280, 720, False), (1280, 0, 1920, 1080, True)]
    layout = render.plan_layout(mons, "primary")
    assert layout.window == Rect(1280, 0, 1920, 1080)
    assert layout.monitors == (Rect(0, 0, 1920, 1080),)


def test_layout_primary_without_a_flag_uses_the_first():
    layout = render.plan_layout([(0, 0, 800, 600, False), (800, 0, 800, 600, False)], "primary")
    assert layout.window == Rect(0, 0, 800, 600)


def test_layout_without_monitors_is_an_error():
    with pytest.raises(ValueError):
        render.plan_layout([], "all")


# --- ambient animation -----------------------------------------------------


def test_fireflies_are_deterministic_per_seed():
    assert render.make_fireflies(5, 20) == render.make_fireflies(5, 20)
    assert render.make_fireflies(5, 20) != render.make_fireflies(6, 20)


def test_fireflies_stay_inside_the_monitor_for_hours():
    margin = render.MARGIN - 0.01  # allow for the small quick wobble
    for spec in render.make_fireflies(123, 60):
        for t in range(0, 8 * 3600, 97):
            x, y, b = render.firefly_state(spec, float(t))
            assert margin <= x <= 1 - margin and margin <= y <= 1 - margin, (spec, t)
            assert 0.2 - 1e-9 <= b <= 1.0 + 1e-9


def test_firefly_motion_is_gentle():
    # Restrained animation: no jumps between consecutive frames (30 fps) on a 1080p screen.
    for spec in render.make_fireflies(9, 40):
        x0, y0, _ = render.firefly_state(spec, 100.0)
        x1, y1, _ = render.firefly_state(spec, 100.0 + 1 / 30)
        assert abs(x1 - x0) * 1920 < 1.5 and abs(y1 - y0) * 1080 < 1.5


def test_firefly_count_scales_with_screen_but_is_clamped():
    assert render.count_fireflies(800, 600) == 14
    assert 20 <= render.count_fireflies(1920, 1080) <= 26
    assert render.count_fireflies(7680, 4320) == 40


def test_clock_drift_is_small_slow_and_bounded():
    reach = 0.012 * 1080
    for t in range(0, 4 * 3600, 53):
        dx, dy = render.clock_drift(float(t), 1920, 1080)
        assert abs(dx) <= reach + 1 and abs(dy) <= reach + 1
    assert render.clock_drift(0.0, 1920, 1080) == render.clock_drift(0.0, 1920, 1080)


def test_vignette_is_dark_centre_to_bright_corner():
    assert render.vignette_amount(0, -0.12) == 0.0
    assert render.vignette_amount(1, 1) == 1.0
    samples = [render.vignette_amount(i / 10, 0) for i in range(11)]
    assert samples == sorted(samples)


# --- pygame drawing (headless) ---------------------------------------------


@pytest.fixture
def pg(monkeypatch):
    pygame = pytest.importorskip("pygame")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    pygame.font.init()
    yield pygame
    pygame.quit()


def make_renderer(pg, monitors, size, seed=1, **cfg):
    screen = pg.display.set_mode(size)
    layout = render.Layout(Rect(0, 0, *size), tuple(monitors))
    return screen, render.Renderer(screen, layout, config.from_dict(cfg), seed=seed)


NOW = datetime(2026, 10, 8, 22, 47, 5)


def test_renderer_draws_frames_and_reports_rects_inside_the_window(pg):
    screen, r = make_renderer(pg, [Rect(0, 0, 960, 540)], (960, 540))
    r.draw_first_frame()
    bounds = screen.get_rect()
    for i in range(5):
        updates = r.frame(NOW, i * 10.0)
        assert updates, "every frame must report something to redraw"
        assert all(bounds.contains(u) for u in updates)


def test_clock_is_actually_drawn_near_the_centre(pg):
    screen, r = make_renderer(pg, [Rect(0, 0, 960, 540)], (960, 540))
    r.draw_first_frame()
    r.frame(NOW, 0.0)
    text_color = config.from_dict({}).colors.text
    centre_band = [screen.get_at((x, y))[:3] for x in range(300, 660) for y in range(180, 320)]
    bright = [c for c in centre_band if sum(c) > 0.6 * sum(text_color)]
    assert len(bright) > 300, "expected clock glyph pixels in the middle of the screen"


def test_dirty_rect_restore_leaves_no_trails(pg):
    # Draw many frames while things move, then compare with a fresh full render
    # of the same instant: partial updates must give the same picture.
    screen, r = make_renderer(pg, [Rect(0, 0, 960, 540)], (960, 540), seed=3)
    r.draw_first_frame()
    for i in range(30):
        r.frame(NOW, i * 7.0)
    incremental = pg.image.tobytes(screen, "RGB")

    screen2, r2 = make_renderer(pg, [Rect(0, 0, 960, 540)], (960, 540), seed=3)
    r2.draw_first_frame()
    r2.frame(NOW, 29 * 7.0)
    assert pg.image.tobytes(screen2, "RGB") == incremental


def test_nothing_is_drawn_outside_a_monitor_area(pg):
    # Two monitors with a dark gap between/around them: fireflies near an edge
    # must not leak into the gap (the clip rectangle is per monitor).
    monitors = [Rect(0, 100, 640, 360), Rect(700, 0, 640, 360)]
    screen, r = make_renderer(pg, monitors, (1340, 460))
    r.draw_first_frame()
    gap_before = [screen.get_at((x, y))[:3] for x in range(645, 695) for y in range(0, 460, 7)]
    for i in range(20):
        r.frame(NOW, i * 31.0)
    gap_after = [screen.get_at((x, y))[:3] for x in range(645, 695) for y in range(0, 460, 7)]
    assert gap_before == gap_after
    below_second = [screen.get_at((x, y))[:3] for x in range(700, 1340, 9) for y in range(365, 460, 9)]
    assert set(below_second) == {config.from_dict({}).colors.background_edge}


def _ideal_level(colors, channel, x, y, w, h):
    """The exact (unrounded) colour level the vignette should have at a pixel."""
    amount = render.vignette_amount((x + 0.5) / w * 2 - 1, (y + 0.5) / h * 2 - 1)
    centre, edge = colors.background[channel], colors.background_edge[channel]
    return centre + (edge - centre) * amount


def test_background_dither_is_unbiased_so_gradient_steps_cannot_form(pg):
    # Regression for the blocky look on Spirit Temple's 1440p monitor. The gradient only
    # spans ~10 colour levels. Noise added after rounding (the old code) left 1-level
    # rectangular steps and shifted everything up by ~0.5 level. Noise added before rounding
    # gives, on average, exactly the unrounded gradient, so any patch's mean must match it.
    colors = config.from_dict({}).colors
    w, h = 1280, 720
    surf = render.make_background(w, h, colors, random.Random(4))
    for x0, y0 in [(40, 40), (580, 300), (1100, 600), (560, 20), (20, 610)]:  # each patch stays inside 1280x720
        size = 100
        for channel in range(3):
            measured = sum(surf.get_at((x, y))[channel] for x in range(x0, x0 + size) for y in range(y0, y0 + size)) / size**2
            expected = sum(_ideal_level(colors, channel, x, y, w, h) for x in range(x0, x0 + size) for y in range(y0, y0 + size)) / size**2
            assert abs(measured - expected) < 0.12, (x0, y0, channel, measured, expected)


def test_background_has_grain_not_flat_bands(pg):
    # Dither means neighbouring pixels differ by a level now and then; a banded gradient
    # would be perfectly flat over long runs.
    colors = config.from_dict({}).colors
    surf = render.make_background(800, 600, colors, random.Random(2))
    row = [surf.get_at((x, 300))[1] for x in range(200, 600)]
    assert len(set(row)) >= 2
    assert sum(1 for a, b in zip(row, row[1:]) if a != b) > 40  # many level changes, not a few steps


def test_background_has_no_seams_between_processing_strips(pg):
    # The background is built in 256-row strips; row averages must flow across the joins.
    colors = config.from_dict({}).colors
    w, h = 1200, 700
    surf = render.make_background(w, h, colors, random.Random(5))
    for seam in (256, 512):
        means = [sum(surf.get_at((x, y))[1] for x in range(100, 1100)) / 1000 for y in range(seam - 6, seam + 6)]
        assert max(abs(b - a) for a, b in zip(means, means[1:])) < 0.1, (seam, means)


def test_firefly_glow_matches_the_analytic_falloff_within_one_dither_level(pg):
    # Regression for faint concentric rings and radial spokes (1 px rings drawn in 8 bits).
    # floor(value + noise) is always within 1 level of the exact float value, so a
    # sprite built the right way agrees with the formula at EVERY pixel.
    radius, accent = 40, (127, 212, 138)
    sprites = render.make_glow_sprites(radius, accent, random.Random(3))
    assert len(sprites) == render.BRIGHTNESS_LEVELS
    middle = radius - 0.5
    for level in (0, 4, 9):
        gain = render.GLOW_PEAK * (level + 1) / render.BRIGHTNESS_LEVELS
        sprite = sprites[level]
        assert sprite.get_size() == (2 * radius, 2 * radius)
        for y in range(2 * radius):
            for x in range(2 * radius):
                falloff = max(0.0, 1.0 - math.hypot(x - middle, y - middle) / radius) ** 2.2
                got = sprite.get_at((x, y))
                for channel in range(3):
                    assert abs(got[channel] - accent[channel] * gain * falloff) <= 1.0, (level, x, y, channel)


def test_firefly_glow_is_exactly_black_outside_its_circle_so_no_square_edge_shows(pg):
    sprites = render.make_glow_sprites(30, (127, 212, 138), random.Random(1))
    for sprite in sprites:
        for corner in ((0, 0), (59, 0), (0, 59), (59, 59), (2, 2), (57, 3)):
            assert sprite.get_at(corner)[:3] == (0, 0, 0)


def test_brighter_levels_are_brighter(pg):
    sprites = render.make_glow_sprites(30, (127, 212, 138), random.Random(1))
    centres = [s.get_at((29, 29))[1] for s in sprites]
    assert centres == sorted(centres) and centres[-1] > centres[0] * 5


def _block_coverage(width=800, height=400, box=(300, 100, 500, 300)):
    from PIL import Image, ImageDraw

    coverage = Image.new("L", (width, height), 0)
    ImageDraw.Draw(coverage).rectangle(box, fill=255)
    return coverage


def test_halo_falls_off_smoothly_with_no_stair_steps(pg):
    # Regression for the blocky edge around the clock digits. The old halo enlarged an
    # 8x-shrunk mask in 8 bits, giving ~8 px stair steps. Row-averaging cancels the dither
    # grain; a smooth glow then has a tiny second difference, a stair has a huge one.
    halo = render.make_halo(_block_coverage(), 200, (100, 200, 100), 0.5, random.Random(1))
    green = halo.getchannel("G")
    profile = [sum(green.getpixel((x, y)) for y in range(140, 260)) / 120 for x in range(500, 780)]
    second = [profile[i - 1] - 2 * profile[i] + profile[i + 1] for i in range(1, len(profile) - 1)]
    assert max(abs(s) for s in second) < 1.0
    assert all(a >= b - 0.15 for a, b in zip(profile, profile[1:])), "glow must fade steadily outward"
    assert profile[0] > 30 and profile[-1] < 2  # a real glow at the edge, nothing left far away


def test_halo_far_from_the_text_is_exactly_black(pg):
    # floor(0 + noise) is 0, so the dither can never lift the black far field.
    halo = render.make_halo(_block_coverage(), 200, (100, 200, 100), 0.5, random.Random(1))
    assert halo.crop((0, 0, 40, 40)).getextrema() == ((0, 0), (0, 0), (0, 0))


def test_halo_is_centred_on_the_text_and_tinted_with_the_accent(pg):
    from PIL import Image

    halo = render.make_halo(_block_coverage(), 200, (60, 200, 100), 0.5, random.Random(1))
    green = halo.getchannel("G")
    columns = list(green.resize((800, 1), Image.BOX).getdata())
    rows = list(green.resize((1, 400), Image.BOX).getdata())
    centroid_x = sum(i * v for i, v in enumerate(columns)) / sum(columns)
    centroid_y = sum(i * v for i, v in enumerate(rows)) / sum(rows)
    assert abs(centroid_x - 400) < 2 and abs(centroid_y - 200) < 2  # blur has not shifted it
    # Brightness ratio between channels follows the accent colour (60 : 200 : 100).
    means = [sum(halo.getchannel(c).resize((1, 1), Image.BOX).getdata()) for c in "RGB"]
    assert means[1] > means[2] > means[0]


def test_clock_halo_surface_is_padded_to_a_multiple_of_the_shrink_factor(pg):
    scene = render.MonitorScene(Rect(0, 0, 1000, 700), config.from_dict({}), seed=1)
    for text in ("22:47", "7:05 PM", "11:11:11"):
        scene._refresh_text(text, "Thursday, 8 October")
        w, h = scene._glow_surf.get_size()
        assert w % render.HALO_SHRINK == 0 and h % render.HALO_SHRINK == 0
        tw, th = scene._time_surf.get_size()
        assert w >= tw + 2 * scene._glow_margin and h >= th + 2 * scene._glow_margin


def test_background_handles_sizes_that_are_not_strip_multiples(pg):
    for w, h in [(1000, 700), (333, 257), (64, 64), (2, 2)]:
        assert render.make_background(w, h, config.from_dict({}).colors, random.Random(1)).get_size() == (w, h)


def test_font_fallback_uses_builtin_when_nothing_matches(pg):
    font = render.load_font("No Such Font, Also Missing", 40)
    assert font.get_height() > 0
