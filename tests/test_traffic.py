"""Other people, using the road.

A circuit with nothing on it is a time trial. What makes it a *road* is that
somebody else is on it, going the speed limit, in both directions -- and that
what they do next is not entirely predictable, because a car in front braking
for something the driver cannot see is the thing that makes traffic worth
overtaking rather than scenery to drive around.

Traffic is placed by *station*: how far along the course it is, which way it is
going, and which side of the centreline it keeps. Everything about how it moves
is that number and a speed, which is why none of it needs a window to test.
"""
import numpy as np
import pytest
from omi_physics.world import PhysicsWorld

from glisteel import models
from glisteel.traffic import (
    CRUISING,
    DEFAULT_TRAFFIC,
    PULLING_OFF,
    SLOWING,
    Traffic,
    TrafficCar,
)
from glisteel.world import Course

LIMIT = 25.0


def _course(length=2000.0, count=201, closed=False):
    z = np.linspace(0.0, length, count)
    return Course(name='road', centreline=np.stack(
        [np.zeros(count), np.zeros(count), z], axis=-1),
        carriageway_width=7.2, total_width=10.6, closed=closed, length=length)


def _ring(radius=300.0, count=241):
    angle = np.linspace(0.0, 2.0 * np.pi, count)
    line = np.stack([np.cos(angle) * radius, np.zeros(count),
                     np.sin(angle) * radius], axis=-1)
    steps = np.linalg.norm(np.diff(line, axis=0), axis=1)
    return Course(name='ring', centreline=line, carriageway_width=7.2,
                  total_width=10.6, closed=True, length=float(steps.sum()))


def _car(course=None, station=100.0, heading=1, **named):
    return TrafficCar(course=course or _course(), station=station,
                      heading=heading, limit=LIMIT, seed=1, **named)


class TestWhereATrafficCarIs:
    def test_it_starts_where_it_was_put(self) -> None:
        assert _car(station=250.0).station == 250.0

    def test_it_is_on_the_road(self) -> None:
        at = _car().position()
        assert abs(float(at[2]) - 100.0) < 1.0

    def test_it_keeps_its_own_side_going_one_way(self) -> None:
        """The road's own "right", which is the frame everything swept along it
        uses: for a course running towards +Z that is -X."""
        assert float(_car(heading=1).position()[0]) < -0.5

    def test_and_the_other_side_going_the_other(self) -> None:
        assert float(_car(heading=-1).position()[0]) > 0.5

    def test_neither_is_off_the_carriageway(self) -> None:
        for heading in (1, -1):
            assert abs(float(_car(heading=heading).position()[0])) < 3.6

    def test_it_faces_the_way_it_is_going(self) -> None:
        along = _car(heading=1).forward()
        against = _car(heading=-1).forward()
        assert float(np.dot(along, against)) < -0.9

    def test_driving_moves_it_along(self) -> None:
        car = _car(station=100.0)
        for _ in range(60):
            car.advance(1.0 / 60.0)
        assert car.station > 120.0

    def test_and_the_other_way_moves_it_back(self) -> None:
        car = _car(station=500.0, heading=-1)
        for _ in range(60):
            car.advance(1.0 / 60.0)
        assert car.station < 480.0

    def test_it_gets_up_to_the_limit_and_stays_there(self) -> None:
        car = _car()
        for _ in range(600):
            car.advance(1.0 / 60.0)
        assert abs(car.speed - LIMIT) < LIMIT * 0.2

    def test_it_does_not_run_off_the_end_of_an_open_road(self) -> None:
        course = _course(length=400.0)
        car = _car(course=course, station=380.0)
        for _ in range(600):
            car.advance(1.0 / 60.0)
        assert 0.0 <= car.station <= course.length

    def test_a_circuit_wraps_instead(self) -> None:
        course = _ring()
        car = _car(course=course, station=course.length - 10.0)
        for _ in range(300):
            car.advance(1.0 / 60.0)
        assert car.station < course.length / 2.0


