"""The keys that drive the car, from the names the window actually sends.

The arrows arrive as ``<left>`` and ``<right>`` rather than under bare names,
and a control bound to the wrong one is steering that does nothing. Nothing
here needs a window: :class:`~glisteel.steering.KeyboardDriver` is a set of
held keys and the arithmetic that turns them into pedals and a wheel.
"""
import pytest

from glisteel.steering import KeyboardDriver

STEP = 1.0 / 120.0


class _Car:
    """A car that is standing still, which is all the brake pedal asks about.

    One method, because that is all the pedal reaches for now: it used to go
    through the car to the vehicle underneath, and a double had to be shaped
    like both.
    """

    def forward_speed(self) -> float:
        return 0.0


class _Session:
    car = _Car()


def _steer_for(driver: KeyboardDriver, seconds: float) -> float:
    """Sample the controls for ``seconds`` and return the steering it settles at."""
    steer = 0.0
    for _ in range(int(round(seconds / STEP))):
        steer = driver.controls(_Session(), STEP)[2]
    return steer


class TestTheKeysThatDriveIt:
    def test_the_left_arrow_winds_on_to_full_left(self) -> None:
        driver = KeyboardDriver()
        driver.press('<left>')
        assert _steer_for(driver, 1.5) == pytest.approx(1.0)

    def test_the_right_arrow_winds_on_to_full_right(self) -> None:
        driver = KeyboardDriver()
        driver.press('<right>')
        assert _steer_for(driver, 1.5) == pytest.approx(-1.0)

    def test_a_tap_is_only_a_nudge(self) -> None:
        """A brief press must not fling the car to full lock."""
        driver = KeyboardDriver()
        driver.press('<left>')
        assert 0.0 < _steer_for(driver, 0.05) < 0.2

    def test_releasing_the_wheel_returns_it_to_centre(self) -> None:
        driver = KeyboardDriver()
        driver.press('<right>')
        _steer_for(driver, 1.5)
        driver.release('<right>')
        assert _steer_for(driver, 1.5) == pytest.approx(0.0)

    def test_letting_go_of_everything_returns_it_too(self) -> None:
        """Losing the window drops every key at once, and the wheel has to come
        back from that the same way it comes back from a release."""
        driver = KeyboardDriver()
        driver.press('<left>')
        _steer_for(driver, 1.5)
        driver.release_all()
        assert _steer_for(driver, 1.5) == pytest.approx(0.0)

    def test_the_up_arrow_is_the_throttle(self) -> None:
        driver = KeyboardDriver()
        driver.press('<up>')
        assert driver.controls(_Session(), STEP)[0] == pytest.approx(1.0)

    def test_a_and_d_still_steer(self) -> None:
        """The arrows and WASD are the same control, so both have to work."""
        driver = KeyboardDriver()
        driver.press('a')
        assert _steer_for(driver, 1.5) == pytest.approx(1.0)
        driver.release('a')
        driver.press('d')
        assert _steer_for(driver, 3.0) == pytest.approx(-1.0)

    def test_w_is_the_throttle(self) -> None:
        driver = KeyboardDriver()
        driver.press('w')
        assert driver.controls(_Session(), STEP)[0] == pytest.approx(1.0)

    def test_the_brake_reverses_a_car_that_has_stopped(self) -> None:
        driver = KeyboardDriver()
        driver.press('<down>')
        throttle, brake, _ = driver.controls(_Session(), STEP)
        assert throttle == pytest.approx(-1.0) and brake == 0.0

    def test_and_stops_one_that_is_moving(self) -> None:
        driver = KeyboardDriver()
        driver.press('<down>')

        class _Moving(_Session):
            class car:
                @staticmethod
                def forward_speed() -> float:
                    return 20.0
        throttle, brake, _ = driver.controls(_Moving(), STEP)
        assert brake == pytest.approx(1.0) and throttle == 0.0

    def test_the_handbrake_stops_it_whatever_else_is_held(self) -> None:
        driver = KeyboardDriver()
        driver.press('w')
        driver.press(' ')
        _throttle, brake, _steer = driver.controls(_Session(), STEP)
        assert brake == pytest.approx(1.0)


class TestSteeringWithThePointer:
    def test_the_pointer_has_the_wheel_while_no_key_is_down(self) -> None:
        from glisteel.steering import MouseWheel
        pointer = MouseWheel(width=1000)
        driver = KeyboardDriver(pointer)
        pointer.moved(200)
        assert driver.controls(_Session(), STEP)[2] == pytest.approx(
            pointer.position)

    def test_and_a_key_takes_it_back(self) -> None:
        """A driver reaching for a key has decided the pointer is not where
        they want the wheel."""
        from glisteel.steering import MouseWheel
        pointer = MouseWheel(width=1000)
        driver = KeyboardDriver(pointer)
        pointer.moved(200)
        driver.press('<right>')
        assert _steer_for(driver, 1.5) == pytest.approx(-1.0)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
