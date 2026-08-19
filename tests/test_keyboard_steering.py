"""Steering from on/off keys, wound into a wheel instead of a switch.

The keys give three states -- full left, straight, full right -- and fed to the
car as they are, that is a wheel yanked to the stop and back: a tap at speed is a
spin. The wheel *winds* on and off instead, so a tap is a nudge and a hold builds
to lock. Nothing here needs a window; it is time and arithmetic.
"""
import pytest

from glisteel.steering import KeyboardWheel


def _hold(wheel: KeyboardWheel, target: float, seconds: float,
          dt: float = 1.0 / 120.0) -> float:
    """Hold ``target`` for ``seconds`` and return where the wheel ends up."""
    for _ in range(int(round(seconds / dt))):
        wheel.toward(target, dt)
    return wheel.position


class TestTheKeyboardWheel:
    def test_straight_stays_straight(self) -> None:
        wheel = KeyboardWheel()
        assert _hold(wheel, 0.0, 1.0) == pytest.approx(0.0)

    def test_a_tap_is_only_a_nudge(self) -> None:
        """A brief press is a small angle, not full lock."""
        wheel = KeyboardWheel()
        assert 0.0 < _hold(wheel, 1.0, 0.05) < 0.2

    def test_a_hold_builds_to_full_lock(self) -> None:
        wheel = KeyboardWheel()
        assert _hold(wheel, 1.0, 1.5) == pytest.approx(1.0)

    def test_it_does_not_wind_past_the_lock(self) -> None:
        wheel = KeyboardWheel()
        assert _hold(wheel, 1.0, 5.0) == pytest.approx(1.0)

    def test_the_right_key_is_the_other_way(self) -> None:
        wheel = KeyboardWheel()
        assert _hold(wheel, -1.0, 1.5) == pytest.approx(-1.0)

    def test_letting_go_returns_to_centre(self) -> None:
        wheel = KeyboardWheel()
        _hold(wheel, 1.0, 1.5)
        assert _hold(wheel, 0.0, 1.5) == pytest.approx(0.0)

    def test_it_centres_quicker_than_it_winds_on(self) -> None:
        """Letting go straightens the car sooner than holding reaches lock."""
        wind = KeyboardWheel()
        _hold(wind, 1.0, 1.0 / wind.wind_on * 0.5)
        reached = wind.position
        back = KeyboardWheel()
        back.position = reached
        # The same distance, timed each way: centring covers it in less time.
        wind_on_time = reached / wind.wind_on
        centre_time = reached / back.centre
        assert centre_time < wind_on_time

    def test_a_flick_to_the_far_lock_crosses_centre(self) -> None:
        wheel = KeyboardWheel()
        _hold(wheel, 1.0, 1.5)
        assert _hold(wheel, -1.0, 2.0) == pytest.approx(-1.0)

    def test_the_target_is_clamped(self) -> None:
        wheel = KeyboardWheel()
        assert _hold(wheel, 5.0, 2.0) == pytest.approx(1.0)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
