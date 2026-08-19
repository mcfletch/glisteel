"""A drive written down: which controls are held, and when.

A player's input is a square wave -- a key is down or it is not -- and a driver
that produces one is a different thing from an autopilot producing a smooth
signal. What makes a keyboard feel like a car is everything between the key and
the road, and none of it can be tested without being able to say *hold left for
four hundred milliseconds at fifty metres a second* and get the same answer
twice.

    >>> Script.parse('throttle 0..8; left 3..3.4')
    Script(throttle 0..8, left 3..3.4)

A script is a :class:`~glisteel.session.Controller`, so it drives a run the way
anything else does -- and it drives it through the same
:class:`~glisteel.steering.KeyboardDriver` a person's keys go through, so the
wheel winds on and centres exactly as it does for them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from glisteel.steering import CONTROLS, KeyboardDriver, MouseWheel

__all__ = ['Hold', 'Script']


@dataclass(frozen=True)
class Hold:
    """One control held down from ``start`` to ``end``, in seconds.

    ``control`` is one of the names in
    :data:`~glisteel.steering.CONTROLS` -- what the player meant, rather than
    which of the two keys for it they used.
    """

    control: str
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.control not in CONTROLS:
            raise ValueError(
                "no control called %r; there is %s"
                % (self.control, ', '.join(sorted(CONTROLS))))

    def __str__(self) -> str:
        return '%s %g..%g' % (self.control, self.start, self.end)

    def down_at(self, when: float) -> bool:
        """Whether this key is down at that moment of the drive."""
        return bool(self.start <= when < self.end)


class Script:
    """A drive: a set of holds, replayed against whatever is being driven.

    Build one from :class:`Hold` objects or from a line --
    ``'throttle 0..12; left 3..3.4'`` -- and hand it to a
    :class:`~glisteel.session.Session` as its driver. It keeps its own clock,
    advanced by the steps it is asked over, so it replays the same way whatever
    rate the run is advanced at.

    ``pointer`` steers with the mouse instead of the keys where one is given;
    the holds still work, and take the wheel back while a steering key is down.
    """

    def __init__(self, holds: Any = (), pointer: MouseWheel | None = None) -> None:
        self.holds = tuple(holds)
        self.driver = KeyboardDriver(pointer)
        #: How far into the drive the script has been asked for.
        self.elapsed = 0.0

    def __repr__(self) -> str:
        return 'Script(%s)' % ', '.join(str(hold) for hold in self.holds)

    @classmethod
    def parse(cls, line: str, **named: Any) -> Script:
        """A script from a line: ``'throttle 0..12; left 3..3.4'``.

        Semicolons or newlines separate the holds; each is a control name and
        the seconds it is down for.
        """
        holds = []
        for part in re.split(r'[;\n]', line):
            part = part.strip()
            if not part:
                continue
            found = re.fullmatch(
                r'(\w+)\s+([0-9.]+)\s*\.\.\s*([0-9.]+)', part)
            if found is None:
                raise ValueError(
                    "%r is not a hold; write one as 'throttle 0..12'" % (part,))
            holds.append(Hold(found.group(1), float(found.group(2)),
                              float(found.group(3))))
        return cls(holds, **named)

    @property
    def duration(self) -> float:
        """When the last key comes up, in seconds."""
        return max((hold.end for hold in self.holds), default=0.0)

    def holding_at(self, when: float) -> set[str]:
        """Which controls are down at that moment of the drive."""
        return {hold.control for hold in self.holds if hold.down_at(when)}

    def restart(self) -> None:
        """Wind the drive back to its beginning, with nothing held."""
        self.elapsed = 0.0
        self.driver.release_all()

    def controls(self, session: Any, dt: float) -> tuple[float, float, float]:
        """The pedals and the wheel this far into the drive.

        The keys go down and come up through the same held-key set a window
        fills, so what reaches the car is what a person holding those keys for
        those moments would have produced.
        """
        self.elapsed += float(dt)
        wanted = self.holding_at(self.elapsed)
        for control, keys in CONTROLS.items():
            name = sorted(keys)[0]
            if control in wanted:
                self.driver.press(name)
            else:
                self.driver.release(name)
        return self.driver.controls(session, dt)
