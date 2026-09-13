#! /usr/bin/env python3
"""Build the content a release carries, and the registry that names it.

A track is 30 MB and a release of four is 114 MB, so the content does not go to
PyPI with the code: it is attached to a GitHub release and fetched by
:mod:`OpenGLContext.contentpacks`. This builds the archives, measures them,
digests them, and writes ``glisteel/packs.json`` naming what it built.

    tools/release_content.py --from <baked> --tag content-v1

``<baked>`` is a directory holding one directory per track plus ``_art`` -- what
``glisteel-bake --recipe ... --art-pack`` produces. Every digest in the registry
is of a file this wrote, so the registry cannot describe content that was never
built.

**The archives are reproducible.** Fixed timestamps, sorted entries, no owner
and no mode beyond read/write, so building the same content twice gives the same
bytes and the same digest -- which is what makes a digest worth recording and a
rebuild from a tag worth attempting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile

#: Where a release's artefacts are fetched from.
URL = 'https://github.com/mcfletch/glisteel/releases/download/%s/%s'

#: The namespace this game's packs sit under.
NAMESPACE = 'glisteel'

#: Everything in an archive carries this, so the bytes do not depend on when
#: they were built. The date is arbitrary and fixed; what matters is that it
#: does not move.
EPOCH = 1600000000


def build(where: str, name: str, into: str) -> tuple[str, int, str]:
    """Archive ``where`` as ``name``; return its path, size and digest."""
    path = os.path.join(into, '%s.tar.gz' % (name,))
    with tarfile.open(path, 'w:gz', compresslevel=9) as archive:
        for root, directories, files in os.walk(where):
            directories.sort()
            for leaf in sorted(files):
                full = os.path.join(root, leaf)
                info = archive.gettarinfo(full,
                                          os.path.relpath(full, where))
                info.mtime = EPOCH
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                info.mode = 0o644
                with open(full, 'rb') as handle:
                    archive.addfile(info, handle)
    return path, os.path.getsize(path), digest_of(path)


def digest_of(path: str) -> str:
    found = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            found.update(block)
    return found.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--from', dest='baked', required=True,
                        help='a directory of baked tracks, plus _art')
    parser.add_argument('--tag', default='content-v1',
                        help='the release tag the artefacts are attached to')
    parser.add_argument('--into', default='dist/content',
                        help='where to write the archives')
    parser.add_argument('--assets', default='glisteel/assets',
                        help="the game's own art, which becomes the base pack")
    options = parser.parse_args(argv)
    os.makedirs(options.into, exist_ok=True)

    packs = []
    art = os.path.join(options.baked, '_art')
    if not os.path.isdir(art):
        print('%s holds no _art: bake with --art-pack' % (options.baked,),
              file=sys.stderr)
        return 2

    path, size, sha = build(options.assets, 'glisteel-cars', options.into)
    packs.append(_entry('cars', 'The cars', path, size, sha, options.tag,
                        marker='cars/hero.glb', base=True,
                        copyright=_credits(options.assets),
                        notes='The hero car, its wheels and five traffic cars.'))

    path, size, sha = build(art, 'glisteel-forest-art', options.into)
    packs.append(_entry('forest-art', 'Forest art', path, size, sha,
                        options.tag, marker='trees',
                        copyright=TREE_CREDIT,
                        notes='Tree and gantry art, shared by every track.'))

    for name in sorted(os.listdir(options.baked)):
        where = os.path.join(options.baked, name)
        if name.startswith('_') or not os.path.isdir(where):
            continue
        path, size, sha = build(where, 'glisteel-%s' % (name,), options.into)
        packs.append(_entry(name, _titled(where, name), path, size, sha,
                            options.tag, marker='tileset.json',
                            needs=['%s/forest-art' % (NAMESPACE,)],
                            copyright=_world_credit(where),
                            notes=_summary(where),
                            preview='previews/%s.jpg' % (name,)))

    registry = {'namespace': NAMESPACE, 'packs': packs}
    out = os.path.join('glisteel', 'packs.json')
    with open(out, 'w', encoding='utf-8') as handle:
        json.dump(registry, handle, indent=1)
        handle.write('\n')
    total = sum(one['approximate_bytes'] for one in packs)
    print('%d packs, %.1f MB, written to %s' % (len(packs), total / 1048576, out))
    for one in packs:
        print('  %-24s %6.1f MB  %s'
              % (one['key'], one['approximate_bytes'] / 1048576,
                 one['sha256'][:12]))
    return 0


TREE_CREDIT = (
    "'Fir tree' by Georgeous, 'Noel_Pine_Tree' by 3D Error 404 and 'Maple "
    "trees pack' by LOLIPOP, all CC-BY 4.0; ground materials from ambientCG "
    "(CC0 1.0). The meshes, textures and impostor cards here are derivative "
    "works and carry the same licence; packaged by the glisteel project.")


def _entry(name, title, path, size, sha, tag, marker, copyright,
           notes='', needs=None, base=False, preview=''):
    entry = {
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


def _titled(where, name):
    manifest = os.path.join(where, 'world.json')
    if os.path.isfile(manifest):
        with open(manifest, encoding='utf-8') as handle:
            return json.load(handle).get('name') or name.title()
    return name.title()


def _summary(where):
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


def _world_credit(where):
    """What the bake recorded about where its content came from."""
    credits = os.path.join(where, 'CREDITS.txt')
    if os.path.isfile(credits):
        with open(credits, encoding='utf-8') as handle:
            first = handle.read().strip().replace('\n', ' ')
        if first:
            return first[:600]
    return TREE_CREDIT


def _credits(where):
    found = os.path.join(where, 'cars', 'CREDITS.md')
    if os.path.isfile(found):
        with open(found, encoding='utf-8') as handle:
            for line in handle:
                if line.strip() and not line.startswith('#'):
                    return line.strip()
    return 'glisteel project, BSD-3-Clause'


if __name__ == '__main__':
    raise SystemExit(main())
