"""Driving a car round a course without a player.

The same three pedals, produced by looking at the road instead of at a keyboard.
It runs the demo lap, it is what an opponent car would use, and it is a way to
ask whether a circuit is actually drivable without anyone having to drive it.

**Pure pursuit** for the steering: aim at a point some distance up the road,
steer toward it, and let the distance grow with speed so the car looks further
ahead the faster it goes. It is the oldest path-following rule there is and it
holds a racing line better than anything of its size.

On its own it *cuts* a corner: aiming ``L`` up the road on a bend of radius
``R`` settles the car about ``L**2 / 2R`` inside the line, which on a narrow
road is the width of the carriageway. So the driver also corrects the error it
can see under itself, as an angle that softens with speed -- the same metres off
the line is a smaller correction the faster you are going, or what settles at
20 m/s saws the wheel at 50.

**Corner-limited speed** for the pedals: how fast a car may go through a bend of
radius *r* is `sqrt(grip * g * r)`, so the target speed comes from the curvature
of the road ahead rather than from a number written down per corner. Below the
target it accelerates, above it brakes -- and it looks far enough ahead to brake
*before* the corner rather than in it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = ['Autopilot', 'DriverStyle']

#: Standing still, the car looks this far up the road; at speed it looks this
#: many seconds ahead. Too short and it saws at the wheel; too long and it cuts
#: every corner.
LOOK_AHEAD_METRES = 12.0
LOOK_AHEAD_SECONDS = 0.6

#: How far ahead it reads the curvature to set its speed. A car doing 40 m/s
#: needs about 80 m to lose 20 of them, so it has to be looking that far.
BRAKING_SECONDS = 2.4
BRAKING_METRES = 30.0


@dataclass
class DriverStyle:
    """How hard this driver tries.

    ``grip`` is the cornering acceleration it believes it has, in g -- the
    single number that decides how fast it takes a bend, and deliberately less
    than the tyres actually have: a driver who believes the limit exactly is
    over it whenever the road is bumpy, off camber, or crests as it turns.
    ``margin`` scales the speed it aims for on top of that, so a cautious
    opponent is the same driver at 0.85.
    """

    grip: float = 0.95
    margin: float = 1.0
    maximum_speed: float = 46.0
    #: How hard it steers per radian of error, and the most it will ask for.
    steering_gain: float = 1.8
    #: How hard it pulls back to the centreline, in metres per second of
    #: sideways speed per metre off it. Zero is pure pursuit, corner-cutting
    #: and all.
    tracking: float = 4.0
    #: Speed error, in m/s, at which it goes to full throttle or full brake.
    pedal_span: float = 6.0
    #: How close this driver will get to whatever is in front, in metres, and
    #: how hard it believes it can brake, in metres per second squared. The two
    #: together are the following rule: the speed it could still stop from in
    #: the room it has.
    standing_gap: float = 7.0
    braking: float = 6.0


class Autopilot:
    """Drives a car round a :class:`~glisteel.world.Course`.

    Call :meth:`update` once a frame and pass what it returns to the car. It
    holds no state but the course and the style, so the same one can drive any
    car and a fresh one can be dropped in mid-race.
    """

    def __init__(self, course: Any, style: DriverStyle | None = None,
                 lane: float = 0.0) -> None:
        self.course = course
        self.style = style or DriverStyle()
        #: How far to its own right of the centreline this driver holds, in
        #: metres. Zero is the racing line, which is what an empty circuit
        #: wants; on a road with something coming the other way it is the
        #: middle of its own half, and the driver keeps a side.
        self.lane = float(lane)
        #: What is in front in this lane, as (gap in metres, its speed), or
        #: None for an open road. A driver who knows the corners and not the
        #: traffic drives into the back of the first car it catches.
        self.ahead: tuple[float, float] | None = None

    def following(self, gap: float | None, speed: float = 0.0) -> None:
        """Say what is in front: how far, and how fast it is going."""
        self.ahead = None if gap is None else (float(gap), float(speed))

    def line_at(self, index: int) -> np.ndarray:
        """The point of the line this driver is following, there."""
        found: np.ndarray = (self.course.point(index) if not self.lane
                             else self.course.lane_point(index, self.lane))
        return found

    def controls(self, session: Any, dt: float) -> tuple[float, float, float]:
        """Drive the session's car: a :class:`~glisteel.session.Controller`.

        What it looks at first is whatever is in front of it, because a driver
        who knows the corners and not the traffic drives into the back of the
        first car it catches.
        """
        found = session.traffic_ahead()
        self.following(*(found if found is not None else (None, 0.0)))
        return self.update(session.car)

    def update(self, car: Any) -> tuple[float, float, float]:
        """The throttle, brake and steer this driver would use right now."""
        position = np.asarray(car.position, dtype='d')
        speed = float(car.speed())
        index, _ = self.course.nearest(position)
        aim = self._aim_point(index, speed)
        steer = self._steer_towards(car, position, aim) \
            + self._back_to_the_line(car, position, index, speed)
        steer = float(np.clip(steer, -1.0, 1.0))
        target = self.target_speed(index, speed)
        throttle, brake = self._pedals(speed, target)
        return throttle, brake, steer

    # -- steering --------------------------------------------------------------

    def _aim_point(self, index: int, speed: float) -> np.ndarray:
        """The point up the road the car steers at."""
        reach = LOOK_AHEAD_METRES + speed * LOOK_AHEAD_SECONDS
        return self.line_at(index + self._points_for(reach))

    def _steer_towards(self, car: Any, position: np.ndarray,
                       aim: np.ndarray) -> float:
        """Steering input that turns the car's nose toward a point.

        The error is the angle between where the car points and where it should
        be going, measured in the ground plane -- a crest ahead is not a reason
        to steer.
        """
        forward = np.asarray(car.forward(), dtype='d')
        to_aim = aim - position
        forward[1] = to_aim[1] = 0.0
        if not np.any(to_aim) or not np.any(forward):    # pragma: no cover
            return 0.0
        forward /= np.linalg.norm(forward)
        to_aim /= np.linalg.norm(to_aim)
        # Signed angle about up: positive is a left turn, as the controls are.
        angle = math.atan2(float(np.cross(forward, to_aim)[1]),
                           float(np.dot(forward, to_aim)))
        return float(np.clip(angle * self.style.steering_gain, -1.0, 1.0))

    def _back_to_the_line(self, car: Any, position: np.ndarray, index: int,
                          speed: float) -> float:
        """The correction for being off the line where the car is now.

        ``atan2(k * error, speed)``: a heading that closes the error at
        ``k`` metres per second sideways, which is a smaller angle the faster
        the car is going. The classic cross-track term, and what stops pure
        pursuit settling inside every bend.
        """
        if not self.style.tracking:
            return 0.0
        forward = np.asarray(car.forward(), dtype='d')
        forward[1] = 0.0
        if not np.any(forward):                          # pragma: no cover
            return 0.0
        forward /= np.linalg.norm(forward)
        offset = position - self.line_at(index)
        offset[1] = 0.0
        # Positive to the car's left, which is the direction a positive steer
        # turns towards -- so the correction is its negative.
        sideways = float(np.cross(forward, offset)[1])
        angle = math.atan2(-self.style.tracking * sideways, max(speed, 1.0))
        return float(np.clip(angle, -1.0, 1.0))

    # -- pedals ----------------------------------------------------------------

    def target_speed(self, index: int, speed: float) -> float:
        """How fast the road ahead allows, in m/s.

        The tightest bend within braking distance decides it: a straight into a
        hairpin has to be slowed *on the straight*, so the limit is the minimum
        over what is coming rather than what is underfoot. Whatever is in front
        of the car holds it back as well -- see :meth:`following`.
        """
        reach = BRAKING_METRES + speed * BRAKING_SECONDS
        ahead = max(2, self._points_for(reach))
        limits = [self._corner_speed(index + step) for step in range(ahead)]
        wanted = min(min(limits), self.style.maximum_speed) * self.style.margin
        return min(wanted, self._room())

    def _room(self) -> float:
        """The fastest this driver may go for whatever is in front of it.

        ``v = sqrt(2 a s)`` in the room it has, plus whatever the car ahead is
        doing: the braking distance read backwards. The same rule the traffic
        uses on itself, so a queue behaves the same way whoever is in it.
        """
        if self.ahead is None:
            return self.style.maximum_speed
        gap, speed = self.ahead
        room = max(gap - self.style.standing_gap, 0.0)
        return float(max(speed, 0.0)
                     + math.sqrt(2.0 * self.style.braking * room))

    def _corner_speed(self, index: int) -> float:
        """The speed a bend of the road's own radius allows."""
        radius = self.curve_radius(index)
        return math.sqrt(self.style.grip * 9.81 * radius)

    def curve_radius(self, index: int) -> float:
        """The radius of the circle through three consecutive course points.

        A straight gives an enormous radius rather than an infinite one, which
        the speed limit then caps; the alternative is a special case in the one
        place the number is used.
        """
        a = self.course.point(index - 1)[[0, 2]]
        b = self.course.point(index)[[0, 2]]
        c = self.course.point(index + 1)[[0, 2]]
        first, second, third = (float(np.linalg.norm(b - a)),
                                float(np.linalg.norm(c - b)),
                                float(np.linalg.norm(c - a)))
        # Twice the triangle's area, from the two-dimensional cross product of
        # two of its sides. Written out because numpy 2 dropped the 2-D form.
        first_side, second_side = b - a, c - a
        area2 = abs(float(first_side[0] * second_side[1]
                          - first_side[1] * second_side[0]))
        if area2 < 1e-9:
            return 1e6
        return first * second * third / (2.0 * area2)

    def _pedals(self, speed: float, target: float) -> tuple[float, float]:
        """Throttle and brake from how far off the target speed the car is."""
        error = (target - speed) / max(self.style.pedal_span, 1e-6)
        if error >= 0.0:
            return min(1.0, error), 0.0
        return 0.0, min(1.0, -error)

    def _points_for(self, metres: float) -> int:
        """How many course points span a distance, at the course's own spacing."""
        spacing = self.course.length / max(1, len(self.course.centreline))
        return max(1, int(round(metres / max(spacing, 1e-6))))
