"""Steering with the mouse, until there is a wheel or a pad to steer with.

A keyboard gives three states -- full left, straight, full right -- and no
amount of tuning makes that feel like a car. A pointer gives a *position*, and
turning sideways movement into lock is what mouse-look already does for a head.

The wheel is centred on the window, not accumulated from the movements: an
accumulated angle drifts, and a pointer that has to be walked back to the middle
to straighten up is a pointer nobody can drive with. Where the pointer is across
the window *is* where the wheel is.
"""
import pytest

from glisteel.steering import MouseWheel


class TestWhereTheWheelIs:
    def test_the_middle_of_the_window_is_straight(self) -> None:
        wheel = MouseWheel(width=1000)
        assert wheel.steer(500) == pytest.approx(0.0)

    def test_the_left_of_it_is_left_lock(self) -> None:
        wheel = MouseWheel(width=1000)
        assert wheel.steer(0) == pytest.approx(1.0)

    def test_and_the_right_is_right_lock(self) -> None:
        wheel = MouseWheel(width=1000)
        assert wheel.steer(1000) == pytest.approx(-1.0)

    def test_it_is_proportional_in_between(self) -> None:
        wheel = MouseWheel(width=1000, curve=1.0, travel=1.0)
        assert wheel.steer(250) == pytest.approx(0.5)

    def test_past_the_edge_is_still_full_lock(self) -> None:
        wheel = MouseWheel(width=1000)
        assert wheel.steer(-400) == pytest.approx(1.0)
        assert wheel.steer(1400) == pytest.approx(-1.0)

    def test_a_narrower_travel_reaches_lock_sooner(self) -> None:
        wide = MouseWheel(width=1000, travel=1.0)
        tight = MouseWheel(width=1000, travel=0.4)
        assert abs(tight.steer(350)) > abs(wide.steer(350))

    def test_the_window_can_change_size_under_it(self) -> None:
        wheel = MouseWheel(width=1000)
        wheel.resize(600)
        assert wheel.steer(300) == pytest.approx(0.0)
        assert wheel.steer(0) == pytest.approx(1.0)


class TestHowItFeels:
    def test_small_movements_near_the_middle_are_gentle(self) -> None:
        """A curve, so a twitch at speed is a twitch and not a spin."""
        wheel = MouseWheel(width=1000, curve=2.0)
        assert abs(wheel.steer(400)) < 0.2

    def test_and_the_ends_still_reach_lock(self) -> None:
        wheel = MouseWheel(width=1000, curve=2.0)
        assert wheel.steer(0) == pytest.approx(1.0)

    def test_a_curve_of_one_is_the_straight_line(self) -> None:
        wheel = MouseWheel(width=1000, curve=1.0, travel=1.0)
        assert wheel.steer(400) == pytest.approx(0.2)

    def test_it_keeps_the_side_it_was_given(self) -> None:
        wheel = MouseWheel(width=1000, curve=2.0)
        assert wheel.steer(400) > 0.0 and wheel.steer(600) < 0.0

    def test_the_last_answer_is_remembered(self) -> None:
        """Read once a physics step, moved once a frame: the wheel is where the
        pointer last put it, not wherever it happens to be asked."""
        wheel = MouseWheel(width=1000)
        wheel.moved(250)
        assert wheel.position == pytest.approx(wheel.steer(250))
        assert wheel.position == pytest.approx(wheel.position)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