class TestWhatItDoesNext:
    def test_it_cruises_by_default(self) -> None:
        assert _car().state == CRUISING

    def test_it_can_be_made_to_slow_for_something(self) -> None:
        car = _car()
        car.brake_for('a deer')
        assert car.state == SLOWING
        assert car.target_speed() < LIMIT

    def test_slowing_actually_slows_it(self) -> None:
        car = _car()
        for _ in range(600):
            car.advance(1.0 / 60.0)
        fast = car.speed
        car.brake_for('a deer')
        for _ in range(180):
            car.advance(1.0 / 60.0)
        assert car.speed < fast * 0.6

    def test_and_it_gets_going_again(self) -> None:
        car = _car()
        car.brake_for('a deer')
        for _ in range(60 * 9):
            car.advance(1.0 / 60.0)
        assert car.state == CRUISING

    def test_pulling_off_takes_it_off_the_carriageway(self) -> None:
        car = _car()
        car.pull_off()
        for _ in range(60 * 8):
            car.advance(1.0 / 60.0)
        assert car.state == PULLING_OFF
        assert abs(float(car.position()[0])) > 4.0

    def test_and_stops_beside_the_road_rather_than_in_the_trees(self) -> None:
        """A car pulls onto the verge. Where it ends up is measured from the
        road, so the side of it the car was already keeping is part of the
        distance rather than something to add to it -- counted twice, a car
        that pulled off is a car rooted a metre and a half inside the forest.
        """
        course = _course()
        car = _car(course=course)
        car.pull_off()
        for _ in range(60 * 8):
            car.advance(1.0 / 60.0)
        assert abs(float(car.position()[0])) <= course.total_width / 2.0

    def test_and_it_is_off_the_carriageway_all_the_same(self) -> None:
        course = _course()
        car = _car(course=course)
        car.pull_off()
        for _ in range(60 * 8):
            car.advance(1.0 / 60.0)
        assert abs(float(car.position()[0])) > course.carriageway_width / 2.0

    def test_and_it_comes_to_a_stop(self) -> None:
        car = _car()
        car.pull_off()
        for _ in range(60 * 8):
            car.advance(1.0 / 60.0)
        assert car.speed < 0.5

    def test_it_decides_for_itself_as_it_goes(self) -> None:
        """Not scripted: over a few kilometres a car does something."""
        car = _car(course=_ring(), station=0.0)
        seen = set()
        for _ in range(60 * 400):
            car.advance(1.0 / 60.0)
            seen.add(car.state)
        assert len(seen) > 1

    def test_the_same_car_makes_the_same_decisions(self) -> None:
        def run(seed):
            car = TrafficCar(course=_ring(), station=0.0, heading=1,
                             limit=LIMIT, seed=seed)
            out = []
            for _ in range(60 * 200):
                car.advance(1.0 / 60.0)
                out.append(car.state)
            return out
        assert run(7) == run(7)

    def test_two_cars_do_not_make_the_same_ones(self) -> None:
        def run(seed):
            car = TrafficCar(course=_ring(), station=0.0, heading=1,
                             limit=LIMIT, seed=seed)
            out = []
            for _ in range(60 * 200):
                car.advance(1.0 / 60.0)
                out.append(car.state)
            return out
        assert run(7) != run(8)


class TestTheTrafficOnARoad:
    def _traffic(self, **named):
        named.setdefault('course', _ring())
        named.setdefault('seed', 4)
        return Traffic(**named)

    def test_it_starts_with_nothing_on_the_road(self) -> None:
        assert self._traffic().cars == []

    def test_the_first_update_fills_the_road_around_the_player(self) -> None:
        traffic = self._traffic()
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        assert traffic.cars

    def test_they_are_all_near_the_player(self) -> None:
        traffic = self._traffic(reach=250.0)
        at = np.array([300.0, 0.0, 0.0])
        traffic.update(at, 0.0)
        for car in traffic.cars:
            assert float(np.linalg.norm(car.position() - at)) < 320.0

    def test_both_ways(self) -> None:
        """On a road. A circuit is raced one way round -- see
        :class:`TestWhichWayTheTrafficGoes`."""
        traffic = self._traffic(course=_course(length=8000.0, count=801),
                                count=12)
        traffic.update(np.array([0.0, 0.0, 300.0]), 0.0)
        assert {car.heading for car in traffic.cars} == {1, -1}

    def test_none_of_them_is_on_top_of_another(self) -> None:
        traffic = self._traffic(count=12)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        for one in traffic.cars:
            for other in traffic.cars:
                if one is not other and one.heading == other.heading:
                    assert abs(one.station - other.station) > 8.0

    def test_driving_away_replaces_them(self) -> None:
        traffic = self._traffic(reach=200.0)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        first = list(traffic.cars)               # held, or the ids come round again
        assert first
        traffic.update(np.array([-300.0, 0.0, 0.0]), 1.0)
        assert not any(car is other for car in first for other in traffic.cars)

    def test_and_the_new_road_fills_up_as_it_is_driven(self) -> None:
        """Not at once: traffic joins at the edge of the reach and drives in
        from there, so a stretch of road nobody has driven yet is a stretch of
        road with nothing on it -- which is what stops a car appearing in front
        of somebody who was looking at that piece of road a moment ago."""
        traffic = self._traffic(count=8)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        for step in range(300):
            traffic.update(np.array([-300.0 + step * 3.0, 0.0, 0.0]), 0.2)
        assert len(traffic.cars) >= 6

    def test_a_road_with_no_traffic_asked_for_stays_empty(self) -> None:
        traffic = self._traffic(count=0)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        assert traffic.cars == []

    def test_it_says_what_is_in_the_player_s_way(self) -> None:
        traffic = self._traffic(count=10)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        ahead = traffic.ahead_of(np.array([300.0, 0.0, 0.0]),
                                 np.array([0.0, 0.0, 1.0]), reach=400.0)
        assert all(car.heading in (1, -1) for car in ahead)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


