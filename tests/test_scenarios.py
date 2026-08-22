"""Small pieces of road to drive, and the ground under them.

A scenario is a few hundred metres of road with one question in it: does the
wheel come back to centre on a straight, does the car stay on the deck through a
chicane, does it get over a crest with its wheels down. Everything in one is
real -- the course the game reads, the carriageway's own collider, the ground's
height field -- so what a test drives is what a player drives, cut down to the
part that answers the question.
"""

import math

import numpy as np
import pytest

from glisteel import scenarios

STEP = 1.0 / 120.0


class TestAPieceOfRoad:
    def test_a_straight_runs_where_its_plan_does(self) -> None:
        piece = scenarios.straight(length=200.0)
        line = piece.centreline()
        assert len(line) > 2
        assert float(np.linalg.norm(line[-1] - line[0])) == pytest.approx(
            200.0, rel=0.02)

    def test_it_is_flat_unless_it_says_otherwise(self) -> None:
        assert np.allclose(scenarios.straight().centreline()[:, 1], 0.0)

    def test_a_crest_is_not(self) -> None:
        heights = scenarios.crest().centreline()[:, 1]
        assert float(heights.max() - heights.min()) > 1.0

    def test_a_circuit_returns_to_where_it_started(self) -> None:
        piece = scenarios.circuit()
        assert piece.closed
        assert piece.course().closed

    def test_the_course_carries_the_road_s_width(self) -> None:
        piece = scenarios.straight()
        assert piece.course().carriageway_width == piece.carriageway_width

    def test_every_named_scenario_builds_a_course(self) -> None:
        for name in scenarios.CATALOGUE:
            course = scenarios.named(name).course()
            assert len(course.centreline) >= 2, name
            assert course.length > 0.0, name


class TestTheGroundUnderIt:
    def test_a_car_dropped_on_the_road_lands_on_it(self) -> None:
        """It comes to rest on its wheels on the surface, not through it and
        not hovering over it."""
        world = scenarios.straight().world()
        start, heading = world.course.grid_position(height=1.0)
        surface = float(start[1]) - 1.0
        car = _settled(world, start, heading)
        assert surface + 0.2 < car.position[1] < surface + 1.2

    def test_and_stays_on_the_carriageway(self) -> None:
        world = scenarios.straight().world()
        start, heading = world.course.grid_position(height=1.0)
        car = _settled(world, start, heading)
        assert world.course.on_road(car.position)

    def test_a_car_dropped_beside_it_lands_on_the_ground(self) -> None:
        """Off the carriageway there is still a world to stand on: a car that
        runs wide slides onto grass, not into nothing."""
        world = scenarios.straight().world()
        start, heading = world.course.grid_position(height=1.0)
        beside = np.asarray(start, dtype='d') + np.array([14.0, 0.0, 0.0])
        car = _settled(world, beside, heading)
        assert car.position[1] > -2.0

    def test_the_ground_follows_a_crest(self) -> None:
        world = scenarios.crest().world()
        course = world.course
        top = int(np.argmax(course.centreline[:, 1]))
        above = course.point(top) + np.array([0.0, 5.0, 0.0])
        world.stream(tuple(float(v) for v in above), 720.0)
        under = world.ground_under(above)
        assert under is not None
        assert under == pytest.approx(float(course.point(top)[1]), abs=1.6)


class TestWhatAScenarioCarries:
    def test_by_default_there_is_nothing_to_hit(self) -> None:
        world = scenarios.straight().world()
        assert world.props.props == []

    def test_boulders_can_be_put_on_the_verges(self) -> None:
        world = scenarios.verge().world()
        assert world.props.props

    def test_and_they_stand_up_when_the_car_is_near_them(self) -> None:
        world = scenarios.verge().world()
        world.stream(tuple(float(v) for v in world.course.point(0)), 720.0)
        assert world.props.standing

    def test_traffic_can_be_put_on_the_road(self) -> None:
        world = scenarios.circuit().world(traffic=4)
        assert world.traffic is not None

    def test_and_an_empty_road_has_none(self) -> None:
        assert scenarios.circuit().world().traffic is None


def _settled(world, position, heading, seconds=2.0):
    """A car dropped at a point and left to find the ground."""
    from glisteel.car import Car
    world.stream(tuple(float(v) for v in position), 720.0)
    car = Car(world.physics, position=position, heading=heading)
    for _ in range(int(seconds / STEP)):
        car.update(STEP)
        world.physics.step(STEP)
    return car


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


class TestARoadWithSomewhereToPassOnIt:
    """A ring is a road a driver can never see far enough along to overtake on:
    the view round a bend of radius *r* runs `sqrt(8 * r * clear)`, which on a
    circuit small enough to test with is a hundred metres, and getting by an
    80 km/h car at racing speed wants half as much again.

    An *oval* has straights, which is where a pass happens on any real circuit.
    A test about a driver deciding to overtake needs a road the manoeuvre fits
    on, or it is a test about the road.
    """

    def _course(self, piece):
        from glisteel.world import Course
        line = np.stack([piece.plan[:, 0], np.zeros(len(piece.plan)),
                         piece.plan[:, 1]], axis=-1)
        steps = np.linalg.norm(np.diff(line, axis=0), axis=1)
        return Course(name=piece.name, centreline=line, carriageway_width=7.2,
                      total_width=10.6, closed=True,
                      length=float(steps.sum()))

    def test_it_is_a_closed_lap_like_any_other_circuit(self) -> None:
        piece = scenarios.oval()
        assert piece.closed and len(piece.plan) > 16

    def test_it_joins_up(self) -> None:
        """Every step of the same size, including the one that closes it: a
        plan with a jump in it is a road with a jump in it, and a car put on
        the start line of one never gets going."""
        plan = scenarios.oval().plan
        steps = np.linalg.norm(np.diff(np.vstack([plan, plan[:1]]), axis=0),
                               axis=1)
        assert steps.max() < 2.0 * steps.min(), (
            'steps run from %.1f m to %.1f m' % (steps.min(), steps.max()))

    def test_and_it_goes_round_once(self) -> None:
        """Not back on itself: the plan turns through a full circle and no
        more, which is what makes it one lap rather than a figure of eight."""
        plan = scenarios.oval().plan
        step = np.diff(np.vstack([plan, plan[:2]]), axis=0)
        angle = np.unwrap(np.arctan2(step[:, 1], step[:, 0]))
        assert abs(angle[-1] - angle[0]) == pytest.approx(2.0 * math.pi,
                                                          abs=0.2)

    def test_and_a_driver_can_see_a_long_way_down_its_straights(self) -> None:
        course = self._course(scenarios.oval())
        assert course._sight.max() > 300.0

    def test_which_a_ring_of_the_same_size_cannot(self) -> None:
        ring = self._course(scenarios.circuit(radius_x=400.0, radius_z=300.0))
        assert ring._sight.max() < 200.0

    def test_it_is_in_the_catalogue_by_name(self) -> None:
        assert scenarios.named('oval').name == 'oval'
