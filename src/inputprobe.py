"""Input probe: does Windows mark Apollo's client input as "injected"? (phase 4, experiment E2)

    python src/inputprobe.py --seconds 90

Read-only. For a set time it listens to keyboard and mouse input system-wide with low-level
hooks and records, for every event, whether Windows flagged it as INJECTED (made by software
through SendInput, which is how a streaming host feeds in a client's input) or physical
(real hardware). It changes nothing and blocks nothing: every event is passed straight on.

If the client's input is flagged and the hardware's is not, the saver can ignore the client
and still react to a real hand on the mouse, which is what phase 4 needs.

Privacy: modifier keys (Shift, Ctrl, Alt, Win) are recorded by name, because the client's quit
chord is made of them. Every other key is only counted, never named, so what you type is not
captured. The result is printed and saved to logs\\input-probe.txt.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import winapi

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0
PM_REMOVE = 0x0001

WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_MOUSEWHEEL = 0x020A

LLKHF_INJECTED = 0x10  # KBDLLHOOKSTRUCT.flags
LLKHF_LOWER_IL_INJECTED = 0x02
LLMHF_INJECTED = 0x01  # MSLLHOOKSTRUCT.flags (a different bit from the keyboard's)
LLMHF_LOWER_IL_INJECTED = 0x02

PHYSICAL = "physical"
INJECTED = "injected"
INJECTED_LOW = "injected (lower integrity)"

_KEY_ACTIONS = {WM_KEYDOWN: "down", WM_SYSKEYDOWN: "down", WM_KEYUP: "up", WM_SYSKEYUP: "up"}
_MOUSE_ACTIONS = {
    WM_MOUSEMOVE: "move",
    WM_LBUTTONDOWN: "left down", WM_LBUTTONUP: "left up",
    WM_RBUTTONDOWN: "right down", WM_RBUTTONUP: "right up",
    WM_MBUTTONDOWN: "middle down", WM_MBUTTONUP: "middle up",
    WM_MOUSEWHEEL: "wheel",
}  # fmt: skip
# Named on purpose: the client's quit chord is made of these. No other key is ever named.
_MODIFIERS = {
    0x10: "Shift", 0x11: "Ctrl", 0x12: "Alt",
    0xA0: "LShift", 0xA1: "RShift", 0xA2: "LCtrl", 0xA3: "RCtrl", 0xA4: "LAlt", 0xA5: "RAlt",
    0x5B: "LWin", 0x5C: "RWin",
}  # fmt: skip


# Fixed-width fields (a DWORD is 32 bits, a ULONG_PTR pointer-sized) so the layouts are right on any platform.
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.c_uint32),
        ("scanCode", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint32),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint32),
        ("pt", POINT),
    ]


@dataclass(frozen=True)
class Event:
    t: float  # seconds since the probe started
    device: str  # "keyboard" or "mouse"
    action: str  # "down", "up", "move", "left down", ...
    name: str  # a modifier's name, "other key", or "" for the mouse
    source: str  # PHYSICAL, INJECTED or INJECTED_LOW


def source_of(flags: int, injected_bit: int, lower_il_bit: int) -> str:
    """Windows' own verdict. The lower-integrity bit only ever accompanies the injected bit."""
    if flags & injected_bit:
        return INJECTED_LOW if flags & lower_il_bit else INJECTED
    return PHYSICAL


def key_event(t: float, message: int, vk_code: int, flags: int) -> Event | None:
    action = _KEY_ACTIONS.get(message)
    if action is None:
        return None
    name = _MODIFIERS.get(vk_code, "other key")
    return Event(t, "keyboard", action, name, source_of(flags, LLKHF_INJECTED, LLKHF_LOWER_IL_INJECTED))


def mouse_event(t: float, message: int, flags: int) -> Event | None:
    action = _MOUSE_ACTIONS.get(message)
    if action is None:
        return None
    return Event(t, "mouse", action, "", source_of(flags, LLMHF_INJECTED, LLMHF_LOWER_IL_INJECTED))