class TestTrafficYouCanSeeAndHit:
    """A car nobody can see is a rumour and a car nobody can hit is scenery.

    The body is *kinematic*: it drives its own position rather than being
    pushed about by contacts. What a player needs from it is that it is there
    and that hitting it hurts, and a road full of raycast vehicles buys neither
    of those for four wheels a second of physics each.
    """

    def _fleet(self, **named):
        from omi_physics.world import PhysicsWorld
        world = PhysicsWorld()
        named.setdefault('course', _ring())
        named.setdefault('count', 4)
        named.setdefault('seed', 2)
        return world, Traffic(physics=world, **named)

    def test_each_car_gets_a_node_to_draw(self) -> None:
        _world, traffic = self._fleet()
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        assert len(traffic.node.children) == len(traffic.cars)

    def test_and_a_body_to_hit(self) -> None:
        world, traffic = self._fleet()
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        assert world.live_body_count == len(traffic.cars)

    def test_the_body_is_where_the_car_is(self) -> None:
        world, traffic = self._fleet(count=1)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        car = traffic.cars[0]
        at = world.position[traffic.body_of(car)]
        assert float(np.linalg.norm(np.asarray(at)[[0, 2]]
                                    - car.position()[[0, 2]])) < 0.2

    def test_it_follows_the_car_as_it_drives(self) -> None:
        world, traffic = self._fleet(count=1)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        car = traffic.cars[0]
        before = np.asarray(world.position[traffic.body_of(car)]).copy()
        traffic.update(np.array([300.0, 0.0, 0.0]), 1.0)
        after = np.asarray(world.position[traffic.body_of(car)])
        assert float(np.linalg.norm(after - before)) > 3.0

    def test_a_retired_car_takes_its_body_with_it(self) -> None:
        world, traffic = self._fleet(count=3, reach=400.0)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        traffic.update(np.array([-300.0, 0.0, 0.0]), 1.0)
        assert world.live_body_count == len(traffic.cars) == 3

    def test_and_its_node(self) -> None:
        _world, traffic = self._fleet(count=3, reach=400.0)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        traffic.update(np.array([-300.0, 0.0, 0.0]), 1.0)
        assert len(traffic.node.children) == 3

    def test_a_car_does_not_fall_over(self) -> None:
        """Kinematic: it drives its own position, contacts do not move it."""
        world, traffic = self._fleet(count=1)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        body = traffic.body_of(traffic.cars[0])
        height = float(world.position[body][1])
        for _ in range(120):
            world.step(1.0 / 120.0)
        assert float(world.position[body][1]) == pytest.approx(height, abs=0.01)

    def test_without_physics_it_still_draws(self) -> None:
        traffic = Traffic(course=_ring(), count=2, seed=2)
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        assert len(traffic.node.children) == 2


class TestNotAppearingOnTopOfAnybody:
    """A car put out where the player already is, is not traffic: it is an
    ambush, and a kinematic body shoves a dynamic one off the road."""

    def test_nothing_is_placed_next_to_the_player(self) -> None:
        traffic = Traffic(course=_ring(), count=10, seed=5)
        at = np.array([300.0, 0.0, 0.0])
        traffic.update(at, 0.0)
        assert traffic.cars
        for car in traffic.cars:
            assert float(np.linalg.norm(car.position() - at)) > 60.0

    def test_nor_at_any_point_in_a_lap_of_topping_up(self) -> None:
        """Passing close is the whole idea; *arriving* close is not, so what is
        checked is each car on the frame it first appears. The driver is moving,
        because a road tops up by being driven along."""
        # A ring long enough that the reach is a part of it rather than most
        # of it, so cars really do fall behind and are replaced.
        course = _ring(radius=900.0, count=721)
        traffic = Traffic(course=course, count=8, seed=5)
        seen: set = set()
        for step in range(400):
            at = course.point((step * 3) % len(course.centreline))
            traffic.update(at, 0.1)
            for car in traffic.cars:
                if id(car) not in seen:
                    seen.add(id(car))
                    assert float(np.linalg.norm(car.position() - at)) > 60.0
        assert len(seen) > 8                     # they really were replaced


