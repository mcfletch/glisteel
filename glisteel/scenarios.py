"""Small pieces of road to drive, each with one question in it.

A world is eight kilometres of circuit through half a million trees, and
answering "does the wheel come back to centre" in one means baking it, streaming
it, and driving to the part that matters. A **scenario** is the part that
matters and nothing else: a few hundred metres of road, the ground under it, and
whatever stands beside it.

Everything in one is the real thing. The course is the same
:class:`~glisteel.world.Course` a baked world hands over; the carriageway is
swept by the engine's own :class:`~OpenGLContext.physics.road.RoadColliders`;
the ground is a
:class:`~OpenGLContext.scenegraph.terrain.heightfield.HeightField` cut into
chunks by :class:`~OpenGLContext.physics.heightfield.HeightFieldColliders`, the
way a field world's is. What is left out is the drawing: there are no tiles, no
textures and no trees, which is what makes one cost milliseconds instead of
seconds.

    >>> from glisteel import scenarios
    >>> world = scenarios.chicane().world()
    >>> world.course.length                                    # doctest: +SKIP
    340.0

Drive one with :class:`~glisteel.session.Session`. The catalogue is
:data:`CATALOGUE`, and :func:`named` looks a piece up by name.

**The ground sits at the road's own outer edge.** A road is built up from the
land it crosses, and its cross-section already falls from the crown to the far
side of the verge; the field is put at that depth, so the two surfaces meet
where the road ends rather than fighting over the same triangles.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from glisteel.world import Course, RaceWorld

__all__ = ['CATALOGUE', 'Scenario', 'chicane', 'circuit', 'crest', 'dip',
           'hairpin', 'named', 'straight', 'sweeper', 'verge']

#: How far the ground reaches past the road, in metres. Wide enough that a car
#: that has left the road has somewhere to land and somewhere to be recovered
#: from, and no wider: every metre of it is triangles a chunk has to hold.
MARGIN = 120.0

#: How many metres one cell of the ground's grid covers. The shipped world's
#: field is sampled at about this, and a surface a car drives at fifty metres a
#: second wants to be no coarser.
CELL = 2.0

#: How far apart the centreline is written down, in metres. The baker's own
#: spacing: a course sampled more finely than this says nothing more about
#: where the road goes, and everything that reads it walks its points.
SPACING = 5.0

#: The road's cross-section, the same one the shipped world is built to: two
#: lanes, a shoulder and a verge that falls to meet the ground. Written down
#: rather than inferred, because what a road is like at its edge is most of what
#: running off one feels like.
PROFILE = {'laneWidth': 3.6, 'lanes': 2, 'shoulderWidth': 0.7,
           'shoulderDrop': 0.05, 'vergeWidth': 1.0, 'vergeDrop': 0.35,
           'crossfall': 0.02, 'textureLength': 22.0}

def level(x: Any, z: Any) -> Any:
    """Land with nothing to say: the height of it is zero everywhere."""
    return np.zeros_like(np.asarray(x, 'd'))


#: A road that crosses level ground.
FLAT: Callable[[Any, Any], Any] = level


@dataclass(frozen=True)
class Scenario:
    """A piece of road, the ground under it, and what stands beside it.

    ``plan`` is the road's line as an (N,2) array of XZ, centred on the origin
    because the ground is a square field centred there. ``relief`` gives the
    height of the land at any point, and the road is laid on it, so the two
    agree wherever the road goes.

    Build the world to drive with :meth:`world`; everything else here is what
    that is made of, exposed because a test that wants only the course should
    not have to stand up a physics world to get one.
    """

    name: str
    plan: np.ndarray
    closed: bool = False
    relief: Callable[[Any, Any], Any] = FLAT
    carriageway_width: float = 7.2
    total_width: float = 10.6
    #: Boulders on the verges, as (station along the road, which side).
    boulders: tuple[tuple[float, float], ...] = ()
    _cache: dict = field(default_factory=dict, compare=False, repr=False)

    # -- the road --------------------------------------------------------------

    def centreline(self) -> np.ndarray:
        """The road's line in three dimensions, laid on the land."""
        plan = np.asarray(self.plan, dtype='d').reshape(-1, 2)
        height = np.asarray(self.relief(plan[:, 0], plan[:, 1]), dtype='d')
        return np.stack([plan[:, 0], height, plan[:, 1]], axis=-1)

    def course(self) -> Course:
        """This piece of road as the game reads one."""
        line = self.centreline()
        ends = np.vstack([line, line[:1]]) if self.closed else line
        return Course(
            name=self.name, centreline=line,
            carriageway_width=self.carriageway_width,
            total_width=self.total_width, closed=self.closed,
            length=float(np.linalg.norm(np.diff(ends, axis=0), axis=1).sum()),
            profile=dict(PROFILE))

    # -- the land --------------------------------------------------------------

    @property
    def extent(self) -> float:
        """How far across the ground reaches, in metres, centred on the origin."""
        plan = np.asarray(self.plan, dtype='d')
        return float(2.0 * np.abs(plan).max() + 2.0 * MARGIN)

    def ground(self) -> Any:
        """The land, as the height field a world carries.

        Sunk to the depth the road's own cross-section reaches, so the field
        meets the outer edge of the verge instead of cutting through it.
        """
        from OpenGLContext.scenegraph.terrain.heightfield import HeightField
        drop = float(self.course().road_profile().section()[:, 1].min())

        def under(x: Any, z: Any) -> Any:
            return np.asarray(self.relief(x, z), dtype='d') + drop
        return HeightField.from_function(
            under, res=int(self.extent / CELL) | 1, extent=self.extent)

    def props(self) -> list:
        """The boulders standing beside this road."""
        from OpenGLContext.scenegraph.props import Prop
        course = self.course()
        beside = self.total_width / 2.0 + 1.6
        found = []
        for station, side in self.boulders:
            index = int(round(station / SPACING)) % len(course.centreline)
            at = course.lane_point(index, beside * side)
            found.append(Prop(kind='rock', position=tuple(float(v) for v in at),
                              radius=1.1, height=1.8))
        return found

    # -- the whole thing -------------------------------------------------------

    def world(self, traffic: int = 0) -> RaceWorld:
        """A world to drive this piece of road in, with nothing drawn."""
        return RaceWorld.from_course(self.course(), field=self.ground(),
                                     props=self.props(), traffic=traffic)


