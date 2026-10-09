"""The app reporting on its own CPU and memory use.

The saver covers the whole screen, so you cannot watch it in Task Manager; and for the
8-hour soak test a log of memory over time shows a leak better than any glance would.
Reports go to the process's own log (`logs/saver.log`, `logs/tray.log`).

CPU is measured the way Task Manager does, from the process's CPU time over wall time,
and given two ways: as a share of ONE core (100 = a core fully busy) and as a share of
the whole machine (what Task Manager's CPU column shows).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

import winapi


@dataclass(frozen=True)
class Sample:
    seconds: float  # wall-clock time this sample covers
    cpu_core_percent: float  # 100 = one core fully busy
    cpu_machine_percent: float  # the same, as a share of all logical processors
    memory_mb: float | None


class ProcessSampler:
    """CPU and memory of this process, per interval and in total."""

    def __init__(
        self,
        wall: Callable[[], float] = time.monotonic,
        cpu: Callable[[], float] = time.process_time,  # user + system CPU time of this process
        memory: Callable[[], float | None] = winapi.process_memory_mb,
        cores: int | None = None,
    ):
        self._wall, self._cpu, self._memory = wall, cpu, memory
        self._cores = max(1, cores or os.cpu_count() or 1)
        self._start_wall = self._last_wall = wall()
        self._start_cpu = self._last_cpu = cpu()

    def _sample(self, since_wall: float, since_cpu: float, now_wall: float, now_cpu: float) -> Sample | None:
        seconds = now_wall - since_wall
        if seconds <= 0:
            return None
        core = 100.0 * (now_cpu - since_cpu) / seconds
        return Sample(seconds, core, core / self._cores, self._memory())

    def sample(self) -> Sample | None:
        """Use since the previous call (or since creation); None if no time has passed."""
        now_wall, now_cpu = self._wall(), self._cpu()
        result = self._sample(self._last_wall, self._last_cpu, now_wall, now_cpu)
        self._last_wall, self._last_cpu = now_wall, now_cpu
        return result

    def total(self) -> Sample | None:
        """Average use since creation."""
        return self._sample(self._start_wall, self._start_cpu, self._wall(), self._cpu())

    @property
    def cores(self) -> int:
        return self._cores


def format_sample(sample: Sample | None, cores: int) -> str:
    if sample is None:
        return "no data"
    memory = "memory n/a" if sample.memory_mb is None else f"memory {sample.memory_mb:.0f} MB"
    return (
        f"cpu {sample.cpu_core_percent:.1f}% of one core "
        f"({sample.cpu_machine_percent:.2f}% of all {cores} logical processors, as Task Manager shows), {memory}"
    )


class FrameStats:
    """How long each frame's work took (not counting the wait that holds 30 fps)."""

    def __init__(self) -> None:
        self._count = 0
        self._total_ms = 0.0
        self._worst_ms = 0.0

    def add(self, milliseconds: float) -> None:
        self._count += 1
        self._total_ms += milliseconds
        self._worst_ms = max(self._worst_ms, milliseconds)

    def summary(self) -> str:
        """Text for the frames since the last call; starts a fresh interval."""
        if not self._count:
            return "no frames"
        text = f"{self._count} frames, work avg {self._total_ms / self._count:.1f} ms, worst {self._worst_ms:.0f} ms"
        self._count, self._total_ms, self._worst_ms = 0, 0.0, 0.0
        return text


def start_reporter(
    log: logging.Logger,
    label: str,
    first_after: float,
    every: float,
    stop: threading.Event,
    sampler: ProcessSampler | None = None,
) -> threading.Thread:
    """Log CPU and memory from a background thread until `stop` is set (used by the tray)."""
    sampler = sampler or ProcessSampler()

    def run() -> None:
        wait = first_after
        while not stop.wait(wait):
            log.info("%s perf: %s", label, format_sample(sampler.sample(), sampler.cores))
            wait = every

    thread = threading.Thread(target=run, name=f"{label}-perf", daemon=True)
    thread.start()
    return thread
