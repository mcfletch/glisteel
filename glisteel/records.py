"""The best times driven on each track, kept between one session and the next.

A lap time on its own is a number. What makes it worth driving for is the table
it lands in -- so the only question this answers is **where did that lap come**,
and the answer is what the finish is for::

    >>> import os, tempfile
    >>> table = Records(os.path.join(tempfile.mkdtemp(), 'times.json'))
    >>> table.offer('ashdown', 84.115)
    1
    >>> table.offer('ashdown', 91.0)
    2
    >>> [lap.clock() for lap in table.best('ashdown')]
    ['1:24.115', '1:31.000']

:data:`KEPT` times per track, quickest first, so a lap is turned away only once
the table is full and it beat none of them::

    >>> for seconds in (70.0, 71.0, 72.0, 73.0, 74.0):
    ...     place = table.offer('speedwell', seconds)
    >>> table.offer('speedwell', 999.0) is None
    True
    >>> table.offer('speedwell', 69.0)
    1

A race that ended without a lap has no time to offer, and gets the same answer::

    >>> table.offer('speedwell', 0.0) is None
    True

The file is JSON under the player's own directory (:mod:`glisteel.tracks`),
written so that a person can read it. A file that will not parse loses the times
and not the game: a corrupt score table is worth nothing, and refusing to start
over one is worth less.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from typing import Any

from glisteel.tracks import home

__all__ = ['KEPT', 'Record', 'Records', 'RECORDS', 'records_path']

log = logging.getLogger(__name__)

#: How many times are kept for each track. Enough that a quick lap is worth
#: chasing for a while and few enough that the table is read at a glance.
KEPT = 5

#: What the file is called, under the player's own directory.
RECORDS = 'times.json'


def records_path() -> str:
    """Where this player's times are kept."""
    return os.path.join(home(), RECORDS)


@dataclass(frozen=True)
class Record:
    """One lap worth keeping: how long it took, and the day it was driven."""

    seconds: float
    when: str = ''

    def clock(self) -> str:
        """The time as a driver reads it: ``m:ss.mmm``."""
        minutes, rest = divmod(max(0.0, float(self.seconds)), 60.0)
        return '%d:%06.3f' % (int(minutes), rest)

    def to_json(self) -> dict[str, Any]:
        document: dict[str, Any] = {'seconds': round(float(self.seconds), 3)}
        if self.when:
            document['when'] = self.when
        return document

    @classmethod
    def from_json(cls, document: Any) -> Record | None:
        """One record from a document, or None for something that is not one."""
        try:
            return cls(seconds=float(document['seconds']),
                       when=str(document.get('when', '')))
        except (TypeError, ValueError, KeyError, IndexError):
            return None


class Records:
    """The best times on every track this player has driven.

    Keyed by :attr:`glisteel.tracks.Track.key`, so a table is readable and a
    world that moves on disk keeps its times.
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path or records_path()
        self._tables: dict[str, list[Record]] = self._read()

    def __repr__(self) -> str:
        return 'Records(%d tracks, %r)' % (len(self._tables), self.path)

    # -- reading it ------------------------------------------------------------

    def best(self, track: str) -> list[Record]:
        """Every kept time for a track, quickest first."""
        return list(self._tables.get(str(track), ()))

    def record(self, track: str) -> Record | None:
        """The quickest lap driven on a track, or None for one never driven."""
        found = self._tables.get(str(track))
        return found[0] if found else None

    # -- adding to it ----------------------------------------------------------

    def offer(self, track: str, seconds: float, when: str | None = None
              ) -> int | None:
        """Offer a lap; answer where it came, counting from one, or None.

        None means it was not quick enough to keep, which is the same answer a
        lap of no time at all gets: a race abandoned has no time to offer.
        """
        seconds = float(seconds)
        if not seconds > 0.0:
            return None
        record = Record(seconds=seconds,
                        when=when if when is not None else date.today().isoformat())
        table = self._tables.setdefault(str(track), [])
        table.append(record)
        # Sorted by time, and by nothing else, so two equal laps keep the order
        # they were offered in -- and found by identity, because ``index``
        # answers about the *first* record equal to this one, which for a lap
        # that ties another is the wrong one.
        table.sort(key=lambda one: one.seconds)
        del table[KEPT:]
        for place, kept in enumerate(table, start=1):
            if kept is record:
                return place
        return None

    # -- keeping it ------------------------------------------------------------

    def save(self) -> str:
        """Write the table out; answer where it went.

        Beside the file and then moved onto it, so a write that fails part way
        -- a full disk, a machine that goes down -- leaves the times that were
        there rather than a file with half a table in it. This module already
        says a corrupt table is worth nothing; this is what stops one being
        made. In UTF-8, and as its own characters, because a track may be named
        in any language and the file is meant to be readable.
        """
        beside = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(beside, exist_ok=True)
        document = {track: [one.to_json() for one in table]
                    for track, table in sorted(self._tables.items()) if table}
        handle, temporary = tempfile.mkstemp(dir=beside, suffix='.times-new')
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as writing:
                json.dump(document, writing, indent=2, sort_keys=True,
                          ensure_ascii=False)
                writing.write('\n')
            os.replace(temporary, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise
        return self.path

    def _read(self) -> dict[str, list[Record]]:
        try:
            with open(self.path, encoding='utf-8') as handle:
                document = json.load(handle)
        except FileNotFoundError:
            return {}
        except (ValueError, OSError):
            log.warning('could not read the times in %s; starting a fresh table',
                        self.path, exc_info=True)
            return {}
        if not isinstance(document, dict):
            log.warning('%s does not hold a table of times', self.path)
            return {}
        tables = {}
        for track, times in document.items():
            found = [Record.from_json(one) for one in (times or ())]
            kept = sorted((one for one in found if one is not None),
                          key=lambda one: one.seconds)[:KEPT]
            if kept:
                tables[str(track)] = kept
        return tables
