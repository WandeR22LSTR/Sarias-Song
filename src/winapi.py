"""Windows-only helpers, all behind `IS_WINDOWS` so the rest runs anywhere.

Everything here goes through `ctypes` and cannot be exercised in the cloud
session; the tests mock `ctypes.windll`. Luca's manual test checklist in the
README covers the real behavior.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"

ERROR_ALREADY_EXISTS = 183


@dataclass(frozen=True)
class MonitorRect:
    x: int
    y: int
    width: int
    height: int
    primary: bool = False


def acquire_single_instance(name: str):
    """Take a named mutex so only one tray app runs per login session.

    Returns a handle that must be kept alive for the life of the process, or
    None if another instance already holds the mutex. On non-Windows it always
    succeeds (returns a truthy placeholder) so development on Linux/macOS works.
    """
    if not IS_WINDOWS:
        return object()
    kernel32 = ctypes.windll.kernel32
    # "Local\" scopes the mutex to this login session, so two users on the same
    # PC (fast user switching) do not block each other.
    handle = kernel32.CreateMutexW(None, False, f"Local\\{name}")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return handle


def set_dpi_aware() -> None:
    """Make window and monitor coordinates physical pixels.

    Must run before pygame creates its window. Without it Windows bitmap-scales
    the saver on high-DPI displays (blurry text) and reports virtualised
    monitor sizes. Per-monitor v2 is preferred; older calls are fallbacks.
    """
    if not IS_WINDOWS:
        return
    user32 = ctypes.windll.user32
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 is the pseudo-handle -4.
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass  # Windows older than 10 1703
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return
    except (AttributeError, OSError):
        pass
    try:
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


MONITORINFOF_PRIMARY = 1


def monitor_rects() -> list[MonitorRect]:
    """Return every attached monitor's rectangle in virtual-desktop pixels.

    The virtual desktop can have negative coordinates (a monitor left of or
    above the primary). Returns [] on non-Windows or if enumeration fails;
    callers fall back to pygame's desktop sizes.
    """
    if not IS_WINDOWS:
        return []
    user32 = ctypes.windll.user32
    found: list[MonitorRect] = []

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_RECT), ctypes.c_void_p
    )

    def _callback(hmonitor, _hdc, _rect, _data):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(ctypes.c_void_p(hmonitor), ctypes.byref(info)):
            r = info.rcMonitor
            found.append(
                MonitorRect(r.left, r.top, r.right - r.left, r.bottom - r.top, bool(info.dwFlags & MONITORINFOF_PRIMARY))
            )
        return 1  # keep enumerating

    # Keep a reference to the callback object for the duration of the call.
    proc = MONITORENUMPROC(_callback)
    if not user32.EnumDisplayMonitors(None, None, proc, 0):
        return []
    return found


def make_topmost(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    """Pin a window above the taskbar at an exact rectangle.

    A borderless window that spans several monitors is not recognised by the
    shell as "fullscreen", so the taskbar would otherwise stay on top of it.
    """
    if not IS_WINDOWS:
        return
    HWND_TOPMOST = ctypes.c_void_p(-1)
    SWP_SHOWWINDOW = 0x0040
    ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(hwnd), HWND_TOPMOST, x, y, width, height, SWP_SHOWWINDOW)
