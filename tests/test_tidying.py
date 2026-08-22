"""Behaviour the P3 clean-up must not change, and the small things it fixes.

Most of the P3 list is naming, placement and dead code, and moving those must
leave the game doing exactly what it did. A handful are small defects in their
own right -- a parameter that is ignored, a lookup that answers about the wrong
one of two equal things, a shared object one caller can change for every other
-- and those have an answer worth asserting.
"""
import dataclasses

import numpy as np
import pytest

from glisteel import scenarios
from glisteel.camera import ChaseCamera
from glisteel.lighting import Headlights
from glisteel.race import ROUGH, TARMAC, VERGE, Collisions, OffRoad
from glisteel.records import Records
from glisteel.scripted import Script
from glisteel.session import Session
from glisteel.traffic import SPEED_LIMIT, TrafficCar
from glisteel.world import Course


def _course(points=80, radius=200.0, closed=True):
    angle = np.linspace(0.0, 2.0 * np.pi, points, endpoint=False)
    line = np.stack([np.cos(angle) * radius, np.zeros(points),
                     np.sin(angle) * radius], axis=-1)
    return Course(name='c', centreline=line, carriageway_width=7.2,
                  total_width=12.0, closed=closed,
                  length=float(2.0 * np.pi * radius))


class TestTheSpeedARoadIsDrivenAt:
    """A number nobody typed, with a name and a unit."""

    def test_it_is_the_open_road_limit(self) -> None:
        assert SPEED_LIMIT * 3.6 == pytest.approx(80.0, abs=0.5)

    def test_a_car_with_nothing_said_drives_it(self) -> None:
        from glisteel.traffic import Traffic
        assert Traffic(_course()).limit == pytest.approx(SPEED_LIMIT)


class TestWhyATrafficCarSlowedDown:
    def test_the_reason_is_kept(self) -> None:
        car = TrafficCar(_course(), station=0.0, heading=1, limit=25.0)
        car.brake_for('a tractor')
        assert car.reason == 'a tractor'

    def test_it_is_cleared_when_the_car_picks_up_again(self) -> None:
        from glisteel.traffic import CRUISING, SLOW_FOR
        car = TrafficCar(_course(), station=0.0, heading=1, limit=25.0)
        car.brake_for('a tractor')
        # Wound past the hold rather than driven there: a driver decides things
        # at random, and one that braked again would be a different answer to
        # the question being asked.
        car._elapsed += SLOW_FOR + 1.0
        car.advance(0.0)
        assert car.state == CRUISING
        assert car.reason == ''


class TestACarThatRunsOutOfRoad:
    """Turning round at the end is a thing a car does; finding out where it is
    is not the same question."""

    def test_it_turns_round_at_the_far_end(self) -> None:
        course = _course(closed=False)
        car = TrafficCar(course, station=course.length - 1.0, heading=1,
                         limit=30.0)
        car.turn_at_the_end(course.length + 50.0)
        assert car.heading == -1

    def test_it_turns_round_at_the_near_end(self) -> None:
        course = _course(closed=False)
        car = TrafficCar(course, station=1.0, heading=-1, limit=30.0)
        car.turn_at_the_end(-20.0)
        assert car.heading == 1

    def test_asking_where_a_station_falls_moves_nothing(self) -> None:
        course = _course(closed=False)
        car = TrafficCar(course, station=10.0, heading=1, limit=30.0)
        before = car.heading
        assert car.on_the_road(course.length + 100.0) == \
            pytest.approx(course.length)
        assert car.heading == before

    def test_a_circuit_wraps_instead(self) -> None:
        course = _course(closed=True)
        car = TrafficCar(course, station=0.0, heading=1, limit=30.0)
        assert car.on_the_road(course.length + 10.0) == pytest.approx(10.0)
        assert car.heading == 1


class TestWhatEachCarIsDrivingOn:
    """One car's surface is not every car's."""

    def test_the_shipped_surfaces_cannot_be_changed_under_everyone(self) -> None:
        for surface in (TARMAC, VERGE, ROUGH):
            with pytest.raises(dataclasses.FrozenInstanceError):
                surface.grip = 0.01

    def test_they_are_still_what_they_were(self) -> None:
        assert VERGE.grip < TARMAC.grip
        assert ROUGH.grip < VERGE.grip

    def test_a_watcher_still_answers_with_them(self) -> None:
        watch = OffRoad(_course())
        watch.update(_course().point(0), 0.1)
        assert watch.surface() is TARMAC


class TestTheCrashRuleTakesWhatItUses:
    def test_a_gentle_touch_is_survivable(self) -> None:
        assert Collisions().update(1.0) is None

    def test_meeting_something_hard_ends_the_run(self) -> None:
        assert Collisions().update(40.0) == 'HIT A CAR'

    def test_it_only_says_so_once(self) -> None:
        crashes = Collisions()
        crashes.update(40.0)
        assert crashes.update(40.0) is None


class TestWhereTheDriversEyeIs:
    def test_it_is_on_the_centreline_of_the_car(self) -> None:
        """The car seats two in single file, so there is no side to sit on."""
        class _Car:
            position = np.array([10.0, 1.0, -20.0])

            def forward(self):
                return np.array([1.0, 0.0, 0.0])

            def speed(self):
                return 0.0
        pose = ChaseCamera('cockpit').update(_Car(), 1.0 / 60.0)
        # Across the car is +Z here; the eye must not be off to either side.
        assert pose.position[2] == pytest.approx(-20.0)


class TestTheLightTheCarCarries:
    def test_it_is_described_by_its_fields(self) -> None:
        assert dataclasses.is_dataclass(Headlights)

    def test_one_can_be_given_a_different_beam(self) -> None:
        assert Headlights(reach=120.0).reach == pytest.approx(120.0)

    def test_the_defaults_are_untouched(self) -> None:
        assert Headlights().fitted and not Headlights().always


class TestAScriptedDrive:
    def test_it_presses_the_same_key_every_step(self) -> None:
        script = Script.parse('throttle 0..2')
        first = script.driver.held.copy()
        script.controls(None, 0.5)
        pressed = script.driver.held.copy()
        script.controls(None, 0.5)
        assert script.driver.held == pressed
        assert pressed != first


class TestOfferingALapThatTiesAnother:
    def test_the_second_of_two_equal_laps_is_placed_after_the_first(self) -> None:
        table = Records('/nonexistent/times.json')
        assert table.offer('ashdown', 84.115, when='2026-01-01') == 1
        assert table.offer('ashdown', 84.115, when='2026-01-01') == 2

    def test_the_table_holds_both(self) -> None:
        table = Records('/nonexistent/times.json')
        table.offer('ashdown', 84.115, when='2026-01-01')
        table.offer('ashdown', 84.115, when='2026-01-01')
        assert len(table.best('ashdown')) == 2


class TestStartingAFreshRace:
    def test_it_does_not_carry_the_last_races_leftover_time(self) -> None:
        session = Session(scenarios.straight().world())
        session.advance(0.007)               # less than one physics step
        assert session._accumulated > 0.0
        session.restart()
        assert session._accumulated == 0.0
