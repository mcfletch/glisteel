"""What a drive did, as numbers: one row a step, and the measures over them.

"Jerky" is a real property with a real number behind it -- how fast what the
eye and the hands see is changing -- and a test that cannot read that number
cannot notice it getting worse. A :class:`Trace` is a run recorded a physics
step at a time: where the car was, what the driver asked for, where the wheel
was, where the camera looked, and how far off the line it all ran.

    >>> from glisteel import scenarios
    >>> from glisteel.scripted import Script
    >>> from glisteel.session import Session
    >>> trace = drive(Session(scenarios.straight().world()),
    ...               Script.parse('throttle 0..4; left 2..2.4'), seconds=6.0)
    >>> trace.time_to_centre(after=2.4) < 0.5
    True

**A drive is recorded at the physics step**, one frame per step, so the record
has no gaps in it and the same script gives the same numbers every time. That is
not how the game runs -- a frame is several steps -- and running a trace at
1/60 as well is how a measure is shown not to depend on the frame rate.

The measures :meth:`Trace.measures` returns are the ones worth watching; each
says what it means and in what units, because a budget on a number nobody can
interpret is a number nobody will maintain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from glisteel.session import PHYSICS_STEP

__all__ = ['Trace', 'drive']

#: Below this the wheel is straight, in wheel units. Not zero: a wheel eased
#: back to centre passes through very small numbers on the way, and a driver
#: cannot tell a hundredth of a degree of lock from none.
CENTRED = 0.02

#: Which quantile the noisy measures are read at. The peak of a differenced
#: signal is one step of one bump; what a driver feels is what happens nearly
#: all the time.
QUANTILE = 0.95


@dataclass(eq=False)
class Trace:
    """A recorded drive: a column per thing worth measuring, a row per step.

    Every column is a numpy array of the same length, and :attr:`t` is the
    clock they are all against.

    Compared by identity (``eq=False``): every field is an array, and a
    generated ``__eq__`` would compare them element by element and then raise on
    being asked whether the resulting array is true. A drive is one run of the
    car rather than a value, and :meth:`measures` is what two of them are
    actually compared through.
    """

    t: np.ndarray
    position: np.ndarray
    speed: np.ndarray
    yaw: np.ndarray
    throttle: np.ndarray
    brake: np.ndarray
    #: What the driver asked the wheel for, -1 to 1.
    steer: np.ndarray
    #: Where the front wheels actually ended up, in radians.
    wheel_angle: np.ndarray
    camera: np.ndarray
    camera_yaw: np.ndarray
    camera_pitch: np.ndarray
    off_line: np.ndarray
    on_road: np.ndarray
    #: Why the run ended, on the step it ended, and empty on every other.
    ended: np.ndarray
    step: float = PHYSICS_STEP
    laps: list = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.t)

    # -- what the hands do -----------------------------------------------------

    def steering_rate(self) -> float:
        """The quickest the wheel moved, in wheel units a second.

        A wheel that snaps from lock to lock is a car that spins, and this is
        the number that says how sharp it gets. The peak rather than a quantile
        because the wheel's rate is not a noisy signal: it winds on at one rate,
        centres at another, and holds still the rest of the time.
        """
        return float(np.max(np.abs(np.diff(self.steer)) / self.step)) \
            if len(self) > 1 else 0.0

    def time_to_centre(self, after: float) -> float | None:
        """How long the wheel took to come back to straight, from ``after``.

        None if it never did, which is what a wheel still being held reads as --
        and what a wheel that has stuck reads as too.
        """
        from_here = np.nonzero(self.t >= after)[0]
        if not len(from_here):
            return None
        start = int(from_here[0])
        straight = np.nonzero(np.abs(self.steer[start:]) <= CENTRED)[0]
        if not len(straight):
            return None
        return float(self.t[start + int(straight[0])] - self.t[start])

    # -- what the eye sees -----------------------------------------------------

    def camera_yaw_rate(self) -> float:
        """How fast the view swings, in radians a second.

        Read off the camera rather than off the car: what makes a corner
        watchable is the rate the *frame* turns at, and a camera that filters
        the car is doing its job precisely when the two differ.
        """
        return self._quantile(np.abs(np.diff(np.unwrap(self.camera_yaw))
                                     / self.step))

    def camera_yaw_jerk(self) -> float:
        """How sharply that swing changes, in radians a second squared.

        A steady turn is comfortable at any rate; what is not is the rate
        changing under the viewer, which is what reads as jerky.
        """
        return self._quantile(np.abs(np.diff(np.unwrap(self.camera_yaw), n=2)
                                     / self.step ** 2))

    def camera_bounce(self) -> float:
        """The eye's vertical acceleration, in metres a second squared.

        The suspension moving the head up and down. A camera bolted rigidly to
        a chassis on springs passes all of it to the viewer.
        """
        return self._quantile(np.abs(np.diff(self.camera[:, 1], n=2)
                                     / self.step ** 2))

    # -- what the car does -----------------------------------------------------

    def lateral_g(self) -> float:
        """The hardest the car cornered, in g.

        From the path rather than from the physics: speed times the rate the
        car's own heading is turning, which is the acceleration a driver feels
        through the seat.
        """
        if len(self) < 2:
            return 0.0
        turning = np.abs(np.diff(np.unwrap(self.yaw)) / self.step)
        return float(np.max(turning * self.speed[1:]) / 9.81)

    def heading_change(self, start: float | None = None,
                       end: float | None = None) -> float:
        """How much the car's direction changed over a window, in degrees.

        What a steering input actually buys, which is the number a keyboard's
        feel is about: the wheel comes back to centre by itself, and the *car*
        keeps whichever way the input left it pointing.
        """
        window = self if start is None and end is None else self.between(
            start if start is not None else float(self.t[0]),
            end if end is not None else float(self.t[-1]))
        if len(window) < 2:
            return 0.0
        turned = np.unwrap(window.yaw)
        return float(np.degrees(abs(turned[-1] - turned[0])))

    def worst_off_line(self) -> float:
        """The furthest the car ran from the middle of the road, in metres."""
        return float(np.max(self.off_line)) if len(self) else 0.0

    def left_the_road(self) -> bool:
        """Whether the car was ever off the carriageway."""
        return bool(len(self) and not self.on_road.all())

    def why_it_ended(self) -> str | None:
        """The first reason the run ended, or None if it never did."""
        found = [str(one) for one in self.ended if one]
        return found[0] if found else None

    def between(self, start: float, end: float) -> Trace:
        """The part of the drive between two moments, as a trace of its own.

        What a measure of one input needs: the peak cornering force of a whole
        drive is whatever the car did on its worst moment of it, which may be
        long after the input being asked about.
        """
        kept = (self.t >= float(start)) & (self.t <= float(end))
        return Trace(
            t=self.t[kept], position=self.position[kept], speed=self.speed[kept],
            yaw=self.yaw[kept], throttle=self.throttle[kept],
            brake=self.brake[kept], steer=self.steer[kept],
            wheel_angle=self.wheel_angle[kept], camera=self.camera[kept],
            camera_yaw=self.camera_yaw[kept],
            camera_pitch=self.camera_pitch[kept], off_line=self.off_line[kept],
            on_road=self.on_road[kept], ended=self.ended[kept], step=self.step,
            laps=list(self.laps))

    # -- everything at once ----------------------------------------------------

    def measures(self) -> dict[str, float]:
        """Every measure worth watching, by name.

        What a budget is written against and what a regression is read from: a
        run whose picture is unchanged while its camera jerk has doubled is
        still a regression.
        """
        return {
            'steering_rate': self.steering_rate(),
            'camera_yaw_rate': self.camera_yaw_rate(),
            'camera_yaw_jerk': self.camera_yaw_jerk(),
            'camera_bounce': self.camera_bounce(),
            'lateral_g': self.lateral_g(),
            'heading_change': self.heading_change(),
            'worst_off_line': self.worst_off_line(),
            'top_speed': float(np.max(self.speed)) if len(self) else 0.0,
        }

    def report(self) -> str:
        """The measures as lines, for the message a failed budget prints.

        A test that says only that a number was too big leaves whoever reads it
        to run the drive again to find out what the rest of it was doing.
        """
        return '\n'.join('  %-16s %10.3f' % (name, value)
                          for name, value in self.measures().items())

    def _quantile(self, found: np.ndarray) -> float:
        return float(np.quantile(found, QUANTILE)) if len(found) else 0.0


class _Watched:
    """A driver with somebody looking over its shoulder.

    What the driver asked for is not recoverable from the car -- the steering
    lock eases off with speed, so the wheels are not the wheel -- so the answer
    is taken where it is given.
    """

    def __init__(self, driver: Any) -> None:
        self.driver = driver
        self.last: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def controls(self, session: Any, dt: float) -> tuple[float, float, float]:
        self.last = (self.driver.controls(session, dt) if self.driver is not None
                     else (0.0, 0.0, 0.0))
        return self.last


def drive(session: Any, script: Any = None, seconds: float | None = None,
          step: float = PHYSICS_STEP) -> Trace:
    """Drive a session to a script and bring back what it did.

    ``seconds`` is how long to drive for, and defaults to the script's own
    length -- give it a longer one to watch what the car does after the driver
    lets go, which is most of the question about how a control feels.

    ``step`` is how long a frame is. The default is the physics step, so the
    record has a row for every step of the simulation; a coarser one is how a
    measure is shown not to depend on the frame rate.
    """
    if script is not None:
        session.driver = script
    # At the green light. What a scripted drive measures is the car, and a
    # start sequence in front of it would put every hold in the script six
    # seconds later than it reads.
    session.run.go()
    watched = _Watched(session.driver)
    session.driver = watched
    course = session.course
    length = seconds if seconds is not None else getattr(script, 'duration', 0.0)
    rows: list[tuple] = []
    laps: list = []
    for count in range(int(round(float(length) / step))):
        before = session.ended
        pose = session.advance(step)
        index, off = course.nearest(session.car.position)
        steered = [wheel.steer_angle for wheel in session.car.vehicle.wheels
                   if wheel.spec.steering]
        rows.append((
            (count + 1) * step,
            tuple(float(v) for v in session.car.position),
            session.car.speed(),
            _heading(session.car),
            watched.last[0], watched.last[1], watched.last[2],
            float(np.mean(steered)) if steered else 0.0,
            tuple(float(v) for v in pose.position),
            pose.heading(), pose.pitch(),
            off, off <= course.carriageway_width / 2.0,
            session.ended if session.ended != before else '',
        ))
        if session.timing.laps and len(session.timing.laps) > len(laps):
            laps = list(session.timing.laps)
    session.driver = watched.driver
    return _assemble(rows, step, laps)


def _heading(car: Any) -> float:
    """Which way the car is pointing, as a yaw about the vertical."""
    forward = np.asarray(car.forward(), dtype='d')
    return float(np.arctan2(forward[0], -forward[2]))


def _assemble(rows: list, step: float, laps: list) -> Trace:
    """The recorded rows as columns."""
    if not rows:
        empty = np.zeros(0)
        return Trace(t=empty, position=np.zeros((0, 3)), speed=empty,
                     yaw=empty, throttle=empty, brake=empty, steer=empty,
                     wheel_angle=empty, camera=np.zeros((0, 3)),
                     camera_yaw=empty, camera_pitch=empty, off_line=empty,
                     on_road=np.zeros(0, dtype=bool),
                     ended=np.zeros(0, dtype=object), step=step, laps=laps)
    columns = list(zip(*rows, strict=True))
    return Trace(
        t=np.asarray(columns[0], dtype='d'),
        position=np.asarray(columns[1], dtype='d'),
        speed=np.asarray(columns[2], dtype='d'),
        yaw=np.asarray(columns[3], dtype='d'),
        throttle=np.asarray(columns[4], dtype='d'),
        brake=np.asarray(columns[5], dtype='d'),
        steer=np.asarray(columns[6], dtype='d'),
        wheel_angle=np.asarray(columns[7], dtype='d'),
        camera=np.asarray(columns[8], dtype='d'),
        camera_yaw=np.asarray(columns[9], dtype='d'),
        camera_pitch=np.asarray(columns[10], dtype='d'),
        off_line=np.asarray(columns[11], dtype='d'),
        on_road=np.asarray(columns[12], dtype=bool),
        ended=np.asarray(columns[13], dtype=object),
        step=step, laps=laps)
