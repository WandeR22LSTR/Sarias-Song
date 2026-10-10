"""Soak report: read logs\\saver.log and say how a long saver run went.

    python src/soakreport.py            # reads logs\\saver.log
    python src/soakreport.py some.log   # or any saver log

Read-only. The saver writes a `perf:` line a minute, so after an 8-hour run this turns about 480 lines
into a few: how long each run lasted, how it ended, and whether memory stayed flat. Every run found in
the log gets a block, oldest first (short blocks are earlier quick tests); the long one is the soak.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from applog import log_dir

_STAMP = "%Y-%m-%d %H:%M:%S,%f"
_STAMP_LENGTH = 23  # "2026-10-10 03:12:01,234"
_START = re.compile(r"saver running \(")
_PERF = re.compile(r"\bperf: cpu ([\d.]+)% of one core .*?memory (\d+) MB(?:; .*?worst (\d+) ms)?")
_EXIT = re.compile(r"\bexit on (\S+)")
_WHOLE_RUN = re.compile(r"perf over the whole run \((\d+) s\)")
SAMPLES_PER_HOUR = 60  # one perf line a minute


@dataclass
class Run:
    started: datetime
    last_seen: datetime
    cpu: list[float] = field(default_factory=list)
    memory: list[int] = field(default_factory=list)
    worst_ms: list[int] = field(default_factory=list)
    exit_reason: str | None = None  # None: no exit line, so a crash, a kill, or still running
    seconds: int | None = None  # from the whole-run line, which only a clean exit writes


def _stamp(line: str) -> datetime | None:
    try:
        return datetime.strptime(line[:_STAMP_LENGTH], _STAMP)
    except ValueError:
        return None  # a continuation line (for example a traceback) has no timestamp


def parse_runs(lines: list[str]) -> list[Run]:
    runs: list[Run] = []
    for line in lines:
        when = _stamp(line)
        if when is None:
            continue
        if _START.search(line):
            runs.append(Run(started=when, last_seen=when))
            continue
        if not runs:
            continue
        run = runs[-1]
        run.last_seen = when
        if (match := _PERF.search(line)) is not None:
            run.cpu.append(float(match[1]))
            run.memory.append(int(match[2]))
            if match[3] is not None:
                run.worst_ms.append(int(match[3]))
        elif (match := _EXIT.search(line)) is not None:
            run.exit_reason = match[1]
        elif (match := _WHOLE_RUN.search(line)) is not None:
            run.seconds = int(match[1])
    return runs


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"


def describe(run: Run, number: int) -> str:
    length = run.seconds if run.seconds is not None else (run.last_seen - run.started).total_seconds()
    ended = f"ended by {run.exit_reason}" if run.exit_reason else "NO exit line (crash, kill, or still running)"
    out = [f"Run {number}: started {run.started:%Y-%m-%d %H:%M:%S}, lasted {_duration(length)}, {ended}"]
    if not run.memory:
        out.append("  no perf lines (the run was shorter than 10 seconds)")
        return "\n".join(out)
    out.append(f"  {len(run.memory)} perf lines")
    out.append(
        f"  memory MB: first {run.memory[0]}, last {run.memory[-1]}, lowest {min(run.memory)}, highest {max(run.memory)}"
    )
    hourly = run.memory[::SAMPLES_PER_HOUR]
    out.append("  memory MB at about each hour: " + ", ".join(str(m) for m in hourly))
    out.append(f"  cpu % of one core: average {sum(run.cpu) / len(run.cpu):.1f}, highest {max(run.cpu):.1f}")
    if run.worst_ms:
        out.append(f"  slowest single frame in any minute: {max(run.worst_ms)} ms (a frame has 33 ms at 30 fps)")
    return "\n".join(out)


def report(lines: list[str]) -> str:
    runs = parse_runs(lines)
    if not runs:
        return "No saver run found in this log (looking for a 'saver running' line)."
    return "\n\n".join(describe(run, number) for number, run in enumerate(runs, start=1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarise the saver runs recorded in saver.log.")
    parser.add_argument("log", nargs="?", type=Path, default=log_dir() / "saver.log", help="log file (default logs\\saver.log)")
    args = parser.parse_args(argv)
    try:
        lines = args.log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        print(f"Could not read {args.log}: {error}", file=sys.stderr)
        return 1
    print(report(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
