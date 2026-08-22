"""What a course works out once, and what it works out again every time.

A course is read from a baked world and never changes after that: its points,
the distance along it to each of them, and the segments between them are settled
the moment it is built. Several things ask about the same car in the same frame
-- the lap timing, the off-road watch, what the car reflects, the traffic, and
whoever is driving -- so anything recomputed per question is recomputed a dozen
times a frame for an answer that cannot have changed.

What is asserted here is that the derived arrays are worked out once. The
numbers behind it are in ``plans/2026-08-19-CODE-REVIEW.md`` section 3.
"""
import numpy as np
import pytest
import support

from glisteel.world import Course


def _course(points=400, closed=True):
    return Course(name='circuit',
                  centreline=support.ring(points, radius=500.0, radius_z=300.0),
                  carriageway_width=7.0, total_width=12.0, closed=closed,
                  length=2500.0)


class TestWhatIsWorkedOutOnce:
    def test_the_stations_are_the_same_array_every_time(self) -> None:
        course = _course()
        assert course.stations is course.stations

    def test_the_segments_are_the_same_arrays_every_time(self) -> None:
        course = _course()
        assert course.segments is course.segments

    def test_a_second_course_gets_its_own(self) -> None:
        one, other = _course(), _course()
        assert one.stations is not other.stations


class TestTheAnswersAreStillRight:
    """Caching must not change what a course says about anything."""

    def test_the_stations_are_the_distance_along_the_line(self) -> None:
        course = _course(points=5, closed=False)
        steps = np.linalg.norm(np.diff(course.centreline, axis=0), axis=1)
        assert np.allclose(course.stations,
                           np.concatenate([[0.0], np.cumsum(steps)]))

    def test_a_point_on_the_line_is_on_the_line(self) -> None:
        course = _course()
        on_it = course.centreline[7]
        index, off = course.nearest(on_it)
        assert index == 7
        assert off == pytest.approx(0.0, abs=1e-9)

    def test_a_point_beside_the_line_is_measured_to_the_road(self) -> None:
        course = _course()
        # Half way between two written points, three metres to one side: on the
        # line as far as the road goes, and not four metres off it.
        middle = (course.centreline[7] + course.centreline[8]) / 2.0
        _index, off = course.nearest(middle + np.array([0.0, 0.0, 0.0]))
        assert off < 0.5

    def test_an_open_course_is_measured_the_same_way(self) -> None:
        course = _course(closed=False)
        index, off = course.nearest(course.centreline[3])
        assert index == 3
        assert off == pytest.approx(0.0, abs=1e-9)

    def test_the_answer_does_not_drift_when_it_is_asked_repeatedly(self) -> None:
        course = _course()
        first = course.nearest(course.centreline[11])
        for _ in range(20):
            assert course.nearest(course.centreline[11]) == first


class TestARoadThatIsMovedSaysSo:
    """The cache is only sound because a course does not change under it."""

    def test_replacing_the_line_can_be_declared(self) -> None:
        course = _course()
        before = course.stations[-1]
        course.centreline = course.centreline * 2.0
        course.moved()
        assert course.stations[-1] == pytest.approx(before * 2.0)

    def test_the_segments_are_rebuilt_too(self) -> None:
        course = _course()
        was = course.segments
        course.moved()
        assert course.segments is not was

    def test_everything_worked_out_from_the_line_is_forgotten(self) -> None:
        """Every cache the line feeds, not the handful that were there when the
        method was written: one left behind is a road answering about the shape
        it used to be, which is worse than no cache at all."""
        course = _course()
        derived = ('stations', 'segments', 'ground_line', 'radii', '_section',
                   'start_index', '_spacing', '_clear', '_sight',
                   'caution_speeds')
        for name in derived:
            getattr(course, name)
        course.moved()
        held = [name for name in derived if name in course.__dict__]
        assert not held, 'kept %s across a moved line' % ', '.join(held)


class TestAskingTwiceAboutTheSamePlace:
    """Several things ask where the same car is, in the same step.

    The lap timing, the off-road watch, whoever is driving and the steering aid
    all want the nearest point of the road to one car, and the car does not move
    between them. Working it out again for each is a pass over the whole
    centreline for an answer that is already known.
    """

    def test_the_same_position_is_only_worked_out_once(self) -> None:
        course = _course()
        at = course.centreline[13] + np.array([0.0, 1.0, 2.0])
        first = course.nearest(at)
        with support.counting(np.linalg, 'norm') as worked:
            again = course.nearest(at)
        assert again == first
        assert not worked, 'worked it out again for a position already asked'

    def test_a_different_position_is_worked_out(self) -> None:
        course = _course()
        one = course.nearest(course.centreline[3])
        other = course.nearest(course.centreline[40])
        assert one != other

    def test_going_back_and_forth_is_still_right(self) -> None:
        course = _course()
        for _ in range(5):
            assert course.nearest(course.centreline[3])[0] == 3
            assert course.nearest(course.centreline[40])[0] == 40

    def test_a_list_and_an_array_of_the_same_place_agree(self) -> None:
        course = _course()
        point = course.centreline[9]
        assert course.nearest(point) == course.nearest(list(point))

    def test_moving_the_line_forgets_the_answer(self) -> None:
        course = _course()
        at = course.centreline[13]
        before = course.nearest(at)
        course.centreline = course.centreline * 3.0
        course.moved()
        assert course.nearest(at) != before
