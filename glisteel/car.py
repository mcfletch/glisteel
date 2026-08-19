"""The car: a body to render, a body to simulate, and the tuning between them.

The physics is ``omi_physics``' :class:`~omi_physics.vehicle.RaycastVehicle` --
a rigid chassis on four spring-loaded rays. What is here is everything that
makes it *this* car: the shape it is drawn as, the numbers that give it its
handling, and the scenegraph nodes that follow the simulation each frame.

The car is drawn from the model :mod:`glisteel.models` names -- bodywork,
interior and canopy as three named subtrees, and its wheels from their own
files, so that four of them turn and roll. A model that will not load leaves
the primitive car in :func:`car_body_mesh` and :func:`wheel_mesh` drawn in its
place: art is not rules, and a game that would not start without its ``.glb``
files has made a picture into a dependency.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from omi_physics import model
from omi_physics.vehicle import RaycastVehicle, VehicleTuning, car_wheels
from OpenGLContext.scenegraph.appearance import Appearance
from OpenGLContext.scenegraph.pbrmaterial import PBRMaterial
from OpenGLContext.scenegraph.pbrmesh import PBRMesh
from OpenGLContext.scenegraph.shape import Shape
from OpenGLContext.scenegraph.switch import Switch
from OpenGLContext.scenegraph.transform import Transform

from glisteel import models

log = logging.getLogger(__name__)

__all__ = ['Car', 'CarSpec', 'car_body_mesh', 'car_nodes',
           'wheel_mesh']

#: The car's own dimensions, in metres: a low sports car seating two in single file.
BODY_LENGTH = 4.2
BODY_WIDTH = 1.85
BODY_HEIGHT = 0.62
CABIN_HEIGHT = 0.19


@dataclass
class CarSpec:
    """What kind of car this is.

    ``mass`` and the wheels decide how it behaves; ``paint`` decides how it
    looks. The tuning defaults are a fast road car: enough power to spin the
    wheels out of a slow corner, enough brake to stop it, and a steering lock
    that eases off as the speed rises.
    """

    mass: float = 1180.0
    wheelbase: float = 2.55
    track: float = 1.58
    wheel_radius: float = 0.33
    ride_height: float = 0.14
    paint: tuple[float, float, float] = (0.62, 0.09, 0.07)
    tuning: VehicleTuning = field(default_factory=lambda: VehicleTuning(
        engine_force=9000.0, brake_force=16000.0, maximum_steer=0.52,
        steer_speed=3.2, rolling_resistance=0.02, downforce=6.0,
        # Full lock is half a radian, which is a car park; at speed the same
        # input has to be a gentler turn or every touch of a key is a spin. The
        # lock falls with the square of the speed against this
        # (:meth:`~omi_physics.vehicle.VehicleTuning.steer_lock`), and this
        # number is chosen so that full lock at the top end asks for about two
        # g -- hard cornering, and inside what the tyres and the wings have.
        steer_falloff_speed=10.0,
        # An electric drivetrain: all of it from a standstill, and constant
        # power from fifteen metres a second on, so the pull falls away as the
        # speed rises instead of shoving just as hard at a hundred and sixty.
        base_speed=15.0,
        # The air, and what actually decides how fast this car will go. Higher
        # than a coupe's own drag, which is the honest way to say that the top
        # speed is chosen -- a little under two hundred, which is what a forest
        # road with hundred-and-eighty-metre corners is worth driving at.
        drag=0.9))

    def wheels(self) -> list[Any]:
        """The four wheels, rear-driven, front-steered."""
        return car_wheels(wheelbase=self.wheelbase, track=self.track,
                          height=-BODY_HEIGHT / 2.0 + self.ride_height,
                          drive='rear', radius=self.wheel_radius,
                          suspension_travel=0.22, suspension_stiffness=26.0,
                          suspension_damping=0.55, grip=1.9)


class Car:
    """A car in a world: its physics, its scenegraph, and its controls.

    Add it to a :class:`~glisteel.world.RaceWorld`'s physics, mount
    :attr:`node` in the scene, drive it with :meth:`control`, and call
    :meth:`update` once per physics step and :meth:`follow` once per frame.
    Simulation and presentation are separate on purpose: physics runs at a fixed
    step and drawing runs at whatever the display manages.
    """

    def __init__(self, world: Any, spec: CarSpec | None = None,
                 position: Any = (0.0, 2.0, 0.0), heading: float = 0.0) -> None:
        self.spec = spec or CarSpec()
        self.world = world
        # The lower body, not the whole car. A collider is centred on the body
        # it belongs to, so a box tall enough to take in the canopy would reach
        # as far below the floor as the canopy stands above it and catch on the
        # road the wheels are holding the car off. What the taller box would add
        # is a glass roof to hit things with; what it would cost is the car
        # riding on its own collider.
        chassis = world.add_shape(model.Shape.box(
            (BODY_WIDTH, BODY_HEIGHT, BODY_LENGTH)))
        self.body = world.add_body(
            model.Motion(type=model.DYNAMIC, mass=self.spec.mass,
                         angularDamping=0.4),
            collider=model.Collider(shape=chassis), position=position)
        self.vehicle = RaycastVehicle(world, self.body, self.spec.wheels(),
                                      self.spec.tuning)
        self.vehicle.place(position, heading)
        #: What poses the steering wheel, or None where the model carries no
        #: ``steer`` clip -- the primitive car, or a model exported without it.
        self._steering: Any = None
        #: The rim the clip turns, for anything that wants to look at it.
        self.rim: Any = None
        self.node, self._shell, self._wheel_nodes = self._build_nodes()
        self._wheel_spin = [0.0] * len(self.vehicle.wheels)

    # -- driving ---------------------------------------------------------------

    def control(self, throttle: float = 0.0, brake: float = 0.0,
                steer: float = 0.0) -> None:
        self.vehicle.control(throttle=throttle, brake=brake, steer=steer)

    def update(self, dt: float) -> None:
        """One physics step's worth of vehicle forces."""
        self.vehicle.update(dt)

    def place(self, position: Any, heading: float = 0.0) -> None:
        self.vehicle.place(position, heading)

    @property
    def position(self) -> np.ndarray:
        return self.vehicle.position()

    def speed(self) -> float:
        return self.vehicle.speed()

    def speed_kph(self) -> float:
        return self.vehicle.speed() * 3.6

    def velocity(self) -> np.ndarray:
        """How fast it is going and which way, in metres per second.

        What deciding a crash needs: the severity of one is the relative
        velocity along the line between the two, and a scalar speed cannot say
        whether the other car is coming or going.
        """
        found: np.ndarray = np.asarray(
            self.world.linear_velocity[self.body], dtype='d')
        return found

    def forward(self) -> np.ndarray:
        return self.vehicle.forward()

    def upside_down(self) -> bool:
        """Whether the car has ended up on its roof."""
        return bool(self.vehicle.up()[1] < 0.1)

    # -- presentation ----------------------------------------------------------

    def follow(self, dt: float) -> None:
        """Move the scenegraph onto the simulation, and turn the wheels."""
        self.node.translation = tuple(float(v) for v in self.position)
        self.node.rotation = _axis_angle(self.world.orientation[self.body])
        for index, (wheel, node) in enumerate(
                zip(self.vehicle.wheels, self._wheel_nodes, strict=True)):
            local = np.asarray(wheel.spec.position, dtype='d')
            drop = wheel.spec.suspension_travel - wheel.compression
            node.translation = (float(local[0]), float(local[1] - drop),
                                float(local[2]))
            # Roll the wheel at the speed the car is going, and steer the ones
            # that steer. A wheel that does not turn makes a car look towed.
            self._wheel_spin[index] -= self.vehicle.forward_speed() * dt \
                / max(wheel.spec.radius, 1e-3)
            node.rotation = (0.0, 1.0, 0.0, wheel.steer_angle)
            node.children[0].rotation = (1.0, 0.0, 0.0, self._wheel_spin[index])
        self._turn_the_rim()

    def _turn_the_rim(self) -> None:
        """Pose the steering wheel at the fraction of lock the front wheels are at.

        The rim's travel is a clip in the model rather than an angle here, so
        how far it turns is the artist's decision: this only says how far
        through that travel the car is. The fraction comes from the wheels
        rather than from the driver's input because the steering lock eases off
        with speed -- a rim driven from the key would show full lock at a
        hundred and eighty while the front wheels were barely turned.
        """
        if self._steering is None:
            return
        lock = max(float(self.spec.tuning.maximum_steer), 1e-6)
        steered = [wheel.steer_angle for wheel in self.vehicle.wheels
                   if wheel.spec.steering]
        if not steered:                          # pragma: no cover - four fixed wheels
            return
        fraction = max(-1.0, min(1.0, float(np.mean(steered)) / lock))
        # The clip runs from full left at its first key to full right at its
        # last, and a positive steer angle is a turn to the left.
        self._steering.evaluate((0.5 - 0.5 * fraction) * self._steering.duration)

    @property
    def hidden(self) -> bool:
        """Whether the car's own bodywork is left out of the frame.

        For the view from the driver's seat, which is a point inside it: what
        that view would otherwise show is the outside of this car's bodywork,
        from within. The interior and the canopy stay -- they are what that view
        is *of* -- and the node stays in the scene and keeps following the
        physics, so nothing has to be added or removed as the player changes
        view.
        """
        return self._shell.whichChoice < 0

    @hidden.setter
    def hidden(self, value: bool) -> None:
        self._shell.whichChoice = -1 if value else 0

    def _build_nodes(self) -> tuple[Transform, Switch, list[Transform]]:
        """The scenegraph the car is drawn as: shells, wheels, and the rim.

        The bodywork sits in a ``Switch`` of its own so the cockpit view can
        drop it without touching anything else; everything the driver looks at
        from inside hangs outside that switch.
        """
        wheels = [Transform(children=[Transform(children=self._wheel_art(spec))])
                  for spec in self.vehicle.wheels]
        exterior, inside = self._shell_art()
        # The wheels are switched with the bodywork rather than with the
        # interior: they belong to the outside of the car, and four wheels
        # without the arches around them are discs rolling along in mid-air.
        # They keep following the suspension either way; a switch that is off
        # simply does not draw them.
        shell = Switch(choice=[Transform(children=[*exterior, *wheels])],
                       whichChoice=0)
        return Transform(children=[shell, *inside]), shell, wheels

    def _shell_art(self) -> tuple[list[Any], list[Any]]:
        """What is drawn outside the car, and what is drawn inside it."""
        scene = models.ART.load(models.HERO)
        if scene is not None:
            outside = [scene.getDEF(models.BODY)]
            inside = [scene.getDEF(models.INTERIOR), scene.getDEF(models.GLASS)]
            if all(node is not None for node in outside + inside):
                self._steering = scene.player_named(models.STEER_CLIP, loop=False)
                self.rim = scene.getDEF(models.RIM)
                return outside, inside
            log.warning('%s is missing one of its named shells', models.HERO)
        paint = PBRMaterial(baseColor=self.spec.paint, metallic=0.55,
                            roughness=0.32)
        glass = PBRMaterial(baseColor=(0.10, 0.13, 0.16), metallic=0.1,
                            roughness=0.08)
        return ([_painted(car_body_mesh(paint), paint)],
                [_painted(cabin_mesh(glass), glass)])

    def _wheel_art(self, spec: Any) -> list[Any]:
        """One wheel's geometry: the shipped model, or a cylinder.

        Both sides of an axle are the one model, mounted twice: a wheel is the
        same wheel wherever it is bolted on.
        """
        front = float(spec.spec.position[2]) < 0.0
        scene = models.ART.shared(models.HERO_WHEEL_FRONT if front
                                  else models.HERO_WHEEL_REAR)
        if scene is not None:
            return [scene.group]
        rubber = PBRMaterial(baseColor=(0.045, 0.045, 0.05), metallic=0.0,
                             roughness=0.85)
        return [_painted(wheel_mesh(spec.spec.radius, 0.24, rubber), rubber)]


