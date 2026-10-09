import logging
import threading
import time
from unittest import mock

import perfstats
import winapi


class Clocks:
    """Fake wall and CPU clocks that the test advances by hand."""

    def __init__(self):
        self.wall = 100.0
        self.cpu = 5.0

    def advance(self, wall, cpu):
        self.wall += wall
        self.cpu += cpu


def sampler(clocks, cores=4, memory=lambda: 84.4):
    return perfstats.ProcessSampler(wall=lambda: clocks.wall, cpu=lambda: clocks.cpu, memory=memory, cores=cores)


def test_cpu_is_cpu_time_over_wall_time_per_core_and_per_machine():
    c = Clocks()
    s = sampler(c, cores=4)
    c.advance(wall=10.0, cpu=2.5)
    sample = s.sample()
    assert sample.seconds == 10.0
    assert sample.cpu_core_percent == 25.0  # a quarter of one core
    assert sample.cpu_machine_percent == 6.25  # what Task Manager would show with 4 logical processors
    assert sample.memory_mb == 84.4


def test_each_sample_covers_only_the_time_since_the_last_one():
    c = Clocks()
    s = sampler(c)
    c.advance(10, 5)
    assert s.sample().cpu_core_percent == 50.0
    c.advance(10, 1)
    assert s.sample().cpu_core_percent == 10.0  # not the 30% average of both


def test_total_averages_over_the_whole_run():
    c = Clocks()
    s = sampler(c)
    c.advance(10, 5)
    s.sample()
    c.advance(10, 1)
    s.sample()
    total = s.total()
    assert total.seconds == 20 and total.cpu_core_percent == 30.0


def test_no_elapsed_time_gives_no_sample_rather_than_a_division_by_zero():
    s = sampler(Clocks())
    assert s.sample() is None
    assert s.total() is None


def test_a_busy_multithreaded_process_can_exceed_one_core():
    c = Clocks()
    s = sampler(c, cores=8)
    c.advance(10, 25)
    sample = s.sample()
    assert sample.cpu_core_percent == 250.0 and sample.cpu_machine_percent == 31.25


def test_format_names_both_cpu_figures_and_memory():
    c = Clocks()
    s = sampler(c, cores=12)
    c.advance(60, 3.0)
    text = perfstats.format_sample(s.sample(), s.cores)
    assert "cpu 5.0% of one core" in text
    assert "0.42% of all 12 logical processors" in text
    assert "memory 84 MB" in text


def test_format_copes_with_unknown_memory_and_no_data():
    c = Clocks()
    s = sampler(c, memory=lambda: None)
    c.advance(1, 0.1)
    assert "memory n/a" in perfstats.format_sample(s.sample(), s.cores)
    assert perfstats.format_sample(None, 4) == "no data"


def test_frame_stats_summarise_then_reset():
    f = perfstats.FrameStats()
    assert f.summary() == "no frames"
    for ms in (2.0, 4.0, 30.0):
        f.add(ms)
    assert f.summary() == "3 frames, work avg 12.0 ms, worst 30 ms"
    assert f.summary() == "no frames"  # a new interval starts after each report


def test_reporter_logs_periodically_and_stops_when_told(caplog):
    log = logging.getLogger("perf-test")
    stop = threading.Event()
    with caplog.at_level(logging.INFO, logger="perf-test"):
        thread = perfstats.start_reporter(log, "tray", first_after=0.02, every=0.02, stop=stop)
        deadline = time.monotonic() + 3
        while len([r for r in caplog.records if "tray perf:" in r.getMessage()]) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        stop.set()
        thread.join(timeout=2)
    assert not thread.is_alive()
    lines = [r.getMessage() for r in caplog.records if "tray perf:" in r.getMessage()]
    assert len(lines) >= 2 and "of one core" in lines[0]
    count = len(lines)
    time.sleep(0.1)
    assert len([r for r in caplog.records if "tray perf:" in r.getMessage()]) == count  # silent after stop


def test_reporter_set_to_stop_immediately_never_logs(caplog):
    stop = threading.Event()
    stop.set()
    with caplog.at_level(logging.INFO, logger="perf-test2"):
        thread = perfstats.start_reporter(logging.getLogger("perf-test2"), "tray", 60, 300, stop)
        thread.join(timeout=2)
    assert not thread.is_alive() and not caplog.records


# --- memory ------------------------------------------------------------------


def test_memory_off_windows_reads_proc_and_is_plausible(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", False)
    mb = winapi.process_memory_mb()
    assert mb is None or 5 < mb < 100_000  # None only where /proc does not exist


def test_memory_on_windows_reads_the_working_set(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", True)

    def fake_get_process_memory_info(handle, pointer, size):
        pointer.contents.WorkingSetSize = 123 * 1024 * 1024
        return 1

    kernel32, psapi = mock.Mock(), mock.Mock()
    psapi.GetProcessMemoryInfo.side_effect = fake_get_process_memory_info
    windll = mock.Mock(kernel32=kernel32, psapi=psapi)
    with mock.patch.object(winapi.ctypes, "windll", windll, create=True):
        assert winapi.process_memory_mb() == 123.0
    # The process handle is 64-bit: the call must be told so it is not truncated to an int.
    assert kernel32.GetCurrentProcess.restype is winapi.ctypes.c_void_p


def test_memory_on_windows_is_none_when_the_call_fails(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", True)
    psapi = mock.Mock()
    psapi.GetProcessMemoryInfo.return_value = 0
    with mock.patch.object(winapi.ctypes, "windll", mock.Mock(kernel32=mock.Mock(), psapi=psapi), create=True):
        assert winapi.process_memory_mb() is None
