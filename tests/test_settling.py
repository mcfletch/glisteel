"""Handing the player a car that is already standing on the grid.

The car is put over the grid and dropped onto it before anybody sees it, because
one that lands on a slope with the brake off is already rolling by the time the
player takes it. What that must not be is a fixed number of physics steps spent
whatever the car is doing: the drop is over in a fraction of a second, and the
rest is a machine simulating a car that is standing still -- once when the
session is built and again on every restart, where it is a visible hitch.
"""
import pytest

from glisteel import scenarios
from glisteel.session import PHYSICS_STEP, SETTLE_SECONDS, Session


class _Counted:
    """A physics world that says how many steps were taken through it."""

    def __init__(self, real):
        self._real = real
        self.steps = 0

    def step(self, dt):
        self.steps += 1
        return self._real.step(dt)

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def world():
    return scenarios.straight().world()


class TestTheCarIsStandingWhenItIsHandedOver:
    def test_it_is_on_its_wheels(self, world) -> None:
        session = Session(world)
        assert not session.car.upside_down()

    def test_it_is_not_moving(self, world) -> None:
        session = Session(world)
        assert session.car.speed() < 0.5

    def test_it_is_not_still_falling(self, world) -> None:
        session = Session(world)
        assert abs(float(session.car.velocity()[1])) < 0.5

    def test_it_is_on_the_road_rather_than_over_it(self, world) -> None:
        session = Session(world)
        # Dropped from six metres; if it were handed over mid-fall it would
        # still be up there.
        assert session.car.position[1] < 2.0

    def test_a_restart_puts_it_back_the_same_way(self, world) -> None:
        session = Session(world)
        session.car.place((30.0, 12.0, 0.0), 0.0)
        session.restart()
        assert session.car.speed() < 0.5
        assert session.car.position[1] < 2.0


class TestItDoesNotSimulateAFallItCouldHaveAvoided:
    """The car is put where the road is rather than six metres over it.

    Dropping it from a height and waiting means simulating a second of free fall
    before anybody sees the car -- once when the session is built, and again on
    every restart, where the player is waiting for it. Where the ground is is a
    question the world can answer.
    """

    #: A quarter of the fixed budget: the drop is short, and what is left is
    #: the suspension taking up.
    BUDGET = int(SETTLE_SECONDS / PHYSICS_STEP)

    def test_building_a_session_costs_a_fraction_of_the_budget(self, world) -> None:
        world.physics = _Counted(world.physics)
        Session(world)
        assert world.physics.steps < self.BUDGET // 3, \
            'took %d of %d steps' % (world.physics.steps, self.BUDGET)

    def test_a_restart_costs_a_fraction_of_it_too(self, world) -> None:
        session = Session(world)
        world.physics = _Counted(world.physics)
        session.restart()
        assert world.physics.steps < self.BUDGET // 3, \
            'took %d of %d steps' % (world.physics.steps, self.BUDGET)

    def test_it_still_gives_the_car_time_to_land(self, world) -> None:
        world.physics = _Counted(world.physics)
        Session(world)
        assert world.physics.steps > 5

    def test_a_world_that_cannot_say_where_its_ground_is_still_works(self) -> None:
        """Nothing under the grid: the car is dropped from the old height."""
        one = scenarios.straight().world()
        one.ground_under = lambda at, reach=200.0, skip=(): None
        session = Session(one)
        assert not session.car.upside_down()
