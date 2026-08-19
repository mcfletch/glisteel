"""How the car feels, as numbers a budget can be written against.

"Jerky" and "it will not hold a line" are real properties with real numbers
behind them: how fast the wheel moves, how sharply the view swings, and where
the car ends up after an input a player actually gave. Each test here scripts a
drive somebody complained about and measures what came of it.

The tests marked ``xfail`` are the ones the game does not pass yet. Each is a
defect written down as the run that shows it, so that fixing it turns a marker
off rather than needing a test written afterwards; see
``plans/GAMEPLAY-TEST-HARNESS.md`` for what the fix is expected to be.
"""

import numpy as np
import pytest

from glisteel import scenarios
from glisteel.scripted import Script
from glisteel.session import PHYSICS_STEP, Session
from glisteel.trace import drive

#: How fast the car is going when a control is tested at speed, in km/h, and
#: how long the throttle is held to get there.
UP_TO_SPEED = 6.0


def _drive(line, piece=None, seconds=None, view='cockpit', assist=None):
    """Drive a scripted line on a piece of road and bring back the trace.

    ``assist`` is how much of the steering the game puts in
    (:mod:`glisteel.assist`); the default is the shipped one. A test about what
    the car does when nobody corrects it passes 0, since with the assist on
    nobody has to.
    """
    piece = piece or scenarios.straight(length=1600.0)
    named = {} if assist is None else {'assist': assist}
    session = Session(piece.world(), view=view, **named)
    script = Script.parse(line)
    return drive(session, script,
                 seconds=seconds if seconds is not None else script.duration)


class TestTheWheel:
    """The keys give full lock or none; what makes that drivable is the wheel
    they wind, so what it does over time is the whole of how steering feels."""

    def test_letting_go_brings_it_back_to_centre(self) -> None:
        trace = _drive('throttle 0..10; left 4..5', seconds=10.0)
        assert trace.time_to_centre(after=5.0) < 0.5

    def test_a_tap_is_a_nudge_rather_than_a_lock(self) -> None:
        trace = _drive('throttle 0..8; left 6..6.15', seconds=8.0)
        assert trace.steer.max() < 0.4

    def test_the_wheel_never_moves_faster_than_it_is_wound(self) -> None:
        from glisteel.steering import CENTRE
        trace = _drive('throttle 0..10; left 4..5; right 6..7', seconds=10.0)
        assert trace.steering_rate() <= CENTRE * 1.01, trace.report()


class TestACarDrivenStraight:
    """Throttle and nothing else, on a straight road, for twelve seconds.

    Whatever else a car does, it goes where it is pointed. A road is crowned so
    that it drains, so the two sides of the car stand on ground tilted opposite
    ways the whole way along -- and a car that cannot hold that line wanders off
    a road nobody steered it away from, which the player then has to correct for
    without ever having asked it to turn.
    """

    def test_it_stays_on_the_line(self) -> None:
        trace = _drive('throttle 0..12', seconds=12.0)
        assert trace.worst_off_line() < 0.5, trace.report()

    def test_it_stays_pointed_where_it_started(self) -> None:
        trace = _drive('throttle 0..12', seconds=12.0)
        assert trace.heading_change() < 0.5, trace.report()

    def test_and_the_view_is_steady_while_it_does(self) -> None:
        trace = _drive('throttle 0..12', seconds=12.0)
        assert trace.camera_yaw_rate() < 0.02, trace.report()

    def test_over_a_crest_as_well(self) -> None:
        trace = _drive('throttle 0..8', piece=scenarios.crest(), seconds=8.0)
        assert trace.worst_off_line() < 0.5, trace.report()


