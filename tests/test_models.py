"""The art the game ships: what each model must be for the game to drive it.

A model is not only a picture. The car's bodywork has to be the size the physics
holds up, its wheels have to turn about their own hubs, its rim has to carry the
travel the steering poses it through, and a vehicle the player can hit has to be
as big to hit as it is to see. Those are the properties asserted here, against
the files themselves, so that re-exporting the art cannot quietly move the car
off its wheels or the traffic off its colliders.

No window: a model is geometry, names and materials.
"""
import math

import numpy as np
import pytest
from OpenGLContext.loaders.assets import bounds, shapes
from OpenGLContext.loaders.gltf.transforms import _local_matrix_rv

from glisteel import models
from glisteel.camera import COCKPIT_BACK, COCKPIT_UP
from glisteel.car import BODY_HEIGHT, BODY_LENGTH, BODY_WIDTH, CABIN_HEIGHT, CarSpec

#: How far a model may be from the dimension it is authored to, in metres.
TOLERANCE = 0.02

#: How far a wheel's hub may be from its own origin, in metres.
HUB_TOLERANCE = 0.002

#: What each model may cost, in triangles. The hero's exterior loft is cut in
#: two at the windscreen base -- :data:`models.BONNET` and :data:`models.BODY`
#: -- so the pair shares ``body``'s budget rather than each drawing its own.
BUDGET = {'body': 10000, 'interior': 6000, 'glass': 2000,
          'hero': 25000, 'wheel': 2500, 'traffic': 2000}


def _load(relative):
    scene = models.ART.load(relative)
    assert scene is not None, 'the model %s does not load' % (relative,)
    return scene


def _bounds(node):
    """The box a subtree occupies, from the engine's own measurement of one."""
    measured = bounds(node)
    assert measured is not None, 'nothing to measure in %r' % (node,)
    return measured


def _size(node):
    minimum, maximum = _bounds(node)
    return maximum - minimum


def _centre(node):
    minimum, maximum = _bounds(node)
    return (minimum + maximum) / 2.0


