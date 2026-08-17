"""A baked world as a game sees it: the course, and where a car is on it."""

import math

import numpy as np
import pytest


class TestHowFarOffTheLineACarIs:
    """Measured to the road, not to the nearest point written down for it. A
    course is a shape sampled every few metres, and a car exactly on the line
    but half way between two samples is on the line."""

    def _straight(self, spacing=8.0, points=40):
        from glisteel.world import Course
        line = np.stack([np.arange(points) * spacing, np.zeros(points),
                         np.zeros(points)], axis=-1)
        return Course(name='straight', centreline=line, carriageway_width=7.2,
                      total_width=10.6, closed=False,
                      length=float((points - 1) * spacing))

    def test_a_car_on_the_line_is_on_the_line(self) -> None:
        course = self._straight()
        for along in (0.0, 1.0, 4.0, 7.9, 12.0, 100.0):
            assert course.nearest((along, 0.0, 0.0))[1] \
                == pytest.approx(0.0, abs=1e-6)

    def test_a_car_beside_it_is_that_far_beside_it(self) -> None:
        course = self._straight()
        assert course.nearest((12.0, 0.0, 3.0))[1] == pytest.approx(3.0)

    def test_height_does_not_count(self) -> None:
        """A car in the air over the track is still on the track."""
        course = self._straight()
        assert course.nearest((12.0, 40.0, 0.0))[1] == pytest.approx(0.0, abs=1e-6)

    def test_the_index_is_still_a_point_of_the_line(self) -> None:
        course = self._straight()
        index, _off = course.nearest((12.0, 0.0, 0.0))
        assert 0 <= index < len(course.centreline)

    def test_it_is_the_nearer_of_the_two_it_lies_between(self) -> None:
        course = self._straight(spacing=8.0)
        assert course.nearest((17.0, 0.0, 0.0))[0] == 2

    def test_a_closed_course_measures_across_its_join(self) -> None:
        from glisteel.world import Course
        angle = np.linspace(0.0, 2 * math.pi, 64, endpoint=False)
        line = np.stack([100.0 * np.cos(angle), np.zeros(64),
                         100.0 * np.sin(angle)], axis=-1)
        course = Course(name='ring', centreline=line, carriageway_width=7.2,
                        total_width=10.6, closed=True, length=628.0)
        # Between the last point and the first, on the circle.
        between = 0.5 * (line[-1] + line[0])
        between *= 100.0 / np.linalg.norm(between[[0, 2]])
        assert course.nearest(between)[1] < 0.2

    def test_an_open_course_does_not_join_its_ends(self) -> None:
        course = self._straight(points=10, spacing=8.0)
        far = (36.0, 0.0, 400.0)
        assert course.nearest(far)[1] == pytest.approx(400.0, abs=0.1)

    def test_on_road_follows_it(self) -> None:
        course = self._straight()
        assert course.on_road((12.0, 0.0, 0.0))
        assert not course.on_road((12.0, 0.0, 9.0))


class TestTheRoadsOwnSection:
    """A game builds the carriageway's collider itself, because tile geometry
    changes resolution under a car and the surface must not. The cut comes with
    the world."""

    def _course(self, **profile):
        from glisteel.world import Course
        line = np.stack([np.arange(20) * 8.0, np.zeros(20), np.zeros(20)],
                        axis=-1)
        return Course(name='r', centreline=line, carriageway_width=7.2,
                      total_width=10.6, closed=False, length=152.0,
                      profile=profile)

    def test_a_course_without_one_still_has_a_profile(self) -> None:
        """An older world says only how wide it is; the cut is inferred from
        that rather than refused."""
        found = self._course().road_profile()
        assert found.carriageway_width == pytest.approx(7.2)
        assert found.total_width == pytest.approx(10.6, abs=0.1)

    def test_the_numbers_a_world_gives_are_the_ones_used(self) -> None:
        found = self._course(laneWidth=3.0, lanes=2, shoulderWidth=0.5,
                             shoulderDrop=0.04, vergeWidth=0.8, vergeDrop=0.3,
                             crossfall=0.025, textureLength=20.0)
        profile = found.road_profile()
        assert profile.lane_width == pytest.approx(3.0)
        assert profile.verge_drop == pytest.approx(0.3)
        assert profile.total_width == pytest.approx(3.0 * 2 + 2 * (0.5 + 0.8))

    def test_it_is_read_out_of_a_baked_world(self, tmp_path) -> None:
        import json
        from glisteel.world import load_courses
        line = [[float(i) * 8.0, 0.0, 0.0] for i in range(20)]
        document = {'asset': {'version': '1.1'}, 'geometricError': 1.0,
                    'root': {'boundingVolume': {'box': [0] * 12},
                             'geometricError': 0.0},
                    'extras': {'roads': [{
                        'name': 'r', 'closed': False, 'length': 152.0,
                        'carriagewayWidth': 7.2, 'totalWidth': 10.6,
                        'centreline': line,
                        'profile': {'laneWidth': 3.0, 'lanes': 2,
                                    'shoulderWidth': 0.5, 'shoulderDrop': 0.04,
                                    'vergeWidth': 0.8, 'vergeDrop': 0.3,
                                    'crossfall': 0.025, 'textureLength': 20.0}}]}}
        path = tmp_path / 'tileset.json'
        path.write_text(json.dumps(document))
        course = load_courses(str(path))[0]
        assert course.road_profile().lane_width == pytest.approx(3.0)


class TestWhereTheGroundIsOpened:
    """A bore runs inside a hill and the hill's surface is still drawn over it,
    so the collider has to be cut for the road to pass. The cut has to start
    before the portal: the ground beside a portal is a cutting sampled on a
    grid metres wide, and where the two meet it rides over the carriageway."""

    def _course(self):
        from glisteel.world import Course, Structure
        line = np.stack([np.arange(200) * 8.0, np.zeros(200), np.zeros(200)],
                        axis=-1)
        return Course(name='r', centreline=line, carriageway_width=7.2,
                      total_width=10.6, closed=False, length=1592.0,
                      structures=(Structure('tunnel', 400.0, 800.0),))

    def test_the_ground_over_the_bore_is_cut(self) -> None:
        course = self._course()
        assert bool(course.inside('tunnel', np.array([600.0]),
                                  np.array([0.0]))[0])

    def test_the_ground_well_before_it_is_not(self) -> None:
        course = self._course()
        assert not bool(course.inside('tunnel', np.array([100.0]),
                                      np.array([0.0]))[0])

    def test_the_cut_reaches_back_up_the_approach(self) -> None:
        course = self._course()
        just_before = np.array([390.0])
        assert not bool(course.inside('tunnel', just_before, np.array([0.0]))[0])
        assert bool(course.inside('tunnel', just_before, np.array([0.0]),
                                  along=30.0)[0])

    def test_it_reaches_past_the_far_portal_too(self) -> None:
        course = self._course()
        assert bool(course.inside('tunnel', np.array([810.0]), np.array([0.0]),
                                  along=30.0)[0])

    def test_it_does_not_reach_further_than_it_is_told(self) -> None:
        course = self._course()
        assert not bool(course.inside('tunnel', np.array([300.0]),
                                      np.array([0.0]), along=30.0)[0])

    def test_a_kind_the_road_does_not_have_cuts_nothing(self) -> None:
        course = self._course()
        assert not course.inside('bridge', np.array([600.0]),
                                 np.array([0.0])).any()
