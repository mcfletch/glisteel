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
    escape              the menu
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
import dataclasses
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

import numpy as np

os.environ.setdefault('OPENGLCONTEXT_PROFILE', 'core')
os.environ.setdefault('OPENGLCONTEXT_BACKEND', 'glfw')
os.environ.setdefault('OPENGLCONTEXT_RENDERER', 'pbr')

from OpenGLContext import quaternion, testingcontext  # noqa: E402
from OpenGLContext.events.systemtime import systemTime  # noqa: E402
from OpenGLContext.scenegraph.scenegraph import SceneGraph  # noqa: E402
from OpenGLContext.ui.overlay import OverlayMixin  # noqa: E402
from OpenGLContext.video.recorder import RecordingMixin  # noqa: E402
from OpenGLContext.viewer import environment  # noqa: E402
from OpenGLContext.viewer.sceneviewer import ViewerContext  # noqa: E402

from glisteel import (  # noqa: E402
    menu,
    schemes,  # noqa: E402
    tracks,
)
from glisteel.assist import STRENGTH as ASSIST  # noqa: E402
from glisteel.camera import VIEWS  # noqa: E402
from glisteel.car import CarSpec  # noqa: E402
from glisteel.driver import (  # noqa: E402
    PACE,  # noqa: E402
    RACING_KPH,
    Autopilot,
    DriverStyle,
    StandIn,
)
from glisteel.hud import RaceHUD  # noqa: E402
from glisteel.lighting import (  # noqa: E402
    BEAM_COLOUR,
    LAMP_COLOUR,
    Headlights,
)
from glisteel.options import DEFAULT_SIZE, Options, window_size  # noqa: E402
from glisteel.records import Records  # noqa: E402
from glisteel.session import RACE_LAPS, Session  # noqa: E402
from glisteel.steering import CONTROLS, KeyboardDriver, MouseWheel  # noqa: E402
from glisteel.traffic import DEFAULT_TRAFFIC  # noqa: E402
from glisteel.world import RaceWorld  # noqa: E402

log = logging.getLogger(__name__)
BaseContext: Any = testingcontext.getInteractive()

#: What the keys do, for ``--help``. Its own constant rather than a slice cut
#: out of the module docstring by searching for two phrases in it: rewording the
#: docstring would then raise at startup, which is a long way from where anybody
#: would look for the cause.
KEYS = """Keys::

    up / w              throttle
    down / s            brake, and reverse once stopped
    left / right, a / d steer
    space               handbrake
    mouse               steer, with --mouse
    c                   cockpit / chase / bonnet camera
    r                   put the car back on the track
    n                   a fresh race, from the grid
    escape              the menu
    F2                  save a screenshot
"""

#: The scale the default light rig is sized to. A world is kilometres across
#: and the rig's fill light is placed as a multiple of this, so it is the size
#: of the *scene the player is in* rather than of the whole map.
WORLD_LIGHT_SCALE = 120.0

#: How far a driver can see before the air takes the view, in metres. Far
#: enough to place the car for the corner after next; close enough that the far
#: side of a baked world is haze rather than a line where the ground stops.
VISIBILITY = 1800.0

#: How long a track is driven for before its own picture is taken, in seconds.
#: Far enough off the grid that the picture is of the world rather than of a
#: start line, which every world has and none is recognised by.
PICTURE_SECONDS = 25.0

#: How far one tunnel luminaire's real light reaches, in metres, how hard it
#: burns, and how it falls off with distance. Short, and falling off with the
#: square of the distance the way a real lamp does: what lights the *lining* is
#: baked into it, and this is only for the car and the road under the fitting.
#: Without the square term a lamp lights the whole bore evenly and the tunnel
#: comes out as a brightly lit corridor rather than a dark one with lamps in it.
#:
#: Low, for the same reason. The lining already carries the pool this lamp
#: throws, so anything this adds to the *walls* is that lamp counted twice --
#: and a bore whose walls are lit twice is a white corridor rather than the
#: dark one a headlight is worth having in.
LAMP_REACH = 30.0
LAMP_INTENSITY = 0.9
LAMP_FALLOFF = (1.0, 0.0, 0.02)


