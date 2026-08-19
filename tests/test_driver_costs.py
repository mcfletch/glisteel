"""What the autopilot works out per frame, and what it works out once.

The road's curvature is fixed the moment a course is read: how tight the bend at
each point of it is cannot change while the car drives round it. Working it out
per frame means three points, three norms and a cross product for every point
within braking distance -- sixty-odd of them at speed -- for every driver on the
road, every frame.

Deciding where the car is on the road is the other one. ``update`` asked, and
then ``steering`` asked again about the same car in the same step.
"""
import numpy as np
import pytest

from glisteel.driver import Autopilot, DriverStyle
from glisteel.world import Course


def _circuit(points=400, radius=200.0):
    angle = np.linspace(0.0, 2.0 * np.pi, points, endpoint=False)
    line = np.stack([np.cos(angle) * radius, np.zeros(points),
                     np.sin(angle) * radius], axis=-1)
    return Course(name='circuit', centreline=line, carriageway_width=7.0,
                  total_width=12.0, closed=True,
                  length=float(2.0 * np.pi * radius))


class _Car:
    """A car that says where it is and how fast, and nothing else."""

    def __init__(self, course, index=0, speed=30.0):
        self.position = course.point(index)
        self._speed = speed
        self.vehicle = None

    def speed(self):
        return self._speed

    def forward(self):
        return np.array([0.0, 0.0, -1.0])


class TestTheRoadsShapeIsWorkedOutOnce:
    def test_the_radii_are_the_same_array_every_time(self) -> None:
        course = _circuit()
        assert course.radii is course.radii

    def test_a_circle_has_the_radius_it_has(self) -> None:
        course = _circuit(points=720, radius=200.0)
        assert course.radii[10] == pytest.approx(200.0, rel=1e-3)

    def test_a_straight_reads_as_an_enormous_radius(self) -> None:
        line = np.stack([np.zeros(50), np.zeros(50), np.linspace(0, 400, 50)],
                        axis=-1)
        course = Course(name='straight', centreline=line, carriageway_width=7.0,
                        total_width=12.0, closed=False, length=400.0)
        assert course.radii[10] > 1e5

    def test_it_agrees_with_asking_one_point_at_a_time(self) -> None:
        course = _circuit(points=180, radius=140.0)
        driver = Autopilot(course)
        for index in (0, 1, 37, 179):
            assert driver.curve_radius(index) == pytest.approx(
                float(course.radii[index % len(course.centreline)]), rel=1e-9)

    def test_moving_the_line_forgets_them(self) -> None:
        course = _circuit()
        was = course.radii
        course.moved()
        assert course.radii is not was


class TestWhatTheDriverAsksTheCourse:
    def test_one_decision_asks_where_the_car_is_once(self) -> None:
        course = _circuit()
        asked = []
        real = Course.nearest
        Course.nearest = lambda self, at: (asked.append(1), real(self, at))[1]
        try:
            Autopilot(course).update(_Car(course))
        finally:
            Course.nearest = real
        assert len(asked) == 1, 'asked %d times for one decision' % len(asked)

    def test_the_pedals_and_the_wheel_are_still_what_they_were(self) -> None:
        course = _circuit(radius=200.0)
        driver = Autopilot(course, style=DriverStyle(grip=0.95))
        throttle, brake, steer = driver.update(_Car(course, speed=20.0))
        assert 0.0 <= throttle <= 1.0
        assert 0.0 <= brake <= 1.0
        assert -1.0 <= steer <= 1.0

    def test_a_tight_circuit_is_taken_slower_than_a_wide_one(self) -> None:
        tight = Autopilot(_circuit(radius=60.0))
        wide = Autopilot(_circuit(radius=400.0))
        assert tight.target_speed(0, 30.0) < wide.target_speed(0, 30.0)

    def test_the_limit_is_the_tightest_bend_within_braking_distance(self) -> None:
        """A straight into a hairpin has to be slowed *on the straight*."""
        straight = np.stack([np.zeros(60), np.zeros(60),
                             np.linspace(300.0, 5.0, 60)], axis=-1)
        angle = np.linspace(0.0, np.pi, 20)
        bend = np.stack([25.0 * (1.0 - np.cos(angle)), np.zeros(20),
                         -25.0 * np.sin(angle)], axis=-1)
        line = np.vstack([straight, bend])
        course = Course(name='hairpin', centreline=line, carriageway_width=7.0,
                        total_width=12.0, closed=False,
                        length=float(np.linalg.norm(np.diff(line, axis=0),
                                                    axis=1).sum()))
        driver = Autopilot(course)
        # At 40 m/s the driver reads 126 m of road ahead. From the top of the
        # straight the bend is 300 m away and the road allows everything the car
        # has; twenty points from it, it does not.
        assert driver.target_speed(0, 40.0) == pytest.approx(
            driver.style.maximum_speed)
        assert driver.target_speed(45, 40.0) < driver.style.maximum_speed

    def test_it_reads_the_road_ahead_rather_than_the_road_underneath(self) -> None:
        # The same point of the same course, at two speeds: the faster car looks
        # further and finds the bend the slower one has not reached yet.
        straight = np.stack([np.zeros(40), np.zeros(40),
                             np.linspace(200.0, 5.0, 40)], axis=-1)
        angle = np.linspace(0.0, np.pi, 20)
        bend = np.stack([25.0 * (1.0 - np.cos(angle)), np.zeros(20),
                         -25.0 * np.sin(angle)], axis=-1)
        line = np.vstack([straight, bend])
        course = Course(name='hairpin', centreline=line, carriageway_width=7.0,
                        total_width=12.0, closed=False,
                        length=float(np.linalg.norm(np.diff(line, axis=0),
                                                    axis=1).sum()))
        driver = Autopilot(course)
        assert driver.target_speed(20, 45.0) <= driver.target_speed(20, 5.0)
