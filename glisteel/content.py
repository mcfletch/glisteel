"""What this game offers to download, and what of it is already here.

glisteel ships its code and fetches its data. A baked track is 22 MB and the
four this release carries are 88 MB together, which is not a wheel and not
something an index should be asked to serve; the archives are attached to a
GitHub release and fetched from there. The car the player drives is the same
story at a smaller size, so it is the **base pack** -- the one thing fetched
before the menu, because a game with none of it has nothing to draw.

The facility is the engine's (:mod:`OpenGLContext.contentpacks`), which reads
the registry, checks the digests, unpacks safely and runs the download off the
frame loop. What is here is which registry, which namespace, and how a track
that arrived as a pack reaches the chooser beside one baked by hand.

    >>> from glisteel import content
    >>> for pack in content.missing():                     # doctest: +SKIP
    ...     print(pack.title, pack.human_size())

``tools/release_content.py`` writes :data:`CATALOG_PATH` from the archives it
builds, so every digest in it is of a file that was built rather than of one
somebody hoped for.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Any

from OpenGLContext.contentpacks import ContentPack, ContentStore, catalog, fetch

log = logging.getLogger(__name__)

__all__ = ['BASE', 'CATALOG_PATH', 'NAMESPACE', 'art_directory', 'installed',
           'installed_tracks', 'missing', 'needed_to_start', 'registry',
           'store', 'track_packs']

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

_registry: list[ContentPack] | None = None


def registry() -> list[ContentPack]:
    """Every pack this build offers, the shipped ones and any added.

    Read once: a registry is a file on disk and a chooser asks for it a great
    many times. A build that wants it read again clears :data:`_registry`.
    """
    global _registry
    if _registry is None:
        added = [catalog.load(path) for path in store().registries()]
        _registry = catalog.merge(catalog.load(CATALOG_PATH), *added)
    return _registry


def store(root: str | None = None) -> ContentStore:
    """Where this game's content lives on this machine."""
    return ContentStore(NAMESPACE, root=root)


def installed(packs: Sequence[ContentPack] | None = None,
              store: ContentStore | None = None) -> list[ContentPack]:
    """Those packs already on this machine."""
    where = store if store is not None else globals()['store']()
    return list(where.installed(packs if packs is not None else registry()))


def missing(packs: Sequence[ContentPack] | None = None,
            store: ContentStore | None = None) -> list[ContentPack]:
    """Those that would have to be fetched."""
    where = store if store is not None else globals()['store']()
    return list(where.missing(packs if packs is not None else registry()))


def needed_to_start(store: ContentStore | None = None) -> list[ContentPack]:
    """What a first run has to fetch before the game can draw anything.

    The base pack and whatever it is incomplete without. Empty once it is here,
    which is every run but the first.
    """
    where = store if store is not None else globals()['store']()
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
    from glisteel import tracks
    where = store if store is not None else globals()['store']()
    found = []
    for pack in track_packs():
        root = where.root_for(pack)
        if root is None:
            continue
        track = tracks.Track.at(root)
        if track is not None:
            found.append(track)
    return found


def wanted_for(pack: ContentPack) -> list[ContentPack]:
    """``pack`` and everything it is incomplete without.

    What a user is asked to consent to: fetching a track without the art it
    shares leaves them looking at bare ground.
    """
    return list(catalog.with_needed(pack, registry()))


def art_directory(store: ContentStore | None = None) -> str:
    """Where the game's own art is read from.

    The base pack once it has been fetched, and the copy inside the wheel until
    then. Both, deliberately: the art leaves the wheel when the release carrying
    it exists, and until that day an install has to work anyway. When it does
    leave, this is the only place that has to stop looking there.
    """
    from importlib import resources
    where = store if store is not None else globals()['store']()
    pack = catalog.pack_for_key(BASE, registry())
    if pack is not None:
        root = where.root_for(pack)
        if root is not None:
            return str(root)
    return str(resources.files("glisteel") / "assets")