class GlisteelContext(RecordingMixin, OverlayMixin, BaseContext):
    """The game window: a run to advance, a scene to draw, and keys to deliver."""

    #: What this run was asked for. Checked once, at the command line.
    config: Options = None      # type: ignore[assignment]
    #: The run this window is showing.
    session: Session | None = None
    _capture: Any = None
    #: Whoever is at the keyboard, or None while the autopilot is driving.
    keyboard: KeyboardDriver | None = None
    hud: Any = None
    #: Which world is loaded, or None while the menu is up.
    track: Any = None
    #: The player's best times, kept between sessions.
    records: Any = None
    #: Whether the finish screen has been shown for the run now over.
    _told: bool = False
    #: The lights the car carries and the ones the world lends it.
    headlights: Any = None
    _beam: Any = None
    _lamps: Any = None
    #: The video being written, or None. Declared because the mixin that owns it
    #: is untyped, and mypy cannot otherwise tell what it holds.
    recorder: Any = None
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
        self.records = Records()
        self.hud = RaceHUD()
        self.addHUDLayer(self.hud)
        self._show_hud()
        self._bind_keys()
        self.sg = SceneGraph(children=[environment.horizon_background()])
        track = self._opening_track()
        if track is None:
            self.show_menu()
        else:
            self.open(track)

    def _opening_track(self) -> Any:             # pragma: no cover - needs a window
        """Which world to open, or None to offer a choice.

        The one named on the command line if it is there; otherwise the
        player's library, which is offered rather than guessed at -- except
        where it holds exactly one, since choosing between one thing is not a
        choice.
        """
        found = tracks.Track.opening(self.config.world)
        if found is not None:
            return found
        library = tracks.library()
        return library[0] if len(library) == 1 else None

    def open(self, track: Any) -> None:          # pragma: no cover - needs a window
        """Load a world and stand a car on its grid.

        A track that cannot be raced -- moved, half-baked, or baked without a
        circuit in it -- leaves the game where it was with the menu up and the
        reason under the title. A chooser offers whatever is on disk, so picking
        one of those is something a player does, not a reason to stop.
        """
        try:
            world = self._world_for(track)
        except (OSError, ValueError) as error:
            log.warning('%s', error)
            self.show_menu(subtitle=str(error))
            return
        self.close()
        self.track = track
        self.session = Session(world, CarSpec(),
                               view=self.config.view,
                               laps=self.config.laps,
                               assist=self.config.assist)
        self.session.driver = self._driver()
        self._told = False
        # The engine's own sky and light rig, rather than one written here: a
        # world baked for the viewer is lit the way the viewer lights it, and a
        # game that invents its own rig renders the same tiles differently.
        # What a race adds to it is its own air, because a baked world is a few
        # kilometres across and then it stops.
        self.sg.children = [
            environment.horizon_background(),
            race_fog(),
            *ViewerContext.defaultLights(WORLD_LIGHT_SCALE),
            world.terrain,
            self.session.car.node,
        ]
        if world.traffic is not None:
            # Mounted once; the cars under it come and go as the player passes.
            self.sg.children.append(world.traffic.node)
        self._light_the_car(world)
        self.hud.route(world.course)
        self._show_hud()

    def _world_for(self, track: Any) -> Any:     # pragma: no cover - needs a window
        """The world a track carries, or the reason it is not one to race on."""
        world = RaceWorld(track.tileset, max_sse=self.config.sse,
                          traffic=self.config.traffic)
        fault = opening_fault(world, track)
        if fault is not None:
            world.shutdown()
            raise ValueError(fault)
        return world

    def _light_the_car(self, world: Any) -> None:  # pragma: no cover - a window
        """Mount the lights that move: the beam, and the lamps of a bore.

        Mounted once and moved, rather than made and unmade as the car passes:
        a light is a shader slot, and a scenegraph that gains and loses one
        every twenty-five metres recompiles for it.
        """
        from OpenGLContext.scenegraph.light import PointLight, SpotLight
        self.headlights = Headlights(
            fitted=self.config.headlights)
        self._beam = SpotLight(color=BEAM_COLOUR,
                               intensity=self.headlights.intensity,
                               cutOffAngle=self.headlights.spread,
                               beamWidth=self.headlights.spread * 0.5,
                               radius=self.headlights.reach,
                               attenuation=(1.0, 0.0, 0.0), castShadows=False)
        self._beam.on = False
        # One point light per luminaire slot, dark until the car is among them.
        self._lamps = [
            PointLight(color=LAMP_COLOUR, intensity=0.0,
                       radius=LAMP_REACH, attenuation=LAMP_FALLOFF,
                       castShadows=False)
            for _ in range(world.luminaires.count)]
        for lamp in self._lamps:
            lamp.on = False
        self.sg.children.append(self._beam)
        self.sg.children.extend(self._lamps)

    def _move_the_lights(self) -> None:          # pragma: no cover - needs a window
        """Point the beam where the car is going, and put the world's lamps
        where the nearest fittings are."""
        assert self.session is not None
        car = self.session.car
        dark = self.session.in_the_dark()
        if self._beam is not None:
            burning = self.headlights.wanted(dark)
            self._beam.on = burning
            if burning:
                offset = np.asarray(self.headlights.offset, dtype='d')
                forward = np.asarray(car.forward(), dtype='d')
                across = np.cross(forward, (0.0, 1.0, 0.0))
                self._beam.location = tuple(
                    car.position + forward * -offset[2]
                    + across * offset[0] + np.array([0.0, offset[1], 0.0]))
                self._beam.direction = tuple(self.headlights.aim(forward))
        if not self._lamps:
            return
        # Not gated on being in a bore: a lamp is dark long before the car
        # is out of one, so distance is what turns them off and there is no
        # threshold at the portal for them to be switched at.
        wanted = self.session.world.luminaires.burning(car.position)
        for slot, lamp in enumerate(self._lamps):
            if slot < len(wanted):
                index, share = wanted[slot]
                lamp.location = tuple(
                    self.session.world.luminaires.at(index))
                lamp.intensity = LAMP_INTENSITY * share
                lamp.on = True
            else:
                lamp.on = False
                lamp.intensity = 0.0

    def close(self) -> None:                     # pragma: no cover - needs a window
        """Put away whatever world is loaded."""
        if self.session is not None:
            self.session.world.shutdown()
        self.session = None
        self._beam = None
        self._lamps = None
        self.sg.children = [environment.horizon_background()]
        self._show_hud()

    def _show_hud(self) -> None:                 # pragma: no cover - needs a window
        """The read-outs belong to a car. With no world there is nothing to read."""
        if self.hud is not None:
            self.hud.visible = bool(self.config.hud and self.session is not None)

    # -- the screens -----------------------------------------------------------

    def show_menu(self, event: Any = None,
                  subtitle: str | None = None) -> None:  # pragma: no cover - a window
        """The menu, over whatever is behind it.

        A second one pushed over the first would leave two, so an open one is
        found rather than replaced. ``subtitle`` says why it is up, for the menu
        that comes back when a track could not be opened.
        """
        if self.overlays.named('menu') is not None:
            return
        racing = self.session is not None
        if subtitle is None:
            subtitle = self.track.name if self.track is not None else ''
        panel = menu.main_menu(
            on_drive=self._on_drive, on_tracks=self.show_tracks,
            on_settings=self._on_settings, on_quit=self._on_quit,
            on_resume=self._on_resume if racing else None,
            subtitle=subtitle)
        panel.name = 'menu'
        self.pushOverlay(panel)

    def show_tracks(self) -> None:               # pragma: no cover - needs a window
        """The library, as a band of pictures. Replaces the menu, not over it."""
        self._drop_menu()
        found = tracks.library()
        best = {track.key: self.records.record(track.key) for track in found}
        self.pushOverlay(menu.track_screen(
            found, chosen=self.track,
            records={key: one for key, one in best.items() if one is not None},
            on_choose=self._on_track, on_cancel=self.show_menu))

    def show_finish(self, result: Any, place: Any) -> None:  # pragma: no cover
        """What the race came to, and what to do next.

        Over the world it was driven in and nothing else: a menu left standing
        behind this would be two screens asking at once.
        """
        self._drop_menu()
        key = self.track.key if self.track is not None else ''
        self.pushOverlay(menu.finish_screen(
            result, place=place, records=self.records.best(key),
            track=self.track, on_again=self._on_again,
            on_tracks=self.show_tracks, on_quit=self._on_quit))

    def _drop_menu(self) -> None:                # pragma: no cover - needs a window
        panel = self.overlays.named('menu')
        if panel is not None:
            self.overlays.remove(panel)

    def _on_resume(self) -> None:                # pragma: no cover - needs a window
        self._drop_menu()

    def _on_drive(self) -> None:                 # pragma: no cover - needs a window
        self._drop_menu()
        if self.session is None:
            self.show_tracks()
        else:
            self.session.restart()

    def _on_again(self) -> None:                 # pragma: no cover - needs a window
        if self.session is not None:
            self.session.restart()
        self._told = False

    def _on_track(self, track: Any) -> None:     # pragma: no cover - needs a window
        self.open(track)

    def _on_settings(self) -> None:              # pragma: no cover - needs a window
        from OpenGLContext.ui import settings
        self._drop_menu()
        settings.open_settings(self)

    def _on_quit(self) -> None:                  # pragma: no cover - needs a window
        self.OnQuit()

    def _record(self, result: Any) -> Any:       # pragma: no cover - needs a window
        """Offer this race's best lap to the table; answer where it came."""
        if result.seconds is None or self.track is None:
            return None
        place = self.records.offer(self.track.key, result.seconds)
        if place is not None:
            self.records.save()
        return place

    def _driver(self) -> Any:                    # pragma: no cover - needs a window
        """Whoever is driving, and the keys to deliver to them."""
        assert self.session is not None
        driver = driver_for(self.config, self.session)
        self.keyboard = (driver.source
                         if isinstance(driver, schemes.ControlScheme) else None)
        return driver

    def _bind_keys(self) -> None:                # pragma: no cover - needs a window
        """Ask the runtime for every event the game acts on.

        Made once, from :func:`bindings`, and unconditionally: the bindings are
        put in before a world is open, so anything decided here about whoever is
        driving would be decided before there is one. Each handler guards itself
        instead.
        """
        for one in bindings():
            named = {'function': getattr(self, one.handler)}
            if one.name is not None:
                named['name'] = one.name
            if one.state is not None:
                named['state'] = one.state
            self.addEventHandler(one.kind, **named)

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
        if self.session is None:
            return
        self.session.camera.cycle()
        self.triggerRedraw(1)

    def _on_reset(self, event: Any) -> None:     # pragma: no cover - needs a window
        if self.session is None:
            return
        self.session.return_to_track()

    def _on_restart(self, event: Any) -> None:   # pragma: no cover - needs a window
        if self.session is None:
            return
        self.session.restart()
        self._told = False

    # -- the frame -------------------------------------------------------------

    def OnIdle(self, *args: Any) -> int:         # pragma: no cover - needs a window
        now = systemTime()
        elapsed = now - self._clock
        self._clock = now
        if self.session is not None:
            self.advance(elapsed)
        self.triggerRedraw(1)
        return 1

    def advance(self, elapsed: float) -> None:   # pragma: no cover - needs a window
        """One frame of the run, and the window pointed at what it says."""
        assert self.session is not None
        self.session.viewport = self.getViewPort()
        pose = self.session.advance(elapsed)
        self._aim(pose)
        self._move_the_lights()
        self._update_hud()
        self._tell_them_how_it_went()

    def _tell_them_how_it_went(self) -> None:    # pragma: no cover - needs a window
        """Put the finish up, once, when the race stops being one."""
        assert self.session is not None
        result = self.session.result()
        if result is None:
            self._told = False
            return
        if self._told:
            return
        self._told = True
        self.show_finish(result, self._record(result))

    def _aim(self, pose: Any) -> None:           # pragma: no cover - needs a window
        self.platform.setPosition(tuple(float(v) for v in pose.position))
        aim = (quaternion.fromXYZR(1, 0, 0, -pose.pitch())
               * quaternion.fromXYZR(0, 1, 0, pose.heading()))
        self.platform.setOrientation(aim)

    def _update_hud(self) -> None:               # pragma: no cover - needs a window
        if self.hud is None or self.session is None:
            return
        self.hud.show(self.session.readout())

    def presentFrame(self) -> Any:               # pragma: no cover - needs a window
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
            result = super().presentFrame()
            self.setCurrent()
            sys.stdout.write('captured %s\n' % (self.config.capture,))
            wanted = self.config.picture_track
            if wanted is not None:
                where = tracks.remember_picture(wanted)
                if where is not None:
                    sys.stdout.write('recorded it in %s\n' % (where,))
            # What the drive cost, machine-readably: a picture that is unchanged
            # while the frame rate has halved is still a regression, and the
            # numbers in the README are measured this way.
            counter = getattr(self, 'frameCounter', None)
            if counter is not None:
                sys.stdout.write('DRIVE_STATS fps=%s\n' % (counter.recentFps(),))
            sys.stdout.flush()
            self._finish()
            # Straight out, rather than back into a main loop that is mid-frame
            # and has just been told to present one: the backend owns the loop
            # and offers no way to leave it from inside presenting a frame.
            # Every teardown that matters has happened above, which is what
            # :meth:`_finish` is for.
            os._exit(0)
            return result
        return super().presentFrame()

    def OnQuit(self, *args: Any) -> None:        # pragma: no cover - needs a window
        self._finish()
        super().OnQuit(*args)

    def _finish(self) -> None:                   # pragma: no cover - needs a window
        """Put everything down, whichever way the game is ending.

        Both ways end here -- the player quitting and a capture exiting once it
        has its frame -- because they were not doing the same thing: the capture
        path left a recording unclosed, which is a file missing its last frames
        and its sample tables.

        The recording first: one closed after the world has gone is missing the
        same thing.
        """
        if self.recorder is not None:
            self.recorder.close()
            self.recorder = None
        self.close()


