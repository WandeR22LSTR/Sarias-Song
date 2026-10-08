"""Configuration for Saria's Song.

`config.json` lives next to the executable (or in the repo root when running
from source) so the whole folder can be moved. Loading never raises: bad or
missing values fall back to defaults and are reported through
`Config.warnings`, because a typo in the config must not stop the saver.
"""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

APP_NAME = "Saria's Song"

# Modes the saver can render. Phase 4 adds "text", "slideshow" and "mixed".
VALID_MODES = ("clock",)
VALID_MONITORS = ("all", "primary")
VALID_EXIT_EVENTS = ("key", "mouse_move", "mouse_click")

DEFAULTS: dict[str, Any] = {
    "mode": "clock",
    # Deep green-black rather than pure black, soft green accents.
    "colors": {
        "background": "#0b1410",
        "background_edge": "#040806",
        "accent": "#7fd48a",
        "text": "#cfe8d4",
        "dim": "#5f8a68",
    },
    # Comma-separated, tried in order. Falls back to pygame's built-in font.
    "font": "Segoe UI Light, Segoe UI, Calibri",
    "clock": {
        "format_24h": True,
        "show_seconds": False,
        "show_date": True,
    },
    "animation_speed": 1.0,  # 1.0 = calm; 0 freezes the ambient animation
    "monitors": "all",  # "all" or "primary"
    "grace_seconds": 2.0,  # input is ignored this long after launch
    "exit_on": list(VALID_EXIT_EVENTS),
    "mouse_move_threshold_px": 12,  # ignore tiny jitter (e.g. streaming clients)
}


@dataclass(frozen=True)
class Colors:
    background: tuple[int, int, int]
    background_edge: tuple[int, int, int]
    accent: tuple[int, int, int]
    text: tuple[int, int, int]
    dim: tuple[int, int, int]


@dataclass(frozen=True)
class ClockConfig:
    format_24h: bool
    show_seconds: bool
    show_date: bool


@dataclass(frozen=True)
class Config:
    mode: str
    colors: Colors
    font: str
    clock: ClockConfig
    animation_speed: float
    monitors: str
    grace_seconds: float
    exit_on: tuple[str, ...]
    mouse_move_threshold_px: int
    warnings: tuple[str, ...] = field(default=(), compare=False)


