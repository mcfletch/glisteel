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
import functools
import json
import math
import os
from dataclasses import dataclass
from typing import Any

import numpy as np
from omi_physics import model
from omi_physics.raycast import raycast
from omi_physics.world import PhysicsWorld
from OpenGLContext.loaders.tiles3d import fetch
from OpenGLContext.loaders.tiles3d.frustum import view_projection as frustum_matrix
from OpenGLContext.scenegraph.tilesterrain import TilesTerrain

from glisteel.geometry import yaw_to_face

__all__ = ['Course', 'RaceWorld', 'courses_in', 'load_courses']

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

#: How far under a starting position its ground may be, in metres, before the
#: world counts as settled. A grid slot sits about a metre over the surface it
#: is on; anything much further down is a different surface.
SETTLE_DROP = 4.0

#: How far in from the end of an open road a car is put, in metres. Longer than
#: a car, so all four wheels are on the surface rather than the back two hanging
#: over the end of it.
GRID_SETBACK = 12.0

#: How far under the world's own datum a car has to be to have left it, in
#: metres. Far enough that a viaduct's valley is not "gone" -- a car on the deck
#: has ninety metres of air under it and has fallen nowhere.
LOST_BELOW = 500.0

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

#: The most lamps a world may declare. A bore has one every twenty-five metres,
#: so a world of them is thousands rather than millions: past this the number is
#: not a world but an allocation, and a tileset is something a player may have
#: been handed by somebody else.
MOST_LUMINAIRES = 1_000_000


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


