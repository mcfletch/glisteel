"""The steering the game puts in while the player is not steering."""
import numpy as np
import pytest

from glisteel import scenarios
from glisteel.assist import DEADZONE, STRENGTH, Straighten
from glisteel.session import Session


def _session(piece=None, traffic=0, **named):
    piece = piece or scenarios.straight(length=1600.0)
    session = Session(piece.world(traffic=traffic), **named)
    session.run.go()
    return session


def _off(session):
    _index, distance = session.course.nearest(session.car.position)
    return float(distance)


def _across(course, at):
    """How far to its own right of the centreline a point is, in metres."""
    at = np.asarray(at, dtype='d')[:3]
    index, _distance = course.nearest(at)
    return float(np.dot(at - course.point(index), course.across(index)))


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
    """A tap moves the car across the road and leaves it there, rather than
    starting it across the road for good."""

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

    def test_and_the_car_settles_onto_a_line_after_it(self):
        """It crosses the road while the key is down -- that is the input --
        and then runs along the road again, rather than carrying on across it
        until there is none left."""
        trace = self._drive(line='throttle 0..4; left 5..6.0', seconds=13.0)
        assert trace.heading_change(11.5, 13.0) < 1.0, trace.report()
        assert abs(float(trace.off_line[-1])) \
            < float(np.abs(trace.off_line).max())

    def test_it_does_not_steer_a_car_that_is_already_on_the_line(self):
        trace = self._drive(line='throttle 0..8', seconds=8.0)
        assert trace.worst_off_line() < 0.5


class TestTheLineItHolds:
    """The aid holds the line the car is on, not one of its own.

    A player who has put the car where they want it must not find it drawn
    across the road under them: an aid with a line of its own has to be fought
    the whole way past anything being overtaken, and it takes a car nobody
    steered somewhere nobody asked for. Steering out and letting go is how a
    lane is changed, and what is held afterwards is the new one.
    """

    @staticmethod
    def _driving(line='throttle 0..14', seconds=14.0, traffic=0):
        from glisteel.scripted import Script
        from glisteel.trace import drive
        session = Session(
            scenarios.straight(length=1600.0).world(traffic=traffic))
        return session, drive(session, Script.parse(line), seconds=seconds)

    #: A drive that pulls out of the lane it started in and lets go.
    PULLING_OUT = 'throttle 0..16; left 5..5.6'

    @classmethod
    @pytest.fixture(scope='class')
    def pulled_out(cls):
        """Where that drive started, where it settled, and what is held now.

        Three readings of one sixteen-second drive rather than three drives of
        it. Read off here and handed over as numbers, so that nothing below
        holds the session itself: a live session shared between tests is a
        test that passes or fails on what the one before it did.
        """
        session, trace = cls._driving(cls.PULLING_OUT, seconds=16.0)
        return {'started': _across(session.course, trace.position[0]),
                'settled': _across(session.course, session.car.position),
                'held': session.assist.line}

    def test_a_car_steered_onto_another_line_is_held_on_that_one(self, pulled_out):
        assert pulled_out['settled'] == pytest.approx(pulled_out['held'], abs=0.4)

    def test_and_that_line_is_the_one_the_player_let_go_on(self, pulled_out):
        assert abs(pulled_out['held'] - pulled_out['started']) > 0.8

    def test_rather_than_taken_back_to_the_line_it_came_from(self, pulled_out):
        assert abs(pulled_out['settled'] - pulled_out['started']) > 0.8, pulled_out

    def test_a_car_put_on_a_road_with_two_ways_keeps_its_own_side(self):
        """Which is where the session stands it, and the aid holds it there
        without ever having been told which side that is."""
        session, _trace = self._driving(traffic=4)
        assert _across(session.course, session.car.position) \
            == pytest.approx(session.lane, abs=0.4)

    def test_a_car_already_running_straight_is_asked_for_nothing(self):
        session, _trace = self._driving(seconds=8.0)
        assert abs(session.assist.steer(session, 0.0)) < 0.05

    def test_the_line_it_holds_stays_on_the_carriageway(self):
        """A player who lets go with two wheels on the grass is not asking to
        be held there."""
        session = _session()
        course = session.course
        edge = course.carriageway_width / 2.0
        position, heading = course.grid_position(session.grid, height=0.9,
                                                 lane=edge + 3.0)
        session.car.place(position, heading)
        session.assist.steer(session, 0.0)
        assert abs(session.assist.line) < edge

    def test_a_car_set_back_down_takes_a_fresh_line(self):
        """The line it was on was a line on the road it was on before."""
        session = _session()
        session.assist.hold(2.0)
        session.return_to_track()
        session.assist.steer(session, 0.0)
        assert abs(session.assist.line) < 0.5


class TestItIsTheGameSDial:
    def test_a_session_takes_the_strength_it_is_given(self):
        assert _session(assist=0.3).assist.strength == pytest.approx(0.3)

    def test_and_the_shipped_default_otherwise(self):
        assert _session().assist.strength == pytest.approx(STRENGTH)

    def test_a_session_that_is_not_helped_leaves_the_line_alone(self):
        session = _session(assist=0.0, traffic=4)
        session.assist.hold(3.0)
        session.assist.steer(session, 0.0)
        assert session.assist.line == pytest.approx(3.0)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
