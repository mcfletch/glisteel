"""What the game is configured by, checked once and in one place.

Everything a run needs arrives on a command line and is then read all over the
window. Reading it as an ``argparse`` namespace has two costs a checker cannot
help with: nothing knows what fields exist, so callers reach for them with
``getattr(config, name, default)`` and quietly write a *second* default beside
the parser's; and nothing checks the values, so a number that makes no sense --
a negative lap count, a steering aid of 1.5 -- reaches the physics rather than
the person who typed it.

So the namespace is turned into one of these as the game starts, and the window
reads this. It is a plain object with types on it, which means a test can build
one without a parser, and a mistake in the window is a checker error rather than
an attribute that silently was not there.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, fields
from typing import Any

from glisteel import schemes
from glisteel.assist import STRENGTH
from glisteel.camera import VIEWS
from glisteel.driver import PACE
from glisteel.session import RACE_LAPS
from glisteel.traffic import DEFAULT_TRAFFIC

__all__ = ['Options', 'window_size']

#: The window this game opens unless it is told otherwise.
DEFAULT_SIZE = (1280, 720)


def window_size(text: str) -> tuple[int, int]:
    """``WIDTHxHEIGHT`` as two numbers, or a usage error.

    An ``argparse`` type, so ``--size wide`` is the usage message argparse
    writes for every other malformed option rather than a traceback out of the
    middle of the program.
    """
    width, _, height = str(text).lower().partition('x')
    try:
        found = (int(width), int(height))
    except ValueError:
        raise argparse.ArgumentTypeError(
            '%r is not a window size; write one as WIDTHxHEIGHT, '
            'for example 1280x720' % (text,)) from None
    if found[0] < 1 or found[1] < 1:
        raise argparse.ArgumentTypeError(
            '%r is not a window size: both sides have to be at least one '
            'pixel' % (text,))
    return found


@dataclass
class Options:
    """One run's worth of settings, with the values checked.

    Built from a parsed command line by :meth:`from_namespace`, or directly by
    anything that wants to set a run up without one -- which is what a test
    wants, and what the window's own defaults are measured against.
    """

    #: The tileset to open. Everything else has a default; this does not,
    #: because without it there is nothing to say what is being driven.
    world: str

    #: Screen-space error the world refines to; lower is sharper and slower.
    sse: float = 12.0
    #: Whether the speed and lap read-outs are drawn.
    hud: bool = True
    #: Whether the pointer steers. A source rather than a way of driving, so
    #: it goes with any of them (:mod:`glisteel.schemes`).
    mouse: bool = False
    #: Which way of driving the car, by name.
    control: str = schemes.DEFAULT
    #: Whether the car carries a light into a bore.
    headlights: bool = True
    #: How much of the steering the game puts in while nobody is steering.
    assist: float = STRENGTH
    #: How many laps a race is; 0 drives on with no finish.
    laps: int = RACE_LAPS
    #: How many other cars are on the road at once.
    traffic: int = DEFAULT_TRAFFIC
    #: Whether the car drives itself.
    autopilot: bool = False
    #: How hard it drives itself, as a fraction of what the road allows, where
    #: it is driving through the controls (:class:`~glisteel.driver.StandIn`).
    pace: float = PACE
    #: Which view the run starts in, one of :data:`glisteel.camera.VIEWS`.
    view: str = VIEWS[0]
    #: The window, in pixels.
    size: tuple[int, int] = DEFAULT_SIZE

    # -- the modes that are not playing ---------------------------------------
    #: Take this track's own picture and record it in its manifest.
    picture: bool = False
    #: Render one frame to this path once the world has settled, then exit.
    capture: str | None = None
    capture_delay: float = 4.0
    #: Record the drive to this path (an ``.mp4``) and exit when it is done.
    record: str | None = None
    record_seconds: float = 20.0
    record_fps: int = 60
    record_delay: float = 6.0
    record_bitrate: int = 0
    #: Drive for this long before capturing, so the picture has a car going
    #: somewhere in it.
    drive_seconds: float = 0.0

    #: The track being photographed, once ``--picture`` has chosen one. Not
    #: something anybody types.
    picture_track: Any = None
    #: Where the last bake went, for the editor's "drive it".
    baked: str | None = field(default=None)

    def __post_init__(self) -> None:
        self.assist = _within('assist', float(self.assist), 0.0, 1.0)
        self.pace = _within('pace', float(self.pace), 0.05, 2.0)
        self.laps = _at_least('laps', int(self.laps), 0)
        self.traffic = _at_least('traffic', int(self.traffic), 0)
        self.sse = _at_least('sse', float(self.sse), 0.0)
        if self.control not in schemes.available():
            raise ValueError(
                'control is %r, which is not a way of driving; there is %s'
                % (self.control, ', '.join(schemes.available())))
        if self.view not in VIEWS:
            raise ValueError(
                'there is no view called %r; there is %s'
                % (self.view, ', '.join(VIEWS)))
        self.size = (int(self.size[0]), int(self.size[1]))

    @classmethod
    def from_namespace(cls, namespace: Any) -> Options:
        """The settings a parsed command line asked for.

        Only the fields declared above are taken, so an option the parser grew
        and nothing reads is a visible gap rather than a silent one.
        """
        wanted = {one.name for one in fields(cls)}
        return cls(**{name: value for name, value in vars(namespace).items()
                      if name in wanted})


def _within(name: str, value: float, low: float, high: float) -> float:
    if not low <= value <= high:
        raise ValueError('%s is %g, which is outside %g to %g'
                         % (name, value, low, high))
    return value


def _at_least(name: str, value: Any, low: Any) -> Any:
    if value < low:
        raise ValueError('%s is %s, which is less than %s' % (name, value, low))
    return value
