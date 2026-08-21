"""Ways of driving the car, and the switch between them.

A key on a keyboard says one thing: it is down, or it is not. What the game
makes of that is a decision, and today's decision -- the key is the **steering
lock** -- is the hardest one to drive by, because where the car ends up across
the road is then the key integrated twice, once into a heading and once into a
position. A driver closing that loop is doing it by eye at forty metres a second
on a road seven metres wide.

A scheme is that decision, written down and swappable:

    >>> from glisteel import schemes
    >>> schemes.available()
    ('wheel', 'loose', 'line', 'lanes', 'chauffeur')
    >>> schemes.named('line').summary
    'the wheel places the car across the road, and the road is held for you'

Three parts, kept apart, and this module is the middle one:

* the **source** is where the number comes from -- a key pair that winds a
  wheel, or the pointer's place across the window
  (:mod:`glisteel.steering`). It knows nothing about roads;
* the **scheme** is what that number *means* -- a lock, a place across the road,
  a lane;
* the **aid** is what the game adds on top (:mod:`glisteel.assist`), and each
  scheme says what it needs of it.

Because the source is separate, ``--mouse`` is available under every scheme
rather than being one of its own, and the window presses keys on
``scheme.source`` without knowing or caring which scheme is on.

**These are experiments.** The point of the switch is that the same drive can be
run under each of them and measured (:mod:`glisteel.trace`,
`plans/CONTROL-SCHEMES.md`); which of them the game finally offers is a decision
for the numbers, and a scheme here is a candidate rather than a commitment.

A scheme is a :class:`~glisteel.session.Controller`, so a session neither knows
nor cares which is driving; it takes the run it is handed on the first step it is
asked for, which is what sets the aid to what the scheme needs.
"""
from __future__ import annotations

import math
from typing import Any

from glisteel.driver import Autopilot
from glisteel.steering import KeyboardDriver, MouseWheel
from glisteel.zone import DrivableZone

__all__ = ['CROSSING', 'DEFAULT', 'HANDBACK', 'LANE_CHANGE_G',
           'LANE_CHANGE_LONGEST', 'LANE_CHANGE_QUICKEST',
           'LANE_CHANGE_SHARE', 'SCHEMES',
           'Chauffeur', 'ControlScheme', 'Lanes', 'Line', 'Loose', 'Wheel',
           'available', 'named']

#: How fast a scheme that steers by *position* moves the car across the road at
#: full ask, in metres per second. A lane is 3.6 m, so this is a lane change in
#: something over a second, which is what one is: quick enough to be a decision
#: the driver makes and slow enough to be a manoeuvre rather than a jump.
CROSSING = 3.0

#: How hard a lane change pushes the car sideways at its hardest, in metres per
#: second squared. A fifth of a g: what a driver changing lanes on an open road
#: puts in, and far enough inside what the tyres have that the change costs
#: nothing a corner might have wanted.
LANE_CHANGE_G = 2.0

#: How much of what the front wheels could ask for at this speed a lane change
#: will use. The rest is left for holding the new lane and for whatever the road
#: is doing while the car crosses it.
LANE_CHANGE_SHARE = 0.5

#: How long a lane change may take, in seconds, however slowly the car is going.
#: A car barely moving cannot be turned sideways quickly whatever the wheel
#: does, and the manoeuvre is over when the car gets there.
LANE_CHANGE_LONGEST = 8.0

#: And the least it may take, so a car with grip to spare still changes lanes at
#: the pace of a decision rather than of a flinch.
LANE_CHANGE_QUICKEST = 1.2

#: How long the chauffeur waits, with nothing being asked of it, before taking
#: the car back, in seconds.
HANDBACK = 2.0

#: How long a lane the driver asked for is held as asked-for while there is
#: something in it, in seconds. Long enough to cover lifting off and dropping
#: in behind a car -- which is what the driver is doing while it waits -- and
#: short enough that a press nobody remembers making does not take the car
#: across the road a minute later.
QUEUED_FOR = 6.0