def driver_for(config: Any, session: Any) -> Any:
    """Whoever is driving a run set up like this.

    The autopilot where the car drives itself, and otherwise the way of driving
    the player asked for (:mod:`glisteel.schemes`) over the keys and, where
    ``--mouse`` says so, the pointer. Here rather than in the window because
    which driver a command line asks for is a decision, and one made inside a
    window is a decision no test can ask about -- which is how ``--mouse`` came
    to be a documented control that was never connected to anything.
    """
    scheme = schemes.named(config.control, trim=config.assist,
                           pointer=MouseWheel() if config.mouse else None)
    if not config.autopilot:
        return scheme
    # A way of driving that steers for the driver is a way of driving to be
    # judged, so the autopilot drives it the way a player would -- through the
    # controls. Where the steering *is* the wheel there is nothing to judge in
    # pressing a key to wind one, and it steers directly.
    if scheme.holds_the_line:
        # Racing, not driving: what it aims for on an open road is
        # :data:`~glisteel.driver.RACING_KPH` rather than the speed a driver
        # going somewhere would pick, and ``--pace`` is the fraction of that
        # and of every corner it asks for.
        return StandIn(scheme, lane=session.lane,
                       style=DriverStyle(margin=config.pace,
                                         maximum_speed=RACING_KPH / 3.6))
    # ``--pace`` is how hard the car drives itself, and it means that whichever
    # way it is being driven: steering directly is not a reason to drive at the
    # limit of the tyres, and a driver with nothing in hand runs wide the first
    # time anything puts it off its line.
    return Autopilot(session.course, lane=session.lane,
                     style=DriverStyle(margin=config.pace))


