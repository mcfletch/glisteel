"""What a driver's hands do that a keyboard cannot say.

A real driver never stops steering. Between the deliberate inputs there is a
continuous small correction holding the car where they want it -- a few degrees
of wheel, put in and taken out without thinking about it -- and a keyboard has
no way to express any of it, because a key is down or it is not.

Left out, every tap is a **permanent** change of direction: the wheel centres,
the car keeps the heading the tap gave it, and it crosses the road at a steady
rate until it runs out of road. On a seven-metre carriageway three tenths of a
second on a key is eventually a car in the trees, whatever the tap itself was
worth. That is not what the car does wrong; it is what the *driver* is not
there to do.

So when nothing is held, the wheel is not merely centred: it is put where it
needs to be to bring the car back to the way the road goes.

    >>> from glisteel.assist import Straighten
    >>> assist = Straighten(course, strength=0.0)     # doctest: +SKIP
    >>> assist.steer(session, wanted=0.4)             # doctest: +SKIP
    0.4

:attr:`Straighten.strength` is how much of that correction is used, and it is
the game's difficulty dial for steering: **0 hands the car back entirely** and
is the car as the physics has it, 1 holds the line for the player. Nothing is
applied while a steering key is down, so a deliberate input is always the
player's own.
"""
from __future__ import annotations

from typing import Any

from glisteel.driver import Autopilot, DriverStyle

__all__ = ['DEADZONE', 'STRENGTH', 'Straighten']

#: How much of the correction is put in when nothing says otherwise. Enough
#: that a tap is a nudge the car comes back from, little enough that the player
#: is still the one placing it on the road.
STRENGTH = 0.55

#: Steering input below this counts as hands off. Not zero: a wheel on its way
#: back to centre passes through very small values, and waiting for exactly
#: nothing would leave the car un-helped for the moment it most needs it.
DEADZONE = 0.05


class Straighten:
    """The steering the game puts in while the player is not steering.

    ``course`` is the road to hold to and ``lane`` how far to its own right the
    car is held -- zero on an empty circuit, its own side of the road where
    something is coming the other way.

    It holds no state, so the same one serves a whole race and changing
    :attr:`strength` mid-race takes effect on the next step.
    """

    def __init__(self, course: Any, strength: float = STRENGTH,
                 lane: float = 0.0, deadzone: float = DEADZONE) -> None:
        self.strength = float(strength)
        self.deadzone = float(deadzone)
        #: What works out where the road wants the car; the same geometry the
        #: autopilot drives by, at a gentler gain.
        self.driver = Autopilot(course, style=DriverStyle(tracking=2.5),
                                lane=lane)

    def __repr__(self) -> str:
        return 'Straighten(%.0f%%)' % (self.strength * 100.0)

    @property
    def helping(self) -> bool:
        """Whether this is doing anything at all."""
        return self.strength > 0.0

    def holding(self, wanted: float) -> bool:
        """Whether the player is steering, and so is to be left alone."""
        return abs(float(wanted)) > self.deadzone

    def steer(self, session: Any, wanted: float) -> float:
        """What reaches the wheel, given what the player asked for."""
        if not self.helping or self.holding(wanted):
            return float(wanted)
        correction = self.driver.steering(session.car) * self.strength
        return max(-1.0, min(1.0, float(wanted) + correction))