# -- the catalogue -------------------------------------------------------------

def straight(length: float = 400.0) -> Scenario:
    """Level road in a straight line: what the controls do, undisturbed."""
    return Scenario(name='straight', plan=_along(length))


def verge(length: float = 400.0) -> Scenario:
    """A straight with boulders either side of it: surfaces, and hitting things."""
    return Scenario(name='verge', plan=_along(length),
                    boulders=tuple((station, side)
                                   for station in (60.0, 140.0, 220.0, 300.0)
                                   for side in (-1.0, 1.0)))


def sweeper(radius: float = 120.0, sweep: float = math.pi / 2.0) -> Scenario:
    """One long constant bend: what the car does held at a steady angle."""
    angle = np.linspace(0.0, float(sweep), max(int(radius * sweep / SPACING), 3))
    plan = np.stack([radius * (1.0 - np.cos(angle)), -radius * np.sin(angle)],
                    axis=-1)
    return Scenario(name='sweeper', plan=_centred(plan))


def chicane(length: float = 360.0, offset: float = 9.0) -> Scenario:
    """A straight with a left and a right in it: what a change of direction costs.

    The shifts are raised cosines rather than corners, so the road has a
    curvature everywhere and the car is answering a road rather than a kink.
    """
    plan = _along(length)
    z = plan[:, 1]
    plan[:, 0] = (offset * _shift(z, -length * 0.10, 60.0)
                  - offset * _shift(z, -length * 0.45, 60.0))
    return Scenario(name='chicane', plan=plan)


