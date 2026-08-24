"""Other people, using the road.

A circuit with nothing on it is a time trial. What makes it a *road* is that
somebody else is on it, going the speed limit, in both directions -- and that
what they do next is not entirely predictable. A car in front braking for
something its driver can see and the player cannot is the thing that makes
traffic worth overtaking rather than scenery to drive around.

Traffic is placed and driven by **station**: how far along the course it is,
which way it is going, and which side of the centreline it keeps. Everything
about how it moves is that number and a speed, so none of it needs a window --
and it costs a fraction of what a full vehicle simulation each would.

A traffic car is *kinematic*: it drives its own position rather than being
pushed around by contacts. What a player needs from it is that it is there and
that hitting it hurts, and a road full of raycast vehicles buys neither of those
for the four wheels a second of physics each.
"""
from __future__ import annotations

import math
from collections.abc import KeysView
from typing import Any

import numpy as np
from omi_physics import model
from OpenGLContext.scenegraph.transform import Transform

from glisteel import models
from glisteel.geometry import yaw_to_face

__all__ = ['TrafficCar', 'Traffic', 'CRUISING', 'SLOWING', 'PULLING_OFF',
           'DEFAULT_TRAFFIC', 'SPEED_LIMIT', 'MEETING_SECONDS', 'RETIRE',
           'EDGE_BAND',
           'cars_for']

#: What a traffic car is doing. Cruising is the speed limit and its own lane;
#: slowing is something its driver saw and the player did not; pulling off is a
#: turning, a gateway, or somewhere to stop.
CRUISING = 'cruising'
SLOWING = 'slowing'
PULLING_OFF = 'pulling-off'

#: How hard a traffic car accelerates and brakes, in metres per second squared.
#: An ordinary car being driven ordinarily, which is the point of it.
PULL = 2.4
BRAKE = 4.5

#: How much of the limit a slowing car comes down to, and how long it stays
#: there before picking up again, in seconds.
SLOW_TO = 0.35
SLOW_FOR = 6.0

#: How far past the carriageway's own edge a car pulled off sits, in metres,
#: and how long it takes to get there. Onto the verge and no further: the
#: forest starts a metre or so beyond that, and a car parked in it is a car
#: that drove through trees to get there.
OFF_ROAD = 1.6
PULL_OFF_SECONDS = 14.0

#: How often a driver does something, as a chance per second, and how much of
#: that is pulling off rather than braking.
EVENT_RATE = 1.0 / 55.0
PULL_OFF_SHARE = 0.25

#: How far from the player traffic exists, in metres, and how many cars there
#: are inside that. Past it there is nothing to see and nothing to hit.
#:
#: Far enough that a driver can *decide* things: at two hundred against a road
#: posted at eighty, two cars meet at over seventy metres a second, so a pass
#: that takes six seconds needs the better part of half a kilometre of road
#: known to be empty. A shorter reach is a road nobody can overtake on, because
#: nobody can see far enough down it to know.
REACH = 600.0
CARS = 10

#: How much further than the reach a car is followed before it is retired, as
#: a fraction of it. A car just past the edge is a car the player has only
#: this moment driven by, and taking it away there is taking it away in the
#: mirror.
RETIRE = 0.25

#: How wide the band at the edge of the reach is that new cars join in, in
#: metres. Traffic arrives from beyond the end of the road the player has and
#: drives in from there: a car placed anywhere nearer is a car that was not
#: there a moment ago, which is a pop-in to look at and a lie to anyone
#: deciding whether the road ahead is clear. Wide enough to hold a road's
#: worth of traffic at :data:`HEADWAY` apart, since every car alive joins
#: through it.
EDGE_BAND = 560.0

#: How many cars a road carries unless somebody says otherwise.
#:
#: Traffic is what makes a lap different from the last one, and what a racer's
#: lap is *made of*: something to catch and get by every few seconds. The number
#: is chosen from that rather than picked -- see :func:`cars_for`, which turns
#: "one to pass every ten seconds" into a count over the reach. A road with
#: nothing on it is a time trial.
#: The speed a road is driven at when nobody says, in metres per second: a
#: hundred kilometres an hour, which is what an open two-lane road is when it is
#: not being raced.
SPEED_LIMIT = 22.2

MEETING_SECONDS = 10.0

