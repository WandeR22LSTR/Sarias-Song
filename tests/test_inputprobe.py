import ctypes
from unittest import mock

import pytest

import inputprobe
from inputprobe import (
    INJECTED,
    INJECTED_LOW,
    PHYSICAL,
    Event,
    KBDLLHOOKSTRUCT,
    MSLLHOOKSTRUCT,
    POINT,
    Probe,
    key_event,
    mouse_event,
    source_of,
    summarize,
)

VK_LSHIFT, VK_LCTRL, VK_LALT, VK_Q = 0xA0, 0xA2, 0xA4, 0x51


# --- decoding Windows' flags ---------------------------------------------------


def test_the_keyboard_and_mouse_injected_bits_are_different_and_documented():
    # KBDLLHOOKSTRUCT uses 0x10; MSLLHOOKSTRUCT uses 0x01. Mixing them up would label everything wrongly.
    assert inputprobe.LLKHF_INJECTED == 0x10 and inputprobe.LLMHF_INJECTED == 0x01
    assert source_of(0x10, inputprobe.LLKHF_INJECTED, inputprobe.LLKHF_LOWER_IL_INJECTED) == INJECTED
    assert source_of(0x01, inputprobe.LLKHF_INJECTED, inputprobe.LLKHF_LOWER_IL_INJECTED) == PHYSICAL
    assert source_of(0x01, inputprobe.LLMHF_INJECTED, inputprobe.LLMHF_LOWER_IL_INJECTED) == INJECTED
    assert source_of(0x10, inputprobe.LLMHF_INJECTED, inputprobe.LLMHF_LOWER_IL_INJECTED) == PHYSICAL


def test_input_injected_from_a_lower_integrity_process_is_labelled_as_such():
    assert source_of(0x10 | 0x02, 0x10, 0x02) == INJECTED_LOW
    assert source_of(0x02, 0x10, 0x02) == PHYSICAL  # the lower-IL bit alone means nothing


def test_modifier_keys_are_named_and_every_other_key_is_not():
    # The quit chord is made of modifiers, so they are named. What you type must not be captured.
    assert key_event(1.0, inputprobe.WM_KEYDOWN, VK_LSHIFT, 0x10).name == "LShift"
    assert key_event(1.0, inputprobe.WM_KEYUP, VK_LCTRL, 0).name == "LCtrl"
    assert key_event(1.0, inputprobe.WM_SYSKEYDOWN, VK_LALT, 0x20).name == "LAlt"
    other = key_event(1.0, inputprobe.WM_KEYDOWN, VK_Q, 0x10)
    assert other.name == "other key"
    assert "Q" not in repr(other) and "0x51" not in repr(other) and "81" not in repr(other)


def test_key_actions_and_unknown_messages():
    assert key_event(0, inputprobe.WM_KEYDOWN, VK_LSHIFT, 0).action == "down"
    assert key_event(0, inputprobe.WM_SYSKEYUP, VK_LSHIFT, 0).action == "up"
    assert key_event(0, 0x9999, VK_LSHIFT, 0) is None


def test_mouse_events_are_classified():
    assert mouse_event(0, inputprobe.WM_MOUSEMOVE, 0).action == "move"
    assert mouse_event(0, inputprobe.WM_LBUTTONDOWN, 1).source == INJECTED
    assert mouse_event(0, inputprobe.WM_RBUTTONUP, 0).action == "right up"
    assert mouse_event(0, inputprobe.WM_MOUSEWHEEL, 0).action == "wheel"
    assert mouse_event(0, 0x9999, 0) is None


# --- the report ------------------------------------------------------------------


def ev(t, device, action, name, source):
    return Event(t, device, action, name, source)


def test_report_says_so_when_both_kinds_are_seen():
    events = [
        ev(1.0, "keyboard", "down", "LShift", INJECTED),
        ev(2.0, "keyboard", "down", "LShift", PHYSICAL),
        ev(3.0, "mouse", "move", "", INJECTED),
    ]
    text = summarize(events, 60, "2026-10-09 10:00:00")
    assert "RESULT: both kinds were seen" in text
    assert "Keyboard" in text and "2 events" in text and "1 injected" in text and "1 physical" in text


def test_report_flags_the_bad_case_where_the_clients_input_looks_like_hardware():
    text = summarize([ev(1.0, "keyboard", "down", "LShift", PHYSICAL)], 60, "x")
    assert "only physical input" in text and "bad case" in text