class ControlScheme:
    """One way of driving: a source of input, and what it is taken to mean.

    ``source`` is what the window presses keys on, and a fresh
    :class:`~glisteel.steering.KeyboardDriver` is made where none is given;
    ``pointer`` steers with the mouse under any scheme. ``trim`` is how much of
    the line aid the player asked for, and None leaves the run with whatever it
    was built with -- which is what a run set up with ``--assist`` already has.
    A scheme with its own need of the aid (:attr:`fixed_trim`) overrides both.
    """

    #: What the scheme is called on the command line and in the settings.
    name = ''
    #: One line, for ``--help`` and for a menu.
    summary = ''
    #: What this scheme needs of the line aid whatever the player asked for, or
    #: None where what they asked for is what they get.
    fixed_trim: float | None = None

    #: Whether this way of driving holds the car on a line for the driver, so
    #: what they are choosing is where the car sits on the road rather than how
    #: far its wheels are turned. It is what decides whether a drive by
    #: something other than a person goes *through* the controls
    #: (:class:`~glisteel.driver.StandIn`) or past them: an autopilot pressing a
    #: key to wind a wheel it could turn directly is a worse driver rather than
    #: a truer one.
    holds_the_line = False

    #: Whether the run reads the road ahead for this driver and says when they
    #: are arriving at a corner too fast. What the signs beside the road say
    #: already, for a driver whose hands are not the ones steering and who is
    #: therefore reading the road rather than fighting it.
    advises = False

    def __init__(self, source: KeyboardDriver | None = None,
                 pointer: MouseWheel | None = None,
                 trim: float | None = None) -> None:
        #: The keys and the pointer, which the window fills.
        self.source = source if source is not None else KeyboardDriver(pointer)
        #: What the line aid is set to when this scheme takes a run, or None to
        #: leave the run's own.
        self.trim = (self.fixed_trim if self.fixed_trim is not None
                     else None if trim is None else float(trim))
        self._session: Any = None

    def __repr__(self) -> str:
        return '%s(trim=%s)' % (
            type(self).__name__,
            'as the run has it' if self.trim is None else '%.2f' % self.trim)

    def controls(self, session: Any, dt: float) -> tuple[float, float, float]:
        """The pedals and the wheel this scheme asks for, once a physics step.

        The run is taken on the first step it is asked about rather than when
        the scheme is built: a scheme is chosen from a command line before there
        is a world open, and it can be handed a different run later without
        being rebuilt.
        """
        if session is not self._session:
            self._session = session
            self.enter(session)
        return self.drive(session, dt)

    def enter(self, session: Any) -> None:
        """Take this run: set the aid to what this way of driving needs.

        A scheme with nothing to say about the aid leaves it alone, because the
        run was already built with the strength the player asked for and a
        second default here would quietly replace it.
        """
        if self.trim is not None:
            session.assist.strength = self.trim

    def drive(self, session: Any, dt: float) -> tuple[float, float, float]:
        """What reaches the car. Each scheme's own."""
        raise NotImplementedError                # pragma: no cover - a base


class Wheel(ControlScheme):
    """The steering is the front wheels, and the aid trims the line.

    What the game ships: the keys wind a wheel toward full lock and the aid
    holds whatever line the car is left on between deliberate inputs. The
    difficulty is ``--assist``, which is how much of that trim is put in.
    """

    name = 'wheel'
    summary = 'the wheel is the front wheels, and the aid trims between inputs'

    def drive(self, session: Any, dt: float) -> tuple[float, float, float]:
        return self.source.controls(session, dt)


class Loose(Wheel):
    """The same, with nothing helping: the car as the physics has it."""

    name = 'loose'
    summary = 'the wheel is the front wheels, and nothing is put in for you'
    fixed_trim = 0.0