#: How fast the driver those cars are put there for gets round, in m/s.
#:
#: The **average over a lap**, not the speed they see on the straights: what
#: decides how often a racer arrives at somebody else is how quickly they cover
#: the road, and a lap is mostly corners. Aim the count at the top speed
#: instead and the road is sized for a racer nobody can be, so the traffic
#: arrives half as often as it was asked to.
#:
#: Measured rather than chosen, and measured *in traffic*, which is the
#: condition being sized for: a clear lap of the shipped 4 km circuit is
#: 1:34.6 and a lap through this much of it is 1:52.9. The two settle on each
#: other -- this speed asks for that many cars, and that many cars produce this
#: speed.
RACING_SPEED = 120.0 / 3.6


def cars_for(seconds: float = MEETING_SECONDS, racing: float = RACING_SPEED,
             limit: float = SPEED_LIMIT, reach: float = REACH,
             two_way: bool = False) -> int:
    """How many cars put one in front of a racer every ``seconds``.

    A car exists from where it joins the road to where it is retired, and one
    is put out the moment one goes -- so the road is a queue: how many are
    alive at once is how often a new one arrives times how long each lasts. Of
    what arrives, only the cars put out *in front* and going the racer's own
    way are ever passed, so the count is what makes those arrive at the
    asked-for rate with the rest carried alongside them.

    How long one lasts is the road it covers *relative to the racer* divided by
    the speed the two close at: a car put out in front is met and then left
    behind, which is most of the reach twice over; one put out behind only
    falls back to where it is retired. A car coming the other way does all of
    that at the sum of the two speeds rather than the difference, so it is gone
    in a quarter of the time -- which is why a two-way road needs more of them
    on it to be passed as often.

    Written down rather than picked, because the number that makes a good lap
    depends on how fast the racer goes and how fast the road is posted, and one
    chosen for a pair of those numbers is wrong for any other pair.
    """
    reach = float(reach)
    # What a car covers relative to the racer before it is retired: the whole
    # reach in front and the way back out of it, or, for one put out behind,
    # only the road between the reach and where it is retired.
    in_front = reach * (2.0 + RETIRE)
    behind = reach * RETIRE
    catching = max(float(racing) - float(limit), 1e-3)
    meeting = float(racing) + float(limit)
    if not two_way:
        kinds = [(1.0, in_front / catching)]
    else:
        kinds = [(0.25, in_front / catching), (0.25, behind / catching),
                 (0.25, in_front / meeting), (0.25, behind / meeting)]
    passed, alive = kinds[0][0], sum(share * lasts for share, lasts in kinds)
    return max(int(round(alive / passed / max(float(seconds), 1e-3))), 1)


DEFAULT_TRAFFIC = cars_for(two_way=True)

#: How far apart two cars going the same way are placed, at least, in metres.
HEADWAY = 45.0

#: The gap a driver keeps to whatever is in front, in metres, however slowly it
#: is going.
STANDING_GAP = 6.5

#: How wide "in the way" is, in metres: about a car and a half, so something in
#: the other lane is not something you are about to hit. A loose answer here
#: makes every car coming the other way a crash and the road impassable.
IN_THE_WAY = 2.8

#: How far ahead a driver looks for something in its own lane, in metres. Long
#: enough to cover stopping from the limit with room over: a window shorter than
#: the braking distance is a car that notices the queue too late to join it.
LOOK_AHEAD = 130.0

#: How much road is left clear around the player when a car is put out, in
#: metres. A car appearing on top of somebody is not traffic, it is an ambush.
CLEAR_OF_PLAYER = 90.0



