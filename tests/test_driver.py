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


class TestItGetsOverTheHills:
    """A circuit is not flat, and the interesting question a hilly one asks is
    not about steering: it is whether the car stays on the road over a crest.

    A car that leaves the ground has no grip and no drive, so it goes where it
    was pointed when it left rather than where the road goes. What keeps its
    wheels down is the road being built with vertical curves long enough for the
    speed it is driven at (``OpenGLContext_editor``'s ``design_speed``), so the
    course here is built to exactly that limit and driven at exactly that speed.
    """

    #: How much of the car's weight a crest may take off the wheels, and the
    #: speed the course is built for -- the shipped circuit's figures.
    WEIGHT_LOSS = 0.25
    DESIGN_SPEED = 47.0
    GRAVITY = 9.81

    def _relief(self, x, z):
        """Rolling ground whose crests are at the design limit and no sharper."""
        radius = self.DESIGN_SPEED ** 2 / (self.GRAVITY * self.WEIGHT_LOSS)
        wavelength = 260.0
        k = 2 * math.pi / wavelength
        # A sine of curvature k^2 * a has its sharpest crest at the peak.
        amplitude = 1.0 / (k * k * radius)
        return amplitude * np.sin(k * np.asarray(x, 'd'))

    def _course(self, points=240, radius_x=300.0, radius_z=200.0):
        angle = np.linspace(0.0, 2 * math.pi, points, endpoint=False)
        x = radius_x * np.cos(angle)
        z = radius_z * np.sin(angle)
        line = np.stack([x, self._relief(x, z), z], axis=-1)
        length = float(np.linalg.norm(np.diff(np.vstack([line, line[:1]]),
                                              axis=0), axis=1).sum())
        return Course(name='hills', centreline=line, carriageway_width=9.0,
                      total_width=18.0, closed=True, length=length)

    def _ground(self, world, extent=420.0, resolution=121):
        """The same relief as a triangle mesh, which is what the car drives on."""
        from omi_physics import model
        axis = np.linspace(-extent, extent, resolution)
        gx, gz = np.meshgrid(axis, axis, indexing='ij')
        points = np.stack([gx.ravel(), self._relief(gx, gz).ravel(),
                           gz.ravel()], axis=-1)
        faces = []
        for i in range(resolution - 1):
            for j in range(resolution - 1):
                a = i * resolution + j
                faces += [(a, a + 1, a + resolution),
                          (a + 1, a + resolution + 1, a + resolution)]
        shape = world.add_shape(
            model.Shape.trimesh(points, np.asarray(faces, dtype='i')))
        world.add_body(model.Motion(type=model.STATIC),
                       collider=model.Collider(shape=shape))

    def _drive(self, seconds=150.0):
        from glisteel.race import RaceTiming
        world = PhysicsWorld()
        self._ground(world)
        course = self._course()
        start, heading = course.grid_position(height=1.0)
        car = Car(world, position=start, heading=heading)
        pilot = Autopilot(course, DriverStyle(maximum_speed=self.DESIGN_SPEED))
        timing = RaceTiming(course)
        worst = 0.0
        for _ in range(int(seconds / STEP)):
            car.control(*pilot.update(car))
            car.update(STEP)
            world.step(STEP)
            timing.update(car.position, STEP)
            worst = max(worst, float(course.nearest(car.position)[1]))
            if timing.laps:
                break
        return timing, worst

    def test_it_completes_a_lap_over_the_crests(self) -> None:
        timing, _worst = self._drive()
        assert timing.laps, "the autopilot did not get round the hilly circuit"

    def test_it_stays_on_the_road_over_them(self) -> None:
        _timing, worst = self._drive()
        assert worst < 18.0, "wandered %.1f m from the centreline" % worst