class Line(ControlScheme):
    """The steering is where the car sits across the road.

    Full left is *cross to the left*, and letting go is *stay here* -- so a tap
    is a step across the road rather than a permanent change of direction, and
    the car is placed where the driver means rather than pointed and corrected.
    The aid does the steering, at all of its strength, to the line this scheme
    keeps moving; what the driver is doing is choosing that line.

    The width it may be moved across is the carriageway's
    (:class:`~glisteel.zone.DrivableZone`), so a road with four lanes has four
    lanes' worth of room and a narrow one has what it has.
    """

    name = 'line'
    summary = ('the wheel places the car across the road, and the road is held '
               'for you')
    fixed_trim = 1.0
    holds_the_line = True

    def __init__(self, *args: Any, **named: Any) -> None:
        super().__init__(*args, **named)
        #: How wide the road is and where its lanes are, once there is a run.
        self.zone = DrivableZone(width=0.0)

    def enter(self, session: Any) -> None:
        super().enter(session)
        self.zone = DrivableZone.of(session.course)

    def held_line(self, session: Any) -> float:
        """The line to move from: the one being held, or the car's own.

        The aid lets go of its line whenever the car is picked up and put down
        again -- a restart, or being put back on the road -- and what was being
        held then is a line on a road the car is no longer on. Taking the car's
        own line in that case, and forgetting anything in progress
        (:meth:`replaced`), is what stops a restart setting off towards where
        the last lap was being driven.
        """
        assist = session.assist
        if not assist.hands_on:
            return float(assist.line)
        self.replaced()
        return float(assist.line_under(session.car))

    def replaced(self) -> None:
        """The car is somewhere else now: forget any manoeuvre in progress."""

    def drive(self, session: Any, dt: float) -> tuple[float, float, float]:
        throttle, brake = self.source.pedals(session)
        self.place(session, self.moved(self.held_line(session),
                                       self.source.axis(), dt))
        # Nothing for the wheel: the aid is holding the line this scheme just
        # put it on, which is the whole of the steering under this scheme.
        return throttle, brake, 0.0

    def moved(self, line: float, axis: float, dt: float) -> float:
        """Where the line goes, given what the driver is asking for.

        A positive axis is a request to go *left*, and offsets across a road are
        measured to its own right, so the one turns into the other by a sign.
        """
        return line - float(axis) * CROSSING * float(dt)

    def place(self, session: Any, line: float) -> None:
        """Hold that line, brought onto the road if it is not already on it."""
        session.assist.hold(self.zone.clamp(line))


