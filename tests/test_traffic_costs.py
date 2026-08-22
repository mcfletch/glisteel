"""What the traffic asks the course, and how the road behind a car is found.

Two things, on the same road, every frame. **Where the player is** was asked for
twice -- once for the station along the road and once for which side of the
centreline they are on -- and each answer is a pass over the whole centreline.
**What is in front of each car** was every car against every other, which is
fine for ten and is not what a road full of traffic means.

Nothing about the answers changes here; what changes is how many times the same
question is asked.
"""
import numpy as np
import pytest
import support

from glisteel.traffic import LOOK_AHEAD, Traffic, TrafficCar
from glisteel.world import Course


def _circuit(points=400, radius=300.0):
    return Course(name='circuit', centreline=support.ring(points, radius),
                  carriageway_width=7.2, total_width=12.0, closed=True,
                  length=float(2.0 * np.pi * radius))


def _traffic(course=None, count=8):
    return Traffic(course or _circuit(), count=count, seed=3)


class TestHowOftenTheCourseIsAsked:
    def test_a_frame_asks_where_the_player_is_once(self) -> None:
        traffic = _traffic()
        traffic.update(traffic.course.point(0), 0.0)
        with support.counting(Course, 'nearest') as asked:
            traffic.update(traffic.course.point(0), 1.0 / 60.0)
        assert len(asked) == 1, 'asked %d times in one frame' % len(asked)


class TestWhatIsInFrontIsStillWhatIsInFront:
    """The answers, against the rule stated in the module: the nearest car in
    front in the same direction, within the look-ahead, or nothing."""

    def _cars(self, course, stations, heading=1):
        return [TrafficCar(course, station=one, heading=heading, limit=25.0,
                           seed=index)
                for index, one in enumerate(stations)]

    def test_a_car_sees_the_one_just_in_front_of_it(self) -> None:
        course = _circuit()
        traffic = _traffic(course)
        traffic.cars = self._cars(course, [0.0, 40.0, 500.0])
        traffic._look_ahead(course.point(0) * 3.0, 0.0)
        assert traffic.cars[0].ahead is not None
        assert traffic.cars[0].ahead[0] == pytest.approx(40.0, abs=1e-6)

    def test_it_sees_the_nearest_rather_than_any(self) -> None:
        course = _circuit()
        traffic = _traffic(course)
        traffic.cars = self._cars(course, [0.0, 30.0, 60.0, 90.0])
        traffic._look_ahead(course.point(0) * 3.0, 0.0)
        assert traffic.cars[0].ahead[0] == pytest.approx(30.0, abs=1e-6)

    def test_the_car_in_front_has_an_open_road(self) -> None:
        course = _circuit()
        traffic = _traffic(course)
        traffic.cars = self._cars(course, [0.0, 30.0])
        traffic._look_ahead(course.point(0) * 3.0, 0.0)
        assert traffic.cars[1].ahead is None

    def test_something_beyond_the_look_ahead_is_not_seen(self) -> None:
        course = _circuit()
        traffic = _traffic(course)
        traffic.cars = self._cars(course, [0.0, LOOK_AHEAD + 50.0])
        traffic._look_ahead(course.point(0) * 3.0, 0.0)
        assert traffic.cars[0].ahead is None

    def test_a_car_coming_the_other_way_is_not_in_the_way(self) -> None:
        course = _circuit()
        traffic = _traffic(course)
        traffic.cars = (self._cars(course, [0.0]) +
                        self._cars(course, [40.0], heading=-1))
        traffic._look_ahead(course.point(0) * 3.0, 0.0)
        assert traffic.cars[0].ahead is None

    def test_it_carries_the_speed_of_whatever_is_in_front(self) -> None:
        course = _circuit()
        traffic = _traffic(course)
        traffic.cars = self._cars(course, [0.0, 40.0])
        traffic.cars[1].speed = 11.0
        traffic._look_ahead(course.point(0) * 3.0, 0.0)
        assert traffic.cars[0].ahead[1] == pytest.approx(11.0)

    def test_a_car_going_the_other_way_sees_the_one_in_front_of_it(self) -> None:
        course = _circuit()
        traffic = _traffic(course)
        traffic.cars = self._cars(course, [100.0, 60.0], heading=-1)
        traffic._look_ahead(course.point(0) * 3.0, 0.0)
        assert traffic.cars[0].ahead is not None
        assert traffic.cars[0].ahead[0] == pytest.approx(40.0, abs=1e-6)
