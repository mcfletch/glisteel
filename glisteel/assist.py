"""What a driver's hands do that a keyboard cannot say.

A real driver never stops steering. Between the deliberate inputs there is a
continuous small correction holding the car on the line they picked -- a few
degrees of wheel, put in and taken out without thinking about it -- and a
keyboard has no way to express any of it, because a key is down or it is not.

Left out, every tap is a **permanent change of direction**: the wheel centres,
the car keeps the heading the tap gave it, and it crosses the road at a steady
rate until it runs out of road. On a seven-metre carriageway three tenths of a
second on a key is eventually a car in the trees, whatever the tap itself was
worth. That is not what the car does wrong; it is what the *driver* is not
there to do. A crowned road does the same thing more slowly and in one
direction: the surface falls away to each side so that it drains, and a car
standing on that fall slides down it unless somebody trims the wheel.

So when nothing is held, the wheel is not merely centred: it is put where it
needs to be to hold the car on the line it is on.

    >>> from glisteel.assist import Straighten
    >>> assist = Straighten(course, strength=0.0)     # doctest: +SKIP
    >>> assist.steer(session, wanted=0.4)             # doctest: +SKIP
    0.4

**The line is the player's, not the aid's.** Whatever the car is on when the
player lets go of the wheel is what gets held (:attr:`Straighten.line`), out to
:data:`MARGIN` inside the carriageway's own edge. An aid that held a line of its
own -- the middle of the road, or the middle of a lane -- would pull the car
across the road under a player who put it somewhere else on purpose, and would
have to be fought the whole way past anything being overtaken. Steering out and
letting go is how a lane is changed; the aid then holds the new one.

:attr:`Straighten.strength` is how much of that correction is used, and it is
the game's difficulty dial for steering: **0 hands the car back entirely** and
is the car as the physics has it, 1 holds the line for the player. Nothing is
applied while a steering key is down, so a deliberate input is always the
player's own.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from glisteel.driver import Autopilot, DriverStyle
from glisteel.interfaces import CourseLike, SessionLike

__all__ = ['DEADZONE', 'MARGIN', 'STRENGTH', 'Straighten']

#: How much of the correction is put in when nothing says otherwise. Enough
#: that a tap is a nudge the car settles out of, little enough that the player
#: is still the one placing it on the road.
STRENGTH = 0.55

#: Steering input below this counts as hands off. Not zero: a wheel on its way
#: back to centre passes through very small values, and waiting for exactly
#: nothing would leave the car un-helped for the moment it most needs it.
DEADZONE = 0.05

#: How far inside the carriageway's own edge a held line may sit, in metres.
#: About half a car: a player who lets go with two wheels on the grass is not
#: asking to be held there, so the line the aid takes up is drawn back onto the
#: road -- and no further, because the rest of the road is theirs to use.
MARGIN = 1.0


class Straighten:
    """The steering the game puts in while the player is not steering.

    ``course`` is the road, and the line held on it is taken from wherever the
    car is each time the player lets go of the wheel. ``margin`` is how far
    inside the carriageway's edge that line may sit.

    Its only state is the line it is holding, so the same one serves a whole
    race and changing :attr:`strength` mid-race takes effect on the next step.
    """

    def __init__(self, course: CourseLike, strength: float = STRENGTH,
                 deadzone: float = DEADZONE, margin: float = MARGIN) -> None:
        self.strength = float(strength)
        self.deadzone = float(deadzone)
        self.margin = float(margin)
        #: What works out where the road wants the car; the same geometry the
        #: autopilot drives by, at a gentler gain.
        self.driver = Autopilot(course, style=DriverStyle(tracking=2.5))
        #: Whether the wheel is the player's right now. Starts true, so the
        #: first step with nobody steering takes the line the car was stood on.
        self._hands_on = True

    def __repr__(self) -> str:
        return 'Straighten(%.0f%%)' % (self.strength * 100.0)

    @property
    def helping(self) -> bool:
        """Whether this is doing anything at all."""
        return self.strength > 0.0

    @property
    def line(self) -> float:
        """The line being held: how far to the road's own right, in metres."""
        return float(self.driver.lane)

    def hold(self, line: float) -> None:
        """Hold this line from now on, in metres right of the centreline."""
        self.driver.lane = float(line)

    def release(self) -> None:
        """Let go of the line, so the next hands-off step takes a fresh one.

        For a car that has been picked up and set down somewhere else: the line
        it was on is not a line on the road it is on now.
        """
        self._hands_on = True

    def holding(self, wanted: float) -> bool:
        """Whether the player is steering, and so is to be left alone."""
        return abs(float(wanted)) > self.deadzone

    def line_under(self, car: Any) -> float:
        """The line a car is on: how far to the road's own right it is.

        Drawn back inside the carriageway by :attr:`margin`, so the line taken
        up from a car with a wheel on the grass is one on the road.
        """
        course = self.driver.course
        at = np.asarray(car.position, dtype='d').reshape(-1)[:3]
        index, _distance = course.nearest(at)
        across = float(np.dot(at - course.point(index), course.across(index)))
        edge = max(float(course.carriageway_width) / 2.0 - self.margin, 0.0)
        return max(-edge, min(edge, across))

    def steer(self, session: SessionLike, wanted: float) -> float:
        """What reaches the wheel, given what the player asked for."""
        if not self.helping:
            return float(wanted)
        if self.holding(wanted):
            # The player has the wheel: their input is their own, and where
            # they leave the car is the line to hold afterwards.
            self._hands_on = True
            return float(wanted)
        if self._hands_on:
            self._hands_on = False
            self.hold(self.line_under(session.car))
        correction = self.driver.steering(session.car) * self.strength
        return max(-1.0, min(1.0, float(wanted) + correction))