class TestNotDrivingIntoTheCarInFront:
    """Two cars in one lane at different speeds is one car driving through
    another, and a stationary player on the grid is something the traffic
    behind arrives at. A driver keeps a gap, and closes it no faster than the
    gap allows."""

    def test_nothing_ahead_means_the_limit(self) -> None:
        car = _car()
        car.following(gap=None, speed=0.0)
        assert car.target_speed() == pytest.approx(LIMIT)

    def test_something_far_ahead_is_still_the_limit(self) -> None:
        car = _car()
        car.following(gap=200.0, speed=LIMIT)
        assert car.target_speed() == pytest.approx(LIMIT)

    def test_something_close_slows_it(self) -> None:
        car = _car()
        car.following(gap=18.0, speed=LIMIT * 0.4)
        assert car.target_speed() < LIMIT

    def test_something_stopped_in_the_way_stops_it(self) -> None:
        car = _car()
        car.following(gap=6.0, speed=0.0)
        assert car.target_speed() == pytest.approx(0.0, abs=0.5)

    def test_it_settles_behind_rather_than_into(self) -> None:
        course = _course(length=4000.0, count=401)
        leader = TrafficCar(course=course, station=300.0, heading=1,
                            limit=8.0, seed=1)
        follower = TrafficCar(course=course, station=200.0, heading=1,
                              limit=LIMIT, seed=2)
        for _ in range(60 * 60):
            leader.following(gap=None, speed=0.0)
            follower.following(gap=leader.station - follower.station,
                               speed=leader.speed)
            leader.advance(1.0 / 60.0)
            follower.advance(1.0 / 60.0)
        assert leader.station - follower.station > 4.0

    def test_the_road_keeps_its_own_cars_apart(self) -> None:
        traffic = Traffic(course=_ring(), count=10, seed=9)
        at = np.array([300.0, 0.0, 0.0])
        for _ in range(600):
            traffic.update(at, 0.1)
            for one in traffic.cars:
                for other in traffic.cars:
                    if one is not other and one.heading == other.heading:
                        assert abs(one.station - other.station) > 3.0

    def test_and_does_not_run_the_player_over_from_behind(self) -> None:
        """A car on the grid has not started yet, and the road behind it has to
        notice."""
        course = _ring()
        traffic = Traffic(course=course, count=8, seed=3)
        at = course.lane_point(0, course.driving_lane)
        closest = 1e9
        for _ in range(900):
            traffic.update(at, 0.1)
            for car in traffic.cars:
                closest = min(closest,
                              float(np.linalg.norm(car.position() - at)))
        assert closest > 3.0


class TestWhatIsActuallyInTheWay:
    """A car in the other lane is not in your way, and a car coming the other
    way is not closing on you at the difference of your speeds. Both of those
    read as a crash if the question is asked loosely enough, and a road you
    cannot pass anybody on is not a road."""

    def _straight(self):
        course = _course(length=2000.0, count=201)
        traffic = Traffic(course=course, count=0, seed=1)
        return course, traffic

    def test_something_in_the_other_lane_is_not_ahead(self) -> None:
        course, traffic = self._straight()
        traffic.cars = [TrafficCar(course=course, station=140.0, heading=-1,
                                   limit=LIMIT)]
        at = course.lane_point(10, course.driving_lane)
        assert traffic.ahead_of(at, np.array([0.0, 0.0, 1.0]),
                                reach=200.0) == []

    def test_something_in_this_one_is(self) -> None:
        course, traffic = self._straight()
        traffic.cars = [TrafficCar(course=course, station=140.0, heading=1,
                                   limit=LIMIT)]
        at = course.lane_point(10, course.driving_lane)
        assert len(traffic.ahead_of(at, np.array([0.0, 0.0, 1.0]),
                                    reach=200.0)) == 1

    def test_a_wider_question_finds_both(self) -> None:
        """A driver deciding whether it can swerve wants the whole road."""
        course, traffic = self._straight()
        traffic.cars = [
            TrafficCar(course=course, station=140.0, heading=-1, limit=LIMIT),
            TrafficCar(course=course, station=160.0, heading=1, limit=LIMIT)]
        at = course.lane_point(10, course.driving_lane)
        assert len(traffic.ahead_of(at, np.array([0.0, 0.0, 1.0]), reach=200.0,
                                    width=8.0)) == 2

    def test_a_car_knows_how_fast_it_is_travelling_and_where(self) -> None:
        course, _traffic = self._straight()
        car = TrafficCar(course=course, station=100.0, heading=1, limit=LIMIT,
                         speed=20.0)
        assert float(np.linalg.norm(car.velocity())) == pytest.approx(20.0)
        assert float(np.dot(car.velocity(), car.forward())) > 0.0

    def test_and_one_going_the_other_way_travels_the_other_way(self) -> None:
        course, _traffic = self._straight()
        along = TrafficCar(course=course, station=100.0, heading=1,
                           limit=LIMIT, speed=20.0)
        against = TrafficCar(course=course, station=100.0, heading=-1,
                             limit=LIMIT, speed=20.0)
        assert float(np.dot(along.velocity(), against.velocity())) < 0.0