@dataclass(frozen=True)
class Binding:
    """One event the window asks the runtime for.

    ``kind`` is the event, ``name`` the key or None for one that has none,
    ``state`` 1 for going down and 0 for coming up (None where it does not
    matter), and ``handler`` the name of the method to call.
    """

    kind: str
    handler: str
    name: str | None = None
    state: int | None = None


def bindings() -> tuple[Binding, ...]:
    """Every event the game acts on, as a table.

    Worked out here rather than in the window because a binding that is never
    made is a control that silently does nothing: nothing raises, and the key or
    the pointer simply has no effect. A table is something a test can read.

    Nothing here is conditional. The bindings go in as the window is built,
    before a world is open and therefore before there is anybody driving, so a
    binding that asked about the driver would always get the same answer --
    which is how ``--mouse`` came to be a documented control that was never
    connected to anything. The pointer handler guards itself
    (:meth:`GlisteelContext._on_pointer`), and a pointer event with no wheel to
    turn costs a comparison.
    """
    found = [Binding('keyboard', '_on_key', name=name, state=state)
             for names in CONTROLS.values() for name in sorted(names)
             for state in (1, 0)]
    found.append(Binding('mousemove', '_on_pointer'))
    found.extend([Binding('keypress', '_on_camera', name='c'),
                  Binding('keypress', '_on_reset', name='r'),
                  Binding('keypress', '_on_restart', name='n'),
                  Binding('keyboard', 'show_menu', name='<escape>', state=1)])
    return tuple(found)


