"""Saria's Song screensaver process.

    python -m saver.main /s              fullscreen saver (what the tray launches)
    python -m saver.main /s --windowed   1280x720 window, handy while developing
    python -m saver.main /c              open config.json
    python -m saver.main /p <hwnd>       preview: not supported, exits at once

`/s`, `/c`, `/p` follow the Windows screensaver convention so this could become
a real `.scr` later. Unlike a real .scr, no argument at all means "run".
Run it from `src/` (`cd src`), as the tray does, so the imports resolve.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from enum import Enum

import applog
import config
import winapi
from saver import exitpolicy
from saver.render import FPS, Layout, Rect, Renderer, plan_layout


class Mode(Enum):
    RUN = "run"
    CONFIG = "config"
    PREVIEW = "preview"


def parse_args(argv: list[str]) -> tuple[Mode, bool]:
    """Return (mode, windowed). Accepts /s, /S, -s, /c, /c:1234, /p 1234 and so on."""
    mode, windowed = Mode.RUN, False
    for arg in argv:
        low = arg.lower()
        if low == "--windowed":
            windowed = True
            continue
        key = low.lstrip("/-").split(":", 1)[0]
        if key == "s":
            mode = Mode.RUN
        elif key == "c":
            mode = Mode.CONFIG
        elif key == "p":
            mode = Mode.PREVIEW
        # Anything else (such as the window handle after /p) is ignored.
    return mode, windowed


def detect_monitors(pygame) -> list[tuple[int, int, int, int, bool]]:
    """(x, y, w, h, is_primary) for each display."""
    rects = winapi.monitor_rects()
    if rects:
        return [(r.x, r.y, r.width, r.height, r.primary) for r in rects]
    # Not Windows (or enumeration failed): lay pygame's desktop sizes out left to right.
    x, out = 0, []
    for i, (w, h) in enumerate(pygame.display.get_desktop_sizes()):
        out.append((x, 0, w, h, i == 0))
        x += w
    return out


def classify(pygame, event) -> str | None:
    """Map a pygame event to an exit-policy event kind, or None if it is not input."""
    t = event.type
    if t == pygame.KEYDOWN:
        return exitpolicy.KEY
    if t == pygame.MOUSEMOTION:
        return exitpolicy.MOUSE_MOVE
    if t in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEWHEEL, pygame.FINGERDOWN):
        return exitpolicy.MOUSE_CLICK
    return None


def _set_window_icon(pygame, log) -> None:
    try:
        from icon import make_icon_image

        img = make_icon_image(32)
        pygame.display.set_icon(pygame.image.frombytes(img.tobytes(), img.size, "RGBA"))
    except Exception:
        log.exception("could not set the window icon")  # cosmetic only


def run_saver(cfg: config.Config, windowed: bool, log) -> int:
    winapi.set_dpi_aware()  # before pygame creates a window: physical pixels, no blur
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    # Not pygame.init(): that would also open the audio device and scan joysticks.
    pygame.display.init()
    pygame.font.init()
    try:
        if windowed:
            layout = Layout(Rect(100, 100, 1280, 720), (Rect(0, 0, 1280, 720),))
            flags = 0
        else:
            layout = plan_layout(detect_monitors(pygame), cfg.monitors)
            flags = pygame.NOFRAME  # borderless "fake fullscreen": no mode switch, streams cleanly
        win = layout.window
        log.info("window %dx%d at (%d,%d); %d monitor(s)", win.w, win.h, win.x, win.y, len(layout.monitors))
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{win.x},{win.y}"
        screen = pygame.display.set_mode((win.w, win.h), flags)
        pygame.display.set_caption(config.APP_NAME)
        _set_window_icon(pygame, log)
        if not windowed:
            hwnd = pygame.display.get_wm_info().get("window")
            if hwnd:
                winapi.make_topmost(hwnd, win.x, win.y, win.w, win.h)
                winapi.bring_to_front(hwnd)
            pygame.mouse.set_visible(False)

        started = time.monotonic()
        # No starting pointer position on purpose: SDL only learns the position
        # from events, so pygame.mouse.get_pos() can be a stale (0, 0) right after
        # the window opens. The first mouse event is the reference instead.
        policy = exitpolicy.ExitPolicy(
            start=started,
            grace_seconds=cfg.grace_seconds,
            exit_on=cfg.exit_on,
            move_threshold_px=cfg.mouse_move_threshold_px,
        )
        renderer = Renderer(screen, layout, cfg, log=log)
        renderer.draw_first_frame()
        pygame.display.flip()
        log.info("saver running (%d fps cap, grace %.1fs)", FPS, cfg.grace_seconds)

        frame_clock = pygame.time.Clock()
        running = True
        while running:
            now = time.monotonic()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                kind = classify(pygame, event)
                if kind and policy.should_exit(kind, now, getattr(event, "pos", None)):
                    log.info("exit on %s", kind)
                    running = False
                    break  # one event is enough; the rest of this batch must not log again
            if not running:
                break
            pygame.display.update(renderer.frame(datetime.now(), (now - started) * cfg.animation_speed))
            frame_clock.tick(FPS)
        return 0
    finally:
        pygame.quit()


def main(argv: list[str] | None = None) -> int:
    log = applog.setup("saver")
    mode, windowed = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if mode is Mode.PREVIEW:
            return 0  # the tiny preview pane in the Windows dialog is not supported
        if mode is Mode.CONFIG:
            from launcher import open_config_file

            open_config_file()
            return 0
        cfg = config.load()
        for warning in cfg.warnings:
            log.warning("config: %s", warning)
        return run_saver(cfg, windowed, log)
    except Exception:
        log.exception("saver crashed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
