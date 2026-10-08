"""Small rotating file logger.

The tray and the saver are separate processes, so each writes its own file
(`logs/tray.log`, `logs/saver.log`); two processes sharing one rotating file
would corrupt it. When something goes wrong on Spirit Temple, the log is what
Luca sends back.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import app_dir

_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"


def log_dir() -> Path:
    return app_dir() / "logs"


def setup(name: str) -> logging.Logger:
    """Configure and return the process logger writing to logs/<name>.log."""
    logger = logging.getLogger(name)
    if logger.handlers:  # already configured (e.g. called twice)
        return logger
    logger.setLevel(logging.INFO)
    handler: logging.Handler
    try:
        directory = log_dir()
        directory.mkdir(exist_ok=True)
        handler = RotatingFileHandler(directory / f"{name}.log", maxBytes=256_000, backupCount=2, encoding="utf-8")
    except OSError:
        # Read-only install folder etc.: logging must never stop the app.
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)

    def _excepthook(exc_type, exc, tb):
        logger.critical("uncaught exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = _excepthook
    return logger
