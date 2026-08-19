"""Steering with a pointer, until there is a wheel or a pad to steer with.

A keyboard gives three states -- full left, straight, full right -- and no
amount of tuning in the vehicle makes that feel like a car. A pointer gives a
*position*, and turning sideways movement into lock is what mouse-look already
does for a head.

The wheel is **centred on the window** rather than accumulated from the
movements. An accumulated angle drifts, and a pointer that has to be walked back
to the middle before the car will go straight is a pointer nobody can drive
with: where the pointer is across the window *is* where the wheel is, and
letting go of it in the middle is straight ahead.
"""
from __future__ import annotations

__all__ = ['KeyboardWheel', 'MouseWheel', 'TRAVEL', 'CURVE', 'WIND_ON', 'CENTRE']

#: How much of the window's half-width is full lock. Under 1 so a driver does
#: not have to reach the very edge of the screen to get all of it.
TRAVEL = 0.8

#: How the lock is shaped across that travel. 1 is proportional; above it the
#: middle is gentler and the ends are as far as ever, which is what keeps a
#: twitch at speed a twitch rather than a spin.
CURVE = 1.8


class MouseWheel:
    """Where the steering is, from where the pointer is across the window.

    ``width`` is the window's width in pixels, ``travel`` how much of its half
    is full lock, and ``curve`` how the lock is shaped across that. Positive is
    left, which is the direction a positive steering input turns towards.
    """

    def __init__(self, width: int = 1280, travel: float = TRAVEL,
                 curve: float = CURVE) -> None:
        self.width = max(int(width), 1)
        self.travel = max(float(travel), 1e-3)
        self.curve = max(float(curve), 1e-3)
        #: Where the wheel was last put, so a physics step reads the same
        #: answer however often it asks between one frame and the next.
        self.position = 0.0

    def resize(self, width: int) -> None:
        """The window changed size; the middle of it moved with it."""
        self.width = max(int(width), 1)

    def moved(self, x: int) -> float:
        """The pointer is here: turn the wheel to match, and say where it is."""
        self.position = self.steer(x)
        return self.position

    def steer(self, x: int) -> float:
        """What the wheel reads with the pointer at ``x`` pixels across."""
        half = self.width / 2.0
        offset = (half - float(x)) / (half * self.travel)
        offset = max(-1.0, min(1.0, offset))
        shaped = abs(offset) ** self.curve
        return float(shaped if offset >= 0.0 else -shaped)


#: How quickly the keyboard wheel winds on toward a lock the driver is holding,
#: in wheel units -- full lock is one -- a second. A tap is then a nudge and a
#: hold builds to lock over a fraction of a second; fed the keys directly the
#: wheel is at full lock the instant one goes down, and a tap at speed is a spin.
WIND_ON = 2.2

#: How quickly it returns to centre with nothing held, brisker than it winds on
#: so letting go of a key straightens the car promptly.
CENTRE = 4.5


class KeyboardWheel:
    """A steering wheel driven by on/off keys, kept as a smoothed position.

    Left and right are a key each, so the only inputs are full left, straight
    and full right. Handed to the car as they are, that is a wheel yanked to the
    stop and back, and at speed a tap is a spin. :meth:`toward` makes it a wheel
    that *winds*: it moves toward the held lock at ``wind_on`` wheel units a
    second and back to centre at ``centre``, so a tap is a small angle and a
    hold builds to full lock.

    ``position`` is where the wheel is, from -1 (full right) to +1 (full left),
    the sign a positive steering input turns towards -- the same convention as
    :class:`MouseWheel`, so the two are interchangeable where the car is
    steered.
    """

    def __init__(self, wind_on: float = WIND_ON, centre: float = CENTRE) -> None:
        self.wind_on = max(float(wind_on), 1e-3)
        self.centre = max(float(centre), 1e-3)
        #: Where the wheel is, read once a physics step.
        self.position = 0.0

    def toward(self, target: float, dt: float) -> float:
        """Wind the wheel toward ``target`` over ``dt`` seconds, and say where
        it now is.

        ``target`` is where the keys are asking for it: +1 for left held, -1 for
        right, 0 for neither. Coming back to centre, or crossing it to the other
        lock, uses the quicker ``centre`` rate; winding further into a lock uses
        ``wind_on``.
        """
        target = max(-1.0, min(1.0, float(target)))
        returning = target == 0.0 or (
            self.position != 0.0 and (self.position > 0.0) != (target > 0.0))
        rate = self.centre if returning else self.wind_on
        step = rate * max(float(dt), 0.0)
        if self.position < target:
            self.position = min(target, self.position + step)
        else:
            self.position = max(target, self.position - step)
        return self.position
