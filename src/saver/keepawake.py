"""Keep the PC awake while the saver is on screen.

Uses SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) and clears it on exit.
That blocks IDLE sleep only. It does not change power plans or the registry, and it does
not stop a deliberate sleep command: Luca puts this PC to sleep on purpose from the
Raspberry Pi (Sleep-on-LAN), and that must keep working while the saver is up. The
README's manual test checklist has the remote-sleep test that proves it on Spirit Temple.

The request belongs to the thread that made it, so `start` and `stop` must run on the same
thread (the saver's main thread). If the saver crashes, Windows drops the request when the
thread dies, so a crash cannot leave the PC unable to sleep.
"""

from __future__ import annotations

import logging
from typing import Callable

import winapi


class KeepAwake:
    def __init__(self, log: logging.Logger, set_state: Callable[[int], int] = winapi.set_thread_execution_state):
        self._log = log
        self._set_state = set_state
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> None:
        if self._active:
            return
        previous = self._set_state(winapi.ES_CONTINUOUS | winapi.ES_SYSTEM_REQUIRED)
        self._active = True
        if previous == 0 and winapi.IS_WINDOWS:
            # 0 is how the API reports failure. Say so, but carry on: the saver still works.
            self._log.warning("keep-awake: SetThreadExecutionState returned 0 (it may have failed); "
                              "check with `powercfg /requests` in an administrator PowerShell")
        else:
            self._log.info("keep-awake on (previous state 0x%08X)", previous)

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        self._set_state(winapi.ES_CONTINUOUS)  # ES_CONTINUOUS alone clears the request
        self._log.info("keep-awake off")
