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

__all__ = ['MouseWheel', 'TRAVEL', 'CURVE']

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
