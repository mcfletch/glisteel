"""How fast the road ahead is worth, and being told when you are over it."""
import math

import numpy as np
import pytest
import support
from OpenGLContext.scenegraph.road import advisory_speed, corner_speed

from glisteel import scenarios
from glisteel.hud import RaceHUD
from glisteel.session import Readings, Session
from glisteel.world import Course


def _stage(bend=60.0, run=1200.0, points=240):
    """An open road: a tight bend, and then a long straight away from it.

    A stage rather than a circuit, which is the case a look-ahead has to know
    about: a circuit's last point runs into its first, and a stage's runs into
    whatever is at the end of it.
    """
    angle = np.linspace(0.0, math.pi / 2.0, 30)
    turn = np.stack([bend - bend * np.cos(angle), np.zeros(30),
                     -bend * np.sin(angle)], axis=-1)
    away = np.stack([bend + np.linspace(5.0, run, points), np.zeros(points),
                     np.full(points, -bend)], axis=-1)
    line = np.vstack([turn, away])
    return Course(name='stage', centreline=line, carriageway_width=7.2,
                  total_width=12.6, closed=False,
                  length=support.perimeter(line, closed=False))


class TestWhatTheRoadAllows:
    def test_a_bend_allows_what_its_radius_allows(self) -> None:
        course = scenarios.sweeper(radius=120.0).course()
        index = len(course.centreline) // 2
        assert course.corner_speed(index) == pytest.approx(
            corner_speed(course.radii[index]))

    def test_a_straight_allows_as_much_as_anything_does(self) -> None:
        course = scenarios.straight().course()
        assert course.corner_speed(4) > 60.0

    def test_the_caution_speed_is_what_a_sign_would_say(self) -> None:
        course = scenarios.sweeper(radius=120.0).course()
        index = len(course.centreline) // 2
        assert course.caution_speed(index) == advisory_speed(
            course.radii[index])

    def test_and_a_straight_needs_no_caution(self) -> None:
        course = scenarios.straight().course()
        assert course.caution_speed(4) == 0


class TestWhatIsComing:
    def test_a_bend_ahead_is_read_before_it_arrives(self) -> None:
        course = scenarios.sweeper(radius=90.0).course()
        assert course.caution_ahead(0, 30.0) > 0

    def test_and_a_straight_ahead_is_not(self) -> None:
        course = scenarios.straight(length=1600.0).course()
        assert course.caution_ahead(0, 30.0) == 0

    def test_the_tightest_thing_coming_is_what_counts(self) -> None:
        """A driver braking for a corner is braking for the tightest part of
        it, not for the gentle bit they meet first."""
        course = scenarios.chicane().course()
        found = [course.caution_ahead(index, 40.0)
                 for index in range(len(course.centreline) - 1)]
        least = min(one for one in found if one)
        assert least <= min(course.caution_speed(index)
                            for index in range(len(course.centreline))
                            if course.caution_speed(index))

    def test_looking_further_ahead_the_faster_it_goes(self) -> None:
        course = scenarios.sweeper(radius=90.0).course()
        slow = [course.caution_ahead(i, 10.0) for i in range(20)]
        quick = [course.caution_ahead(i, 50.0) for i in range(20)]
        assert sum(1 for one in quick if one) >= sum(1 for one in slow if one)


class TestTheEndOfAnOpenRoad:
    """A road that is not a circuit runs out, and what is past the end of it is
    nothing rather than its own beginning. Looking round the join is right for a
    lap and wrong for a stage: it advises a driver at the finish about the
    corner they left a kilometre back, and tells them the road they can see is
    the road behind them.
    """

    def test_the_corner_behind_is_not_a_corner_ahead(self) -> None:
        course = _stage()
        last = len(course.centreline) - 1
        assert course.caution_ahead(0, 30.0) > 0, 'the bend is at the start'
        assert course.caution_ahead(last, 30.0) == 0

    def test_and_a_circuit_still_reads_round_its_own_join(self) -> None:
        course = scenarios.circuit().course()
        assert course.closed
        found = [course.caution_ahead(index, 50.0)
                 for index in range(len(course.centreline))]
        assert any(found), 'a circuit that advises about nothing anywhere'

    def test_the_view_over_a_stretch_is_the_least_of_that_stretch(self) -> None:
        course = _stage()
        at, reach = 40, 300.0
        ahead = [course.sight_ahead(index)
                 for index in range(at, len(course.centreline))]
        assert course.sight_over(at, reach) >= min(ahead)
        assert course.sight_over(at, reach) <= course.sight_ahead(at)


class TestBeingToldAboutIt:
    def _session(self, scheme='lanes'):
        from glisteel import schemes
        session = Session(scenarios.sweeper(radius=90.0).world(traffic=0))
        session.driver = schemes.named(scheme)
        session.run.go()
        return session

    def test_a_run_says_how_fast_the_road_ahead_is_worth(self) -> None:
        assert self._session().readout().caution >= 0

    def test_a_driver_well_over_it_is_told(self) -> None:
        assert RaceHUD().over_caution(Readings(speed_kph=120.0, caution=60))

    def test_a_little_over_it_is_not(self) -> None:
        """A number on a plate is advice, and a HUD that shouts at a driver
        one km/h over it is a HUD they learn to ignore."""
        assert not RaceHUD().over_caution(Readings(speed_kph=68.0, caution=60))

    def test_and_under_it_is_not(self) -> None:
        assert not RaceHUD().over_caution(Readings(speed_kph=50.0, caution=60))

    def test_a_road_with_nothing_to_say_says_nothing(self) -> None:
        assert not RaceHUD().over_caution(Readings(speed_kph=200.0, caution=0))

    def test_the_warning_names_the_speed_to_be_doing(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=120.0, caution=60))
        assert '60' in hud.caution.value

    def test_and_goes_quiet_again(self) -> None:
        hud = RaceHUD()
        hud.show(Readings(speed_kph=120.0, caution=60))
        hud.show(Readings(speed_kph=50.0, caution=60))
        assert hud.caution.value == ''


class TestADriveWrittenDown:
    def test_a_script_drives_through_its_scheme_and_is_advised_like_one(self
                                                                       ) -> None:
        """What the harness measures is what a player gets, so a script driving
        under a way of driving that is advised is advised."""
        from glisteel.scripted import Script
        assert Script.parse('throttle 0..2', scheme='lanes').advises

    def test_and_one_that_is_not_is_not(self) -> None:
        from glisteel.scripted import Script
        assert not Script.parse('throttle 0..2', scheme='wheel').advises

    def test_a_scripted_drive_reads_the_road_ahead(self) -> None:
        from glisteel.scripted import Script
        session = Session(scenarios.sweeper(radius=90.0).world(traffic=0))
        session.driver = Script.parse('throttle 0..4', scheme='lanes')
        session.run.go()
        for _ in range(120):
            session.advance(1.0 / 120.0)
        assert session.readout().caution > 0


class TestWhichWaysOfDrivingAdvise:
    def test_the_lane_switch_tells_a_driver_to_slow_down(self) -> None:
        from glisteel import schemes
        assert schemes.named('lanes').advises

    def test_and_driving_it_yourself_does_not(self) -> None:
        from glisteel import schemes
        assert not schemes.named('wheel').advises

    def test_a_run_only_reads_the_road_for_a_driver_who_wants_it(self) -> None:
        from glisteel import schemes
        session = Session(scenarios.sweeper(radius=90.0).world(traffic=0))
        session.driver = schemes.named('wheel')
        session.advance(1.0 / 60.0)
        assert session.readout().caution == 0


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
