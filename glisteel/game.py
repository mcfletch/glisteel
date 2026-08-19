"""GLinting Steel: drive a car round a baked world.

    oglc-bake --output /tmp/world        # make a world (OpenGLContext-editor)
    glisteel /tmp/world/tileset.json     # drive it

Keys::

    up / w              throttle
    down / s            brake, and reverse once stopped
    left / right, a / d steer
    space               handbrake
    mouse               steer, with --mouse
    c                   cockpit / chase / bonnet camera
    r                   put the car back on the track
    n                   a fresh race, from the grid
    F2                  save a screenshot

The world streams itself in around the car and hands each tile it loads to the
physics as a static collider, so the car drives on exactly the triangles that
are drawn. The car is a rigid body on four spring-loaded rays
(:class:`~omi_physics.vehicle.RaycastVehicle`); everything about how it feels
is in :class:`~glisteel.car.CarSpec`.

**The run is not in here.** The loop -- fixed-step physics, the camera, the lap
timing and the rules about leaving the road -- is
:class:`~glisteel.session.Session`, which needs no window and can be driven a
step at a time by a test. What is here is the window: the scene it draws, the
keys it delivers, and where it points the view.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

os.environ.setdefault('OPENGLCONTEXT_PROFILE', 'core')
os.environ.setdefault('OPENGLCONTEXT_BACKEND', 'glfw')
os.environ.setdefault('OPENGLCONTEXT_RENDERER', 'pbr')

from OpenGLContext import testingcontext  # noqa: E402
from OpenGLContext.events.systemtime import systemTime  # noqa: E402
from OpenGLContext.scenegraph.scenegraph import SceneGraph  # noqa: E402
from OpenGLContext.ui.overlay import OverlayMixin  # noqa: E402
from OpenGLContext.video.recorder import RecordingMixin  # noqa: E402
from OpenGLContext.viewer import environment  # noqa: E402
from OpenGLContext.viewer.sceneviewer import ViewerContext  # noqa: E402

from glisteel.camera import VIEWS  # noqa: E402
from glisteel.car import CarSpec  # noqa: E402
from glisteel.driver import Autopilot  # noqa: E402
from glisteel.hud import RaceHUD  # noqa: E402
from glisteel.session import RACE_LAPS, Session  # noqa: E402
from glisteel.steering import CONTROLS, KeyboardDriver, MouseWheel  # noqa: E402
from glisteel.world import RaceWorld  # noqa: E402

log = logging.getLogger(__name__)
BaseContext: Any = testingcontext.getInteractive()

#: The scale the default light rig is sized to. A world is kilometres across
#: and the rig's fill light is placed as a multiple of this, so it is the size
#: of the *scene the player is in* rather than of the whole map.
WORLD_LIGHT_SCALE = 120.0

#: How far a driver can see before the air takes the view, in metres. Far
#: enough to place the car for the corner after next; close enough that the far
#: side of a baked world is haze rather than a line where the ground stops.
VISIBILITY = 1800.0


class GlisteelContext(RecordingMixin, OverlayMixin, BaseContext):
    """The game window: a run to advance, a scene to draw, and keys to deliver."""

    config: Any = None
    #: The run this window is showing.
    session: Session | None = None
    _capture: Any = None
    #: Whoever is at the keyboard, or None while the autopilot is driving.
    keyboard: KeyboardDriver | None = None
    hud: Any = None
    # Supplied by the interactive runtime base.
    platform: Any
    addEventHandler: Any
    triggerRedraw: Any
    sg: Any

    def OnInit(self) -> None:                    # pragma: no cover - needs a window
        # The engine's clock rather than the wall clock directly: a recording
        # replaces it with one that advances a frame at a time, and the car has
        # to move on that same clock or the video is not what was driven.
        self._clock = systemTime()
        world = RaceWorld(self.config.world, max_sse=self.config.sse,
                          traffic=getattr(self.config, 'traffic', 0))
        if world.course is None:
            raise SystemExit(
                "%s carries no roads, so there is nothing to race on. Bake a "
                "world with a circuit in it." % self.config.world)
        self.session = Session(world, CarSpec(),
                               view=getattr(self.config, 'view', None) or VIEWS[0],
                               laps=getattr(self.config, 'laps', RACE_LAPS))
        self.session.driver = self._driver()
        # The engine's own sky and light rig, rather than one written here: a
        # world baked for the viewer is lit the way the viewer lights it, and a
        # game that invents its own rig renders the same tiles differently.
        # What a race adds to it is its own air, because a baked world is a few
        # kilometres across and then it stops.
        self.sg = SceneGraph(children=[
            environment.horizon_background(),
            race_fog(),
            *ViewerContext.defaultLights(WORLD_LIGHT_SCALE),
            world.terrain,
            self.session.car.node,
        ])
        if world.traffic is not None:
            # Mounted once; the cars under it come and go as the player passes.
            self.sg.children.append(world.traffic.node)
        self.hud = RaceHUD()
        self.hud.visible = self.config.hud
        self.hud.route(world.course)
        self.addHUDLayer(self.hud)
        self._bind_keys()

    def _driver(self) -> Any:                    # pragma: no cover - needs a window
        """Whoever is driving: the autopilot, or whoever is at the keyboard."""
        if self.config.autopilot:
            assert self.session is not None
            return Autopilot(self.session.course, lane=self.session.lane)
        self.keyboard = KeyboardDriver(
            MouseWheel() if getattr(self.config, 'mouse', False) else None)
        return self.keyboard

    def _bind_keys(self) -> None:                # pragma: no cover - needs a window
        for names in CONTROLS.values():
            for name in names:
                for state in (1, 0):
                    self.addEventHandler('keyboard', name=name, state=state,
                                         function=self._on_key)
        if self.keyboard is not None and self.keyboard.pointer is not None:
            self.addEventHandler('mousemove', function=self._on_pointer)
        self.addEventHandler('keypress', name='c', function=self._on_camera)
        self.addEventHandler('keypress', name='r', function=self._on_reset)
        self.addEventHandler('keypress', name='n', function=self._on_restart)

    # -- input -----------------------------------------------------------------

    def _on_key(self, event: Any) -> None:       # pragma: no cover - needs a window
        name = getattr(event, 'name', None)
        if name is None or self.keyboard is None:
            return
        if getattr(event, 'state', 0):
            self.keyboard.press(name)
        else:
            self.keyboard.release(name)
        self.triggerRedraw(1)

    def _on_pointer(self, event: Any) -> None:   # pragma: no cover - needs a window
        """The pointer moved: the wheel is where it is across the window."""
        if self.keyboard is None or self.keyboard.pointer is None:
            return
        wheel = self.keyboard.pointer
        width, _height = self.getViewPort()
        wheel.resize(int(width or wheel.width))
        wheel.moved(int(event.getPickPoint()[0]))

    def _on_camera(self, event: Any) -> None:    # pragma: no cover - needs a window
        assert self.session is not None
        self.session.camera.cycle()
        self.triggerRedraw(1)

    def _on_reset(self, event: Any) -> None:     # pragma: no cover - needs a window
        assert self.session is not None
        self.session.return_to_track()

    def _on_restart(self, event: Any) -> None:   # pragma: no cover - needs a window
        assert self.session is not None
        self.session.restart()

    # -- the frame -------------------------------------------------------------

    def OnIdle(self, *args: Any) -> int:         # pragma: no cover - needs a window
        now = systemTime()
        elapsed = now - self._clock
        self._clock = now
        self.advance(elapsed)
        self.triggerRedraw(1)
        return 1

    def advance(self, elapsed: float) -> None:   # pragma: no cover - needs a window
        """One frame of the run, and the window pointed at what it says."""
        assert self.session is not None
        self.session.viewport = self.getViewPort()
        pose = self.session.advance(elapsed)
        self._aim(pose)
        self._update_hud()

    def _aim(self, pose: Any) -> None:           # pragma: no cover - needs a window
        from OpenGLContext import quaternion
        self.platform.setPosition(tuple(float(v) for v in pose.position))
        aim = (quaternion.fromXYZR(1, 0, 0, -pose.pitch())
               * quaternion.fromXYZR(0, 1, 0, pose.heading()))
        self.platform.setOrientation(aim)

    def _update_hud(self) -> None:               # pragma: no cover - needs a window
        if self.hud is None or self.session is None:
            return
        reading = self.session.readout()
        self.hud.show(speed_kph=reading.speed_kph, timing=reading.timing,
                      off=reading.off, ended=reading.ended, at=reading.at,
                      others=reading.others, phase=reading.phase,
                      lit=reading.lit, lights=reading.lights)

    def SwapBuffers(self, *args: Any) -> Any:    # pragma: no cover - needs a window
        """Present the frame, and take the picture when one is asked for.

        A capture is settled by *drawn frames*, so it is ticked here rather than
        on a clock: the world streams in while the count runs, and the picture
        is of a world that has arrived. A recording takes the same frame, for
        the same reason: the back buffer holds it only until it is swapped away.
        """
        if self.recording:
            self.tickRecording()
        capture = getattr(self, '_capture', None)
        if capture is not None and capture.tick():
            result = super().SwapBuffers(*args)
            self.setCurrent()
            sys.stdout.write('captured %s\n' % (self.config.capture,))
            # What the drive cost, machine-readably: a picture that is unchanged
            # while the frame rate has halved is still a regression, and the
            # numbers in the README are measured this way.
            counter = getattr(self, 'frameCounter', None)
            if counter is not None:
                sys.stdout.write('DRIVE_STATS fps=%s\n' % (counter.recentFps(),))
            sys.stdout.flush()
            self._shutdown()
            os._exit(0)
            return result
        return super().SwapBuffers(*args)

    def OnQuit(self, *args: Any) -> None:        # pragma: no cover - needs a window
        # Finish the file first: a recording closed after the world has gone is
        # a recording missing its last frames and its sample tables.
        if self.recorder is not None:
            self.recorder.close()
            self.recorder = None
        self._shutdown()
        super().OnQuit(*args)

    def _shutdown(self) -> None:                 # pragma: no cover - needs a window
        if self.session is not None:
            self.session.world.shutdown()


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
        epilog=__doc__[__doc__.index('Keys::'):__doc__.index('The world streams')])
    parser.add_argument('world', nargs='?', default='baked-world/tileset.json',
                        help='the tileset.json of a baked world '
                             '(default: %(default)s)')
    parser.add_argument('--sse', type=float, default=12.0,
                        help='screen-space error the world refines to; lower is '
                             'sharper and slower (default: %(default)s)')
    parser.add_argument('--hud', action=argparse.BooleanOptionalAction,
                        default=True, help='draw the speed and lap readouts')
    parser.add_argument('--mouse', action='store_true',
                        help='steer with the pointer: where it is across the '
                             'window is where the wheel is')
    parser.add_argument('--laps', type=int, default=RACE_LAPS, metavar='N',
                        help='how many laps the race is; 0 drives on with no '
                             'finish (default: %(default)s)')
    parser.add_argument('--traffic', type=int, default=0, metavar='CARS',
                        help='how many other cars are on the road at once; '
                             'the default is an empty circuit, which is what a '
                             'timed lap is')
    parser.add_argument('--autopilot', action='store_true',
                        help='let the car drive itself round the circuit')
    parser.add_argument('--size', default='1280x720', metavar='WxH',
                        help='window size (default: %(default)s)')
    parser.add_argument('--view', choices=VIEWS, default=VIEWS[0],
                        help='which view to start in, which `c` then cycles '
                             '(default: %(default)s)')
    parser.add_argument('--capture', metavar='PATH',
                        help='render to PATH (PNG) once the world has settled, '
                             'then exit')
    parser.add_argument('--capture-delay', type=float, default=4.0,
                        metavar='SECONDS',
                        help='how long to let the world stream in before '
                             '--capture (default: %(default)s)')
    parser.add_argument('--record', metavar='PATH',
                        help='record the drive to PATH (an .mp4) and exit when '
                             'the recording is done')
    parser.add_argument('--record-seconds', type=float, default=20.0,
                        metavar='SECONDS',
                        help='how long a recording runs for '
                             '(default: %(default)s)')
    parser.add_argument('--record-fps', type=int, default=60, metavar='FPS',
                        help='frames a second in the recording; the world is '
                             'advanced by exactly one frame of time per frame '
                             'recorded (default: %(default)s)')
    parser.add_argument('--record-delay', type=float, default=6.0,
                        metavar='SECONDS',
                        help='let the world stream in for this long before the '
                             'recording starts (default: %(default)s)')
    parser.add_argument('--record-bitrate', type=int, default=0, metavar='BITS',
                        help='bits a second; 0 lets the encoder choose from the '
                             'frame size and rate')
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
    if options.record:
        _record(options, int(width), int(height))
        return 0
    GlisteelContext.ContextMainLoop(size=(int(width), int(height)))
    return 0


def _record(options: Any, width: int, height: int) -> None:  # pragma: no cover
    """Drive, recording the drive to a video file, and exit when it is done.

    The recording drives the clock: the world is advanced by exactly one frame
    of time for every frame written, so the video is smooth whatever the frame
    rate was and the same drive records the same way twice. What that costs is
    that the run is no longer real time -- a heavy frame takes as long as it
    takes -- which is why this is a mode rather than something the game does
    while someone is playing it.
    """
    encoder: dict[str, Any] = {}
    if options.record_bitrate:
        encoder['bitrate'] = options.record_bitrate

    class RecordingContext(GlisteelContext):
        config = options

        def OnInit(self) -> None:
            super().OnInit()
            self.setupRecording(
                options.record, fps=options.record_fps,
                seconds=options.record_seconds, start_after=options.record_delay,
                **encoder)

    RecordingContext.ContextMainLoop(size=(width, height))


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
            assert self.session is not None
            if options.drive_seconds:
                # A picture of a car going somewhere is not a picture of a
                # standing start, so the lights are dropped and the throttle
                # goes down. Without it the picture is of the grid, which is
                # what a track wants for its own portrait.
                self.session.run.go()
                if self.keyboard is not None:
                    for name in CONTROLS['throttle']:
                        self.keyboard.press(name)
            self._capture = SettleCapture(
                options.capture,
                delay=options.capture_delay + options.drive_seconds,
                min_frames=30)

    CapturingContext.ContextMainLoop(size=(width, height))


if __name__ == '__main__':                       # pragma: no cover - module entry
    sys.exit(main())