def hairpin(approach: float = 240.0, radius: float = 28.0) -> Scenario:
    """A straight into a tight bend: braking, and what the car does at the apex."""
    run = _along(approach)
    angle = np.linspace(0.0, math.pi, max(int(math.pi * radius / SPACING), 8))
    bend = np.stack([radius * (1.0 - np.cos(angle)),
                     run[-1, 1] - radius * np.sin(angle)], axis=-1)
    return Scenario(name='hairpin', plan=_centred(np.vstack([run, bend[1:]])))


def crest(length: float = 400.0, height: float = 4.0,
          wavelength: float = 220.0) -> Scenario:
    """A rise the road goes over: whether the wheels stay down at the top."""
    return Scenario(name='crest', plan=_along(length),
                    relief=_wave(height, wavelength, phase=0.0))


def dip(length: float = 400.0, height: float = 4.0,
        wavelength: float = 220.0) -> Scenario:
    """A hollow the road runs through: the compression at the bottom of it."""
    return Scenario(name='dip', plan=_along(length),
                    relief=_wave(height, wavelength, phase=math.pi))


def circuit(radius_x: float = 150.0, radius_z: float = 95.0) -> Scenario:
    """A small closed circuit: laps, sectors, the map, and traffic on a road."""
    count = max(int(2.0 * math.pi * max(radius_x, radius_z) / SPACING), 16)
    angle = np.linspace(0.0, 2.0 * math.pi, count, endpoint=False)
    plan = np.stack([radius_x * np.cos(angle), radius_z * np.sin(angle)],
                    axis=-1)
    return Scenario(name='circuit', plan=plan, closed=True)


#: Every piece by name, for a test or a command line that takes one.
CATALOGUE: dict[str, Callable[[], Scenario]] = {
    'straight': straight,
    'verge': verge,
    'sweeper': sweeper,
    'chicane': chicane,
    'hairpin': hairpin,
    'crest': crest,
    'dip': dip,
    'circuit': circuit,
}


def named(name: str) -> Scenario:
    """The piece of road called ``name``."""
    try:
        return CATALOGUE[name]()
    except KeyError:
        raise KeyError("no scenario called %r; there is %s"
                       % (name, ', '.join(sorted(CATALOGUE)))) from None


# -- building the plans --------------------------------------------------------

def _along(length: float) -> np.ndarray:
    """A straight line down -Z, centred on the origin."""
    count = max(int(length / SPACING) + 1, 2)
    z = np.linspace(length / 2.0, -length / 2.0, count)
    return np.stack([np.zeros(count), z], axis=-1)


def _centred(plan: np.ndarray) -> np.ndarray:
    """A plan moved so its middle is the origin, which is where the ground is."""
    found = np.asarray(plan, dtype='d').reshape(-1, 2)
    middle: np.ndarray = found - (found.min(axis=0) + found.max(axis=0)) / 2.0
    return middle


def _shift(z: Any, at: float, over: float) -> Any:
    """A raised cosine from 0 to 1, centred at ``at`` and taking ``over`` metres.

    A step would be a corner, and a corner has no radius for a driver or an
    autopilot to read; this has a curvature everywhere along it.
    """
    fraction = np.clip((np.asarray(z, 'd') - at) / over + 0.5, 0.0, 1.0)
    return 0.5 - 0.5 * np.cos(math.pi * fraction)


def _wave(height: float, wavelength: float, phase: float) -> Callable:
    """Land that rises and falls along Z and is level across it.

    Level across, so the road's own surface and the ground agree all the way
    over the top: a crest that also tilted the road sideways would be asking
    two questions at once.
    """
    def relief(x: Any, z: Any) -> Any:
        return height / 2.0 * np.cos(
            2.0 * math.pi * np.asarray(z, 'd') / wavelength + phase)
    return relief