def car_nodes(paint: tuple[float, float, float] = (0.62, 0.09, 0.07),
              wheel_radius: float = 0.33) -> Transform:
    """A car to look at: body, cabin and four wheels, and nothing to drive it.

    What a car standing in the world is made of, without the physics that makes
    one the player's. Traffic is drawn with this: its wheels do not turn and its
    suspension does not move, which nobody driving past at speed reads, and it
    costs a transform apiece instead of a raycast vehicle.
    """
    body = PBRMaterial(baseColor=paint, metallic=0.55, roughness=0.32)
    glass = PBRMaterial(baseColor=(0.10, 0.13, 0.16), metallic=0.1,
                        roughness=0.08)
    rubber = PBRMaterial(baseColor=(0.045, 0.045, 0.05), metallic=0.0,
                         roughness=0.85)
    half_track, half_base = 1.58 / 2.0, 2.55 / 2.0
    wheels = [
        Transform(children=[_painted(wheel_mesh(wheel_radius, 0.24, rubber),
                                     rubber)],
                  translation=(side * half_track,
                               -BODY_HEIGHT / 2.0 + wheel_radius,
                               end * half_base))
        for side in (-1.0, 1.0) for end in (-1.0, 1.0)]
    return Transform(children=[_painted(car_body_mesh(body), body),
                               _painted(cabin_mesh(glass), glass), *wheels])


