"""A drive written down, and what it did.

A player's inputs are a square wave -- a key is down or it is not -- and what
makes them feel like driving is what happens between the key and the road. To
test that at all, the inputs have to be written down and replayed exactly, and
what the car and the camera did has to come back as numbers.
"""

import numpy as np
import pytest

from glisteel import scenarios
from glisteel.scripted import Hold, Script
from glisteel.session import PHYSICS_STEP, Session
from glisteel.trace import drive


class TestWritingADriveDown:
    def test_a_hold_is_on_between_its_ends(self) -> None:
        script = Script([Hold('throttle', 1.0, 2.0)])
        assert script.holding_at(0.5) == set()
        assert script.holding_at(1.5) == {'throttle'}
        assert script.holding_at(2.5) == set()

    def test_two_holds_can_overlap(self) -> None:
        script = Script([Hold('throttle', 0.0, 4.0), Hold('left', 1.0, 2.0)])
        assert script.holding_at(1.5) == {'throttle', 'left'}

    def test_it_knows_how_long_it_runs(self) -> None:
        assert Script([Hold('throttle', 0.0, 4.0),
                       Hold('left', 1.0, 6.5)]).duration == pytest.approx(6.5)

    def test_it_can_be_written_as_a_line(self) -> None:
        script = Script.parse('throttle 0..4; left 1..2')
        assert script.holding_at(1.5) == {'throttle', 'left'}
        assert script.duration == pytest.approx(4.0)

    def test_an_unknown_control_is_refused(self) -> None:
        with pytest.raises(ValueError):
            Script.parse('boost 0..1')

    def test_nothing_held_is_nothing_asked_for(self) -> None:
        script = Script([])
        assert script.controls(None, PHYSICS_STEP) == (0.0, 0.0, 0.0)


class TestDrivingIt:
    def test_the_throttle_gets_the_car_going(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..4'))
        assert trace.speed.max() > 10.0

    def test_and_the_brake_stops_it(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..6; brake 6..9'))
        assert trace.speed[:600].max() > 10.0
        assert trace.speed[600:].min() < 0.5

    def test_and_holding_it_on_a_stopped_car_reverses(self) -> None:
        """One pedal, two meanings, which is what an arrow key has to do."""
        trace = drive(_session(), Script.parse('brake 0..4'))
        assert trace.throttle.min() == pytest.approx(-1.0)

    def test_holding_a_steering_key_winds_the_wheel_on(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..6; left 2..6'))
        assert trace.steer.max() > 0.9

    def test_and_letting_go_brings_it_back(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..8; left 2..4'))
        assert trace.steer[-1] == pytest.approx(0.0, abs=1e-6)


class TestWhatComesBack:
    def test_there_is_a_row_for_every_step(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..2'))
        assert len(trace.t) == pytest.approx(2.0 / PHYSICS_STEP, abs=2)

    def test_the_clock_runs_at_the_step(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..2'))
        assert np.allclose(np.diff(trace.t), PHYSICS_STEP)

    def test_it_says_where_the_car_was(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..4'))
        assert float(np.linalg.norm(trace.position[-1] - trace.position[0])) > 10.0

    def test_and_where_the_camera_was(self) -> None:
        trace = drive(_session(view='chase'), Script.parse('throttle 0..2'))
        gap = np.linalg.norm(trace.camera - trace.position, axis=1)
        assert gap.min() > 1.0

    def test_and_how_far_off_the_line_it_ran(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..3'))
        assert trace.off_line.max() < 2.0

    def test_and_whether_it_was_on_the_road(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..3'))
        assert trace.on_road.all()

    def test_a_drive_may_be_longer_than_the_script(self) -> None:
        """What the car does after the driver lets go is most of the question."""
        trace = drive(_session(), Script.parse('left 0..1'), seconds=4.0)
        assert trace.t[-1] == pytest.approx(4.0, abs=0.05)


class TestTheMeasures:
    def test_a_wheel_let_go_of_comes_back_to_centre_promptly(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..8; left 2..4'),
                      seconds=8.0)
        assert trace.time_to_centre(after=4.0) < 0.5

    def test_a_wheel_still_held_never_centres(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..8; left 2..8'),
                      seconds=8.0)
        assert trace.time_to_centre(after=4.0) is None

    def test_the_steering_rate_is_what_the_wheel_does_a_second(self) -> None:
        """Held to a lock, the wheel winds on at the rate it is given."""
        from glisteel.steering import WIND_ON
        trace = drive(_session(), Script.parse('throttle 0..8; left 2..8'),
                      seconds=7.0)
        assert trace.steering_rate() == pytest.approx(WIND_ON, rel=0.15)

    def test_a_car_going_straight_is_not_swinging_the_view(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..6'), seconds=6.0)
        assert trace.camera_yaw_rate() < 0.05

    def test_and_one_being_steered_is(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..6; left 2..6'))
        assert trace.camera_yaw_rate() > 0.05

    def test_the_measures_come_back_together(self) -> None:
        trace = drive(_session(), Script.parse('throttle 0..3'))
        found = trace.measures()
        assert 'camera_yaw_jerk' in found and 'steering_rate' in found
        assert all(isinstance(value, float) for value in found.values())


def _session(piece=None, **named):
    piece = piece or scenarios.straight(length=800.0)
    return Session(piece.world(), **named)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