class TrafficCar:
    """One car using the road: where it is along it, and what it is doing.

    ``station`` is metres along the course, ``heading`` +1 with the course's
    direction and -1 against it, and ``limit`` the speed it drives at in metres
    per second. ``seed`` decides what this driver does and when, and what kind of
    vehicle it is, so a car behaves and looks the same way every time the same
    world is driven.
    """

    def __init__(self, course: Any, station: float, heading: int,
                 limit: float, seed: int = 0, speed: float | None = None,
                 lane: float | None = None) -> None:
        self.course = course
        self.station = float(station)
        self.heading = 1 if heading >= 0 else -1
        self.limit = float(limit)
        self.seed = int(seed)
        self.speed = self.limit if speed is None else float(speed)
        #: How far this car sits from the centreline, on its own side.
        self.lane = (float(lane) if lane is not None
                     else course.carriageway_width / 4.0)
        self.state = CRUISING
        #: Why this car is slowing, or empty while it is not.
        self.reason = ''
        #: What is in front in this lane, as (gap in metres, its speed), or
        #: None for an open road. Set by :class:`Traffic` each update.
        self.ahead: tuple[float, float] | None = None
        self.paint = _paint(self.seed)
        #: What kind of vehicle this is: its model, and how big it is to hit.
        self.kind = models.TRAFFIC[self.seed % len(models.TRAFFIC)]
        self._rng = np.random.default_rng(self.seed)
        self._until = 0.0
        self._sideways = 0.0
        self._elapsed = 0.0

    def __repr__(self) -> str:
        return 'TrafficCar(%s at %.0fm, %s)' % (
            'with' if self.heading > 0 else 'against', self.station, self.state)

    def target_speed(self) -> float:
        """How fast this car is trying to go, in metres per second.

        Its own intention, held down by whatever is in front of it: no driver
        drives into the back of the car ahead, and a stationary one on the grid
        is something the road behind has to notice.
        """
        if self.state == CRUISING:
            wanted = self.limit
        elif self.state == SLOWING:
            wanted = self.limit * SLOW_TO
        else:
            wanted = 0.0
        return min(wanted, self._room())

    def following(self, gap: float | None, speed: float = 0.0) -> None:
        """Say what is in front: how far, and how fast it is going."""
        self.ahead = None if gap is None else (float(gap), float(speed))

    def _room(self) -> float:
        """The fastest this car may go for what is in front of it.

        The speed it could still stop from in the room it has, plus whatever
        the car in front is doing -- ``v = sqrt(2 a s)``, the braking distance
        read backwards. Not a window with a number in it: a window shorter than
        the stopping distance is a driver who notices the queue too late to
        join it, and one longer is a driver who crawls behind nothing.
        """
        if self.ahead is None:
            return self.limit
        gap, speed = self.ahead
        room = max(gap - STANDING_GAP, 0.0)
        return float(min(self.limit,
                         max(speed, 0.0) + math.sqrt(2.0 * BRAKE * room)))

    def brake_for(self, reason: str = '') -> None:
        """Slow down: the driver has seen something the player has not."""
        self.state = SLOWING
        #: What this driver braked for, for anything asking why a car in front
        #: is slowing -- a read-out, a replay, or a test.
        self.reason = str(reason)
        self._until = self._elapsed + SLOW_FOR

    def pull_off(self) -> None:
        """Leave the carriageway and stop -- a turning, a gate, a lay-by."""
        self.state = PULLING_OFF
        self._until = self._elapsed + PULL_OFF_SECONDS

    def advance(self, dt: float) -> None:
        """Drive for ``dt`` seconds: decide, then accelerate, then move."""
        self._elapsed += dt
        self._decide(dt)
        wanted = self.target_speed()
        rate = PULL if wanted > self.speed else BRAKE
        self.speed += max(-rate * dt, min(rate * dt, wanted - self.speed))
        self.speed = max(self.speed, 0.0)
        # However badly the speed was judged, a car does not drive through the
        # one in front. The rule above eases it in; this is what makes it true.
        step = self.speed * dt
        if self.ahead is not None:
            step = min(step, max(self.ahead[0] - STANDING_GAP, 0.0))
        wanted = self.station + self.heading * step
        self.turn_at_the_end(wanted)
        self.station = self.on_the_road(wanted)
        wanted_side = self._pulled_off() if self.state == PULLING_OFF else 0.0
        self._sideways += max(-dt * 1.2, min(dt * 1.2,
                                             wanted_side - self._sideways))

    def _pulled_off(self) -> float:
        """How much further out than its own side a car pulling off goes.

        :data:`OFF_ROAD` past the carriageway's edge is where it ends up, and
        it is already :attr:`lane` out from the centreline, so what it has left
        to travel is the difference. Added to the lane instead, a car that
        pulled off is standing half its own width past the verge, which on this
        road is inside the trees.
        """
        return max(float(self.course.carriageway_width) / 2.0 + OFF_ROAD
                   - self.lane, 0.0)

    def position(self) -> np.ndarray:
        """Where the car is: on its own side of the road, on the surface.

        The height is the road's own, taken from the centreline at this station
        and dropped by the camber at this distance across
        (:meth:`glisteel.world.Course.surface_offset`). The road knows where
        its surface is everywhere it goes -- through a bore, over a deck, on
        the ground -- so nothing is asked of the physics, which would answer
        about whatever else is standing there and about nothing at all where
        the surface under a car has not been built yet.
        """
        centre, right, _along, lean = self._frame()
        out = self.side()
        at: np.ndarray = centre + right * out
        at[1] += float(self.course.surface_offset(abs(out), lean))
        return at

    def side(self) -> float:
        """How far to the road's own right this car is, in metres.

        Signed in the *road's* frame rather than the car's, so a car coming the
        other way is on the other side of the crown -- which is what somebody
        deciding whether a lane is clear is asking about.
        """
        return float((self.lane + self._sideways) * self.heading)

    def velocity(self) -> np.ndarray:
        """How fast it is going and which way, in metres per second."""
        return self.forward() * self.speed

    def forward(self) -> np.ndarray:
        """Which way it is pointing, as a unit vector.

        The road's own direction, which is level whatever the carriageway is
        doing across itself: a car on a banked corner leans, and it does not
        point up the hill.
        """
        _centre, _across, along, _lean = self._frame()
        pointing: np.ndarray = along * self.heading
        return pointing

    def heading_angle(self) -> float:
        """The yaw that turns the car's own mesh to face the way it is going.

        The mesh's nose is down -Z, and a yaw of ``t`` about the vertical sends
        that to ``(-sin t, 0, -cos t)`` -- so the angle is read off the
        *negated* direction. Taken from the direction itself the car is
        sideways across the road on every axis but one, which is exactly the
        sort of thing one road running the other way finds.
        """
        return yaw_to_face(self.forward())

    def _decide(self, dt: float) -> None:
        """Whether this driver does something, and what."""
        if self.state != CRUISING:
            if self._elapsed >= self._until:
                self.state = CRUISING
                self.reason = ''
            return
        if self._rng.random() < EVENT_RATE * dt:
            if self._rng.random() < PULL_OFF_SHARE:
                self.pull_off()
            else:
                self.brake_for('something in the road')

    def on_the_road(self, station: float) -> float:
        """Where a station actually falls: wrapped on a circuit, held at an end.

        A question, and only a question. Whether the car should *turn round* as
        a result is :meth:`turn_at_the_end`, which is a decision -- and having
        the two in one method meant asking where something was moved the car
        that asked.
        """
        length = float(self.course.length)
        if self.course.closed:
            return float(station % length)
        return float(min(max(station, 0.0), length))

    def turn_at_the_end(self, station: float) -> bool:
        """Turn round if this station is off the end of an open road.

        An open road runs out. Turning round is what a car does when it gets to
        the end of one, and it keeps the road busy either way.
        """
        if self.course.closed or 0.0 <= station <= float(self.course.length):
            return False
        self.heading = -self.heading
        return True

    def _frame(self) -> tuple:
        """Where this car is on the road, as ``(centre, across, along, lean)``.

        The centreline point at its station, the way across the road there, the
        way along it, and how far the road leans -- all four together, because
        everything that places a car needs some of them and finding the station
        is the cost.

        The way across **leans with the road**, so a car on a superelevated
        corner keeps its own side of a carriageway that is not level. Held flat,
        it would hold its distance from the crown in plan and float over the
        outside of every bend or sink into the inside of it.
        """
        line = self.course.centreline
        stations = self.course.stations
        index = int(np.clip(np.searchsorted(stations, self.station) - 1, 0,
                            len(line) - 2))
        span = max(float(stations[index + 1] - stations[index]), 1e-6)
        blend = float(np.clip((self.station - stations[index]) / span, 0.0, 1.0))
        centre = line[index] * (1.0 - blend) + line[index + 1] * blend
        along = line[index + 1] - line[index]
        run = float(np.linalg.norm(along))
        right = np.cross(along, (0.0, 1.0, 0.0))
        length = float(np.linalg.norm(right))
        if length <= 1e-9 or run <= 1e-9:        # pragma: no cover - a repeat
            return (centre, np.array([1.0, 0.0, 0.0]),
                    np.array([0.0, 0.0, -1.0]), 0.0)
        right, along = right / length, along / run
        lean = (self.course.bank_at(index) * (1.0 - blend)
                + self.course.bank_at(index + 1) * blend)
        if not lean:
            return centre, right, along, 0.0
        angle = math.atan(lean)
        across = (math.cos(angle) * right
                  - math.sin(angle) * np.cross(right, along))
        return centre, across, along, lean


