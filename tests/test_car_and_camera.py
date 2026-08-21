"""The car and the camera, on a flat floor with nothing drawn.

Everything a car does that a player can feel is numbers, and so is everything
the camera does. What is left for a window is the picture, which
``tests/test_plays.py`` takes.
"""

import math

import numpy as np
import pytest
from omi_physics.world import PhysicsWorld
from OpenGLContext.loaders.assets import bounds
from OpenGLContext.scenegraph.pbrmaterial import PBRMaterial

from glisteel import models
from glisteel.camera import ChaseCamera
from glisteel.car import (
    BODY_HEIGHT,
    CABIN_HEIGHT,
    Car,
    CarSpec,
    cabin_mesh,
    car_body_mesh,
    wheel_mesh,
)
from glisteel.world import static_ground

STEP = 1.0 / 120.0


@pytest.fixture
def floor():
    world = PhysicsWorld()
    # Wide enough to hold a full-throttle run: this car settles at about 73
    # metres a second, so half a minute of it covers better than two
    # kilometres, and a car that reaches the edge falls off the world and
    # reads as still accelerating.
    static_ground(world, size=12000.0)
    return world


def _drive(world, car, seconds, **controls):
    for _ in range(int(seconds / STEP)):
        car.control(**controls)
        car.update(STEP)
        world.step(STEP)
        car.follow(STEP)


