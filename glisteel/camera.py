"""Where the player watches from.

A racing camera is not a rigid mount. Bolted to the car it turns as fast as the
car does, and a spin becomes unwatchable; pinned to the world it tells the
driver nothing about which way they are pointing. So the camera *chases*: it
wants to be a set distance behind and above the car, and it gets there over
time rather than at once, which turns a flick of oversteer into a slide the
player can read and catch.

Two views, because they answer different questions. The chase view shows where
the car is going and what it is doing; the bonnet view shows exactly where the
front wheels are. :class:`ChaseCamera` is both, with :attr:`mode`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = ['CameraPose', 'ChaseCamera']

UP = np.array([0.0, 1.0, 0.0])

#: The chase camera's resting place, in metres behind and above the car, and
#: how far ahead of the car it looks.
CHASE_BACK = 7.5
CHASE_UP = 2.6
CHASE_AHEAD = 9.0

#: How quickly the camera closes on where it wants to be, as a fraction of the
#: remaining gap per second. High enough to keep up with a fast car, low enough
#: that the car moves within the frame rather than being nailed to its centre.
CHASE_RESPONSE = 6.0

#: The camera is pushed back as the car speeds up, which is what makes speed
#: read on screen: metres per metre per second.
SPEED_PULL_BACK = 0.06
MAXIMUM_PULL_BACK = 6.0


@dataclass
class CameraPose:
    """Where the camera is and what it is looking at."""

    position: np.ndarray
    target: np.ndarray

    def heading(self) -> float:
        """Yaw in radians from -Z, for a view platform that wants angles."""
        forward = self.target - self.position
        return math.atan2(float(forward[0]), -float(forward[2]))

    def pitch(self) -> float:
        """Pitch in radians, positive looking up."""
        forward = self.target - self.position
        length = float(np.linalg.norm(forward))
        if length < 1e-9:                        # pragma: no cover - same point
            return 0.0
        return math.asin(float(forward[1]) / length)


class ChaseCamera:
    """A camera that follows a car, and can sit on its bonnet instead.

    Call :meth:`update` once a frame with the car and the time since the last
    one; it returns the pose to put the view at. The chase position is smoothed
    and the aim is not, so the camera lags the car's *position* while always
    looking where the car is going -- which is what stops a corner from
    swinging the whole frame.
    """

    #: ``'chase'`` or ``'bonnet'``.
    mode: str

    def __init__(self, mode: str = 'chase') -> None:
        self.mode = mode
        self._position: np.ndarray | None = None

    def cycle(self) -> str:
        """Switch to the other view, and say which it now is."""
        self.mode = 'bonnet' if self.mode == 'chase' else 'chase'
        self._position = None
        return self.mode

    def reset(self) -> None:
        """Forget where the camera was: the next frame snaps into place.

        For a car that has just been put back on the grid, where following it
        smoothly would mean sweeping across the whole map to catch up.
        """
        self._position = None

    def update(self, car: Any, dt: float) -> CameraPose:
        wanted, target = self._wanted(car)
        if self.mode == 'bonnet' or self._position is None or dt <= 0:
            self._position = wanted
        else:
            # Exponential approach, framed so the rate is per second and the
            # result does not change with the frame rate.
            blend = 1.0 - math.exp(-CHASE_RESPONSE * dt)
            self._position = self._position + (wanted - self._position) * blend
        return CameraPose(position=self._position.copy(), target=target)

    def _wanted(self, car: Any) -> tuple[np.ndarray, np.ndarray]:
        position = np.asarray(car.position, dtype='d')
        forward = np.asarray(car.forward(), dtype='d')
        flat = forward - UP * float(np.dot(forward, UP))
        length = float(np.linalg.norm(flat))
        flat = flat / length if length > 1e-6 else np.array([0.0, 0.0, -1.0])
        if self.mode == 'bonnet':
            eye = position + flat * 1.1 + UP * 0.55
            return eye, eye + flat * 40.0
        back = min(CHASE_BACK + car.speed() * SPEED_PULL_BACK,
                   CHASE_BACK + MAXIMUM_PULL_BACK)
        eye = position - flat * back + UP * CHASE_UP
        return eye, position + flat * CHASE_AHEAD + UP * 0.8
