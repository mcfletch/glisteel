"""The world a race is held in: a baked tileset, its physics, and its roads.

A world arrives as a directory someone baked -- a ``tileset.json``, a ``.glb``
per tile, and the textures they share. The game streams it through
:class:`~OpenGLContext.scenegraph.tilesterrain.TilesTerrain`, which pages tiles
in around the car and hands each one to the physics world as a static collider,
so the car drives on the same triangles the player sees.

**The roads come with it.** A pile of triangles does not say where a track goes,
so the baker writes the centreline into the tileset's ``extras`` and
:class:`Course` reads it back. That is what puts the car on the grid, decides
which way it faces, and tells the timing where the lap begins.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any

import numpy as np
from omi_physics import model
from omi_physics.world import PhysicsWorld
from OpenGLContext.loaders.tiles3d import fetch
from OpenGLContext.scenegraph.tilesterrain import TilesTerrain

__all__ = ['Course', 'RaceWorld', 'load_courses']

#: How much memory the streamer may hold in tiles. A racing camera sees a long
#: way and returns to the same ground every lap, so a circuit is worth keeping
#: resident where a walking demo would page.
DEFAULT_MEMORY = 768 * 1024 * 1024

#: Screen-space error the streamer refines to. Lower is sharper and costs more;
#: at speed the road ahead matters more than the hillside beside it.
DEFAULT_SSE = 12.0

#: The camera's vertical field of view, and how far it sees. The streamer has
#: to agree with the renderer about both or it prepares tiles for a frame that
#: is not the one drawn.
FOV = math.radians(55.0)
VIEW_DISTANCE = 4000.0


@dataclass
class Course:
    """A road out of a baked world: where it goes and how wide it is."""

    name: str
    centreline: np.ndarray
    carriageway_width: float
    total_width: float
    closed: bool
    length: float

    def point(self, index: int) -> np.ndarray:
        """One point of the centreline, wrapping round a closed circuit."""
        point: np.ndarray = self.centreline[index % len(self.centreline)]
        return point

    def heading_at(self, index: int) -> float:
        """Which way the road runs there, as a yaw in radians from -Z.

        The direction from this point to the next, which is the way a car
        parked here should face.
        """
        ahead = self.point(index + 1) - self.point(index)
        return math.atan2(float(ahead[0]), -float(ahead[2]))

    def nearest(self, position: Any) -> tuple[int, float]:
        """The index of the nearest centreline point, and how far off it is.

        Distance is measured across the ground, so a car in the air over the
        track is still on it.
        """
        point = np.asarray(position, dtype='d')
        gaps = np.linalg.norm(self.centreline[:, [0, 2]] - point[[0, 2]], axis=1)
        index = int(gaps.argmin())
        return index, float(gaps[index])

    def on_road(self, position: Any) -> bool:
        """Whether a point is on the carriageway rather than beside it."""
        return self.nearest(position)[1] <= self.carriageway_width / 2.0

    def grid_position(self, index: int = 0, height: float = 1.0,
                      offset: float = 0.0) -> tuple[np.ndarray, float]:
        """Where to put a car on the grid, and the heading to give it.

        ``offset`` moves it across the road, for a second car on the row.
        """
        point = self.point(index)
        heading = self.heading_at(index)
        across = np.array([math.cos(heading), 0.0, math.sin(heading)])
        return point + np.array([0.0, height, 0.0]) + across * offset, heading


def load_courses(tileset_path: str) -> list[Course]:
    """The roads a baked world carries, or an empty list if it has none."""
    document = json.loads(fetch.read_bytes(tileset_path))
    roads = (document.get('extras') or {}).get('roads') or []
    out = []
    for road in roads:
        line = np.asarray(road['centreline'], dtype='d')
        if len(line) < 2:
            continue
        out.append(Course(
            name=str(road.get('name', 'road')),
            centreline=line,
            carriageway_width=float(road.get('carriagewayWidth', 7.0)),
            total_width=float(road.get('totalWidth', 12.0)),
            closed=bool(road.get('closed', False)),
            length=float(road.get('length', 0.0))))
    return out


class RaceWorld:
    """A baked world, streaming, with a physics world under it.

    Build one, mount :attr:`terrain` in a scenegraph, and call :meth:`stream`
    once a frame with wherever the camera is. The colliders follow the tiles, so
    physics only ever knows about ground that is actually loaded -- which is why
    :meth:`settled` exists: a car dropped before its tile arrives falls through
    the world.
    """

    def __init__(self, tileset_path: str, memory: int = DEFAULT_MEMORY,
                 max_sse: float = DEFAULT_SSE, gravity: float = 9.81) -> None:
        if not os.path.exists(tileset_path) and not fetch.is_url(tileset_path):
            raise SystemExit(
                "no world at %s -- bake one with 'oglc-bake --output %s'"
                % (tileset_path, os.path.dirname(tileset_path) or 'world'))
        self.path = tileset_path
        self.physics = PhysicsWorld(gravity=model.Gravity(gravity=abs(gravity)))
        self.terrain = TilesTerrain(tileset_path, physics_world=self.physics,
                                    memory_budget=memory, max_sse=max_sse)
        self.courses = load_courses(tileset_path)

    @property
    def course(self) -> Course | None:
        """The road a race is run on: the longest one the world carries."""
        if not self.courses:
            return None
        return max(self.courses, key=lambda road: road.length)

    def stream(self, camera: Any, viewport_height: float,
               view_projection: Any = None) -> Any:
        """One streaming tick, from wherever the camera is.

        ``view_projection`` is what lets the streamer cull: without it every
        tile in the world is a candidate to refine and to draw, including the
        half of it behind the car.
        """
        return self.terrain.update_for_camera(
            camera, viewport_height, view_projection=view_projection)

    def view_projection(self, eye: Any, target: Any, aspect: float,
                        fov: float = FOV, near: float = 0.5,
                        far: float | None = None) -> Any:
        """The matrix the streamer culls and measures screen-space error against.

        Built from where the camera *is going to be* this frame rather than read
        back from the renderer, because the streaming runs before the frame it
        is preparing tiles for.
        """
        from OpenGLContext.loaders.tiles3d.frustum import view_projection
        return view_projection(tuple(float(v) for v in eye),
                               tuple(float(v) for v in target), (0.0, 1.0, 0.0),
                               fov, aspect, near,
                               far if far is not None else VIEW_DISTANCE)

    def settled(self, camera: Any, viewport_height: float = 720.0,
                rounds: int = 24, timeout: float = 20.0) -> bool:
        """Stream until the ground under ``camera`` is loaded, or give up.

        A car placed on a road whose tile has not arrived falls through the
        world and keeps falling, so the grid waits for its ground.
        """
        for _ in range(rounds):
            self.stream(camera, viewport_height)
            self.terrain.runtime.wait_for_loads(timeout=timeout / rounds)
            self.stream(camera, viewport_height)
            if self.ground_under(camera) is not None:
                return True
        return False

    def ground_under(self, position: Any, reach: float = 200.0) -> float | None:
        """The height of the ground below a point, or None if nothing is there.

        The car's own bodies are not excluded, so ask before adding them or
        about a point that is not inside one.
        """
        from omi_physics.raycast import raycast
        point = np.asarray(position, dtype='d')
        hit = raycast(self.physics, point + np.array([0.0, 1.0, 0.0]),
                      (0.0, -1.0, 0.0), max_distance=reach)
        return None if hit is None else float(hit.point[1])

    def shutdown(self) -> None:
        """Stop the streamer's workers."""
        runtime = getattr(self.terrain, 'runtime', None)
        if runtime is not None:
            runtime.shutdown()


def static_ground(world: PhysicsWorld, size: float = 400.0,
                  height: float = 0.0) -> int:
    """A flat floor, for a test or a shakedown with no world to load."""
    shape = world.add_shape(model.Shape.box((size, 2.0, size)))
    return world.add_body(model.Motion(type=model.STATIC),
                          collider=model.Collider(shape=shape),
                          position=(0.0, height - 1.0, 0.0))
