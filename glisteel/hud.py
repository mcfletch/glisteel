"""What the driver is told, and where on the screen it goes.

Four readouts and nothing else. A racing HUD earns its space: the speed,
because it is the one number a driver acts on; the lap clock, because that is
what the lap is for; the last and best laps, because a lap is only meaningful
against another one; and a warning when the car is off the road, because at
speed that is not always obvious from the picture.
"""
from __future__ import annotations

from typing import Any

from OpenGLContext.ui.hudwidgets import HUDGroup, HUDLayer, Readout

__all__ = ['RaceHUD']

#: Speed above which the readout goes critical: the skin's warning colour, so
#: the driver's eye is caught by the number rather than having to read it.
FAST_KPH = 160.0


class RaceHUD(HUDLayer):
    """The race read-outs. Call :meth:`show` once a frame."""

    def __init__(self, **named: Any) -> None:
        super().__init__(**named)
        self.speed = Readout(anchor='bottom-right', align='right', label='KM/H')
        self.lap = Readout(label='LAP')
        self.best = Readout(label='BEST', value='--:--.---')
        self.last = Readout(label='LAST', value='--:--.---')
        self.warning = Readout(anchor='center', align='center', value='')
        # The three clocks are one block in the corner: anchored separately they
        # would each take the same corner and be drawn on top of one another.
        self.times = HUDGroup(anchor='top-left',
                              children=[self.lap, self.last, self.best])
        self.children = [self.times, self.speed, self.warning]

    def show(self, speed_kph: float, timing: Any = None,
             off: bool = False) -> None:
        """Put this frame's numbers on the readouts."""
        self.speed.value = '%3.0f' % max(0.0, speed_kph)
        self.speed.critical = bool(speed_kph >= FAST_KPH)
        if timing is not None:
            self.lap.value = '%d   %s' % (len(timing.laps) + 1,
                                          _clock(timing.current))
            self.last.value = timing.last.clock() if timing.last else '--:--.---'
            self.best.value = timing.best.clock() if timing.best else '--:--.---'
        self.warning.value = 'OFF TRACK' if off else ''
        self.warning.critical = bool(off)


def _clock(seconds: float) -> str:
    """A running lap time, as a driver reads it."""
    minutes, rest = divmod(max(0.0, seconds), 60.0)
    return "%d:%06.3f" % (int(minutes), rest)