class Lanes(Line):
    """The steering asks for the lane over, and the car takes it.

    A press is *the next lane to your left*, or right; the steering takes the
    car there and holds it, through the bends, until it is asked for something
    else. Held down it goes on taking lanes, one at a time, and stops where the
    road does -- it is a lane switch, and what it switches between is lanes.
    The driver's job is the pedals and the decision about when to pass.

    **It does the steering and nothing else.** It does not touch the pedals,
    it does not look for what is coming the other way, and it will not stop a
    driver arriving at a corner too fast. A player can still crash it; what
    they cannot do is crash it *because of the steering*, which is what
    :meth:`seconds_for` is about.

    The one thing it does look at is the lane the driver has already asked for.
    A press with somebody alongside is *kept* rather than obeyed or thrown away
    (:data:`QUEUED_FOR`), and taken the moment there is room -- by which time
    the driver has made that room on the pedals, which is theirs to do. What
    that buys is a switch that always means something when it is pressed.

    The lane asked for is counted from the one the car is *in*, so a driver who
    has drifted across a line asks for the lane beside them; asked for again
    part-way across, it counts from the lane being taken, so two presses are two
    lanes.
    """

    name = 'lanes'
    summary = 'the wheel asks for the lane over, and the car takes it'
    advises = True

    def __init__(self, *args: Any, **named: Any) -> None:
        super().__init__(*args, **named)
        #: The lane being taken, in metres right of the crown, or None where the
        #: car is where it was asked to be.
        self.taking: float | None = None
        self._from = 0.0
        self._seconds = 0.0
        self._elapsed = 0.0
        self._asked = 0.0
        self._pointed: float | None = None
        #: A lane asked for that there is not yet room in, or None. Held rather
        #: than obeyed or dropped: see :meth:`clear_to`.
        self.queued: float | None = None
        self._queued_for = 0.0

    def enter(self, session: Any) -> None:
        super().enter(session)
        self.replaced()
        self._asked = 0.0
        # Where the pointer already is is not a request: it is where a pointer
        # sits until somebody moves it.
        self._pointed = self.source.pointer_axis()

    def replaced(self) -> None:
        self.taking = None
        self._elapsed = 0.0
        self.queued = None
        self._queued_for = 0.0

    # -- what a lane change is -------------------------------------------------

    def seconds_for(self, across: float, speed: float, car: Any) -> float:
        """How long a change of ``across`` metres takes at this speed.

        Long enough that the car is never pushed sideways harder than
        :data:`LANE_CHANGE_G`, and never harder than the front wheels could ask
        for at the speed it is doing: what a car may demand of its tyres
        sideways is ``v**2 / r`` at the tightest radius its lock allows there
        (:meth:`omi_physics.vehicle.RaycastVehicle.turning_radius`), and at
        walking pace that is a good deal less than the same lock buys at eighty.
        Taking :data:`LANE_CHANGE_SHARE` of it leaves the rest for holding the
        new lane and for whatever the road is doing while the car crosses it.

        The line moves as a raised cosine (:meth:`arriving`), whose hardest
        sideways push is ``d * pi**2 / (2 T**2)``; this is that, read for ``T``.
        """
        across = abs(float(across))
        if across <= 0.0:
            return LANE_CHANGE_QUICKEST
        sideways = min(LANE_CHANGE_G, self.sideways_room(speed, car))
        if sideways <= 0.0:
            return LANE_CHANGE_LONGEST
        wanted = math.pi * math.sqrt(across / (2.0 * sideways))
        return max(LANE_CHANGE_QUICKEST, min(LANE_CHANGE_LONGEST, wanted))

    @staticmethod
    def sideways_room(speed: float, car: Any) -> float:
        """The hardest this car may be steered sideways here, in m/s squared.

        ``v**2 / r`` at the tightest circle it will hold at this speed, which is
        what its steering lock is worth as a sideways push. A car that cannot
        say answers zero, and a change then takes as long as one is allowed to.
        """
        vehicle = getattr(car, 'vehicle', None)
        radius = getattr(vehicle, 'turning_radius', None)
        if radius is None:                       # pragma: no cover - a double
            return 0.0
        found = float(radius(speed))
        if not found or not math.isfinite(found):
            return 0.0
        return float(speed) * float(speed) / found * LANE_CHANGE_SHARE

    def take(self, wanted: float, session: Any, line: float) -> None:
        """Take that lane, over as long as the car needs to arrive cleanly.

        ``line`` is where the car is being held now, which is what the change
        is measured from -- not the aid's own line, which on the first step of a
        run has not yet been given the car's.
        """
        self.taking = self.zone.clamp(wanted)
        self._from = float(line)
        self._elapsed = 0.0
        self._seconds = self.seconds_for(self.taking - self._from,
                                         float(session.car.speed()),
                                         session.car)

    # -- driving it ------------------------------------------------------------

    def moved(self, line: float, axis: float, dt: float) -> float:
        """A press is a lane; nothing else moves the car across the road.

        A lane with something in it is *asked for* rather than taken, and taken
        the moment there is room in it (:data:`QUEUED_FOR`, :meth:`clear_to`).
        On an open road that moment is this one, and the press behaves as it
        always has.
        """
        wanted = self.asked_for(line)
        if wanted is not None:
            self.queued, self._queued_for = wanted, 0.0
        if self.queued is not None:
            self._queued_for += float(dt)
            if self._queued_for > QUEUED_FOR:
                self.queued = None
            elif self.clear_to(self.queued):
                self.take(self.queued, self._session, line)
                self.queued = None
        return self.arriving(line, dt)

    def clear_to(self, across: float) -> bool:
        """Whether there is room in that lane to move into now.

        The one thing this scheme looks at, and it looks at it about the lane
        the driver has *already asked for* rather than deciding for them
        whether to pass. A run that cannot say answers yes: what the scheme
        does without an answer is what it did before there was a question.
        """
        ask = getattr(self._session, 'lane_clear', None)
        return True if ask is None else bool(ask(float(across)))

    def asked_for(self, line: float) -> float | None:
        """The lane the driver has just asked for, or None for no new request.

        A key asks for one when it goes down, and again whenever the car has
        arrived and the key is still held -- so holding it takes the lanes one
        at a time rather than sliding the car across the road, and stops where
        the road does.

        A pointer asks by *moving*: where it is across the window is the lane it
        is over. One nobody has touched asks for nothing, since it sits in the
        middle of the window and the middle of a two-lane road is a place no
        driver chose.
        """
        keys = self.source.key_axis()
        pressed, self._asked = keys != self._asked and keys, keys
        if keys and (pressed or self.taking is None):
            return self.next_lane(line, -int(keys))
        pointer = self.source.pointer_axis()
        if pointer is None or pointer == self._pointed:
            return None
        self._pointed = pointer
        return self.lane_over(line, self.zone.lane_at(-pointer * self.zone.edge))

    def next_lane(self, line: float, direction: int) -> float | None:
        """The lane that way, or None where there is no road that way."""
        return self.lane_over(line, self.lane_of(line) + int(direction))

    def lane_over(self, line: float, index: int) -> float | None:
        """That lane, or None where the car is in it or going to it already."""
        found = self.zone.centre_of(index)
        return None if self.zone.lane_at(found) == self.lane_of(line) else found

    def lane_of(self, line: float) -> int:
        """Which lane the car is in, or is on its way to."""
        return self.zone.lane_at(line if self.taking is None else self.taking)

    def arriving(self, line: float, dt: float) -> float:
        """The line, moved on towards the lane being taken.

        A raised cosine from where the manoeuvre started to where it is going:
        it leaves one lane and arrives in the next with no sideways speed at
        either end, which is what makes it a lane change rather than a swerve
        followed by a catch.
        """
        if self.taking is None:
            return line
        self._elapsed += float(dt)
        if self._elapsed >= self._seconds:
            found, self.taking = self.taking, None
            return found
        along = self._elapsed / self._seconds
        return self._from + (self.taking - self._from) * (
            1.0 - math.cos(math.pi * along)) / 2.0