def app_dir() -> Path:
    """Folder that holds config.json, logs/ and assets/.

    Frozen (PyInstaller): the folder containing the exe. From source: the repo
    root, one level above src/.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return app_dir() / "config.json"


def parse_color(value: Any) -> tuple[int, int, int]:
    """Parse '#rrggbb' or '#rgb'. Raises ValueError on anything else."""
    if not isinstance(value, str):
        raise ValueError(f"expected a '#rrggbb' string, got {value!r}")
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"expected '#rrggbb', got {value!r}")
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        raise ValueError(f"expected '#rrggbb', got {value!r}") from None


def _number(value: Any, default: float, lo: float, hi: float, name: str, warnings: list[str]) -> float:
    # bool is an int subclass; "true" is never a sensible number here.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        warnings.append(f"{name}: expected a number, using {default}")
        return default
    if not lo <= value <= hi:
        clamped = min(max(value, lo), hi)
        warnings.append(f"{name}: {value} is outside {lo}..{hi}, using {clamped}")
        return clamped
    return value


def _boolean(value: Any, default: bool, name: str, warnings: list[str]) -> bool:
    if isinstance(value, bool):
        return value
    warnings.append(f"{name}: expected true or false, using {str(default).lower()}")
    return default


def _choice(value: Any, choices: tuple[str, ...], default: str, name: str, warnings: list[str]) -> str:
    if isinstance(value, str) and value.lower() in choices:
        return value.lower()
    warnings.append(f"{name}: {value!r} is not one of {', '.join(choices)}, using {default!r}")
    return default


def _merge(defaults: dict[str, Any], user: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """Overlay user values on the defaults. Unknown top-level keys are dropped.

    Object-valued sections ("colors", "clock") merge key by key so a partial
    section keeps the remaining defaults; a non-object there is rejected.
    """
    merged = copy.deepcopy(defaults)
    for key, default_value in defaults.items():
        if key not in user:
            continue
        if isinstance(default_value, dict):
            if isinstance(user[key], dict):
                merged[key] = {**default_value, **user[key]}
            else:
                warnings.append(f"{key}: expected an object, using the defaults")
        else:
            merged[key] = user[key]
    return merged


def from_dict(raw: dict[str, Any] | None) -> Config:
    """Build a validated Config from a (possibly partial or invalid) dict."""
    warnings: list[str] = []
    raw = raw if isinstance(raw, dict) else {}
    data = _merge(DEFAULTS, raw, warnings)

    unknown = sorted(set(raw) - set(DEFAULTS))
    if unknown:
        warnings.append(f"ignoring unknown setting(s): {', '.join(unknown)}")

    colors_in = data["colors"]
    color_values: dict[str, tuple[int, int, int]] = {}
    for name, default_hex in DEFAULTS["colors"].items():
        try:
            color_values[name] = parse_color(colors_in.get(name, default_hex))
        except ValueError as exc:
            warnings.append(f"colors.{name}: {exc}; using {default_hex}")
            color_values[name] = parse_color(default_hex)

    clock_in = data["clock"]
    clock = ClockConfig(
        format_24h=_boolean(clock_in.get("format_24h"), DEFAULTS["clock"]["format_24h"], "clock.format_24h", warnings),
        show_seconds=_boolean(clock_in.get("show_seconds"), DEFAULTS["clock"]["show_seconds"], "clock.show_seconds", warnings),
        show_date=_boolean(clock_in.get("show_date"), DEFAULTS["clock"]["show_date"], "clock.show_date", warnings),
    )

    font = data["font"]
    if not isinstance(font, str) or not font.strip():
        warnings.append(f"font: expected a font name, using {DEFAULTS['font']!r}")
        font = DEFAULTS["font"]

    exit_in = data["exit_on"]
    if isinstance(exit_in, list) and all(isinstance(e, str) for e in exit_in):
        bad = [e for e in exit_in if e not in VALID_EXIT_EVENTS]
        if bad:
            warnings.append(f"exit_on: ignoring unknown event(s): {', '.join(bad)}")
        exit_on = tuple(e for e in exit_in if e in VALID_EXIT_EVENTS)
    else:
        warnings.append(f"exit_on: expected a list of {', '.join(VALID_EXIT_EVENTS)}, using the default")
        exit_on = tuple(DEFAULTS["exit_on"])
    if not exit_on:
        # An empty list would make the saver impossible to leave.
        warnings.append("exit_on is empty, which would trap you in the saver; using the default")
        exit_on = tuple(DEFAULTS["exit_on"])

    return Config(
        mode=_choice(data["mode"], VALID_MODES, DEFAULTS["mode"], "mode", warnings),
        colors=Colors(**color_values),
        font=font,
        clock=clock,
        animation_speed=_number(data["animation_speed"], DEFAULTS["animation_speed"], 0.0, 5.0, "animation_speed", warnings),
        monitors=_choice(data["monitors"], VALID_MONITORS, DEFAULTS["monitors"], "monitors", warnings),
        grace_seconds=_number(data["grace_seconds"], DEFAULTS["grace_seconds"], 0.0, 30.0, "grace_seconds", warnings),
        exit_on=exit_on,
        mouse_move_threshold_px=int(
            _number(data["mouse_move_threshold_px"], DEFAULTS["mouse_move_threshold_px"], 0, 500, "mouse_move_threshold_px", warnings)
        ),
        warnings=tuple(warnings),
    )


def load(path: Path | None = None) -> Config:
    """Load config.json. Missing or unreadable files give the defaults plus a warning."""
    path = path or config_path()
    try:
        text = path.read_text(encoding="utf-8-sig")  # tolerate a Notepad BOM
    except FileNotFoundError:
        cfg = from_dict(None)
        return _with_warning(cfg, f"{path.name} not found, using defaults")
    except OSError as exc:
        return _with_warning(from_dict(None), f"could not read {path.name} ({exc}), using defaults")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        return _with_warning(from_dict(None), f"{path.name} is not valid JSON ({exc}), using defaults")
    if not isinstance(raw, dict):
        return _with_warning(from_dict(None), f"{path.name} must contain a JSON object, using defaults")
    return from_dict(raw)


def _with_warning(cfg: Config, message: str) -> Config:
    return replace(cfg, warnings=(message, *cfg.warnings))


def write_defaults(path: Path | None = None) -> Path:
    """Write a fresh config.json with the default values (used if it is missing)."""
    path = path or config_path()
    path.write_text(json.dumps(DEFAULTS, indent=2) + "\n", encoding="utf-8")
    return path
