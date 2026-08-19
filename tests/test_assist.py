"""The steering the game puts in while the player is not steering."""
import numpy as np
import pytest

from glisteel import scenarios
from glisteel.assist import DEADZONE, STRENGTH, Straighten
from glisteel.session import Session


def _session(piece=None, **named):
    piece = piece or scenarios.straight(length=1600.0)
    session = Session(piece.world(traffic=0), **named)
    session.run.go()
    return session


def _off(session):
    _index, distance = session.course.nearest(session.car.position)
    return float(distance)


class TestWhenItHelps:
    def test_it_leaves_a_player_who_is_steering_alone(self):
        assist = Straighten(_session().course)
        assert assist.holding(0.6)

    def test_and_one_who_is_not_is_helped(self):
        assert not Straighten(_session().course).holding(0.0)

    def test_a_wheel_on_its_way_back_to_centre_counts_as_hands_off(self):
        """Waiting for exactly nothing leaves the car un-helped for the moment
        it most needs it."""
        assert not Straighten(_session().course).holding(DEADZONE / 2.0)

    def test_what_a_player_asked_for_reaches_the_wheel_unchanged(self):
        session = _session()
        assert session.assist.steer(session, 0.7) == pytest.approx(0.7)

    def test_switched_off_it_changes_nothing_at_all(self):
        session = _session(assist=0.0)
        assert session.assist.steer(session, 0.0) == pytest.approx(0.0)

    def test_and_says_it_is_not_helping(self):
        assert not Straighten(_session().course, strength=0.0).helping

    def test_it_says_how_much_it_is_helping(self):
        assert 'Straighten(55%)' == repr(Straighten(_session().course, 0.55))


class TestWhatItDoesToADrive:
    """A tap is a nudge the car comes back from, rather than a permanent change
    of direction that eventually runs out of road."""

    LINE = 'throttle 0..4; left 5..5.3'

    def _drive(self, assist=STRENGTH, seconds=11.0, line=None):
        from glisteel.scripted import Script
        from glisteel.trace import drive
        session = Session(scenarios.straight(length=1600.0).world(traffic=0),
                          assist=assist)
        return drive(session, Script.parse(line or self.LINE), seconds=seconds)

    def test_a_tap_leaves_the_car_on_the_road(self):
        assert self._drive().worst_off_line() < 2.0

    def test_and_pointed_the_way_it_was(self):
        assert self._drive().heading_change(4.9, 11.0) < 1.0

    def test_without_it_the_same_tap_does_not(self):
        """Which is the defect this exists for: the wheel centres, the car
        keeps the heading, and it crosses the road until the road ends."""
        assert self._drive(assist=0.0).worst_off_line() > 3.0

    def test_a_longer_hold_is_still_a_deliberate_input(self):
        """It steers while the key is down; what it does not do is keep going
        afterwards."""
        trace = self._drive(line='throttle 0..4; left 5..6.0', seconds=11.0)
        turned = trace.heading_change(5.0, 6.0)
        assert turned > 3.0

    def test_and_the_car_is_brought_back_to_the_line_after_it(self):
        """It swings wide while the key is down -- that is the input -- and
        then comes back, rather than carrying on across the road."""
        trace = self._drive(line='throttle 0..4; left 5..6.0', seconds=13.0)
        settled = abs(float(trace.off_line[-1]))
        assert settled < float(np.abs(trace.off_line).max())
        assert settled < 3.0

    def test_it_does_not_steer_a_car_that_is_already_on_the_line(self):
        trace = self._drive(line='throttle 0..8', seconds=8.0)
        assert trace.worst_off_line() < 0.5


class TestItIsTheGameSDial:
    def test_a_session_takes_the_strength_it_is_given(self):
        assert _session(assist=0.3).assist.strength == pytest.approx(0.3)

    def test_and_the_shipped_default_otherwise(self):
        assert _session().assist.strength == pytest.approx(STRENGTH)

    def test_it_holds_the_lane_the_session_drives_in(self):
        piece = scenarios.straight(length=1600.0)
        session = Session(piece.world(traffic=4))
        assert session.assist.driver.lane == pytest.approx(session.lane)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
