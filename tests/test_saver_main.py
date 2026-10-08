import logging

import pytest

import applog
import config
from saver import main as saver_main
from saver.main import Mode, parse_args


# Captured once: wrapping Renderer.frame again inside one test would chain wrappers.
REAL_FRAME = saver_main.Renderer.frame


@pytest.fixture(autouse=True)
def isolated_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(applog, "log_dir", lambda: tmp_path / "logs")


@pytest.mark.parametrize(
    "argv, expected",
    [
        ([], (Mode.RUN, False)),  # not a real .scr: no argument means "run"
        (["/s"], (Mode.RUN, False)),
        (["/S"], (Mode.RUN, False)),
        (["-s"], (Mode.RUN, False)),
        (["/s", "--windowed"], (Mode.RUN, True)),
        (["/c"], (Mode.CONFIG, False)),
        (["/c:1234"], (Mode.CONFIG, False)),
        (["/C:1234"], (Mode.CONFIG, False)),
        (["/p", "1234"], (Mode.PREVIEW, False)),
        (["/p:5678"], (Mode.PREVIEW, False)),
        (["/P", "99"], (Mode.PREVIEW, False)),
        (["/s", "nonsense"], (Mode.RUN, False)),
    ],
)
def test_parse_args(argv, expected):
    assert parse_args(argv) == expected


def test_preview_exits_immediately_without_touching_pygame(monkeypatch):
    monkeypatch.setattr(saver_main, "run_saver", lambda *a: pytest.fail("must not run the saver"))
    assert saver_main.main(["/p", "1234"]) == 0


def test_config_mode_opens_the_config_file(monkeypatch):
    import launcher

    opened = []
    monkeypatch.setattr(launcher, "open_config_file", lambda: opened.append(True))
    monkeypatch.setattr(saver_main, "run_saver", lambda *a: pytest.fail("must not run the saver"))
    assert saver_main.main(["/c"]) == 0
    assert opened == [True]


def test_a_crash_is_contained_logged_and_returns_nonzero(monkeypatch):
    def boom(*a):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(saver_main, "run_saver", boom)
    assert saver_main.main(["/s"]) == 1  # the tray sees a non-zero exit code and logs it


def test_config_warnings_do_not_stop_the_saver(monkeypatch, tmp_path):
    bad = tmp_path / "config.json"
    bad.write_text('{"mode": "disco", "colors": {"accent": "nope"}}', encoding="utf-8")
    monkeypatch.setattr(config, "config_path", lambda: bad)
    seen = {}
    monkeypatch.setattr(saver_main, "run_saver", lambda cfg, windowed, log: seen.update(cfg=cfg) or 0)
    assert saver_main.main(["/s"]) == 0
    assert seen["cfg"].warnings and seen["cfg"].mode == "clock"


def test_classify_maps_input_events(monkeypatch):
    pygame = pytest.importorskip("pygame")
    ev = pygame.event.Event
    assert saver_main.classify(pygame, ev(pygame.KEYDOWN, key=pygame.K_a)) == "key"
    assert saver_main.classify(pygame, ev(pygame.MOUSEMOTION, pos=(1, 2), rel=(1, 1), buttons=(0, 0, 0))) == "mouse_move"
    assert saver_main.classify(pygame, ev(pygame.MOUSEBUTTONDOWN, pos=(1, 2), button=1)) == "mouse_click"
    assert saver_main.classify(pygame, ev(pygame.MOUSEWHEEL, x=0, y=1)) == "mouse_click"
    assert saver_main.classify(pygame, ev(pygame.KEYUP, key=pygame.K_a)) is None  # releasing the launch click/key
    assert saver_main.classify(pygame, ev(pygame.WINDOWFOCUSLOST)) is None


# --- the real event loop, headless -----------------------------------------


@pytest.fixture
def loop_env(monkeypatch):
    pygame = pytest.importorskip("pygame")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_VIDEO_WINDOW_POS", "0,0")  # registered so the saver's own change is undone
    return pygame


def run_with_scripted_events(pygame, monkeypatch, script, **cfg_overrides):
    """Run the saver loop in a window with scripted input. `script[i]` is the
    list of events delivered on loop iteration i. A fake clock advances 0.5 s per
    iteration so grace periods can be tested without waiting."""
    clock = {"t": 1000.0}
    iteration = {"i": 0}
    frames = []

    def fake_get():
        i = iteration["i"]
        iteration["i"] += 1
        clock["t"] += 0.5
        return script[i] if i < len(script) else [pygame.event.Event(pygame.QUIT)]

    monkeypatch.setattr(pygame.event, "get", fake_get)
    monkeypatch.setattr(saver_main.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(saver_main.Renderer, "frame", lambda self, now, t: frames.append(t) or REAL_FRAME(self, now, t))
    # Don't actually sleep to hold 30 fps. (Clock is an immutable C type, so
    # replace the class on the module rather than its method.)
    class NoSleepClock:
        def tick(self, fps=0):
            return 0

    monkeypatch.setattr(pygame.time, "Clock", NoSleepClock)

    cfg = config.from_dict(cfg_overrides)
    code = saver_main.run_saver(cfg, windowed=True, log=logging.getLogger("loop-test"))
    return code, frames


def key():
    import pygame

    return pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)


def test_key_during_grace_is_ignored_and_a_later_key_exits(loop_env, monkeypatch):
    pygame = loop_env
    # grace 2 s, clock advances 0.5 s per loop: iterations 0..3 are inside it.
    script = [[key()], [], [key()], [], [], [key()]]
    code, frames = run_with_scripted_events(pygame, monkeypatch, script, grace_seconds=2.0)
    assert code == 0
    assert len(frames) == 5  # drew frames for iterations 0-4, exited on iteration 5


def test_small_mouse_jitter_is_ignored_but_a_real_move_exits(loop_env, monkeypatch):
    pygame = loop_env
    move = lambda p: pygame.event.Event(pygame.MOUSEMOTION, pos=p, rel=(1, 1), buttons=(0, 0, 0))  # noqa: E731
    script = [[], [], [], [], [move((10, 10))], [move((14, 12))], [move((300, 300))]]
    code, frames = run_with_scripted_events(pygame, monkeypatch, script, grace_seconds=1.0)
    assert code == 0
    assert len(frames) == 6  # the 4 px wiggle did not end it; the 290 px move did


def test_window_close_event_ends_the_saver(loop_env, monkeypatch):
    pygame = loop_env
    code, frames = run_with_scripted_events(pygame, monkeypatch, [[], [pygame.event.Event(pygame.QUIT)]])
    assert code == 0 and len(frames) == 1


def test_animation_speed_scales_time(loop_env, monkeypatch):
    pygame = loop_env
    _, normal = run_with_scripted_events(pygame, monkeypatch, [[], [], []], animation_speed=1.0)
    _, double = run_with_scripted_events(pygame, monkeypatch, [[], [], []], animation_speed=2.0)
    assert double[-1] == pytest.approx(normal[-1] * 2)
    _, frozen = run_with_scripted_events(pygame, monkeypatch, [[], [], []], animation_speed=0)
    assert set(frozen) == {0.0}
