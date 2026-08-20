"""What decides how a run is going, and what ends it.

Four rules, each fed a reading and a step and each answering once: how far round
the car is (:class:`RaceTiming`), whether it is on the road and what it is
driving on (:class:`OffRoad`), whether it hit something hard enough to matter
(:class:`Collisions`), and how fast two things are coming together
(:func:`closing_speed`). They share a shape -- fed, then asked, with a
``restart`` -- so a session composes them without knowing what each is about.


A lap is not "crossed the line": a car that reverses over the start line has
not done a lap, and one that drives across the infield has not either. So the
circuit is divided into *sectors* and a lap counts only when the car has passed
through all of them in order and come back to the first. That is the same rule
a real timing loop uses, and it costs one integer of state.

The circuit comes from the world (:class:`~glisteel.world.Course`), so nothing
here knows or cares how the track was made.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from omi_physics.vehicle import Surface

__all__ = ['Collisions', 'Lap', 'OffRoad', 'RaceTiming',
           'LOST', 'PATIENCE', 'ROUGH', 'SECTORS', 'SURVIVABLE',
           'TARMAC', 'VERGE', 'closing_speed', 'off_course']

#: How many sectors a circuit is divided into for the purpose of saying a lap
#: was completed rather than cut. Enough that a shortcut across the middle
#: misses one; few enough that a car briefly off the road does not.
SECTORS = 8


@dataclass
class Lap:
    """One completed lap: how long it took, and when."""

    number: int
    seconds: float

    def clock(self) -> str:
        """The time as a driver reads it: ``m:ss.mmm``."""
        minutes, seconds = divmod(self.seconds, 60.0)
        return "%d:%06.3f" % (int(minutes), seconds)


@dataclass
class RaceTiming:
    """Laps, sectors and the clock, driven by where the car is.

    Feed it :meth:`update` once a frame. It answers :attr:`current`, the lap in
    progress, :attr:`laps`, the ones completed, and :attr:`best`, the quickest.
    A car that has not yet reached the far side of the circuit cannot complete a
    lap by turning round at the line and coming back.
    """

    course: Any
    sectors: int = SECTORS
    laps: list[Lap] = field(default_factory=list)
    #: Seconds since the current lap began.
    current: float = 0.0
    #: Which sectors have been visited this lap.
    visited: set[int] = field(default_factory=set)
    #: How far round the car is, 0 at the line and 1 back at it.
    progress: float = 0.0
    started: bool = False

    def __post_init__(self) -> None:
        self._last_sector: int | None = None

    @property
    def best(self) -> Lap | None:
        """The quickest lap so far."""
        return min(self.laps, default=None, key=lambda lap: lap.seconds)

    @property
    def last(self) -> Lap | None:
        return self.laps[-1] if self.laps else None

    def sector_of(self, position: Any) -> int:
        """Which sector of the circuit a point is nearest."""
        return int(self.round_from_the_line(position) * self.sectors)

    def round_from_the_line(self, position: Any) -> float:
        """How far round the circuit a point is, 0 at the line and 1 back at it.

        Measured from where the world drew its start line
        (:attr:`~glisteel.world.Course.start_index`) rather than from wherever
        the centreline's array happens to begin: those are the same place only
        by accident, and timed from the second the clock turns over somewhere
        down the back of the circuit.
        """
        index, _ = self.course.nearest(position)
        total = len(self.course.centreline)
        return float((index - self.course.start_index) % total) / total

    def update(self, position: Any, dt: float) -> Lap | None:
        """Advance the clock; return a lap if one has just been completed."""
        self.progress = self.round_from_the_line(position)
        sector = int(self.progress * self.sectors)

        if not self.started or self._last_sector is None:
            # The clock starts when the car first moves off the line, not when
            # the world finishes loading.
            self.started = True
            self._last_sector = sector
            self.visited = {sector}
            return None

        self.current += max(0.0, dt)
        finished = None
        if sector != self._last_sector:
            forward = (sector - self._last_sector) % self.sectors == 1
            if forward and sector == 0 and self._complete():
                finished = Lap(number=len(self.laps) + 1, seconds=self.current)
                self.laps.append(finished)
                self.current = 0.0
                self.visited = set()
            self._last_sector = sector
        self.visited.add(sector)
        return finished

    def _complete(self) -> bool:
        """Whether every sector has been visited since the last line crossing."""
        return len(self.visited) >= self.sectors

    def restart(self) -> None:
        """Abandon the lap in progress -- the car has been put back on the grid."""
        self.current = 0.0
        self.visited = set()
        self.started = False
        self._last_sector = None


def off_course(course: Any, position: Any, tolerance: float = 12.0) -> bool:
    """Whether a car has left the road by more than a car's width or two.

    Not a penalty -- a car that has slid onto the verge is still racing. This is
    what a "return to track" key asks before moving anything.
    """
    _, distance = course.nearest(np.asarray(position, dtype='d'))
    return bool(distance > course.total_width / 2.0 + tolerance)


#: What a car is on, on the road and off it. The verge is the strip either side
#: of the carriageway -- gravel, then grass -- where a wheel loses most of its
#: grip and picks up a great deal of drag. Past that is rough ground, and a car
#: in it is not coming back out at speed.
#: One of each is handed to every car that is on it. That is safe because
#: ``Surface`` is frozen: nothing can change what every car in the process is
#: driving on by changing what it was given.
TARMAC = Surface()
VERGE = Surface(grip=0.45, rolling=0.25)
ROUGH = Surface(grip=0.30, rolling=0.55)

#: How long a car may be off the carriageway before the run is over, in
#: seconds. Long enough to slide a wheel wide and gather it up; short enough
#: that driving across the infield is not a strategy.
PATIENCE = 2.5

#: How far off the carriageway is far enough that the run is over the moment it
#: happens, as a multiple of the road's total width from the centreline. Down a
#: bank and into the trees: there is no gathering that up.
LOST = 2.0


@dataclass
class OffRoad:
    """Whether the car is on the road, what it is driving on, and when to stop.

    A forest road is as wide as it is and the forest starts at the verge, so
    leaving it matters: a wheel on the grass loses most of its grip and picks up
    drag, and a car that stays there is mired and the run is over. Feed it
    :meth:`update` once a frame with where the car is; it answers the surface to
    put under the wheels and, once, the reason the run ended.

    It is deliberately about *where the car is* rather than about what it hit:
    what stops a car leaving a forest road is the trees, and modelling every
    trunk as a collider costs more than the answer is worth.
    """

    course: Any
    patience: float = PATIENCE
    lost: float = LOST
    #: Whether the car is off the carriageway right now.
    off: bool = False
    #: How far off the centreline it is, in metres.
    distance: float = 0.0
    #: How long it has been off, in seconds; zero the moment it is back on.
    time_off: float = 0.0
    #: Set once the run is over, and the reason why.
    ended: str | None = None

    def update(self, position: Any, dt: float) -> str | None:
        """Read where the car is; return the reason the run ended, once.

        Returns the reason on the frame it ends and None on every other frame,
        so a caller can act on it without keeping a flag of its own.
        """
        if self.ended is not None:
            return None
        _index, self.distance = self.course.nearest(
            np.asarray(position, dtype='d'))
        self.off = self.distance > self.course.carriageway_width / 2.0
        if not self.off:
            self.time_off = 0.0
            return None
        if self.distance > self.course.total_width * self.lost:
            return self._over("off the road")
        self.time_off += float(dt)
        if self.time_off >= self.patience:
            return self._over("mired off the road")
        return None

    def surface(self) -> Surface:
        """What the wheels are on, from how far off the road the car is."""
        if not self.off:
            return TARMAC
        beside = max(self.course.total_width - self.course.carriageway_width,
                     1e-6) / 2.0
        edge = self.course.carriageway_width / 2.0
        return VERGE if self.distance <= edge + beside else ROUGH

    def restart(self) -> None:
        """The car has been put back on the grid: the run is on again."""
        self.off = False
        self.time_off = 0.0
        self.distance = 0.0
        self.ended = None

    def _over(self, why: str) -> str:
        self.ended = why
        return why


#: How fast a car may meet something solid and drive on, in metres per second.
#: Brushing a wing at walking pace is a scrape; meeting the back of a lorry at
#: forty metres a second is not.
SURVIVABLE = 9.0


@dataclass
class Collisions:
    """Whether the car hit something hard enough to end the run.

    Fed the *closing speed* rather than a contact: a car is always touching the
    road, and what decides a crash is how fast it arrived at whatever else it
    found. Which cars and boulders are near enough to matter is the physics
    world's business; this is only the rule about what counts.
    """

    survivable: float = SURVIVABLE
    #: Set once the run is over, and the reason why.
    ended: str | None = None

    def update(self, closing: float) -> str | None:
        """Read a closing speed; return the reason the run ended, once.

        No time step: what decides a crash is how fast the car arrived at
        whatever it found, and how long it spent arriving changes nothing about
        that. The sibling watchers take one because what they measure -- how
        long a car has been off the road -- accumulates.
        """
        if self.ended is not None:
            return None
        if float(closing) <= self.survivable:
            return None
        self.ended = 'HIT A CAR'
        return self.ended

    def restart(self) -> None:
        """Back on the grid: nothing has happened yet."""
        self.ended = None


def closing_speed(mine: Any, theirs: Any, offset: Any) -> float:
    """How fast two things are coming together, in metres per second.

    The relative velocity along the line between them, which is the number a
    crash's severity is about. Taken as a difference of speeds instead, two cars
    meeting head-on at thirty read as closing at nothing, and one being overtaken
    reads as a crash.
    """
    between = np.asarray(offset, dtype='d').reshape(-1)[:3]
    length = float(np.linalg.norm(between))
    if length < 1e-9:
        return 0.0
    return float(np.dot(np.asarray(mine, dtype='d').reshape(-1)[:3]
                        - np.asarray(theirs, dtype='d').reshape(-1)[:3],
                        between / length))
