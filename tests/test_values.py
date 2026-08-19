"""The things that carry arrays, compared and put in collections.

A course, a recorded drive, a frame's readings and a scenario all hold numpy
arrays, and a dataclass compares itself by comparing its fields. Comparing two
arrays gives an array, and asking whether *that* is true raises -- so ``==`` on
any of these was a crash waiting for the first caller to write ``assert course
== expected``, ``if reading in seen`` or ``{scenario: ...}``.

What is asserted here is that each of them has an answer rather than an
exception. Which answer is the design decision: a course, a drive and a frame's
readings are *things*, and two of them are the same one only if they are the
same object; a scenario is a description, and two descriptions of the same piece
of road are the same description.
"""
import dataclasses

import numpy as np
import pytest

from glisteel import scenarios
from glisteel.session import Readings
from glisteel.trace import Trace
from glisteel.world import Course


def _course(**named):
    named.setdefault('name', 'circuit')
    named.setdefault('centreline', np.zeros((4, 3)))
    named.setdefault('carriageway_width', 7.0)
    named.setdefault('total_width', 12.0)
    named.setdefault('closed', True)
    named.setdefault('length', 400.0)
    return Course(**named)


def _trace():
    empty = np.zeros(3)
    return Trace(t=empty.copy(), position=np.zeros((3, 3)), speed=empty.copy(),
                 yaw=empty.copy(), throttle=empty.copy(), brake=empty.copy(),
                 steer=empty.copy(), wheel_angle=empty.copy(),
                 camera=np.zeros((3, 3)), camera_yaw=empty.copy(),
                 camera_pitch=empty.copy(), off_line=empty.copy(),
                 on_road=np.zeros(3, dtype=bool),
                 ended=np.zeros(3, dtype=object))


class TestComparingThemHasAnAnswer:
    """None of them raises when asked whether it equals another."""

    def test_two_courses(self) -> None:
        assert (_course() == _course()) in (True, False)

    def test_two_traces(self) -> None:
        assert (_trace() == _trace()) in (True, False)

    def test_two_readings(self) -> None:
        assert (Readings(at=np.zeros(3)) == Readings(at=np.zeros(3))) in (True, False)

    def test_two_scenarios(self) -> None:
        assert (scenarios.straight() == scenarios.straight()) in (True, False)

    def test_a_course_against_something_that_is_not_one(self) -> None:
        assert _course() != 'circuit'

    def test_looking_for_one_in_a_list(self) -> None:
        # ``in`` compares against every member, so it raised on the first miss.
        wanted, other = _course(), _course(name='other')
        assert wanted in [other, wanted]


class TestWhichOnesAreTheSameThing:
    def test_a_course_is_itself_and_no_other(self) -> None:
        one = _course()
        assert one == one
        assert one != _course()

    def test_a_recorded_drive_is_itself_and_no_other(self) -> None:
        one = _trace()
        assert one == one
        assert one != _trace()

    def test_a_frames_readings_are_their_own(self) -> None:
        one = Readings(at=np.zeros(3))
        assert one == one
        assert one != Readings(at=np.zeros(3))

    def test_two_descriptions_of_the_same_road_are_the_same_description(self) -> None:
        assert scenarios.straight() == scenarios.straight()
        assert scenarios.straight() != scenarios.chicane()
        assert scenarios.straight(length=400.0) != scenarios.straight(length=600.0)


class TestPuttingThemInCollections:
    def test_a_scenario_can_be_a_key(self) -> None:
        # A catalogue of pieces of road invites exactly this.
        found = {scenarios.straight(): 'a straight'}
        assert found[scenarios.straight()] == 'a straight'

    def test_a_course_can_go_in_a_set(self) -> None:
        one, other = _course(), _course(name='other')
        assert len({one, other, one}) == 2

    def test_a_scenario_is_still_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            scenarios.straight().name = 'something else'

    def test_the_same_land_asked_for_twice_is_the_same_land(self) -> None:
        # The relief is a function, so two scenarios describing one hillside
        # are the same description only if they were handed the same one.
        assert scenarios.crest() == scenarios.crest()
        assert scenarios.crest() != scenarios.dip()
        assert hash(scenarios.crest()) == hash(scenarios.crest())
