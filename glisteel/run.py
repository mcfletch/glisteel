"""Where a run is: waiting on the lights, racing, home, or over.

A race is not one long moment of driving. There is a car standing on the grid
that the player does not yet have; there is the race itself; and there is the
moment after it, which is either a time to keep or a reason it did not happen.
Each of those decides two things -- **what reaches the car** and **whether the
clock runs** -- and both of them were previously nobody's job, so a mired car
kept being driven and a lap clock kept counting while the run was over.

    >>> run = Run(lights=3, interval=1.0, hold=1.0)
    >>> run.update(3.0), run.lit
    (None, 3)
    >>> run.update(1.0)
    'racing'
    >>> run.allow(1.0, 0.0, 0.3)
    (1.0, 0.0, 0.3)

Nothing here knows about a car, a course or a window: it is handed the length
of the step and what the world has done since the last one -- how many laps are
in, whether anything has ended the run -- and answers with a phase. What acts on
that is :class:`~glisteel.session.Session`.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ['Run', 'COUNTDOWN', 'RACING', 'FINISHED', 'ENDED', 'PHASES',
           'LIGHTS', 'LIGHT_INTERVAL', 'LIGHTS_OUT']

#: Standing on the grid with the lamps running. The car is held.
COUNTDOWN = 'countdown'
#: Driving, and being timed.
RACING = 'racing'
#: The laps asked for are done.
FINISHED = 'finished'
#: Over for a reason that is not finishing: mired, or wrecked.
ENDED = 'ended'

PHASES = (COUNTDOWN, RACING, FINISHED, ENDED)

#: Lamps in the start rig, and how long apart they light. Five at a second
#: apart is the start a driver already knows how to read: the count is *seen*
#: rather than read, which a number on the screen never manages.
LIGHTS = 5
LIGHT_INTERVAL = 1.0

#: How long the full rig holds before it goes out, in seconds. The wait is what
#: makes a start a start -- a rig that goes out the instant it fills is a
#: metronome, and everyone leaves on the beat.
LIGHTS_OUT = 1.4


@dataclass
class Run:
    """One race, and the rules that come with the part of it now happening.

    ``laps`` is how many are being raced; **0 races none**, which is free
    driving on a circuit with no line to come home to. ``lights``, ``interval``
    and ``hold`` are the start rig: how many lamps, how far apart they come on,
    and how long the full rig holds before it goes out.

    Feed it :meth:`update` once a physics step with what the world has done,
    and ask :meth:`allow` what may reach the car.
    """

    laps: int = 1
    lights: int = LIGHTS
    interval: float = LIGHT_INTERVAL
    hold: float = LIGHTS_OUT

    #: One of :data:`PHASES`.
    phase: str = COUNTDOWN
    #: Seconds spent in the current phase.
    elapsed: float = 0.0
    #: Why the run is over, or None -- including when it is over by finishing,
    #: which is not something that went wrong.
    outcome: str | None = None

    def __repr__(self) -> str:
        return 'Run(%s, %d lap%s)' % (self.phase, self.laps,
                                      '' if self.laps == 1 else 's')

    # -- what the phase means --------------------------------------------------

    @property
    def lit(self) -> int:
        """How many lamps are burning: 0 at every moment but the countdown."""
        if self.phase != COUNTDOWN or self.interval <= 0:
            return 0
        return min(self.lights, int(self.elapsed / self.interval))

    @property
    def timed(self) -> bool:
        """Whether the lap clock runs. Only while racing."""
        return self.phase == RACING

    @property
    def over(self) -> bool:
        """Whether the race has stopped happening, however it stopped."""
        return self.phase in (FINISHED, ENDED)

    def allow(self, throttle: float, brake: float, steer: float
              ) -> tuple[float, float, float]:
        """What of the driver's controls reaches the car.

        Racing, all of it. Every other phase is a car the player does not have:
        on the lights it is held on the grid, and once the run is over it is
        brought to a stop, because a race that is over and a car still being
        driven round the circuit are not both true.
        """
        if self.phase == RACING:
            return float(throttle), float(brake), float(steer)
        return 0.0, 1.0, 0.0

    # -- the step --------------------------------------------------------------

    def update(self, dt: float, laps: int = 0, ended: str | None = None
               ) -> str | None:
        """Advance by one step; answer the phase moved to, or None for no move.

        ``laps`` is how many are complete and ``ended`` why the run is over, if
        anything has decided that. Both are what the world knows and this does
        not.
        """
        self.elapsed += max(0.0, float(dt))
        was = self.phase
        if self.phase == COUNTDOWN:
            if self.elapsed >= self.lights * self.interval + self.hold:
                self._enter(RACING)
        elif self.phase == RACING:
            if ended:
                self.outcome = str(ended)
                self._enter(ENDED)
            elif self.laps and laps >= self.laps:
                self._enter(FINISHED)
        return None if self.phase == was else self.phase

    # -- picking it up again ---------------------------------------------------

    def resume(self) -> None:
        """Back into the race the car was put out of.

        A car that has been recovered onto the road carries on; a race that has
        been *won* does not reopen, because there is nothing left to drive.
        """
        if self.phase == ENDED:
            self.outcome = None
            self._enter(RACING)

    def go(self) -> None:
        """Drop the lights now.

        The start sequence is part of the race and not part of the driving, so
        anything measuring how a car behaves -- the scripted drives in
        :mod:`glisteel.trace` -- begins here rather than spending six seconds
        watching lamps.
        """
        if self.phase == COUNTDOWN:
            self._enter(RACING)

    def restart(self) -> None:
        """A fresh race: back onto the grid with the lamps out."""
        self.outcome = None
        self._enter(COUNTDOWN)

    def _enter(self, phase: str) -> None:
        self.phase = phase
        self.elapsed = 0.0
