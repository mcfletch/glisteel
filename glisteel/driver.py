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
from OpenGLContext.telemetry import NOT_RECORDING

from glisteel import traffic
from glisteel.interfaces import CarLike, CourseLike, SessionLike
from glisteel.steering import KEY_FOR

__all__ = ['Autopilot', 'DriverStyle', 'StandIn', 'PASSING_REACH',
           'WORTH_PASSING', 'PASS_ACROSS', 'CAR_LENGTHS', 'PASS_MARGIN',
           'PASS_AGAIN',
           'PASSED_BY', 'PASS_LONGEST', 'PACE', 'SETTLED', 'ALONGSIDE',
           'FOLLOWING_SECONDS', 'FOLLOWING_LEAST', 'RACING_KPH',
           'PASSING_GAP', 'THINKING', 'CROSSING_MARGIN', 'LANE_WIDTH',
           'STILL_ON', 'REASON_HOLDS']

#: Standing still, the car looks this far up the road; at speed it looks this
#: many seconds ahead. Too short and it saws at the wheel; too long and it cuts
#: every corner.
LOOK_AHEAD_METRES = 12.0
LOOK_AHEAD_SECONDS = 0.6

#: How far ahead it reads the curvature to set its speed. A car doing 40 m/s
#: needs about 80 m to lose 20 of them, so it has to be looking that far.
BRAKING_SECONDS = 2.4
BRAKING_METRES = 30.0

#: What to assume about a car that will not say: an ordinary saloon's wheelbase
#: in metres, and a front-wheel angle at full lock in radians. Only reached for
#: something that is not a raycast vehicle, which is a test double.
WHEELBASE = 2.6
STEER_LOCK = 0.55


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
    #: How eagerly it turns towards where it is going, as a multiple of the
    #: heading error. One is the geometry's own answer -- pure pursuit, which
    #: arrives on the line without overshooting it; above one is a driver who
    #: turns in harder than the shortest arc.
    steering_gain: float = 1.0
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
    #: How hard it believes it accelerates, in metres per second squared.
    #: What decides how long getting by something takes, since a pass is
    #: driven rather than coasted: at the speed the car happens to be doing, a
    #: standing start behind something stopped never closes at all.
    #:
    #: One number for a drivetrain that has two -- the shipped car pulls
    #: 7.4 m/s\u00b2 off the line and 1.9 at thirty-five, being electric and
    #: therefore constant-force to :attr:`base_speed` and constant-power after
    #: it. This is what it averages over a manoeuvre, which is what the
    #: manoeuvre is being measured with, and it sits beside ``braking`` for the
    #: same reason: what a driver *believes* they have is what they drive on.
    pull: float = 3.5


