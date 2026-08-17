"""Driving a course without a player: does it steer the right way, and slow down?

The autopilot is tested twice over. First on its own, against a car it is told
about -- which way does it turn, when does it lift? Then for real: put a car on
a circuit, let the autopilot drive, and see whether it gets round.
"""

import math

import numpy as np
import pytest
from omi_physics.world import PhysicsWorld

from glisteel.car import Car
from glisteel.driver import Autopilot, DriverStyle
from glisteel.world import Course, static_ground

STEP = 1.0 / 120.0


def _oval(points=200, radius_x=140.0, radius_z=90.0, height=0.0):
    angle = np.linspace(0.0, 2 * math.pi, points, endpoint=False)
    line = np.stack([radius_x * np.cos(angle), np.full(points, height),
                     radius_z * np.sin(angle)], axis=-1)
    length = float(np.linalg.norm(np.diff(np.vstack([line, line[:1]]),
                                          axis=0), axis=1).sum())
    return Course(name='oval', centreline=line, carriageway_width=9.0,
                  total_width=18.0, closed=True, length=length)


def _straight(points=200, spacing=5.0):
    line = np.stack([np.zeros(points), np.zeros(points),
                     -np.arange(points) * spacing], axis=-1)
    return Course(name='straight', centreline=line, carriageway_width=9.0,
                  total_width=18.0, closed=False,
                  length=float((points - 1) * spacing))


class _Car:
    def __init__(self, position=(0, 0, 0), forward=(0, 0, -1), speed=0.0):
        self.position = np.asarray(position, dtype='d')
        self._forward = np.asarray(forward, dtype='d')
        self._speed = speed

    def forward(self):
        return self._forward

    def speed(self):
        return self._speed


class TestSteering:
    def test_pointed_down_the_road_it_holds_the_wheel_straight(self) -> None:
        course = _straight()
        pilot = Autopilot(course)
        _, _, steer = pilot.update(_Car(position=course.point(4), speed=20.0))
        assert abs(steer) < 0.02

    def test_pointed_left_of_the_road_it_steers_right(self) -> None:
        course = _straight()
        pilot = Autopilot(course)
        askew = _Car(position=course.point(4), forward=(-0.5, 0, -0.87),
                     speed=20.0)
        assert pilot.update(askew)[2] < -0.1

    def test_pointed_right_of_the_road_it_steers_left(self) -> None:
        course = _straight()
        pilot = Autopilot(course)
        askew = _Car(position=course.point(4), forward=(0.5, 0, -0.87),
                     speed=20.0)
        assert pilot.update(askew)[2] > 0.1

    def test_the_steering_is_within_range(self) -> None:
        course = _straight()
        pilot = Autopilot(course)
        backwards = _Car(position=course.point(4), forward=(0, 0, 1), speed=20.0)
        assert -1.0 <= pilot.update(backwards)[2] <= 1.0

    def test_it_looks_further_ahead_at_speed(self) -> None:
        """The aim point moves up the road as the car speeds up, or the car
        saws at the wheel."""
        course = _oval()
        pilot = Autopilot(course)
        near = pilot._aim_point(0, speed=0.0)
        far = pilot._aim_point(0, speed=50.0)
        origin = course.point(0)
        assert np.linalg.norm(far - origin) > np.linalg.norm(near - origin)