def opening_fault(world: Any, track: Any) -> str | None:
    """Why this world is not one to race on, or None if it is.

    Separate from the window because it is a question about a world and a track
    and has no picture in it: what the window does with the answer is put it in
    front of the player.
    """
    if world.course is None:
        return ("%s carries no roads, so there is nothing to race on. Bake a "
                "world with a circuit in it." % track.tileset)
    return None


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
        epilog=KEYS)
    parser.add_argument('world', nargs='?', default='baked-world/tileset.json',
                        help='the tileset.json of a baked world. Without one, '
                             'the game offers whatever is in the track library '
                             '(default: %(default)s)')
    parser.add_argument('--sse', type=float, default=12.0,
                        help='screen-space error the world refines to; lower is '
                             'sharper and slower (default: %(default)s)')
    parser.add_argument('--hud', action=argparse.BooleanOptionalAction,
                        default=True, help='draw the speed and lap readouts')
    parser.add_argument('--mouse', action='store_true',
                        help='steer with the pointer: where it is across the '
                             'window is where the wheel is. Goes with any '
                             '--control')
    parser.add_argument('--control', choices=schemes.available(),
                        default=schemes.DEFAULT, metavar='WAY',
                        help='how the steering is driven: %s (default: '
                             '%%(default)s)'
                             % '; '.join('%s, %s' % (one, schemes.named(one).summary)
                                         for one in schemes.available()))
    parser.add_argument('--headlights', action=argparse.BooleanOptionalAction,
                        default=True,
                        help='the light the car carries into a bore')
    parser.add_argument('--assist', type=float, default=ASSIST, metavar='FRACTION',
                        help='how much of the steering the car does for you '
                             'while you are not steering: 0 hands it back '
                             'entirely, 1 holds the line for you '
                             '(default: %(default)s)')
    parser.add_argument('--laps', type=int, default=RACE_LAPS, metavar='N',
                        help='how many laps the race is; 0 drives on with no '
                             'finish (default: %(default)s)')
    parser.add_argument('--traffic', type=int, default=DEFAULT_TRAFFIC,
                        metavar='CARS',
                        help='how many other cars are on the road at once. '
                             'Traffic is what makes one lap different from the '
                             'last; 0 is an empty circuit, which is what a '
                             'timed lap is (default: %(default)s)')
    parser.add_argument('--autopilot', action='store_true',
                        help='let the car drive itself round the circuit. With '
                             'a --control that steers for the driver it drives '
                             'through the controls, the way a player does')
    parser.add_argument('--pace', type=float, default=PACE, metavar='FRACTION',
                        help='how hard it drives itself when it is driving '
                             'through the controls, as a fraction of what the '
                             'road allows (default: %(default)s)')
    parser.add_argument('--size', default=DEFAULT_SIZE, type=window_size,
                        metavar='WIDTHxHEIGHT',
                        help='window size (default: %dx%d)' % DEFAULT_SIZE)
    parser.add_argument('--view', choices=VIEWS, default=VIEWS[0],
                        help='which view to start in, which `c` then cycles '
                             '(default: %(default)s)')
    parser.add_argument('--picture', action='store_true',
                        help="take this track's own picture: drive it, "
                             'photograph the car on it, and record the picture '
                             'in the world manifest so a chooser can show it')
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


