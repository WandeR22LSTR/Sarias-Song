"""Saria's Song tray app.

Left-click the green note to start the screensaver; right-click for the menu.

    python src/tray.py                      run the tray app
    python src/tray.py --install-autostart  start it at every login
    python src/tray.py --uninstall-autostart
"""

from __future__ import annotations

import argparse
import functools
import sys
import threading
from pathlib import Path

# Allow `python src/tray.py` from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import applog  # noqa: E402
import autostart  # noqa: E402
import config  # noqa: E402
import perfstats  # noqa: E402
import winapi  # noqa: E402
from launcher import SaverLauncher, open_config_file  # noqa: E402

INSTANCE_MUTEX = "SariasSong.Tray"
TRAY_PERF_FIRST_SECONDS = 60
TRAY_PERF_EVERY_SECONDS = 300


def _guarded(log, fn):
    """Menu callbacks run on pystray's thread: log failures instead of losing them."""

    @functools.wraps(fn)
    def wrapper(*args):
        try:
            return fn()
        except Exception:
            log.exception("menu action %s failed", getattr(fn, "__name__", fn))

    return wrapper


def run_tray() -> int:
    log = applog.setup("tray")

    instance = winapi.acquire_single_instance(INSTANCE_MUTEX)
    if instance is None:
        log.info("another tray instance is already running; exiting")
        return 0

    # pystray is imported here, not at the top: on Linux its import needs a
    # display, and everything above must stay importable for the tests.
    import pystray

    from icon import make_icon_image

    launcher = SaverLauncher(log)
    # The tray's own CPU and memory, logged (after a minute, then every 5) so a
    # slow leak over a long uptime would show up in logs\tray.log.
    stop_reporting = threading.Event()
    perfstats.start_reporter(log, "tray", TRAY_PERF_FIRST_SECONDS, TRAY_PERF_EVERY_SECONDS, stop_reporting)
    start_saver = _guarded(log, launcher.start)
    open_settings = _guarded(log, open_config_file)

    menu = pystray.Menu(
        # default=True is what a left-click activates.
        pystray.MenuItem("Start screensaver", lambda icon, item: start_saver(), default=True),
        pystray.MenuItem("Settings", lambda icon, item: open_settings()),
        pystray.MenuItem("Exit", lambda icon, item: icon.stop()),
    )
    icon = pystray.Icon("saria-song", make_icon_image(64), config.APP_NAME, menu)
    log.info("tray started (python %s)", sys.version.split()[0])
    try:
        icon.run()  # blocks until Exit; `instance` (the mutex) stays referenced meanwhile
    finally:
        stop_reporting.set()
        launcher.stop()
        log.info("tray stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tray", description=f"{config.APP_NAME} tray app")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install-autostart", action="store_true", help="start the tray app at login")
    group.add_argument("--uninstall-autostart", action="store_true", help="stop starting at login")
    args = parser.parse_args(argv)

    if args.install_autostart:
        try:
            print(f"Autostart enabled: {autostart.enable()}")
        except Exception as exc:
            print(f"Could not enable autostart: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.uninstall_autostart:
        try:
            removed = autostart.disable()
        except Exception as exc:
            print(f"Could not disable autostart: {exc}", file=sys.stderr)
            return 1
        print("Autostart disabled." if removed else "Autostart was not enabled.")
        return 0
    return run_tray()


if __name__ == "__main__":
    sys.exit(main())
