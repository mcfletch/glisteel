"""The worlds a player can choose between, and where their own files live.

A baked world is a directory of tiles, which says how to draw it and nothing
about what it is. What a chooser needs -- the name, how far round it goes, how
much of it is on structures, and the picture that shows it -- is in the manifest
the bake wrote beside the tileset
(:mod:`OpenGLContext.loaders.tiles3d.manifest`). A **track** is that manifest
with its paths resolved, so everything a chooser does it can do without loading
a single tile.

    >>> from glisteel.tracks import library, tracks_directory
    >>> for track in library():                            # doctest: +SKIP
    ...     print(track.name, track.summary())

Worlds live in :func:`tracks_directory`, under the platform's own place for a
user's application files (:mod:`OpenGLContext.userpaths`) -- the same rule the
engine's settings and asset cache follow, rather than a second one invented
here. Nothing in this module creates a directory: asking where a file belongs is
not a reason to make one.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from OpenGLContext import userpaths
from OpenGLContext.loaders.tiles3d.manifest import (
    read_manifest,
    write_manifest,
)

__all__ = ['PICTURE', 'Track', 'home', 'library', 'named',
           'remember_picture', 'tracks_directory']

log = logging.getLogger(__name__)

#: The directory this game keeps a player's own files in, under the platform's
#: application-data directory.
APPLICATION = 'glisteel'

#: What a track's own picture is called, in the track's own directory.
PICTURE = 'track.png'

#: What the worlds are kept in, under that.
TRACKS = 'tracks'


def home() -> str:
    """Where this player's own glisteel files belong."""
    return os.path.join(userpaths.appdatadirectory(), APPLICATION)


def tracks_directory() -> str:
    """Where this player's worlds are looked for."""
    return os.path.join(home(), TRACKS)


@dataclass(frozen=True)
class Track:
    """One world a player can choose, as a chooser sees it.

    ``tileset`` and ``picture`` are absolute paths that exist -- a manifest
    naming a picture that is not there gives a track with no picture rather than
    a chooser that fails to open, since a missing picture is a plate and a
    missing world is the only thing worth refusing.
    """

    name: str
    directory: str
    tileset: str
    picture: str | None = None
    length: float | None = None
    structures: dict = field(default_factory=dict)
    closed: bool = True

    @classmethod
    def at(cls, where: str) -> Track | None:
        """The track in a directory, or None where there is not one.

        A directory with no manifest, or one whose tileset is not beside it, is
        not a track: what a chooser offers has to be something it can start.
        """
        manifest = read_manifest(where)
        if manifest is None:
            return None
        directory = os.path.abspath(where if os.path.isdir(where)
                                    else os.path.dirname(where))
        tileset = _beside(directory, manifest.tileset)
        if tileset is None:
            return None
        return cls(name=manifest.name, directory=directory, tileset=tileset,
                   picture=_beside(directory, manifest.picture),
                   length=manifest.road_length, structures=manifest.structures,
                   closed=manifest.closed)

    @classmethod
    def bare(cls, tileset: str) -> Track | None:
        """A track for a tileset with no manifest beside it.

        A world baked before manifests, or one somebody points the game at
        directly, is still a world to drive: it takes its name from the
        directory it sits in and says nothing else about itself.
        """
        if not os.path.exists(tileset):
            return None
        directory = os.path.abspath(os.path.dirname(tileset) or '.')
        return cls(name=_named_after(directory),
                   directory=directory, tileset=os.path.abspath(tileset))

    @classmethod
    def opening(cls, tileset: str) -> Track | None:
        """The track at a tileset path, manifest or no manifest."""
        return cls.at(tileset) or cls.bare(tileset)

    @property
    def key(self) -> str:
        """What this track's records are kept against.

        Its name, folded: a player identifies a track by what it is called, and
        keying on where it happens to sit on disk would lose their times the
        first time they moved it.
        """
        return self.name.strip().casefold()

    def carried(self) -> float:
        """How many metres of this road are on a bridge, a bore or a causeway."""
        return float(sum(self.structures.values()))

    def summary(self) -> str:
        """A line under this track's name in a chooser.

        Its length and what carries it: two circuits of the same length are
        different drives if one of them is a third viaduct.
        """
        parts = []
        if self.length:
            parts.append('%.1f km' % (self.length / 1000.0))
        for kind, metres in sorted(self.structures.items()):
            if metres > 0:
                parts.append('%.1f km %s' % (metres / 1000.0, kind))
        return ', '.join(parts) or 'a road'


def library(directory: str | None = None) -> list[Track]:
    """Every world under a directory, by name.

    Sorted, because a chooser that reorders itself between runs is one a player
    cannot learn. A directory that holds no worlds -- including one that is not
    there -- is an empty library rather than an error: a fresh install is
    exactly that.
    """
    root = directory or tracks_directory()
    try:
        inside = sorted(os.listdir(root))
    except OSError:
        return []
    found = [Track.at(os.path.join(root, entry)) for entry in inside
             if os.path.isdir(os.path.join(root, entry))]
    return sorted((track for track in found if track is not None),
                  key=lambda track: track.key)


def named(name: str, directory: str | None = None) -> Track | None:
    """The world of that name, or None for one that is not there."""
    wanted = str(name).strip().casefold()
    for track in library(directory):
        if track.key == wanted:
            return track
    return None


def remember_picture(track: Track, filename: str = PICTURE) -> str | None:
    """Write into a track's manifest that this is the picture of it.

    The picture itself is taken by the game, since taking it means driving the
    world; what is recorded is only the name, so a chooser finds it without
    guessing at filenames. Answers where the manifest went, or None for a world
    that carries no manifest to write into.
    """
    manifest = read_manifest(track.directory)
    if manifest is None:
        return None
    manifest.picture = filename
    written: str | None = write_manifest(track.directory, manifest)
    return written


def _named_after(directory: str) -> str:
    """A readable name for a world sitting in that directory."""
    stem = os.path.basename(os.path.abspath(directory))
    return stem.replace('-', ' ').replace('_', ' ').strip().title() or 'Untitled'


def _beside(directory: str, relative: Any) -> str | None:
    """A file the manifest named, if it is there and is *inside* the track.

    A world is a directory that can be moved or copied, and a manifest names
    what it carries relative to itself. It is also something a player collects
    from somebody else, so the name in it is input rather than data: a manifest
    naming ``../../..`` or an absolute path is describing a file that is not
    part of the world it came with, and there is no reason to follow it.
    Anything outside reads as no file at all, which is what a track with no
    picture already is.
    """
    if not relative:
        return None
    root = os.path.realpath(directory)
    where = os.path.realpath(os.path.join(root, str(relative)))
    if os.path.commonpath([root, where]) != root:
        log.warning('%s names %r, which is outside the track it came with',
                    directory, str(relative))
        return None
    return str(where) if os.path.exists(where) else None