def test_report_asks_for_the_missing_half_when_only_injected_input_was_seen():
    text = summarize([ev(1.0, "mouse", "move", "", INJECTED)], 60, "x")
    assert "only injected input" in text and "own keyboard and mouse" in text


def test_report_with_no_input():
    assert "no input was seen" in summarize([], 60, "x")


def test_a_burst_of_identical_events_is_folded_into_one_line():
    events = [ev(i / 100, "mouse", "move", "", INJECTED) for i in range(250)]
    events.append(ev(3.0, "keyboard", "down", "LCtrl", INJECTED))
    text = summarize(events, 60, "x")
    assert "x250" in text
    assert text.count("move") == 1


def test_a_long_report_is_capped():
    events = []
    for i in range(300):  # alternate so nothing folds
        events.append(ev(i, "keyboard", "down" if i % 2 else "up", "LShift", INJECTED))
    text = summarize(events, 60, "x", max_lines=20)
    assert "and 280 more lines" in text


def test_the_report_never_names_a_non_modifier_key():
    events = [key_event(1.0, inputprobe.WM_KEYDOWN, vk, 0) for vk in (0x41, 0x50, 0x51, 0x31, 0x0D)]
    text = summarize([e for e in events if e], 60, "x")
    assert "other key" in text
    for forbidden in ("0x41", "0x50", "0x51", "'A'", "'P'", "'Q'", "Enter"):
        assert forbidden not in text


def test_probe_records_times_relative_to_its_start():
    clock = iter([100.0, 100.5, 102.25])
    probe = Probe(clock=lambda: next(clock))
    probe.key(inputprobe.WM_KEYDOWN, VK_LSHIFT, 0x10)
    probe.mouse(inputprobe.WM_MOUSEMOVE, 0)
    assert [round(e.t, 2) for e in probe.events] == [0.5, 2.25]


# --- the Windows hook plumbing, with a mocked user32 -------------------------------


@pytest.fixture
def fake_windows(monkeypatch):
    user32, kernel32 = mock.Mock(), mock.Mock()
    handles = iter([111, 222, 333])
    user32.SetWindowsHookExW.side_effect = lambda *args: next(handles)
    user32.PeekMessageW.return_value = 0
    user32.CallNextHookEx.return_value = 0
    monkeypatch.setattr(inputprobe.ctypes, "windll", mock.Mock(user32=user32, kernel32=kernel32), raising=False)
    # On Windows WINFUNCTYPE wraps a Python function into a C callback; here the function itself will do.
    monkeypatch.setattr(inputprobe.ctypes, "WINFUNCTYPE", lambda restype, *argtypes: (lambda f: f), raising=False)
    monkeypatch.setattr(inputprobe.ctypes, "WinError", lambda: OSError("could not install the hook"), raising=False)
    return user32, kernel32


def ticking_clock():
    state = {"t": 0.0}

    def clock():
        state["t"] += 0.01
        return state["t"]

    return clock


def test_listen_installs_both_low_level_hooks_and_removes_them(fake_windows):
    user32, _ = fake_windows
    inputprobe.listen(Probe(clock=ticking_clock()), 0.05, clock=ticking_clock(), sleep=lambda s: None)
    installed = [call.args[0] for call in user32.SetWindowsHookExW.call_args_list]
    assert installed == [inputprobe.WH_KEYBOARD_LL, inputprobe.WH_MOUSE_LL]  # 13 and 14
    assert [call.args[0] for call in user32.UnhookWindowsHookEx.call_args_list] == [111, 222]


