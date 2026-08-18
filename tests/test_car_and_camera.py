"""The car and the camera, on a flat floor with nothing drawn.

Everything a car does that a player can feel is numbers, and so is everything
the camera does. What is left for a window is the picture, which
``tests/test_plays.py`` takes.
"""

import math

import numpy as np
import pytest
from omi_physics.world import PhysicsWorld

from glisteel.camera import ChaseCamera
from glisteel.car import Car, CarSpec, car_body_mesh, wheel_mesh
from glisteel.world import static_ground

STEP = 1.0 / 120.0


@pytest.fixture
def floor():
    world = PhysicsWorld()
    static_ground(world, size=4000.0)
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
        from omi_physics.vehicle import car_wheels
        stiff = Car(floor, CarSpec(), position=(-20.0, 2.0, 0))
        soft = Car(floor, CarSpec(), position=(20.0, 2.0, 0))
        soft.vehicle.wheels = [
            type(wheel)(spec=spec) for wheel, spec in zip(
                soft.vehicle.wheels,
                car_wheels(suspension_stiffness=8.0, radius=0.33,
                           suspension_travel=0.22), strict=True)]
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

    def test_the_car_has_a_body_a_cabin_and_four_wheels(self, floor) -> None:
        car = Car(floor, position=(0, 1.0, 0))
        assert len(car.node.children[0].choice[0].children) == 6


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

    def test_the_body_wears_the_paint_it_was_given(self, floor) -> None:
        car = Car(floor, CarSpec(paint=(0.8, 0.1, 0.05)), position=(0, 1.0, 0))
        colours = [tuple(round(float(v), 3)
                         for v in shape.appearance.material.baseColor)
                   for shape in _shapes(car.node)]
        assert (0.8, 0.1, 0.05) in colours

    def test_the_tyres_are_black_and_the_glass_is_not_the_paint(self, floor) -> None:
        car = Car(floor, CarSpec(paint=(0.8, 0.1, 0.05)), position=(0, 1.0, 0))
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
        assert 35.0 < car.speed() < 70.0

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
