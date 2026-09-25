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
from glisteel.driver import (
    ALONGSIDE,
    PASSED_BY,
    REASON_HOLDS,
    REJOIN_SPEED,
    Autopilot,
    DriverStyle,
)
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
    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
    def test_it_completes_a_lap_over_the_crests(self) -> None:
        timing, _worst = self._drive()
        assert timing.laps, "the autopilot did not get round the hilly circuit"

    @pytest.mark.slow
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

    @pytest.mark.slow
    def test_it_holds_a_narrow_lane_round_a_bend(self) -> None:
        course = _oval(radius_x=200.0, radius_z=150.0)
        assert self._lap(course) < 3.0

    @pytest.mark.slow
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
        assert not car.upside_down(), 'it came back on its roof'
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


class TestHowFarBackItSits:
    """A following distance is a *time*, not a length of road.

    Seven metres off a bumper is comfortable at a crawl and a third of a second
    at speed -- too close to do anything about the car in front braking, and too
    close to see past it. So the gap the autopilot keeps grows with the speed it
    is doing, which is the rule :class:`~glisteel.driver.StandIn` already drove
    by and the rule the traffic keeps on itself.
    """

    def _settled(self, lead_speed, seconds=70.0):
        """How far back it settles behind a car going at a steady speed."""
        course = _straight(points=1200, spacing=5.0)
        world = PhysicsWorld()
        static_ground(world, size=8000.0)
        start, heading = course.grid_position(height=1.0)
        car = Car(world, position=start, heading=heading)
        pilot = Autopilot(course)
        gap = 260.0
        for _ in range(int(seconds / STEP)):
            gap = gap + (lead_speed - car.speed()) * STEP
            pilot.following(gap, lead_speed)
            car.control(*pilot.update(car))
            car.update(STEP)
            world.step(STEP)
        return gap, car.speed()

    def test_at_speed_it_sits_a_couple_of_seconds_back(self) -> None:
        from glisteel.driver import FOLLOWING_SECONDS
        gap, speed = self._settled(28.0)
        assert speed == pytest.approx(28.0, abs=3.0)
        assert gap > FOLLOWING_SECONDS * speed * 0.7

    def test_which_is_much_further_than_a_car_length(self) -> None:
        gap, _speed = self._settled(28.0)
        assert gap > 25.0, "sat %.1f m off a bumper at a hundred km/h" % gap

    def test_behind_something_slow_it_closes_up(self) -> None:
        """A time gap at a crawl is a couple of car lengths, not a hundred
        metres: a driver in a queue does not leave the road open."""
        from glisteel.driver import FOLLOWING_LEAST
        gap, _speed = self._settled(4.0)
        assert gap < FOLLOWING_LEAST * 1.6

    def test_it_is_never_closer_than_a_standing_gap(self) -> None:
        gap, _speed = self._settled(0.0)
        assert gap > DriverStyle().standing_gap * 0.8


class _Ahead:
    """A car in front, as a session tells a driver about one."""

    def __init__(self, gap, speed, clear=True):
        self.gap = float(gap)
        self.speed = float(speed)
        self.clear = clear


class _Road:
    """The bit of a session a driver asks about traffic and lanes."""

    def __init__(self, car, ahead=None, clear=True, lane=1.8, own_lane=None):
        self.car = car
        self._ahead = ahead
        #: What is up the car's *own* lane, where that is a different thing
        #: from what it is following -- which it is once a pass is past the car
        #: it pulled out for.
        self._own_lane = own_lane
        self._clear = clear
        #: Whether a passing lane beside this car's own can be moved into.
        self.beside_clear = True
        self.lane = lane
        self.asked: list = []

    def _within(self, reach):
        """What a session answers about the lane the car is *in*.

        From the car's own position, as `Session.traffic_ahead` does: a car out
        in the oncoming lane is not following what is in the lane it left. One
        answer for wherever the car happened to be said a driver crossing back
        was already braking for what it was crossing towards, which is the
        case that wanted testing.
        """
        if self._ahead is None or self._ahead.gap > float(reach):
            return None
        return self._ahead if self.car.position[0] * self.lane > 0.0 else None

    def traffic_ahead(self, reach=140.0):
        found = self._within(reach)
        return None if found is None else (found.gap, found.speed)

    def car_ahead(self, reach=140.0):
        return self._within(reach)

    def lane_clear(self, across, ahead=24.0, behind=14.0):
        """Whether that lane can be moved into.

        ``_clear`` is about the lane being *pulled out into*; the car's own
        side answers for itself, from where the car it is passing has got to.
        One flag for both lanes said a driver giving up a pass could always
        come back, whatever was beside it -- which is exactly the case that
        wanted testing.
        """
        self.asked.append(across)
        if self._is_own(across):                 # the lane it started in
            beside = self._ahead
            if beside is None:
                return True
            return not (-float(behind) <= beside.gap <= float(ahead))
        if across * self.lane > 0.0:             # a passing lane beside it
            return self.beside_clear
        return self._clear

    def _is_own(self, across):
        """Whether that offset names the lane this car drives in.

        By where it is across the road, not by which side of the crown it is
        on: a climbing lane is on the car's own side and is not its lane, and
        a double that cannot tell the two apart says a car being passed is
        parked in the lane being passed in.
        """
        return abs(float(across) - self.lane) < 1.2

    def lane_ahead(self, across, reach=140.0):
        """What is up the lane *named*, wherever the car itself happens to be.

        Which is the whole difference from :meth:`traffic_ahead`: that one
        answers about the lane the car is in, and this one about a lane it is
        asking after. The car's own side holds whatever it is following; the
        far side is empty unless a test says otherwise.
        """
        found = self._own_lane if self._own_lane is not None else self._ahead
        if not self._is_own(across) or found is None:
            return None
        if not 0.0 <= found.gap <= float(reach):
            return None                          # behind is not ahead
        return (found.gap, found.speed)

    def along(self, other):
        return other.gap


