from unittest import mock

from PIL import Image

import icon
import winapi


def test_icon_is_rgba_square_with_green_and_transparency():
    img = icon.make_icon_image(64)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"
    px = list(img.get_flattened_data())
    assert any(p[3] == 0 for p in px), "background should be transparent"
    greens = [p for p in px if p[3] == 255 and p[1] > p[0] and p[1] > p[2]]
    assert len(greens) > 200, "the note body should be solidly green"


def test_icon_is_drawn_inside_the_canvas_with_margin():
    img = icon.make_icon_image(128)
    left, top, right, bottom = img.getchannel("A").getbbox()
    assert left >= 1 and top >= 1 and right <= 127 and bottom <= 127


def test_write_ico_has_all_sizes(tmp_path):
    path = icon.write_ico(tmp_path / "x.ico")
    with Image.open(path) as ico:
        assert set(ico.info["sizes"]) == {(s, s) for s in icon.ICO_SIZES}


def test_single_instance_is_trivially_true_off_windows(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", False)
    assert winapi.acquire_single_instance("x")


def _fake_windll(last_error):
    k32 = mock.Mock()
    k32.CreateMutexW.return_value = 77
    k32.GetLastError.return_value = last_error
    return mock.Mock(kernel32=k32), k32


def test_single_instance_first_caller_gets_the_handle(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", True)
    windll, k32 = _fake_windll(last_error=0)
    with mock.patch.object(winapi.ctypes, "windll", windll, create=True):
        assert winapi.acquire_single_instance("SariasSong.Tray") == 77
    k32.CreateMutexW.assert_called_once_with(None, False, "Local\\SariasSong.Tray")


def test_single_instance_second_caller_is_refused_and_closes_its_handle(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", True)
    windll, k32 = _fake_windll(last_error=winapi.ERROR_ALREADY_EXISTS)
    with mock.patch.object(winapi.ctypes, "windll", windll, create=True):
        assert winapi.acquire_single_instance("SariasSong.Tray") is None
    k32.CloseHandle.assert_called_once_with(77)


def test_monitor_rects_empty_off_windows(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", False)
    assert winapi.monitor_rects() == []


def test_dpi_awareness_prefers_per_monitor_v2(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", True)
    user32 = mock.Mock()
    user32.SetProcessDpiAwarenessContext.return_value = 1
    windll = mock.Mock(user32=user32)
    with mock.patch.object(winapi.ctypes, "windll", windll, create=True):
        winapi.set_dpi_aware()
    user32.SetProcessDpiAwarenessContext.assert_called_once()
    windll.shcore.SetProcessDpiAwareness.assert_not_called()


def test_dpi_awareness_falls_back_on_old_windows(monkeypatch):
    monkeypatch.setattr(winapi, "IS_WINDOWS", True)
    user32 = mock.Mock()
    user32.SetProcessDpiAwarenessContext.side_effect = AttributeError  # pre-1703
    windll = mock.Mock(user32=user32)
    with mock.patch.object(winapi.ctypes, "windll", windll, create=True):
        winapi.set_dpi_aware()
    windll.shcore.SetProcessDpiAwareness.assert_called_once_with(2)