class Autopilot:
    """Drives a car round a :class:`~glisteel.world.Course`.

    Call :meth:`update` once a frame and pass what it returns to the car. It
    holds no state but the course and the style, so the same one can drive any
    car and a fresh one can be dropped in mid-race.
    """

    def __init__(self, course: CourseLike, style: DriverStyle | None = None,
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

    def controls(self, session: SessionLike, dt: float
                 ) -> tuple[float, float, float]:
        """Drive the session's car: a :class:`~glisteel.session.Controller`.

        What it looks at first is whatever is in front of it, because a driver
        who knows the corners and not the traffic drives into the back of the
        first car it catches.
        """
        found = session.traffic_ahead()
        self.following(*(found if found is not None else (None, 0.0)))
        return self.update(session.car)

    def update(self, car: CarLike) -> tuple[float, float, float]:
        """The throttle, brake and steer this driver would use right now.

        The steering is worked out as an **angle for the front wheels** and only
        then turned into a control input, because the two are not the same
        thing: how much of the wheels' travel one unit of input buys falls away
        as the car speeds up (:meth:`omi_physics.vehicle.VehicleTuning.steer_lock`).
        A driver that asked for a fraction of the travel instead would take a
        given bend differently at every speed, and would have to be re-tuned for
        every car it was put in.
        """
        speed = float(car.speed())
        position = np.asarray(car.position, dtype='d')
        index, _ = self.course.nearest(position)
        return (*self._pedals(speed, self.target_speed(index, speed)),
                self.steering(car, index=index, position=position, speed=speed))

    def steering(self, car: CarLike, index: int | None = None,
                 position: Any = None, speed: float | None = None) -> float:
        """The steering input that puts this car back on the line.

        Separate from the pedals, because holding a car on a line and choosing
        how fast to go are different jobs and something may want only the first
        -- :class:`~glisteel.assist.Straighten` is the case that does.

        ``index``, ``position`` and ``speed`` are what :meth:`update` has
        already worked out about this car this step; a caller that has them
        passes them rather than having the course asked a second time about a
        car that has not moved in between.
        """
        if position is None:
            position = np.asarray(car.position, dtype='d')
        if speed is None:
            speed = float(car.speed())
        if index is None:
            index, _ = self.course.nearest(position)
        aim = self._aim_point(index, speed)
        heading = (self._error_towards(car, position, aim)
                   * self.style.steering_gain
                   + self._back_to_the_line(car, position, index, speed))
        return self._input_for(car, self._front_wheels(car, heading, speed),
                               speed)

    def _front_wheels(self, car: CarLike, heading: float, speed: float) -> float:
        """The front-wheel angle that closes a heading error, in radians.

        Pure pursuit: a car of wheelbase *L* held on one steering angle follows
        a circle, and the circle through the car and a point ``reach`` ahead of
        it at a heading error of ``heading`` needs
        ``atan(2 L sin(heading) / reach)``. The geometry supplies the number, so
        there is nothing here to tune per car.
        """
        reach = LOOK_AHEAD_METRES + speed * LOOK_AHEAD_SECONDS
        base = self._wheelbase(car)
        return math.atan2(2.0 * base * math.sin(heading), max(reach, 1e-6))

    def _input_for(self, car: CarLike, wanted: float, speed: float) -> float:
        """The control input that asks the front wheels for that angle."""
        lock = self._lock(car, speed)
        if lock <= 0.0:                                  # pragma: no cover
            return 0.0
        return float(np.clip(wanted / lock, -1.0, 1.0))

    @staticmethod
    def _wheelbase(car: CarLike) -> float:
        vehicle = getattr(car, 'vehicle', None)
        base = vehicle.wheelbase() if vehicle is not None else 0.0
        return base if base > 0.0 else WHEELBASE

    @staticmethod
    def _lock(car: CarLike, speed: float) -> float:
        vehicle = getattr(car, 'vehicle', None)
        if vehicle is None:                              # pragma: no cover
            return STEER_LOCK
        return float(vehicle.tuning.steer_lock(speed))

    # -- steering --------------------------------------------------------------

    def _aim_point(self, index: int, speed: float) -> np.ndarray:
        """The point up the road the car steers at."""
        reach = LOOK_AHEAD_METRES + speed * LOOK_AHEAD_SECONDS
        return self.line_at(index + self._points_for(reach))

    def _error_towards(self, car: CarLike, position: np.ndarray,
                       aim: np.ndarray) -> float:
        """How far round the car has to come to point at somewhere, in radians.

        Measured in the ground plane -- a crest ahead is not a reason to steer.
        """
        forward = np.asarray(car.forward(), dtype='d')
        to_aim = aim - position
        forward[1] = to_aim[1] = 0.0
        if not np.any(to_aim) or not np.any(forward):    # pragma: no cover
            return 0.0
        forward /= np.linalg.norm(forward)
        to_aim /= np.linalg.norm(to_aim)
        # Signed angle about up: positive is a left turn, as the controls are.
        return math.atan2(float(np.cross(forward, to_aim)[1]),
                          float(np.dot(forward, to_aim)))

    def _back_to_the_line(self, car: CarLike, position: np.ndarray, index: int,
                          speed: float) -> float:
        """The extra heading wanted for being off the line, in radians.

        ``atan2(k * error, speed)``: a heading that closes the error at ``k``
        metres per second sideways, which is a smaller angle the faster the car
        is going. The classic cross-track term, and what stops pure pursuit
        settling inside every bend. It is added to the heading error rather than
        to the steering, so the one geometric conversion covers both.
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

    def road_speed(self, index: int, speed: float) -> float:
        """How fast the *road* ahead allows, in m/s, whatever is on it.

        The tightest bend within braking distance decides it: a straight into a
        hairpin has to be slowed *on the straight*, so the limit is the minimum
        over what is coming rather than what is underfoot.

        Separate from :meth:`target_speed` because a driver deciding whether
        something in front is worth passing has to compare it against the speed
        it *could* be doing -- and the speed it is doing has already been cut
        down by that very car.

        For the *pedals*. What a manoeuvre is planned at is
        :meth:`pace_over`.
        """
        reach = BRAKING_METRES + speed * BRAKING_SECONDS
        ahead = max(2, self._points_for(reach))
        # One pass over the road's own radii rather than working each bend out
        # again: the shape of a course is settled when it is read, and this is
        # asked for by every driver on the road every frame.
        radii = self.course.radii
        wanted_indices = (index + np.arange(ahead)) % len(radii)
        tightest = float(radii[wanted_indices].min())
        limit = math.sqrt(self.style.grip * 9.81 * tightest)
        return min(limit, self.style.maximum_speed) * self.style.margin

    def pace_over(self, index: int, metres: float) -> float:
        """The speed the road allows *on average* over the next stretch, m/s.

        What a manoeuvre is planned at. :meth:`road_speed` answers with the
        slowest the road gets within braking distance, which is the number the
        pedals need: a car that cannot slow for the tightest part of what is
        coming is a car off the road. Over the length of a pass it is the wrong
        number twice over -- the tight part is one corner of two hundred metres
        of road, the car drives the rest of it at what the rest of it holds,
        and a pass planned at the speed of the slowest corner in it is a pass
        the driver believes it has no acceleration for and never takes.
        """
        radii = self.course.radii
        points = max(2, self._points_for(max(float(metres), 0.0)))
        wanted_indices = (index + np.arange(points)) % len(radii)
        limits = np.sqrt(self.style.grip * 9.81 * radii[wanted_indices])
        return float(np.minimum(limits, self.style.maximum_speed).mean()
                     * self.style.margin)

    def target_speed(self, index: int, speed: float) -> float:
        """How fast to be going, in m/s: the road, and what is on it.

        Whatever is in front of the car holds it back as well as the corners do
        -- see :meth:`following`.
        """
        return min(self.road_speed(index, speed), self._room())

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
        return math.sqrt(self.style.grip * 9.81 * self.curve_radius(index))

    def curve_radius(self, index: int) -> float:
        """The radius of the bend at one point of the road, in metres.

        The course works this out for the whole line at once and keeps it
        (:attr:`glisteel.world.Course.radii`), since it is geometry and cannot
        change while the car drives round it. This is the single-point way in,
        for anything asking about one bend rather than about the road ahead.
        """
        radii = self.course.radii
        return float(radii[index % len(radii)])

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


#: The least road a stand-in decides a pass over, in metres. Far enough that
#: the decision is made before it has caught the car in front, since a pass
#: begun from a car length back is a pass spent alongside. Going quickly it
#: looks further, because a hundred metres is two seconds at a hundred and
#: forty km/h and the lane change alone takes more than that -- see
#: :meth:`StandIn.deciding`.
PASSING_REACH = 110.0

#: How much slower than this driver wants to be going the car in front has to
#: be before passing it is worth the road, in metres per second. Pulling out for
#: somebody doing all but two of your own speed is a manoeuvre spent for nothing.
WORTH_PASSING = 3.0

#: How long the two lane changes of a pass take, in seconds, over and above
#: the closing. The rest of a pass is the closing itself, which depends on
#: what is being passed (:meth:`StandIn.pass_seconds`).
PASS_ACROSS = 2.0

#: Two cars' worth of length to clear, in metres.
CAR_LENGTHS = 9.0

#: How much more road than getting back out of a pass strictly takes a driver
#: wants before they are willing to try -- their appetite for the risk, as a
#: multiple of :meth:`StandIn.getting_back`.
#:
#: This is the dial the whole mechanic turns on. A pass is a bet: the reward is
#: the time it buys, and the stake is being on the wrong side of the road when
#: the road runs out. Set high, nothing is ever worth trying and the mode has
#: no passing in it; set at nothing, every blind bend is taken on and the drive
#: ends against something coming the other way. A racer's appetite is thin --
#: see plans/CONTROL-SCHEMES.md section 8.1.2 for what each setting measured.
PASS_MARGIN = 1.1

#: How hard a stand-in drives unless it is told otherwise, as a fraction of what
#: the road allows.
#:
#: The number is the *aid's* limit rather than the tyres'. What is steering is
#: the game's line-holding aid, at a gain chosen to be gentle, and above this it
#: loses the line on a tight bend however much grip the car still has. Measured
#: on the 150 by 95 m circuit of :mod:`glisteel.scenarios`, which is the
#: tightest thing anything here drives: it gets round at this and goes off at
#: 0.92. ``--pace`` is how a caller asks for more.
PACE = 0.88

#: How far off the speed it is aiming for a stand-in coasts rather than doing
#: anything, in metres per second. Without a band the throttle and the brake
#: swap every step at the speed it wants, which is a foot going up and down a
#: hundred times a second rather than a driver.
SETTLED = 1.0

#: How far a stand-in sits behind whatever it is following, in **seconds**, and
#: the least that is worth in metres.
#:
#: A time rather than a distance, because what a following distance is for is
#: the moment between the car in front braking and this one doing something
#: about it -- and at two hundred against a road doing eighty, a gap that is
#: comfortable at a crawl is a second and a half. It is also what a driver
#: deciding whether to pass needs: room to see past the car in front and room to
#: pull out into, neither of which exists from seven metres off its bumper.
FOLLOWING_SECONDS = 2.0
FOLLOWING_LEAST = 14.0

#: How fast a stand-in means to be going, in km/h. It is *racing*: everything
#: else on the road is doing the posted limit, and a driver who joins them at it
#: is not in a race. Where the corners allow less, the corners win -- this is
#: what it aims for on the parts of the road that allow anything, and what the
#: traffic's own spacing is chosen against
#: (:func:`glisteel.traffic.cars_for`).
RACING_KPH = 200.0

#: How far behind a stand-in wants what it pulled out for before it comes back
#: in, in metres. Further than the room it asks for behind it in the lane it is
#: returning to, so the car it has just passed is not what makes that lane
#: un-clear.
PASSED_BY = 18.0

#: How much more room than the lane change strictly needs a driver wants
#: before pulling out, as a multiple. The crossing time is what a comfortable
#: change takes; leaving exactly that is arriving in the other lane at the
#: moment of contact.
CROSSING_MARGIN = 1.5

#: How wide a lane is when a driver is working out how long it takes to get
#: out of one, in metres. The road's own lanes are what a pass is actually
#: driven across; this is the figure the *decision* is taken on, before there
#: is a road in front of the driver to measure.
LANE_WIDTH = 3.6

#: How long a driver takes to act on what it has seen, in seconds. What turns
#: a look-ahead into a distance along with the braking (:meth:`StandIn.looking`).
THINKING = 1.0

#: How close a driver getting past something runs to it, in metres.
#:
#: A pass is an *acceleration*, and the gap that keeps a driver comfortable
#: behind a car is the gap that stops them ever drawing alongside one: held to
#: :data:`FOLLOWING_SECONDS` of road all the way past, the car sits out in the
#: other lane at the speed of what it is passing until the road runs out.
#: Short enough to get by with, and still the room to stop in
#: (:meth:`Autopilot._room` goes on applying), so it is a racing gap rather
#: than no gap.
PASSING_GAP = 6.0

#: How long a reason for not passing has to hold before it is worth writing
#: down, in seconds. Shorter than a decision and longer than a frame: two
#: reasons swapping every frame are the boundary between them rather than a
#: driver changing its mind, and written down they bury the stretches a reader
#: came for.
REASON_HOLDS = 0.2

#: The appetite a pass already under way is judged with, as a multiple of what
#: finishing it costs (:meth:`StandIn.room_to_finish`). Well under
#: :data:`PASS_MARGIN`, so a pass is kept until it is clearly not on rather
#: than dropped the moment it stops being comfortable: how much road a pass
#: needs is a number that wanders about the bar it is measured against as the
#: car moves along the road, and a band narrower than the wander is a driver
#: that changes its mind at whatever rate it is asked.
#:
#: It cannot make a pass unsafe to leave: the room to get back out
#: (:meth:`StandIn.getting_back`) is a floor under the question rather than
#: something the appetite scales.
STILL_ON = 0.75

#: How far in front what is being passed has to still be for the pass to be
#: given up, in metres. Nearer than this the two cars are alongside, and
#: crossing back is crossing onto the other one.
ALONGSIDE = 12.0

#: How far clear of the car it pulled out for the stand-in has to get before
#: the pedals go back to driving the road, in metres. A car's length and the
#: room a lane change needs beside it: the gap has to be one a driver would
#: actually turn into.
SLIPPED = 20.0

#: How long the pedals may be given to making that gap, in seconds. A gap that
#: has not opened by now is not going to -- the other car is doing the same
#: speed -- and sitting on one pedal waiting for it is worse than driving the
#: road again and asking for the lane when it comes.
SLIP_LONGEST = 5.0

#: The longest a stand-in stays out for one pass, in seconds. Whatever it pulled
#: out for, if it is not by after this it is not getting by: something has
#: changed -- the other car sped up, the road went uphill -- and sitting in the
#: oncoming lane waiting to find out is the one thing not to do.
PASS_LONGEST = 14.0

#: How long a stand-in stays on its own side after a pass before considering
#: another, in seconds. Without it, a pass given up because something was coming
#: is begun again the moment that car is by, and the road either side of an
#: abandoned pass is where a driver wants to be settled.
PASS_AGAIN = 2.5


class StandIn:
    """An autopilot at the controls, driving the way a player does.

    Handed a way of driving (:mod:`glisteel.schemes`), it presses the keys a
    player would press -- the pedals, and the lane keys when it wants to pass --
    and what reaches the car is whatever that scheme makes of them. That is the
    point of it: a driver that reached past the controls and steered would
    measure the *road*, and what is worth measuring is the controls.

    It decides the two things a player decides in a mode that steers for them:
    how fast to be going, and when to pull out. The first is
    :class:`Autopilot`\'s answer, held through a keyboard's on-or-off pedals.
    The second is its own, and it is where the checks live that the lane switch
    deliberately does not do (:class:`~glisteel.schemes.Lanes`): a player in easy
    mode is the one who looks before pulling out, and so is this.

        >>> from glisteel import schemes
        >>> stand_in = StandIn(schemes.named('lanes'))
        >>> stand_in.advises
        True
    """

    def __init__(self, scheme: Any, style: DriverStyle | None = None,
                 lane: float = 0.0) -> None:
        self.scheme = scheme
        #: What works out how fast the road ahead allows.
        #: Whether it drives at :data:`RACING_KPH` or at the pace it was given.
        self.racing = style is None
        self.pilot = Autopilot(getattr(scheme, 'course', None) or _NO_COURSE,
                               style=style or DriverStyle(margin=PACE),
                               lane=lane)
        #: Whether it is out of its own lane, getting past something.
        self.overtaking = False
        #: How many cars it has been past, which is what a drive is judged on
        #: as much as by its lap time.
        self.passes = 0
        #: Which side of the crown it keeps to where the run does not say.
        self.own_side = float(lane)
        #: What it pulled out for, while it is getting by it.
        self.passing: Any = None
        #: Which way it is making room to come back in -- 'ahead' on the
        #: throttle, 'behind' on the brake -- or None when it is driving the
        #: road rather than fitting into a gap.
        self.slipping: str | None = None
        self._slip_car: Any = None
        self._slipping_for = 0.0
        #: How long it has been out there, in seconds.
        self.passing_for = 0.0
        self._waited = PASS_AGAIN
        self._refused: str | None = None
        self._refusing: str | None = None
        self._refused_for = 0.0
        #: How long the last pass this driver thought about would have taken,
        #: in seconds -- what the decision to take it or refuse it was made on.
        self._planned = 0.0
        self._session: Any = None

    def __repr__(self) -> str:
        return 'StandIn(%s%s)' % (getattr(self.scheme, 'name', '?'),
                                  ', overtaking' if self.overtaking else '')

    @property
    def source(self) -> Any:
        """The keys this presses, which are the scheme\'s own."""
        return self.scheme.source

    @property
    def advises(self) -> bool:
        """Whether the run reads the road ahead for this drive."""
        return bool(getattr(self.scheme, 'advises', False))

    def controls(self, session: SessionLike, dt: float
                 ) -> tuple[float, float, float]:
        """Press what a player would press, and let the scheme answer."""
        if session is not self._session:
            self._session = session
            self.pilot.course = session.course
            self.race_at(session.course)
        self.pedals(session, dt)
        self.lanes(session, dt)
        found: tuple[float, float, float] = self.scheme.controls(session, dt)
        return found

    def race_at(self, course: Any) -> None:
        """Aim at :data:`RACING_KPH` wherever the road allows it.

        Only where the run did not say otherwise: a caller that built this with
        a style of its own asked for that pace, and a road is not the place to
        overrule it.
        """
        if self.racing:
            self.pilot.style.maximum_speed = RACING_KPH / 3.6

    # -- how fast ---------------------------------------------------------------

    def pedals(self, session: SessionLike, dt: float = 0.0) -> None:
        """Hold the throttle or the brake, from the speed the road allows.

        A keyboard has one pedal position and it is *down*, so what a
        proportional answer becomes is a key held while the car is short of the
        speed it wants and the other one held when it is over -- which is what a
        player has as well, and part of what a way of driving is being judged on.

        :data:`SETTLED` is the band between them, where neither is held. Without
        one the two keys swap every step around the speed it is aiming for, which
        is a car being driven with its foot going up and down forty times a
        second.
        """
        if self.slipping is not None:
            self._slipping_for += float(dt)
            if self.slipped(session):
                self.slipping = self._slip_car = None
            else:
                # Making the gap is the whole of the driving until it is made:
                # the road's own speed is what to come back to afterwards.
                self.hold('throttle', self.slipping == 'ahead')
                self.hold('brake', self.slipping == 'behind')
                return
        car = session.car
        speed = float(car.speed())
        # How far back to sit. Behind something it means to stay behind, that
        # is a time gap (:data:`FOLLOWING_SECONDS`); behind something it is
        # getting past, it is :data:`PASSING_GAP` -- a pass is not a follow.
        self.pilot.style.standing_gap = (
            PASSING_GAP if self.overtaking
            else max(FOLLOWING_SECONDS * speed, FOLLOWING_LEAST))
        index, _distance = self.pilot.course.nearest(car.position)
        reach = self.looking(speed)
        # Whatever is in front, whether or not a pass is under way: the car
        # being passed is still a car to keep off the back of until it is
        # actually beside this one, and a lane the car has not reached yet is
        # a lane it is not in.
        found = session.traffic_ahead(reach)
        self.pilot.following(*(found if found is not None else (None, 0.0)))
        wanted = self.pilot.target_speed(index, speed)
        if found is not None:
            wanted = self.keeping_back(wanted, *found)
        self.hold('throttle', speed < wanted - SETTLED)
        self.hold('brake', speed > wanted + SETTLED)

    def deciding(self, session: SessionLike) -> float:
        """How far up the road to look for something to get past, in metres.

        The same road it would brake in (:meth:`looking`): a driver decides to
        pass from as far back as they can act on what they see, and one that
        waits until the car in front is inside a fixed window has left itself
        no room to cross before arriving at it.
        """
        return self.looking(float(session.car.speed()))

    def looking(self, speed: float) -> float:
        """How far up the road to watch for traffic, in metres.

        As far as it would take to stop from here, and the road covered while
        deciding to. A fixed number is a speed limit in disguise: stopping
        from two hundred kilometres an hour takes a quarter of a kilometre,
        and a driver watching a hundred metres of road meets a stopped car
        with no room left to stop in however early it starts braking.

        Never less than :data:`PASSING_REACH`, which is the road a pass is
        decided over rather than the road it is stopped in.
        """
        speed = max(float(speed), 0.0)
        braking = max(self.pilot.style.braking, 1e-6)
        return max(PASSING_REACH,
                   speed * speed / (2.0 * braking) + speed * THINKING)

    def keeping_back(self, wanted: float, gap: float, speed: float) -> float:
        """The speed to aim for, given what is in front and how far off it is.

        A following distance is a *distance*, and a driver closer than the one
        they want aims **under** the speed of the car in front until they have
        it back. The racing rule underneath (the fastest you could still stop
        from in the room you have,
        :meth:`~glisteel.driver.Autopilot._room`) says "match them" at every gap
        shorter than that, which holds a gap closed up in a corner for as long
        as the road goes on -- fine for a driver whose plan is to be past in a
        moment, and not what somebody driving a road does.

        Left in the stand-in rather than pushed down into the autopilot because
        the two want different things of the same number: a racing driver's
        ``standing_gap`` is how close it will get, and this is how far back it
        will sit.
        """
        room = float(gap) / max(self.pilot.style.standing_gap, 1e-6)
        if room >= 1.0:
            return float(wanted)
        return max(min(float(wanted), float(speed) * room), 0.0)

    # -- and when to pull out ---------------------------------------------------

    def lanes(self, session: SessionLike, dt: float = 0.0) -> None:
        """Ask for the lane over when there is something worth getting past.

        One press: the lane switch takes the car across and holds it there, so
        holding the key would be asking for the lane after that one.
        """
        self.hold('left', False)
        self.hold('right', False)
        self._waited += float(dt)
        if self.overtaking:
            self.passing_for += float(dt)
            if self.abandoning(session):
                self.give_up(session, 'the road ran out')
            elif self.given_up():
                self.give_up(session, 'took too long')
            elif self.got_by(session):
                self.passes += 1
                self.mark(session, 'pass-done',
                          seconds=round(self.passing_for, 1))
                self.come_back(session)
            return
        if self._waited < PASS_AGAIN:
            return
        why = self.refusing(session)
        if why is not None:
            self.refused(session, why, dt)
            return
        self._refused = None
        found = session.traffic_ahead(self.deciding(session))
        self.overtaking = True
        self.passing = session.car_ahead(self.deciding(session))
        self.passing_for = 0.0
        self.hold('left', True)
        self.mark(session, 'pass-begun',
                  gap=round(found[0], 1) if found else 0.0,
                  theirs=round(found[1] * 3.6, 1) if found else 0.0,
                  speed=round(float(session.car.speed()) * 3.6, 1),
                  sight=round(self.seen(session)[0], 1),
                  seconds=round(self._planned, 1))

    def give_up(self, session: SessionLike, why: str) -> None:
        """Come in without counting it: a pass given up got past nothing.

        Written down with how much of the manoeuvre was left, because that is
        the question a reader has: a pass dropped with the other car still a
        hundred metres up the road was never on, and one dropped a car's
        length short was the road, not the decision.
        """
        along = (session.along(self.passing) if self.passing is not None
                 else 0.0)
        left, _quick = self.planning(
            session, along,
            float(self.passing.speed) if self.passing is not None else 0.0)
        self.mark(session, 'pass-given-up', why=why,
                  seconds=round(self.passing_for, 1),
                  across=round(self.across(session), 2),
                  along=round(float(along), 1),
                  left=round(left, 1),
                  sight=round(self.seen(session)[0], 1))
        self.come_back(session)

    def refused(self, session: SessionLike, why: str, dt: float = 0.0) -> None:
        """Note that a pass was not on, the first time each reason is.

        Once per reason rather than once a frame: a reason that has not changed
        is a reason already written down, and sixty of them a second is a file
        nobody reads. What a reader wants is the *stretch* -- it wanted to pass
        from here to there and the bend was too blind.

        And only once the reason has *held* for :data:`REASON_HOLDS`.
        """
        if why != self._refusing:
            self._refusing, self._refused_for = why, 0.0
        self._refused_for += max(float(dt), 0.0)
        if why == self._refused or self._refused_for < REASON_HOLDS:
            return
        self._refused = why
        self.mark(session, 'pass-refused', why=why,
                  speed=round(float(session.car.speed()) * 3.6, 1),
                  sight=round(self.seen(session)[0], 1),
                  seconds=round(self._planned, 1))

    @staticmethod
    def mark(session: SessionLike, name: str, **fields: Any) -> None:
        """Write one moment of the drive into the session record."""
        getattr(session, 'telemetry', NOT_RECORDING).mark(name, **fields)

    def come_back(self, session: SessionLike) -> None:
        """Take the lane back, and make the gap to come back into.

        Coming in is not only a steering input. Level with the car it pulled
        out for there is no gap to steer into, and one has to be *made*: past
        it, the way in is forward and the throttle makes it; still beside it,
        the way in is backward and lifting off makes it. That is the choice a
        driver makes with their right foot, which is why the stand-in makes it
        -- the lane switch steers and nothing else, and a player in easy mode
        is expected to do exactly this for themselves.
        """
        self._slip_car = self.passing
        self.slipping = self.slip_for(session)
        self._slipping_for = 0.0
        self.overtaking = False
        self.passing = None
        self._waited = 0.0
        self.hold('right', True)

    def slip_for(self, session: SessionLike) -> str | None:
        """Which way to make the gap, or None with nothing to make one beside.

        Read from where the other car's middle is rather than from which lane
        this one has reached: what decides whether forward or backward is the
        shorter way in is how much of the pass is already done.
        """
        if self._slip_car is None:
            return None
        return 'ahead' if session.along(self._slip_car) < 0.0 else 'behind'

    def slipped(self, session: SessionLike) -> bool:
        """Whether the gap is made and the pedals belong to the road again."""
        if self._slip_car is None or self._slipping_for > SLIP_LONGEST:
            return True
        along = float(session.along(self._slip_car))
        return bool(along < -SLIPPED if self.slipping == 'ahead'
                    else along > SLIPPED)

    def abandoning(self, session: SessionLike) -> bool:
        """Whether to give the pass up rather than finish it.

        The road stops being clear after the decision was made -- something
        comes round the bend nobody could see round -- and a driver who will
        not give a pass up is a driver who meets it head-on.

        What decides whether they *can* is where the other car is, not which
        lane this one has got to: while it is still :data:`ALONGSIDE` metres or
        more behind what it pulled out for, lifting off drops it in behind;
        once it is beside it, coming back across the crown is coming back onto
        it, and finishing is the safer half of a bad choice.

        Asked about the car it pulled out for, not about whatever is in front
        now: half-way out of the lane there is nothing in front any more, and a
        pass that gave itself up on that would be a pass that never happened.
        """
        if self.passing is None:                 # pragma: no cover - no target
            return True
        along = session.along(self.passing)
        if along <= ALONGSIDE:
            return False
        # What is left of the pass, not the one that was planned: half of it is
        # already driven, and a driver a car's length off the back bumper needs
        # far less road than the one who pulled out did.
        #
        # Asked with a thinner appetite than the one that began it
        # (:data:`STILL_ON`): the room a pass needs is a number that wanders
        # about the bar it is measured against, and a driver who asks the same
        # question of it sixty times a second answers differently sixty times a
        # second -- it pulls out and, a fifth of a second later, before the car
        # has moved, gives up. A decision taken is worth keeping until it is
        # clearly wrong rather than until it stops being clearly right.
        left, _quick = self.planning(session, along, float(self.passing.speed))
        return not self.room_to_finish(session, left, margin=STILL_ON)

    def given_up(self) -> bool:
        """Whether the pass has simply gone on too long to be one.

        Whatever it pulled out for, if it is not by after :data:`PASS_LONGEST`
        it is not getting by: something has changed -- the other car sped up,
        the road went uphill -- and sitting out there waiting to find out is
        the one thing not to do. Coming in, not a pass: what is counted is
        cars got past, and a manoeuvre given up got past nothing.
        """
        return bool(self.passing_for > PASS_LONGEST)

    def got_by(self, session: SessionLike) -> bool:
        """Whether what it pulled out for is behind it, with room to come back.

        Both halves matter. A driver who comes back in as soon as the other car
        stops being *in front* comes back in on top of it, because a car
        alongside is in front of nobody; and one that waits for its own lane to
        be clear without checking what it was passing waits for ever behind a
        queue.
        """
        if self.passing is None:                 # pragma: no cover - no target
            return True
        across = self.side(session)
        return bool(session.along(self.passing) < -PASSED_BY
                    and session.lane_clear(across)
                    and self.room_in(session, across))

    def can_pull_out(self, session: SessionLike) -> bool:
        """Whether the far lane can be moved into, held, and got by in."""
        return self.refusing(session) is None

    def refusing(self, session: SessionLike) -> str | None:
        """Why this driver is not pulling out, or None when it would.

        The same decision :meth:`can_pull_out` answers, with the reason kept
        rather than thrown away. A lap that passes nothing says nine passes or
        none and never *which* check said no, and that one word is the whole of
        what is wanted when a drive turns out boring: the road was too blind,
        or something was coming, or it had already arrived at the car in front.
        It goes into the session record (:mod:`OpenGLContext.telemetry`), so a
        drive nobody watched can still be read afterwards.

        Built as the *source* of the answer rather than beside it, because two
        copies of four conditions drift apart and the one that drifts is the
        explanation.
        """
        found = session.traffic_ahead(self.deciding(session))
        if found is None:
            return 'nothing in front'
        if not self.worth_passing(session):
            return 'nothing worth passing'
        gap, speed = found
        # How long it takes given what the car can do about it: from here, at
        # the pull it has, up to the speed the road allows. A pass longer than
        # the driver will stay out there is one that ends on
        # :data:`PASS_LONGEST` with the car across the crown, which is where
        # the next thing coming finds it.
        seconds, _quick = self.planning(session, gap, speed)
        self._planned = seconds
        if seconds > PASS_LONGEST:
            return 'it would take too long'
        across = -self.side(session)
        if not session.lane_clear(across):
            return 'the other lane is occupied'
        if not self.room_in(session, across):
            return 'no room to hold the other lane'
        if not self.room_to_cross(session, gap, speed):
            return 'too close to cross'
        if not self.room_to_finish(session, seconds):
            return ('something is coming' if session.oncoming() is not None
                    else 'cannot see far enough')
        return None

    def planning(self, session: SessionLike, gap: float,
                 speed: float) -> tuple[float, float]:
        """How long getting past that will take, and at what speed, from here.

        Returns ``(seconds, speed the road allows)``. The two come together
        because each decides the other: how fast the car may go decides how
        long the pass takes, and how long it takes decides how much road it
        covers -- and it is the *slowest* the road gets over that stretch that
        the car will actually be doing. Worked out once at the speed of the
        road underfoot and then again over the road the answer reaches, which
        is enough: the second answer moves the first by the length of one
        corner, and a third pass moves it by nothing anybody drives.
        """
        now = float(session.car.speed())
        index, _distance = self.pilot.course.nearest(session.car.position)
        quick = self.pilot.road_speed(index, now)
        seconds = self.pass_seconds(now, gap, speed, quick=quick)
        quick = self.pilot.pace_over(index, seconds * quick)
        return self.pass_seconds(now, gap, speed, quick=quick), quick

    def room_in(self, session: SessionLike, across: float) -> bool:
        """Whether the lane at that offset can be moved into *and held*.

        Not "is there anything within a window": a window is a fixed time only
        at one speed, and twenty-four metres is a second and a half at forty
        km/h and half a second at a hundred and sixty. What decides it is
        whether there is road enough in that lane to shed the speed being
        carried into it and still sit behind whatever is in it.

        ``across`` is metres to the road's own right, so this asks about the
        lane being pulled out into and, afterwards, about the one being
        returned to.
        """
        speed = float(session.car.speed())
        found = session.lane_ahead(across, reach=self.looking(speed))
        if found is None:
            return True
        gap, theirs = found
        losing = max(speed - float(theirs), 0.0)
        braking = max(self.pilot.style.braking, 1e-6)
        return bool(float(gap) > losing * losing / (2.0 * braking) + PASSING_GAP)

    def room_to_cross(self, session: SessionLike, gap: float,
                      speed: float) -> bool:
        """Whether the lane change finishes before the gap in front does.

        A pass begins with seconds spent crossing the crown, and a car closing
        on what it is passing either covers the gap in that time or does not.
        Pulling out with a car length to spare is arriving in the other lane
        after the crash.

        Counting the *acceleration*, because pulling out is flooring it: a
        driver sitting behind something at its own speed is not closing on it
        at all until they do, so measured on the difference the two of them
        have now the gap looks like it will last for ever and the car arrives
        in the other lane after the crash.
        """
        from glisteel.schemes import CROSSING
        crossing = CROSSING * CROSSING_MARGIN
        now = max(float(session.car.speed()) - float(speed), 0.0)
        pull = max(self.pilot.style.pull, 1e-6)
        # What the gap loses while the car is crossing the crown.
        closed = now * crossing + 0.5 * pull * crossing * crossing
        return bool(float(gap) > closed)

    def side(self, session: SessionLike) -> float:
        """Which side of the crown this car keeps to, in metres."""
        return float(getattr(session, 'lane', 0.0)) or self.own_side

    def across(self, session: SessionLike) -> float:
        """How far to the road's own right the car is, in metres."""
        course = self.pilot.course
        at = np.asarray(session.car.position, dtype='d').reshape(-1)[:3]
        index, _distance = course.nearest(at)
        return float(np.dot(at - course.point(index), course.across(index)))

    def worth_passing(self, session: SessionLike) -> bool:
        """Whether what is in front is slow enough to be worth the other lane.

        Against what the **road** allows, not against the speed this car is
        managing: the car in front is the reason that speed is what it is, so
        comparing the two says every car is going as fast as you want to, and
        nothing is ever worth passing.
        """
        found = session.traffic_ahead(self.deciding(session))
        if found is None:
            return False
        _gap, speed = found
        index, _distance = self.pilot.course.nearest(session.car.position)
        wanted = self.pilot.road_speed(index, float(session.car.speed()))
        return bool(speed <= wanted - WORTH_PASSING)

    def pass_seconds(self, speed: float, gap: float, other: float,
                     quick: float | None = None) -> float:
        """How long getting by something in front would take, in seconds.

        The overtaking sum. The relative distance to cover is the gap, the two
        cars' lengths and the room to leave behind; the rate is the difference
        in speed -- and that difference *grows*, because a pass is driven
        rather than coasted. The car pulls at
        :attr:`DriverStyle.pull` until it reaches ``quick``, the speed the road
        allows, and holds it from there.

        Taken at the speed the car happens to be doing, a standing start
        behind something stopped never closes at all: the sum divides by
        nothing and answers half a minute, and a race car that reaches a
        hundred in five seconds is told it is too slow to get by a parked one.

        ``quick`` left out is a car already at the speed it will pass at.
        :data:`PASS_ACROSS` is added for the two lane changes, which happen at
        each end of it.
        """
        room = float(gap) + PASSED_BY + CAR_LENGTHS
        now = float(speed) - float(other)
        top = (now if quick is None else float(quick) - float(other))
        pull = max(self.pilot.style.pull, 1e-6)
        if top <= now:                           # nothing left to gain
            return PASS_ACROSS + room / max(now, 1e-3)
        # Accelerating: cover what can be covered before the speed tops out,
        # and the rest at the difference that is left.
        winding = (top - max(now, 0.0)) / pull
        gained = max(now, 0.0) * winding + 0.5 * pull * winding * winding
        if gained >= room:
            return PASS_ACROSS + (math.sqrt(max(now, 0.0) ** 2
                                            + 2.0 * pull * room)
                                  - max(now, 0.0)) / pull
        return PASS_ACROSS + winding + (room - gained) / max(top, 1e-3)

    def room_to_finish(self, session: SessionLike, seconds: float,
                       margin: float = PASS_MARGIN) -> bool:
        """Whether the road that can be seen covers the rest of the manoeuvre.

        ``seconds`` is how much longer getting past is going to take
        (:meth:`planning`), and the question is whether the road the driver
        can actually see lasts that long at the speed it is being used up --
        the closing speed against whatever might be coming down it.

        Asked before pulling out, and asked again every frame until the car
        draws alongside what it is passing. The two together are what makes
        the manoeuvre survivable: the entitlement to *commit* has to cover
        everything that happens after the commitment, and a check that covered
        only the next second would let a driver commit to five and meet
        whatever the sixth held. While the other car is still in front there is
        always the other way out -- lift off and drop in behind it -- so a pass
        that stops fitting is dropped rather than driven into.

        The bet is still a bet. A road seen to the end of a straight is a road
        clear to the end of the straight, and what comes round the bend after
        it was not there to be seen. The reward is the time; the stake is that
        it appears while the car is committed; and :data:`PASS_MARGIN` is how
        much more road than the sums need this driver wants before it takes
        the bet on.

        Never less than :meth:`getting_back`, whatever the sums say and
        whatever appetite it is asked with: a pass that would be over in a
        moment still needs the room to get back out of it, and that floor is
        not a preference to be traded against. Where nothing comes the other
        way there is nothing to bet against, and what answers instead is the
        lane being clear to move into and hold (:meth:`can_pull_out`).

        ``margin`` scales what the *pass* asks for, and is the appetite the
        question is asked with: :data:`PASS_MARGIN` to begin one and
        :data:`STILL_ON`, which is under 1, to keep one -- see
        :meth:`abandoning`.
        """
        if not session.two_way:
            return True
        needed = max(float(seconds) * float(margin), self.getting_back())
        room, closing = self.seen(session)
        if closing <= 0.0:                       # pragma: no cover - away
            return True
        return bool(room / closing > needed)

    @staticmethod
    def getting_back() -> float:
        """How long giving a pass up takes, in seconds.

        The moment it takes to see that it is not on, and the swerve back. Not
        two of the lane change a pass *begins* with: that one is a decision
        taken at the pace of a decision (:data:`~glisteel.schemes.CROSSING`),
        and a driver abandoning a pass is not being comfortable about it --
        they use what the tyres have (:data:`~glisteel.schemes.LANE_CHANGE_G`).

        The least that has to fit inside the road a driver can see before they
        are entitled to try; see :meth:`room_to_finish`.
        """
        from glisteel.schemes import LANE_CHANGE_G
        lane = LANE_WIDTH
        return THINKING + math.sqrt(2.0 * lane / max(LANE_CHANGE_G, 1e-6))

    def seen(self, session: SessionLike) -> tuple[float, float]:
        """How much road is known clear, and how fast it is used up.

        An empty look-ahead is **not** an empty road: it is a road nobody can
        see the end of, and what a driver has is how far the road lets them
        look (:meth:`~glisteel.session.Session.sight`) divided by the speed
        the two of them would be closing at. Treated as endless, every pass
        looks safe right up until the thing coming the other way arrives --
        out of the very piece of road that was empty a moment ago.

        The road is measured from *here*, over the little of it that getting
        back out of a pass uses. How much has to be seen is the caller's
        question (:meth:`room_to_finish`), and it is asked again every frame:
        a driver part-way past has less of the manoeuvre left and needs less
        of the road, so a requirement carried over the whole stretch at its
        opening value is a requirement no straight is long enough for.
        """
        found = session.oncoming()
        if found is not None:
            return found
        # The least that will be seen while getting back out of a pass, not
        # the most that can be seen from here: a driver who takes the view off
        # the end of a straight pulls out on it and abandons the pass in the
        # bend that follows, over and over, and spends the lap crossing the
        # crown for nothing.
        #
        # The stretch is measured at the speed the *road* allows rather than
        # the speed the car is doing, so that it does not move while the car is
        # on it. Taken from the current speed it grows as the car accelerates,
        # and a pass -- which is an acceleration -- widens its own window,
        # reaches further into the bend with it, and is given up for having
        # been begun.
        speed = float(session.car.speed())
        index, _distance = self.pilot.course.nearest(session.car.position)
        over = self.getting_back()
        settled = self.pilot.pace_over(index, over * speed)
        return (session.sight(over=over * settled),
                speed + traffic.SPEED_LIMIT)


    # -- the keys ---------------------------------------------------------------

    def hold(self, control: str, down: bool) -> None:
        """Hold or let go of one of the controls, as a player\'s hand does."""
        key = KEY_FOR[control]
        if down:
            self.source.press(key)
        else:
            self.source.release(key)


#: What a stand-in follows until it is handed a run. A driver is built from a
#: command line, before there is a world open to say where its road goes.
_NO_COURSE: Any = None