class TestWhichWayACarIsPointing:
    """The mesh's nose is down -Z, so the yaw that turns it to face a direction
    is not the same as the yaw a heading is quoted in. Get it wrong and every
    car on the road is sideways across it."""

    def test_a_car_going_down_the_road_points_down_it(self) -> None:
        course = _course(length=1000.0, count=101)   # runs towards +Z
        car = TrafficCar(course=course, station=100.0, heading=1, limit=LIMIT)
        assert _pointing(car.heading_angle()) == pytest.approx(
            tuple(car.forward()), abs=1e-6)

    def test_and_one_going_the_other_way_points_the_other_way(self) -> None:
        course = _course(length=1000.0, count=101)
        car = TrafficCar(course=course, station=100.0, heading=-1, limit=LIMIT)
        assert _pointing(car.heading_angle()) == pytest.approx(
            tuple(car.forward()), abs=1e-6)

    def test_on_a_road_running_the_other_axis_too(self) -> None:
        from glisteel.world import Course
        count = 101
        x = np.linspace(0.0, 1000.0, count)
        course = Course(name='road', centreline=np.stack(
            [x, np.zeros(count), np.zeros(count)], axis=-1),
            carriageway_width=7.2, total_width=10.6, closed=False,
            length=1000.0)
        car = TrafficCar(course=course, station=100.0, heading=1, limit=LIMIT)
        assert _pointing(car.heading_angle()) == pytest.approx(
            tuple(car.forward()), abs=1e-6)


def _pointing(yaw):
    """Where the car mesh's nose ends up after a yaw about the vertical."""
    nose = np.array([0.0, 0.0, -1.0])
    turn = np.array([[np.cos(yaw), 0.0, np.sin(yaw)],
                     [0.0, 1.0, 0.0],
                     [-np.sin(yaw), 0.0, np.cos(yaw)]])
    return tuple(turn @ nose)


class TestStandingOnTheRoad:
    """A car is placed by how far along the road it is and how far across it,
    so where its wheels meet the surface is something the road itself answers.

    Asking the physics what is under a car instead answers about whatever is
    standing there -- which includes the car's own collider, a metre of it, so
    the whole fleet bounces between the road and its own roof; and it answers
    about nothing at all where the surface under a car has not been built yet,
    which over a viaduct is the valley floor twenty metres down.
    """

    def _fleet(self, course=None):
        from omi_physics.world import PhysicsWorld
        world = PhysicsWorld()
        return world, Traffic(course=course or _ring(), count=1, seed=2,
                              physics=world)

    def test_a_car_rides_the_road_it_is_on(self) -> None:
        _world, traffic = self._fleet()
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        assert float(traffic._standing(traffic.cars[0])[1]) < 1.5

    def test_and_it_is_hit_about_its_own_middle(self) -> None:
        _world, traffic = self._fleet()
        traffic.update(np.array([300.0, 0.0, 0.0]), 0.0)
        car = traffic.cars[0]
        assert float(traffic._centre(car)[1]) == pytest.approx(
            float(traffic._standing(car)[1]) + car.kind.height / 2.0)

    def test_it_stands_on_the_surface_rather_than_on_the_crown(self) -> None:
        """A road is crowned so that it drains, and a car keeping its own side
        of one stands lower than the middle of it by the camber."""
        course = _course()
        car = _car(course=course, station=100.0)
        drop = course.road_profile().section_offset(car.lane)
        assert float(car.position()[1]) == pytest.approx(float(drop), abs=1e-6)
        assert float(drop) < 0.0

    def test_and_a_car_pulled_onto_the_verge_stands_on_the_verge(self) -> None:
        course = _course()
        car = _car(course=course)
        car.pull_off()
        for _ in range(60 * 8):
            car.advance(1.0 / 60.0)
        across = abs(float(car.position()[0]))
        assert float(car.position()[1]) == pytest.approx(
            float(course.road_profile().section_offset(across)), abs=1e-6)

    def test_a_car_climbing_rides_the_line_it_is_on(self) -> None:
        """Between two points of the centreline as well as at them: a fleet
        that only knows the sampled heights hops from one to the next."""
        rising = _course()
        rising.centreline[:, 1] = rising.centreline[:, 2] * 0.05
        heights = []
        car = _car(course=rising, station=100.0)
        for _ in range(200):
            car.station += 0.25
            heights.append(float(car.position()[1]))
        steps = np.diff(heights)
        assert float(steps.max() - steps.min()) < 1e-6