def test_the_hooks_record_what_windows_hands_them_and_pass_everything_on(fake_windows):
    user32, _ = fake_windows
    probe = Probe(clock=ticking_clock())
    keyboard_struct = KBDLLHOOKSTRUCT(vkCode=VK_LSHIFT, flags=0x10)  # injected
    mouse_struct = MSLLHOOKSTRUCT(pt=POINT(5, 6), flags=0)  # physical

    def fire(_seconds):
        callbacks = {c.args[0]: c.args[1] for c in user32.SetWindowsHookExW.call_args_list}
        callbacks[inputprobe.WH_KEYBOARD_LL](0, inputprobe.WM_KEYDOWN, ctypes.addressof(keyboard_struct))
        callbacks[inputprobe.WH_MOUSE_LL](0, inputprobe.WM_MOUSEMOVE, ctypes.addressof(mouse_struct))
        callbacks[inputprobe.WH_KEYBOARD_LL](-1, inputprobe.WM_KEYDOWN, 0)  # nCode < 0: must be ignored, not read

    inputprobe.listen(probe, 0.03, clock=ticking_clock(), sleep=fire)
    kinds = {(e.device, e.name, e.source) for e in probe.events}
    assert kinds == {("keyboard", "LShift", INJECTED), ("mouse", "", PHYSICAL)}
    # Every callback, including the ignored one, handed the event on to the next hook untouched.
    assert user32.CallNextHookEx.call_count >= 3
    assert probe.errors == 0


def test_a_bad_event_is_counted_and_never_raised_into_windows(fake_windows):
    user32, _ = fake_windows
    probe = Probe(clock=ticking_clock())

    def fire(_seconds):
        callbacks = {c.args[0]: c.args[1] for c in user32.SetWindowsHookExW.call_args_list}
        callbacks[inputprobe.WH_MOUSE_LL](0, inputprobe.WM_MOUSEMOVE, 0)  # a null pointer: reading it must not crash

    inputprobe.listen(probe, 0.02, clock=ticking_clock(), sleep=fire)
    assert probe.errors >= 1


def test_hooks_are_removed_even_if_listening_fails_midway(fake_windows):
    user32, _ = fake_windows

    def explode(_seconds):
        raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError):
        inputprobe.listen(Probe(clock=ticking_clock()), 1.0, clock=ticking_clock(), sleep=explode)
    assert [call.args[0] for call in user32.UnhookWindowsHookEx.call_args_list] == [111, 222]


def test_if_the_second_hook_cannot_be_installed_the_first_is_removed(fake_windows):
    user32, _ = fake_windows
    results = iter([111, 0])
    user32.SetWindowsHookExW.side_effect = lambda *args: next(results)
    with pytest.raises(OSError):
        inputprobe.listen(Probe(clock=ticking_clock()), 0.05, clock=ticking_clock(), sleep=lambda s: None)
    assert [call.args[0] for call in user32.UnhookWindowsHookEx.call_args_list] == [111]


# --- running it ---------------------------------------------------------------------


def test_run_refuses_off_windows(monkeypatch, capsys):
    monkeypatch.setattr(inputprobe.winapi, "IS_WINDOWS", False)
    assert inputprobe.run(5, None) == 1
    assert "only runs on Windows" in capsys.readouterr().err


def test_run_prints_and_saves_the_report(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(inputprobe.winapi, "IS_WINDOWS", True)

    def fake_listen(probe, seconds):
        probe.events.append(ev(1.0, "keyboard", "down", "LShift", INJECTED))
        probe.events.append(ev(2.0, "keyboard", "down", "LShift", PHYSICAL))

    monkeypatch.setattr(inputprobe, "listen", fake_listen)
    out = tmp_path / "logs" / "input-probe.txt"
    assert inputprobe.run(5, out) == 0
    assert "RESULT: both kinds were seen" in out.read_text(encoding="utf-8")
    assert "Saved to" in capsys.readouterr().out


def test_run_reports_a_hook_that_cannot_be_installed(monkeypatch, capsys):
    monkeypatch.setattr(inputprobe.winapi, "IS_WINDOWS", True)

    def failing_listen(probe, seconds):
        raise OSError("access denied")

    monkeypatch.setattr(inputprobe, "listen", failing_listen)
    assert inputprobe.run(5, None) == 1
    assert "Could not install the input hooks" in capsys.readouterr().err


def test_main_saves_to_the_logs_folder(monkeypatch, tmp_path):
    import applog

    monkeypatch.setattr(applog, "log_dir", lambda: tmp_path / "logs")
    seen = {}
    monkeypatch.setattr(inputprobe, "run", lambda seconds, out: seen.update(seconds=seconds, out=out) or 0)
    assert inputprobe.main(["--seconds", "90"]) == 0
    assert seen == {"seconds": 90.0, "out": tmp_path / "logs" / "input-probe.txt"}
    inputprobe.main(["--seconds", "0"])
    assert seen["seconds"] == 1.0  # never zero
