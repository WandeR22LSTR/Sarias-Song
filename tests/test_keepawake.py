import logging
from unittest import mock

import pytest

import winapi
from saver.keepawake import KeepAwake

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


class Recorder:
    def __init__(self, returns=ES_CONTINUOUS):
        self.calls = []
        self.returns = returns

    def __call__(self, flags):
        self.calls.append(flags)
        return self.returns


@pytest.fixture
def log():
    return logging.getLogger("keepawake-test")


def test_constants_are_the_documented_windows_values():
    assert winapi.ES_CONTINUOUS == ES_CONTINUOUS
    assert winapi.ES_SYSTEM_REQUIRED == ES_SYSTEM_REQUIRED


def test_start_requests_a_continuous_system_required_state(log):
    rec = Recorder()
    KeepAwake(log, rec).start()
    assert rec.calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED]


def test_it_never_forces_the_display_on(log):
    # Blocking idle sleep must not hold the monitors on as well.
    rec = Recorder()
    k = KeepAwake(log, rec)
    k.start()
    k.stop()
    assert all(call & ES_DISPLAY_REQUIRED == 0 for call in rec.calls)


def test_stop_clears_with_continuous_alone(log):
    rec = Recorder()
    k = KeepAwake(log, rec)
    k.start()
    k.stop()
    assert rec.calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED, ES_CONTINUOUS]
    assert not k.active


def test_start_and_stop_are_idempotent(log):
    rec = Recorder()
    k = KeepAwake(log, rec)
    k.start()
    k.start()
    k.stop()
    k.stop()
    assert len(rec.calls) == 2


def test_refresh_reasserts_the_same_request_only_while_active(log):
    rec = Recorder()
    k = KeepAwake(log, rec)
    k.refresh()
    assert rec.calls == []  # nothing to refresh before start
    k.start()
    k.refresh()
    assert rec.calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED] * 2
    k.stop()
    k.refresh()
    assert rec.calls[-1] == ES_CONTINUOUS  # still just the clear: refresh after stop does nothing


def test_refresh_is_silent(log, caplog):
    k = KeepAwake(log, Recorder())
    k.start()
    with caplog.at_level(logging.INFO, logger="keepawake-test"):
        caplog.clear()
        k.refresh()
    assert not caplog.records  # once a minute for hours must not fill the log


def test_stop_without_start_does_nothing(log):
    rec = Recorder()
    KeepAwake(log, rec).stop()
    assert rec.calls == []


def test_start_and_stop_run_on_the_same_thread(log):
    # The request belongs to the calling thread; a clear from another thread would not clear it.
    import threading

    threads = []

    def recording(flags):
        threads.append(threading.get_ident())
        return ES_CONTINUOUS

    k = KeepAwake(log, recording)
    k.start()
    k.stop()
    assert len(set(threads)) == 1


def test_a_zero_return_on_windows_is_reported_but_not_fatal(log, monkeypatch, caplog):
    monkeypatch.setattr(winapi, "IS_WINDOWS", True)
    with caplog.at_level(logging.INFO, logger="keepawake-test"):
        k = KeepAwake(log, Recorder(returns=0))
        k.start()
    assert k.active
    assert any("returned 0" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)


def test_a_normal_start_and_stop_are_logged(log, caplog):
    with caplog.at_level(logging.INFO, logger="keepawake-test"):
        k = KeepAwake(log, Recorder())
        k.start()
        k.stop()
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("keep-awake on") for m in messages)
    assert "keep-awake off" in messages


# --- the Windows call itself, mocked ------------------------------------------


def test_the_api_call_uses_unsigned_arguments_and_passes_the_flags_through(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", True)
    kernel32 = mock.Mock()
    kernel32.SetThreadExecutionState.return_value = ES_CONTINUOUS
    with mock.patch.object(winapi.ctypes, "windll", mock.Mock(kernel32=kernel32), create=True):
        result = winapi.set_thread_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    assert result == ES_CONTINUOUS
    kernel32.SetThreadExecutionState.assert_called_once_with(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    # ES_CONTINUOUS has the top bit set, so a signed int argument type would overflow.
    assert kernel32.SetThreadExecutionState.argtypes == [winapi.ctypes.c_uint]
    assert kernel32.SetThreadExecutionState.restype is winapi.ctypes.c_uint


def test_the_api_call_is_a_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", False)
    assert winapi.set_thread_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) == 0
