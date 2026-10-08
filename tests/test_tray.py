"""Tray wiring, tested against a fake `pystray` (the real one needs a display)."""

import sys
import types

import pytest

import applog
import autostart
import tray


class FakeMenuItem:
    def __init__(self, text, action, default=False):
        self.text, self.action, self.default = text, action, default


class FakeIcon:
    last = None

    def __init__(self, name, image, title, menu):
        self.name, self.image, self.title, self.menu = name, image, title, menu
        self.stopped = False
        FakeIcon.last = self

    def run(self):
        pass  # the real one blocks until Exit is chosen

    def stop(self):
        self.stopped = True


@pytest.fixture
def fake_pystray(monkeypatch):
    mod = types.ModuleType("pystray")
    mod.Menu = lambda *items: list(items)
    mod.MenuItem = FakeMenuItem
    mod.Icon = FakeIcon
    monkeypatch.setitem(sys.modules, "pystray", mod)
    FakeIcon.last = None
    return mod


@pytest.fixture(autouse=True)
def isolated_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(applog, "log_dir", lambda: tmp_path / "logs")


def test_menu_has_start_settings_exit_and_start_is_the_left_click_default(fake_pystray):
    assert tray.run_tray() == 0
    items = FakeIcon.last.menu
    assert [i.text for i in items] == ["Start screensaver", "Settings", "Exit"]
    assert [i.default for i in items] == [True, False, False]
    assert FakeIcon.last.title == "Saria's Song"
    assert FakeIcon.last.image.size == (64, 64)


def test_menu_actions_call_launcher_settings_and_stop(fake_pystray, monkeypatch):
    started, opened = [], []
    monkeypatch.setattr(tray.SaverLauncher, "start", lambda self: started.append(1) or True)
    monkeypatch.setattr(tray, "open_config_file", lambda: opened.append(1))
    tray.run_tray()
    icon = FakeIcon.last
    start, settings, exit_ = icon.menu
    start.action(icon, start)
    settings.action(icon, settings)
    assert started == [1] and opened == [1]
    exit_.action(icon, exit_)
    assert icon.stopped


def test_a_failing_menu_action_is_logged_not_raised(fake_pystray, monkeypatch):
    def boom(self):
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(tray.SaverLauncher, "start", boom)
    tray.run_tray()
    start = FakeIcon.last.menu[0]
    start.action(FakeIcon.last, start)  # must not propagate into pystray's thread


def test_second_instance_exits_quietly_without_building_an_icon(fake_pystray, monkeypatch):
    monkeypatch.setattr(tray.winapi, "acquire_single_instance", lambda name: None)
    assert tray.run_tray() == 0
    assert FakeIcon.last is None


def test_cli_install_and_uninstall_autostart(monkeypatch, capsys):
    monkeypatch.setattr(autostart, "enable", lambda: "C:/x/Saria's Song.lnk")
    assert tray.main(["--install-autostart"]) == 0
    assert "Autostart enabled" in capsys.readouterr().out

    monkeypatch.setattr(autostart, "disable", lambda: True)
    assert tray.main(["--uninstall-autostart"]) == 0
    assert "disabled" in capsys.readouterr().out

    monkeypatch.setattr(autostart, "disable", lambda: False)
    tray.main(["--uninstall-autostart"])
    assert "was not enabled" in capsys.readouterr().out


def test_cli_reports_autostart_failure_with_nonzero_exit(monkeypatch, capsys):
    def fail():
        raise RuntimeError("autostart is only supported on Windows")

    monkeypatch.setattr(autostart, "enable", fail)
    assert tray.main(["--install-autostart"]) == 1
    assert "only supported on Windows" in capsys.readouterr().err