def summarize(events: list[Event], seconds: float, started: str, max_lines: int = 80) -> str:
    """The report: counts per device, a verdict, and the events in order with repeats folded."""
    lines = [f"Input probe, {seconds:.0f} s, started {started}", ""]
    for device in ("keyboard", "mouse"):
        subset = [e for e in events if e.device == device]
        counts = Counter(e.source for e in subset)
        detail = ", ".join(f"{n} {source}" for source, n in counts.most_common()) or "none"
        lines.append(f"{device.capitalize():9}{len(subset):5} events  ({detail})")
    lines.append("")

    injected = any(e.source != PHYSICAL for e in events)
    physical = any(e.source == PHYSICAL for e in events)
    if injected and physical:
        lines.append("RESULT: both kinds were seen, so Windows separates software-made input from real hardware input here.")
    elif injected:
        lines.append("RESULT: only injected input was seen. Did you also use the PC's own keyboard and mouse? Without that "
                     "the two cannot be compared.")
    elif physical:
        lines.append("RESULT: only physical input was seen. Either nothing was sent from the client, or the client's input is "
                     "NOT marked as injected and looks like hardware. Tell me which; the second is the bad case.")
    else:
        lines.append("RESULT: no input was seen at all.")
    lines.append("")

    # Fold runs of identical events, so a burst of mouse moves is one line.
    folded: list[tuple[Event, int]] = []
    for e in events:
        if folded and (folded[-1][0].device, folded[-1][0].action, folded[-1][0].name, folded[-1][0].source) == (
            e.device, e.action, e.name, e.source,
        ):  # fmt: skip
            folded[-1] = (folded[-1][0], folded[-1][1] + 1)
        else:
            folded.append((e, 1))
    lines.append("In order (a repeated event is folded into one line with a count):")
    for e, n in folded[:max_lines]:
        what = f"{e.action} {e.name}".strip()
        lines.append(f"  +{e.t:7.3f}s  {e.device:8} {what:24} {e.source}" + (f"  x{n}" if n > 1 else ""))
    if len(folded) > max_lines:
        lines.append(f"  ... and {len(folded) - max_lines} more lines")
    return "\n".join(lines) + "\n"


class Probe:
    """Collects events. The hook callbacks do as little as possible: Windows drops a hook that is slow."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._start = clock()
        self.events: list[Event] = []
        self.errors = 0

    def key(self, message: int, vk_code: int, flags: int) -> None:
        e = key_event(self._clock() - self._start, message, vk_code, flags)
        if e:
            self.events.append(e)

    def mouse(self, message: int, flags: int) -> None:
        e = mouse_event(self._clock() - self._start, message, flags)
        if e:
            self.events.append(e)


def listen(probe: Probe, seconds: float, clock=time.monotonic, sleep=time.sleep) -> None:
    """Install both hooks, pump messages for `seconds`, then always remove the hooks."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hook_proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)

    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, hook_proc, ctypes.c_void_p, ctypes.c_uint32]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]

    def keyboard_proc(n_code, w_param, l_param):
        try:
            if n_code == HC_ACTION:
                data = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                probe.key(w_param, data.vkCode, data.flags)
        except Exception:  # a hook must never raise into Windows
            probe.errors += 1
        return user32.CallNextHookEx(None, n_code, w_param, l_param)  # pass everything on, untouched

    def mouse_proc(n_code, w_param, l_param):
        try:
            if n_code == HC_ACTION:
                data = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                probe.mouse(w_param, data.flags)
        except Exception:
            probe.errors += 1
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    # Keep references to the callback objects for as long as the hooks exist, or they are garbage collected.
    keyboard_cb, mouse_cb = hook_proc(keyboard_proc), hook_proc(mouse_proc)
    module = kernel32.GetModuleHandleW(None)
    handles = []
    try:
        for hook_id, callback in ((WH_KEYBOARD_LL, keyboard_cb), (WH_MOUSE_LL, mouse_cb)):
            handle = user32.SetWindowsHookExW(hook_id, callback, module, 0)
            if not handle:
                raise ctypes.WinError()
            handles.append(handle)
        message = MSG()
        end = clock() + seconds
        while clock() < end:
            # Hook callbacks run while this thread is retrieving messages, so keep doing it.
            while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
            sleep(0.005)
    finally:
        for handle in handles:
            user32.UnhookWindowsHookEx(handle)


def run(seconds: float, out_path: Path | None) -> int:
    if not winapi.IS_WINDOWS:
        print("The input probe uses Windows hooks and only runs on Windows.", file=sys.stderr)
        return 1
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Listening for {seconds:.0f} seconds. Do your test now: type Shift, move and click the mouse, "
          f"on the client and then on this PC's own keyboard and mouse.")
    probe = Probe()
    try:
        listen(probe, seconds)
    except OSError as exc:
        print(f"Could not install the input hooks: {exc}", file=sys.stderr)
        return 1
    text = summarize(probe.events, seconds, started)
    if probe.errors:
        text += f"\n({probe.errors} events could not be read.)\n"
    print(text)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"Saved to {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record whether keyboard and mouse input is marked as injected.")
    parser.add_argument("--seconds", type=float, default=60.0, help="how long to listen (default 60)")
    args = parser.parse_args(argv)
    import applog

    return run(max(1.0, args.seconds), applog.log_dir() / "input-probe.txt")


if __name__ == "__main__":
    sys.exit(main())
