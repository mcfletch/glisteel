"""GLinting Steel: drive a car round a baked world.

    oglc-bake --output /tmp/world        # make a world (OpenGLContext-editor)
    glisteel /tmp/world/tileset.json     # drive it

Keys::

    up / w              throttle
    down / s            brake, and reverse once stopped
    left / right, a / d steer
    space               handbrake
    c                   cockpit / chase / bonnet camera
    r                   put the car back on the track
    F2                  save a screenshot

The world streams itself in around the car and hands each tile it loads to the
physics as a static collider, so the car drives on exactly the triangles that
are drawn. The car is a rigid body on four spring-loaded rays
(:class:`~omi_physics.vehicle.RaycastVehicle`); everything about how it feels
is in :class:`~glisteel.car.CarSpec`.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Any

os.environ.setdefault('OPENGLCONTEXT_PROFILE', 'core')
os.environ.setdefault('OPENGLCONTEXT_BACKEND', 'glfw')
os.environ.setdefault('OPENGLCONTEXT_RENDERER', 'pbr')

from OpenGLContext import testingcontext  # noqa: E402
from OpenGLContext.scenegraph.scenegraph import SceneGraph  # noqa: E402
from OpenGLContext.ui.overlay import OverlayMixin  # noqa: E402
from OpenGLContext.viewer import environment  # noqa: E402
from OpenGLContext.viewer.sceneviewer import ViewerContext  # noqa: E402

from glisteel.camera import ChaseCamera  # noqa: E402
from glisteel.car import Car, CarSpec  # noqa: E402
from glisteel.driver import Autopilot  # noqa: E402
from glisteel.hud import RaceHUD  # noqa: E402
from glisteel.race import (  # noqa: E402
    Collisions,
    OffRoad,
    RaceTiming,
    off_course,
)
from glisteel.world import RaceWorld  # noqa: E402

log = logging.getLogger(__name__)
BaseContext: Any = testingcontext.getInteractive()

#: The physics step. Fixed, and finer than a frame: a vehicle held up by
#: springs is stiff, and integrating it at whatever the display manages makes
#: the car bounce on a fast machine and sink through the road on a slow one.
PHYSICS_STEP = 1.0 / 120.0

#: The most simulation one frame may catch up on. Past this the game runs slow
#: rather than spiralling: a frame that tries to make up a lost second takes
#: longer than a second and loses more.
MAXIMUM_CATCHUP = 0.1

#: A car that has stopped somewhere it should not be -- wedged against a bank,
#: on its roof, off the map -- is put back on the road after this long. Long
#: enough that a driver who has stopped on purpose is left alone, short enough
#: that nobody sits looking at a hillside.
STUCK_SECONDS = 3.0
STUCK_SPEED = 1.0

#: The scale the default light rig is sized to. A world is kilometres across
#: and the rig's fill light is placed as a multiple of this, so it is the size
#: of the *scene the player is in* rather than of the whole map.
WORLD_LIGHT_SCALE = 120.0

#: How far a driver can see before the air takes the view, in metres. Far
#: enough to place the car for the corner after next; close enough that the far
#: side of a baked world is haze rather than a line where the ground stops.
VISIBILITY = 1800.0

#: Which keys do what. Each is a set of names, so the arrows and WASD are the
#: same control rather than two.
CONTROLS = {
    'throttle': {'w', 'W', 'up'},
    'brake': {'s', 'S', 'down'},
    'left': {'a', 'A', 'left'},
    'right': {'d', 'D', 'right'},
    'handbrake': {' '},
}


class GlisteelContext(OverlayMixin, BaseContext):
    """The game window: a streamed world, a car in it, and a camera behind."""

    config: Any = None
    world: RaceWorld | None = None
    _capture: Any = None
    car: Car | None = None
    autopilot: Autopilot | None = None
    timing: RaceTiming | None = None
    watch: OffRoad | None = None
    crashes: Collisions | None = None
    hud: Any = None
    # Supplied by the interactive runtime base.
    platform: Any
    addEventHandler: Any
    triggerRedraw: Any
    sg: Any

    def OnInit(self) -> None:                    # pragma: no cover - needs a window
        self.held: set[str] = set()
        self._clock = time.time()
        self._accumulated = 0.0
        self._stuck_for = 0.0
        self.camera = ChaseCamera()
        self.world = RaceWorld(self.config.world, max_sse=self.config.sse,
                               traffic=getattr(self.config, 'traffic', 0))
        # The engine's own sky and light rig, rather than one written here: a
        # world baked for the viewer is lit the way the viewer lights it, and a
        # game that invents its own rig renders the same tiles differently.
        # What a race adds to it is its own air, because a baked world is a few
        # kilometres across and then it stops.
        self.sg = SceneGraph(children=[
            environment.horizon_background(),
            race_fog(),
            *ViewerContext.defaultLights(WORLD_LIGHT_SCALE),
            self.world.terrain,
        ])
        self._start_the_car()
        self.hud = RaceHUD()
        self.hud.visible = self.config.hud
        self.addHUDLayer(self.hud)
        self._bind_keys()

    # -- setting up ------------------------------------------------------------

    def _start_the_car(self) -> None:            # pragma: no cover - needs a window
        """Put the car on the grid, once the ground under it has arrived."""
        assert self.world is not None
        course = self.world.course
        if course is None:
            raise SystemExit(
                "%s carries no roads, so there is nothing to race on. Bake a "
                "world with a circuit in it." % self.config.world)
        lane = self._lane(course)
        position, heading = course.grid_position(height=6.0, lane=lane)
        self.platform.setPosition(tuple(float(v) for v in position))
        if not self.world.settled(tuple(float(v) for v in position)):
            log.warning("the ground under the grid has not loaded; "
                        "the car may fall")
        self.car = Car(self.world.physics, CarSpec(), position=position,
                       heading=heading)
        self.sg.children.append(self.car.node)
        if self.world.traffic is not None:
            # Mounted once; the cars under it come and go as the player passes.
            self.sg.children.append(self.world.traffic.node)
        self.timing = RaceTiming(course)
        self.watch = OffRoad(course)
        self.crashes = Collisions()
        self.autopilot = (Autopilot(course, lane=lane)
                          if self.config.autopilot else None)
        self._settle_onto_the_road()

    def _settle_onto_the_road(self) -> None:     # pragma: no cover - needs a window
        """Drop the car the last few metres before the player gets it."""
        assert self.car is not None and self.world is not None
        for _ in range(int(1.5 / PHYSICS_STEP)):
            self.car.update(PHYSICS_STEP)
            self.world.physics.step(PHYSICS_STEP)
        self.car.follow(PHYSICS_STEP)
        self.camera.reset()

    def _bind_keys(self) -> None:                # pragma: no cover - needs a window
        for names in CONTROLS.values():
            for name in names:
                for state in (1, 0):
                    self.addEventHandler('keyboard', name=name, state=state,
                                         function=self._on_key)
        self.addEventHandler('keypress', name='c', function=self._on_camera)
        self.addEventHandler('keypress', name='r', function=self._on_reset)

    # -- input -----------------------------------------------------------------

    def _on_key(self, event: Any) -> None:       # pragma: no cover - needs a window
        name = getattr(event, 'name', None)
        if name is None:
            return
        if getattr(event, 'state', 0):
            self.held.add(name)
        else:
            self.held.discard(name)
        self.triggerRedraw(1)

    def _on_camera(self, event: Any) -> None:    # pragma: no cover - needs a window
        self.camera.cycle()
        self.triggerRedraw(1)

    def _on_reset(self, event: Any) -> None:     # pragma: no cover - needs a window
        self.return_to_track()

    def _held(self, control: str) -> bool:
        return bool(self.held & CONTROLS[control])

    def driver_input(self) -> tuple[float, float, float]:
        """The pedals and the wheel, from whatever is held down."""
        throttle = 1.0 if self._held('throttle') else 0.0
        brake = 0.0
        if self._held('brake'):
            # One pedal, two meanings: it stops a car that is moving forward
            # and reverses one that has stopped, which is what an arrow key on
            # a keyboard has to do.
            assert self.car is not None
            if self.car.vehicle.forward_speed() > 0.4:
                brake = 1.0
            else:
                throttle = -1.0
        if self._held('handbrake'):
            brake = 1.0
        steer = (1.0 if self._held('left') else 0.0) - \
            (1.0 if self._held('right') else 0.0)
        return throttle, brake, steer

    def controls(self) -> tuple[float, float, float]:
        """Whoever is driving: the autopilot, or whoever is at the keyboard."""
        if self.autopilot is not None and self.car is not None:
            return self.autopilot.update(self.car)
        return self.driver_input()

    def return_to_track(self) -> None:           # pragma: no cover - needs a window
        """Put the car back on the road, facing the right way, stopped."""
        if self.car is None or self.world is None:
            return
        course = self.world.course
        if course is None:
            return
        index, _ = course.nearest(self.car.position)
        position, heading = course.grid_position(
            index, height=1.5, lane=self._lane(course))
        self.car.place(position, heading)
        self.camera.reset()
        if self.timing is not None:
            self.timing.restart()
        if self.watch is not None:
            self.watch.restart()
        if self.crashes is not None:
            self.crashes.restart()

    # -- the frame -------------------------------------------------------------

    def OnIdle(self, *args: Any) -> int:         # pragma: no cover - needs a window
        now = time.time()
        elapsed = min(now - self._clock, MAXIMUM_CATCHUP)
        self._clock = now
        self.advance(elapsed)
        self.triggerRedraw(1)
        return 1

    def advance(self, elapsed: float) -> None:   # pragma: no cover - needs a window
        """One frame: fixed-step physics, then camera, HUD and streaming."""
        assert self.car is not None and self.world is not None
        # The controls are sampled inside the fixed step, not once a frame. A
        # steering loop that only runs when a frame is drawn is a controller at
        # the frame rate, and on a slow frame it holds full lock for a quarter
        # of a second and puts the car on its roof.
        self._accumulated += elapsed
        while self._accumulated >= PHYSICS_STEP:
            self._read_the_ground(PHYSICS_STEP)
            self.car.control(*self.controls())
            self.car.update(PHYSICS_STEP)
            self.world.physics.step(PHYSICS_STEP)
            self._accumulated -= PHYSICS_STEP
        self.car.follow(elapsed)
        if self.world.traffic is not None and not self._over():
            self.world.traffic.update(self.car.position, elapsed)
            self._watch_for_a_crash(elapsed)
        self._recover_if_stuck(elapsed)
        pose = self.camera.update(self.car, elapsed)
        self.car.hidden = self.camera.inside
        self._aim(pose)
        if self.timing is not None and not self._over():
            self.timing.update(self.car.position, elapsed)
        self._update_hud()
        width, height = self.getViewPort()
        self.world.stream(
            tuple(float(v) for v in pose.position), float(height or 1),
            view_projection=self.world.view_projection(
                pose.position, pose.target, (width or 1) / (height or 1)))
        if self.car.position[1] < self.world.terrain.tileset.root \
                .bounding_volume.center[1] - 500.0:
            # Through the floor of the world: put it back rather than let the
            # player watch it fall for ever.
            self.return_to_track()

    def _read_the_ground(self, dt: float) -> None:
        """What the wheels are on, and whether the run is over.

        Inside the fixed step rather than once a frame: the surface decides the
        forces, and a surface sampled at the frame rate would change under the
        car in jumps on a slow frame.
        """
        assert self.car is not None
        if self.watch is None:
            return
        reason = self.watch.update(self.car.position, dt)
        self.car.vehicle.surface = self.watch.surface()
        if reason is not None:
            log.info("run over: %s", reason)

    def _lane(self, course: Any) -> float:       # pragma: no cover - needs a window
        """Which side of the road to drive on.

        The middle of the road on an empty circuit, because that is the racing
        line and there is nothing to meet. With traffic coming the other way it
        is the middle of this car's own half, because that is what a road with
        two directions on it means.
        """
        return (course.driving_lane
                if getattr(self.config, 'traffic', 0) else 0.0)

    def _watch_for_a_crash(self, dt: float) -> None:  # pragma: no cover - needs a window
        """End the run if the car met another one hard enough.

        The closing speed against the nearest car in front, which is what the
        severity of a crash is: a car alongside at the same speed is an
        overtake, and the back of one at forty metres a second is not.
        """
        if self.crashes is None or self.world.traffic is None:
            return
        ahead = self.world.traffic.ahead_of(self.car.position,
                                            self.car.forward(), reach=6.0)
        if not ahead:
            return
        closing = float(self.car.speed()) - float(ahead[0].speed)
        self.crashes.update(max(closing, 0.0), dt)

    def _ended(self) -> str | None:              # pragma: no cover - needs a window
        """Why the run is over, or None while it is not."""
        for watcher in (self.watch, self.crashes):
            if watcher is not None and watcher.ended:
                return str(watcher.ended)
        return None

    def _over(self) -> bool:                     # pragma: no cover - needs a window
        return self._ended() is not None

    def _recover_if_stuck(self, elapsed: float) -> None:
        """Put the car back on the road if it has got itself stuck.

        Wedged against a bank, upside down, or through the floor of the world:
        all of them end with a car that is not going anywhere, and a game that
        leaves the player looking at it is broken however correct the physics
        was on the way there.
        """
        assert self.car is not None
        stuck = (self.car.speed() < STUCK_SPEED
                 and (self._off_course() or self.car.upside_down()))
        self._stuck_for = self._stuck_for + elapsed if stuck else 0.0
        if self._stuck_for > STUCK_SECONDS:
            self._stuck_for = 0.0
            self.return_to_track()

    def _aim(self, pose: Any) -> None:           # pragma: no cover - needs a window
        from OpenGLContext import quaternion
        self.platform.setPosition(tuple(float(v) for v in pose.position))
        aim = (quaternion.fromXYZR(1, 0, 0, -pose.pitch())
               * quaternion.fromXYZR(0, 1, 0, pose.heading()))
        self.platform.setOrientation(aim)

    def _update_hud(self) -> None:               # pragma: no cover - needs a window
        if self.hud is None or self.car is None:
            return
        self.hud.show(speed_kph=self.car.speed_kph(), timing=self.timing,
                      off=self.watch.off if self.watch else False,
                      ended=self._ended())

    def _off_course(self) -> bool:               # pragma: no cover - needs a window
        assert self.world is not None and self.car is not None
        course = self.world.course
        return bool(course is not None and off_course(course, self.car.position))

    def SwapBuffers(self, *args: Any) -> Any:    # pragma: no cover - needs a window
        """Present the frame, and take the picture when one is asked for.

        A capture is settled by *drawn frames*, so it is ticked here rather than
        on a clock: the world streams in while the count runs, and the picture
        is of a world that has arrived.
        """
        capture = getattr(self, '_capture', None)
        if capture is not None and capture.tick():
            result = super().SwapBuffers(*args)
            self.setCurrent()
            sys.stdout.write('captured %s\n' % (self.config.capture,))
            sys.stdout.flush()
            if self.world is not None:
                self.world.shutdown()
            os._exit(0)
            return result
        return super().SwapBuffers(*args)

    def OnQuit(self, *args: Any) -> None:        # pragma: no cover - needs a window
        if self.world is not None:
            self.world.shutdown()
        super().OnQuit(*args)


def race_fog() -> Any:
    """The air the world is seen through.

    A baked world runs out, and past the last of it a camera at ground level
    sees the background. The fog is the colour the background's horizon is, so
    the ground fades into the same air rather than ending at a line, and it
    closes in over a distance rather than at one -- an exponential fall-off has
    no visible edge, which is the whole point of it here.
    """
    from OpenGLContext.scenegraph.fog import Fog
    return Fog(color=environment.HORIZON_HAZE, fogType='EXPONENTIAL',
               visibilityRange=VISIBILITY)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='glisteel', description=__doc__.split('\n\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__[__doc__.index('Keys::'):])
    parser.add_argument('world', nargs='?', default='baked-world/tileset.json',
                        help='the tileset.json of a baked world '
                             '(default: %(default)s)')
    parser.add_argument('--sse', type=float, default=12.0,
                        help='screen-space error the world refines to; lower is '
                             'sharper and slower (default: %(default)s)')
    parser.add_argument('--hud', action=argparse.BooleanOptionalAction,
                        default=True, help='draw the speed and lap readouts')
    parser.add_argument('--traffic', type=int, default=8, metavar='CARS',
                        help='how many other cars are on the road at once '
                             '(0 for an empty circuit)')
    parser.add_argument('--autopilot', action='store_true',
                        help='let the car drive itself round the circuit')
    parser.add_argument('--size', default='1280x720', metavar='WxH',
                        help='window size (default: %(default)s)')
    parser.add_argument('--capture', metavar='PATH',
                        help='render to PATH (PNG) once the world has settled, '
                             'then exit')
    parser.add_argument('--capture-delay', type=float, default=4.0,
                        metavar='SECONDS',
                        help='how long to let the world stream in before '
                             '--capture (default: %(default)s)')
    parser.add_argument('--drive-seconds', type=float, default=0.0,
                        metavar='SECONDS',
                        help='drive for this long before capturing, so the '
                             'picture is of a car that is going somewhere')
    return parser


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - needs a window
    logging.basicConfig(level=logging.INFO)
    options = build_parser().parse_args(argv)
    width, _, height = options.size.partition('x')
    GlisteelContext.config = options
    if options.capture:
        _capture(options, int(width), int(height))
        return 0
    GlisteelContext.ContextMainLoop(size=(int(width), int(height)))
    return 0


def _capture(options: Any, width: int, height: int) -> None:  # pragma: no cover
    """Render one frame of the game to a file and exit.

    The world streams while the clock runs, so the capture waits; with
    ``--drive-seconds`` the car is driven forward first, which is how a picture
    of the game gets a car that is going somewhere.
    """
    from OpenGLContext.capture import SettleCapture

    class CapturingContext(GlisteelContext):
        config = options

        def OnInit(self) -> None:
            self._capture = None
            super().OnInit()
            if options.drive_seconds and self.autopilot is None:
                self.held.update(CONTROLS['throttle'])
            self._capture = SettleCapture(
                options.capture,
                delay=options.capture_delay + options.drive_seconds,
                min_frames=30)

    CapturingContext.ContextMainLoop(size=(width, height))


if __name__ == '__main__':                       # pragma: no cover - module entry
    sys.exit(main())
