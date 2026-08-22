"""A course whose corners lean, and the car that has to drive them.

The baker writes the road's superelevation beside its centreline, because a
game that builds the carriageway itself -- which this one does, for the
collider under the wheels -- has to build the road that was drawn. What is here
is that the lean survives the trip, and that everything placed *on* the road by
how far along and how far across it is lands on the surface rather than through
it.
"""
import numpy as np
import pytest

from glisteel.world import Course, courses_in


def _line(count=41, length=400.0):
    z = np.linspace(0.0, -length, count)
    return np.stack([np.zeros(count), np.zeros(count), z], axis=-1)


def _course(bank=None, **kwargs):
    return Course(name='road', centreline=_line(), carriageway_width=7.2,
                  total_width=12.6, closed=False, length=400.0,
                  bank=(np.zeros(41) if bank is None else np.full(41, bank)),
                  **kwargs)


class TestReadingTheLeanOutOfAWorld:
    def _read(self, road):
        document = {'extras': {'roads': [dict(
            {'name': 'r', 'centreline': [[0, 0, 0], [0, 0, -10], [0, 0, -20]],
             'closed': False, 'length': 20.0}, **road)]}}
        return courses_in(document)[0]

    def test_a_world_that_wrote_one_carries_it(self) -> None:
        found = self._read({'bank': [0.0, 0.1, 0.2]})
        assert found.bank_at(1) == pytest.approx(0.1)

    def test_a_world_that_wrote_none_reads_as_flat(self) -> None:
        assert self._read({}).bank_at(1) == 0.0

    def test_a_lean_that_does_not_match_the_line_is_dropped(self) -> None:
        """A road half described is a road driven flat, not a road that raises
        on the first corner."""
        assert self._read({'bank': [0.1, 0.2]}).bank_at(1) == 0.0


class TestTheWayAcrossABankedRoad:
    def test_a_level_road_is_crossed_flat(self) -> None:
        assert _course().across(4)[1] == pytest.approx(0.0)

    def test_a_banked_road_is_crossed_downhill_to_its_right(self) -> None:
        across = _course(0.25).across(4)
        assert across[1] < 0.0
        assert np.linalg.norm(across) == pytest.approx(1.0)

    def test_it_leans_by_the_lean_it_was_given(self) -> None:
        across = _course(0.25).across(4)
        assert across[1] / np.hypot(across[0], across[2]) == pytest.approx(-0.25)

    def test_the_other_way_round_it_leans_the_other_way(self) -> None:
        assert _course(-0.25).across(4)[1] > 0.0


class TestPlacingSomethingOnABankedRoad:
    def test_a_car_on_the_high_side_stands_above_the_crown(self) -> None:
        course = _course(0.25)
        at = course.lane_point(4, -3.0)          # to the road's left
        assert at[1] > course.point(4)[1]

    def test_a_car_on_the_low_side_stands_below_it(self) -> None:
        course = _course(0.25)
        assert course.lane_point(4, 3.0)[1] < course.point(4)[1]

    def test_the_camber_is_used_up_by_the_lean(self) -> None:
        """Past the crossfall there is no crown left to drop off."""
        course = _course(0.25)
        assert course.surface_offset(3.0, bank=0.25) == pytest.approx(0.0)
        assert course.surface_offset(3.0, bank=0.0) < 0.0


class TestHowFastABankedCourseSaysItsCornersAre:
    def _bent(self, bank):
        angle = np.linspace(0.0, np.pi / 2, 41)
        line = np.stack([200.0 * np.cos(angle), np.zeros(41),
                         -200.0 * np.sin(angle)], axis=-1)
        return Course(name='r', centreline=line, carriageway_width=7.2,
                      total_width=12.6, closed=False, length=314.0,
                      bank=np.full(41, bank))

    def test_a_banked_corner_is_faster_than_the_same_corner_flat(self) -> None:
        assert self._bent(0.3).corner_speed(20) > self._bent(0.0).corner_speed(20)

    def test_the_sign_before_it_says_so_too(self) -> None:
        assert self._bent(0.3).caution_speed(20) > self._bent(0.0).caution_speed(20)


class TestTheColliderUnderTheWheels:
    """The surface the car rides is swept from the course, and the course is
    what everything else places a car by. If the two disagree on a banked
    corner the car sinks into the road on one side of the crown and floats over
    it on the other, so what these assert is that they agree."""

    def _corner(self, bank):
        """A quarter circle to the right, banked or not, and its collider."""
        from omi_physics.world import PhysicsWorld
        from OpenGLContext.physics.road import RoadColliders
        angle = np.linspace(0.0, np.pi / 2, 60)
        line = np.stack([300.0 - 300.0 * np.cos(angle), np.full(60, 20.0),
                         -300.0 * np.sin(angle)], axis=-1)
        course = Course(name='r', centreline=line, carriageway_width=7.2,
                        total_width=12.6, closed=False, length=471.0,
                        bank=bank(line))
        world = PhysicsWorld()
        RoadColliders(world, line, course.road_profile(), closed=False,
                      bank=course.bank).update(line[30])
        return course, world

    def _gaps(self, bank):
        """How far the collider is from where the course says the road is."""
        from omi_physics.raycast import raycast
        course, world = self._corner(bank)
        found = []
        for index in range(10, 50):
            for across in (-3.0, 0.0, 3.0):
                want = course.lane_point(index, across)
                # Straight down onto it from above, which is where a wheel is.
                hit = raycast(world, np.array([want[0], want[1] + 5.0, want[2]]),
                              np.array([0.0, -1.0, 0.0]), 20.0)
                if hit is not None:
                    found.append(abs(want[1] + 5.0 - hit.distance - want[1]))
        return np.asarray(found)

    def test_a_corner_that_leans_has_a_collider_that_leans_with_it(self) -> None:
        from OpenGLContext.scenegraph.road import bank_profile
        gaps = self._gaps(lambda line: bank_profile(line, speed=200 / 3.6))
        assert len(gaps) > 100, "the ray found no road to land on"
        assert gaps.max() < 0.01

    def test_a_flat_corner_is_no_worse_off_for_the_machinery(self) -> None:
        gaps = self._gaps(lambda line: np.zeros(len(line)))
        assert len(gaps) > 100
        assert gaps.max() < 0.01

    def test_a_collider_swept_flat_under_a_banked_road_does_not_line_up(self) -> None:
        """What the lean is *for*: without it the two disagree by most of the
        road's own width times the lean."""
        from omi_physics.raycast import raycast
        from OpenGLContext.physics.road import RoadColliders
        course, _world = self._corner(
            lambda line: np.full(len(line), 0.10))
        from omi_physics.world import PhysicsWorld
        flat = PhysicsWorld()
        RoadColliders(flat, course.centreline, course.road_profile(),
                      closed=False).update(course.centreline[30])
        want = course.lane_point(30, 3.0)
        hit = raycast(flat, np.array([want[0], want[1] + 5.0, want[2]]),
                      np.array([0.0, -1.0, 0.0]), 20.0)
        assert hit is not None
        assert abs(want[1] + 5.0 - hit.distance - want[1]) > 0.2