class TestGettingPastSomethingSlower:
    """A driver that only ever follows spends the lap behind the first slow
    thing it meets. What decides a pass is the driver's -- whether the road
    ahead is worth having and whether there is room -- and it is the same
    decision whichever way the car is being steered.
    """

    def _pilot(self, lane=1.8):
        return Autopilot(_straight(points=400, spacing=5.0), lane=lane)

    def _car(self, speed=40.0):
        return _Car(position=(1.8, 0.0, -100.0), speed=speed)

    def test_it_pulls_out_for_something_much_slower(self) -> None:
        pilot = self._pilot()
        road = _Road(self._car(40.0), ahead=_Ahead(40.0, 18.0))
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8)
        assert pilot.passing is not None

    def test_it_asks_whether_the_other_lane_is_clear_first(self) -> None:
        pilot = self._pilot()
        road = _Road(self._car(40.0), ahead=_Ahead(40.0, 18.0), clear=False)
        pilot.controls(road, 1 / 60)
        assert road.asked == [-1.8]
        assert pilot.lane == pytest.approx(1.8), 'pulled out into a busy lane'

    def test_it_stays_in_for_something_going_the_speed_the_road_allows(self) -> None:
        """Nothing to gain: what a pass is worth is measured against the speed
        the road would let this car do, not against what it is doing now."""
        pilot = self._pilot()
        road = _Road(self._car(40.0),
                     ahead=_Ahead(40.0, DriverStyle().maximum_speed - 1.0))
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(1.8)

    def test_the_room_it_asks_for_is_the_speed_it_will_be_doing(self) -> None:
        """Crawling behind a stopped queue, a pass sized on the current speed
        asks for forty metres and then takes four hundred."""
        pilot = self._pilot()
        crawling = _Road(_Car(position=(1.8, 0.0, -100.0), speed=3.0),
                         ahead=_Ahead(9.0, 0.0))
        pilot.controls(crawling, 1 / 60)
        assert crawling.asked, 'never considered the other lane'
        asked = crawling.asked[0]
        assert pilot.lane == pytest.approx(-1.8)
        # Sized on the road's speed, not on three metres a second.
        assert pilot._pass_room(crawling, 3.0,
                                DriverStyle().maximum_speed,
                                crawling._ahead) > 300.0
        assert asked == pytest.approx(-1.8)

    def test_it_passes_a_car_it_has_settled_in_behind(self) -> None:
        """The case every other test here misses, and the one a lap is made of.

        A driver keeps a time gap, so within a few seconds of catching
        something it is doing exactly what that thing is doing -- and a pass
        that may only start while *already* gaining can then never start at
        all. Watched on a recorded lap: the car pulled up behind one van and
        drove the rest of the circuit at its speed.
        """
        pilot = self._pilot()
        matched = _Road(self._car(18.0), ahead=_Ahead(40.0, 18.0))
        pilot.controls(matched, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8), 'sat behind it for ever'
        assert pilot.passing is not None

    def test_and_sizes_that_pass_on_more_than_the_speed_it_is_doing(self
                                                                   ) -> None:
        """Matched, the difference between the two cars is nought, and a pass
        measured on that is a pass of infinite length."""
        pilot = self._pilot()
        matched = _Road(self._car(18.0), ahead=_Ahead(40.0, 18.0))
        room = pilot._pass_room(matched, 18.0, DriverStyle().maximum_speed,
                                matched._ahead)
        assert room is not None and room > 0.0

    def test_but_not_on_a_speed_it_cannot_reach_yet(self) -> None:
        """The other half of the trade. A pass is run at neither the speed the
        car is doing nor the one the road allows, but at what it averages
        getting from one to the other -- so crawling behind a stopped queue
        still asks for a lot of road rather than a little.

        A third more than the same pass taken at speed, which is how much
        longer winding up to it takes.
        """
        pilot = self._pilot()
        crawling = _Road(_Car(position=(1.8, 0.0, -100.0), speed=3.0),
                         ahead=_Ahead(9.0, 0.0))
        top = DriverStyle().maximum_speed
        crawl = pilot._pass_room(crawling, 3.0, top, crawling._ahead)
        flying = pilot._pass_room(crawling, top, top, crawling._ahead)
        assert crawl > flying * 1.25, 'sized as though it were already up to speed'

    def test_it_gives_the_pass_up_if_the_way_through_closes(self) -> None:
        """Being on the wrong side of a road is the one place not to wait and
        see -- so the pass is over at once, whatever the car does next."""
        pilot = self._pilot()
        slow = _Ahead(40.0, 18.0)
        road = _Road(self._car(40.0), ahead=slow)
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8)
        road._clear = False
        pilot.controls(road, 1 / 60)
        assert pilot.passing is None

    def test_and_comes_back_at_once_rather_than_waiting_for_room(self) -> None:
        """Even into a lane it will arrive in too fast.

        Measured both ways on the 7.2 km circuit: made to wait for road enough
        to shed its speed into, the driver stayed in the oncoming lane 3.4 s
        and met a car head-on at 44.8 m/s of closing speed; coming back at once
        cost a same-direction contact at 10.3. There is nothing on a two-way
        road worse than being on the wrong side of it, so how fast it arrives
        is the brakes' problem and not this decision's.
        """
        pilot = self._pilot()
        slow = _Ahead(40.0, 18.0)                # too near to slot in behind
        road = _Road(self._car(40.0), ahead=slow)
        pilot.controls(road, 1 / 60)
        road._clear = False
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(1.8), 'stayed out on the wrong side'

    def test_it_stays_in_for_something_a_long_way_off(self) -> None:
        pilot = self._pilot()
        road = _Road(self._car(40.0), ahead=_Ahead(300.0, 10.0))
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(1.8)

    def test_it_comes_back_in_once_it_is_past(self) -> None:
        pilot = self._pilot()
        slow = _Ahead(40.0, 18.0)
        road = _Road(self._car(40.0), ahead=slow)
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8)
        slow.gap = -30.0                         # it is behind now
        road._ahead = None
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(1.8)
        assert pilot.passing is None

    def test_it_stays_out_until_it_actually_is_past(self) -> None:
        pilot = self._pilot()
        slow = _Ahead(40.0, 18.0)
        road = _Road(self._car(40.0), ahead=slow)
        pilot.controls(road, 1 / 60)
        slow.gap = 3.0                           # alongside, not past
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8)

    def test_a_driver_on_the_racing_line_has_no_lane_to_leave(self) -> None:
        """An empty circuit is driven on the crown, and there is no other side
        of the road to pull out into."""
        pilot = self._pilot(lane=0.0)
        road = _Road(self._car(40.0), ahead=_Ahead(40.0, 18.0), lane=0.0)
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(0.0)
        assert road.asked == []


class TestGettingBackOnTheRoad:
    """A driver with a wheel off the carriageway slows down and comes back.

    Nothing in pure pursuit says so: it steers at a point up the road and holds
    whatever speed the road allows, so a car knocked off its line drives on at
    road speed in whatever direction it is pointing -- which off a carriageway
    is into the trees, and what it ends as is a car nobody can recover.
    """

    def _pilot(self):
        return Autopilot(_straight(points=400, spacing=5.0))

    def _target(self, across):
        pilot = self._pilot()
        course = pilot.course
        at = course.lane_point(20, across)
        car = _Car(position=at, forward=(0, 0, -1), speed=30.0)
        return pilot.update(car), course.nearest(at)[1]

    def test_on_the_carriageway_it_drives_the_road(self) -> None:
        (throttle, brake, _steer), off = self._target(1.5)
        assert off < 4.5
        assert throttle > 0.0 and brake == 0.0

    def test_off_the_carriageway_it_lifts(self) -> None:
        """Off the tarmac at thirty metres a second: the pedal it wants is the
        brake, whatever the road ahead would have allowed."""
        (throttle, brake, _steer), off = self._target(6.5)
        assert off > 4.5
        assert brake > 0.0 and throttle == 0.0

    def test_it_still_steers_back_towards_the_line(self) -> None:
        pilot = self._pilot()
        at = pilot.course.lane_point(20, 6.5)
        car = _Car(position=at, forward=(0, 0, -1), speed=30.0)
        _throttle, _brake, steer = pilot.update(car)
        # A car to the right of the line steers left, which is positive here.
        assert steer > 0.02, 'off to the right and not steering back'

    def test_a_crawl_off_the_road_is_left_to_crawl_back_on(self) -> None:
        """Slow enough already: what it needs is the steering, not the brake."""
        pilot = self._pilot()
        at = pilot.course.lane_point(20, 6.5)
        car = _Car(position=at, forward=(0, 0, -1), speed=2.0)
        throttle, brake, _steer = pilot.update(car)
        assert brake == 0.0 and throttle > 0.0


