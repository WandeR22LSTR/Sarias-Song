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


def test_lerp_color():
    assert render.lerp_color((0, 0, 0), (100, 200, 50), 0.5) == (50, 100, 25)
    assert render.lerp_color((10, 10, 10), (20, 20, 20), 0) == (10, 10, 10)


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


def test_background_has_no_exact_tile_repetition(pg):
    # The dither must not repeat on a fixed period (it once did at 128 px, a faint grid).
    surf = render.make_background(1024, 256, config.from_dict({}).colors, random.Random(4))
    row = lambda x: [surf.get_at((x + i, 128))[1] for i in range(256)]  # noqa: E731
    assert row(0) != row(256) or row(256) != row(512)


def test_font_fallback_uses_builtin_when_nothing_matches(pg):
    font = render.load_font("No Such Font, Also Missing", 40)
    assert font.get_height() > 0