def main(argv: list[str] | None = None) -> int:
    """Run the game; answer the status a shell should see.

    The world named on the command line is opened here rather than in the
    window, so that a path which is not a world is a sentence on stderr and a
    non-zero status -- what a shell script wants -- while the same failure
    reached from the track chooser is a message on the menu and a game that goes
    on running (:meth:`GlisteelContext.open`).
    """
    logging.basicConfig(level=logging.INFO)
    parsed = build_parser().parse_args(argv)
    try:
        options = Options.from_namespace(parsed)
    except ValueError as error:
        sys.stderr.write('%s\n' % (error,))
        return 2
    width, height = options.size
    GlisteelContext.config = options
    named = tracks.Track.opening(options.world)
    if named is None and options.world != _default_world():
        # Asked for a particular world by name and it is not there. Without a
        # name the library is offered instead, which is not a failure.
        sys.stderr.write(
            'no world at %s -- bake one with %r\n'
            % (options.world,
               'oglc-bake --output %s' % (os.path.dirname(options.world)
                                          or 'world',)))
        return 1
    return _run(options, width, height)               # pragma: no cover - a window


def _default_world() -> str:
    """The world the command line assumes when nobody names one."""
    return str(build_parser().get_default('world'))


def _run(options: Any, width: int, height: int) -> int:  # pragma: no cover
    """Whichever of the modes the options asked for."""
    if options.picture:
        _picture(options, width, height)
        return 0
    if options.capture:
        _capture(options, width, height)
        return 0
    if options.record:
        _record(options, width, height)
        return 0
    GlisteelContext.ContextMainLoop(size=(width, height))
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


def _picture(options: Any, width: int, height: int) -> None:  # pragma: no cover
    """Take a track's own picture and record it in the world's manifest.

    A chooser shows each world by what it looks like, and only the world can
    say what that is. So the game drives it -- a car going somewhere, from
    behind, which is the view a player recognises the place from -- photographs
    that, and writes the picture's name into the manifest beside the tileset.
    """
    track = tracks.Track.opening(options.world)
    if track is None:
        raise SystemExit('%s is not a world to photograph' % options.world)
    # A copy rather than the settings the player asked for, so what --picture
    # overrides is visible here rather than discovered by whatever reads it
    # next; ``replace`` re-checks the result the way any other Options is.
    _capture(dataclasses.replace(
        options, capture=os.path.join(track.directory, tracks.PICTURE),
        view='chase', autopilot=True, picture_track=track,
        drive_seconds=options.drive_seconds or PICTURE_SECONDS),
        width, height)


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
            if options.drive_seconds and self.session is not None:
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
