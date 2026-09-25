#! /usr/bin/env python3
"""Bake the tracks a release carries, install them here, and publish them.

A track is 22 MB and the launch set is 90 MB, so the content does not go to
PyPI with the code: it is attached to a GitHub release and fetched by
:mod:`OpenGLContext.contentpacks`. One command covers the whole of that:

    ./release-assets.py                   # bake, archive, write the registry
    ./release-assets.py --install         # ...and put it in this machine's store
    ./release-assets.py --reinstall       # ...replacing the copies installed there
    ./release-assets.py --push            # ...attach it to the release tag and
                                          #    write the shipped packs.json

``--install`` is what makes a content release testable before it is a release:
the game then finds the tracks in its own store and offers them as an installed
copy would, with nothing published and no network reached.

Every track is baked from its recipe (``--recipes``), so a release is rebuilt
from what is written down rather than from a command somebody remembers typing;
``--from`` uses a bake that is already on disk instead. Every digest in the
registry is of a file this wrote, so the registry cannot describe content that
was never built, and
:func:`OpenGLContext.contentpacks.archive.write` makes the archives'
bytes a function of the content and of nothing else -- which is what makes a
digest worth recording and a rebuild from a tag worth attempting.

The registry is written beside the archives, and ``glisteel/packs.json``, the
one the game ships, only by ``--push`` or ``--write-registry``; the registry
and the track previews also go into one ``glisteel-registry.zip``, attached
with the archives. The options, the install and the push are
:func:`OpenGLContext.contentpacks.publish.main`'s.

Baking needs ``glisteel-editor``, which is not on an index: a checkout of it
beside this one is where the recipes and the baker are looked for.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from typing import Any

from OpenGLContext.contentpacks import publish

#: The namespace this game's packs sit under.
NAMESPACE = 'glisteel'

HERE = os.path.dirname(os.path.abspath(__file__))

#: The registry this writes, which is the one the game ships.
CATALOG = os.path.join(HERE, NAMESPACE, 'packs.json')

#: Where the track recipes are looked for, in order. The first is this
#: repository's own; the second is the editor checkout that bakes them, which
#: is where they live while ``glisteel-editor`` is the only thing that reads
#: them.
RECIPES = (os.path.join(HERE, 'tracks'),
           os.path.join(os.path.dirname(HERE), 'glisteel-editor', 'tracks'))


def recipes(named: str | None = None) -> list[str]:
    """Every track recipe to bake, in a settled order.

    A release is the set of recipes, so adding a track is adding a file rather
    than editing this command.
    """
    looked = [named] if named else list(RECIPES)
    for where in looked:
        found = sorted(glob.glob(os.path.join(where, '*.toml')))
        if found:
            return found
    raise SystemExit(
        'no track recipes in %s. Point --recipes at them, or --from at a bake.'
        % (' or '.join(looked),))


def bake(into: str, named: str | None = None, depth: int | None = None) -> str:
    """Bake every recipe into ``into``; the directory it filled.

    One directory per track and one ``_art`` beside them, which is the shape
    the packs are built from: the art every track shares is 32 MB and is
    carried once rather than four times.
    """
    try:
        from glisteel_editor import bake as baker
    except ImportError as error:              # pragma: no cover - needs the editor
        raise SystemExit(
            'baking needs glisteel-editor, which is not installed: %s. Check '
            'one out beside this repository, or pass --from a bake.' % (error,)
        ) from error
    for recipe in recipes(named):
        name = os.path.splitext(os.path.basename(recipe))[0]
        print('baking %s' % (name,))
        argv = ['--recipe', recipe, '--output', os.path.join(into, name),
                '--art-pack', os.path.join(into, '_art'), '--force', '--quiet']
        if depth is not None:
            argv += ['--depth', str(depth)]
        try:
            status = baker.main(argv)
        except baker.ArtDiffers as error:
            # The art left by an earlier run is not the art this one makes, so
            # the two cannot share a pack. Said rather than resolved here:
            # what to throw away is the caller's decision, not this command's.
            raise SystemExit(
                '%s\n\nThe art in %s is from an earlier build. Remove that '
                'directory, or bake into a fresh --worlds.'
                % (error, os.path.join(into, '_art'))) from error
        if status:
            raise SystemExit('baking %s failed' % (name,))
    return into


def declare(build: publish.Build) -> list[dict[str, Any]]:
    """Build every archive a release carries; what the registry says of them.

    The cars first, because they are the pack the game cannot start without;
    then the art every track shares; then a pack per track, each naming that
    art in ``needs`` so choosing a track fetches a track that works.
    """
    options = build.options
    baked = options.baked or bake(options.worlds, options.recipes,
                                  options.depth)
    if not os.path.isdir(os.path.join(baked, '_art')):
        raise SystemExit('%s holds no _art: bake with --art-pack' % (baked,))
    packs = [build.entry(
        'cars', build.archive(options.assets, 'glisteel-cars'),
        title='The cars', marker='cars/hero.glb', base=True,
        copyright=_credits(options.assets),
        notes='The hero car, its wheels and five traffic cars.')]
    packs.append(build.entry(
        'forest-art', build.archive(os.path.join(baked, '_art'),
                                    'glisteel-forest-art'),
        title='Forest art', marker='trees', copyright=TREE_CREDIT,
        notes='Tree and gantry art, shared by every track.'))
    for name in sorted(os.listdir(baked)):
        where = os.path.join(baked, name)
        if name.startswith('_') or not os.path.isdir(where):
            continue
        packs.append(build.entry(
            name, build.archive(where, 'glisteel-%s' % (name,)),
            title=_titled(where, name), marker='tileset.json',
            needs=['%s/forest-art' % (NAMESPACE,)],
            copyright=_world_credit(where), notes=_summary(where),
            preview='previews/%s.jpg' % (name,)))
    return packs


def arguments(parser: argparse.ArgumentParser) -> None:
    """Where the tracks and the cars come from."""
    parser.add_argument('--from', dest='baked', default=None,
                        help='a bake that is already on disk -- one directory '
                             'per track plus _art -- instead of baking one')
    parser.add_argument('--recipes', default=None, metavar='DIR',
                        help='where the track recipes are (default: %s)'
                             % (' or '.join(os.path.relpath(one, HERE)
                                            for one in RECIPES),))
    parser.add_argument('--depth', type=int, default=None,
                        help='bake to this tile depth rather than each '
                             "recipe's own, for a draft set that builds fast")
    parser.add_argument('--worlds', default=os.path.join(HERE, 'dist', 'worlds'),
                        help='where the bake is written')
    parser.add_argument('--assets', default=os.path.join(HERE, 'glisteel',
                                                         'assets'),
                        help="the game's own art, which becomes the base pack")


TREE_CREDIT = (
    "'Fir tree' by Georgeous, 'Noel_Pine_Tree' by 3D Error 404 and 'Maple "
    "trees pack' by LOLIPOP, all CC-BY 4.0; ground materials from ambientCG "
    "(CC0 1.0). The meshes, textures and impostor cards here are derivative "
    "works and carry the same licence; packaged by the glisteel project.")


def _titled(where: str, name: str) -> str:
    manifest = os.path.join(where, 'world.json')
    if os.path.isfile(manifest):
        with open(manifest, encoding='utf-8') as handle:
            return json.load(handle).get('name') or name.title()
    return name.title()


def _summary(where: str) -> str:
    manifest = os.path.join(where, 'world.json')
    if not os.path.isfile(manifest):
        return ''
    with open(manifest, encoding='utf-8') as handle:
        found = json.load(handle)
    length = found.get('roadLength')
    if length is None:
        return ''
    shape = 'a lap' if found.get('closed', True) else 'point to point'
    carried = found.get('structures') or {}
    built = ', '.join('%d m of %s' % (round(metres), kind)
                      for kind, metres in sorted(carried.items()))
    return '%.1f km, %s%s.' % (length / 1000.0, shape,
                               '; ' + built if built else '')


def _world_credit(where: str) -> str:
    """What the bake recorded about where its content came from.

    Whole, however long it runs. Most of a track's art is somebody else's
    under CC-BY and the condition of using it is that the credit travels with
    it, so the notice goes into the registry entry at the length the bake
    wrote it: a credit cut to fit names a work and not who made it.
    """
    credits = os.path.join(where, 'CREDITS.txt')
    if os.path.isfile(credits):
        with open(credits, encoding='utf-8') as handle:
            said = handle.read().strip().replace('\n', ' ')
        if said:
            return said
    return TREE_CREDIT


def _credits(where: str) -> str:
    found = os.path.join(where, 'cars', 'CREDITS.md')
    if os.path.isfile(found):
        with open(found, encoding='utf-8') as handle:
            for line in handle:
                if line.strip() and not line.startswith('#'):
                    return line.strip()
    return 'glisteel project, BSD-3-Clause'


RELEASE = publish.Release(
    namespace=NAMESPACE,
    url='https://github.com/mcfletch/glisteel/releases/download/%s/%s',
    catalog=CATALOG, declare=declare,
    into=os.path.join(HERE, 'dist', 'content'), bundle=True,
    arguments=arguments, description=__doc__.split('\n\n')[0],
    title='glisteel content',
    notes='The cars, the shared forest art and the tracks this release '
          "offers. Terms are in the registry and in each pack's own "
          'CREDITS.txt.')


if __name__ == '__main__':
    raise SystemExit(publish.main(RELEASE))
