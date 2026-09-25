"""Drive a world without drawing it, and say what happened.

What this is for: a run that went wrong, explained from the run's own record
rather than from a script written afterwards to ask one question. Every answer
here comes out of marks the game already writes
(:mod:`OpenGLContext.telemetry`) -- where it ended and why, every pass it took
and every one it wanted and could not have, every time it had to be put back on
the road -- plus the pace it managed while doing it.

    glisteel-diagnose /tmp/world/tileset.json

or from code::

    from glisteel.diagnose import drive_it
    report = drive_it('/tmp/world/tileset.json')
    print(report)

``--marks`` prints every mark in order, for what the summary does not
cover. Nothing here opens a window, so a whole circuit costs seconds of
CPU and no display.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from OpenGLContext.telemetry import Keeping, Tee

from glisteel.driver import PACE, Autopilot, DriverStyle
from glisteel.session import Session
from glisteel.world import RaceWorld

__all__ = ['Report', 'drive_it', 'main']

#: How long a run is given before it is called a run that does not end, in
#: seconds. Long enough for a lap of the longest circuit shipped at the speed
#: the traffic on it allows.
LONGEST = 900.0

FRAME = 1.0 / 60.0


@dataclass
class Report:
    """What a drive came to, in the words the game used at the time."""

    world: str
    seconds: float = 0.0
    outcome: str | None = None
    laps: int = 0
    length: float = 0.0
    closed: bool = True
    cars: int = 0
    speeds: Any = field(default_factory=lambda: np.zeros(0))
    marks: list = field(default_factory=list)

    def kinds(self) -> Counter[str]:
        """How many of each kind of mark the run wrote."""
        return Counter(name for _when, name, _fields in self.marks)

    def wanted(self) -> dict[str, float]:
        """The passes it wanted and could not have, by why, in seconds."""
        found: dict[str, float] = {}
        for _when, name, fields in self.marks:
            if name == 'pass-wanted':
                why = str(fields.get('why', '?'))
                found[why] = found.get(why, 0.0) + float(
                    fields.get('seconds', 0.0))
        return dict(sorted(found.items(), key=lambda one: -one[1]))

    def ended_at(self) -> dict:
        """Where and why the run stopped being a race, or an empty answer."""
        found = [fields for _when, name, fields in self.marks
                 if name == 'drive-ended']
        return found[-1] if found else {}

    def pace(self) -> dict[str, float]:
        """How fast it got round, in km/h."""
        if not len(self.speeds):
            return {}
        return {'mean': float(self.speeds.mean()),
                'median': float(np.median(self.speeds)),
                'p10': float(np.percentile(self.speeds, 10)),
                'p90': float(np.percentile(self.speeds, 90)),
                'top': float(self.speeds.max())}

    def stopped_share(self) -> float:
        """How much of the run was spent below walking pace, 0 to 1."""
        if not len(self.speeds):
            return 0.0
        return float((self.speeds < 5.0).mean())

    def __str__(self) -> str:
        lines = ['%s -- %s, %.0f m, %d cars'
                 % (self.world, 'a circuit' if self.closed else 'an open road',
                    self.length, self.cars)]
        lines.append('  ran %.1f s, %d lap%s, %s'
                     % (self.seconds, self.laps, '' if self.laps == 1 else 's',
                        'finished' if self.outcome is None
                        else 'ended %r' % self.outcome))
        where = self.ended_at()
        if where:
            lines.append('    at station %s of %.0f, %s m off the crown, %s km/h'
                         % (where.get('station', '?'), self.length,
                            where.get('across', '?'), where.get('speed', '?')))
        pace = self.pace()
        if pace:
            lines.append('  km/h: mean %(mean).0f  median %(median).0f'
                         '  p10 %(p10).0f  p90 %(p90).0f  top %(top).0f' % pace)
            lines.append('  %.0f%% of it below walking pace'
                         % (100.0 * self.stopped_share()))
        kinds = self.kinds()
        if kinds:
            lines.append('  what it did: %s'
                         % ', '.join('%s x%d' % (name, count)
                                     for name, count in kinds.most_common()
                                     if name != 'pass-wanted'))
        wanted = self.wanted()
        if wanted:
            lines.append('  passes it wanted and could not have:')
            for why, seconds in wanted.items():
                lines.append('    %-24s %5.1f s of the run (%.0f%%)'
                             % (why, seconds,
                                100.0 * seconds / max(self.seconds, 1e-6)))
        return '\n'.join(lines)


def drive_it(tileset: str, seconds: float = LONGEST, pace: float = PACE,
             traffic: int | None = None, laps: int = 1,
             journal: Any = None, seed: int = 0) -> Report:
    """Drive ``tileset`` with the autopilot and answer a :class:`Report`.

    ``traffic`` left out lets the road decide, which is what the game does.
    ``journal`` is a recorder (:mod:`OpenGLContext.telemetry`) that is handed
    every mark as well; the report keeps them either way.

    ``seed`` is which traffic this run meets. **One run says very little**: a
    lap is chaotic in the ordinary sense -- a car a metre further on at the
    first corner is a different lap by the third -- so a change judged from a
    single before-and-after is judged from noise. :func:`over_seeds` is the
    honest comparison.
    """
    world = world_for(tileset, traffic)
    if world.traffic is not None:
        world.traffic.reseed(seed)
    session = Session(world, laps=laps)
    session.driver = Autopilot(session.course, lane=session.lane,
                               style=DriverStyle(margin=pace))
    driven, speeds = 0.0, []
    keeping = Keeping(clock=lambda: driven)
    session.telemetry = keeping if journal is None else Tee(keeping, journal)
    session.run.go()
    while driven < seconds:
        session.advance(FRAME)
        driven += FRAME
        speeds.append(session.car.speed_kph())
        if session.run.over:
            break
    course = session.course
    return Report(
        world=(str(tileset) if '/' not in str(tileset)
               else str(tileset).rstrip('/').split('/')[-2] or str(tileset)),
        seconds=driven, outcome=session.ended, laps=len(session.timing.laps),
        length=float(course.length), closed=bool(course.closed),
        cars=world.traffic.count if world.traffic is not None else 0,
        speeds=np.asarray(speeds, dtype='d'), marks=keeping.marks)


def world_for(named: str, traffic: int | None) -> RaceWorld:
    """A world to drive: a baked tileset, or one of the named scenarios.

    A scenario is a piece of road built in memory with nothing drawn -- the
    oval, the hairpin, the chicane -- which is what to ask for when the
    question is about the *driving* rather than about a particular place. They
    cost a second to build where a baked world costs a bake.
    """
    from glisteel import scenarios
    if named in scenarios.CATALOGUE:
        piece = scenarios.named(named)
        made = piece.world(traffic=0)
        if traffic is None or traffic > 0:
            from glisteel.traffic import Traffic
            made.traffic = Traffic(
                made.course, physics=made.physics,
                count=(made.cars_the_road_carries() if traffic is None
                       else int(traffic)))
        return made
    return RaceWorld(named, traffic=traffic)


def over_seeds(tileset: str, seeds: int = 5, **named: Any) -> list[Report]:
    """The same world driven against several sets of traffic.

    What a change is actually measured against: how many of them finish, and
    what the spread of the rest looks like. A single run moving from 560 s to
    120 s is not a regression and not an improvement -- it is a different lap.
    """
    return [drive_it(tileset, seed=seed, **named) for seed in range(seeds)]


def summarise(reports: list[Report]) -> str:
    """How a handful of runs came out, in one line and then in detail."""
    if not reports:                              # pragma: no cover - no runs
        return 'nothing was driven'
    finished = [one for one in reports if one.outcome is None]
    lines = ['%s: %d of %d finished'
             % (reports[0].world, len(finished), len(reports))]
    for seed, report in enumerate(reports):
        # Numbered by where it is in the list rather than looked up by value:
        # a report carries its speeds as an array, so asking two of them
        # whether they are equal is asking an array whether it is true.
        lines.append('  seed %d: %6.1f s  %-22s %3.0f km/h mean, %d passes'
                     % (seed, report.seconds,
                        report.outcome or 'finished',
                        report.pace().get('mean', 0.0),
                        report.kinds().get('pass-done', 0)))
    return '\n'.join(lines)


def main(argv: Any = None) -> int:
    """``glisteel-diagnose``: drive each world named and say what happened."""
    parser = argparse.ArgumentParser(
        prog='glisteel-diagnose', description=__doc__.split('\n\n')[0])
    parser.add_argument('worlds', nargs='+', metavar='WORLD',
                        help='the tileset.json of a baked world, or the name '
                             'of a scenario to build in memory')
    parser.add_argument('--seconds', type=float, default=LONGEST,
                        help='how long to give each run (default: %(default)s)')
    parser.add_argument('--pace', type=float, default=PACE,
                        help='how hard it drives (default: %(default)s)')
    parser.add_argument('--traffic', type=int, default=None, metavar='CARS',
                        help='how many other cars; the road decides by default')
    parser.add_argument('--marks', action='store_true',
                        help='every mark the run wrote, in order')
    parser.add_argument('--seeds', type=int, default=0, metavar='N',
                        help='drive each world against N sets of traffic and '
                             'report how many finished. One run is noise: a '
                             'lap is chaotic, so a change judged from a single '
                             'before-and-after is judged from nothing')
    found = parser.parse_args(argv)
    for world in found.worlds:
        if found.seeds:
            print(summarise(over_seeds(
                world, seeds=found.seeds, seconds=found.seconds,
                pace=found.pace, traffic=found.traffic)))
            continue
        report = drive_it(world, seconds=found.seconds, pace=found.pace,
                          traffic=found.traffic)
        print(report)
        if found.marks:
            for when, name, fields in report.marks:
                print('    %7.2f %-16s %s'
                      % (when, name,
                         ' '.join('%s=%s' % pair for pair in fields.items())))
    return 0


if __name__ == '__main__':                       # pragma: no cover - a script
    sys.exit(main())
