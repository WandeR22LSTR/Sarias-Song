import logging
from datetime import datetime, timedelta

import applog
import perfstats
import soakreport

START = datetime(2026, 10, 10, 0, 0, 0)


def stamped(when: datetime, message: str) -> str:
    """A line exactly as the saver's log writes it (same formatter as applog), at a chosen time."""
    record = logging.LogRecord("saver", logging.INFO, __file__, 0, message, None, None)
    record.created, record.msecs = when.timestamp(), 0
    return logging.Formatter(applog._FORMAT).format(record)


def perf_message(cpu: float, memory_mb: float, worst_ms: float) -> str:
    """The message the saver logs each minute, built with the real formatter so wording drift fails here."""
    sample = perfstats.Sample(60.0, cpu, cpu / 12, memory_mb)
    frames = perfstats.FrameStats()
    frames.add(worst_ms)
    return f"perf: {perfstats.format_sample(sample, 12)}; {frames.summary()}"


def a_run(start: datetime, minutes: int, memory, cpu: float = 18.0, worst: float = 14.0, exit_reason="mouse_move"):
    lines = [stamped(start, "saver running (30 fps cap, grace 2.0s)")]
    for minute in range(minutes):
        when = start + timedelta(minutes=minute, seconds=10)
        lines.append(stamped(when, perf_message(cpu, memory(minute), worst)))
    end = start + timedelta(minutes=minutes)
    if exit_reason:
        lines.append(stamped(end, f"exit on {exit_reason} at (10, 20)"))
        lines.append(stamped(end, f"perf over the whole run ({minutes * 60} s): cpu 18.0% of one core (1.5% of all 12 "
                                  "logical processors, as Task Manager shows), memory 118 MB"))
    return lines


def test_an_eight_hour_flat_run_reads_as_flat():
    runs = soakreport.parse_runs(a_run(START, 480, lambda minute: 120 + minute % 3))
    assert len(runs) == 1
    run = runs[0]
    assert len(run.memory) == 480 and run.exit_reason == "mouse_move" and run.seconds == 28800
    text = soakreport.describe(run, 1)
    assert "lasted 8 h 00 min, ended by mouse_move" in text
    assert "first 120, last 122, lowest 120, highest 122" in text
    assert "cpu % of one core: average 18.0, highest 18.0" in text
    assert "slowest single frame in any minute: 14 ms" in text
    assert text.count(",") >= 8 and "memory MB at about each hour: 120, 120" in text


def test_a_leak_shows_up_in_first_last_and_the_hourly_trend():
    text = soakreport.report(a_run(START, 240, lambda minute: 100 + minute))
    assert "first 100, last 339, lowest 100, highest 339" in text
    assert "memory MB at about each hour: 100, 160, 220, 280" in text


def test_a_run_with_no_exit_line_is_flagged_as_a_crash_or_still_running():
    text = soakreport.report(a_run(START, 30, lambda minute: 120, exit_reason=None))
    assert "NO exit line" in text
    assert "lasted 0 h 29 min" in text  # the span up to the last line seen, since no clean exit wrote a total


def test_every_run_in_the_log_gets_its_own_block_in_order():
    first = a_run(START, 5, lambda minute: 110)
    second = a_run(START + timedelta(hours=1), 90, lambda minute: 130, exit_reason="key")
    text = soakreport.report(first + second)
    assert text.index("Run 1") < text.index("Run 2")
    run_one, run_two = text.split("\n\n")
    assert "lasted 0 h 05 min, ended by mouse_move" in run_one and "first 110" in run_one
    assert "lasted 1 h 30 min, ended by key" in run_two and "first 130" in run_two


def test_a_run_shorter_than_ten_seconds_says_it_has_no_perf_lines():
    lines = [stamped(START, "saver running (30 fps cap, grace 2.0s)"), stamped(START + timedelta(seconds=3), "exit on key")]
    assert "no perf lines" in soakreport.report(lines)


def test_lines_without_a_timestamp_and_lines_before_any_run_are_ignored():
    lines = [
        stamped(START, "window 4480x1440 at (-1920,0); 2 monitor(s)"),
        "Traceback (most recent call last):",
        '  File "x.py", line 1, in <module>',
    ] + a_run(START + timedelta(minutes=1), 2, lambda minute: 120)
    runs = soakreport.parse_runs(lines)
    assert len(runs) == 1 and runs[0].memory == [120, 120]


def test_a_log_with_no_run_says_so():
    assert "No saver run found" in soakreport.report([stamped(START, "SDL allows the screensaver / display sleep: True")])


def test_main_reads_a_file_and_prints_the_report(tmp_path, capsys):
    path = tmp_path / "saver.log"
    path.write_text("\n".join(a_run(START, 3, lambda minute: 120)), encoding="utf-8")
    assert soakreport.main([str(path)]) == 0
    assert "Run 1" in capsys.readouterr().out


def test_main_reports_a_missing_file_instead_of_crashing(tmp_path, capsys):
    assert soakreport.main([str(tmp_path / "nope.log")]) == 1
    assert "Could not read" in capsys.readouterr().err
