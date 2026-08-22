"""What building a world and a scenario asks for more than once.

Three separate readers wanted three different things out of one ``tileset.json``
-- the roads, the props and the luminaires -- and each read and parsed the file
for itself. A scenario has the same shape of problem one layer up: its course is
worked out again for the ground, for the props and for the world.

None of this is per frame, so none of it is a frame rate. It is what a player
waits through before the first one.
"""
import json
import math

import pytest
import support

from glisteel import scenarios


class TestABakedWorldIsReadOnce:
    def _tileset(self, tmp_path):
        line = [[float(x), 0.0, 0.0] for x in range(0, 400, 5)]
        document = {
            'asset': {'version': '1.1'},
            'geometricError': 100.0,
            'root': {'boundingVolume': {'box': [0, 0, 0, 200, 0, 0,
                                                0, 20, 0, 0, 0, 200]},
                     'geometricError': 0.0, 'refine': 'REPLACE'},
            'extras': {
                'roads': [{'name': 'circuit', 'centreline': line,
                           'carriagewayWidth': 7.0, 'totalWidth': 12.0,
                           'closed': False, 'length': 395.0}],
                'props': [],
                'luminaires': [],
            },
        }
        path = tmp_path / 'tileset.json'
        path.write_text(json.dumps(document), encoding='utf-8')
        return str(path)

    def test_the_game_reads_the_file_once(self, tmp_path) -> None:
        """Once here, plus the streamer's own: it needs the tileset to stream.

        Three readers wanted three different things out of it -- the roads, the
        obstacles and the lamps -- and each parsed the whole document for
        itself.
        """
        from OpenGLContext.loaders.tiles3d import fetch

        from glisteel.world import RaceWorld
        path = self._tileset(tmp_path)
        with support.counting(fetch, 'read_bytes') as reads:
            RaceWorld(path)
        mine = [one for (args, _named) in reads for one in args[:1]
                if one == path]
        assert len(mine) <= 2, 'read the tileset %d times' % len(mine)

    def test_everything_it_carries_comes_out_of_one_document(self) -> None:
        """The three readers take a document rather than a path."""
        from glisteel.world import _baked_luminaires, _baked_props, courses_in
        document = {'extras': {
            'roads': [{'name': 'r', 'centreline': [[0, 0, 0], [10, 0, 0]],
                       'length': 10.0}],
            'props': [],
            'luminaires': [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        }}
        assert [one.name for one in courses_in(document)] == ['r']
        assert _baked_props(document['extras']) == []
        assert _baked_luminaires(document['extras']).shape == (2, 3)

    def test_a_document_with_no_extras_is_not_an_error(self) -> None:
        from glisteel.world import _baked_luminaires, _baked_props, courses_in
        assert courses_in({}) == []
        assert _baked_props({}) == []
        assert _baked_luminaires({}).shape == (0, 3)

    def test_it_still_finds_the_road_the_props_and_the_lamps(self, tmp_path) -> None:
        from glisteel.world import RaceWorld
        world = RaceWorld(self._tileset(tmp_path))
        assert world.course is not None
        assert world.course.name == 'circuit'
        assert world.props is not None
        assert len(world.luminaires.lamps) == 0


class TestAScenarioIsWorkedOutOnce:
    def test_the_course_is_the_same_course_every_time(self) -> None:
        piece = scenarios.straight()
        assert piece.course() is piece.course()

    def test_two_scenarios_get_their_own(self) -> None:
        assert scenarios.straight().course() is not scenarios.straight().course()

    def test_the_course_is_still_the_road_that_was_asked_for(self) -> None:
        piece = scenarios.chicane(length=360.0)
        course = piece.course()
        assert len(course.centreline) == len(piece.plan)
        assert course.name == 'chicane'
        assert course.length > 300.0

    def test_a_closed_piece_is_still_closed(self) -> None:
        assert scenarios.circuit().course().closed


class TestTheWheelsDoNotWindUpForEver:
    """A wheel's roll is an angle, and an angle that only ever grows loses the
    precision it is drawn with. A long race is a lot of revolutions."""

    def test_the_roll_stays_within_one_turn(self) -> None:
        from omi_physics.world import PhysicsWorld

        from glisteel.car import Car
        from glisteel.world import static_ground
        world = PhysicsWorld()
        static_ground(world)
        car = Car(world, position=(0.0, 1.0, 0.0))
        # Half an hour at a hundred and eighty, in one go.
        for _ in range(400):
            car.follow(5.0)
        for spin in car._wheel_spin:
            assert abs(spin) <= 2.0 * math.pi + 1e-9, spin

    def test_the_wheels_still_turn(self) -> None:
        from omi_physics.world import PhysicsWorld

        from glisteel.car import Car
        from glisteel.world import static_ground
        world = PhysicsWorld()
        static_ground(world)
        car = Car(world, position=(0.0, 1.0, 0.0))
        for _ in range(240):                     # let it stand on its wheels
            car.update(1.0 / 120.0)
            world.step(1.0 / 120.0)
        before = list(car._wheel_spin)
        car.control(throttle=1.0)
        for _ in range(120):                     # a second of it, from rest
            car.update(1.0 / 120.0)
            world.step(1.0 / 120.0)
        car.follow(1.0 / 60.0)
        assert car._wheel_spin != before
        assert car.vehicle.forward_speed() > 1.0, 'the car did not move'

    def test_the_roll_is_continuous_across_the_wrap(self) -> None:
        """Wrapping must not put a step in the wheel's rotation."""
        from omi_physics.world import PhysicsWorld

        from glisteel.car import Car
        from glisteel.world import static_ground
        world = PhysicsWorld()
        static_ground(world)
        car = Car(world, position=(0.0, 1.0, 0.0))
        car._wheel_spin = [math.pi - 0.01] * len(car.vehicle.wheels)
        was = list(car._wheel_spin)
        car.follow(0.0)                          # no time passes
        for now, before in zip(car._wheel_spin, was, strict=True):
            assert now == pytest.approx(before)
