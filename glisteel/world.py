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

import dataclasses
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


@dataclass(frozen=True)
class Structure:
    """A stretch of a road that is built rather than laid.

    ``kind`` is what it is -- a bridge, a tunnel, a causeway -- and ``start``
    and ``end`` are distances along the centreline, in metres.
    """

    kind: str
    start: float
    end: float

    def holds(self, station: Any, along: float = 0.0) -> Any:
        """Whether each of these distances along the road falls inside it.

        ``along`` extends it that far up each approach, for a caller that needs
        the stretch leading to a structure as well as the structure itself.
        """
        distance = np.asarray(station, dtype='d')
        return ((distance >= self.start - along)
                & (distance <= self.end + along))


@dataclass
class Course:
    """A road out of a baked world: where it goes and how wide it is."""

    name: str
    centreline: np.ndarray
    carriageway_width: float
    total_width: float
    closed: bool
    length: float
    structures: tuple[Structure, ...] = ()
    #: The road's cross-section as the world wrote it, or empty for a world
    #: that only said how wide the road is.
    profile: dict[str, Any] = dataclasses.field(default_factory=dict)

    def road_profile(self) -> Any:
        """The cut across the road, as the engine's own profile.

        What a collider for the carriageway is swept from. A world that did not
        write its section gets one built from the two widths it did write, which
        is the shape of the road even if not every drop of it.
        """
        from OpenGLContext.scenegraph.road import RoadProfile
        found = self.profile
        if found:
            return RoadProfile(
                lane_width=float(found['laneWidth']),
                lanes=int(found['lanes']),
                shoulder_width=float(found['shoulderWidth']),
                shoulder_drop=float(found['shoulderDrop']),
                verge_width=float(found['vergeWidth']),
                verge_drop=float(found['vergeDrop']),
                crossfall=float(found['crossfall']),
                texture_length=float(found['textureLength']))
        beside = max(self.total_width - self.carriageway_width, 0.0) / 2.0
        return RoadProfile(lane_width=self.carriageway_width / 2.0, lanes=2,
                           shoulder_width=beside * 0.4,
                           verge_width=beside * 0.6)

    @property
    def stations(self) -> np.ndarray:
        """Distance along the road to each centreline point."""
        steps = np.linalg.norm(np.diff(self.centreline, axis=0), axis=1)
        return np.concatenate([[0.0], np.cumsum(steps)])

    def inside(self, kind: str, x: Any, z: Any, margin: float = 0.0,
               along: float = 0.0) -> Any:
        """Which of these ground positions lie over a structure of ``kind``.

        What a bore needs from the ground it runs through: the surface is still
        drawn over a tunnel, and a collider left there is a wall across the
        road. ``margin`` widens the answer beyond the road's own width, so the
        opening clears the bore rather than grazing it, and ``along`` extends it
        up the approaches: the ground beside a portal is a cutting sampled on a
        grid metres wide, and where that meets the untouched hillside it rides
        over the carriageway by the better part of a step.
        """
        wanted = [one for one in self.structures if one.kind == kind]
        found = np.zeros(np.shape(np.asarray(x, dtype='d')), dtype=bool)
        if not wanted:
            return found
        reach = self.total_width / 2.0 + margin
        stations = self.stations
        line = self.centreline
        points = np.stack([np.asarray(x, 'd').ravel(),
                           np.asarray(z, 'd').ravel()], axis=-1)
        for one in wanted:
            run = one.holds(stations, along=along)
            if not run.any():
                continue
            near = line[run][:, [0, 2]]
            # Distance to the run's own points rather than to its segments: the
            # centreline is written densely enough that the difference is under
            # a metre, and the margin is metres.
            gaps = np.linalg.norm(points[:, None, :] - near[None, :, :], axis=-1)
            found |= (gaps.min(axis=1) <= reach).reshape(found.shape)
        return found

    def point(self, index: int) -> np.ndarray:
        """One point of the centreline, wrapping round a closed circuit."""
        point: np.ndarray = self.centreline[index % len(self.centreline)]
        return point

    def heading_at(self, index: int) -> float:
        """Which way the road runs there, as a yaw about the vertical.

        The direction from this point to the next, as the angle that turns a
        car to face it. A yaw of ``t`` sends the nose, which points down -Z, to
        ``(-sin t, 0, -cos t)`` -- so the angle is read off the *negated*
        direction. Taken from the direction itself the car ends up square
        across the road, which is what any road not lying along an axis finds.
        """
        ahead = self.point(index + 1) - self.point(index)
        return math.atan2(-float(ahead[0]), -float(ahead[2]))

    def nearest(self, position: Any) -> tuple[int, float]:
        """The nearest centreline point's index, and how far off the *road* it is.

        Distance is to the line, not to the points written down for it: a course
        is a shape sampled every few metres, and a car exactly on the line half
        way between two samples is on the line, not four metres off it. The
        index is still a point -- what a caller wants it for is to look up the
        road ahead -- and it is the nearer of the two the car lies between.

        Measured across the ground, so a car in the air over the track is still
        on it.
        """
        point = np.asarray(position, dtype='d')[[0, 2]]
        line = self.centreline[:, [0, 2]]
        gaps = np.linalg.norm(line - point, axis=1)
        index = int(gaps.argmin())
        start = line if self.closed else line[:-1]
        delta = np.roll(line, -1, axis=0) - line if self.closed \
            else line[1:] - line[:-1]
        length2 = np.einsum('ij,ij->i', delta, delta)
        along = np.clip(np.einsum('ij,ij->i', point - start, delta)
                        / np.where(length2 > 0, length2, 1.0), 0.0, 1.0)
        off = np.linalg.norm(start + along[:, None] * delta - point, axis=1)
        return index, float(off.min())

    def on_road(self, position: Any) -> bool:
        """Whether a point is on the carriageway rather than beside it."""
        return self.nearest(position)[1] <= self.carriageway_width / 2.0

    @property
    def driving_lane(self) -> float:
        """How far from the centreline a car keeps, on a road with two ways.

        The middle of its own half of the carriageway, which is where a driver
        sits when something may be coming the other way.
        """
        return float(self.carriageway_width) / 4.0

    def across(self, index: int) -> np.ndarray:
        """The unit vector across the road there, pointing to its own right.

        The same frame everything swept along a road uses
        (:func:`OpenGLContext.scenegraph.road.sweep_frames`), so the driving
        line, the grid, the signs and the traffic all agree which side is
        which.
        """
        # A closed course's last point is its first, so the segment between
        # them has no direction. Looking on to the next one that does is what
        # keeps the seam agreeing with the road either side of it.
        here = self.point(index)
        for step in range(1, min(len(self.centreline), 8)):
            along = self.point(index + step) - here
            right = np.cross(along, (0.0, 1.0, 0.0))
            length = float(np.linalg.norm(right))
            if length > 1e-9:
                found: np.ndarray = right / length
                return found
        return np.array([1.0, 0.0, 0.0])         # pragma: no cover - a point

    def lane_point(self, index: int, offset: float = 0.0) -> np.ndarray:
        """A point of the centreline, moved ``offset`` metres to its right."""
        return self.point(index) + self.across(index) * float(offset)

    def grid_position(self, index: int = 0, height: float = 1.0,
                      offset: float = 0.0, lane: float = 0.0
                      ) -> tuple[np.ndarray, float]:
        """Where to put a car on the grid, and the heading to give it.

        ``offset`` moves it across the road, for a second car on the row.
        ``lane`` moves it to its own side of a road with traffic on it.
        """
        point = self.lane_point(index, lane)
        heading = self.heading_at(index)
        return (point + np.array([0.0, height, 0.0])
                + self.across(index) * offset), heading


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
            length=float(road.get('length', 0.0)),
            profile=dict(road.get('profile') or {}),
            structures=tuple(
                Structure(kind=str(one.get('kind', 'dirt')),
                          start=float(one.get('from', 0.0)),
                          end=float(one.get('to', 0.0)))
                for one in road.get('structures') or ())))
    return out


