"""A run: a car on a course, somebody driving it, and the rules about both.

This is the game's loop, and it has nothing to do with a window. Physics runs at
a fixed step with the controls sampled *inside* it, the camera follows, the lap
is timed, the world streams around the car, and the rules about leaving the road
and getting stuck are applied. What draws any of that is somebody else's
business: :class:`~glisteel.game.GlisteelContext` builds a session, feeds it the
keyboard and draws what it says.

    >>> from glisteel import scenarios
    >>> from glisteel.session import Session
    >>> session = Session(scenarios.circuit().world())
    >>> session.advance(1.0 / 60.0)                          # doctest: +ELLIPSIS
    CameraPose(...)

**Whoever is driving is a** :class:`Controller`: one method, handed the session
and the length of the step, answering with the throttle, the brake and the
wheel. :class:`~glisteel.driver.Autopilot` is one, the keyboard is one
(:class:`~glisteel.steering.KeyboardDriver`), and so is anything a test scripts.
Swapping :attr:`Session.driver` mid-run hands the car over.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np

from glisteel.assist import STRENGTH, Straighten
from glisteel.camera import VIEWS, CameraPose, ChaseCamera
from glisteel.car import Car, CarSpec
from glisteel.race import Collisions, OffRoad, RaceTiming, closing_speed, off_course
from glisteel.reflections import Reflections
from glisteel.run import COUNTDOWN, Run

log = logging.getLogger(__name__)

__all__ = ['Controller', 'Readings', 'Result', 'Session', 'AHEAD_REACH',
           'MAXIMUM_CATCHUP',
           'PHYSICS_STEP', 'RACE_LAPS', 'STUCK_SECONDS', 'STUCK_SPEED']

#: The physics step. Fixed, and finer than a frame: a vehicle held up by
#: springs is stiff, and integrating it at whatever the display manages makes
#: the car bounce on a fast machine and sink through the road on a slow one.
PHYSICS_STEP = 1.0 / 120.0

#: The most simulation one frame may catch up on. Past this the game runs slow
#: rather than spiralling: a frame that tries to make up a lost second takes
#: longer than a second and loses more.
MAXIMUM_CATCHUP = 0.1

#: How far up the road a driver looks for something to run into, in metres.
AHEAD_REACH = 140.0

#: A car that has stopped somewhere it should not be -- wedged against a bank,
#: on its roof, off the map -- is put back on the road after this long. Long
#: enough that a driver who has stopped on purpose is left alone, short enough
#: that nobody sits looking at a hillside.
STUCK_SECONDS = 3.0
STUCK_SPEED = 1.0

#: How far a crash is looked for around the car, in metres: touching distance
#: and no more. What decides the severity is the closing speed, not the range.
CONTACT_REACH = 6.0

#: How high over the grid a car is put before it is dropped onto it, in metres,
#: and how long it is left to settle. The player is handed a car that is already
#: standing on its wheels rather than one still falling.
GRID_HEIGHT = 6.0
SETTLE_SECONDS = 1.5

#: How many laps a race is unless a caller says otherwise. One: an empty
#: circuit and a single lap is what a timed lap is, and it is what a record
#: (:mod:`glisteel.run`) is kept against.
RACE_LAPS = 1

#: The viewport a session assumes until it is told otherwise. Streaming needs a
#: height to measure screen-space error against and an aspect to cull with.
VIEWPORT = (1280, 720)


@runtime_checkable
class Controller(Protocol):
    """Whoever is driving: the pedals and the wheel, once per physics step.

    Handed the session so a driver may look at the car, the road and what is in
    front of it, and ``dt`` because a wheel that winds on over time needs to
    know how much time has passed. The answer is ``(throttle, brake, steer)``,
    each from -1 to 1 as :meth:`glisteel.car.Car.control` takes them.
    """

    def controls(self, session: Session, dt: float
                 ) -> tuple[float, float, float]:
        ...                                      # pragma: no cover - a protocol


@dataclass
class Readings:
    """What a run looks like from outside it, once a frame.

    Everything the HUD is told and everything a recorded run is measured
    against, in one place: the speed, the clocks, whether the car is off the
    road, why the run ended, and where the car and the traffic are.
    """

    speed_kph: float = 0.0
    timing: Any = None
    off: bool = False
    ended: str | None = None
    at: Any = None
    others: list = field(default_factory=list)
    #: Which part of the race this is, one of :data:`glisteel.run.PHASES`.
    phase: str = COUNTDOWN
    #: Lamps burning on the start rig, and how many there are in it.
    lit: int = 0
    lights: int = 0


@dataclass
class Result:
    """How a run came out, once there is an answer.

    ``outcome`` is why it stopped being a race, or None for one driven home;
    ``seconds`` is the quickest lap of it, or None where none was completed --
    a run can end without a time, and that is a result too.
    """

    outcome: str | None = None
    seconds: float | None = None
    laps: int = 0

    @property
    def finished(self) -> bool:
        """Whether the race was driven home rather than stopped."""
        return self.outcome is None


class Session:
    """One run of the game: build it, then :meth:`advance` it a frame at a time.

    ``world`` is what is being driven (:class:`~glisteel.world.RaceWorld`);
    ``driver`` is whoever is at the controls, and may be left out and set later.
    The car is placed on the grid and dropped onto it as the session is built,
    so what a caller gets back is a car standing on the road ready to go.

    ``view`` names the camera the run starts in; a caller changes it through
    :attr:`camera`.
    """

    def __init__(self, world: Any, spec: CarSpec | None = None,
                 view: str = VIEWS[0], driver: Any = None,
                 viewport: tuple[int, int] = VIEWPORT,
                 laps: int = RACE_LAPS, assist: float = STRENGTH) -> None:
        course = world.course
        if course is None:
            raise ValueError(
                "the world carries no roads, so there is nothing to race on")
        self.world = world
        self.course = course
        #: Whoever is driving, or None for a car nobody is touching.
        self.driver = driver
        #: The window's size, which streaming measures detail against.
        self.viewport = viewport
        self.camera = ChaseCamera(view)
        self.lane = course.driving_lane if world.traffic is not None else 0.0
        self.grid = course.start_index
        # Asked about the road's own surface rather than about the slot six
        # metres over it: what a settled world means is that there is ground
        # where the car is going to land.
        standing, _ = course.grid_position(self.grid, height=1.0, lane=self.lane)
        if not world.settled(tuple(float(v) for v in standing)):
            log.warning("the ground under the grid has not loaded; "
                        "the car may fall")
        position, heading = course.grid_position(self.grid, height=GRID_HEIGHT,
                                                 lane=self.lane)
        self.car = Car(world.physics, spec or CarSpec(), position=position,
                       heading=heading)
        #: What the car is lit and reflected by, which follows the road.
        self.reflections = Reflections(course)
        self.timing = RaceTiming(course)
        self.watch = OffRoad(course)
        self.crashes = Collisions()
        #: Which part of the race this is, and what it lets through to the car.
        self.run = Run(laps=laps)
        #: The steering the game puts in while the player is not steering.
        self.assist = Straighten(course, strength=assist, lane=self.lane)
        self._accumulated = 0.0
        self._stuck_for = 0.0
        self._settle()

    # -- the state of the run --------------------------------------------------

    @property
    def ended(self) -> str | None:
        """Why the run is over, or None while it is not."""
        for watcher in (self.watch, self.crashes):
            if watcher.ended:
                return str(watcher.ended)
        return None

    def readout(self) -> Readings:
        """This frame's numbers, for a HUD or for a recorded run."""
        others = (self.world.traffic.cars
                  if self.world.traffic is not None else ())
        return Readings(
            speed_kph=self.car.speed_kph(), timing=self.timing,
            off=self.watch.off, ended=self.ended, at=self.car.position,
            others=[car.position() for car in others],
            phase=self.run.phase, lit=self.run.lit, lights=self.run.lights)

    def result(self) -> Result | None:
        """How the run came out, or None while it is still a race.

        What a finish screen is made of and what a record is offered from, so
        neither has to reach into the clocks and the watchers to work out what
        happened.
        """
        if not self.run.over:
            return None
        best = self.timing.best
        return Result(outcome=self.run.outcome,
                      seconds=best.seconds if best is not None else None,
                      laps=len(self.timing.laps))

    def traffic_ahead(self, reach: float = AHEAD_REACH
                      ) -> tuple[float, float] | None:
        """What is in front in this lane: how far, and how fast it is going.

        None for an open road. A driver who knows the corners and not the
        traffic drives into the back of the first car it catches, so this is
        what a :class:`Controller` asks before deciding its speed.
        """
        if self.world.traffic is None:
            return None
        ahead = self.world.traffic.ahead_of(self.car.position,
                                            self.car.forward(), reach=reach)
        if not ahead:
            return None
        first = ahead[0]
        offset = np.asarray(first.position(), dtype='d') - self.car.position
        return float(np.linalg.norm(offset)), float(first.speed)

    # -- the frame -------------------------------------------------------------

    def advance(self, elapsed: float) -> CameraPose:
        """One frame: fixed-step physics, then camera, streaming and the rules.

        Returns where to watch the run from. ``elapsed`` is real time since the
        last frame, clamped to :data:`MAXIMUM_CATCHUP` so a slow frame leaves
        the game running slow rather than spiralling.
        """
        elapsed = min(max(float(elapsed), 0.0), MAXIMUM_CATCHUP)
        # The controls are sampled inside the fixed step, not once a frame. A
        # steering loop that only runs when a frame is drawn is a controller at
        # the frame rate, and on a slow frame it holds full lock for a quarter
        # of a second and puts the car on its roof.
        self._accumulated += elapsed
        while self._accumulated >= PHYSICS_STEP:
            self._read_the_ground(PHYSICS_STEP)
            wanted = self._controls(PHYSICS_STEP)
            # The race's own state, stepped on the physics clock so a start
            # sequence counts the same on any machine, and asked *before* the
            # controls are applied so the step the flag falls on is already
            # being driven.
            self.run.update(PHYSICS_STEP, laps=len(self.timing.laps),
                            ended=self.ended)
            self.car.control(*self.run.allow(*wanted))
            self.car.update(PHYSICS_STEP)
            self.world.physics.step(PHYSICS_STEP)
            self._accumulated -= PHYSICS_STEP
        self.car.follow(elapsed)
        if self.world.traffic is not None and not self.run.over:
            self.world.traffic.update(self.car.position, elapsed,
                                      speed=self.car.speed())
            self._watch_for_a_crash(elapsed)
        self._recover_if_stuck(elapsed)
        pose = self.camera.update(self.car, elapsed)
        self.car.hidden = self.camera.inside
        changed = self.reflections.update(self.car.position)
        if changed is not None:
            log.info('the road is %s now: rebuilding what the car reflects',
                     changed)
        if self.run.timed:
            self.timing.update(self.car.position, elapsed)
        self._stream(pose)
        if self.car.position[1] < self.world.floor:
            # Through the floor of the world: put it back rather than let the
            # player watch it fall for ever. A run that is already over stays
            # over -- the car is recovered, the result is not.
            self._replace()
            if not self.run.over:
                self._carry_on()
        return pose

    def return_to_track(self) -> None:
        """Put the car back on the road, facing the right way, stopped.

        The race carries on from there: this is what a player asks for when the
        car is somewhere it cannot drive out of, not a request for a new race.
        A race already won is not reopened by it.
        """
        self._replace()
        self._carry_on()

    def restart(self) -> None:
        """A fresh race, from the grid, on the lights."""
        self.grid = self.course.start_index
        position, heading = self.course.grid_position(
            self.grid, height=GRID_HEIGHT, lane=self.lane)
        self.car.place(position, heading)
        self.timing.restart()
        self.watch.restart()
        self.crashes.restart()
        self.run.restart()
        self._stuck_for = 0.0
        self._settle()

    # -- inside the frame ------------------------------------------------------

    def _replace(self) -> None:
        """Stand the car on the road nearest where it got to, stopped."""
        index, _ = self.course.nearest(self.car.position)
        position, heading = self.course.grid_position(index, height=1.5,
                                                      lane=self.lane)
        self.car.place(position, heading)
        self.camera.reset()

    def _carry_on(self) -> None:
        """Let the race go on: the lap is abandoned, the race is not."""
        self.timing.restart()
        self.watch.restart()
        self.crashes.restart()
        self.run.resume()

    def _controls(self, dt: float) -> tuple[float, float, float]:
        """Whoever is driving, or nothing at all where nobody is.

        What the driver asks for goes through :class:`~glisteel.assist.Straighten`
        on its way to the wheel, which puts in the small correction a driver's
        hands make continuously and a keyboard cannot say. A driver already
        steering -- the autopilot, or a player with a key down -- is left alone.
        """
        if self.driver is None:
            return 0.0, 0.0, 0.0
        throttle, brake, steer = self.driver.controls(self, dt)
        return float(throttle), float(brake), self.assist.steer(self, steer)

    def _read_the_ground(self, dt: float) -> None:
        """What the wheels are on, and whether the run is over.

        Inside the fixed step rather than once a frame: the surface decides the
        forces, and a surface sampled at the frame rate would change under the
        car in jumps on a slow frame.
        """
        reason = self.watch.update(self.car.position, dt)
        self.car.vehicle.surface = self.watch.surface()
        if reason is not None:
            log.info("run over: %s", reason)

    def _watch_for_a_crash(self, dt: float) -> None:
        """End the run if the car met another one hard enough.

        The closing speed against the nearest car in front, which is what the
        severity of a crash is: a car alongside at the same speed is an
        overtake, and the back of one at forty metres a second is not.
        """
        ahead = self.world.traffic.ahead_of(self.car.position,
                                            self.car.forward(),
                                            reach=CONTACT_REACH)
        if not ahead:
            return
        other = ahead[0]
        closing = closing_speed(self.car.velocity(), other.velocity(),
                                other.position() - self.car.position)
        self.crashes.update(max(closing, 0.0), dt)

    def _recover_if_stuck(self, elapsed: float) -> None:
        """Put the car back on the road if it has got itself stuck.

        Wedged against a bank, upside down, or through the floor of the world:
        all of them end with a car that is not going anywhere, and a game that
        leaves the player looking at it is broken however correct the physics
        was on the way there.
        """
        stuck = (not self.run.over and self.car.speed() < STUCK_SPEED
                 and (self._off_course() or self.car.upside_down()))
        self._stuck_for = self._stuck_for + elapsed if stuck else 0.0
        if self._stuck_for > STUCK_SECONDS:
            self._stuck_for = 0.0
            self.return_to_track()

    def _off_course(self) -> bool:
        return bool(off_course(self.course, self.car.position))

    def _stream(self, pose: CameraPose) -> None:
        """Bring the world in around wherever the camera is going to be."""
        width, height = self.viewport
        self.world.stream(
            tuple(float(v) for v in pose.position), float(height or 1),
            view_projection=self.world.view_projection(
                pose.position, pose.target, (width or 1) / (height or 1)))

    def _settle(self) -> None:
        """Drop the car the last few metres before the player gets it.

        On the brake all the way down, because what is being handed over is a
        car standing on the grid: one that lands on a slope with the brake off
        is already rolling by the time anybody sees it, and a car rolling when
        the player takes it is a car they did not put in motion.
        """
        for _ in range(int(SETTLE_SECONDS / PHYSICS_STEP)):
            self.car.control(brake=1.0)
            self.car.update(PHYSICS_STEP)
            self.world.physics.step(PHYSICS_STEP)
        self.car.control()
        self.car.follow(PHYSICS_STEP)
        self.camera.reset()