class TestWhatTheTrafficIsMadeOf:
    """Five kinds of vehicle, each its own size to see and to hit."""

    def _traffic(self, physics=None, count=5):
        course = _course()
        return Traffic(course, count=count, seed=3, physics=physics)

    def test_a_car_is_one_of_the_kinds(self) -> None:
        traffic = self._traffic()
        traffic.update((0.0, 0.0, 0.0), 0.1)
        assert traffic.cars
        for car in traffic.cars:
            assert car.kind in models.TRAFFIC

    def test_the_kinds_are_not_all_the_same(self) -> None:
        """A road of one model repeated is a convoy, not traffic."""
        traffic = self._traffic(count=10)
        traffic.update((0.0, 0.0, 0.0), 0.1)
        assert len({car.kind.name for car in traffic.cars}) > 1

    def test_it_draws_the_model_its_kind_names(self) -> None:
        traffic = self._traffic(count=1)
        traffic.update((0.0, 0.0, 0.0), 0.1)
        car = traffic.cars[0]
        drawn = traffic.node_of(car)
        names = _names(drawn)
        assert models.BODY in names and models.GLASS in names
        assert models.SEATS in names, 'nobody is sitting in it'

    def test_each_car_is_painted_its_own_colour(self) -> None:
        """One model repainted, and only its paint: the glass stays glass."""
        traffic = self._traffic(count=6)
        traffic.update((0.0, 0.0, 0.0), 0.1)
        painted = {tuple(round(float(v), 3) for v in _material(traffic, car, models.PAINT))
                   for car in traffic.cars}
        assert len(painted) > 1
        glass = {tuple(round(float(v), 3) for v in _material(traffic, car, models.GLASS))
                 for car in traffic.cars}
        assert len(glass) == 1

    def test_a_van_is_as_big_to_hit_as_it_is_to_see(self) -> None:
        """The collider comes from the kind's own dimensions, not one box for all."""
        world = PhysicsWorld()
        traffic = self._traffic(physics=world, count=10)
        traffic.update((0.0, 0.0, 0.0), 0.1)
        sizes = {car.kind.name: traffic.collider_size(car) for car in traffic.cars}
        assert len(set(sizes.values())) > 1
        for name, size in sizes.items():
            kind = next(one for one in models.TRAFFIC if one.name == name)
            assert size == pytest.approx(kind.size(), abs=1e-6)

    def test_it_stands_on_the_road_rather_than_in_it(self) -> None:
        """The model's origin is where it meets the road."""
        traffic = self._traffic(count=1)
        traffic.update((0.0, 0.0, 0.0), 0.1)
        car = traffic.cars[0]
        assert traffic.node_of(car).translation[1] == pytest.approx(
            float(car.position()[1]), abs=1e-6)


def _names(node, out=None):
    out = [] if out is None else out
    if getattr(node, 'DEF', ''):
        out.append(node.DEF)
    for child in getattr(node, 'children', None) or ():
        _names(child, out)
    return out


def _material(traffic, car, name):
    scene = traffic.art_of(car)
    return scene.materials[name].baseColor


class TestOneModelPaintedManyWays:
    """A road's worth of traffic is a handful of versions of five models.

    Reading and parsing a ``.glb`` costs about a frame, and cars are put out and
    retired the whole way round a lap -- so a car that loaded its own art would
    arrive with a stutter every time one did. The paint comes from a fixed
    palette, so there is a small number of (model, colour) pairs however many
    cars are on the road.
    """

    def _road(self, count=8):
        traffic = Traffic(_ring(), count=count, seed=3)
        traffic.update(traffic.course.point(0), 0.1)
        return traffic

    def test_two_cars_of_a_kind_and_a_colour_share_one_scene(self):
        traffic = self._road()
        by_look = {}
        for car in traffic.cars:
            by_look.setdefault((car.kind.name, car.paint), []).append(
                traffic.art_of(car))
        shared = [scenes for scenes in by_look.values() if len(scenes) > 1]
        assert all(scene is scenes[0] for scenes in shared for scene in scenes)

    def test_there_are_never_more_scenes_than_kinds_times_colours(self):
        traffic = self._road(count=20)
        scenes = {id(traffic.art_of(car)) for car in traffic.cars}
        assert len(scenes) <= len(models.TRAFFIC) * 6

    def test_a_car_is_painted_the_colour_it_asked_for(self):
        traffic = self._road()
        for car in traffic.cars:
            scene = traffic.art_of(car)
            if scene is None:
                continue
            paint = scene.materials.get(models.PAINT)
            if paint is not None:
                assert tuple(paint.baseColor)[:3] == pytest.approx(car.paint)

    def test_every_car_still_gets_its_own_place_to_stand(self):
        """Shared art, separate transforms: they are in different places."""
        traffic = self._road()
        nodes = [id(traffic.node_of(car)) for car in traffic.cars]
        assert len(set(nodes)) == len(nodes)

    def test_all_of_them_are_mounted(self):
        traffic = self._road()
        assert len(traffic.node.children) == len(traffic.cars)


