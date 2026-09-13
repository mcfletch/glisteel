"""Where a structure is, over ground sampled on a grid.

A field terrain asks this about every sample of a chunk at once -- tens of
thousands of points against a road that may be thousands of points long -- so
the answer has to come back without materialising a point-by-point distance
matrix between the two. What is asserted here is the answer, and that asking
about a lot of ground at once does not cost a lot of memory.
"""
import numpy as np
import pytest

from glisteel.world import Course, Structure


def _road(points=400, length=4000.0, structures=()):
    line = np.stack([np.linspace(0.0, length, points), np.zeros(points),
                     np.zeros(points)], axis=-1)
    return Course(name='road', centreline=line, carriageway_width=7.0,
                  total_width=12.0, closed=False, length=length,
                  structures=tuple(structures))


BORE = Structure(kind='tunnel', start=1000.0, end=2000.0)


class TestWhichGroundIsOverAStructure:
    def test_ground_over_the_bore_is_inside_it(self) -> None:
        course = _road(structures=[BORE])
        assert bool(course.inside('tunnel', 1500.0, 0.0))

    def test_ground_before_it_is_not(self) -> None:
        course = _road(structures=[BORE])
        assert not bool(course.inside('tunnel', 500.0, 0.0))

    def test_ground_after_it_is_not(self) -> None:
        course = _road(structures=[BORE])
        assert not bool(course.inside('tunnel', 3000.0, 0.0))

    def test_ground_beside_it_is_not(self) -> None:
        course = _road(structures=[BORE])
        assert not bool(course.inside('tunnel', 1500.0, 200.0))

    def test_the_margin_widens_it(self) -> None:
        course = _road(structures=[BORE])
        beside = course.total_width / 2.0 + 1.0
        assert not bool(course.inside('tunnel', 1500.0, beside))
        assert bool(course.inside('tunnel', 1500.0, beside, margin=3.0))

    def test_along_extends_it_up_the_approaches(self) -> None:
        course = _road(structures=[BORE])
        assert not bool(course.inside('tunnel', 980.0, 0.0))
        assert bool(course.inside('tunnel', 980.0, 0.0, along=40.0))

    def test_a_road_with_no_such_structure_answers_no(self) -> None:
        assert not bool(_road().inside('tunnel', 1500.0, 0.0))

    def test_it_answers_in_the_shape_it_was_asked(self) -> None:
        course = _road(structures=[BORE])
        x, z = np.meshgrid(np.linspace(0.0, 3000.0, 40),
                           np.linspace(-30.0, 30.0, 25))
        found = course.inside('tunnel', x, z)
        assert found.shape == x.shape
        assert found.dtype == bool

    def test_a_grid_agrees_with_asking_one_point_at_a_time(self) -> None:
        course = _road(structures=[BORE])
        x, z = np.meshgrid(np.linspace(800.0, 2200.0, 21),
                           np.linspace(-20.0, 20.0, 11))
        grid = course.inside('tunnel', x, z, margin=2.0, along=24.0)
        for row in range(x.shape[0]):
            for col in range(x.shape[1]):
                one = course.inside('tunnel', x[row, col], z[row, col],
                                    margin=2.0, along=24.0)
                assert bool(grid[row, col]) == bool(one)

    def test_two_bores_are_both_found(self) -> None:
        course = _road(structures=[BORE,
                                   Structure(kind='tunnel', start=3000.0,
                                             end=3500.0)])
        assert bool(course.inside('tunnel', 1500.0, 0.0))
        assert bool(course.inside('tunnel', 3200.0, 0.0))
        assert not bool(course.inside('tunnel', 2500.0, 0.0))


class TestAskingAboutALotOfGround:
    def test_a_chunk_of_terrain_does_not_cost_a_matrix(self) -> None:
        """The intermediate has to be bounded, not samples x road points."""
        import tracemalloc
        course = _road(points=900, structures=[BORE])
        side = 320
        x, z = np.meshgrid(np.linspace(-100.0, 4100.0, side),
                           np.linspace(-200.0, 200.0, side))
        tracemalloc.start()
        found = course.inside('tunnel', x, z, margin=2.0)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert found.shape == x.shape
        # A point-by-point matrix over this grid is 102400 x ~230 x 2 doubles,
        # which is hundreds of megabytes; the answer itself is 100 kB.
        assert peak < 64e6, 'peak was %.0f MB' % (peak / 1e6)


