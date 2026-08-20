"""What the driver is told, and where on the screen it goes.

A racing HUD earns its space: the speed, because it is the one number a driver
acts on; the lap clock, because that is what the lap is for; the last and best
laps, because a lap is only meaningful against another one; a warning when the
car is off the road, because at speed that is not always obvious from the
picture; and the map, because a driver on an eight-kilometre circuit cannot see
round the next bend and has no idea how much of the lap is left.

Either end of the race there is one more thing, and only for a moment: the start
rig across the top while the car is held on the grid, and the result across the
middle once it is over. The rig is lamps
(:class:`~OpenGLContext.ui.hudwidgets.LampRow`) rather than a counting numeral,
because a driver reads it with their eyes on the road and a number would take
them off it.
"""
from __future__ import annotations

from typing import Any

from OpenGLContext.ui.hudwidgets import (
    HUDGroup,
    HUDLayer,
    LampRow,
    MiniMap,
    Readout,
)

from glisteel.run import COUNTDOWN, FINISHED

__all__ = ['RaceHUD', 'FAST_KPH', 'HOME']

#: Speed above which the readout goes critical: the skin's warning colour, so
#: the driver's eye is caught by the number rather than having to read it.
FAST_KPH = 160.0

#: What the middle of the screen says when the race has been driven home. The
#: time goes with it, because the word is what a driver sees and the time is
#: what they then read.
HOME = 'FINISHED'


class RaceHUD(HUDLayer):
    """The race read-outs. Call :meth:`show` once a frame."""

    def __init__(self, **named: Any) -> None:
        super().__init__(**named)
        self.speed = Readout(anchor='bottom-right', align='right', label='KM/H')
        self.lap = Readout(label='LAP')
        self.best = Readout(label='BEST', value='--:--.---')
        self.last = Readout(label='LAST', value='--:--.---')
        self.warning = Readout(anchor='center', align='center', value='')
        self.map = MiniMap(anchor='bottom-left')
        # Up where a driver looking at the road still catches it, and out of the
        # way of the result, which takes the middle a moment later.
        self.lights = LampRow(anchor='top-center', offset=(0.0, -40.0))
        self.lights.visible = False
        # The three clocks are one block in the corner: anchored separately they
        # would each take the same corner and be drawn on top of one another.
        self.times = HUDGroup(anchor='top-left',
                              children=[self.lap, self.last, self.best])
        self.children = [self.times, self.speed, self.warning, self.map,
                         self.lights]

    def route(self, course: Any) -> None:
        """The circuit the map draws. Set once; a world's shape does not change."""
        self.map.route = None if course is None else course.centreline
        self.map.closed = bool(course is not None and course.closed)

    def show(self, reading: Any) -> None:
        """Put one frame's numbers on the readouts.

        Handed a whole :class:`~glisteel.session.Readings` rather than its
        fields one at a time: it is exactly what a session answers with, and
        naming the fields again here meant two lists that had to agree and a
        third in the window copying between them.
        """
        self.speed.value = '%3.0f' % max(0.0, reading.speed_kph)
        self.speed.critical = bool(reading.speed_kph >= FAST_KPH)
        timing = reading.timing
        if timing is not None:
            self.lap.value = '%d   %s' % (len(timing.laps) + 1,
                                          _clock(timing.current))
            self.last.value = timing.last.clock() if timing.last else '--:--.---'
            self.best.value = timing.best.clock() if timing.best else '--:--.---'
        self._start_rig(reading.phase, reading.lit, reading.lights)
        self.warning.value = self._middle(reading.phase, timing,
                                          reading.ended, reading.off)
        self.warning.critical = bool(self.warning.value
                                     and reading.phase != FINISHED)
        marks = [(float(one[0]), float(one[2]), 'hudText')
                 for one in reading.others]
        if reading.at is not None:
            marks.append((float(reading.at[0]), float(reading.at[2]),
                          'crosshair'))
        self.map.marks = marks

    def _start_rig(self, phase: str, lit: int, lights: int) -> None:
        """The lamps, and only while there is a start to watch."""
        self.lights.visible = bool(phase == COUNTDOWN and lights)
        self.lights.count = int(lights)
        self.lights.lit = int(lit)

    def _middle(self, phase: str, timing: Any, ended: str | None,
                off: bool) -> str:
        """What takes the middle of the screen: the result, or a warning.

        The result outranks everything, because a race that is over is not one
        to be told about the road surface.
        """
        if phase == FINISHED:
            best = timing.best if timing is not None else None
            return '%s   %s' % (HOME, best.clock()) if best else HOME
        if ended:
            return ended.upper()
        return 'OFF TRACK' if off else ''


def _clock(seconds: float) -> str:
    """A running lap time, as a driver reads it."""
    minutes, rest = divmod(max(0.0, seconds), 60.0)
    return "%d:%06.3f" % (int(minutes), rest)