class TestTheCar:
    def test_it_settles_on_the_ground(self, floor) -> None:
        car = Car(floor, position=(0, 3.0, 0))
        _drive(floor, car, 3.0)
        assert 0.2 < float(car.position[1]) < 1.5
        assert car.vehicle.grounded

    def test_it_drives(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 1.5)
        _drive(floor, car, 3.0, throttle=1.0)
        assert car.speed() > 5.0
        assert car.speed_kph() == pytest.approx(car.speed() * 3.6)

    def test_it_stops(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 1.5)
        _drive(floor, car, 3.0, throttle=1.0)
        _drive(floor, car, 3.0, brake=1.0)
        assert car.speed() < 1.0

    def test_it_can_be_put_back_on_the_grid(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 1.5)
        _drive(floor, car, 2.0, throttle=1.0)
        car.place((100.0, 2.0, -50.0), heading=math.pi)
        assert np.allclose(car.position, (100.0, 2.0, -50.0))
        assert car.speed() == pytest.approx(0.0)
        assert np.allclose(car.forward(), (0, 0, 1), atol=1e-6)

    def test_it_knows_when_it_is_on_its_roof(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        assert not car.upside_down()
        floor.orientation[car.body] = (0.0, 0.0, 1.0, 0.0)      # half turn about Z
        assert car.upside_down()

    def test_the_scenegraph_follows_the_simulation(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 1.5)
        _drive(floor, car, 2.0, throttle=1.0)
        assert np.allclose(car.node.translation, car.position, atol=1e-6)

    def test_the_wheels_hang_and_compress(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 2.0)
        drops = [float(node.translation[1]) for node in car._wheel_nodes]
        assert len(drops) == 4
        assert all(-1.0 < drop < 1.0 for drop in drops)

    def test_the_front_wheels_steer_with_the_wheel(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 1.0)
        _drive(floor, car, 1.0, throttle=0.5, steer=1.0)
        turned = [abs(float(node.rotation[3])) for node in car._wheel_nodes]
        assert max(turned) > 0.05
        assert min(turned) == pytest.approx(0.0)

    def test_the_wheels_roll_as_it_goes(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 1.5)
        before = float(car._wheel_nodes[0].children[0].rotation[3])
        _drive(floor, car, 2.0, throttle=1.0)
        assert abs(float(car._wheel_nodes[0].children[0].rotation[3]) - before) > 1.0

    def test_a_heavier_car_rides_at_the_same_height(self, floor) -> None:
        """Spring rates are in car-weights per metre, so a tuning survives a
        change of mass instead of putting a heavy car on its bump stops."""
        light = Car(floor, CarSpec(mass=900.0), position=(-20.0, 2.0, 0))
        heavy = Car(floor, CarSpec(mass=2400.0), position=(20.0, 2.0, 0))
        for _ in range(int(3.0 / STEP)):
            light.update(STEP)
            heavy.update(STEP)
            floor.step(STEP)
        assert float(heavy.position[1]) == pytest.approx(
            float(light.position[1]), abs=0.01)

    def test_a_softer_spring_squats_lower(self, floor) -> None:
        import dataclasses
        stiff = Car(floor, CarSpec(), position=(-20.0, 2.0, 0))
        soft = Car(floor, CarSpec(), position=(20.0, 2.0, 0))
        # The same car with softer springs and nothing else changed: where the
        # wheels hang decides where the body rides, so a set built from
        # defaults rather than from this car's own would be a different car.
        soft.vehicle.wheels = [
            type(wheel)(spec=dataclasses.replace(wheel.spec,
                                                 suspension_stiffness=8.0))
            for wheel in soft.vehicle.wheels]
        for _ in range(int(3.0 / STEP)):
            stiff.update(STEP)
            soft.update(STEP)
            floor.step(STEP)
        assert float(soft.position[1]) < float(stiff.position[1])


class TestHowItIsDrawn:
    def test_the_body_is_a_closed_solid(self) -> None:
        from OpenGLContext.scenegraph.pbrmaterial import PBRMaterial
        mesh = car_body_mesh(PBRMaterial())
        assert len(mesh.positions) % 3 == 0
        assert len(mesh.indices) == len(mesh.positions)

    def test_the_body_is_car_sized(self) -> None:
        from OpenGLContext.scenegraph.pbrmaterial import PBRMaterial
        points = car_body_mesh(PBRMaterial()).positions
        size = points.max(axis=0) - points.min(axis=0)
        assert 1.5 < size[0] < 2.2                    # across
        assert 3.5 < size[2] < 5.0                    # along

    def test_every_face_has_a_normal(self) -> None:
        from OpenGLContext.scenegraph.pbrmaterial import PBRMaterial
        mesh = car_body_mesh(PBRMaterial())
        assert np.allclose(np.linalg.norm(mesh.normals, axis=1), 1.0, atol=1e-4)

    def test_a_wheel_is_round_and_the_right_size(self) -> None:
        points = wheel_mesh(radius=0.4, width=0.2).positions
        radius = np.linalg.norm(points[:, [1, 2]], axis=1)
        assert np.allclose(radius, 0.4, atol=1e-5)
        assert points[:, 0].max() - points[:, 0].min() == pytest.approx(0.2)

    def test_the_car_has_its_shells_and_four_wheels(self, floor) -> None:
        """The outside of the car -- bodywork and wheels -- switches together."""
        car = Car(floor, position=(0, 1.0, 0))
        assert len(car.node.children[0].choice[0].children) == 5
        assert len(car._wheel_nodes) == 4


class TestTheCamera:
    class _Car:
        def __init__(self, position=(0, 0, 0), forward=(0, 0, -1), speed=0.0):
            self.position = np.asarray(position, dtype='d')
            self._forward = np.asarray(forward, dtype='d')
            self._speed = speed

        def forward(self):
            return self._forward

        def speed(self):
            return self._speed

    def test_it_sits_behind_and_above_the_car(self) -> None:
        pose = ChaseCamera(mode='chase').update(self._Car(), 1.0)
        assert pose.position[2] > 0.0                 # behind a car facing -Z
        assert pose.position[1] > 1.0                 # and above it

    def test_it_looks_where_the_car_is_going(self) -> None:
        pose = ChaseCamera(mode='chase').update(self._Car(), 1.0)
        assert pose.target[2] < pose.position[2]
        assert abs(pose.heading()) < 1e-6             # straight down -Z

    def test_it_lags_the_car_rather_than_snapping_to_it(self) -> None:
        camera = ChaseCamera(mode='chase')
        camera.update(self._Car(), 1.0)
        moved = camera.update(self._Car(position=(0, 0, -50.0)), 1.0 / 60.0)
        assert moved.position[2] > -40.0, "the camera teleported after the car"

    def test_a_faster_car_is_watched_from_further_back(self) -> None:
        slow = ChaseCamera(mode='chase').update(self._Car(speed=0.0), 1.0)
        fast = ChaseCamera(mode='chase').update(self._Car(speed=60.0), 1.0)
        assert fast.position[2] > slow.position[2]

    def test_the_pull_back_is_capped(self) -> None:
        fast = ChaseCamera(mode='chase').update(self._Car(speed=1000.0), 1.0)
        assert fast.position[2] < 20.0

    def test_the_cockpit_view_is_where_a_driver_sits(self) -> None:
        camera = ChaseCamera(mode='cockpit')
        pose = camera.update(self._Car(), 1.0)
        assert abs(float(pose.position[2])) < 1.0     # about the car's middle
        assert 0.3 < float(pose.position[1]) < 1.0    # at a driver's eye

    def test_the_cockpit_looks_down_the_road(self) -> None:
        camera = ChaseCamera(mode='cockpit')
        pose = camera.update(self._Car(), 1.0)
        assert pose.target[2] < -10.0
        assert abs(pose.pitch()) < 0.05, "a driver looks at the road, not the sky"

    def test_it_starts_in_the_cockpit(self) -> None:
        """A game about driving a route is seen from the car."""
        assert ChaseCamera().mode == 'cockpit'

    def test_the_view_can_be_cycled(self) -> None:
        camera = ChaseCamera()
        assert camera.cycle() == 'chase'
        assert camera.cycle() == 'bonnet'
        assert camera.cycle() == 'cockpit'

    def test_the_bonnet_view_is_ahead_of_the_driver(self) -> None:
        cockpit = ChaseCamera(mode='cockpit').update(self._Car(), 1.0)
        bonnet = ChaseCamera(mode='bonnet').update(self._Car(), 1.0)
        assert float(bonnet.position[2]) < float(cockpit.position[2])

    def test_a_view_from_the_car_does_not_lag(self) -> None:
        """It is bolted on: lag would be the car sliding around the frame."""
        for mode in ('cockpit', 'bonnet'):
            camera = ChaseCamera(mode=mode)
            camera.update(self._Car(), 1.0)
            moved = camera.update(self._Car(position=(0, 0, -50.0)), 1.0 / 60.0)
            assert float(moved.position[2]) < -45.0

    def test_a_reset_snaps_it_back_into_place(self) -> None:
        camera = ChaseCamera(mode='chase')
        camera.update(self._Car(), 1.0)
        camera.reset()
        pose = camera.update(self._Car(position=(0, 0, -500.0)), 1.0 / 60.0)
        assert pose.position[2] < -480.0

    def test_it_reports_its_pitch(self) -> None:
        pose = ChaseCamera(mode='chase').update(self._Car(), 1.0)
        assert pose.pitch() < 0.0, "a chase camera looks slightly down"

    def test_a_car_facing_east_is_watched_from_the_west(self) -> None:
        pose = ChaseCamera().update(self._Car(forward=(1, 0, 0)), 1.0)
        assert pose.position[0] < 0.0
        assert pose.heading() == pytest.approx(math.pi / 2, abs=1e-6)


class TestTheCarIsPaintedWhereTheRendererLooks:
    """The render pass takes a shape's material from its Appearance.

    A mesh that carries a material but sits in a bare Shape is drawn in the
    default grey -- which is how a red car comes out white.
    """

    def test_every_shape_has_an_appearance_with_a_material(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        shapes = _shapes(car.node)
        assert shapes
        for shape in shapes:
            assert shape.appearance is not None
            assert shape.appearance.material is not None

    def test_the_fallback_body_wears_the_paint_it_was_given(self, floor,
                                                            monkeypatch) -> None:
        """``CarSpec.paint`` is what the primitive car is painted.

        The model carries its own paint and keeps it; the spec's colour is for
        the car drawn when there is no model to load.
        """
        monkeypatch.setattr(models.ART, 'load', lambda relative: None)
        monkeypatch.setattr(models.ART, 'shared', lambda relative: None)
        car = Car(floor, CarSpec(paint=(0.8, 0.1, 0.05)), position=(0, 1.0, 0))
        colours = [tuple(round(float(v), 3)
                         for v in shape.appearance.material.baseColor)
                   for shape in _shapes(car.node)]
        assert (0.8, 0.1, 0.05) in colours

    def test_the_tyres_are_black_and_the_glass_is_not_the_paint(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        colours = {tuple(round(float(v), 2)
                         for v in shape.appearance.material.baseColor)
                   for shape in _shapes(car.node)}
        assert len(colours) >= 3
        assert min(max(colour) for colour in colours) < 0.1     # the tyres


def _shapes(node, out=None):
    from OpenGLContext.scenegraph.shape import Shape
    out = [] if out is None else out
    if isinstance(node, Shape):
        out.append(node)
    for child in ((getattr(node, 'children', None) or [])
                  + (getattr(node, 'choice', None) or [])):
        _shapes(child, out)
    return out


class TestTheAirTheWorldIsSeenThrough:
    """A baked world is a few kilometres across and then it stops. What a
    camera at ground level sees past the last of it is the background, and a
    hard line between the two says where the world ends.
    """

    def test_the_haze_and_the_fog_are_the_same_colour(self) -> None:
        """Terrain fades into the air the background is already made of."""
        from OpenGLContext.viewer import environment

        from glisteel.game import race_fog
        assert (tuple(race_fog().color)
                == pytest.approx(tuple(environment.HORIZON_HAZE)))

    def test_it_thickens_over_a_distance_not_at_a_line(self) -> None:
        from glisteel.game import race_fog
        assert race_fog().fogType == 'EXPONENTIAL'

    def test_the_far_side_of_the_world_is_in_it(self) -> None:
        """Whatever the far plane still draws must be hazed, or the edge shows."""
        from glisteel.game import race_fog
        from glisteel.world import VIEW_DISTANCE
        assert race_fog().visibilityRange < VIEW_DISTANCE

    def test_the_road_ahead_is_not(self) -> None:
        """A driver has to see far enough to place the car for a corner."""
        from glisteel.game import race_fog
        assert race_fog().visibilityRange > 600.0


class TestTheDriverIsInsideTheCar:
    """A cockpit view is taken from a point inside the bodywork.

    Drawn from there, the only thing in frame is the inside of the car's own
    shell -- so the shell comes off. It is the player's own car and they are
    sitting in it; the views that look *at* it are the other two.
    """

    def test_the_cockpit_is_inside_it(self) -> None:
        assert ChaseCamera('cockpit').inside

    def test_the_bonnet_is_not(self) -> None:
        assert not ChaseCamera('bonnet').inside

    def test_the_chase_view_is_not(self) -> None:
        assert not ChaseCamera('chase').inside

    def test_a_car_is_drawn_by_default(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        assert not car.hidden
        assert _drawn(car.node)

    def test_a_hidden_car_is_not(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        car.hidden = True
        assert not _drawn(car.node)

    def test_it_comes_back(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        car.hidden = True
        car.hidden = False
        assert _drawn(car.node)

    def test_hiding_it_does_not_stop_it_moving(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        car.hidden = True
        car.follow(STEP)
        assert car.node.translation is not None


def _drawn(node) -> bool:
    """Whether anything under a car's node would be rendered."""
    from OpenGLContext.scenegraph.switch import Switch
    for child in node.children:
        if isinstance(child, Switch):
            return bool(child.renderedChildren())
    return bool(node.children)          # pragma: no cover - the shell is a Switch


class TestHowItAccelerates:
    """A constant force at every speed is not what any drivetrain gives, and
    nothing pushing back is not what any road does. What a motor gives is
    constant torque to a base speed and constant power above it; what decides
    how fast a car will actually go is the air."""

    def test_the_pull_falls_away_with_speed(self) -> None:
        tuning = CarSpec().tuning
        assert tuning.drive_force(50.0) < tuning.drive_force(5.0) * 0.6

    def test_and_something_pushes_back(self) -> None:
        assert CarSpec().tuning.drag > 0.0

    def test_it_still_gets_off_the_line(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 4.0, throttle=1.0)
        assert car.speed() > 15.0

    def test_and_reaches_a_road_speed(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 30.0, throttle=1.0)
        assert 60.0 < car.speed() < 85.0

    def test_and_stops_there_rather_than_creeping_up(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 30.0, throttle=1.0)
        settled = car.speed()
        _drive(floor, car, 8.0, throttle=1.0)
        assert abs(car.speed() - settled) < 2.0

    def test_lifting_off_slows_it(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 14.0, throttle=1.0)
        rolling = car.speed()
        _drive(floor, car, 6.0, throttle=0.0)
        assert car.speed() < rolling - 1.5


class TestWhichWayItIsGoing:
    def test_a_standing_car_is_going_nowhere(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 1.0)
        assert float(np.linalg.norm(car.velocity())) < 1.0

    def test_a_driven_one_is_going_the_way_it_points(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 4.0, throttle=1.0)
        assert float(np.dot(car.velocity(), car.forward())) > 8.0

    def test_and_its_length_is_its_speed(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        _drive(floor, car, 4.0, throttle=1.0)
        assert float(np.linalg.norm(car.velocity())) \
            == pytest.approx(car.speed(), rel=0.15)


class TestTheCarIsTheModel:
    """The car draws the shipped model, and drives what the model carries."""

    def test_it_draws_the_shipped_shells(self, floor) -> None:
        car = Car(floor)
        drawn = [one.DEF for one in _named(car.node)]
        for name in (models.BODY, models.INTERIOR, models.GLASS):
            assert name in drawn, 'the car does not draw its %s' % (name,)

    def test_the_cockpit_view_draws_the_wheel_and_nothing_else(self, floor
                                                               ) -> None:
        """What a driver needs in front of them is the road and the wheel that
        turns in it. Bodywork seen from inside is bodywork in the way."""
        car = Car(floor)
        car.hidden = True
        drawn = [one.DEF for one in _named(car.node)]
        assert models.COLUMN in drawn
        for gone in (models.BODY, models.INTERIOR, models.GLASS, models.BONNET):
            assert gone not in drawn, 'the cockpit still draws its %s' % (gone,)

    def test_it_draws_the_bonnet_as_its_own_shell(self, floor) -> None:
        car = Car(floor)
        assert models.BONNET in [one.DEF for one in _named(car.node)]

    def test_and_the_view_from_outside_keeps_the_whole_car(self, floor) -> None:
        car = Car(floor)
        drawn = [one.DEF for one in _named(car.node)]
        for name in (models.BODY, models.INTERIOR, models.GLASS, models.BONNET):
            assert name in drawn, 'the car does not draw its %s' % (name,)

    def test_a_model_with_no_bonnet_still_makes_a_car(self, floor, monkeypatch) -> None:
        """Only the player's car is looked out of; the traffic needs none."""
        real = models.ART.load

        def without(relative):
            scene = real(relative)
            found = scene.getDEF(models.BONNET) if scene is not None else None
            if found is not None:
                found.DEF = 'not-a-bonnet'
            return scene
        monkeypatch.setattr(models.ART, 'load', without)
        car = Car(floor)
        drawn = [one.DEF for one in _named(car.node)]
        assert models.INTERIOR in drawn and models.BONNET not in drawn

    def test_the_cockpit_view_takes_the_wheels_with_the_bodywork(self, floor) -> None:
        """Wheels without the arches around them are four discs in mid-air."""
        car = Car(floor)
        car.hidden = True
        assert not any(_shapes(node) and _visible(node, car)
                       for node in car._wheel_nodes)

    def test_the_rim_follows_the_front_wheels(self, floor) -> None:
        """Steering left turns the rim one way, right the other, straight none."""
        car = Car(floor)
        angles = {}
        for name, steer in (('left', 1.0), ('straight', 0.0), ('right', -1.0)):
            _drive(floor, car, 0.4, throttle=0.2, steer=steer)
            angles[name] = _rim_angle(car)
        assert angles['left'] > angles['straight'] > angles['right']

    def test_it_rolls_on_the_wheel_models(self, floor) -> None:
        car = Car(floor)
        assert len(car._wheel_nodes) == 4
        for node in car._wheel_nodes:
            assert _shapes(node), 'a wheel with nothing drawn in it'

    def test_a_missing_model_leaves_a_car_that_still_drives(self, floor, monkeypatch) -> None:
        """Art is not rules: without its model the car is drawn from primitives."""
        monkeypatch.setattr(models.ART, 'load', lambda relative: None)
        monkeypatch.setattr(models.ART, 'shared', lambda relative: None)
        car = Car(floor)
        _drive(floor, car, 1.0, throttle=0.5)
        assert _shapes(car.node), 'nothing at all is drawn'
        assert float(car.speed()) > 0.0


def _visible(node, car):
    """Whether a node is drawn: it is, unless a switched-off shell holds it."""
    return node in _reachable(car.node)


def _reachable(node, out=None):
    out = [] if out is None else out
    out.append(node)
    for child in ((getattr(node, 'children', None) or [])
                  + (getattr(node, 'choice', None) or [])[
                      :max(getattr(node, 'whichChoice', -1) + 1, 0)]):
        _reachable(child, out)
    return out


def _named(node, out=None):
    """Every node a subtree would *draw* that carries a DEF name.

    A switch is followed down the branch it has chosen and no other: what the
    other branches hold is exactly what is not on the screen.
    """
    out = [] if out is None else out
    if getattr(node, 'DEF', ''):
        out.append(node)
    for child in getattr(node, 'children', None) or ():
        _named(child, out)
    choices = getattr(node, 'choice', None) or ()
    which = getattr(node, 'whichChoice', -1)
    if choices and 0 <= which < len(choices):
        _named(choices[which], out)
    return out


def _rim_angle(car):
    rim = car.rim
    assert rim is not None
    axis = np.asarray(rim.rotation[:3], dtype='d')
    return float(rim.rotation[3]) * (1.0 if axis[1] >= 0.0 else -1.0)


class TestTheDriverSitsWhereTheModelPutsThem:
    """The cockpit eye against the interior it is inside of.

    The seat, the wheel and the roof are the model's; where the eye goes has to
    agree with them, or the driver looks through the dashboard, out of the roof
    or from the passenger's chair.
    """

    def _eye(self, floor):
        """The cockpit eye in the *model's* space, which is what it is checked
        against: the car is put at the origin, and the eye is brought back down
        by the drop the bodywork is hung at
        (:attr:`~glisteel.car.CarSpec.mass_drop`), since the body's own origin
        is where its mass is rather than the middle of the shell."""
        car = Car(floor, position=(0.0, 0.0, 0.0))
        camera = ChaseCamera('cockpit')
        eye = np.asarray(camera.update(car, 0.0).position, dtype='d')
        return eye - np.array([0.0, car.spec.mass_drop, 0.0]), car

    def test_the_eye_is_inside_the_cabin(self, floor) -> None:
        eye, car = self._eye(floor)
        low, high = bounds(models.ART.load(models.HERO).getDEF(models.INTERIOR))
        assert low[1] < eye[1] < BODY_HEIGHT / 2.0 + CABIN_HEIGHT, 'through the roof'
        assert low[2] - 0.3 < eye[2] < high[2] + 0.3, 'not in the cabin at all'

    def test_the_eye_is_behind_the_wheel(self, floor) -> None:
        """A driver looks past the rim, not from in front of it."""
        eye, car = self._eye(floor)
        wheel = bounds(models.ART.load(models.HERO).getDEF(models.COLUMN))
        assert eye[2] > wheel[1][2], 'the eye is ahead of the steering wheel'

    def test_the_eye_is_over_the_driver_s_seat(self, floor) -> None:
        """The player sits where the model puts the wheel, wherever that is.

        This car seats two in single file down the centreline, so both the seat
        and the wheel are there; a model that moved the wheel to one side would
        have to bring the eye with it, which is what this holds.
        """
        eye, car = self._eye(floor)
        wheel = bounds(models.ART.load(models.HERO).getDEF(models.COLUMN))
        side = (wheel[0][0] + wheel[1][0]) / 2.0
        assert abs(eye[0] - side) < 0.20, 'the eye is not over the wheel'


def _faces_of(mesh):
    """Every triangle of a mesh, as ``(a, b, c)`` corner positions."""
    points = np.asarray(mesh.positions, dtype='d')
    index = np.asarray(mesh.indices).ravel()
    corners = points[index]
    return corners[0::3], corners[1::3], corners[2::3]


def _outward(mesh):
    """How far each triangle's normal agrees with facing away from the middle.

    A closed convex-ish shell drawn with the engine's own front-face winding has
    every triangle pointing away from the body it encloses. Negative means the
    triangle faces into it, which the renderer culls and the shading lights from
    the wrong side.
    """
    a, b, c = _faces_of(mesh)
    normals = np.cross(b - a, c - a)
    middle = np.asarray(mesh.positions, dtype='d').mean(axis=0)
    return np.einsum('ij,ij->i', normals, (a + b + c) / 3.0 - middle)


class TestThePrimitiveCarIsWoundTheRightWayRound:
    """The car drawn when a model will not load.

    Art is not rules and the game starts without its ``.glb`` files, which is
    only true if what it falls back to can actually be seen: the render pass
    draws front faces wound counter-clockwise and culls the rest
    (``OpenGLContext.passes._flat``), and ``PBRMesh`` is solid and single-sided
    by default, so a shell wound inward is a shell that is not drawn. The
    normals come off the same winding, so it is also what lights it.
    """

    def test_the_body_faces_outward(self) -> None:
        found = _outward(car_body_mesh(PBRMaterial()))
        assert (found > 0).all(), '%d of %d body triangles face inward' % (
            int((found <= 0).sum()), len(found))

    def test_the_cabin_faces_outward(self) -> None:
        found = _outward(cabin_mesh(PBRMaterial()))
        assert (found > 0).all(), '%d of %d cabin triangles face inward' % (
            int((found <= 0).sum()), len(found))

    def test_the_wheel_faces_outward(self) -> None:
        found = _outward(wheel_mesh())
        assert (found > 0).all(), '%d of %d wheel triangles face inward' % (
            int((found <= 0).sum()), len(found))

    def test_the_normals_it_carries_agree_with_its_winding(self) -> None:
        # The shading normals are built from the faces, so if the two ever
        # disagree the shape is lit as something other than what is drawn.
        for mesh in (car_body_mesh(PBRMaterial()), cabin_mesh(PBRMaterial()),
                     wheel_mesh()):
            a, b, c = _faces_of(mesh)
            from_winding = np.cross(b - a, c - a)
            carried = np.asarray(mesh.normals, dtype='d')[0::3]
            assert (np.einsum('ij,ij->i', from_winding, carried) > 0).all()
