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
from typing import Any

import numpy as np
from omi_physics import model
from OpenGLContext.scenegraph.transform import Transform

__all__ = ['TrafficCar', 'Traffic', 'CRUISING', 'SLOWING', 'PULLING_OFF']

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

#: How far off the centreline a car pulled off sits, in metres past the
#: carriageway's own edge, and how long it takes to get there.
OFF_ROAD = 1.6
PULL_OFF_SECONDS = 14.0

#: How often a driver does something, as a chance per second, and how much of
#: that is pulling off rather than braking.
EVENT_RATE = 1.0 / 55.0
PULL_OFF_SHARE = 0.25

#: How far from the player traffic exists, in metres, and how many cars there
#: are inside that. Past it there is nothing to see and nothing to hit.
REACH = 320.0
CARS = 10

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
    per second. ``seed`` decides what this driver does and when, so a car
    behaves the same way every time the same world is driven.
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
        #: What is in front in this lane, as (gap in metres, its speed), or
        #: None for an open road. Set by :class:`Traffic` each update.
        self.ahead: tuple[float, float] | None = None
        self.paint = _paint(self.seed)
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
        self.station = self._along(self.station + self.heading * step)
        wanted_side = (self.course.carriageway_width / 2.0 + OFF_ROAD
                       if self.state == PULLING_OFF else 0.0)
        self._sideways += max(-dt * 1.2, min(dt * 1.2,
                                             wanted_side - self._sideways))

    def position(self) -> np.ndarray:
        """Where the car is: on its own side of the road, on the surface."""
        centre, right = self._frame()
        out = self.lane * self.heading + self._sideways * self.heading
        return centre + right * out

    def velocity(self) -> np.ndarray:
        """How fast it is going and which way, in metres per second."""
        return self.forward() * self.speed

    def forward(self) -> np.ndarray:
        """Which way it is pointing, as a unit vector."""
        _centre, right = self._frame()
        along = np.cross((0.0, 1.0, 0.0), right)
        length = float(np.linalg.norm(along))
        along = along / length if length > 1e-9 else np.array([0.0, 0.0, -1.0])
        return along * self.heading

    def heading_angle(self) -> float:
        """The yaw that turns the car's own mesh to face the way it is going.

        The mesh's nose is down -Z, and a yaw of ``t`` about the vertical sends
        that to ``(-sin t, 0, -cos t)`` -- so the angle is read off the
        *negated* direction. Taken from the direction itself the car is
        sideways across the road on every axis but one, which is exactly the
        sort of thing one road running the other way finds.
        """
        forward = self.forward()
        return math.atan2(-float(forward[0]), -float(forward[2]))

    def _decide(self, dt: float) -> None:
        """Whether this driver does something, and what."""
        if self.state != CRUISING:
            if self._elapsed >= self._until:
                self.state = CRUISING
            return
        if self._rng.random() < EVENT_RATE * dt:
            if self._rng.random() < PULL_OFF_SHARE:
                self.pull_off()
            else:
                self.brake_for('something in the road')

    def _along(self, station: float) -> float:
        """A station kept on the road: wrapped on a circuit, turned at an end."""
        length = float(self.course.length)
        if self.course.closed:
            return float(station % length)
        if station > length or station < 0.0:
            # An open road runs out. Turning round is what a car does when it
            # gets to the end of one, and it keeps the road busy either way.
            self.heading = -self.heading
            return float(min(max(station, 0.0), length))
        return float(station)

    def _frame(self) -> tuple:
        """The centreline point at this station, and the way across the road."""
        line = self.course.centreline
        stations = self.course.stations
        index = int(np.clip(np.searchsorted(stations, self.station) - 1, 0,
                            len(line) - 2))
        span = max(float(stations[index + 1] - stations[index]), 1e-6)
        blend = float(np.clip((self.station - stations[index]) / span, 0.0, 1.0))
        centre = line[index] * (1.0 - blend) + line[index + 1] * blend
        along = line[index + 1] - line[index]
        right = np.cross(along, (0.0, 1.0, 0.0))
        length = float(np.linalg.norm(right))
        return centre, (right / length if length > 1e-9
                        else np.array([1.0, 0.0, 0.0]))


