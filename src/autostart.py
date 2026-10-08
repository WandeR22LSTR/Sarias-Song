"""Start the tray app automatically at login.

Decision: a shortcut in the per-user Startup folder, not a Task Scheduler task.

* No admin rights. `schtasks /create /sc onlogon` is refused for standard users
  in many setups, and the Startup folder is writable by the user.
* Visible and controllable by the user: it shows up in Task Manager > Startup
  apps and Settings > Apps > Startup, and removal is deleting one file.
* No hidden defaults. Scheduled tasks created from the command line inherit
  "stop after 72 hours" and "only on AC power" conditions that would quietly
  kill a tray app. Task Scheduler's main extra (restart on crash) is not needed:
  the saver already runs in its own process and the tray is tiny.

The shortcut is created with PowerShell's WScript.Shell COM object, which avoids
a pywin32 dependency. Values are passed through environment variables, never
interpolated into the script, so paths containing quotes cannot break it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import config
from winapi import IS_WINDOWS

SHORTCUT_NAME = "Saria's Song.lnk"

_POWERSHELL_SCRIPT = (
    "$ws = New-Object -ComObject WScript.Shell; "
    "$s = $ws.CreateShortcut($env:SARIA_LNK); "
    "$s.TargetPath = $env:SARIA_TARGET; "
    "$s.Arguments = $env:SARIA_ARGS; "
    "$s.WorkingDirectory = $env:SARIA_CWD; "
    "$s.IconLocation = $env:SARIA_ICON; "
    "$s.Description = $env:SARIA_DESC; "
    "$s.WindowStyle = 7; "  # minimised, so no window flashes at login
    "$s.Save()"
)


@dataclass(frozen=True)
class ShortcutSpec:
    target: str
    arguments: str
    working_dir: str
    icon: str
    description: str = f"{config.APP_NAME} screensaver tray app"


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set; autostart is only supported on Windows")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return startup_dir() / SHORTCUT_NAME


def build_spec() -> ShortcutSpec:
    """What the Startup shortcut should launch."""
    app = config.app_dir()
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        return ShortcutSpec(target=str(exe), arguments="", working_dir=str(exe.parent), icon=str(exe))
    # From source: run tray.py with pythonw.exe (the windowless interpreter next
    # to python.exe) so no console window sits open for the whole session.
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    target = pythonw if pythonw.exists() else python
    icon = app / "assets" / "saria-song.ico"
    return ShortcutSpec(
        target=str(target),
        arguments=f'"{app / "src" / "tray.py"}"',
        working_dir=str(app),
        icon=str(icon) if icon.exists() else str(target),
    )


def is_enabled() -> bool:
    try:
        return shortcut_path().exists()
    except RuntimeError:
        return False


def enable(run=subprocess.run) -> Path:
    """Create (or refresh) the Startup shortcut and return its path."""
    if not IS_WINDOWS:
        raise RuntimeError("autostart is only supported on Windows")
    spec = build_spec()
    link = shortcut_path()
    link.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "SARIA_LNK": str(link),
        "SARIA_TARGET": spec.target,
        "SARIA_ARGS": spec.arguments,
        "SARIA_CWD": spec.working_dir,
        "SARIA_ICON": spec.icon,
        "SARIA_DESC": spec.description,
    }
    run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _POWERSHELL_SCRIPT],
        env=env,
        check=True,
        capture_output=True,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return link


def disable() -> bool:
    """Remove the Startup shortcut. Returns True if there was one to remove."""
    link = shortcut_path()
    try:
        link.unlink()
    except FileNotFoundError:
        return False
    return True
