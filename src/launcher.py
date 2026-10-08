"""Starts the screensaver as a separate process and opens the config file.

Kept free of any pystray import so it can be tested on any platform. The saver
runs as its own process on purpose: a crash in pygame or the render code can
never take the tray app down with it.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

import applog
import config
import winapi
from winapi import IS_WINDOWS

SRC_DIR = Path(__file__).resolve().parent


class SaverLauncher:
    def __init__(self, log: logging.Logger, popen: Callable[..., subprocess.Popen] = subprocess.Popen):
        self._log = log
        self._popen = popen
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @staticmethod
    def command() -> list[str]:
        """Command line that runs the saver in fullscreen mode (`/s`)."""
        if getattr(sys, "frozen", False):
            # The frozen build dispatches to the saver from the same exe; that
            # wiring is part of the packaging phase.
            raise NotImplementedError("launching the saver from a packaged exe is not implemented yet")
        return [sys.executable, "-m", "saver.main", "/s"]

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> bool:
        """Launch the saver. Returns False if one is already up or it failed to start."""
        with self._lock:
            if self.is_running():
                self._log.info("start ignored: saver already running (pid %s)", self._proc.pid)
                return False
            try:
                cmd = self.command()
                env = {**os.environ, "PYGAME_HIDE_SUPPORT_PROMPT": "1"}
                # Anything the saver prints before its own logging is set up
                # (import errors, missing DLLs) lands here instead of vanishing.
                logs = applog.log_dir()
                logs.mkdir(exist_ok=True)
                with open(logs / "saver-stderr.log", "ab") as stderr_file:
                    self._proc = self._popen(
                        cmd,
                        cwd=str(SRC_DIR),  # so `-m saver.main` can import config, saver, ...
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=stderr_file,
                        # No console window flashing up when run from a console python.exe.
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
            except Exception:
                self._log.exception("could not start the saver")
                self._proc = None
                return False
            try:
                winapi.allow_set_foreground(self._proc.pid)
            except Exception:
                self._log.exception("could not grant the saver foreground rights")
            self._log.info("saver started (pid %s)", self._proc.pid)
            threading.Thread(target=self._reap, args=(self._proc,), daemon=True).start()
            return True

    def _reap(self, proc: subprocess.Popen) -> None:
        """Wait for the saver so it never becomes a zombie, and log how it ended."""
        code = proc.wait()
        if code == 0:
            self._log.info("saver exited normally")
        else:
            self._log.error("saver exited with code %s (see logs/saver.log and logs/saver-stderr.log)", code)

    def stop(self) -> None:
        """Ask a running saver to end (used when the tray app exits)."""
        with self._lock:
            if self.is_running():
                self._log.info("terminating saver (pid %s)", self._proc.pid)
                self._proc.terminate()


def open_config_file(path: Path | None = None, popen: Callable[..., subprocess.Popen] = subprocess.Popen) -> Path:
    """Open config.json in the system editor, creating it from the defaults if missing."""
    path = path or config.config_path()
    if not path.exists():
        config.write_defaults(path)
    if IS_WINDOWS:
        # Notepad directly: os.startfile would show an "Open with" prompt when
        # .json has no association.
        popen(["notepad.exe", str(path)])
    elif sys.platform == "darwin":
        popen(["open", str(path)])
    else:
        popen(["xdg-open", str(path)])
    return path