class TestHoldingTheLine:
    """Pure pursuit alone *cuts* a corner: aiming at a point L up the road on a
    bend of radius R leaves the car about L squared over 2R inside the line, and
    on a narrow road that is the width of the carriageway. So the driver also
    corrects the error it can see under itself."""

    def _lap(self, course, style=None, seconds=45.0):
        world = PhysicsWorld()
        static_ground(world, size=3000.0)
        start, heading = course.grid_position(height=1.0)
        car = Car(world, position=start, heading=heading)
        pilot = Autopilot(course, style)
        worst = 0.0
        for step in range(int(seconds / STEP)):
            car.control(*pilot.update(car))
            car.update(STEP)
            world.step(STEP)
            if step * STEP > 3.0:                # once it is up to speed
                worst = max(worst, course.nearest(car.position)[1])
        return worst

    def test_it_holds_a_narrow_lane_round_a_bend(self) -> None:
        course = _oval(radius_x=200.0, radius_z=150.0)
        assert self._lap(course) < 3.0

    def test_correcting_the_error_is_what_does_it(self) -> None:
        course = _oval(radius_x=200.0, radius_z=150.0)
        loose = DriverStyle(tracking=0.0)
        assert self._lap(course, loose) > self._lap(course)

    def test_it_is_steady_on_a_straight(self) -> None:
        """A correction hard enough to hold a bend must not saw at the wheel."""
        course = _straight(points=400, spacing=5.0)
        assert self._lap(course, seconds=25.0) < 1.0

    def test_a_car_put_off_the_line_comes_back_to_it(self) -> None:
        world = PhysicsWorld()
        static_ground(world, size=3000.0)
        course = _straight(points=400, spacing=5.0)
        start, heading = course.grid_position(height=1.0)
        car = Car(world, position=start + np.array([6.0, 0.0, 0.0]),
                  heading=heading)
        pilot = Autopilot(course)
        for _ in range(int(12.0 / STEP)):
            car.control(*pilot.update(car))
            car.update(STEP)
            world.step(STEP)
        assert course.nearest(car.position)[1] < 2.0


class TestTheCrossTrackTerm:
    def test_a_car_to_the_left_of_the_line_steers_right(self) -> None:
        course = _straight()
        pilot = Autopilot(course)
        left = _Car(position=(-4.0, 0.0, -50.0), forward=(0, 0, -1), speed=20.0)
        assert pilot.update(left)[2] < 0.0

    def test_a_car_to_the_right_of_the_line_steers_left(self) -> None:
        course = _straight()
        pilot = Autopilot(course)
        right = _Car(position=(4.0, 0.0, -50.0), forward=(0, 0, -1), speed=20.0)
        assert pilot.update(right)[2] > 0.0

    def test_a_car_on_the_line_is_unmoved_by_it(self) -> None:
        course = _straight()
        pilot = Autopilot(course)
        on = _Car(position=(0.0, 0.0, -50.0), forward=(0, 0, -1), speed=20.0)
        assert pilot.update(on)[2] == pytest.approx(0.0, abs=1e-6)

    def test_the_correction_softens_with_speed(self) -> None:
        """The same metres off the line is a smaller angle the faster you are
        going, or a correction that settles at 20 m/s oscillates at 50."""
        course = _straight()
        pilot = Autopilot(course, DriverStyle(steering_gain=0.0))
        slow = _Car(position=(3.0, 0, -50.0), forward=(0, 0, -1), speed=10.0)
        fast = _Car(position=(3.0, 0, -50.0), forward=(0, 0, -1), speed=45.0)
        assert abs(pilot.update(slow)[2]) > abs(pilot.update(fast)[2])

    def test_turning_it_off_leaves_pure_pursuit(self) -> None:
        course = _straight()
        off = Autopilot(course, DriverStyle(tracking=0.0))
        beside = _Car(position=(4.0, 0.0, -50.0), forward=(0, 0, -1), speed=20.0)
        assert off.update(beside)[2] == pytest.approx(
            Autopilot(course, DriverStyle(tracking=0.0)).update(beside)[2])