class TestWhatIsComingTheOtherWayDrivesTheLimit:
    """A pass consumes the oncoming lane at the speed the two close on it, and
    what is coming the other way is *traffic*, doing the road's posted limit --
    not another racer doing what this car does.

    Measured before this: on the 3 km circuit the driver asked for a median of
    630 m of clear oncoming lane, which on a road whose oncoming cars sit 500 m
    apart is a pass that never comes. Sized on the limit those cars actually
    drive, the same pass asks for a fifth less road.
    """

    def _pilot(self, posted=80):
        course = _straight(points=400, spacing=5.0)
        course.posted = posted
        return Autopilot(course, lane=1.8)

    def _road(self, speed=40.0):
        return _Road(_Car(position=(1.8, 0.0, -100.0), speed=speed),
                     ahead=_Ahead(40.0, 18.0))

    def test_a_posted_road_asks_for_less_than_a_racer_coming_at_it(self) -> None:
        posted = self._pilot(posted=80)
        silent = self._pilot(posted=0)
        road, top = self._road(), DriverStyle().maximum_speed
        assert posted._pass_room(road, 40.0, top, road._ahead) \
            < silent._pass_room(road, 40.0, top, road._ahead)

    def test_a_road_that_says_nothing_assumes_the_worst(self) -> None:
        """No posted limit is no promise about what is coming, so the pass is
        sized as though it were another car doing what this one does."""
        silent = self._pilot(posted=0)
        road, top = self._road(), DriverStyle().maximum_speed
        room = silent._pass_room(road, 40.0, top, road._ahead)
        taking = silent.pass_seconds(40.0, 40.0, 18.0, quick=top)
        # What is left once this car's own share of the road is taken out is
        # what it expects to meet coming down that lane.
        coming = room - silent.pass_distance(40.0, taking, top)
        assert coming == pytest.approx(top * taking)

    def test_and_the_room_still_grows_with_how_long_it_takes(self) -> None:
        near = self._pilot()
        road, top = self._road(), DriverStyle().maximum_speed
        far = _Road(_Car(position=(1.8, 0.0, -100.0), speed=40.0),
                    ahead=_Ahead(120.0, 18.0))
        assert near._pass_room(far, 40.0, top, far._ahead) \
            > near._pass_room(road, 40.0, top, road._ahead)


class TestGivingUpOnAPassDoesNotDriveIntoTheCarBeingPassed:
    """Abandoning a pass is a manoeuvre too, and it has somewhere to go wrong.

    The way through closes and the driver comes back to its own side -- but its
    own side is where the car it was overtaking is, and alongside that car
    there is nothing to come back to. Watched on the 3 km circuit: out in the
    oncoming lane at 136 km/h, the pass given up, and the car cut back across
    the crown into a car 7 m ahead of it doing 78. The run ended `HIT A CAR`
    after 27.9 s, every time.

    The branch above this one -- the one for a pass that *finished* -- has
    always asked `lane_clear` before coming back in. This is the same question.
    """

    def _pilot(self):
        return Autopilot(_straight(points=400, spacing=5.0), lane=1.8)

    def started(self, pilot):
        """A pass under way in the oncoming lane, and the car it is passing."""
        slow = _Ahead(40.0, 18.0)
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=40.0), ahead=slow)
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8), 'never pulled out'
        return road, slow

    def test_it_stays_out_while_the_other_car_is_beside_it(self) -> None:
        pilot = self._pilot()
        road, slow = self.started(pilot)
        slow.gap = ALONGSIDE + 6.0               # given up, not yet past
        road._clear = False                      # the way through has closed
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8), 'cut back across it'

    def test_and_comes_back_in_once_there_is_room(self) -> None:
        """Room means the car it was passing is no longer beside it -- it has
        dropped back behind it, or got by."""
        pilot = self._pilot()
        road, slow = self.started(pilot)
        slow.gap = ALONGSIDE + 6.0               # still beside its own lane
        road._clear = False
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8), 'came back too early'
        slow.gap = 120.0                         # dropped well back behind it
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(1.8)

    def test_and_the_pass_is_over_either_way(self) -> None:
        """Given up is given up: it is not still overtaking that car, whichever
        side of the road it is finishing on.

        Far enough in front to be given up at all -- beside it there is no
        giving up left to do (:class:`TestAPassCommittedToIsFinished`) -- and
        still near enough that its own lane is not clear to return to.
        """
        pilot = self._pilot()
        road, slow = self.started(pilot)
        slow.gap = ALONGSIDE + 6.0
        road._clear = False
        pilot.controls(road, 1 / 60)
        assert pilot.passing is None
        assert pilot.lane == pytest.approx(-1.8), 'cut back across it'
        assert road.asked[-1] == pytest.approx(1.8), 'never asked its own side'


class TestAPassCommittedToIsFinished:
    """Once the two cars are alongside there is no giving up left to do.

    Recorded on the 3 km circuit: `pass-started x25, pass-given-up x23,
    pass-done x2`. The driver pulled out twenty-five times and abandoned
    twenty-three of them, spending the run dithering on the wrong side of the
    road -- because it re-decided from scratch every frame and the moment
    anything appeared in the oncoming lane it bailed, however far past the car
    it already was.

    :data:`ALONGSIDE` has always said where that line is, and
    :class:`StandIn` has always honoured it. Beside the car being passed,
    finishing is the only way out.
    """

    def _pilot(self):
        return Autopilot(_straight(points=400, spacing=5.0), lane=1.8)

    def started(self, pilot, gap=40.0):
        slow = _Ahead(gap, 18.0)
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=40.0), ahead=slow)
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8), 'never pulled out'
        return road, slow

    def test_it_finishes_one_it_is_already_beside(self) -> None:
        pilot = self._pilot()
        road, slow = self.started(pilot)
        slow.gap = ALONGSIDE / 2.0               # level with it
        road._clear = False                      # and the way through closes
        pilot.controls(road, 1 / 60)
        assert pilot.passing is not None, 'gave up beside the car it was passing'
        assert pilot.lane == pytest.approx(-1.8)

    def test_but_gives_one_up_while_it_is_still_behind(self) -> None:
        """Back there the lane it came from is still its own to return to,
        and the wrong side of a road is no place to wait and see."""
        pilot = self._pilot()
        road, slow = self.started(pilot)
        slow.gap = ALONGSIDE * 3.0               # still well in front
        road._clear = False
        pilot.controls(road, 1 / 60)
        assert pilot.passing is None

    def test_and_a_committed_pass_still_ends_when_it_is_past(self) -> None:
        """Committed is not for ever: past the car, it comes back in."""
        pilot = self._pilot()
        road, slow = self.started(pilot)
        slow.gap = ALONGSIDE / 2.0
        road._clear = False
        pilot.controls(road, 1 / 60)
        slow.gap = -PASSED_BY - 5.0              # past it now
        road._ahead = None
        pilot.controls(road, 1 / 60)
        assert pilot.passing is None
        assert pilot.lane == pytest.approx(1.8)