class TestWhatHasAnEdgeToFallOff:
    """A car that runs wide on a deck goes off it. The barrier the structure is
    drawn with is what stops that, and the collider has to have one too."""

    @staticmethod
    def _course(*kinds):
        from glisteel.world import Course, Structure
        line = np.stack([np.zeros(9), np.zeros(9),
                         -np.arange(9) * 10.0], axis=-1)
        return Course(name='r', centreline=line, carriageway_width=7.2,
                      total_width=12.6, closed=False, length=80.0,
                      structures=tuple(
                          Structure(kind=kind, start=10.0 * at,
                                    end=10.0 * at + 20.0)
                          for at, kind in enumerate(kinds)))

    def test_a_deck_has_one(self) -> None:
        assert self._course('bridge').edges() == ((0.0, 20.0),)

    def test_a_causeway_has_one(self) -> None:
        assert self._course('causeway').edges() == ((0.0, 20.0),)

    def test_a_bore_does_not(self) -> None:
        """What is beside a tunnel is the hillside it is driven through, and a
        wall in there is a wall in the middle of the road."""
        assert self._course('tunnel').edges() == ()

    def test_plain_road_has_none(self) -> None:
        assert self._course().edges() == ()

    def test_each_carried_stretch_gets_its_own(self) -> None:
        found = self._course('bridge', 'tunnel', 'causeway').edges()
        assert found == ((0.0, 20.0), (20.0, 40.0))


class TestACarThatHasPulledOff:
    """Where a car that has left the carriageway actually stands.

    A quarter of the traffic pulls off for fourteen seconds at a time -- a
    turning, a gate, a lay-by -- so two or three of ten are standing at the
    roadside at any moment. Where they stand is the first wrong thing a player
    sees, and they stood in the trees: the offset was measured to the car's
    *centre* and nothing accounted for the car being 2.8 m wide.
    """

    def course(self, carriageway=7.2, total=10.6):
        line = np.stack([np.linspace(0.0, 4000.0, 401), np.zeros(401),
                         np.zeros(401)], axis=-1)
        return Course(name='road', centreline=line,
                      carriageway_width=carriageway, total_width=total,
                      closed=False, length=4000.0, structures=())

    def pulled_off(self, course):
        from glisteel.traffic import TrafficCar
        car = TrafficCar(course, station=1000.0, heading=1, limit=25.0)
        car.pull_off()
        return car._pulled_off() + car.lane

    def test_the_whole_car_is_on_ground_a_car_can_stand_on(self) -> None:
        """Its body, not its centre: half of 2.8 m is what was left out, and
        1.3 m of the car stood past the verge among the trees."""
        from glisteel.traffic import IN_THE_WAY
        course = self.course()
        edge = self.pulled_off(course) + IN_THE_WAY / 2.0
        assert edge <= course.total_width / 2.0 + 1e-9, (
            'a pulled-off car reaches %.2f m and the verge ends at %.2f m'
            % (edge, course.total_width / 2.0))

    def test_it_goes_as_far_off_as_the_verge_allows(self) -> None:
        """Not merely inside it -- against it. A car that pulled off and barely
        moved has not pulled off."""
        from glisteel.traffic import IN_THE_WAY
        course = self.course()
        edge = self.pulled_off(course) + IN_THE_WAY / 2.0
        assert edge == pytest.approx(course.total_width / 2.0)

    def test_it_still_overhangs_the_carriageway_and_that_is_the_road(self) -> None:
        """Stated rather than hidden: there are 1.7 m between the carriageway's
        edge and the verge, and a car is 2.8 m wide. There is nowhere to be
        wholly off, so being partly on is the honest answer and a lay-by is the
        road's to offer."""
        from glisteel.traffic import IN_THE_WAY
        course = self.course()
        room = course.total_width / 2.0 - course.carriageway_width / 2.0
        assert room < IN_THE_WAY, 'this road has room for a lay-by after all'
        inner = self.pulled_off(course) - IN_THE_WAY / 2.0
        assert inner < course.carriageway_width / 2.0

    def test_a_wide_verge_gets_the_car_wholly_off(self) -> None:
        """Where there *is* room, the car uses it -- so a road that offers a
        lay-by gets one without this changing again."""
        from glisteel.traffic import IN_THE_WAY
        course = self.course(carriageway=7.2, total=14.0)
        inner = self.pulled_off(course) - IN_THE_WAY / 2.0
        assert inner >= course.carriageway_width / 2.0

    def test_it_never_pulls_off_towards_the_middle(self) -> None:
        course = self.course()
        assert self.pulled_off(course) >= course.carriageway_width / 2.0 - 1.2
