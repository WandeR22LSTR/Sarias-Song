import logging
import os

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
    monkeypatch.delenv("SDL_VIDEO_ALLOW_SCREENSAVER", raising=False)  # likewise, and so the test sees the saver set it
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


def test_a_burst_of_events_logs_the_exit_once(loop_env, monkeypatch, caplog):
    # Seen on Spirit Temple: three key events in one batch logged "exit on key" three times.
    pygame = loop_env
    script = [[], [], [], [], [key(), key(), key()]]
    with caplog.at_level(logging.INFO, logger="loop-test"):
        code, _ = run_with_scripted_events(pygame, monkeypatch, script, grace_seconds=1.0)
    assert code == 0
    assert [r.getMessage() for r in caplog.records].count("exit on key") == 1


def _recording_keep_awake(monkeypatch, calls):
    """Make run_saver build a KeepAwake that records the flags it is asked to set."""
    real = saver_main.keepawake.KeepAwake
    monkeypatch.setattr(
        saver_main.keepawake, "KeepAwake", lambda log: real(log, lambda flags: calls.append(flags) or 0x80000000)
    )


def test_keep_awake_is_held_while_the_saver_runs_and_released_after(loop_env, monkeypatch):
    pygame = loop_env
    calls, seen_while_drawing = [], []
    _recording_keep_awake(monkeypatch, calls)
    real_update = pygame.display.update
    # (Hooking display.update, which the helper leaves alone: it re-patches Renderer.frame.)
    monkeypatch.setattr(pygame.display, "update", lambda rects=None: seen_while_drawing.append(list(calls)) or real_update(rects))
    code, _ = run_with_scripted_events(pygame, monkeypatch, [[], []])
    assert code == 0
    assert calls == [0x80000001, 0x80000000]  # on at the start (ES_CONTINUOUS | ES_SYSTEM_REQUIRED), cleared at the end
    assert seen_while_drawing and all(c == [0x80000001] for c in seen_while_drawing), "held for every frame"


def test_sdl_is_told_to_allow_the_screensaver_so_it_cannot_override_keep_awake(loop_env, monkeypatch):
    # Regression for what powercfg /requests showed on Spirit Temple: SDL's own request to keep the
    # DISPLAY on (it disables the screensaver by default) replaced the SYSTEM request.
    pygame = loop_env
    allowed = []
    real_update = pygame.display.update
    monkeypatch.setattr(
        pygame.display, "update", lambda rects=None: allowed.append(pygame.display.get_allow_screensaver()) or real_update(rects)
    )
    run_with_scripted_events(pygame, monkeypatch, [[], []])
    assert allowed and all(allowed), "the screensaver must be allowed while the saver is drawing"
    assert os.environ.get("SDL_VIDEO_ALLOW_SCREENSAVER") == "1"


def test_keep_awake_is_reasserted_on_the_periodic_tick(loop_env, monkeypatch):
    pygame = loop_env
    calls = []
    _recording_keep_awake(monkeypatch, calls)
    run_with_scripted_events(pygame, monkeypatch, [[] for _ in range(30)])  # 15 s of fake time: one 10 s tick
    on = 0x80000001
    assert calls == [on, on, 0x80000000]  # start, one refresh at the 10 s report, then cleared


def test_keep_awake_is_released_even_if_the_saver_crashes(loop_env, monkeypatch):
    pygame = loop_env
    calls = []
    _recording_keep_awake(monkeypatch, calls)

    def boom(rects=None):
        raise RuntimeError("display exploded")

    monkeypatch.setattr(pygame.display, "update", boom)
    with pytest.raises(RuntimeError):
        run_with_scripted_events(pygame, monkeypatch, [[], []])
    assert calls == [0x80000001, 0x80000000]  # a crash must not leave the PC unable to sleep


def test_the_saver_logs_its_own_cpu_and_memory(loop_env, monkeypatch, caplog):
    # Luca cannot watch Task Manager behind a fullscreen saver, so it reports to saver.log:
    # a line after PERF_FIRST_REPORT_SECONDS, one per minute after that, and a total at exit.
    pygame = loop_env
    script = [[] for _ in range(30)]  # the fake clock runs 0.5 s per loop: 15 s, so the 10 s report fires
    with caplog.at_level(logging.INFO, logger="loop-test"):
        code, _ = run_with_scripted_events(pygame, monkeypatch, script)
    assert code == 0
    messages = [r.getMessage() for r in caplog.records]
    periodic = [m for m in messages if m.startswith("perf: ")]
    assert len(periodic) == 1, messages
    assert "of one core" in periodic[0] and "logical processors" in periodic[0] and "frames, work avg" in periodic[0]
    assert any(m.startswith("perf over the whole run") for m in messages), messages


def test_a_short_run_logs_only_the_final_total(loop_env, monkeypatch, caplog):
    pygame = loop_env
    with caplog.at_level(logging.INFO, logger="loop-test"):
        run_with_scripted_events(pygame, monkeypatch, [[], [], []])
    messages = [r.getMessage() for r in caplog.records]
    assert not [m for m in messages if m.startswith("perf: ")]
    assert any(m.startswith("perf over the whole run") for m in messages)


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