class TestComingBackInLooksAsFarAsItIsGoing:
    """A lane is clear enough to return to when there is road to shed the
    speed being carried into it, not when a fixed window happens to be empty.

    Read off a recorded lap of the 7.2 km circuit: the pass was given up at
    134.5 km/h, its own lane was judged clear, and 1.2 s later the car hit
    something in that lane going the same way at the same speed. ``lane_clear``
    looks a fixed 24 m ahead -- at 37 m/s that is two thirds of a second, and
    the car covered 45 m before it arrived.

    :meth:`StandIn.room_in` has always asked it the other way round, and says
    why in its own docstring: a window is a fixed time only at one speed.
    """

    def _pilot(self, **style):
        return Autopilot(_straight(points=400, spacing=5.0), lane=1.8,
                         style=DriverStyle(**style))

    def test_a_lane_with_a_car_just_beyond_the_window_is_not_clear(self) -> None:
        """30 m ahead at 37 m/s, which the fixed window never saw."""
        pilot = self._pilot()
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=37.0),
                     ahead=_Ahead(30.0, 14.0))
        assert not pilot.room_in(road, 1.8)

    def test_and_the_same_car_is_fine_at_a_crawl(self) -> None:
        """Thirty metres is plenty when there is nothing to shed."""
        pilot = self._pilot()
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=15.0),
                     ahead=_Ahead(30.0, 14.0))
        assert pilot.room_in(road, 1.8)

    def test_an_empty_lane_is_always_clear(self) -> None:
        pilot = self._pilot()
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=37.0), ahead=None)
        assert pilot.room_in(road, 1.8)

    def test_and_a_car_going_as_fast_is_nothing_to_shed(self) -> None:
        """What matters is the speed being carried *into* it, not the speed."""
        pilot = self._pilot()
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=37.0),
                     ahead=_Ahead(30.0, 37.0))
        assert pilot.room_in(road, 1.8)


class TestItBrakesForTheLaneItIsGoingTo:
    """A driver follows what is in front of where it is *going*, not only what
    is in front of where it is.

    The Ashdown crash, read off the journal: a pass given up at 134.5 km/h,
    back into its own lane, and 1.2 s later the back of a car doing 50 in it.
    While crossing, the driver was following the oncoming lane it was leaving
    -- `traffic_ahead` asks from the car's own position -- so nothing told it
    to brake until it had arrived. Steering into a lane and braking for it are
    the same decision, a second apart.
    """

    def _pilot(self):
        return Autopilot(_straight(points=400, spacing=5.0), lane=1.8)

    def test_it_follows_the_slower_of_the_two_lanes(self) -> None:
        pilot = self._pilot()
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=37.0),
                     ahead=_Ahead(30.0, 14.0))
        pilot.controls(road, 1 / 60)
        assert pilot.ahead is not None, 'following nothing at all'
        assert pilot.ahead[0] == pytest.approx(30.0)

    def test_and_so_slows_for_a_lane_it_has_not_reached(self) -> None:
        """The whole point: the brakes come on while it is still crossing.

        The car is out in the oncoming lane and steering home, and what it is
        steering at is a car doing 14 m/s. From its own position there is
        nothing in front at all.
        """
        pilot = self._pilot()
        road = _Road(_Car(position=(-1.8, 0.0, -100.0), speed=37.0),
                     ahead=_Ahead(30.0, 14.0))
        assert road.traffic_ahead() is None, 'the double is not modelling lanes'
        pilot.controls(road, 1 / 60)
        assert pilot.ahead is not None, 'nothing told it to brake'
        assert pilot._room() < 37.0, 'carried its speed into the lane'

    def test_an_empty_road_is_still_an_empty_road(self) -> None:
        pilot = self._pilot()
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=37.0), ahead=None)
        pilot.controls(road, 1 / 60)
        assert pilot.ahead is None

    def test_but_it_does_not_follow_the_oncoming_lane_it_pulled_into(self
                                                                     ) -> None:
        """A car coming the other way is not something to sit behind.

        The gap to it shuts at the sum of both speeds, and a driver that
        treats it as a car to keep station on brakes to a standstill in the
        wrong lane. Measured when this rule was first written without the
        distinction: on the 3 km road the car went from 108 km/h to 3.9 over
        112 m, sat there ten seconds, and ended mired 8.5 m off the crown.

        Out on the far side, what governs is the pass -- finish it or give it
        up -- and never a following distance.
        """
        pilot = self._pilot()
        road = _Road(_Car(position=(-1.8, 0.0, -100.0), speed=37.0),
                     ahead=_Ahead(30.0, 14.0))
        pilot.lane = -1.8                        # out passing
        assert pilot.what_to_follow(road, 37.0) is None, \
            'tried to keep station on oncoming traffic'
        pilot.lane = pilot.own_side              # and home again
        assert pilot.what_to_follow(road, 37.0) is not None, \
            'stopped following its own lane as well'


class TestItEasesOffBeforeTheEdgeRatherThanAfterIt:
    """Running out of road is not an event, it is an approach.

    ``rejoining`` held road speed at 3.59 m from the crown and cut to
    :data:`REJOIN_SPEED` at 3.61 -- a cliff at the carriageway edge, reacting
    to a wheel that is *already* off. Off a structure that costs a moment on
    the grass; on one there is no verge at all, and the parapet standing 0.9 m
    beyond the edge throws the car into the air. Measured on the shipped
    Ashdown circuit: six excursions in a lap, every one of them at -3.68 m
    against a 3.60 m edge, the car a tenth of a metre wide of the road.

    So the driver eases over the last :data:`EDGE_BAND` of it instead, and is
    already slowing while the wheels are still on the tarmac.
    """

    def _pilot(self):
        return Autopilot(_straight(points=400, spacing=5.0), lane=1.8)

    def test_the_middle_of_the_road_is_untouched(self) -> None:
        pilot = self._pilot()
        assert pilot.rejoining(0.0, 40.0) == pytest.approx(40.0)

    def test_it_is_already_easing_before_a_wheel_is_off(self) -> None:
        """Half a metre from the edge, on the tarmac, and coming down."""
        pilot = self._pilot()
        half = pilot.course.carriageway_width / 2.0
        assert pilot.rejoining(half - 0.3, 40.0) < 40.0

    def test_and_is_down_to_the_rejoining_speed_once_it_is_off(self) -> None:
        pilot = self._pilot()
        half = pilot.course.carriageway_width / 2.0
        assert pilot.rejoining(half + 0.5, 40.0) == pytest.approx(REJOIN_SPEED)

    def test_it_never_asks_for_more_than_it_was_going_to(self) -> None:
        """A lift, not a target: a driver already going slowly stays there."""
        pilot = self._pilot()
        half = pilot.course.carriageway_width / 2.0
        assert pilot.rejoining(half - 0.3, 5.0) == pytest.approx(5.0)

    def test_and_it_comes_down_smoothly_across_the_band(self) -> None:
        """A cliff is a driver that lifts hard at one wheel's width, which
        unsettles the car exactly where it has least room to be unsettled."""
        pilot = self._pilot()
        half = pilot.course.carriageway_width / 2.0
        steps = [pilot.rejoining(half - one, 40.0)
                 for one in (0.6, 0.45, 0.3, 0.15, 0.0)]
        assert steps == sorted(steps, reverse=True)
        assert steps[0] > steps[-1]


