"""The car: a body to render, a body to simulate, and the tuning between them.

The physics is ``omi_physics``' :class:`~omi_physics.vehicle.RaycastVehicle` --
a rigid chassis on four spring-loaded rays. What is here is everything that
makes it *this* car: the shape it is drawn as, the numbers that give it its
handling, and the scenegraph nodes that follow the simulation each frame.

The car is drawn from primitives rather than loaded from a file, so the game
runs from a checkout with no assets to fetch. :func:`car_body_mesh` is a
low-slung coupé built out of two tapered boxes; the wheels are cylinders that
turn with the steering and roll with the speed.
"""
from __future__ import annotations

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
from OpenGLContext.scenegraph.transform import Transform

__all__ = ['Car', 'CarSpec', 'car_body_mesh', 'wheel_mesh']

#: The car's own dimensions, in metres: a low two-seat coupé.
BODY_LENGTH = 4.2
BODY_WIDTH = 1.85
BODY_HEIGHT = 0.62
CABIN_HEIGHT = 0.42


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
        steer_falloff_speed=26.0))

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
        chassis = world.add_shape(model.Shape.box(
            (BODY_WIDTH, BODY_HEIGHT, BODY_LENGTH)))
        self.body = world.add_body(
            model.Motion(type=model.DYNAMIC, mass=self.spec.mass,
                         angularDamping=0.4),
            collider=model.Collider(shape=chassis), position=position)
        self.vehicle = RaycastVehicle(world, self.body, self.spec.wheels(),
                                      self.spec.tuning)
        self.vehicle.place(position, heading)
        self.node, self._wheel_nodes = self._build_nodes()
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

    def _build_nodes(self) -> tuple[Transform, list[Transform]]:
        paint = PBRMaterial(baseColor=self.spec.paint, metallic=0.55,
                            roughness=0.32)
        glass = PBRMaterial(baseColor=(0.10, 0.13, 0.16), metallic=0.1,
                            roughness=0.08)
        rubber = PBRMaterial(baseColor=(0.045, 0.045, 0.05), metallic=0.0,
                             roughness=0.85)
        wheels: list[Transform] = []
        for spec in self.vehicle.wheels:
            spin = Transform(children=[_painted(
                wheel_mesh(spec.spec.radius, 0.24, rubber), rubber)])
            wheels.append(Transform(children=[spin]))
        body = _painted(car_body_mesh(paint), paint)
        cabin = _painted(cabin_mesh(glass), glass)
        return Transform(children=[body, cabin, *wheels]), wheels


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
