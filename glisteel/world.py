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
from OpenGLContext.scenegraph.road import (
    CAUTION,
    advisory_speed,
    corner_speed,
    cornering_radius,
    sight_distances,
)
from OpenGLContext.scenegraph.tilesterrain import TilesTerrain

from glisteel.geometry import yaw_to_face
from glisteel.zone import LANES

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
#: How far up the road a driver is told about a bend: this much, plus this many
#: seconds of it at the speed they are doing. The same shape as the distance a
#: sign is placed at -- what a driver can still act on -- rather than a fixed
#: reach, which is either useless at speed or a warning about somewhere else at
#: a crawl.
CAUTION_METRES = 40.0
CAUTION_SECONDS = 3.5

#: The fastest anything drives here, in m/s. What it settles is which bends are
#: worth a caution: one nothing on the road could take too fast is a straight as
#: far as a sign is concerned.
TOP_SPEED = 55.0

#: Over how much road a bend's radius is measured, in metres.
#:
#: The circle through a point and its two neighbours is exact for a circle and
#: noisy for a road: an alignment written down every few metres carries its
#: arcs as chords, and a point a hand's breadth off its arc reads as a corner
#: half the radius of the one it is on. A driver reading that brakes for a
#: corner nobody built. Long enough that the sampling washes out; short enough
#: to resolve the corner it is about.
CURVE_BASELINE = 20.0

#: How far to the side the view is clear where nothing stands beside the road,
#: in metres. A span has no wood beside it and nothing under the railing to see
#: past, so what limits the view along one is how far a driver is planning
#: rather than what is in the way; this is large enough to say so.
OPEN_SIGHT = 400.0

