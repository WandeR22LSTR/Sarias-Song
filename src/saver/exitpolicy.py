"""When should the screensaver exit? Pure logic, no pygame, fully unit-tested.

Two jobs:

* Grace period. Right after launch the mouse is still settling (the click that
  started the saver, a twitch of the hand), so all input is ignored for
  `grace_seconds`.
* Jitter tolerance. Mouse movement only counts once the pointer is at least
  `move_threshold_px` away from where it came to rest. Streaming clients and
  some mice emit tiny motion events on their own; without a threshold those
  would end the saver instantly.
"""

from __future__ import annotations

import math

KEY = "key"
MOUSE_MOVE = "mouse_move"
MOUSE_CLICK = "mouse_click"


class ExitPolicy:
    def __init__(
        self,
        start: float,
        grace_seconds: float,
        exit_on: tuple[str, ...],
        move_threshold_px: float,
        mouse_origin: tuple[int, int] | None = None,
    ):
        self._start = start
        self._grace = grace_seconds
        self._exit_on = frozenset(exit_on)
        self._threshold = move_threshold_px
        self._origin = mouse_origin

    def in_grace(self, now: float) -> bool:
        return now - self._start < self._grace

    def should_exit(self, kind: str, now: float, pos: tuple[int, int] | None = None) -> bool:
        """Feed one input event; True means the saver should close.

        `kind` is "key", "mouse_move" or "mouse_click"; `pos` is the pointer
        position for mouse events. `now` is a monotonic timestamp in seconds.
        """
        if kind == MOUSE_MOVE and pos is not None:
            if self.in_grace(now) or self._origin is None:
                # Re-baseline while the pointer settles. The very first sample
                # when we have no reference is a reference, not a movement.
                self._origin = pos
                return False
        if self.in_grace(now) or kind not in self._exit_on:
            return False
        if kind == MOUSE_MOVE:
            if pos is None:
                return False
            return math.hypot(pos[0] - self._origin[0], pos[1] - self._origin[1]) >= self._threshold
        return True