def _painted(mesh: PBRMesh, material: PBRMaterial) -> Shape:
    """A mesh ready to render: the material on the Appearance, not only the mesh.

    The render pass takes a shape's material from its ``Appearance``. A mesh
    that carries one and sits in a bare Shape is drawn in the default grey,
    which is how a red car comes out white.
    """
    return Shape(geometry=mesh, appearance=Appearance(material=material))


def car_body_mesh(material: PBRMaterial) -> PBRMesh:
    """The car's lower body: a box drawn in at the nose and tail."""
    half_w, half_h = BODY_WIDTH / 2.0, BODY_HEIGHT / 2.0
    nose, tail = -BODY_LENGTH / 2.0, BODY_LENGTH / 2.0
    taper = 0.72
    return _box_mesh(
        bottom=[(-half_w * taper, -half_h, nose), (half_w * taper, -half_h, nose),
                (half_w, -half_h, tail * 0.2), (half_w * 0.86, -half_h, tail),
                (-half_w * 0.86, -half_h, tail), (-half_w, -half_h, tail * 0.2)],
        height=BODY_HEIGHT, material=material)


def cabin_mesh(material: PBRMaterial) -> PBRMesh:
    """The greenhouse: a shorter, narrower box sitting on the body."""
    half_w = BODY_WIDTH / 2.0 * 0.78
    base = BODY_HEIGHT / 2.0
    front, back = -0.35, BODY_LENGTH / 2.0 * 0.62
    return _box_mesh(
        bottom=[(-half_w * 0.8, base, front), (half_w * 0.8, base, front),
                (half_w, base, back * 0.5), (half_w * 0.9, base, back),
                (-half_w * 0.9, base, back), (-half_w, base, back * 0.5)],
        height=CABIN_HEIGHT, material=material)