class Traffic:
    """The cars using a road near the player, kept topped up as they pass.

    ``count`` is how many exist at once and ``reach`` how far away they are
    allowed to be. A car that falls behind is retired and a new one is put in
    ahead, so a lap meets a road's worth of traffic without a world's worth of
    it ever existing.
    """

    def __init__(self, course: Any, count: int = CARS, reach: float = REACH,
                 limit: float | None = None, seed: int = 0,
                 physics: Any = None, two_way: bool | None = None) -> None:
        self.course = course
        self.count = int(count)
        self.reach = float(reach)
        #: Whether cars come the other way as well. A road has two sides to
        #: it, and a circuit is a road.
        #:
        #: It is what makes passing worth anything: the lane a driver pulls
        #: into is the lane somebody else is coming down, so a pass is a
        #: decision to get right and the time it buys is bought with a risk.
        #: Take the oncoming traffic away and the other lane is just more
        #: road -- there is nothing to come back to your own side for, and a
        #: driver can sit out there for a whole lap.
        self.two_way = True if two_way is None else bool(two_way)
        # What the road is posted at is what the traffic on it does. A road
        # that says nothing gets the default limit.
        posted = float(getattr(course, 'posted', 0) or 0.0)
        self.limit = float(limit) if limit is not None else (
            posted / 3.6 if posted > 0.0 else SPEED_LIMIT)
        self.seed = int(seed)
        self.physics = physics
        #: Every car on the road right now.
        self.cars: list[TrafficCar] = []
        #: What draws them. Mount it once; its children come and go.
        self.node = Transform(children=[])
        self._rng = np.random.default_rng(seed)
        self._next = 0
        self._drawn: dict[TrafficCar, Any] = {}
        self._scenes: dict[TrafficCar, Any] = {}
        self._bodies: dict[TrafficCar, int] = {}
        # Keyed on the car itself rather than on id(car): a car is hashable
        # by identity already, so the two behave the same -- except that an id
        # is reused once its object is collected, and a mapping outliving the
        # thing it describes is a bug that waits for the allocator.
        #: The same mapping read the other way, for anything the physics has
        #: answered about a body index -- what was hit, rather than what to hit.
        self._by_body: dict[int, TrafficCar] = {}
        #: One collider shape per kind, since a van and a hatchback are not the
        #: same thing to run into.
        self._shapes: dict[str, Any] = {}

    def update(self, position: Any, dt: float, speed: float = 0.0) -> None:
        """Drive every car, retire the ones left behind, and put out more.

        ``position`` and ``speed`` are the player's: a car on the road is
        something the traffic behind it has to notice, whether or not it is
        being driven.
        """
        at = np.asarray(position, dtype='d').reshape(-1)[:3]
        # Where the player is on the road, found once. Every car put out this
        # frame joins relative to that same point, and finding a point on a
        # course is a pass over the whole centreline.
        here = self._look_ahead(at, speed)
        for car in self.cars:
            car.advance(dt)
        keeping: list[TrafficCar] = []
        leaving: list[TrafficCar] = []
        for car in self.cars:
            (keeping if float(np.linalg.norm(car.position() - at))
             <= self.reach * (1.0 + RETIRE) else leaving).append(car)
        self.cars = keeping
        for car in leaving:
            self._retire(car)
        while len(self.cars) < self.count:
            fresh = self._spawn(at, here)
            if fresh is None:
                break
            self.cars.append(fresh)
            self._show(fresh)
        self._follow()

    def _look_ahead(self, at: Any, speed: float) -> float:
        """Tell every car what is in front of it in its own lane.

        The player counts: a car sitting on the grid is a car in the road, and
        traffic that drove through it would be traffic nobody could race.

        Answers how far along the road the player is, because finding that is
        the expensive part of this and the rest of the frame wants it too.
        """
        here, side = self._where_is(at)
        mine = float(np.sign(side) or 1.0)
        # Grouped by direction and answered a group at a time. Every car in a
        # group is looking at the same set of stations, so the comparison is one
        # array operation each rather than one Python step per pair of cars --
        # which is what stops a busy road costing the square of what a quiet one
        # does.
        groups: dict[int, list[TrafficCar]] = {}
        for car in self.cars:
            groups.setdefault(car.heading, []).append(car)
        for heading, group in groups.items():
            stations = np.array([one.station for one in group], dtype='d')
            speeds = np.array([one.speed for one in group], dtype='d')
            if mine == float(heading):
                # The player is a car in the road, and traffic that drove
                # through them would be traffic nobody could race.
                stations = np.append(stations, here)
                speeds = np.append(speeds, float(speed))
            for index, car in enumerate(group):
                gaps = self._reaches(car, stations)
                gaps[index] = np.nan             # not itself
                if np.all(np.isnan(gaps)):
                    car.following(None)
                    continue
                nearest = int(np.nanargmin(gaps))
                car.following(float(gaps[nearest]), float(speeds[nearest]))
        return here

    def _reaches(self, car: TrafficCar, stations: Any) -> np.ndarray:
        """How far in front of ``car`` each station is; NaN for anything behind.

        The array form of :meth:`_reach`, which is what a group of cars on one
        side of the road is answered with in one go.
        """
        gaps = (np.asarray(stations, dtype='d') - car.station) * car.heading
        if self.course.closed:
            length = self.course.length
            gaps = np.mod(gaps, length)
            gaps = np.where(gaps > length / 2.0, gaps - length, gaps)
        return np.where((gaps > 0.0) & (gaps <= LOOK_AHEAD), gaps, np.nan)

    def _reach(self, car: TrafficCar, station: float) -> float | None:
        """How far in front of ``car`` a station is, or None if it is behind."""
        found = float(self._reaches(car, [station])[0])
        return None if np.isnan(found) else found

    def _where_is(self, at: Any) -> tuple[float, float]:
        """How far along the road something is, and which side of it it is on.

        One question rather than two: both answers come from the same nearest
        point of the centreline, and finding that is a pass over the whole line.
        """
        point = np.asarray(at, dtype='d')[:3]
        index, _distance = self.course.nearest(point)
        stations = self.course.stations
        station = float(stations[int(np.clip(index, 0, len(stations) - 1))])
        offset = point - self.course.point(index)
        return station, float(np.dot(offset, self.course.across(index)))

    def body_of(self, car: TrafficCar) -> int:
        """The physics body driving along under one car."""
        return self._bodies[car]

    def car_of(self, body: int) -> TrafficCar | None:
        """Which car a physics body belongs to, or None for anything else.

        What the physics answers with is a body index, so this is how a caller
        turns "something was hit" into "which car" -- and None is the ordinary
        answer for the road, a bank or a bridge parapet.
        """
        return self._by_body.get(int(body))

    @property
    def bodies(self) -> KeysView[int]:
        """The physics bodies these cars are, for asking the world about them.

        A set to test membership against, which is how a question about the
        traffic is put to something that knows only body indices.
        """
        return self._by_body.keys()

    def put_out(self, car: TrafficCar) -> TrafficCar:
        """Put a car the caller made themselves on the road, and return it.

        The cars this manages are its own -- where they are, what kind and how
        many is what makes a road feel used, and none of it is anybody else's
        business. A set piece is: a scenario that wants a lorry on the crest of
        a hill, or a test that wants one particular vehicle in one particular
        place. Such a car is drawn and given a collider exactly as a spawned
        one is, and is retired by the same rules once it is left behind.
        """
        self.cars.append(car)
        self._show(car)
        return car

    def halt(self) -> None:
        """Stop every car where it stands, and leave it there.

        For a caller that has stopped driving this: the cars keep their bodies
        and their colliders, and those bodies carry a velocity, so a manager
        left un-driven would go on integrating them down a road nobody is
        putting them on -- an invisible car half a street from the one being
        drawn. Idempotent, and undone by the next :meth:`update`.
        """
        if self.physics is None:
            return
        for body in self._by_body:
            self.physics.linear_velocity[body] = 0.0

    def release(self) -> None:
        """Take every car off the road."""
        for car in list(self.cars):
            self._retire(car)
        self.cars = []

    def _show(self, car: TrafficCar) -> None:
        """Give a new car something to draw and something to hit.

        Its own copy of its kind's model, because it is repainted: a road full
        of one colour is a convoy. The collider is the kind's own dimensions, so
        a van is as big to hit as it is to see.
        """
        node = self._art(car)
        self._drawn[car] = node
        self.node.children = list(self.node.children) + [node]
        if self.physics is None:
            return
        shape = self._shapes.get(car.kind.name)
        if shape is None:
            shape = self.physics.add_shape(model.Shape.box(car.kind.size()))
            self._shapes[car.kind.name] = shape
        body = int(self.physics.add_body(
            model.Motion(type=model.KINEMATIC, mass=1200.0),
            collider=model.Collider(shape=shape),
            position=tuple(self._centre(car))))
        self._bodies[car] = body
        self._by_body[body] = car

    def _art(self, car: TrafficCar) -> Any:
        """One vehicle to look at, painted in this car's own colour.

        Only the paint moves: the glass, the bright trim and what is inside are
        the model's own, and repainting those would cost the car its windows.

        **One scene per kind and colour, not per car.** The paint comes from a
        fixed palette, so a road's worth of traffic is a handful of versions of
        five models however many cars are on it: each is read and painted once
        and then mounted wherever it is needed, which keeps a car appearing off
        the frame it appears on and lets the renderer draw every saloon of one
        colour in a single batch.
        """
        scene = models.ART.variant(car.kind.model, car.paint,
                                   prepare=lambda one: _repaint(one, car.paint))
        if scene is not None:
            self._scenes[car] = scene
            return Transform(children=[scene.group])
        from glisteel.car import BODY_HEIGHT, car_nodes
        # Without a model, the primitive car -- which is drawn about its own
        # middle, where a vehicle model stands on its wheels.
        return Transform(children=[Transform(
            children=[car_nodes(car.paint)],
            translation=(0.0, BODY_HEIGHT / 2.0 + 0.33, 0.0))])

    def art_of(self, car: TrafficCar) -> Any:
        """The loaded scene one car is drawn from, for anything asking about it."""
        return self._scenes.get(car)

    def node_of(self, car: TrafficCar) -> Any:
        """What draws one car."""
        return self._drawn.get(car)

    def collider_size(self, car: TrafficCar) -> tuple[float, float, float]:
        """How big this car is to hit, in metres."""
        return car.kind.size()

    def _retire(self, car: TrafficCar) -> None:
        self._scenes.pop(car, None)
        node = self._drawn.pop(car, None)
        if node is not None:
            self.node.children = [one for one in self.node.children
                                  if one is not node]
        body = self._bodies.pop(car, None)
        if body is not None:
            self._by_body.pop(body, None)
            if self.physics is not None:
                self.physics.remove_body(body)

    def _follow(self) -> None:
        """Put every car's node and body where the car now is, and how fast.

        The **velocity** as well as the pose, because a kinematic body without
        one is a wall: the solver resolves against the difference between two
        bodies' velocities, so a car doing thirty that is written down as still
        both throws the player off like a parked one and reads as having been
        hit at thirty by anybody who merely caught up with it. It is also what
        carries a car along between the frames this runs on -- the physics
        steps several times to each of them, and a pose written once a frame
        would otherwise stand still for all but the first.
        """
        for car in self.cars:
            at = self._standing(car)
            node = self._drawn.get(car)
            if node is not None:
                node.translation = tuple(float(v) for v in at)
                node.rotation = (0.0, 1.0, 0.0, car.heading_angle())
            body = self._bodies.get(car)
            if body is not None and self.physics is not None:
                self.physics.place_body(body, self._centre(car, at),
                                        _yaw(car.heading_angle()))
                self.physics.linear_velocity[body] = car.velocity()

    def _standing(self, car: TrafficCar) -> np.ndarray:
        """Where a car meets the road: its own position, on the surface."""
        return np.asarray(car.position(), dtype='d')

    def _centre(self, car: TrafficCar, at: Any = None) -> np.ndarray:
        """Where the middle of a car is: half its own height off the road.

        ``at`` is where its wheels are, for a caller that has already worked
        that out.
        """
        found = (self._standing(car) if at is None
                 else np.asarray(at, dtype='d')).copy()
        found[1] += car.kind.height / 2.0
        return found

    def around(self, position: Any, forward: Any, ahead: float = REACH,
               behind: float = 0.0, width: float = IN_THE_WAY
               ) -> list[tuple[float, TrafficCar]]:
        """The cars near something, each with how far along the road it is.

        The gap is positive in front and negative behind, measured **along the
        road** rather than along the line the nose points down -- see
        :meth:`ahead_of` for why that distinction matters. ``ahead`` and
        ``behind`` are how far to look each way, and ``width`` is how far across
        the road still counts. Nearest first, whichever side it is on.
        """
        way = np.asarray(forward, dtype='d').reshape(-1)[:3]
        if float(np.linalg.norm(way)) < 1e-9:    # pragma: no cover - no heading
            return []
        at = np.asarray(position, dtype='d').reshape(-1)[:3]
        index, _distance = self.course.nearest(at)
        stations = self.course.stations
        here = float(stations[int(np.clip(index, 0, len(stations) - 1))])
        offset = at - self.course.point(index)
        mine = float(np.dot(offset, self.course.across(index)))
        # Which way this is facing along the road, so somebody turned round is
        # not told the road behind them is the road in front.
        heading = 1.0 if float(np.dot(way, self.course.point(index + 1)
                                      - self.course.point(index))) >= 0.0 else -1.0
        found = []
        for car in self.cars:
            gap = (car.station - here) * heading
            if self.course.closed:
                gap = math.remainder(gap, self.course.length)
            if -float(behind) <= gap <= float(ahead) and abs(car.side() - mine) < width:
                found.append((gap, car))
        return sorted(found, key=lambda one: abs(one[0]))

    def ahead_of(self, position: Any, forward: Any, reach: float = REACH,
                 width: float = IN_THE_WAY) -> list[TrafficCar]:
        """The cars in front of something looking that way, nearest first.

        What an autopilot or a driving aid asks: not "what is near" but "what
        am I about to arrive at". ``width`` is how far across the road still
        counts -- a car's width by default, so the other lane does not; a
        driver deciding whether it has room to swerve asks for the whole road.

        **Along the road**, not along the line the nose points down. A straight
        line from the nose leaves the road at the first bend, so a car a couple
        of hundred metres up a curving road is off that line and reads as
        nothing in front -- until the bend swings it onto the line all at once,
        inside braking distance. A driver looking at a road sees what is on the
        road, and this is what a driver would be told.
        """
        near = self.around(position, forward, ahead=reach, behind=0.0,
                           width=width)
        return [car for gap, car in near if gap > 0.0]

    def _spawn(self, at: Any, here: float | None = None) -> TrafficCar | None:
        """A new car at the edge of the reach, on a side with room for it.

        ``here`` is how far along the road the player is, for a caller that
        has already worked it out -- which the frame has, and which costs a
        search over the whole centreline to find again.
        """
        here = self._station_of(at) if here is None else float(here)
        for _try in range(12):
            heading = 1 if not self.two_way or self._rng.random() < 0.5 else -1
            # In through the band at the edge of the reach, which is the one
            # place a car can arrive without anybody watching it arrive.
            edge = self.reach - float(self._rng.uniform(0.0, EDGE_BAND))
            # Behind only where something might come *from* behind. Traffic
            # going the racer's own way and slower than them is caught by
            # being driven up to, so one put behind is one met a whole lap
            # later -- a car spent on nothing. What comes the other way is
            # met wherever it starts.
            behind = ((self.two_way or heading < 0)
                      and self._rng.random() < 0.5)
            offset = -edge if behind else edge
            station = here + offset
            if not self.course.closed:
                station = min(max(station, 0.0), self.course.length)
            else:
                station %= self.course.length
            if self._gap(here, station) < CLEAR_OF_PLAYER:
                continue
            if any(car.heading == heading
                   and self._gap(car.station, station) < HEADWAY
                   for car in self.cars):
                continue
            self._next += 1
            return TrafficCar(
                self.course, station=station, heading=heading,
                limit=self.limit * float(self._rng.uniform(0.85, 1.05)),
                seed=self.seed * 1000 + self._next)
        return None

    def _gap(self, one: float, other: float) -> float:
        """How far apart two stations are, the short way round a circuit."""
        gap = abs(one - other)
        if self.course.closed:
            gap = min(gap, self.course.length - gap)
        return gap

    def _station_of(self, at: Any) -> float:
        """How far along the road something is, in metres."""
        return self._where_is(at)[0]





def _yaw(angle: float) -> tuple:
    """A rotation about the vertical, as the quaternion a body wants."""
    half = float(angle) / 2.0
    return (0.0, float(np.sin(half)), 0.0, float(np.cos(half)))


def _repaint(scene: Any, colour: tuple) -> None:
    """Put one colour on a vehicle's bodywork and leave the rest of it alone."""
    paint = scene.materials.get(models.PAINT)
    if paint is not None:
        paint.baseColor = colour


def _paint(seed: int) -> tuple:
    """A colour for one car, so a road is not a convoy of one model."""
    colours = ((0.72, 0.72, 0.74), (0.16, 0.18, 0.22), (0.35, 0.12, 0.11),
               (0.13, 0.24, 0.38), (0.58, 0.55, 0.48), (0.20, 0.32, 0.22))
    return colours[seed % len(colours)]