class TestWhatATapAtSpeedDoes:
    """A tenth of a second on a steering key at a hundred and ten is an input a
    player gives without meaning anything by it. What comes of it is what "the
    steering is too jerky" is about."""

    #: What the car can actually hold, in g: the tyres' own grip plus what the
    #: aerodynamics press on at this speed. Past it something has slipped in the
    #: arithmetic rather than in the corner.
    GRIP = 3.2

    def test_it_corners_within_the_grip_the_car_has(self) -> None:
        trace = _drive('throttle 0..12; left 6..6.15', seconds=12.0)
        assert trace.lateral_g() < self.GRIP, trace.report()

    def test_it_is_a_small_change_of_direction(self) -> None:
        trace = _drive('throttle 0..12; left 6..6.15', seconds=12.0)
        assert trace.heading_change(5.9, 8.0) < 2.0, trace.report()

    def test_and_the_run_survives_it(self) -> None:
        trace = _drive('throttle 0..12; left 6..6.15', seconds=12.0)
        assert trace.why_it_ended() is None, trace.report()

    def test_and_a_driver_who_never_corrects_stays_on_the_road(self) -> None:
        """Which is what the steering assist is for: the wheel centres, and the
        game puts the car back the way the road goes rather than leaving it
        crossing the carriageway until the road runs out."""
        trace = _drive('throttle 0..12; left 6..6.15', seconds=12.0)
        assert not trace.left_the_road(), trace.report()

    def test_and_without_the_assist_a_longer_one_does_not(self) -> None:
        """The defect the assist exists for, kept as a measurement.

        Six tenths of a second, which is what a player gives when the frame
        rate is what decides how briefly they can press a key: the wheel
        centres afterwards and nothing brings the heading back, so the car
        crosses the carriageway and keeps going.
        """
        trace = _drive('throttle 0..12; left 6..6.6', seconds=12.0, assist=0.0)
        assert trace.left_the_road(), trace.report()

    def test_and_with_it_the_same_hold_stays_on(self) -> None:
        trace = _drive('throttle 0..12; left 6..6.6', seconds=12.0)
        assert not trace.left_the_road(), trace.report()

    def test_a_tap_and_a_counter_tap_bring_it_back(self) -> None:
        """Which is what a driver actually does, and what has to be meterable:
        the same touch of the other key puts the car back on the line."""
        trace = _drive('throttle 0..12; left 6..6.15; right 6.6..6.75',
                       seconds=12.0)
        assert not trace.left_the_road(), trace.report()
        assert trace.heading_change(8.0, 12.0) < 0.5, trace.report()


class TestTheViewFromTheDriversSeat:
    """The cockpit is the default view and the one the game is for, so what it
    costs the eye is what most players get."""

    LINE = 'throttle 0..12; left 4..4.6; right 6..6.6'

    def test_a_car_going_straight_does_not_swing_the_view(self) -> None:
        trace = _drive('throttle 0..8', seconds=8.0)
        assert trace.camera_yaw_rate() < 0.05, trace.report()

    @pytest.mark.xfail(strict=True, reason=(
        "the cockpit and bonnet cameras are bolted rigidly to the chassis -- "
        "position and aim are taken from it every frame with nothing between "
        "-- so the eye gets every bump and every twitch of yaw the body does. "
        "See plans/GAMEPLAY-TEST-HARNESS.md section 4.2."))
    def test_it_is_no_harsher_than_watching_from_behind(self) -> None:
        inside = _drive(self.LINE, seconds=12.0, view='cockpit')
        behind = _drive(self.LINE, seconds=12.0, view='chase')
        assert inside.camera_bounce() <= behind.camera_bounce() * 1.5, (
            'from the seat:\n%s\nfrom behind:\n%s'
            % (inside.report(), behind.report()))

    def test_it_is_measured_over_the_same_drive(self) -> None:
        """The two views are the same run seen from two places, so anything
        about the car itself has to come back identical."""
        inside = _drive(self.LINE, seconds=12.0, view='cockpit')
        behind = _drive(self.LINE, seconds=12.0, view='chase')
        assert inside.worst_off_line() == pytest.approx(behind.worst_off_line())


class TestBeingMired:
    """A car that has stayed off the road is mired and the run is over. What
    that has to mean is that the run is over.

    Driven with the steering assist off, because with it on the car does not
    leave the road at all -- which is the point of it, and no way to test what
    happens when a car does.
    """

    LINE = 'throttle 0..14; left 6..6.8'

    def test_a_run_ends_when_the_car_stays_off_the_road(self) -> None:
        trace = _drive(self.LINE, seconds=14.0, assist=0.0)
        assert trace.why_it_ended() is not None

    def _after_it_ended(self, seconds=14.0):
        """The speeds recorded from the moment the run was over."""
        trace = _drive(self.LINE, seconds=seconds, assist=0.0)
        over = [index for index, why in enumerate(trace.ended) if why]
        assert over, "the run did not end at all"
        return trace, trace.speed[over[0]:]

    def test_and_the_car_stops_being_driven(self) -> None:
        """The throttle is no longer connected to anything."""
        trace, after = self._after_it_ended()
        assert after[-1] < 0.5, trace.report()

    def test_and_it_is_never_driven_again_on_the_way_there(self) -> None:
        """Slowing all the way down, rather than slowing and being picked up.

        A car put back on the road would show up here as the speed rising
        again, which is the thing that made a mired run something a player
        could drive out of.
        """
        trace, after = self._after_it_ended()
        gained = float(np.diff(after).max())
        assert gained < 0.05, trace.report()

    def test_and_how_long_that_takes_is_the_grip_it_has_left(self) -> None:
        """Off the road, so it is a long slide rather than a stop."""
        trace, after = self._after_it_ended()
        stopped = int(np.argmax(after < 0.5)) * PHYSICS_STEP
        assert 3.0 < stopped < 12.0, trace.report()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