# ``eq=False`` throughout the array-carrying dataclasses here and in
# :mod:`glisteel.trace`, :mod:`glisteel.session` and :mod:`glisteel.scenarios`:
# a generated ``__eq__`` compares field by field, and comparing two numpy arrays
# gives an array of answers rather than one, so asking whether it is true
# raises. A course is a *thing* rather than a value -- the road this race is on
# -- so it is itself and no other, which is what identity comparison says and
# what lets one go in a set or be looked for in a list.
@dataclass(eq=False)
class Course:
    """A road out of a baked world: where it goes and how wide it is.

    Compared by identity: two courses are the same course when they are the same
    road, not when they happen to have been read from the same file twice.
    """

    name: str
    centreline: np.ndarray
    carriageway_width: float
    total_width: float
    closed: bool
    length: float
    #: How far along the centreline the lap begins, in metres -- where the
    #: world drew its own start line and stood its gantry. Zero for a road with
    #: no line on it, which is where its own start is anyway.
    start: float = 0.0
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

    @functools.cached_property
    def _section(self) -> Any:
        """This road's cross-section, worked out once.

        A baked world's road does not change shape, and this is asked about
        every vehicle on it every frame.
        """
        return self.road_profile()

    def surface_offset(self, across: Any) -> Any:
        """How far below the crown the road's surface is, that far out.

        ``across`` is one distance from the centreline or an array of them, in
        metres. What puts anything placed by how far along and how far across
        the road it is -- a traffic car, a marker -- at the height the road
        actually is there, rather than at the height of its crown.
        """
        return self._section.section_offset(across)

    @functools.cached_property
    def stations(self) -> np.ndarray:
        """Distance along the road to each centreline point.

        Worked out once. A course is read from a baked world and does not move
        after that, and this is asked for by everything that places anything
        along the road -- every traffic car, every frame. Call :meth:`moved` if
        the line is ever replaced under it.
        """
        steps = np.linalg.norm(np.diff(self.centreline, axis=0), axis=1)
        return np.concatenate([[0.0], np.cumsum(steps)])

    @functools.cached_property
    def segments(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The road's segments on the ground: where each starts, where it goes,
        and the square of how long it is.

        What :meth:`nearest` measures against, worked out once rather than per
        question: the alternative is a fresh copy of the whole centreline, two
        dot products and a division every time anything asks where the car is,
        which several things do about the same car in the same frame.
        """
        line = self.centreline[:, [0, 2]]
        if self.closed:
            starts = line
            delta = np.roll(line, -1, axis=0) - line
        else:
            starts, delta = line[:-1], line[1:] - line[:-1]
        length2 = np.einsum('ij,ij->i', delta, delta)
        return starts, delta, np.where(length2 > 0, length2, 1.0)

    @functools.cached_property
    def radii(self) -> np.ndarray:
        """The radius of the bend at each point of the line, in metres.

        The circle through each point and its two neighbours, measured on the
        ground. Pure geometry, and therefore settled the moment the course is:
        how fast a bend may be taken depends on the driver, but how tight it is
        does not. A straight gives an enormous radius rather than an infinite
        one, which whatever reads it then caps -- the alternative is a special
        case in every caller.

        What reads it is :meth:`glisteel.driver.Autopilot.target_speed`, which
        wants the tightest bend within braking distance and would otherwise work
        out sixty of these per driver per frame.
        """
        line = self.ground_line
        before = np.roll(line, 1, axis=0)
        after = np.roll(line, -1, axis=0)
        if not self.closed:
            # An open road has no bend at its ends: hold the first and last to
            # their neighbours rather than wrapping onto the other end of the
            # world.
            before[0], after[-1] = line[0], line[-1]
        first = np.linalg.norm(line - before, axis=1)
        second = np.linalg.norm(after - line, axis=1)
        third = np.linalg.norm(after - before, axis=1)
        side, other = line - before, after - before
        area2 = np.abs(side[:, 0] * other[:, 1] - side[:, 1] * other[:, 0])
        return np.where(area2 < 1e-9, 1e6,
                        first * second * third / (2.0 * np.maximum(area2, 1e-30)))

    #: The last position :meth:`nearest` was asked about and what it answered.
    _last_nearest: tuple[tuple[float, float], tuple[int, float]] | None = None

    def moved(self) -> None:
        """The line has been replaced: forget what was worked out from it.

        Nothing in the game does this -- a baked world's road is what it is --
        but a tool that edits a course in place has to be able to say so, and a
        cache with no way to clear it is a trap rather than a saving.
        """
        for name in ('stations', 'segments', 'ground_line', 'radii',
                     '_section', 'start_index'):
            self.__dict__.pop(name, None)
        self._last_nearest = None

    @functools.cached_property
    def ground_line(self) -> np.ndarray:
        """The centreline seen from above, which is what distances are taken in."""
        found: np.ndarray = self.centreline[:, [0, 2]]
        return found

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
        line = self.ground_line
        points = np.stack([np.asarray(x, 'd').ravel(),
                           np.asarray(z, 'd').ravel()], axis=-1)
        flat = found.reshape(-1)
        for one in wanted:
            run = one.holds(stations, along=along)
            if not run.any():
                continue
            near = line[run]
            self._within(points, near, reach, flat)
        return found

    #: How many ground samples are measured against a structure at a time. The
    #: work is samples times road points, and a field terrain asks about a whole
    #: chunk at once against a road that may be thousands of points long -- so
    #: the whole product is never held, only a slice of it. Large enough that
    #: numpy is doing the work rather than the loop around it.
    CHUNK = 4096

    def _within(self, points: np.ndarray, near: np.ndarray, reach: float,
                found: np.ndarray) -> None:
        """Mark every point within ``reach`` of any of ``near``, in place.

        Distance to the run's own points rather than to its segments: the
        centreline is written densely enough that the difference is under a
        metre, and the margin is metres.

        Two things keep this off the point-by-point matrix it reads as. Only the
        samples inside the run's own bounding box, grown by ``reach``, can be
        near it at all -- which on a road that crosses a landscape is nearly all
        of them ruled out by two comparisons. What is left is measured
        :attr:`CHUNK` samples at a time, so the largest array in flight is a
        slice rather than the product.
        """
        low = near.min(axis=0) - reach
        high = near.max(axis=0) + reach
        maybe = np.flatnonzero(np.all((points >= low) & (points <= high), axis=1))
        for start in range(0, len(maybe), self.CHUNK):
            batch = maybe[start:start + self.CHUNK]
            gaps = points[batch][:, None, :] - near[None, :, :]
            close = np.einsum('ijk,ijk->ij', gaps, gaps).min(axis=1) <= reach ** 2
            found[batch[close]] = True

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
        return yaw_to_face(self.point(index + 1) - self.point(index))

    def nearest(self, position: Any) -> tuple[int, float]:
        """The nearest centreline point's index, and how far off the *road* it is.

        Distance is to the line, not to the points written down for it: a course
        is a shape sampled every few metres, and a car exactly on the line half
        way between two samples is on the line, not four metres off it. The
        index is still a point -- what a caller wants it for is to look up the
        road ahead -- and it is the nearer of the two the car lies between.

        Measured across the ground, so a car in the air over the track is still
        on it.

        The last answer is kept. Within one physics step the lap timing, the
        off-road watch, whoever is driving and the steering aid all ask about
        the same car, which has not moved in between -- so the second and third
        of those are answered without another pass over the line.
        """
        wanted = np.asarray(position, dtype='d').reshape(-1)
        key = (float(wanted[0]), float(wanted[2]))
        if self._last_nearest is not None and self._last_nearest[0] == key:
            found: tuple[int, float] = self._last_nearest[1]
            return found
        answer = self._nearest(key)
        self._last_nearest = (key, answer)
        return answer

    def _nearest(self, where: tuple[float, float]) -> tuple[int, float]:
        """:meth:`nearest`, without the memo in front of it."""
        point = np.asarray(where, dtype='d')
        line = self.ground_line
        gaps = np.linalg.norm(line - point, axis=1)
        index = int(gaps.argmin())
        start, delta, length2 = self.segments
        along = np.clip(np.einsum('ij,ij->i', point - start, delta) / length2,
                        0.0, 1.0)
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

    @functools.cached_property
    def start_index(self) -> int:
        """Which point of the line a car is put on to begin with.

        The point nearest :attr:`start`, which is where the world drew its
        chequered line and stood its gantry: a car stood anywhere else is a car
        on a grid the lap is not timed from, and on a circuit routed through a
        landscape that is as likely to be a shoulder on a bend as a straight.

        An open road has no line, and its first point is a place where half the
        car hangs over the end with nothing under the back wheels, so the grid
        is set back far enough along it for a car to stand on the road.
        """
        wanted = max(float(self.start), 0.0 if self.closed else GRID_SETBACK)
        found = int(np.searchsorted(self.stations, wanted))
        if self.closed:
            return found % len(self.centreline)
        return min(found, max(len(self.centreline) - 2, 0))

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
    return courses_in(json.loads(fetch.read_bytes(tileset_path)))


def courses_in(document: Any) -> list[Course]:
    """The roads in a tileset document already read.

    Separate from :func:`load_courses` because a world wants the roads, the
    obstacles and the lamps out of one file, and reading it three times to get
    them is three parses of a document that can be large.
    """
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
            start=float(road.get('start', 0.0)),
            profile=dict(road.get('profile') or {}),
            structures=tuple(
                Structure(kind=str(one.get('kind', 'dirt')),
                          start=float(one.get('from', 0.0)),
                          end=float(one.get('to', 0.0)))
                for one in road.get('structures') or ())))
    return out


def _baked_props(extras: Any) -> list:
    """The obstacles a world carries, out of its tileset's ``extras``.

    Not off the tiles: tile geometry is level-of-detail geometry that arrives
    and leaves as the car moves, and a collider built from it would be a boulder
    the car drives through at the moment the tile behind it swaps. The baker
    writes them into ``extras`` for exactly this.
    """
    from OpenGLContext.scenegraph.props import Prop
    return [Prop.from_json(one) for one in (extras.get('props') or [])]


def _baked_luminaires(extras: Any) -> Any:
    """Where the lamps hang in a world's bores, out of its tileset's ``extras``.

    The pool each throws is baked onto the lining and needs nothing from the
    game. These are for lighting what is *in* the bore -- the car, and the road
    under it -- which the lining cannot do.
    """
    wanted = extras.get('luminaires') or []
    if len(wanted) > MOST_LUMINAIRES:
        raise ValueError(
            'this world declares %d luminaires, which is more than a world has '
            '(the limit is %d)' % (len(wanted), MOST_LUMINAIRES))
    try:
        found = np.asarray(wanted, dtype='d')
    except (TypeError, ValueError) as error:
        raise ValueError('the luminaires in this world are not numbers: %s'
                         % (error,)) from error
    if found.size % 3 or (found.size and found.ndim not in (1, 2)):
        raise ValueError(
            'the luminaires in this world are %d numbers, which is not a whole '
            'number of points' % found.size)
    return found.reshape(-1, 3)


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

    #: Where this world was read from, or None for one built from a course.
    path: str | None
    #: The tile tree that streams, or None for a world with no tiles.
    terrain: Any

    def __init__(self, tileset_path: str = '', memory: int = DEFAULT_MEMORY,
                 max_sse: float = DEFAULT_SSE, gravity: float = 9.81,
                 traffic: int = 0, _nothing_to_stream: bool = False) -> None:
        # A world built from a course has nothing to read and nothing to
        # stream, and says so here rather than by being constructed around
        # ``__init__`` -- which left two places that had to agree about what a
        # half-built world looks like. See :meth:`from_course`.
        self.path = None
        self.terrain = None
        if _nothing_to_stream:
            return
        if not os.path.exists(tileset_path) and not fetch.is_url(tileset_path):
            # An ordinary exception rather than SystemExit: this is a library
            # class, and a menu that offered a world which has since been moved
            # has to be able to say so and stay running. Turning it into an exit
            # is the command line's decision, and it makes it in
            # :func:`glisteel.game.main`.
            raise FileNotFoundError(
                "no world at %s -- bake one with 'oglc-bake --output %s'"
                % (tileset_path, os.path.dirname(tileset_path) or 'world'))
        self.path = tileset_path
        # No colliders from the tiles: tile geometry is level-of-detail
        # geometry, and a surface that changes resolution under the wheels is a
        # step to hit at speed. The two surfaces a car meets are built here
        # instead, each from the thing itself rather than from a drawing of it.
        self.terrain = TilesTerrain(tileset_path, memory_budget=memory,
                                    max_sse=max_sse)
        # One read and one parse. The roads, the obstacles and the lamps are
        # three readers of one file, and a tileset for a world worth driving is
        # not a small one.
        document = json.loads(fetch.read_bytes(tileset_path))
        extras = (document.get('extras') or {})
        self._assemble(courses_in(document), field=self.terrain.field,
                       props=_baked_props(extras), traffic=traffic,
                       gravity=gravity, luminaires=_baked_luminaires(extras))

    @classmethod
    def from_course(cls, courses: Any, field: Any = None, props: Any = (),
                    traffic: int = 0, gravity: float = 9.81) -> RaceWorld:
        """A world made of a road and its ground, with no tiles to stream.

        Everything a car meets is here -- the carriageway swept from the
        centreline, the ground as a height field, the props standing on it and
        the traffic using the road -- and nothing is drawn. That is what a
        scenario is (:mod:`glisteel.scenarios`): a few hundred metres of road
        with one question in it, built in the time a test can afford.

        ``courses`` is one :class:`Course` or several, ``field`` the ground as
        a :class:`~OpenGLContext.scenegraph.terrain.heightfield.HeightField`,
        and ``props`` whatever stands beside the road.
        """
        world = cls(_nothing_to_stream=True)
        world._assemble(
            [courses] if isinstance(courses, Course) else list(courses),
            field=field, props=list(props), traffic=traffic, gravity=gravity)
        return world

    def _assemble(self, courses: list[Course], field: Any, props: list,
                  traffic: int, gravity: float, luminaires: Any = None) -> None:
        """Stand up the physics, the surfaces, the obstacles and the traffic."""
        self.physics = PhysicsWorld(gravity=model.Gravity(gravity=abs(gravity)))
        self.courses = courses
        #: The landscape this world carries, or None where it has none.
        self.field = field
        #: The ground, when the world carries its landscape as a field. The
        #: chunks near the car are in the physics world; the rest are not.
        self.ground: Any = None
        if field is not None:
            from OpenGLContext.physics.heightfield import HeightFieldColliders
            self.ground = HeightFieldColliders(self.physics, field,
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
        self.props = PropColliders(self.physics, props)
        #: The lamps in this world's bores, and which of them are worth a real
        #: light where the car is (:mod:`glisteel.lighting`).
        from glisteel.lighting import Luminaires
        self.luminaires = Luminaires(luminaires)
        #: The other cars using the road, or None for a world with no course.
        self.traffic: Any = None
        if traffic and self.course is not None:
            from glisteel.traffic import Traffic
            self.traffic = Traffic(self.course, count=int(traffic),
                                   physics=self.physics)

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
        if self.terrain is None:
            return None
        return self.terrain.update_for_camera(
            camera, viewport_height, view_projection=view_projection)

    @property
    def floor(self) -> float:
        """The height below which the world has been left behind, in metres.

        A car that has gone through the ground has nothing left to land on and
        nothing left to look at, so a game puts it back rather than let the
        player watch it fall. The datum is whatever this world stands on -- the
        tileset's own middle, the field's base, or the road itself -- and the
        floor is well under it, because a viaduct's valley is a long way down
        and a car on the deck has not fallen anywhere.
        """
        if self.terrain is not None:
            return float(self.terrain.tileset.root.bounding_volume.center[1]) \
                - LOST_BELOW
        if self.field is not None:
            return float(self.field.base) - LOST_BELOW
        lowest = min(float(road.centreline[:, 1].min()) for road in self.courses)
        return lowest - LOST_BELOW

    def view_projection(self, eye: Any, target: Any, aspect: float,
                        fov: float = FOV, near: float = 0.5,
                        far: float | None = None) -> Any:
        """The matrix the streamer culls and measures screen-space error against.

        Built from where the camera *is going to be* this frame rather than read
        back from the renderer, because the streaming runs before the frame it
        is preparing tiles for.
        """
        return frustum_matrix(tuple(float(v) for v in eye),
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
            if self.terrain is None:
                # Nothing is on its way: a world with no tiles has all of its
                # ground the moment it is built.
                return False
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
