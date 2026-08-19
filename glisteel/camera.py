"""Where the player watches from.

A racing camera is not a rigid mount. Bolted to the car it turns as fast as the
car does, and a spin becomes unwatchable; pinned to the world it tells the
driver nothing about which way they are pointing. So the camera *chases*: it
wants to be a set distance behind and above the car, and it gets there over
time rather than at once, which turns a flick of oversteer into a slide the
player can read and catch.

Three views, because they answer different questions. The **cockpit** view is
where the driver is, and is what the game is for: a route is a thing you drive
*through*, and a forest read from seven metres up and behind reads as scenery
rather than as trees you are passing between. The **chase** view shows what the
car is doing, which is what a player catching a slide needs. The **bonnet** view
shows exactly where the front wheels are. :class:`ChaseCamera` is all three,
with :attr:`mode`.

The cockpit's eye is a point inside the bodywork, so :attr:`ChaseCamera.inside`
says so and the game hides the player's own car for that view -- see
:attr:`glisteel.car.Car.hidden`.
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

#: Where a driver's eyes are, relative to the car body's own centre: a little
#: back of it and above it. The body sits about two thirds of a metre off the
#: road, so this puts the eye at about the height of a
#: real one. The car seats two in single file down the centreline, so the eye
#: goes there too: ``glisteel.models`` names the column the model puts the wheel
#: on, and ``tests/test_car_and_camera.py`` holds the two together.
COCKPIT_BACK = 0.10
COCKPIT_UP = 0.40
COCKPIT_SIDE = 0.0

#: Where the bonnet camera sits, ahead of the centre and lower.
BONNET_AHEAD = 1.1
BONNET_UP = 0.55

#: How far down the road a view from inside the car looks. Far enough that the
#: aim point does not swing with every bump, near enough that it is on the road
#: rather than on the horizon.
AHEAD_VIEW = 60.0

#: The views, in the order the key cycles them.
VIEWS = ('cockpit', 'chase', 'bonnet')

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

    #: One of :data:`VIEWS`.
    mode: str

    def __init__(self, mode: str = VIEWS[0]) -> None:
        self.mode = mode
        self._position: np.ndarray | None = None

    @property
    def inside(self) -> bool:
        """Whether the eye is within the car's own shell.

        A view from in there draws the inside of the bodywork and nothing else,
        so the car it belongs to is not drawn for it.
        """
        return self.mode == 'cockpit'

    @property
    def onboard(self) -> bool:
        """Whether the camera is bolted to the car rather than chasing it."""
        return self.mode != 'chase'

    def cycle(self) -> str:
        """Move to the next view, and say which it now is."""
        found = VIEWS.index(self.mode) if self.mode in VIEWS else -1
        self.mode = VIEWS[(found + 1) % len(VIEWS)]
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
        if self.onboard or self._position is None or dt <= 0:
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
        if self.mode == 'cockpit':
            # Across the car, which is what puts the eye in the driver's seat
            # rather than between the two.
            across = np.cross(flat, UP)
            eye = (position - flat * COCKPIT_BACK + UP * COCKPIT_UP
                   + across * COCKPIT_SIDE)
            return eye, eye + flat * AHEAD_VIEW
        if self.mode == 'bonnet':
            eye = position + flat * BONNET_AHEAD + UP * BONNET_UP
            return eye, eye + flat * AHEAD_VIEW
        back = min(CHASE_BACK + car.speed() * SPEED_PULL_BACK,
                   CHASE_BACK + MAXIMUM_PULL_BACK)
        eye = position - flat * back + UP * CHASE_UP
        return eye, position + flat * CHASE_AHEAD + UP * 0.8
