# The vehicles

Every model here is this project's own, built by [`tools/cars.py`](../../../tools/cars.py)
and shipped under the same BSD-3-Clause licence as the rest of GLinting Steel
(see [licence.txt](../../../license.txt)). Nothing is derived from a third-party
model, mesh or texture.

| File | What it is |
|---|---|
| `hero.glb` | the player's car: `body`, `interior` and `glass`, and the `steer` clip its rim turns through |
| `hero-wheel-front.glb`, `hero-wheel-rear.glb` | its wheels, mounted four times; the rear is the wider |
| `traffic/*.glb` | the five ordinary vehicles that use the same road |

The shapes are described in [plans/CAR-MODELS.md](../../../plans/CAR-MODELS.md);
what each one has to be for the game to drive it is asserted in
`tests/test_models.py`. Rebuild them with

    /workspaces/OpenGL-dev/.venv-bpy/bin/python tools/cars.py

which writes `models/cars.blend` for editing and these files for the game.

## Where the shape came from

The player's car is drawn to the **proportions of a real sports car**, measured
from a CC-BY reference — **"Lamborghini 2.0" by NewlyNewNewbie on BlendSwap**
([blend/25453](https://blendswap.com/blend/25453)) — with
`tools/measure_form.py`: where a car of that kind is wide, where its flanks
and its top surface sit, where its floor is, and where its wheels and greenhouse
are, all scaled to the length this game's physics uses.

**No geometry, material or texture of that reference is in these files.** What
crossed is a table of numbers describing proportions, which is why everything
here remains this project's own under BSD-3-Clause. The reference is credited
because taking a shape's measure from someone else's work is worth saying out
loud, not because its licence reaches these files.

The canopy is deliberately not the reference's: a long, hard-raked screen over a
short flat roof, narrow enough that the bodywork carries a shoulder either side
of it, with the cabin seating two in single file down the centreline.

## The paint

The player's car is painted on a **CC0 finish from ambientCG**:
[Metal032](https://ambientcg.com/view?id=Metal032), public domain, fetched and
cached by `OpenGLContext.loaders.cc0` and carried at 512 px. Its colour,
roughness and normal maps give the paint its grain; the car's own colour is
multiplied over them, and a clear coat
(`KHR_materials_clearcoat`) sits on top, which is what makes paint read as
paint rather than as coloured metal.

To fetch it before a build:

    python -c "from OpenGLContext.loaders import cc0; cc0.material('Metal032')"

A build that cannot find those maps paints the car in flat colour and says so,
so the models can still be rebuilt offline.

## The paint

The player's car is painted on a **CC0 finish from ambientCG**:
[Metal032](https://ambientcg.com/view?id=Metal032), public domain, fetched and
cached by `OpenGLContext.loaders.cc0` and carried at 512 px. Its colour,
roughness and normal maps give the paint its grain; the car's own colour is
multiplied over them, and a clear coat sits on top
(`KHR_materials_clearcoat`, weight 1.0, roughness 0.03 over a fully metallic
base), which is what makes paint read as paint rather than as coloured metal.

To fetch it before a build:

    python -c "from OpenGLContext.loaders import cc0; cc0.material('Metal032')"

A build that cannot find those maps paints the car in flat colour and says so,
so the models can still be rebuilt offline.