class TestItUsesAPassingLaneWhereTheRoadHasOne:
    """Where the carriageway widens there is room to get by on this car's own
    side of the crown, and a pass taken there needs nothing of the oncoming
    road at all.

    The driver only ever considered ``-own_side`` -- the oncoming lane -- so a
    climbing lane was invisible to it. On the shipped Ashdown circuit that is
    1183 m of road, 16% of the lap, and the driver spent 39 to 47 per cent of
    every run refusing passes because the *oncoming* lane was not clear while a
    lane beside it stood empty.

    Two cars abreast want about 4.7 m; an ordinary 7.2 m carriageway offers
    3.6 m a side and a widened one 5.4 m, which is the whole difference.
    """

    def road(self, widening=0.0):
        course = _straight(points=400, spacing=5.0)
        course.widening = np.full(len(course.centreline), float(widening))
        return course

    def test_an_ordinary_road_offers_none(self) -> None:
        pilot = Autopilot(self.road(), lane=1.8)
        assert pilot.passing_lane(0) is None

    def test_a_widened_one_offers_a_lane_on_its_own_side(self) -> None:
        pilot = Autopilot(self.road(widening=3.6), lane=1.8)
        found = pilot.passing_lane(0)
        assert found is not None
        assert found > 1.8, 'it is not outside the lane the car is in'

    def test_and_that_lane_is_on_the_road(self) -> None:
        """Outside the lane it is in, inside the tarmac."""
        course = self.road(widening=3.6)
        pilot = Autopilot(course, lane=1.8)
        assert pilot.passing_lane(0) < course.width_at(0) / 2.0

    def test_the_other_way_round_on_the_other_side(self) -> None:
        pilot = Autopilot(self.road(widening=3.6), lane=-1.8)
        found = pilot.passing_lane(0)
        assert found is not None and found < -1.8

    def test_a_little_extra_width_is_not_a_lane(self) -> None:
        """Half a lane of widening is a wider road, not one to overtake on."""
        pilot = Autopilot(self.road(widening=1.2), lane=1.8)
        assert pilot.passing_lane(0) is None


class TestALaneChangeIsEasedRatherThanStepped:
    """Asking for the other lane moves the line the car follows by its whole
    width, and a car told to be 3.6 m over *now* darts at it and overshoots.

    Which is how the shipped Beacon road failed, in every one of five runs at
    the same place: passing along the last stretch of a bridge, the car ran to
    -3.8 m against a carriageway edge of 3.6 -- two metres wide of the -1.8 it
    had been told to hold -- put a wheel over the edge of the deck, and ended
    twenty-one metres off the road. The road there is straight and the corner
    speed never enters into it.

    So the *line* eases across at :data:`LANE_RATE` while the *decision* stays
    a decision: :attr:`Autopilot.lane` is still the lane it has chosen, and
    everything that asks which lane it wants gets the same answer as before.
    """

    def _pilot(self):
        return Autopilot(_straight(points=400, spacing=5.0), lane=1.8)

    def test_the_line_starts_where_the_car_does(self) -> None:
        assert self._pilot().line == pytest.approx(1.8)

    def test_asking_for_the_other_lane_does_not_move_it_at_once(self) -> None:
        pilot = self._pilot()
        pilot.lane = -1.8
        pilot.ease(1.0 / 60.0)
        assert -1.8 < pilot.line < 1.8, 'stepped straight across'

    def test_but_it_gets_there(self) -> None:
        pilot = self._pilot()
        pilot.lane = -1.8
        for _ in range(240):
            pilot.ease(1.0 / 60.0)
        assert pilot.line == pytest.approx(-1.8)

    def test_it_takes_about_a_lane_change_to_do_it(self) -> None:
        """A second or two, which is what a considered move across a road is
        -- and slow enough that the car arrives on the line instead of past
        it."""
        pilot = self._pilot()
        pilot.lane = -1.8
        seconds = 0.0
        while abs(pilot.line - pilot.lane) > 0.05 and seconds < 10.0:
            pilot.ease(1.0 / 60.0)
            seconds += 1.0 / 60.0
        assert 0.8 < seconds < 4.0, 'took %.1f s' % seconds

    def test_the_decision_is_still_the_decision(self) -> None:
        """Everything that asks which lane it has chosen still gets that."""
        pilot = self._pilot()
        pilot.lane = -1.8
        pilot.ease(1.0 / 60.0)
        assert pilot.lane == pytest.approx(-1.8)


class TestFinishingAPassWaitsForRoomToSitIn:
    """Being past a car is not the same as having somewhere to go.

    Read off the Ashdown journal: a pass completed at 137 km/h, back to its own
    lane, and a third of a second later the back of a car doing 32 in it --
    `lane_clear` looks a fixed 24 m, which at 38 m/s is two thirds of a second
    of road. The car was still crossing the crown when it arrived.

    Out there it is already past what it overtook and going faster than it, so
    waiting is safe -- which is what makes this different from *abandoning* a
    pass, where staying out means sitting on the wrong side of the road with
    something coming (:class:`TestGivingUpOnAPassDoesNotDriveIntoTheCarBeingPassed`).
    """

    def _pilot(self):
        return Autopilot(_straight(points=400, spacing=5.0), lane=1.8)

    def passed(self, pilot, ahead):
        """A pass taken and finished, with ``ahead`` up its own lane."""
        slow = _Ahead(40.0, 18.0)
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=38.0), ahead=slow)
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8), 'never pulled out'
        slow.gap = -PASSED_BY - 10.0             # past it now
        road._own_lane = _Ahead(*ahead)
        return road

    def test_it_stays_out_for_something_it_cannot_slot_in_behind(self) -> None:
        pilot = self._pilot()
        road = self.passed(pilot, ahead=(24.0, 9.0))
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8), 'came back onto it'

    def test_and_takes_the_lane_when_there_is_road_to_hold_it(self) -> None:
        pilot = self._pilot()
        road = self.passed(pilot, ahead=(200.0, 9.0))
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(1.8)