#: What stands beside the road on each sort of structure, in metres, where it
#: is not the wood the road was cut through. A bore is the tight case: the wall
#: is at the road's edge, so nothing outside the tube is seen at all.
BESIDE = {'bridge': OPEN_SIGHT, 'causeway': OPEN_SIGHT, 'tunnel': 3.6}

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
    #: What the road is posted at, in km/h; 0 for one that says nothing. What
    #: the signs beside it say, as a number rather than as furniture.
    posted: int = 0
    #: How far the road leans at each point of the centreline, as a fraction and
    #: signed the way
    #: :func:`~OpenGLContext.scenegraph.road.plan_curvature` is -- positive
    #: where the road turns right, which is where its right-hand side is the low
    #: one. Empty for a world whose corners are flat, which is what a road laid
    #: out without a design speed has.
    bank: np.ndarray = dataclasses.field(
        default_factory=lambda: np.zeros(0, dtype='d'))

    @property
    def lanes(self) -> int:
        """How many lanes are marked across the carriageway.

        Out of the section the world wrote, where it wrote one. A road that
        only said how wide it is has one lane each way, which is what a road
        with a crown and something coming the other way is
        (:data:`glisteel.zone.LANES`).
        """
        found = self.profile.get('lanes')
        return int(found) if found else LANES

    def bank_at(self, index: int) -> float:
        """How far the road leans at that point of the line, as a fraction.

        Zero for a road that does not lean, which is every road a world wrote
        no lean for: a course half described is a course driven flat, not one
        that rears up on the first corner.
        """
        if not len(self.bank):
            return 0.0
        return float(self.bank[index % len(self.bank)])

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
        return RoadProfile(lane_width=self.carriageway_width / self.lanes,
                           lanes=self.lanes,
                           shoulder_width=beside * 0.4,
                           verge_width=beside * 0.6)

    @functools.cached_property
    def _section(self) -> Any:
        """This road's cross-section, worked out once.

        A baked world's road does not change shape, and this is asked about
        every vehicle on it every frame.
        """
        return self.road_profile()

    def surface_offset(self, across: Any, bank: Any = 0.0) -> Any:
        """How far below the crown the road's surface is, that far out.

        ``across`` is one distance from the centreline or an array of them, in
        metres. What puts anything placed by how far along and how far across
        the road it is -- a traffic car, a marker -- at the height the road
        actually is there, rather than at the height of its crown.

        ``bank`` is how far the road leans there (:meth:`bank_at`). It is the
        *camber* the lean accounts for and nothing else: the tilt itself is in
        :meth:`across`, so something placed by ``lane_point`` and dropped by
        this lands on the surface once rather than twice.
        """
        return self._section.section_offset(across, bank)

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

        Measured over :data:`CURVE_BASELINE` of road rather than between
        neighbouring samples. The three-point circle is exact for a circle and
        noisy for a road: a line written down every few metres carries an arc
        as chords, and one point a hand's breadth off its arc reads as a corner
        half the radius of the one it is on -- which a driver brakes for. Over
        a real length of road the sampling washes out and the corner does not.
        """
        line = self.ground_line
        apart = max(int(round(CURVE_BASELINE / max(self._spacing, 1e-6))), 1)
        before = np.roll(line, apart, axis=0)
        after = np.roll(line, -apart, axis=0)
        if not self.closed:
            # An open road has no bend at its ends: hold the first and last to
            # their neighbours rather than wrapping onto the other end of the
            # world.
            before[:apart], after[-apart:] = line[0], line[-1]
        first = np.linalg.norm(line - before, axis=1)
        second = np.linalg.norm(after - line, axis=1)
        third = np.linalg.norm(after - before, axis=1)
        side, other = line - before, after - before
        area2 = np.abs(side[:, 0] * other[:, 1] - side[:, 1] * other[:, 0])
        return np.where(area2 < 1e-9, 1e6,
                        first * second * third / (2.0 * np.maximum(area2, 1e-30)))

    #: The last position :meth:`nearest` was asked about and what it answered.
    _last_nearest: tuple[tuple[float, float], tuple[int, float]] | None = None

    def corner_speed(self, index: int) -> float:
        """How fast the bend at that point of the road may be taken, in m/s.

        The road's own radius there and the grip a tyre has on it
        (:func:`~OpenGLContext.scenegraph.road.corner_speed`) -- the same rule
        the world was signed by, so what the game says about a corner and what
        the plate beside it says are the same number.
        """
        radii = self.radii
        return float(corner_speed(float(radii[index % len(radii)]),
                                  bank=self.bank_at(index)))

    @functools.cached_property
    def caution_speeds(self) -> np.ndarray:
        """What a sign before each point of the road would say, in km/h.

        Well inside what each bend allows
        (:func:`~OpenGLContext.scenegraph.road.advisory_speed`), because that is
        what an advisory speed is: a number a careful driver beats rather than a
        bound they must not cross. How far the bend leans counts towards what it
        allows, so the plate on a superelevated corner reads the higher number
        the road is actually holding the car to. Zero where the road is straight
        enough to want no sign at all.

        For the whole road at once and kept, like :attr:`radii` underneath it: a
        driver asks about a stretch of road every frame, and the road does not
        change shape between frames.
        """
        radii = self.radii
        found = np.zeros(len(radii), dtype=int)
        for at in np.nonzero(radii < self.straight_radius)[0]:
            found[at] = advisory_speed(float(radii[at]),
                                       bank=self.bank_at(int(at)))
        return found

    def caution_speed(self, index: int) -> int:
        """What a sign before that bend says, in km/h; 0 where it is straight."""
        found = self.caution_speeds
        return int(found[index % len(found)])

    @functools.cached_property
    def straight_radius(self) -> float:
        """How wide a bend has to be before it is a straight, in metres.

        The radius at which the caution speed reaches the fastest thing that
        drives here: past that a sign would be advising a speed nothing on the
        road can reach, which is a sign about nothing.
        """
        return float(cornering_radius(TOP_SPEED) / CAUTION / CAUTION)

    @functools.cached_property
    def _clear(self) -> np.ndarray:
        """How far to the side of each point of the road the view is clear.

        What a driver sees past on a bend, and it is not one figure for the
        whole road. Through the wood it is the road's own width and no more:
        beyond the verge stands what the road was cut through. On a span there
        is nothing to see past -- the railing is see-through and the drop
        beyond it holds nothing -- so a viaduct is looked along however it
        curves. Inside a bore it is the carriageway alone, because the wall is
        at the road's edge and what is not in the tube is not seen.
        """
        clear = np.full(len(self.centreline), self.total_width / 2.0)
        stations = self.stations
        for structure in self.structures or ():
            clear[np.asarray(structure.holds(stations), dtype=bool)] = (
                BESIDE.get(structure.kind, OPEN_SIGHT))
        return clear

    @functools.cached_property
    def _sight(self) -> np.ndarray:
        """How far down the road can be seen from each point of the line.

        The road's own geometry against what stands beside it
        (:attr:`_clear`,
        :func:`~OpenGLContext.scenegraph.road.sight_distances`).

        Worked out once, because the road does not move and a driver asks
        about it every frame.
        """
        found: np.ndarray = sight_distances(
            self.centreline, clear=self._clear, closed=self.closed)
        return found

    def sight_ahead(self, index: int) -> float:
        """How far down the road a driver at that point can see, in metres.

        The stretch in front that stays on the carriageway: a straight is seen
        along to the limit of what is worth planning for, and a bend is seen
        only as far as it holds the line the car is pointing down. What decides
        whether there is room to get past something -- an empty look-ahead on
        a bend is a road nobody has seen, not a road with nothing on it.
        """
        sight = self._sight
        return float(sight[index % len(sight)])

    def sight_over(self, index: int, metres: float) -> float:
        """The least that can be seen anywhere in the next ``metres``.

        What a driver deciding on a manoeuvre needs, rather than what they can
        see from where they are standing: the road has to stay open for as long
        as the manoeuvre takes, and a pass begun on the last of a straight is a
        pass abandoned in the bend after it. Zero or less is the road underfoot,
        which is :meth:`sight_ahead`.
        """
        return float(self._sight[self._ahead(index, metres)].min())

    @functools.cached_property
    def _spacing(self) -> float:
        """How far apart the points of the line are, in metres."""
        steps = np.linalg.norm(np.diff(self.centreline, axis=0), axis=1)
        return float(np.mean(steps)) if len(steps) else 1.0

    def _ahead(self, index: int, metres: float) -> np.ndarray:
        """The points of the line from ``index`` on, over the next ``metres``.

        Round the join for a circuit, which has no end to run out of, and no
        further than the last point of a road that has one: what is past the end
        of a stage is nothing rather than its own beginning, and a driver
        arriving at the finish is not arriving at the first corner.

        Never empty -- the point asked about is always in it -- so a caller may
        take a minimum over what comes back without a special case for the last
        metre of the road.
        """
        count = len(self.centreline)
        points = int(round(max(float(metres), 0.0) / max(self._spacing, 1e-6)))
        found = int(index) % count + np.arange(points + 1)
        return found % count if self.closed else found[found < count]

    def caution_ahead(self, index: int, speed: float) -> int:
        """The lowest caution speed within reach of that point, in km/h.

        ``speed`` is how fast the car is going, and what it decides is how far
        ahead to look: a driver at forty metres a second needs to know about a
        corner a long way before a driver at ten does. Zero for a road with
        nothing on it worth slowing for.

        The *lowest* of what is coming, because a driver braking for a corner is
        braking for the tightest part of it rather than for the gentle bit they
        meet first.
        """
        reach = CAUTION_METRES + max(float(speed), 0.0) * CAUTION_SECONDS
        found = self.caution_speeds[self._ahead(index, reach)]
        wanted = found[found > 0]
        return int(wanted.min()) if len(wanted) else 0

    def moved(self) -> None:
        """The line has been replaced: forget what was worked out from it.

        Nothing in the game does this -- a baked world's road is what it is --
        but a tool that edits a course in place has to be able to say so, and a
        cache with no way to clear it is a trap rather than a saving.
        """
        for name in ('stations', 'segments', 'ground_line', 'radii',
                     '_section', 'start_index', '_spacing', '_clear', '_sight',
                     'caution_speeds'):
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

    def station_of(self, position: Any) -> float:
        """How far along the road something is, in metres.

        Between the samples rather than at the nearest one: a course is a line
        written down every few metres, and anything watching a distance along
        it -- what the car is driving through, how far off what is in front is
        -- moves in those steps unless the answer is worked out between them.

        The point is put on the *segment* it is beside rather than on the
        sample it is nearest, which is the same distinction :meth:`nearest`
        makes when it measures how far off the line something is.
        """
        at = np.asarray(position, dtype='d').reshape(-1)[:3][[0, 2]]
        start, delta, length2 = self.segments
        along = np.clip(np.einsum('ij,ij->i', at - start, delta) / length2,
                        0.0, 1.0)
        off = np.linalg.norm(start + along[:, None] * delta - at, axis=1)
        index = int(off.argmin())
        stations = self.stations
        return float(stations[index]
                     + along[index] * math.sqrt(float(length2[index])))

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
                return self._leaning(right / length, along / max(
                    float(np.linalg.norm(along)), 1e-9), index)
        return np.array([1.0, 0.0, 0.0])         # pragma: no cover - a point

    def _leaning(self, right: np.ndarray, along: np.ndarray,
                 index: int) -> np.ndarray:
        """A level across vector rolled by however far the road leans there.

        A banked corner turns the whole road about its own centreline, so the
        way across it runs downhill on the inside. Anything that goes *out* from
        the crown -- a driving line, a grid slot, a car keeping its own side --
        follows the surface rather than the horizon, which is what this is.
        """
        lean = self.bank_at(index)
        if not lean:
            return right
        angle = math.atan(lean)
        found: np.ndarray = (math.cos(angle) * right
                             - math.sin(angle) * np.cross(right, along))
        return found

    def lane_point(self, index: int, offset: float = 0.0) -> np.ndarray:
        """A point of the road's surface, ``offset`` metres to its right.

        Out along the road as it leans (:meth:`across`) and then down by
        whatever camber the lean has left (:meth:`surface_offset`), so the point
        is on the carriageway and not above or below it.
        """
        found = self.point(index) + self.across(index) * float(offset)
        found[1] += float(self.surface_offset(abs(float(offset)),
                                              self.bank_at(index)))
        return found

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
            posted=int(road.get('posted', 0)),
            profile=dict(road.get('profile') or {}),
            bank=_bank_of(road, len(line)),
            structures=tuple(
                Structure(kind=str(one.get('kind', 'dirt')),
                          start=float(one.get('from', 0.0)),
                          end=float(one.get('to', 0.0)))
                for one in road.get('structures') or ())))
    return out


def _bank_of(road: Any, points: int) -> np.ndarray:
    """A road's lean out of a tileset, or nothing for one that wrote none.

    A lean that does not match the line it belongs to is dropped rather than
    stretched to fit: a world describing half a road is a road to drive flat,
    and guessing the rest of it puts the car on a corner nobody built.
    """
    found = np.asarray(road.get('bank') or (), dtype='d').reshape(-1)
    return found if len(found) == points else np.zeros(0, dtype='d')


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
                closed=road.closed,
                bank=road.bank if len(road.bank) else None))
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