class TestTheRoadIsNotEmpty:
    def test_a_road_carries_traffic_unless_it_is_told_not_to(self):
        """Traffic is what makes one lap different from the last one."""
        assert DEFAULT_TRAFFIC > 0

    def test_and_the_game_starts_with_that_much(self):
        from glisteel.game import build_parser
        assert build_parser().parse_args(['w.json']).traffic == DEFAULT_TRAFFIC

    def test_an_empty_circuit_is_still_askable_for(self):
        from glisteel.game import build_parser
        assert build_parser().parse_args(['w.json', '--traffic', '0']).traffic == 0


class TestTrafficComesFromBeyondWhatCanBeSeen:
    """A car that appears a hundred metres up the road is a car that was not
    there a moment ago, and a driver deciding whether to pass has no way to know
    the road is clear if the road can grow cars in front of them. New traffic
    joins at the edge of the reach and drives in from there.
    """

    def _traffic(self, count=8, course=None):
        from glisteel.traffic import Traffic
        course = course if course is not None else _course(length=8000.0,
                                                           count=801)
        traffic = Traffic(course, count=count, seed=3)
        traffic.update(course.point(0), 0.0)
        return traffic

    def test_nothing_is_placed_where_a_driver_would_see_it_arrive(self) -> None:
        from glisteel.traffic import EDGE_BAND
        traffic = self._traffic()
        here = traffic._station_of(traffic.course.point(0))
        for car in traffic.cars:
            gap = traffic._gap(here, car.station)
            assert gap >= traffic.reach - EDGE_BAND - 1.0, (
                'a car appeared %.0f m away, inside what a driver has road '
                'for' % gap)

    def test_the_band_holds_the_traffic_that_has_to_join_through_it(self
                                                                   ) -> None:
        """Every car alive arrives through it, and the ones that have to keep
        :data:`HEADWAY` from each other are those going the same way on the
        same side -- a quarter of a two-way road's traffic. A band too narrow
        for them is a road that never fills up."""
        from glisteel.traffic import DEFAULT_TRAFFIC, EDGE_BAND, HEADWAY
        together = max(DEFAULT_TRAFFIC // 4, 1)
        assert EDGE_BAND >= HEADWAY * together, (
            '%d m of band for %d cars %d m apart'
            % (EDGE_BAND, together, HEADWAY))

    def test_the_road_fills_up_as_the_driver_goes_down_it(self) -> None:
        """Only a few fit in the band at once, so a road is populated by being
        driven along rather than by being conjured whole."""
        from glisteel.traffic import Traffic
        course = _course(length=20000.0, count=2001)
        traffic = Traffic(course, count=8, seed=3)
        for step in range(400):
            traffic.update(course.point(step * 4), 0.2)
        assert len(traffic.cars) >= 6

    def test_both_ways_along_the_road(self) -> None:
        traffic = self._traffic(count=12)
        assert {car.heading for car in traffic.cars} == {-1, 1}


class TestWhichWayTheTrafficGoes:
    """A road carries traffic both ways, and a circuit is a road.

    What makes passing worth anything is that the lane you pass in is the lane
    somebody else is coming down. Take that away and the other lane is just
    more road: there is no reason to come back to your own, no decision to get
    right, and the time a pass buys costs nothing to take.
    """

    def _filled(self, course, count=10):
        traffic = Traffic(course, count=count, seed=3)
        for step in range(60):
            self.at = course.point(step)
            traffic.update(self.at, 0.2)
        return traffic

    def test_a_circuit_carries_traffic_both_ways(self) -> None:
        traffic = self._filled(_ring(), count=12)
        assert traffic.two_way
        assert {car.heading for car in traffic.cars} == {-1, 1}

    def test_and_so_does_an_open_road(self) -> None:
        traffic = self._filled(_course(length=8000.0, count=801), count=12)
        assert traffic.two_way
        assert {car.heading for car in traffic.cars} == {-1, 1}

    def test_a_caller_can_ask_for_a_road_with_one_side(self) -> None:
        traffic = self._filled(_ring(), count=8)
        one_way = Traffic(_ring(), count=8, seed=3, two_way=False)
        one_way.update(_ring().point(0), 0.0)
        assert traffic.two_way and not one_way.two_way
        assert {car.heading for car in one_way.cars} == {1}


class TestHowMuchTrafficMakesARace:
    def test_it_is_worked_out_from_how_often_a_racer_wants_to_meet_one(self):
        from glisteel.traffic import cars_for
        assert cars_for(seconds=5.0) > cars_for(seconds=20.0)

    def test_a_road_with_traffic_coming_the_other_way_needs_more_of_it(self):
        from glisteel.traffic import cars_for
        assert cars_for(two_way=True) > cars_for(two_way=False)

    def test_a_faster_racer_catches_them_sooner_and_needs_fewer(self):
        from glisteel.traffic import cars_for
        assert cars_for(racing=80.0) < cars_for(racing=40.0)

    def test_there_is_always_at_least_one(self):
        from glisteel.traffic import cars_for
        assert cars_for(seconds=1e6) == 1


class TestWhatIsAheadIsAheadOnTheRoad:
    """Measured along the road, not along the way the car happens to point.

    A straight line from the nose leaves the road at the first bend, so a car
    a couple of hundred metres up a curving road is off that line and reads as
    "nothing in front" -- until the bend brings it onto the line, all at once,
    inside braking distance. A driver looking at a road sees what is on it.
    """

    def _ring(self, radius=200.0, count=256):
        angle = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
        line = np.stack([np.cos(angle) * radius, np.zeros(count),
                         np.sin(angle) * radius], axis=-1)
        return Course(name='ring', centreline=line, carriageway_width=7.2,
                      total_width=10.6, closed=True,
                      length=float(2.0 * np.pi * radius))

    def _traffic(self, course, at):
        traffic = Traffic(course, count=0, seed=1)
        traffic.cars = [TrafficCar(course, station=at, heading=1,
                                   limit=LIMIT, seed=2)]
        return traffic

    def _looking(self, course, station=0.0):
        """Where a car at that station is, in its own lane, and which way it
        points -- because which lane something is in is measured from where the
        driver is, not from the crown of the road."""
        index = int(np.searchsorted(course.stations, station))
        return (course.lane_point(index, course.driving_lane),
                course.point(index + 1) - course.point(index))

    def test_a_car_round_the_bend_is_in_front(self) -> None:
        course = self._ring()
        traffic = self._traffic(course, at=180.0)
        at, way = self._looking(course)
        assert traffic.ahead_of(at, way, reach=300.0)

    def test_and_one_further_round_than_the_reach_is_not(self) -> None:
        course = self._ring()
        traffic = self._traffic(course, at=400.0)
        at, way = self._looking(course)
        assert not traffic.ahead_of(at, way, reach=300.0)

    def test_one_behind_is_not_in_front(self) -> None:
        course = self._ring()
        traffic = self._traffic(course, at=course.length - 100.0)
        at, way = self._looking(course)
        assert not traffic.ahead_of(at, way, reach=300.0)

    def test_nor_is_one_in_the_other_lane(self) -> None:
        course = self._ring()
        traffic = self._traffic(course, at=180.0)
        traffic.cars[0].heading = -1
        at, way = self._looking(course)
        assert not traffic.ahead_of(at, way, reach=300.0)

    def test_unless_the_whole_road_was_asked_about(self) -> None:
        course = self._ring()
        traffic = self._traffic(course, at=180.0)
        traffic.cars[0].heading = -1
        at, way = self._looking(course)
        assert traffic.ahead_of(at, way, reach=300.0,
                                width=course.carriageway_width)

    def test_they_come_back_nearest_first(self) -> None:
        course = self._ring()
        traffic = self._traffic(course, at=90.0)
        for station in (250.0, 40.0, 160.0):
            traffic.cars.append(TrafficCar(course, station=station, heading=1,
                                           limit=LIMIT, seed=3))
        at, way = self._looking(course)
        found = [car.station for car in traffic.ahead_of(at, way, reach=300.0)]
        assert found == sorted(found)

    def test_a_driver_going_the_other_way_looks_the_other_way(self) -> None:
        """Which way is *forward* is still the car's own, so somebody turned
        round on the road is not told the road behind them is in front."""
        course = self._ring()
        traffic = self._traffic(course, at=180.0)
        at, way = self._looking(course)
        assert not traffic.ahead_of(at, -way, reach=300.0)