class TestAPassStartsFromBehindTheCarNotOffItsBumper:
    """A driver sitting inside its own following distance has nowhere to pull
    out from and nothing to see past.

    Read off a recorded run of the shipped Beacon road: `pass-started gap=10.6`
    at 80 km/h, given up a tenth of a second later and stranded on the wrong
    side; then another begun and declared `pass-done` in 0.1 s. The car thrashed
    across the crown and put itself off the road at the next station.

    A pass is decided *from* the following distance -- the room a driver keeps
    precisely so there is somewhere to go and something to see -- so being
    nearer than that is a reason to wait, not a reason to pull out.
    """

    def _pilot(self):
        return Autopilot(_straight(points=400, spacing=5.0), lane=1.8)

    def road(self, gap, speed=38.0, theirs=21.0):
        return _Road(_Car(position=(1.8, 0.0, -100.0), speed=speed),
                     ahead=_Ahead(gap, theirs))

    def test_it_does_not_pull_out_off_a_bumper(self) -> None:
        pilot = self._pilot()
        road = self.road(gap=10.6)
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(1.8), 'pulled out from 10 m behind'
        assert pilot.passing is None

    def test_but_does_from_a_settled_distance_back(self) -> None:
        pilot = self._pilot()
        road = self.road(gap=pilot.pulling_out_from(38.0) + 12.0)
        pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(-1.8)
        assert pilot.passing is not None

    def test_and_a_crawl_behind_a_stopped_car_is_not_on_a_bumper(self) -> None:
        """Ten metres at eighty is paintwork; ten metres at a crawl is three
        seconds of road and an ordinary place to pull out from."""
        pilot = self._pilot()
        pilot.controls(self.road(gap=9.0, speed=3.0, theirs=0.0), 1 / 60)
        assert pilot.passing is not None

    def test_just_inside_it_is_still_too_close(self) -> None:
        pilot = self._pilot()
        pilot.controls(self.road(gap=pilot.pulling_out_from(38.0) * 0.9),
                       1 / 60)
        assert pilot.passing is None


class TestItHoldsSomethingBackWhileCrossingTheRoad:
    """Changing lanes at the absolute limit leaves nothing to correct with.

    Read off a recorded Beacon run: the pass completed at 143.6 km/h where the
    road allows 145.7 -- flat out, in the oncoming lane -- and the car then had
    to cross back with no margin. It diverged two metres from its line in six
    tenths of a second on a straight, put a wheel on the verge, and was mired
    twenty metres off the road.

    So while the line is still moving across, the driver asks for a little less
    than the road would give it. It costs a fraction of a second on a pass and
    buys the grip to arrive on the line rather than past it.
    """

    def _pilot(self):
        return Autopilot(_straight(points=400, spacing=5.0), lane=1.8)

    def test_settled_in_its_lane_it_asks_for_everything(self) -> None:
        pilot = self._pilot()
        assert pilot.crossing_speed(40.0) == pytest.approx(40.0)

    def test_but_less_while_it_is_moving_across(self) -> None:
        pilot = self._pilot()
        pilot.lane = -1.8                        # a change under way
        pilot.ease(1.0 / 60.0)
        assert pilot.crossing_speed(40.0) < 40.0

    def test_and_everything_again_once_it_has_arrived(self) -> None:
        pilot = self._pilot()
        pilot.lane = -1.8
        for _ in range(240):
            pilot.ease(1.0 / 60.0)
        assert pilot.crossing_speed(40.0) == pytest.approx(40.0)

    def test_it_is_a_lift_and_not_a_stop(self) -> None:
        """Most of the speed, not a fraction of it: a pass still has to be a
        pass."""
        pilot = self._pilot()
        pilot.lane = -1.8
        pilot.ease(1.0 / 60.0)
        assert pilot.crossing_speed(40.0) > 40.0 * 0.8


class TestAPassingLaneIsPreferredToTheOncomingOne:
    """Where the carriageway widens the pass can be made without using the
    other side of the road at all, and that is the pass to make.

    :meth:`Autopilot.passing_lane` could find the lane; nothing asked it. So
    on the shipped Ashdown circuit the driver spent between two and five
    fifths of every run refusing passes for want of a clear *oncoming* lane
    while 1183 m of climbing lane stood empty beside it.

    A pass on its own side also needs less room: what has to be clear is the
    length of the pass, not that length closed at the sum of two cars' speeds.
    """

    def road(self, widening=3.6):
        course = _straight(points=400, spacing=5.0)
        course.widening = np.full(len(course.centreline), float(widening))
        return course

    def _pilot(self, widening=3.6):
        return Autopilot(self.road(widening), lane=1.8)

    def _session(self, **named):
        return _Road(_Car(position=(1.8, 0.0, -100.0), speed=40.0),
                     ahead=_Ahead(40.0, 18.0), **named)

    def test_it_passes_on_its_own_side_with_the_far_side_busy(self) -> None:
        pilot, road = self._pilot(), self._session(clear=False)
        pilot.controls(road, 1 / 60)
        assert pilot.passing is not None, 'refused a pass it had room for'
        assert pilot.lane > 1.8, 'used the oncoming lane, or stayed in'

    def test_an_ordinary_road_still_refuses_it(self) -> None:
        pilot, road = self._pilot(widening=0.0), self._session(clear=False)
        pilot.controls(road, 1 / 60)
        assert pilot.passing is None
        assert pilot.lane == pytest.approx(1.8)

    def test_the_passing_lane_comes_first_when_both_are_open(self) -> None:
        pilot, road = self._pilot(), self._session()
        pilot.controls(road, 1 / 60)
        assert pilot.lane > 1.8, 'crossed the crown with a lane beside it'

    def test_a_passing_lane_with_something_in_it_is_no_use(self) -> None:
        pilot, road = self._pilot(), self._session(clear=False)
        road.beside_clear = False
        pilot.controls(road, 1 / 60)
        assert pilot.passing is None
        assert pilot.lane == pytest.approx(1.8)

    def test_it_asks_for_less_room_than_a_pass_across_the_crown(self) -> None:
        """Nothing is coming the other way in a lane going the same way."""
        pilot, road = self._pilot(), self._session()
        first = road.car_ahead()
        beside = pilot._pass_room(road, 40.0, 40.0, first, oncoming=False)
        across = pilot._pass_room(road, 40.0, 40.0, first)
        assert beside is not None and across is not None
        assert beside < across

    def test_and_it_comes_back_in_afterwards(self) -> None:
        pilot, road = self._pilot(), self._session(clear=False)
        pilot.controls(road, 1 / 60)
        taken = pilot.lane
        road._ahead.gap = -30.0                  # by it now
        for _ in range(120):
            pilot.controls(road, 1 / 60)
        assert pilot.lane == pytest.approx(1.8), f'sat out in {taken}'