class Chauffeur(ControlScheme):
    """It drives; the player interrupts.

    The autopilot has the car until something is asked of it, hands it over the
    moment anything is held, and takes it back :data:`HANDBACK` seconds after
    the driver stops asking for anything. The way to watch a lap, to be shown
    the line through a corner, or to have the world without the race.
    """

    name = 'chauffeur'
    summary = 'it drives itself until you touch anything, and then hands back'

    def __init__(self, *args: Any, **named: Any) -> None:
        super().__init__(*args, **named)
        self.autopilot: Autopilot | None = None
        self._idle = HANDBACK

    def enter(self, session: Any) -> None:
        super().enter(session)
        self.autopilot = Autopilot(session.course, lane=session.lane)
        self._idle = HANDBACK

    @property
    def driving(self) -> bool:
        """Whether the car is the autopilot's right now."""
        return self._idle >= HANDBACK

    def drive(self, session: Any, dt: float) -> tuple[float, float, float]:
        # Anything at all held is the player taking the car: a driver reaching
        # for the brake has not asked to be talked out of it.
        self._idle = 0.0 if self.source.held else self._idle + float(dt)
        if self.driving and self.autopilot is not None:
            return self.autopilot.controls(session, dt)
        return self.source.controls(session, dt)


#: Every way of driving the game will build, by the name it is asked for.
SCHEMES: dict[str, type[ControlScheme]] = {
    scheme.name: scheme for scheme in (Wheel, Loose, Line, Lanes, Chauffeur)}

#: The one a player gets without asking: the controls the game has always had.
DEFAULT = Wheel.name


def available() -> tuple[str, ...]:
    """The names of the ways of driving, in the order they are offered."""
    return tuple(SCHEMES)


def named(name: str, **named: Any) -> ControlScheme:
    """Build the scheme called that, or say which there are.

    ``pointer``, ``source`` and ``trim`` go to the scheme
    (:class:`ControlScheme`), so choosing a way of driving and steering it with
    the mouse are separate decisions.
    """
    found = SCHEMES.get(str(name))
    if found is None:
        raise ValueError('there is no way of driving called %r; there is %s'
                         % (name, ', '.join(available())))
    return found(**named)