def _triangles(node):
    return sum(len(one.geometry.indices) // 3 for one in shapes(node))


def _world_triangles(node):
    """Every triangle under ``node``, as ``(N, 3, 3)`` world-space corners.

    ``shapes()`` finds the geometry but carries no accumulated transform, so
    this walks the same ``Transform`` chain :func:`bounds` does and places
    each shape's own triangles before handing them back.
    """
    corners = []

    def collect(here, matrix):
        world = (_local_matrix_rv(here) @ matrix
                if getattr(here, 'translation', None) is not None else matrix)
        points = getattr(getattr(here, 'geometry', None), 'positions', None)
        if points is not None and len(points):
            local = np.asarray(points, dtype='d').reshape(-1, 3)
            placed = (np.column_stack([local, np.ones(len(local))]) @ world)[:, :3]
            index = np.asarray(here.geometry.indices, dtype=np.int64).reshape(-1, 3)
            corners.append(placed[index])
        for child in (getattr(here, 'children', None) or ()):
            collect(child, world)

    collect(node, np.eye(4))
    return np.concatenate(corners) if corners else np.zeros((0, 3, 3))


def _ray_hit(origin, direction, triangles):
    """The nearest distance along ``direction`` that meets one of ``triangles``, or None.

    Moller-Trumbore, vectorised over every triangle at once: a cockpit
    sightline test casts dozens of rays against a thousand-odd triangles, and
    a Python loop over each pair would cost far more than the geometry itself.
    """
    origin = np.asarray(origin, dtype='d')
    direction = np.asarray(direction, dtype='d')
    v0, v1, v2 = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    edge1, edge2 = v1 - v0, v2 - v0
    perpendicular = np.cross(direction, edge2)
    determinant = np.einsum('ij,ij->i', edge1, perpendicular)
    live = np.abs(determinant) > 1e-9
    inverse = np.zeros_like(determinant)
    inverse[live] = 1.0 / determinant[live]
    to_origin = origin - v0
    u = inverse * np.einsum('ij,ij->i', to_origin, perpendicular)
    live &= (u >= -1e-6) & (u <= 1.0 + 1e-6)
    crossed = np.cross(to_origin, edge1)
    v = inverse * np.einsum('j,ij->i', direction, crossed)
    live &= (v >= -1e-6) & (u + v <= 1.0 + 1e-6)
    distance = inverse * np.einsum('ij,ij->i', edge2, crossed)
    live &= distance > 1e-6
    return float(distance[live].min()) if np.any(live) else None


def _box_exit(origin, direction, low, high):
    """How far along ``direction`` the ray leaves the box ``(low, high)``."""
    exit_distance = np.inf
    for axis in range(3):
        component = direction[axis]
        if abs(component) < 1e-12:
            continue
        far = max((low[axis] - origin[axis]) / component,
                  (high[axis] - origin[axis]) / component)
        if far >= 0.0:
            exit_distance = min(exit_distance, far)
    return exit_distance


@pytest.fixture
def hero():
    # Loaded afresh for each test: posing the steering clip moves nodes, and a
    # model shared between tests is a test that passes or fails on its order.
    return _load(models.HERO)


class TestThePlayersCar:
    """The car the player drives: its shell, and what is inside it."""

    def test_it_carries_its_shells_by_name(self, hero) -> None:
        for name in (models.BODY, models.BONNET, models.INTERIOR, models.GLASS):
            assert hero.getDEF(name) is not None, 'no %s in the model' % (name,)

    def test_it_carries_a_bonnet_ahead_of_the_screen(self, hero) -> None:
        """The one piece of the outside a driver still sees from inside."""
        bonnet = hero.getDEF(models.BONNET)
        assert _triangles(bonnet) > 0
        assert _centre(bonnet)[2] < _centre(hero.getDEF(models.BODY))[2], \
            'the bonnet is not ahead of the body'

    def test_it_carries_pillars_framing_the_screen(self, hero) -> None:
        pillars = hero.getDEF(models.PILLARS)
        assert pillars is not None, 'no pillars in the interior'
        assert _triangles(pillars) > 0

    def test_the_cockpit_view_has_no_gap_to_the_road(self, hero) -> None:
        """The driver's eye meets the tub, not the ground under the dash.

        A dashboard shallow enough to see over and no floor to match is a hole
        a driver can see the road straight through. Every downward line of
        sight from the cockpit eye -- ahead, ahead-and-down, and down beside
        the pedals -- has to meet the interior or the bonnet before it would
        leave the car; :func:`glisteel.camera.ChaseCamera` puts the eye at
        :data:`~glisteel.camera.COCKPIT_UP` above the body's centre and
        :data:`~glisteel.camera.COCKPIT_BACK` behind it, on the centreline,
        and only the interior and the bonnet draw in that view.
        """
        triangles = np.concatenate([_world_triangles(hero.getDEF(models.INTERIOR)),
                                   _world_triangles(hero.getDEF(models.BONNET))])
        low, high = _bounds(hero.group)
        eye = np.array([0.0, COCKPIT_UP, COCKPIT_BACK])
        forward, up = np.array([0.0, 0.0, -1.0]), np.array([0.0, 1.0, 0.0])
        right = np.cross(forward, up)

        misses = []
        for azimuth in (0.0, 15.0, 30.0, 45.0, 60.0, 75.0):
            for side in (1.0, -1.0):
                horizontal = (math.cos(math.radians(azimuth)) * forward
                             + math.sin(math.radians(azimuth)) * side * right)
                for dip in range(20, 81, 10):
                    direction = (math.cos(math.radians(dip)) * horizontal
                                - math.sin(math.radians(dip)) * up)
                    direction = direction / np.linalg.norm(direction)
                    exit_distance = _box_exit(eye, direction, low, high)
                    hit_distance = _ray_hit(eye, direction, triangles)
                    if hit_distance is None or hit_distance > exit_distance + 1e-3:
                        misses.append((azimuth * side, dip))
                if azimuth == 0.0:
                    break                              # +0 and -0 are the same ray
        assert not misses, ('sightlines with nothing in the way (azimuth, dip): %r'
                            % (misses,))

    def test_it_is_the_size_the_physics_holds_up(self, hero) -> None:
        """The bodywork is the box the chassis collider is, and the cabin on it."""
        minimum, maximum = _bounds(hero.group)
        assert minimum == pytest.approx(
            (-BODY_WIDTH / 2.0, -BODY_HEIGHT / 2.0, -BODY_LENGTH / 2.0), abs=TOLERANCE)
        assert maximum == pytest.approx(
            (BODY_WIDTH / 2.0, BODY_HEIGHT / 2.0 + CABIN_HEIGHT, BODY_LENGTH / 2.0),
            abs=TOLERANCE)

    def test_it_faces_the_way_the_car_drives(self, hero) -> None:
        """The wheel is in front of the driver, and in front is -Z.

        The wheels the physics steers are at -Z, so a model built facing the
        other way would drive the car backwards down the road.
        """
        assert _centre(hero.getDEF(models.COLUMN))[2] < _centre(hero.getDEF(models.SEATS))[2]

    def test_the_driver_has_something_to_sit_in_and_hold(self, hero) -> None:
        for name in (models.SEATS, models.COLUMN, models.RIM):
            assert hero.getDEF(name) is not None, 'no %s in the interior' % (name,)
        assert _triangles(hero.getDEF(models.SEATS)) > 0

    def test_the_glass_refracts(self, hero) -> None:
        """Transmission, an index of refraction, and a thickness to refract through."""
        glass = hero.materials[models.GLASS]
        assert glass.transmission > 0.0
        assert glass.ior == pytest.approx(1.52, abs=0.02)
        assert glass.thickness > 0.0

    def test_the_paint_is_the_model_s_own(self, hero) -> None:
        """A named material carrying its own colour, so the car is painted
        where it is modelled rather than tinted at runtime.

        The colour may be a factor, a base-colour texture, or both: a paint
        built on a textured finish carries it in the texture and leaves the
        factor white.
        """
        paint = hero.materials[models.PAINT]
        assert (tuple(paint.baseColor) != (1.0, 1.0, 1.0)
                or 'baseColor' in (paint.textures or {})), 'the car is unpainted'

    def test_the_paint_is_a_finish_rather_than_a_colour(self, hero) -> None:
        """A coat over a base that keeps its colour, which is what paint is.

        Not chrome: a fully metallic surface has no colour of its own and takes
        the colour of whatever it reflects, so a car painted that way comes out
        the colour of the sky. The paint stays mostly dielectric and lets the
        coat do the sharp reflections.
        """
        paint = hero.materials[models.PAINT]
        assert 0.05 <= paint.metallic <= 0.6, 'chrome, not paint'
        assert paint.clearcoat > 0.5
        assert paint.clearcoatRoughness <= 0.10

    def test_it_costs_what_it_is_allowed_to(self, hero) -> None:
        assert _triangles(hero.group) <= BUDGET['hero']
        body_and_bonnet = (_triangles(hero.getDEF(models.BODY))
                          + _triangles(hero.getDEF(models.BONNET)))
        assert body_and_bonnet <= BUDGET['body'], 'body + bonnet'
        for name in (models.INTERIOR, models.GLASS):
            assert _triangles(hero.getDEF(name)) <= BUDGET[name], name


class TestTheSteeringClip:
    """The travel of the rim, which the model carries and the game poses."""

    def test_the_clip_is_there_and_turns_the_rim(self, hero) -> None:
        player = hero.player_named(models.STEER_CLIP, loop=False)
        assert player is not None
        assert player.duration > 0.0

    def test_its_ends_are_full_lock_either_way(self, hero) -> None:
        """Centred half way through, and turned the opposite way at each end."""
        left, centre, right = (self._angle(hero, fraction) for fraction in (0.0, 0.5, 1.0))
        assert centre == pytest.approx(0.0, abs=1e-3)
        assert left == pytest.approx(-right, abs=1e-3)
        assert np.radians(60.0) < abs(left) < np.pi

    def test_it_poses_fractionally(self, hero) -> None:
        """A quarter of the way is a quarter of the travel, not a step."""
        assert self._angle(hero, 0.25) == pytest.approx(self._angle(hero, 0.0) / 2.0,
                                                        abs=np.radians(1.0))

    def test_the_rim_turns_about_its_column(self, hero) -> None:
        """Local Y lies along the steering axis, so a pose is a turn, not a tilt."""
        player = hero.player_named(models.STEER_CLIP, loop=False)
        player.evaluate(0.0)
        axis = np.asarray(hero.getDEF(models.RIM).rotation[:3], dtype='d')
        assert abs(axis[1]) == pytest.approx(1.0, abs=1e-6)

    def test_it_stops_at_its_stops(self, hero) -> None:
        """Past either end the rim holds full lock rather than winding on."""
        assert self._angle(hero, 1.5) == pytest.approx(self._angle(hero, 1.0), abs=1e-6)
        assert self._angle(hero, -0.5) == pytest.approx(self._angle(hero, 0.0), abs=1e-6)

    def _angle(self, hero, fraction):
        """The rim's rotation about the column, in radians, posed at ``fraction``."""
        player = hero.player_named(models.STEER_CLIP, loop=False)
        player.evaluate(fraction * player.duration)
        rim = hero.getDEF(models.RIM)
        axis = np.asarray(rim.rotation[:3], dtype='d')
        angle = float(rim.rotation[3])
        return angle * (1.0 if axis[1] >= 0.0 else -1.0)


class TestTheWheels:
    """Four of these are mounted on the car, and they turn."""

    @pytest.fixture(params=[models.HERO_WHEEL_FRONT, models.HERO_WHEEL_REAR])
    def wheel(self, request):
        return _load(request.param)

    def test_it_turns_about_its_own_hub(self, wheel) -> None:
        """The origin is the hub: a wheel off centre wobbles as it rolls."""
        assert _centre(wheel.group) == pytest.approx((0.0, 0.0, 0.0), abs=HUB_TOLERANCE)

    def test_it_is_the_radius_the_physics_rides_on(self, wheel) -> None:
        radius = CarSpec().wheel_radius
        _across, high, deep = _size(wheel.group)
        assert high == pytest.approx(radius * 2.0, abs=0.005)
        assert deep == pytest.approx(radius * 2.0, abs=0.005)

    def test_its_axle_lies_across_the_car(self, wheel) -> None:
        """Wider than it is tall is a barrel; a wheel is the other way round."""
        across, high, _deep = _size(wheel.group)
        assert across < high

    def test_it_costs_what_it_is_allowed_to(self, wheel) -> None:
        assert _triangles(wheel.group) <= BUDGET['wheel']

    def test_the_back_wheels_are_the_wider_ones(self) -> None:
        front, rear = _load(models.HERO_WHEEL_FRONT), _load(models.HERO_WHEEL_REAR)
        assert _size(rear.group)[0] > _size(front.group)[0]


class TestTheTraffic:
    """The ordinary vehicles the road is busy with."""

    @pytest.fixture(params=models.TRAFFIC, ids=lambda kind: kind.name)
    def kind(self, request):
        return request.param

    def test_it_is_the_size_it_says_it_is(self, kind) -> None:
        """What the table declares is what the physics gives the player to hit."""
        width, height, length = _size(_load(kind.model).group)
        assert (width, height, length) == pytest.approx(kind.size(), abs=TOLERANCE)

    def test_it_carries_the_three_shells_by_name(self, kind) -> None:
        scene = _load(kind.model)
        for name in (models.BODY, models.INTERIOR, models.GLASS):
            assert scene.getDEF(name) is not None, '%s has no %s' % (kind.name, name)

    def test_somebody_is_sitting_in_it(self, kind) -> None:
        """Seats and headrests, because they are what a window shows."""
        scene = _load(kind.model)
        seats = scene.getDEF(models.SEATS)
        assert seats is not None and _triangles(seats) > 0
        assert _bounds(seats)[1][1] > _centre(scene.group)[1], 'the headrests are too low'

    def test_it_faces_the_way_it_drives(self, kind) -> None:
        scene = _load(kind.model)
        assert _centre(scene.getDEF(models.COLUMN))[2] < _centre(scene.getDEF(models.SEATS))[2]

    def test_it_is_painted_metal_and_glass(self, kind) -> None:
        scene = _load(kind.model)
        assert sorted(scene.materials) == sorted(models.VEHICLE_MATERIALS)
        assert scene.materials[models.PAINT].metallic > 0.5
        assert scene.materials[models.GLASS].transmission > 0.0

    def test_its_glass_is_thin(self, kind) -> None:
        """A car passing at a closing speed of two hundred needs no volume in it."""
        assert _load(kind.model).materials[models.GLASS].thickness == 0.0

    def test_it_stands_on_the_road(self, kind) -> None:
        """Its origin is where it meets the road, which is where the game puts it."""
        low, high = _bounds(_load(kind.model).group)
        assert low[1] == pytest.approx(0.0, abs=0.005)
        assert high[1] == pytest.approx(kind.height, abs=TOLERANCE)

    def test_it_costs_what_it_is_allowed_to(self, kind) -> None:
        assert _triangles(_load(kind.model).group) <= BUDGET['traffic']

    def test_every_kind_is_its_own_shape(self) -> None:
        """Five vehicles, not one vehicle five times."""
        sizes = {kind.name: kind.size() for kind in models.TRAFFIC}
        assert len(set(sizes.values())) == len(models.TRAFFIC)