class TestReadingTheRoad:
    def test_a_straight_has_almost_no_curvature(self) -> None:
        assert Autopilot(_straight()).curve_radius(5) > 1e5

    def test_a_bend_reports_its_radius(self) -> None:
        course = _oval(radius_x=100.0, radius_z=100.0)
        assert Autopilot(course).curve_radius(10) == pytest.approx(100.0, rel=0.02)

    def test_a_tighter_bend_gets_a_lower_speed(self) -> None:
        wide = Autopilot(_oval(radius_x=300.0, radius_z=300.0))
        tight = Autopilot(_oval(radius_x=40.0, radius_z=40.0))
        assert tight.target_speed(0, 20.0) < wide.target_speed(0, 20.0)

    def test_the_top_speed_caps_a_straight(self) -> None:
        pilot = Autopilot(_straight(), DriverStyle(maximum_speed=30.0))
        assert pilot.target_speed(5, 10.0) == pytest.approx(30.0)

    def test_a_cautious_style_goes_slower_everywhere(self) -> None:
        course = _oval()
        brisk = Autopilot(course, DriverStyle(margin=1.0))
        careful = Autopilot(course, DriverStyle(margin=0.8))
        assert careful.target_speed(0, 20.0) < brisk.target_speed(0, 20.0)

    def test_it_brakes_for_a_corner_before_reaching_it(self) -> None:
        """A straight into a bend has to be slowed on the straight."""
        straight = np.stack([np.zeros(60), np.zeros(60),
                             -np.arange(60) * 5.0], axis=-1)
        angle = np.linspace(0, math.pi, 40)
        bend = np.stack([30.0 - 30.0 * np.cos(angle), np.zeros(40),
                         -295.0 - 30.0 * np.sin(angle)], axis=-1)
        line = np.vstack([straight, bend])
        course = Course(name='hairpin', centreline=line, carriageway_width=9.0,
                        total_width=18.0, closed=False, length=500.0)
        pilot = Autopilot(course)
        far_out = pilot.target_speed(5, 40.0)
        approaching = pilot.target_speed(50, 40.0)
        assert approaching < far_out


class TestThePedals:
    def test_below_the_target_it_accelerates(self) -> None:
        pilot = Autopilot(_straight())
        throttle, brake, _ = pilot.update(_Car(position=(0, 0, -20), speed=5.0))
        assert throttle > 0.5 and brake == 0.0

    def test_above_the_target_it_brakes(self) -> None:
        pilot = Autopilot(_oval(radius_x=40.0, radius_z=40.0))
        throttle, brake, _ = pilot.update(
            _Car(position=(40, 0, 0), forward=(0, 0, 1), speed=55.0))
        assert brake > 0.5 and throttle == 0.0

    def test_at_the_target_it_coasts(self) -> None:
        pilot = Autopilot(_straight(), DriverStyle(maximum_speed=25.0))
        throttle, brake, _ = pilot.update(_Car(position=(0, 0, -20), speed=25.0))
        assert throttle == pytest.approx(0.0) and brake == pytest.approx(0.0)


class TestItActuallyGetsRound:
    def test_it_drives_a_lap_of_a_flat_circuit(self) -> None:
        """The whole thing together: a real car, real physics, a real lap."""
        from glisteel.race import RaceTiming

        world = PhysicsWorld()
        static_ground(world, size=2000.0)
        course = _oval(radius_x=160.0, radius_z=110.0)
        start, heading = course.grid_position(height=1.0)
        car = Car(world, position=start, heading=heading)
        pilot = Autopilot(course)
        timing = RaceTiming(course)
        for _ in range(int(90.0 / STEP)):
            car.control(*pilot.update(car))
            car.update(STEP)
            world.step(STEP)
            timing.update(car.position, STEP)
            if timing.laps:
                break
        assert timing.laps, "the autopilot did not complete a lap in 90 seconds"
        assert timing.laps[0].seconds < 90.0

    def test_it_stays_on_the_road_while_it_does(self) -> None:
        world = PhysicsWorld()
        static_ground(world, size=2000.0)
        course = _oval(radius_x=160.0, radius_z=110.0)
        start, heading = course.grid_position(height=1.0)
        car = Car(world, position=start, heading=heading)
        pilot = Autopilot(course)
        worst = 0.0
        for _ in range(int(40.0 / STEP)):
            car.control(*pilot.update(car))
            car.update(STEP)
            world.step(STEP)
            worst = max(worst, course.nearest(car.position)[1])
        assert worst < course.total_width, (
            "wandered %.1f m from the centreline" % worst)
