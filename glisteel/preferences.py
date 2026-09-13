"""What a player chose, kept between runs.

Choosing a way of driving and finding the wheel back next time is worse than not
offering the choice: the game asked a question, was answered, and threw the
answer away. This is the file that stops that.

    >>> from glisteel import preferences
    >>> kept = preferences.Preferences()                   # doctest: +SKIP
    >>> kept.control = 'lanes'                             # doctest: +SKIP
    >>> kept.save()                                        # doctest: +SKIP

It lives beside the times table and the track library, under the player's own
directory (:func:`glisteel.tracks.home`), because a player's things belong in
one place rather than three.

**Losing it costs one menu visit**, and that is what decides how it handles a
file it cannot read: a corrupt preferences file is ignored rather than raised
on. The times table takes the opposite view of its own corruption and says so;
the difference is that a lost best lap cannot be re-driven and a lost setting is
two clicks.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from typing import Any

log = logging.getLogger(__name__)

__all__ = ['PREFERENCES', 'Preferences', 'preferences_path']

#: What the file is called, under the player's own directory.
PREFERENCES = 'preferences.json'


def preferences_path() -> str:
    """Where this player's settings are kept."""
    from glisteel import tracks
    return os.path.join(tracks.home(), PREFERENCES)


class Preferences:
    """A player's own settings, as a document that survives the process.

    Small on purpose. What belongs here is what a player *chose* and would be
    annoyed to choose again; what the engine already keeps -- the renderer's
    settings, the interface scale -- is the engine's and is not copied here.
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path or preferences_path()
        found = self._read()
        #: Which way of driving, or None for the game's own default. A name no
        #: scheme is called is dropped rather than carried: a file edited by
        #: hand, or written by a build that offered more ways than this one.
        self.control: str | None = _a_scheme(found.get('control'))

    def __repr__(self) -> str:
        return 'Preferences(control=%r, %r)' % (self.control, self.path)

    def save(self) -> str | None:
        """Write the settings out; answer where they went, or None for nothing.

        Beside the file and then moved onto it, so a write that fails part way
        leaves what was there rather than half a document -- which for this file
        would be a choice eaten by the thing that was meant to keep it.

        An untouched install writes nothing, so a fresh one leaves no file to go
        stale.
        """
        document: dict[str, Any] = {}
        if self.control:
            document['control'] = self.control
        if not document:
            return None
        beside = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(beside, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=beside, suffix='.prefs-new')
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

    def _read(self) -> dict[str, Any]:
        """The document on disk, or an empty one for anything that is not one."""
        try:
            with open(self.path, encoding='utf-8') as handle:
                found = json.load(handle)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as error:
            log.warning('ignoring unreadable preferences %s: %s',
                        self.path, error)
            return {}
        return found if isinstance(found, dict) else {}


def _a_scheme(name: Any) -> str | None:
    """``name`` if some way of driving is called that, else None."""
    from glisteel import schemes
    return str(name) if name in schemes.available() else None