def wheel_mesh(radius: float = 0.33, width: float = 0.24,
               material: PBRMaterial | None = None, sides: int = 16) -> PBRMesh:
    """A wheel: a cylinder lying on its side, its axis across the car."""
    angle = np.linspace(0.0, 2.0 * math.pi, sides, endpoint=False)
    circle = np.stack([np.zeros(sides), np.sin(angle) * radius,
                       np.cos(angle) * radius], axis=-1)
    left = circle - np.array([width / 2.0, 0.0, 0.0])
    right = circle + np.array([width / 2.0, 0.0, 0.0])
    points = np.vstack([left, right])
    faces: list[tuple[int, int, int]] = []
    for i in range(sides):
        j = (i + 1) % sides
        faces += [(i, j, sides + i), (j, sides + j, sides + i)]
    for i in range(1, sides - 1):                # the two discs
        faces.append((0, i + 1, i))
        faces.append((sides, sides + i, sides + i + 1))
    return _mesh(points, faces, material or PBRMaterial(baseColor=(0.05, 0.05, 0.05)))


def _box_mesh(bottom: list[tuple[float, float, float]], height: float,
              material: PBRMaterial) -> PBRMesh:
    """A prism: a closed outline extruded upward by ``height``.

    The outline runs clockwise seen from above, which is what makes the sides
    face outward and the caps face the way they should.
    """
    floor = np.asarray(bottom, dtype='d')
    roof = floor + np.array([0.0, height, 0.0])
    points = np.vstack([floor, roof])
    count = len(floor)
    faces: list[tuple[int, int, int]] = []
    for i in range(count):
        j = (i + 1) % count
        faces += [(i, j, count + i), (j, count + j, count + i)]
    for i in range(1, count - 1):
        faces.append((0, i, i + 1))                          # the floor
        faces.append((count, count + i + 1, count + i))      # the roof
    return _mesh(points, faces, material)


def _mesh(points: np.ndarray, faces: list[tuple[int, int, int]],
          material: PBRMaterial) -> PBRMesh:
    """A flat-shaded mesh: every triangle gets its own vertices and normal.

    A car body has creases, and sharing vertices between the panels either side
    of one rounds it off into a bar of soap.
    """
    indices = np.asarray(faces, dtype=np.int64)
    corners = points[indices.ravel()].astype('f')
    a, b, c = corners[0::3], corners[1::3], corners[2::3]
    face_normals = np.cross(b - a, c - a)
    lengths = np.linalg.norm(face_normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    normals = np.repeat(face_normals / lengths, 3, axis=0).astype('f')
    return PBRMesh(positions=corners, normals=normals, material=material,
                   indices=np.arange(len(corners), dtype=np.uint32))


def _axis_angle(quaternion: Any) -> tuple[float, float, float, float]:
    """A VRML ``(x, y, z, radians)`` rotation from an xyzw quaternion."""
    x, y, z, w = (float(v) for v in quaternion)
    length = math.sqrt(x * x + y * y + z * z)
    if length < 1e-9:
        return (0.0, 1.0, 0.0, 0.0)
    return (x / length, y / length, z / length,
            2.0 * math.atan2(length, w))
