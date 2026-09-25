"""What this game offers to download, and what of it is already here.

glisteel ships its code and fetches its data. A baked track is 22 MB and the
four this release carries are 90 MB together with the art they share, which
is not a wheel and not
something an index should be asked to serve; the archives are attached to a
GitHub release and fetched from there. The cars are the **base pack**: the
game draws nothing without them. The wheel carries a copy of them in
``glisteel/assets``, which is read while the pack is not installed; when
neither is here, a first run offers the pack for download before the menu
(:meth:`glisteel.game.GlisteelContext.OnInit`).

The facility is the engine's (:mod:`OpenGLContext.contentpacks`), which reads
the registry, checks the digests, unpacks safely and runs the download off the
frame loop. :data:`CONTENT` is its
:class:`~OpenGLContext.contentpacks.application.Application` for this game;
what is here besides is which packs are tracks, and how a track that arrived
as a pack reaches the chooser beside one baked by hand.

    >>> from glisteel import content
    >>> for pack in content.missing():                     # doctest: +SKIP
    ...     print(pack.title, pack.human_size())

``release-assets.py`` writes :data:`CATALOG_PATH` from the archives it builds,
so every digest in it is of a file that was built rather than of one somebody
hoped for.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from importlib import resources
from typing import Any

from OpenGLContext.contentpacks import (
    Application,
    ContentPack,
    ContentStore,
    catalog,
    fetch,
)

from glisteel import tracks

log = logging.getLogger(__name__)

__all__ = ['BASE', 'CATALOG_PATH', 'CONTENT', 'IN_WHEEL', 'NAMESPACE',
           'art_directory', 'art_is_here', 'installed',
           'installed_tracks', 'missing', 'needed_to_start', 'offered',
           'registry', 'store', 'track_packs', 'wanted_for']

#: The registry shipped with the game.
CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'packs.json')

#: The namespace this game's packs sit under. A registry added to an install
#: may declare only its own, so nothing added can answer for -- or write over --
#: a pack shipped here.
NAMESPACE = 'glisteel'

#: What a track pack carries at its top, which is what makes it a track rather
#: than the art a track needs.
TILESET = 'tileset.json'

#: The pack the game cannot start without: the car a player drives and the
#: traffic it shares the road with.
BASE = '%s/cars' % (NAMESPACE,)

#: The copy of the cars inside the package, read while the pack is not here.
IN_WHEEL = str(resources.files('glisteel') / 'assets')

#: This game's content: the shipped registry and any added to the store.
CONTENT = Application(NAMESPACE, CATALOG_PATH, base=BASE, fallback=IN_WHEEL,
                      added=True)


def registry() -> list[ContentPack]:
    """Every pack this build offers, the shipped ones and any added.

    Read once: a registry is a file on disk and a chooser asks for it a great
    many times. ``CONTENT.reload()`` reads them again.
    """
    return list(CONTENT.registry())


def store(root: str | None = None) -> ContentStore:
    """Where this game's content lives on this machine."""
    return CONTENT.store(root)


def _ours(given: ContentStore | None) -> ContentStore:
    """``given``, or this game's own store where the caller named none."""
    return given if given is not None else store()


def installed(packs: Sequence[ContentPack] | None = None,
              store: ContentStore | None = None) -> list[ContentPack]:
    """Those packs already on this machine."""
    where = _ours(store)
    return list(where.installed(packs if packs is not None else registry()))


def missing(packs: Sequence[ContentPack] | None = None,
            store: ContentStore | None = None) -> list[ContentPack]:
    """Those that would have to be fetched."""
    where = _ours(store)
    return list(where.missing(packs if packs is not None else registry()))


def needed_to_start(store: ContentStore | None = None) -> list[ContentPack]:
    """What a first run has to fetch before the game can draw anything.

    The base pack and whatever it is incomplete without. Empty once it is here,
    which is every run but the first.
    """
    where = _ours(store)
    return list(fetch.missing_base(registry(), where))


def track_packs(packs: Sequence[ContentPack] | None = None
                ) -> list[ContentPack]:
    """Those packs that are worlds to drive, rather than art a world needs."""
    return [one for one in (packs if packs is not None else registry())
            if one.marker == TILESET]


def installed_tracks(store: ContentStore | None = None) -> list[Any]:
    """Every downloaded track, as the chooser's own
    :class:`~glisteel.tracks.Track`.

    A track that arrived as a pack is a track like one baked by hand: it is a
    directory with a manifest beside a tileset, and nothing downstream needs to
    know which it was.
    """
    where = _ours(store)
    found = []
    for pack in track_packs():
        root = where.root_for(pack)
        if root is None:
            continue
        track = tracks.Track.at(root)
        if track is not None:
            found.append(track)
    return found


def offered(store: ContentStore | None = None) -> list[ContentPack]:
    """What a download screen puts in front of a player.

    The packs that are a choice and are not here yet. The art every track
    shares is not one of them: it arrives with whichever track names it, and
    unpacks under that track rather than into a place of its own.
    """
    where = _ours(store)
    return list(where.missing(catalog.offered(registry())))


def wanted_for(pack: ContentPack,
               store: ContentStore | None = None) -> list[ContentPack]:
    """What choosing ``pack`` has to fetch: it, and what it needs.

    What a user is asked to consent to: fetching a track without the art it
    shares leaves them looking at bare ground. Asked within the choice, since
    the art lands under each track that needs it -- so a second track fetches
    the art again, from the download cache rather than from the network.
    """
    where = _ours(store)
    return list(fetch.wanted_for(pack, registry(), where))


def art_is_here(store: ContentStore | None = None) -> bool:
    """Whether the game's own art can be read: the pack, or the wheel's copy."""
    try:
        CONTENT.base_directory(store)
    except LookupError:
        return False
    return True


def art_directory(store: ContentStore | None = None) -> str:
    """Where the game's own art is read from, as of now.

    The base pack once it is installed, else the copy inside the wheel;
    :class:`~OpenGLContext.contentpacks.application.NotInstalled` if neither.
    """
    return str(CONTENT.base_directory(store))
