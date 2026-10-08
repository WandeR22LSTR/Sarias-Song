from pathlib import Path

import pytest

import autostart
import config


@pytest.fixture
def appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    return tmp_path / "AppData" / "Roaming"


def test_shortcut_lives_in_per_user_startup_folder(appdata):
    expected = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Saria's Song.lnk"
    assert autostart.shortcut_path() == expected


def test_startup_dir_without_appdata_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    with pytest.raises(RuntimeError, match="APPDATA"):
        autostart.startup_dir()
    assert autostart.is_enabled() is False


def test_spec_from_source_runs_tray_py_with_pythonw_if_present(monkeypatch, tmp_path):
    py = tmp_path / "venv" / "python.exe"
    pyw = tmp_path / "venv" / "pythonw.exe"
    py.parent.mkdir()
    py.write_text("")
    pyw.write_text("")
    monkeypatch.setattr("sys.executable", str(py))
    spec = autostart.build_spec()
    assert Path(spec.target) == pyw
    assert spec.arguments.startswith('"') and spec.arguments.endswith('tray.py"')
    assert spec.working_dir == str(config.app_dir())
    assert spec.arguments == f'"{config.app_dir() / "src" / "tray.py"}"'
    assert spec.icon == str(config.app_dir() / "assets" / "saria-song.ico")  # the committed .ico exists


def test_spec_from_source_falls_back_to_python_without_pythonw(monkeypatch, tmp_path):
    py = tmp_path / "python"
    py.write_text("")
    monkeypatch.setattr("sys.executable", str(py))
    assert Path(autostart.build_spec().target) == py


def test_spec_when_frozen_points_at_the_exe(monkeypatch, tmp_path):
    exe = tmp_path / "SariasSong.exe"
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(exe))
    spec = autostart.build_spec()
    assert spec.target == str(exe)
    assert spec.arguments == ""
    assert spec.working_dir == str(tmp_path)
    assert spec.icon == str(exe)


def test_enable_refuses_off_windows(monkeypatch):
    monkeypatch.setattr(autostart, "IS_WINDOWS", False)
    with pytest.raises(RuntimeError, match="only supported on Windows"):
        autostart.enable()


def test_enable_passes_values_through_env_not_the_script(monkeypatch, appdata):
    monkeypatch.setattr(autostart, "IS_WINDOWS", True)
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw

    link = autostart.enable(run=fake_run)
    assert link == autostart.shortcut_path()
    assert link.parent.is_dir()  # Startup folder is created if missing
    assert seen["cmd"][0] == "powershell.exe"
    assert "-NoProfile" in seen["cmd"]
    env = seen["kw"]["env"]
    assert env["SARIA_LNK"] == str(link)
    assert env["SARIA_TARGET"] and env["SARIA_CWD"]
    # No path is interpolated into the script text, so quotes in paths cannot break it.
    script = seen["cmd"][-1]
    assert str(link) not in script and env["SARIA_TARGET"] not in script


def test_disable_removes_shortcut(appdata):
    link = autostart.shortcut_path()
    link.parent.mkdir(parents=True)
    link.write_text("")
    assert autostart.is_enabled()
    assert autostart.disable() is True
    assert not autostart.is_enabled()


def test_disable_when_not_enabled_reports_false(appdata):
    assert autostart.disable() is False
