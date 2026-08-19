"""Where a structure is, over ground sampled on a grid.

A field terrain asks this about every sample of a chunk at once -- tens of
thousands of points against a road that may be thousands of points long -- so
the answer has to come back without materialising a point-by-point distance
matrix between the two. What is asserted here is the answer, and that asking
about a lot of ground at once does not cost a lot of memory.
"""
import numpy as np

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