class Traffic:
    """The cars using a road near the player, kept topped up as they pass.

    ``count`` is how many exist at once and ``reach`` how far away they are
    allowed to be. A car that falls behind is retired and a new one is put in
    ahead, so a lap meets a road's worth of traffic without a world's worth of
    it ever existing.
    """

    def __init__(self, course: Any, count: int = CARS, reach: float = REACH,
                 limit: float | None = None, seed: int = 0,
                 physics: Any = None, ground: Any = None) -> None:
        self.course = course
        self.count = int(count)
        self.reach = float(reach)
        self.limit = float(limit) if limit is not None else _limit(course)
        self.seed = int(seed)
        self.physics = physics
        #: The ground a car sits on, ``ground(position) -> height or None``;
        #: without it a car rides the centreline's own height, which is the
        #: road's -- right wherever the road is on the ground.
        self.ground = ground
        #: Every car on the road right now.
        self.cars: list[TrafficCar] = []
        #: What draws them. Mount it once; its children come and go.
        self.node = Transform(children=[])
        self._rng = np.random.default_rng(seed)
        self._next = 0
        self._drawn: dict[int, Any] = {}
        self._bodies: dict[int, int] = {}
        self._shape: Any = None

    def update(self, position: Any, dt: float, speed: float = 0.0) -> None:
        """Drive every car, retire the ones left behind, and put out more.

        ``position`` and ``speed`` are the player's: a car on the road is
        something the traffic behind it has to notice, whether or not it is
        being driven.
        """
        at = np.asarray(position, dtype='d').reshape(-1)[:3]
        self._look_ahead(at, speed)
        for car in self.cars:
            car.advance(dt)
        keeping, leaving = [], []
        for car in self.cars:
            (keeping if float(np.linalg.norm(car.position() - at))
             <= self.reach * 1.25 else leaving).append(car)
        self.cars = keeping
        for car in leaving:
            self._retire(car)
        while len(self.cars) < self.count:
            car = self._spawn(at)
            if car is None:
                break
            self.cars.append(car)
            self._show(car)
        self._follow()

    def _look_ahead(self, at: Any, speed: float) -> None:
        """Tell every car what is in front of it in its own lane.

        The player counts: a car sitting on the grid is a car in the road, and
        traffic that drove through it would be traffic nobody could race.
        """
        here = self._station_of(at)
        mine = float(np.sign(self._offset_of(at)) or 1.0)
        for car in self.cars:
            found = None
            for other in self.cars:
                if other is car or other.heading != car.heading:
                    continue
                gap = self._reach(car, other.station)
                if gap is not None and (found is None or gap < found[0]):
                    found = (gap, other.speed)
            if mine == float(car.heading):
                gap = self._reach(car, here)
                if gap is not None and (found is None or gap < found[0]):
                    found = (gap, float(speed))
            car.following(*(found if found is not None else (None, 0.0)))

    def _reach(self, car: TrafficCar, station: float) -> float | None:
        """How far in front of ``car`` a station is, or None if it is behind."""
        gap = (station - car.station) * car.heading
        if self.course.closed:
            gap %= self.course.length
            if gap > self.course.length / 2.0:
                gap -= self.course.length
        return gap if 0.0 < gap <= LOOK_AHEAD else None

    def _offset_of(self, at: Any) -> float:
        """Which side of the centreline something is on, and how far."""
        index, _distance = self.course.nearest(at)
        offset = np.asarray(at, dtype='d')[:3] - self.course.point(index)
        return float(np.dot(offset, self.course.across(index)))

    def body_of(self, car: TrafficCar) -> int:
        """The physics body driving along under one car."""
        return self._bodies[id(car)]

    def release(self) -> None:
        """Take every car off the road."""
        for car in list(self.cars):
            self._retire(car)
        self.cars = []

    def _show(self, car: TrafficCar) -> None:
        """Give a new car something to draw and something to hit."""
        from glisteel.car import BODY_HEIGHT, car_nodes
        node = car_nodes(car.paint)
        self._drawn[id(car)] = node
        self.node.children = list(self.node.children) + [node]
        if self.physics is None:
            return
        if self._shape is None:
            from glisteel.car import BODY_LENGTH, BODY_WIDTH
            self._shape = self.physics.add_shape(model.Shape.box(
                (BODY_WIDTH, BODY_HEIGHT + 0.3, BODY_LENGTH)))
        self._bodies[id(car)] = int(self.physics.add_body(
            model.Motion(type=model.KINEMATIC, mass=1200.0),
            collider=model.Collider(shape=self._shape),
            position=tuple(self._standing(car))))

    def _retire(self, car: TrafficCar) -> None:
        node = self._drawn.pop(id(car), None)
        if node is not None:
            self.node.children = [one for one in self.node.children
                                  if one is not node]
        body = self._bodies.pop(id(car), None)
        if body is not None and self.physics is not None:
            self.physics.remove_body(body)

    def _follow(self) -> None:
        """Put every car's node and body where the car now is."""
        for car in self.cars:
            at = self._standing(car)
            node = self._drawn.get(id(car))
            if node is not None:
                node.translation = tuple(float(v) for v in at)
                node.rotation = (0.0, 1.0, 0.0, car.heading_angle())
            body = self._bodies.get(id(car))
            if body is not None and self.physics is not None:
                self.physics.position[body] = at
                self.physics.orientation[body] = _yaw(car.heading_angle())

    def _standing(self, car: TrafficCar) -> np.ndarray:
        """Where a car's body centre is: on the road, up off it by its own half."""
        from glisteel.car import BODY_HEIGHT
        at = np.asarray(car.position(), dtype='d').copy()
        if self.ground is not None:
            found = self.ground(at)
            if found is not None:
                at[1] = float(found)
        at[1] += BODY_HEIGHT / 2.0 + 0.33
        return at

    def ahead_of(self, position: Any, forward: Any, reach: float = REACH,
                 width: float = IN_THE_WAY) -> list[TrafficCar]:
        """The cars in front of something looking that way, nearest first.

        What an autopilot or a driving aid asks: not "what is near" but "what am
        I about to arrive at". ``width`` is how far to either side still counts
        -- a car's width by default, so the other lane does not; a driver
        deciding whether it has room to swerve asks for the whole road.
        """
        at = np.asarray(position, dtype='d').reshape(-1)[:3]
        way = np.asarray(forward, dtype='d').reshape(-1)[:3]
        length = float(np.linalg.norm(way))
        if length < 1e-9:                        # pragma: no cover - no heading
            return []
        way = way / length
        found = []
        for car in self.cars:
            offset = car.position() - at
            along = float(np.dot(offset, way))
            aside = float(np.linalg.norm(offset - way * along))
            if 0.0 < along <= reach and aside < width:
                found.append((along, car))
        return [car for _along, car in sorted(found, key=lambda one: one[0])]

    def _spawn(self, at: Any) -> TrafficCar | None:
        """A new car somewhere within reach, on a side with room for it."""
        here = self._station_of(at)
        for _try in range(12):
            heading = 1 if self._rng.random() < 0.5 else -1
            offset = float(self._rng.uniform(-self.reach, self.reach))
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
        index, _offset = self.course.nearest(at)
        stations = self.course.stations
        return float(stations[int(np.clip(index, 0, len(stations) - 1))])


def _limit(course: Any) -> float:
    """The speed a road is driven at when nobody says, in metres per second.

    A hundred kilometres an hour on an open two-lane road, which is what the
    shipped circuit is when it is not being raced.
    """
    return 27.8


def _yaw(angle: float) -> tuple:
    """A rotation about the vertical, as the quaternion a body wants."""
    half = float(angle) / 2.0
    return (0.0, float(np.sin(half)), 0.0, float(np.cos(half)))


def _paint(seed: int) -> tuple:
    """A colour for one car, so a road is not a convoy of one model."""
    colours = ((0.72, 0.72, 0.74), (0.16, 0.18, 0.22), (0.35, 0.12, 0.11),
               (0.13, 0.24, 0.38), (0.58, 0.55, 0.48), (0.20, 0.32, 0.22))
    return colours[seed % len(colours)]