class TestTheEdgeIsWhereTheRoadActuallyEnds:
    """A widened stretch has its edge further out, and a driver that measures
    from the road's ordinary width lifts a lane early on it.

    Which would make a climbing lane unusable by the driver that needs it: the
    pass sits a car's width outside the ordinary carriageway, so measured
    against the ordinary edge it reads as a wheel already off the road and
    :meth:`Autopilot.rejoining` holds the car at walking pace for the length of
    the lane.
    """

    def _road(self, widening=0.0):
        course = _straight(points=400, spacing=5.0)
        course.widening = np.full(len(course.centreline), float(widening))
        return course

    def test_the_ordinary_road_is_unchanged(self) -> None:
        pilot = Autopilot(self._road(), lane=1.8)
        half = pilot.course.carriageway_width / 2.0
        assert pilot.rejoining(half + 0.5, 40.0, 0) == pytest.approx(
            REJOIN_SPEED)

    def test_a_widened_one_is_still_road_out_there(self) -> None:
        pilot = Autopilot(self._road(widening=3.6), lane=1.8)
        half = pilot.course.carriageway_width / 2.0
        assert pilot.rejoining(half + 0.5, 40.0, 0) == pytest.approx(40.0)

    def test_and_it_eases_at_the_wider_edge_instead(self) -> None:
        pilot = Autopilot(self._road(widening=3.6), lane=1.8)
        edge = pilot.course.width_at(0) / 2.0
        assert pilot.rejoining(edge - 0.3, 40.0, 0) < 40.0
        assert pilot.rejoining(edge + 0.5, 40.0, 0) == pytest.approx(
            REJOIN_SPEED)

    def test_a_pass_in_a_climbing_lane_is_driven_at_road_speed(self) -> None:
        """The whole point of the lane: the car sits a width outside the
        ordinary carriageway and is not crawling while it is there."""
        pilot = Autopilot(self._road(widening=3.6), lane=1.8)
        beside = pilot.passing_lane(0)
        assert beside is not None
        assert pilot.rejoining(abs(beside), 40.0, 0) == pytest.approx(40.0)


class TestADriverTooCloseFallsBack:
    """Matching the speed of the car in front holds whatever gap it arrived
    with, which is not the same as keeping a following distance.

    Read off a recorded Tidewater lap: 4.3 m behind a car at 77 km/h, held
    there for a kilometre. A fifth of a second. The rule asked for *the
    leader's speed* as soon as the gap closed inside the following distance,
    and a car doing exactly the speed of the thing in front never gets back
    the room it lost getting there.

    So being too close asks for less than the leader, by enough to bleed the
    shortfall off over the same time the gap is measured in, and the gap opens
    up again instead of being frozen wherever the driver arrived.
    """

    def _pilot(self):
        return Autopilot(_straight(points=400, spacing=5.0), lane=1.8)

    def test_at_its_following_distance_it_matches_the_car_in_front(self) -> None:
        pilot = self._pilot()
        pilot.following(pilot.following_gap(30.0), 25.0)
        assert pilot._room(30.0) == pytest.approx(25.0, abs=0.5)

    def test_further_back_it_may_go_quicker(self) -> None:
        pilot = self._pilot()
        pilot.following(pilot.following_gap(30.0) + 60.0, 25.0)
        assert pilot._room(30.0) > 25.0

    def test_but_too_close_it_asks_for_less(self) -> None:
        pilot = self._pilot()
        pilot.following(4.3, 21.5)
        assert pilot._room(21.5) < 21.5, 'it would sit there for ever'

    def test_and_never_for_less_than_a_standstill(self) -> None:
        """Nose to tail behind something stopped is a stop, not a reverse."""
        pilot = self._pilot()
        pilot.following(0.5, 0.0)
        assert pilot._room(2.0) >= 0.0

    def test_the_fall_back_is_gentle_rather_than_a_stop(self) -> None:
        """A driver a little close lifts; it does not stand on the brakes."""
        pilot = self._pilot()
        gap = pilot.following_gap(30.0)
        pilot.following(gap - 2.0, 25.0)
        assert 20.0 < pilot._room(30.0) < 25.0


class TestHowMuchRoadAPassActuallyUses:
    """What has to be clear is the road the pass **covers**, not the road it
    would cover if it were already going as fast as it will end up.

    A pass consumes the oncoming lane from where the car is now to where it
    finishes, plus whatever is coming down that lane in the meantime. Sized
    instead at the speed the road allows for the whole of it, a pass begun from
    a crawl asks for a third more road than it uses -- and the traffic on a
    two-way road is spaced so that one pass *just* fits
    (:func:`glisteel.traffic.passable_count`), so a third more is a window that
    hardly ever opens. On the recorded Tidewater lap the driver asked for a
    median 440 m of clear oncoming lane on a road whose oncoming cars sit about
    500 m apart, wanted to pass 164 times and started 10.
    """

    def _pilot(self, lane=1.8):
        return Autopilot(_straight(points=400, spacing=5.0), lane=lane)

    def _top(self):
        return DriverStyle().maximum_speed

    def test_a_car_already_at_speed_covers_speed_times_time(self) -> None:
        pilot = self._pilot()
        top = self._top()
        assert pilot.pass_distance(top, 4.0, top) == pytest.approx(top * 4.0)

    def test_one_winding_up_covers_less_than_that(self) -> None:
        pilot = self._pilot()
        top = self._top()
        covered = pilot.pass_distance(4.0, 4.0, top)
        assert 4.0 * 4.0 < covered < top * 4.0

    def test_and_reaches_the_top_speed_part_way_through(self) -> None:
        """Beyond the winding-up it runs at the top speed, so a longer pass
        gains exactly that much more road."""
        pilot = self._pilot()
        top = self._top()
        gained = (pilot.pass_distance(4.0, 20.0, top)
                  - pilot.pass_distance(4.0, 19.0, top))
        assert gained == pytest.approx(top, abs=1e-6)

    def test_the_room_asked_for_is_that_road_and_the_oncoming_car_s(self
                                                                   ) -> None:
        pilot = self._pilot()
        top = self._top()
        crawling = _Road(_Car(position=(1.8, 0.0, -100.0), speed=3.0),
                         ahead=_Ahead(40.0, 0.0))
        taking = pilot.pass_seconds(3.0, 40.0, 0.0, quick=top)
        assert pilot._pass_room(crawling, 3.0, top, crawling._ahead) \
            == pytest.approx(pilot.pass_distance(3.0, taking, top)
                             + pilot.oncoming_speed(top) * taking)

    def test_which_is_less_than_the_road_it_would_use_at_full_speed(self
                                                                   ) -> None:
        pilot = self._pilot()
        top = self._top()
        crawling = _Road(_Car(position=(1.8, 0.0, -100.0), speed=3.0),
                         ahead=_Ahead(40.0, 0.0))
        taking = pilot.pass_seconds(3.0, 40.0, 0.0, quick=top)
        asked = pilot._pass_room(crawling, 3.0, top, crawling._ahead)
        assert asked < (top + pilot.oncoming_speed(top)) * taking * 0.85

    def test_and_a_pass_taken_at_speed_asks_for_what_it_always_did(self
                                                                  ) -> None:
        """Nothing here makes a driver braver: a car already doing what the
        road allows covers exactly the road it always said it would."""
        pilot = self._pilot()
        top = self._top()
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=top),
                     ahead=_Ahead(40.0, top - 12.0))
        taking = pilot.pass_seconds(top, 40.0, top - 12.0, quick=top)
        assert pilot._pass_room(road, top, top, road._ahead) \
            == pytest.approx((top + pilot.oncoming_speed(top)) * taking)