#: How far under a starting position its ground may be, in metres, before the
#: world counts as settled. A grid slot sits about a metre over the surface it
#: is on; anything much further down is a different surface.
SETTLE_DROP = 4.0

#: How far past a road's own width a bore's opening in the ground reaches, in
#: metres. Wide enough to clear the lining, and no wider: the opening is a hole
#: in the ground with the bore's own tube inside it, and one wider than the tube
#: is a trench beside the carriageway.
BORE_MARGIN = 2.0

#: How far up each approach the opening reaches, in metres. The ground beside a
#: portal is a cutting sampled on a grid metres wide, and where that meets the
#: untouched hillside it rides over the carriageway; the road's own surface
#: carries the car through, so opening the ground early costs nothing.
BORE_APPROACH = 24.0


class RaceWorld:
    """A baked world, streaming, with a physics world under it.

    Build one, mount :attr:`terrain` in a scenegraph, and call :meth:`stream`
    once a frame with wherever the camera is. The colliders follow the tiles, so
    physics only ever knows about ground that is actually loaded -- which is why
    :meth:`settled` exists: a car dropped before its tile arrives falls through
    the world.

    A world whose ground is a *field* rather than a tree of tiles brings its own
    colliders instead: the landscape is one height field, cut into chunks and
    held near the car. It settles the moment it is built, because there is
    nothing to wait for.

    ``traffic`` is how many other cars are on the road at once; zero is an empty
    circuit. They are kept near the player and topped up as they pass, so a lap
    meets a road's worth of traffic without a world's worth existing.
    """

    def __init__(self, tileset_path: str, memory: int = DEFAULT_MEMORY,
                 max_sse: float = DEFAULT_SSE, gravity: float = 9.81,
                 traffic: int = 0) -> None:
        if not os.path.exists(tileset_path) and not fetch.is_url(tileset_path):
            raise SystemExit(
                "no world at %s -- bake one with 'oglc-bake --output %s'"
                % (tileset_path, os.path.dirname(tileset_path) or 'world'))
        self.path = tileset_path
        self.physics = PhysicsWorld(gravity=model.Gravity(gravity=abs(gravity)))
        # No colliders from the tiles: tile geometry is level-of-detail
        # geometry, and a surface that changes resolution under the wheels is a
        # step to hit at speed. The two surfaces a car meets are built here
        # instead, each from the thing itself rather than from a drawing of it.
        self.terrain = TilesTerrain(tileset_path, memory_budget=memory,
                                    max_sse=max_sse)
        self.courses = load_courses(tileset_path)
        #: The ground, when the world carries its landscape as a field. The
        #: chunks near the car are in the physics world; the rest are not.
        self.ground: Any = None
        if self.terrain.field is not None:
            from OpenGLContext.physics.heightfield import HeightFieldColliders
            self.ground = HeightFieldColliders(self.physics,
                                               self.terrain.field,
                                               holes=self._bores())
        #: The carriageway, built from the course rather than from the tiles.
        self.roads: list[Any] = []
        for road in self.courses:
            from OpenGLContext.physics.road import RoadColliders
            self.roads.append(RoadColliders(
                self.physics, road.centreline, road.road_profile(),
                closed=road.closed))
        #: The obstacles: boulders and whatever else a world puts in the way.
        #: The ones near the car are in the physics world; the rest are not.
        from OpenGLContext.physics.props import PropColliders
        self.props = PropColliders(self.physics, self._props())
        #: The other cars using the road, or None for a world with no course.
        self.traffic: Any = None
        if traffic and self.course is not None:
            from glisteel.traffic import Traffic
            self.traffic = Traffic(self.course, count=int(traffic),
                                   physics=self.physics,
                                   ground=self.ground_under)

    def _props(self) -> list:
        """The obstacles this world carries, read off the tileset.

        Not off the tiles: tile geometry is level-of-detail geometry that
        arrives and leaves as the car moves, and a collider built from it would
        be a boulder the car drives through at the moment the tile behind it
        swaps. The baker writes them into ``extras`` for exactly this.
        """
        from OpenGLContext.scenegraph.props import Prop
        document = json.loads(fetch.read_bytes(self.path))
        found = (document.get('extras') or {}).get('props') or []
        return [Prop.from_json(one) for one in found]

    def _bores(self) -> Any:
        """Where the ground is not there, because a road runs inside it.

        A field terrain is a surface and keeps the hill a tunnel passes through,
        which is right to look at and a wall to drive into. The bores are cut
        out of the collider; the bore's own lining, which streams with the tile
        it is in, is what the car actually drives through.
        """
        tunnelled = [road for road in self.courses
                     if any(one.kind == 'tunnel' for one in road.structures)]
        if not tunnelled:
            return None

        def opened(x: Any, z: Any) -> Any:
            found = np.zeros(np.shape(np.asarray(x, dtype='d')), dtype=bool)
            for road in tunnelled:
                found |= road.inside('tunnel', x, z, margin=BORE_MARGIN,
                                     along=BORE_APPROACH)
            return found
        return opened

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
        if self.ground is not None:
            self.ground.update(camera)
        for road in self.roads:
            road.update(camera)
        self.props.update(camera)
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
                rounds: int = 24, timeout: float = 20.0,
                drop: float = SETTLE_DROP) -> bool:
        """Stream until there is ground within ``drop`` under ``camera``.

        A car placed on a road whose tile has not arrived falls through the
        world and keeps falling, so the grid waits for its ground.

        Within ``drop`` rather than anywhere below: a car on a viaduct has the
        valley floor ninety metres under it from the first frame, and a start
        that took that for its ground would drop the car off the deck.
        """
        for _ in range(rounds):
            self.stream(camera, viewport_height)
            if self._standing_on(camera, drop):
                return True
            self.terrain.runtime.wait_for_loads(timeout=timeout / rounds)
            self.stream(camera, viewport_height)
            if self._standing_on(camera, drop):
                return True
        return False

    def _standing_on(self, camera: Any, drop: float) -> bool:
        """Whether there is a surface close enough under a point to stand on."""
        found = self.ground_under(camera)
        if found is None:
            return False
        return bool(float(np.asarray(camera, dtype='d')[1]) - found <= drop)

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
