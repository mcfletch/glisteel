#! /usr/bin/env python3
"""Bake the tracks a release carries, install them here, and publish them.

A track is 22 MB and the launch set is 90 MB, so the content does not go to
PyPI with the code: it is attached to a GitHub release and fetched by
:mod:`OpenGLContext.contentpacks`. One command covers the whole of that:

    ./release-assets.py                 # bake, archive, write the registry
    ./release-assets.py --install       # ...and put it in this machine's store
    ./release-assets.py --push          # ...and attach it to the release tag

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

Baking needs ``glisteel-editor``, which is not on an index: a checkout of it
beside this one is where the recipes and the baker are looked for.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import zipfile
from typing import Any

from OpenGLContext.contentpacks import archive, catalog, publish

#: Where a release's artefacts are fetched from.
URL = 'https://github.com/mcfletch/glisteel/releases/download/%s/%s'

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


def build(where: str, name: str, into: str) -> tuple[str, int, str]:
    """Archive ``where`` as ``name``; return its path, size and digest."""
    path = archive.write(where, os.path.join(into, '%s.tar.gz' % (name,)))
    return path, os.path.getsize(path), archive.digest(path)


def bundle_registry(manifest: str, into: str) -> str:
    """The registry and its thumbnails as one file; its path.

    What an application is pointed at when it is offered a set of content it
    did not ship with. It is a document and some pictures -- 90 KB against the
    90 MB it describes -- so fetching one gives a chooser every pack's title,
    size, terms and picture while downloading none of the content.

    Attached to the same release as the archives, which is what lets a later
    set of tracks reach an installed game without shipping a new version of it.
    Read back by
    :func:`OpenGLContext.contentpacks.catalog.load_bundle`, which wants the
    document at the top under its own name.
    """
    beside = os.path.dirname(os.path.abspath(manifest))
    path = os.path.join(into, '%s-registry.zip' % (NAMESPACE,))
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(manifest, 'packs.json')
        with open(manifest, encoding='utf-8') as handle:
            declared = json.load(handle)
        for entry in declared.get('packs') or ():
            named = entry.get('preview')
            if not named:
                continue
            found = os.path.join(beside, named)
            if os.path.isfile(found):
                bundle.write(found, named)
    return path


def declare(baked: str, assets: str, into: str,
            tag: str) -> list[dict[str, Any]]:
    """Build every archive a release carries; what the registry says of them.

    The cars first, because they are the pack the game cannot start without;
    then the art every track shares; then a pack per track, each naming that
    art in ``needs`` so choosing a track fetches a track that works.
    """
    packs = []
    path, size, sha = build(assets, 'glisteel-cars', into)
    packs.append(_entry('cars', 'The cars', path, size, sha, tag,
                        marker='cars/hero.glb', base=True,
                        copyright=_credits(assets),
                        notes='The hero car, its wheels and five traffic cars.'))

    path, size, sha = build(os.path.join(baked, '_art'), 'glisteel-forest-art',
                            into)
    packs.append(_entry('forest-art', 'Forest art', path, size, sha, tag,
                        marker='trees', copyright=TREE_CREDIT,
                        notes='Tree and gantry art, shared by every track.'))

    for name in sorted(os.listdir(baked)):
        where = os.path.join(baked, name)
        if name.startswith('_') or not os.path.isdir(where):
            continue
        path, size, sha = build(where, 'glisteel-%s' % (name,), into)
        packs.append(_entry(name, _titled(where, name), path, size, sha, tag,
                            marker='tileset.json',
                            needs=['%s/forest-art' % (NAMESPACE,)],
                            copyright=_world_credit(where),
                            notes=_summary(where),
                            preview='previews/%s.jpg' % (name,)))
    return packs


def install(into: str) -> None:
    """Put what was built into the store the game reads, and say where.

    Through the game's own :mod:`glisteel.content`, so what is installed is
    what it will look for -- the registry it ships, the namespace it declares
    and the store it opens, rather than a second opinion about any of the
    three.
    """
    from glisteel import content

    store = content.store()
    packs = catalog.merge(catalog.load(CATALOG))
    print('store: %s' % (store.root,))
    for chosen in catalog.offered(packs):
        # As a download does: the choice, and the art it is incomplete
        # without, into the chosen pack's own directory.
        for pack in catalog.with_needed(chosen, packs):
            where = publish.install(pack, store, into, within=chosen)
            print('  %-24s %s' % (pack.key,
                                  os.path.relpath(where, store.root)))


def push(tag: str, paths: list[str]) -> None:
    """Attach the built archives and the registry bundle to the release."""
    publish.push(publish.repository(URL % (tag, 'x')), tag, paths,
                 title='glisteel content %s' % (tag,),
                 notes='The cars, the shared forest art and the tracks this '
                       'release offers. Terms are in the registry and in each '
                       "pack's own CREDITS.txt.")
    print('attached %d files to %s' % (len(paths), tag))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--tag', default='content-v1',
                        help='the release tag the artefacts are attached to '
                             '(default: %(default)s)')
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
    parser.add_argument('--into', default=os.path.join(HERE, 'dist', 'content'),
                        help='where to write the archives')
    parser.add_argument('--assets', default=os.path.join(HERE, 'glisteel',
                                                         'assets'),
                        help="the game's own art, which becomes the base pack")
    parser.add_argument('--install', action='store_true',
                        help="install what was built into this machine's own "
                             'store, so the game runs against it with nothing '
                             'published')
    parser.add_argument('--push', action='store_true',
                        help='attach the archives and the registry bundle to '
                             'the release at --tag, creating it if it is not '
                             'there yet (needs the GitHub CLI, and an account '
                             'that may write here)')
    options = parser.parse_args(argv)

    baked = options.baked or bake(options.worlds, options.recipes,
                                  options.depth)
    if not os.path.isdir(os.path.join(baked, '_art')):
        print('%s holds no _art: bake with --art-pack' % (baked,),
              file=sys.stderr)
        return 2
    os.makedirs(options.into, exist_ok=True)

    packs = declare(baked, options.assets, options.into, options.tag)
    with open(CATALOG, 'w', encoding='utf-8') as handle:
        json.dump({'namespace': NAMESPACE, 'packs': packs}, handle, indent=1)
        handle.write('\n')
    bundle = bundle_registry(CATALOG, options.into)
    print('registry bundle: %s (%.0f KB)'
          % (os.path.basename(bundle), os.path.getsize(bundle) / 1024))
    total = sum(one['approximate_bytes'] for one in packs)
    print('%d packs, %.1f MB, written to %s'
          % (len(packs), total / 1048576, os.path.relpath(CATALOG, HERE)))
    for one in packs:
        print('  %-24s %6.1f MB  %s'
              % (one['key'], one['approximate_bytes'] / 1048576,
                 one['sha256'][:12]))

    if options.install:
        install(options.into)
    if options.push:
        push(options.tag,
             [os.path.join(options.into, one['url'].rsplit('/', 1)[-1])
              for one in packs] + [bundle])
    return 0


TREE_CREDIT = (
    "'Fir tree' by Georgeous, 'Noel_Pine_Tree' by 3D Error 404 and 'Maple "
    "trees pack' by LOLIPOP, all CC-BY 4.0; ground materials from ambientCG "
    "(CC0 1.0). The meshes, textures and impostor cards here are derivative "
    "works and carry the same licence; packaged by the glisteel project.")


def _entry(name: str, title: str, path: str, size: int, sha: str, tag: str,
           marker: str, copyright: str, notes: str = '',
           needs: list[str] | None = None, base: bool = False,
           preview: str = '') -> dict[str, Any]:
    entry: dict[str, Any] = {
        'key': '%s/%s' % (NAMESPACE, name),
        'title': title,
        'url': URL % (tag, os.path.basename(path)),
        'directory': name,
        'archive': 'tar',
        'approximate_bytes': size,
        'sha256': sha,
        'copyright': copyright,
        'marker': marker,
    }
    if base:
        entry['base'] = True
    if needs:
        entry['needs'] = needs
    if notes:
        entry['notes'] = notes
    if preview:
        entry['preview'] = preview
    return entry


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


if __name__ == '__main__':
    raise SystemExit(main())
