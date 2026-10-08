import logging
import subprocess
import sys
from types import SimpleNamespace

import pytest

import applog
import config
import launcher


class FakeProc:
    def __init__(self, returncode=None, pid=4242):
        self.returncode = returncode
        self.pid = pid
        self.terminated = False

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode if self.returncode is not None else 0

    def terminate(self):
        self.terminated = True
        self.returncode = 1


@pytest.fixture
def log():
    return logging.getLogger("test-launcher")


@pytest.fixture(autouse=True)
def isolated_logs(monkeypatch, tmp_path):
    # Keep logs/saver-stderr.log out of the real repo during tests.
    monkeypatch.setattr(applog, "log_dir", lambda: tmp_path / "logs")


def test_command_runs_saver_module_in_fullscreen_mode():
    assert launcher.SaverLauncher.command() == [sys.executable, "-m", "saver.main", "/s"]


def test_start_spawns_saver_in_src_dir(log):
    calls = []

    def popen(cmd, **kw):
        calls.append((cmd, kw))
        return FakeProc()

    sl = launcher.SaverLauncher(log, popen=popen)
    assert sl.start() is True
    cmd, kw = calls[0]
    assert cmd[-2:] == ["saver.main", "/s"]
    assert kw["cwd"] == str(launcher.SRC_DIR)
    assert kw["env"]["PYGAME_HIDE_SUPPORT_PROMPT"] == "1"
    assert kw["stdin"] == subprocess.DEVNULL


def test_second_click_while_running_does_not_start_another(log):
    popen_calls = []

    def popen(cmd, **kw):
        popen_calls.append(cmd)
        return FakeProc()

    sl = launcher.SaverLauncher(log, popen=popen)
    assert sl.start() is True
    assert sl.is_running()
    assert sl.start() is False
    assert len(popen_calls) == 1


def test_can_start_again_after_saver_exits(log):
    procs = [FakeProc(returncode=0), FakeProc()]
    sl = launcher.SaverLauncher(log, popen=lambda cmd, **kw: procs.pop(0))
    assert sl.start() is True
    assert not sl.is_running()  # first one already finished
    assert sl.start() is True


def test_spawn_failure_is_contained_and_reported(log):
    def popen(cmd, **kw):
        raise OSError("boom")

    sl = launcher.SaverLauncher(log, popen=popen)
    assert sl.start() is False  # tray keeps running
    assert not sl.is_running()


def test_stop_terminates_a_running_saver(log):
    proc = FakeProc()
    sl = launcher.SaverLauncher(log, popen=lambda cmd, **kw: proc)
    sl.start()
    sl.stop()
    assert proc.terminated


def test_stop_without_saver_is_a_no_op(log):
    launcher.SaverLauncher(log).stop()


def test_open_config_creates_missing_file_and_uses_notepad_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "IS_WINDOWS", True)
    opened = []
    target = tmp_path / "config.json"
    result = launcher.open_config_file(target, popen=lambda cmd: opened.append(cmd))
    assert result == target
    assert target.exists()
    assert opened == [["notepad.exe", str(target)]]


def test_open_config_does_not_overwrite_existing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "IS_WINDOWS", True)
    target = tmp_path / "config.json"
    target.write_text('{"mode": "clock", "mine": true}', encoding="utf-8")
    launcher.open_config_file(target, popen=lambda cmd: None)
    assert '"mine"' in target.read_text(encoding="utf-8")


def test_open_config_uses_xdg_open_elsewhere(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "IS_WINDOWS", False)
    monkeypatch.setattr(sys, "platform", "linux")
    opened = []
    launcher.open_config_file(tmp_path / "config.json", popen=lambda cmd: opened.append(cmd))
    assert opened[0][0] == "xdg-open"


def test_frozen_launch_is_explicitly_unsupported_until_packaging(monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    with pytest.raises(NotImplementedError):
        launcher.SaverLauncher.command()
