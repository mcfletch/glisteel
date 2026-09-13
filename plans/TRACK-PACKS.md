# Tracks as downloads, and more than one of them

**Status: §1 has landed — `glisteel-bake --recipe` and every scalar knob, with
the four launch recipes in `glisteel-editor/tracks/`. All four bake, and the
figures below are measured rather than projected. §2–§7 are open.**

A release should offer a player several tracks that feel unlike each other,
without any of them being in the wheel. This plan covers what a track costs,
how a set of them is defined and built, and what makes them different. The
facility that fetches them is
the engine's
([CONTENT-PACKS.md](https://github.com/mcfletch/openglcontext/blob/main/plans/CONTENT-PACKS.md));
this is what glisteel puts through it.

## What a track costs

Measured on this machine, `glisteel-bake` from `glisteel-editor` 1.0.0a1:

| bake | on disk | `.tar.gz` | files | time |
|---|---|---|---|---|
| default — extent 4096, depth 4, resolution 33, `field` ground and forest | **57 MB** | 48 MB | 179 | 22 s |
| `--forest tiles --ground tiles`, same extent and depth | 91 MB | 57 MB | 347 | 32 s |
| extent 1024, depth 2, `--forest tiles --ground tiles` | 7.2 MB | 4.5 MB | 27 | — |

The default breaks down as:

| | |
|---|---|
| `trees/` — bark, branch and impostor maps, per-species meshes | 26.0 MB |
| `trees.npz` — where this track's trees stand | 9.2 MB |
| 154 `t_*.glb` terrain tiles | 17.4 MB |
| `terrain-control.png` | 2.3 MB |
| `terrain-height.png` | 1.3 MB |
| road surface, signs, gantry, manifest, credits | ~0.8 MB |

Compression gains little — 57 MB to 48 MB — because PNG and GLB are already
compressed.

**26 MB of every `field` bake is the same 26 MB.** Baking seed 11 and seed 99
gives byte-identical `trees/` directories; only `trees.npz`, the tiles and the
terrain maps differ. So four tracks is not 4 × 57 MB. It is one shared art pack
and four track packs of roughly 31 MB each at full extent, which is the same
map-pack-plus-texture-pack split twig-bb already uses for Unvanquished maps and
their `companions`.

### How the shared art is carried

A track pack and its art pack **both unpack into the track's own directory**, so
`trees/` lands beside the tiles and every path in the tileset resolves as it
does today. That costs 26 MB of disk per installed track and keeps the
invariant `tracks.py` documents — a whole world is one directory that can be
moved, copied or deleted. The archive is fetched once and cached; only the
extraction repeats.

The alternative — one shared directory and `../_shared/...` in the tiles —
saves disk and makes a track directory no longer self-contained. Disk is the
cheaper thing to spend. If a player ever has enough tracks installed for it to
matter, the store can hard-link identical files without either the baker or the
game changing.

## Tracks as recipes

A track is defined by a file, not by a command somebody remembers typing.
`glisteel/tracks/*.toml` in this repository, one per track, tiny, reviewed like
code and read by `glisteel-bake --recipe`:

```toml
name = "Ashdown"
seed = 11
extent = 4096
depth = 4
ground = "field"
forest = "field"
```

That gives three things the current command line does not: a release that can
be rebuilt from the tag that produced it, a diff when a track changes, and a
place to put the knobs below without growing a flag for each at the call site.

## What makes them different

`ProceduralWorld` takes about twenty parameters and `glisteel-bake` passed six,
so the worlds it could bake were seeds of one idea. The rest were implemented,
documented and unreachable; `glisteel_editor.recipe` declares them once, and
both the command line and a recipe read that:

| | |
|---|---|
| `closed`, `route`, `start_at` | point-to-point rather than a loop; a drawn line |
| `channels` | rivers, which the circuit then crosses |
| `water_level` | raise it and the valleys flood |
| `relief` | flat through to alpine |
| `maximum_bank` | flat corners through to a banked oval |
| `variety` | how unlike each other the corners and straights are |
| `structures` | whether bridges and bores are built at all |
| `posted` | the speed the circuit is signed at |
| `tree_height`, `control_size`, `field_resolution` | |
| `source` | a real DEM as the height base |

"More interesting tracks" was a surface question: the generation was already
there. What each setting does to a world is in the table below, and the
difference between Ashdown and its three siblings is entirely these.

Three need more than a number and are deliberately still out: `route` (a drawn
centreline, which the editor writes), `channels` (river beds, which want their
own small notation) and `source` (a height source such as a real DEM). Each
would be a path in a recipe rather than a value.

Two things fell out of wiring it. `describe()` read the seed and extent off the
*command line*, which now says nothing unless asked, so the manifest recorded
`None`; it reads the world instead, which is what it was describing all along.
And it hardcoded `closed=True`, so a point-to-point run would have been
published as a lap — a chooser reads that field to know which it is.

## The launch set

Four tracks, each leaning on a different part of what is already built. All
four are baked from committed recipes and **measured**, not projected; "unique"
is what is left after the shared art pack.

| track | km | shape | unique | what carries the road |
|---|---|---|---|---|
| **Ashdown** | 7.19 | lap | 30.4 MB | 895 m bridge, 289 m bore, 251 m causeway |
| **Tidewater** | 7.29 | lap | 39.2 MB | 1035 m bridge, 566 m bore, **773 m causeway** |
| **Beacon** | 3.02 | **open** | 11.9 MB | 1053 m bridge, **1774 m bore** |
| **Steelbowl** | 1.70 | lap | 6.5 MB | none |

**Ashdown** is the home circuit and the world every other measurement here is
read against: the shipped defaults, written down.

**Tidewater** raises `water_level` until the valleys flood, and the numbers say
it worked — three times the default's causeway, and the bridges half as long
again. Its corners are laid nearly flat so the causeways read as causeways
rather than as banked curves. One setting, no new code path.

**Beacon** is `closed = false`: a hill climb with a start and a finish rather
than a lap, at high `relief` over a quarter of the extent. It spends more than
half its length inside the hill, which is what an alpine climb does and what
nothing shipped has exercised.

**Steelbowl** is `maximum_bank` near its ceiling with `variety` at zero and
`structures` off — a short banked oval, and the cheapest thing in the release.

With the 25.5 MB art pack that is **113.6 MB** for all four, and a player who
wants one track downloads between 32 MB and 65 MB.

The recipes are `glisteel/tracks/*.toml`, read by `glisteel-bake --recipe`.

## Work

1. **`glisteel-bake --recipe`**, and pass-through for every scalar
   `ProceduralWorld` parameter. Tests: a recipe round-trips to the world it
   describes; an unknown key is refused rather than ignored.
2. **`--art-pack`** — write the shared art to a separate directory instead of
   into the track, so one bake produces the pack and the rest reference it.
3. **Track pictures.** `glisteel <tileset> --picture` already drives a lap and
   photographs it; the release build runs it per track, and the result is the
   pack's `preview`. The engine resolves a preview against the registry, so a
   chooser shows what each track looks like before a byte of it is downloaded.
4. **`glisteel/packs.json`** and `glisteel/previews/*.jpg` — the four tracks and
   the art pack, with digests, `needs` naming the art pack, and `copyright`
   carrying the tree attributions the manifest already records (Fir tree by
   Georgeous, Noel Pine by 3D Error 404, Maple trees by LOLIPOP, all CC-BY 4.0;
   ambientCG ground materials CC0). Also published as a **registry bundle** —
   the JSON and the thumbnails zipped together — on the same release, so a later
   set of tracks can be offered to an already-installed game by pointing it at a
   URL rather than by shipping a new version.
5. **The download screen**, on the engine's `FetchJob`, reached from the track
   chooser: what it is, how big, its terms, a bar, and a cancel.
6. **The release workflow** — bake every recipe, take each picture, archive,
   digest, and upload to a `content-v1` tag. Reproducibility is worth having
   here: the archive should be built with fixed timestamps and sorted entries so
   a rebake at the same tag gives the same digest. Whether the bake itself is
   byte-deterministic at a given seed needs checking before that is claimed.
7. **`glisteel/assets/`** (1.3 MB of cars) becomes the **base pack** — the
   engine's `base` flag, fetched before the menu on a first run, digested,
   published to the same `content-v1` tag as the tracks. A fresh `uv run --with
   glisteel glisteel` then reaches the network before it can draw a car, which
   is the cost of keeping data off PyPI; `OPENGLCONTEXT_CONTENT` is what a
   packaged, offline or CI run uses instead.

## One thing in the way

**`glisteel-editor` is not on PyPI.** Nothing but this workspace can bake a
track today, which is fine for a release we build ourselves and not fine for
the workflow in item 6 unless it installs the editor from the repository. It
also means a player cannot make their own track from an installed game.
`openglcontext-editor` is already published at 1.0.0a1, so the precedent and
the dependency both exist.