class TestDrivingOnItsOwnSide:
    """On an empty circuit the racing line is the centreline. With something
    coming the other way it is not: a driver keeps a side, and the autopilot has
    to do the same or it meets the traffic head-on."""

    def _course(self, count=241, radius=300.0):
        from glisteel.world import Course
        angle = np.linspace(0.0, 2.0 * np.pi, count)
        line = np.stack([np.cos(angle) * radius, np.zeros(count),
                         np.sin(angle) * radius], axis=-1)
        steps = np.linalg.norm(np.diff(line, axis=0), axis=1)
        return Course(name='ring', centreline=line, carriageway_width=7.2,
                      total_width=10.6, closed=True, length=float(steps.sum()))

    def test_by_default_it_drives_the_centreline(self) -> None:
        from glisteel.driver import Autopilot
        assert Autopilot(self._course()).lane == 0.0

    def test_it_can_be_told_to_keep_a_side(self) -> None:
        from glisteel.driver import Autopilot
        course = self._course()
        driver = Autopilot(course, lane=course.driving_lane)
        assert driver.lane == course.driving_lane

    def test_and_then_the_line_it_aims_at_is_over_there(self) -> None:
        from glisteel.driver import Autopilot
        course = self._course()
        middle = Autopilot(course)
        side = Autopilot(course, lane=course.driving_lane)
        assert not np.allclose(middle.line_at(10), side.line_at(10))
        assert float(np.linalg.norm(side.line_at(10) - middle.line_at(10))) \
            == pytest.approx(course.driving_lane, abs=0.01)

    def test_a_car_on_its_lane_is_not_corrected_back(self) -> None:
        """The cross-track term measures against the line being driven, so a
        car sitting on it is where it should be."""
        from glisteel.driver import Autopilot
        course = self._course()
        driver = Autopilot(course, lane=course.driving_lane)
        at = course.lane_point(10, course.driving_lane)
        forward = _along(course, 10)
        assert abs(driver._back_to_the_line(_Car(forward=forward), at, 10,
                                            20.0)) < 0.02

    def test_and_a_car_on_the_centreline_is_pulled_onto_it(self) -> None:
        from glisteel.driver import Autopilot
        course = self._course()
        driver = Autopilot(course, lane=course.driving_lane)
        forward = _along(course, 10)
        middle = driver._back_to_the_line(_Car(forward=forward),
                                          course.point(10), 10, 20.0)
        assert abs(middle) > 0.05
        # Towards its own side, which is the way a positive lane offset lies.
        beyond = course.lane_point(10, course.driving_lane * 2.0)
        past = driver._back_to_the_line(_Car(forward=forward), beyond, 10, 20.0)
        assert float(np.sign(middle)) == -float(np.sign(past))


def _along(course, index):
    """Which way the road runs there, as a unit vector."""
    ahead = course.point(index + 1) - course.point(index)
    ahead[1] = 0.0
    return ahead / np.linalg.norm(ahead)


class TestDrivingBehindSomething:
    """An autopilot that knows the corners and not the traffic drives into the
    back of the first car it catches. What it needs is the same rule the traffic
    uses on itself: the speed it could still stop from in the room it has."""

    def _course(self, count=241, radius=300.0):
        from glisteel.world import Course
        angle = np.linspace(0.0, 2.0 * np.pi, count)
        line = np.stack([np.cos(angle) * radius, np.zeros(count),
                         np.sin(angle) * radius], axis=-1)
        steps = np.linalg.norm(np.diff(line, axis=0), axis=1)
        return Course(name='ring', centreline=line, carriageway_width=7.2,
                      total_width=10.6, closed=True, length=float(steps.sum()))

    def test_an_open_road_is_the_speed_the_corner_allows(self) -> None:
        driver = Autopilot(self._course())
        alone = driver.target_speed(10, 30.0)
        driver.following(gap=None, speed=0.0)
        assert driver.target_speed(10, 30.0) == pytest.approx(alone)

    def test_something_far_ahead_changes_nothing(self) -> None:
        driver = Autopilot(self._course())
        alone = driver.target_speed(10, 30.0)
        driver.following(gap=250.0, speed=28.0)
        assert driver.target_speed(10, 30.0) == pytest.approx(alone)

    def test_something_slower_close_ahead_holds_it_back(self) -> None:
        driver = Autopilot(self._course())
        alone = driver.target_speed(10, 30.0)
        driver.following(gap=25.0, speed=12.0)
        assert driver.target_speed(10, 30.0) < alone

    def test_something_stopped_in_the_way_stops_it(self) -> None:
        driver = Autopilot(self._course())
        driver.following(gap=5.0, speed=0.0)
        assert driver.target_speed(10, 30.0) == pytest.approx(0.0, abs=0.5)

    def test_and_it_brakes_for_it(self) -> None:
        course = self._course()
        driver = Autopilot(course)
        driver.following(gap=8.0, speed=0.0)
        car = _Car(position=course.point(10), forward=(0, 0, -1), speed=30.0)
        _throttle, brake, _steer = driver.update(car)
        assert brake > 0.5
