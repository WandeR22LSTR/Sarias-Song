import json
from pathlib import Path

import pytest

import config

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_defaults_load_without_warnings():
    cfg = config.from_dict({})
    assert cfg.warnings == ()
    assert cfg.mode == "clock"
    assert cfg.monitors == "all"  # Luca chose "cover all monitors"
    assert cfg.grace_seconds == 2.0
    assert set(cfg.exit_on) == {"key", "mouse_move", "mouse_click"}


def test_shipped_config_json_matches_defaults():
    # config.json in the repo is the file users edit; it must not drift from DEFAULTS.
    shipped = json.loads((REPO_ROOT / "config.json").read_text(encoding="utf-8"))
    assert shipped == config.DEFAULTS
    assert config.load(REPO_ROOT / "config.json").warnings == ()


def test_partial_sections_keep_remaining_defaults():
    cfg = config.from_dict({"colors": {"accent": "#ff0000"}, "clock": {"show_seconds": True}})
    assert cfg.colors.accent == (255, 0, 0)
    assert cfg.colors.background == config.parse_color(config.DEFAULTS["colors"]["background"])
    assert cfg.clock.show_seconds is True
    assert cfg.clock.format_24h is True
    assert cfg.warnings == ()


@pytest.mark.parametrize(
    "value, expected",
    [("#7fd48a", (127, 212, 138)), ("#FFF", (255, 255, 255)), ("  #000000 ", (0, 0, 0)), ("0b1410", (11, 20, 16))],
)
def test_parse_color_accepts(value, expected):
    assert config.parse_color(value) == expected


@pytest.mark.parametrize("value", ["", "#12", "#12345", "#gggggg", 123, None, ["#fff"]])
def test_parse_color_rejects(value):
    with pytest.raises(ValueError):
        config.parse_color(value)


def test_bad_color_falls_back_with_warning():
    cfg = config.from_dict({"colors": {"accent": "green"}})
    assert cfg.colors.accent == config.parse_color(config.DEFAULTS["colors"]["accent"])
    assert any("colors.accent" in w for w in cfg.warnings)


def test_wrong_types_fall_back_with_warnings():
    cfg = config.from_dict(
        {
            "mode": "disco",
            "monitors": 3,
            "animation_speed": "fast",
            "grace_seconds": True,
            "clock": {"format_24h": "yes"},
            "font": "",
        }
    )
    assert cfg.mode == "clock"
    assert cfg.monitors == "all"
    assert cfg.animation_speed == 1.0
    assert cfg.grace_seconds == 2.0
    assert cfg.clock.format_24h is True
    assert cfg.font == config.DEFAULTS["font"]
    assert len(cfg.warnings) == 6


def test_numbers_are_clamped():
    cfg = config.from_dict({"animation_speed": 99, "grace_seconds": -5, "mouse_move_threshold_px": 9999})
    assert cfg.animation_speed == 5.0
    assert cfg.grace_seconds == 0.0
    assert cfg.mouse_move_threshold_px == 500
    assert len(cfg.warnings) == 3


def test_section_that_is_not_an_object_is_rejected():
    cfg = config.from_dict({"colors": "green", "clock": 5})
    assert cfg.colors.accent == config.parse_color(config.DEFAULTS["colors"]["accent"])
    assert cfg.clock.show_date is True
    assert len(cfg.warnings) == 2


def test_empty_exit_on_would_trap_the_user_so_it_is_replaced():
    cfg = config.from_dict({"exit_on": []})
    assert set(cfg.exit_on) == {"key", "mouse_move", "mouse_click"}
    assert cfg.warnings


def test_exit_on_unknown_events_are_dropped():
    cfg = config.from_dict({"exit_on": ["key", "teleport"]})
    assert cfg.exit_on == ("key",)
    assert any("teleport" in w for w in cfg.warnings)


def test_unknown_top_level_keys_warn():
    cfg = config.from_dict({"colour": "#fff"})
    assert any("colour" in w for w in cfg.warnings)


def test_mode_is_case_insensitive():
    assert config.from_dict({"mode": "CLOCK"}).mode == "clock"


def test_load_missing_file_gives_defaults_and_warning(tmp_path):
    cfg = config.load(tmp_path / "nope.json")
    assert cfg.mode == "clock"
    assert "not found" in cfg.warnings[0]


def test_load_invalid_json_gives_defaults_and_warning(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not json", encoding="utf-8")
    cfg = config.load(p)
    assert cfg.mode == "clock"
    assert "not valid JSON" in cfg.warnings[0]


def test_load_non_object_json(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("[1, 2]", encoding="utf-8")
    assert "JSON object" in config.load(p).warnings[0]


def test_load_tolerates_utf8_bom(tmp_path):
    # Windows Notepad can save with a BOM; json.loads would choke on it.
    p = tmp_path / "config.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps({"grace_seconds": 4}).encode())
    cfg = config.load(p)
    assert cfg.grace_seconds == 4
    assert cfg.warnings == ()


def test_write_defaults_round_trips(tmp_path):
    p = config.write_defaults(tmp_path / "config.json")
    assert json.loads(p.read_text(encoding="utf-8")) == config.DEFAULTS


def test_app_dir_from_source_is_repo_root():
    assert config.app_dir() == REPO_ROOT


def test_app_dir_when_frozen_is_exe_folder(monkeypatch, tmp_path):
    # Paths stay relative to the exe so the install folder can be moved.
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(tmp_path / "SariasSong.exe"))
    assert config.app_dir() == tmp_path.resolve()
    assert config.config_path() == tmp_path.resolve() / "config.json"