class TestWritingDownWhyAPassWasNotOn:
    """The record wants the *stretch* -- it wanted to pass from here to there
    and the other lane was never clear -- and a reason that lasted one step is
    not a stretch.

    Two reasons on either side of a boundary swap at whatever rate the driver
    is asked, and each swap wrote a line. On the recorded Tidewater lap that is
    what 164 `pass-wanted` entries are: the gap sat on the distance a pass is
    decided from and the journal flipped between "too close to pull out" and
    "other lane not clear" sixty times a second, burying the two stretches a
    reader came for. :data:`REASON_HOLDS` is the line between a driver changing
    its mind and a boundary being sat on: a reason that held starts a stretch,
    and one that did not is folded into the stretch it interrupted.
    """

    class _Kept:
        def __init__(self):
            self.marks = []

        def mark(self, name, **fields):
            self.marks.append((name, fields))

    def _pilot(self):
        pilot = Autopilot(_straight(points=400, spacing=5.0), lane=1.8)
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=40.0))
        road.telemetry = self._Kept()
        return pilot, road

    def test_a_reason_that_held_is_written_down(self) -> None:
        pilot, road = self._pilot()
        pilot.refused(road, 'other lane not clear', REASON_HOLDS * 2)
        pilot.refused(road, 'nothing in front', REASON_HOLDS * 2)
        assert [name for name, _ in road.telemetry.marks] == ['pass-wanted']
        assert road.telemetry.marks[0][1]['why'] == 'other lane not clear'

    def test_a_reason_sat_on_a_boundary_is_one_stretch(self) -> None:
        """Two reasons swapping on every step are one stretch of wanting to
        pass, written once with the whole of its time and the other reason
        named beside it."""
        pilot, road = self._pilot()
        for _ in range(60):
            pilot.refused(road, 'too close to pull out', 1 / 60)
            pilot.refused(road, 'other lane not clear', 1 / 60)
        assert road.telemetry.marks == []
        pilot.refused(road, 'nothing in front', REASON_HOLDS * 2)
        [(name, fields)] = road.telemetry.marks
        assert name == 'pass-wanted'
        assert fields['why'] == 'too close to pull out'
        assert fields['seconds'] == pytest.approx(2.0, abs=0.05)
        assert fields['also'] == ['other lane not clear']

    def test_a_reason_that_did_not_hold_joins_the_stretch_it_interrupted(
            self) -> None:
        pilot, road = self._pilot()
        pilot.refused(road, 'other lane not clear', 1.0)
        pilot.refused(road, 'too close to pull out', REASON_HOLDS / 2)
        pilot.refused(road, 'other lane not clear', 1.0)
        pilot.flush(road)
        [(name, fields)] = road.telemetry.marks
        assert fields['why'] == 'other lane not clear'
        assert fields['seconds'] == pytest.approx(2.0 + REASON_HOLDS / 2,
                                                  abs=0.05)

    def test_the_mark_says_where_the_stretch_began(self) -> None:
        pilot, road = self._pilot()
        began = pilot.station(road)
        pilot.refused(road, 'other lane not clear', 1.0)
        road.car.position = np.asarray((1.8, 0.0, -300.0))
        pilot.flush(road)
        fields = road.telemetry.marks[0][1]
        assert fields['at'] == pytest.approx(began, abs=0.1)
        assert fields['until'] == pytest.approx(pilot.station(road), abs=0.1)

    def test_a_stretch_still_open_at_the_end_of_a_run_is_written(self) -> None:
        pilot, road = self._pilot()
        pilot.refused(road, 'other lane not clear', 3.0)
        pilot.flush(road)
        assert [name for name, _ in road.telemetry.marks] == ['pass-wanted']
        pilot.flush(road)
        assert len(road.telemetry.marks) == 1, 'written twice'

    def test_pulling_out_ends_the_stretch_before_it(self) -> None:
        """A stretch before a pass and one after it are two stretches, and the
        time spent passing is in neither."""
        pilot, road = self._pilot()
        pilot.refused(road, 'other lane not clear', 3.0)
        pilot._pull_out(road, -1.8, _Ahead(40.0, 10.0), 200.0)
        pilot.refused(road, 'other lane not clear', 1.0)
        pilot.flush(road)
        wanted = [fields['seconds'] for name, fields in road.telemetry.marks
                  if name == 'pass-wanted']
        assert wanted == [pytest.approx(3.0), pytest.approx(1.0)]


class TestWritingDownACrawl:
    """A stretch spent far under what the road allows, written once it ends --
    or when the run does, since a run that ends crawling is the stuck run the
    mark is there to explain."""

    def _pilot(self):
        pilot = Autopilot(_straight(points=400, spacing=5.0), lane=1.8)
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=1.0))
        road.telemetry = TestWritingDownWhyAPassWasNotOn._Kept()
        return pilot, road

    def test_a_run_that_ends_crawling_says_so(self) -> None:
        pilot, road = self._pilot()
        for _ in range(120):
            pilot.held_back(road, 1.0, 30.0, 1 / 60)
        pilot.flush(road)
        [(name, fields)] = road.telemetry.marks
        assert name == 'crawled'
        assert fields['seconds'] == pytest.approx(2.0, abs=0.05)

    def test_a_moment_below_the_road_is_not_a_crawl(self) -> None:
        pilot, road = self._pilot()
        pilot.held_back(road, 1.0, 30.0, 0.1)
        pilot.flush(road)
        assert road.telemetry.marks == []


class TestARestartedRaceStartsTheDriverAfresh:
    def test_nothing_of_the_last_race_is_carried(self) -> None:
        pilot = Autopilot(_straight(points=400, spacing=5.0), lane=1.8)
        road = _Road(_Car(position=(1.8, 0.0, -100.0), speed=1.0))
        road.telemetry = TestWritingDownWhyAPassWasNotOn._Kept()
        pilot.refused(road, 'other lane not clear', 3.0)
        pilot.held_back(road, 1.0, 30.0, 3.0)
        pilot._pull_out(road, -1.8, _Ahead(40.0, 10.0), 200.0)
        pilot.passing_for = 4.0
        road.telemetry.marks.clear()
        pilot.restart()
        pilot.flush(road)
        assert road.telemetry.marks == []
        assert pilot.passing is None and pilot.passing_for == 0.0
        assert pilot.lane == pilot.line == pilot.own_side
