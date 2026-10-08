import pytest

from saver.exitpolicy import KEY, MOUSE_CLICK, MOUSE_MOVE, ExitPolicy

ALL = (KEY, MOUSE_MOVE, MOUSE_CLICK)


def policy(**kw):
    args = dict(start=100.0, grace_seconds=2.0, exit_on=ALL, move_threshold_px=12, mouse_origin=(500, 500))
    args.update(kw)
    return ExitPolicy(**args)


@pytest.mark.parametrize("kind", ALL)
def test_everything_is_ignored_during_the_grace_period(kind):
    p = policy()
    assert p.should_exit(kind, now=100.0, pos=(900, 900)) is False
    assert p.should_exit(kind, now=101.99, pos=(900, 900)) is False


def test_grace_ends_exactly_at_the_configured_time():
    p = policy()
    assert p.in_grace(101.999)
    assert not p.in_grace(102.0)


def test_key_exits_after_grace():
    assert policy().should_exit(KEY, now=102.5) is True


def test_click_exits_after_grace():
    assert policy().should_exit(MOUSE_CLICK, now=102.5, pos=(1, 1)) is True


def test_small_jitter_after_grace_does_not_exit():
    p = policy()
    assert p.should_exit(MOUSE_MOVE, now=103, pos=(503, 504)) is False  # 5 px
    assert p.should_exit(MOUSE_MOVE, now=103.1, pos=(500, 511)) is False  # 11 px


def test_real_movement_after_grace_exits():
    assert policy().should_exit(MOUSE_MOVE, now=103, pos=(500, 512)) is True  # exactly 12 px


def test_movement_during_grace_rebaselines_the_pointer():
    # The pointer drifts to (800, 300) while the saver is starting. That is the
    # new resting place; wiggling around it afterwards must not exit.
    p = policy()
    p.should_exit(MOUSE_MOVE, now=100.5, pos=(800, 300))
    assert p.should_exit(MOUSE_MOVE, now=102.5, pos=(804, 303)) is False
    assert p.should_exit(MOUSE_MOVE, now=102.6, pos=(850, 300)) is True


def test_first_mouse_sample_without_a_reference_is_not_a_movement():
    p = policy(mouse_origin=None)
    assert p.should_exit(MOUSE_MOVE, now=105, pos=(10, 10)) is False
    assert p.should_exit(MOUSE_MOVE, now=105.1, pos=(300, 10)) is True


def test_zero_threshold_exits_on_any_motion_event():
    p = policy(move_threshold_px=0)
    assert p.should_exit(MOUSE_MOVE, now=103, pos=(500, 500)) is True


def test_event_kinds_not_in_exit_on_are_ignored():
    p = policy(exit_on=(KEY,))
    assert p.should_exit(MOUSE_CLICK, now=103) is False
    assert p.should_exit(MOUSE_MOVE, now=103, pos=(900, 900)) is False
    assert p.should_exit(KEY, now=103) is True


def test_zero_grace_period_exits_immediately():
    assert policy(grace_seconds=0).should_exit(KEY, now=100.0) is True


def test_mouse_move_without_position_never_exits():
    assert policy().should_exit(MOUSE_MOVE, now=103, pos=None) is False
