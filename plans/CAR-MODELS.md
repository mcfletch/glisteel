# Car models: the player's car, its wheels, and the traffic

Status: 📋 Planned — awaiting review, do not implement yet.

The car the player drives, the four wheels it rolls on, and the five ordinary
vehicles that use the same road, authored as one Blender script and shipped as
glTF binaries. The player's car is a two-seat electric coupé with a wrapped
canopy, a modelled interior and a racing wheel carrying one number; the traffic
is a set of plain, boxy shapes in painted metal and glass, with seats and
headrests you can see through their windows.

## Why

`glisteel.car` draws the car from two tapered boxes and four cylinders, and
`glisteel.traffic` draws every other vehicle with the same function. That is
enough to drive, and it is the reason the game runs from a checkout with nothing
to fetch, but it sets a ceiling on three things the game already has the
machinery for:

- **The cockpit view is the default view**, and it looks at the inside of an
  untextured box. There is no dashboard, no seat beside the driver, and no
  steering wheel to turn as the car is steered.
- **The engine renders refractive glass** (`KHR_materials_transmission`, with
  `KHR_materials_ior` and `KHR_materials_volume`, resolved to the full backdrop
  path on a real GPU — `OpenGLContext/passes/transmission.py`). Nothing in the
  game asks for it, so the one surface in a car that would show it off is drawn
  as a dark grey box.
- **Traffic is scenery you overtake**, and a shape with no interior reads as a
  prop rather than as somebody driving.

The models also exercise parts of the engine that the forest does not: a
transmissive material in a moving, physics-driven object; several loaded assets
sharing textures; named subtrees pulled out of one file and driven separately.

## What ships

```
tools/cars.py               the Blender script that builds everything
models/cars.blend           written by the script, node graphs live, hand-editable
glisteel/assets/cars/
    hero.glb                body, interior and glass as three named subtrees
    hero-wheel-front.glb    hub at the origin, axle along +X
    hero-wheel-rear.glb     the same wheel, wider
    traffic/saloon.glb      \
    traffic/hatchback.glb    |
    traffic/estate.glb       > the road's ordinary traffic
    traffic/van.glb          |
    traffic/pickup.glb      /
    CREDITS.md              provenance and licence for the art
glisteel/models.py          which file is which, and what a game asks of one
```

`tools/cars.py` follows `grass-clumps/arsenal.py`, which is the working
precedent in this workspace for a script-authored asset set: procedural Cycles
materials, an `ASSETS` table of what gets built, a `.blend` saved *before* the
bake so the file kept for editing still has live node graphs, a bake down to the
three glTF metallic/roughness maps, `--only` to rebuild one asset, `--preview`
to render a still, and arguments taken after `--` so it runs either way:

```bash
/workspaces/OpenGL-dev/.venv-bpy/bin/python tools/cars.py --output-dir models
blender --background --python tools/cars.py -- --output-dir models   # with an install
```

**Editing is expected to happen in the `.blend`.** The script is the source of
truth for what the shapes *are*; a developer who opens `models/cars.blend`,
moves a crease and re-exports gets their change, and a developer who wants the
change to survive the next build puts it in the script. Both are supported and
the README says which is which.

## Conventions the models must satisfy

These are not style choices — the physics, the camera and the wheel animation
already assume them.

| Thing | Value | Where it comes from |
|---|---|---|
| Units | metres, one Blender unit each | the whole workspace |
| Up | +Y in glTF (Blender Z-up, exporter converts) | engine convention |
| Forward | **-Z** | `omi_physics.car_wheels` puts the front axle at `-half_base` |
| Authoring direction | nose along **-Y** in Blender | `export_glb` turns the root π about Z, as in `arsenal.py`; Blender's Front view then looks the car in the face |
| Body origin | centre of the chassis box, not the floor | `Car.follow` sets `node.translation` from the body centre |
| Wheel origin | hub centre; axle along **+X**; spin about X, steer about Y | `Car.follow` sets `(0,1,0,steer)` on the wheel node and `(1,0,0,spin)` on its child |

The player's car is authored to the numbers already in `glisteel.car` and
`CarSpec`, so no handling changes fall out of new bodywork:

| Dimension | Metres | Constant |
|---|---|---|
| Body length | 4.20 | `BODY_LENGTH` |
| Body width | 1.85 | `BODY_WIDTH` |
| Lower body height | 0.62 | `BODY_HEIGHT` |
| Cabin above that | 0.42 | `CABIN_HEIGHT` |
| Wheelbase | 2.55 | `CarSpec.wheelbase` |
| Track | 1.58 | `CarSpec.track` |
| Wheel radius | 0.33 | `CarSpec.wheel_radius` |
| Ride height | 0.14 | `CarSpec.ride_height` |

Two of these need a decision rather than a measurement, and both are called out
as tasks below: the **chassis collider** is a box of `BODY_WIDTH × BODY_HEIGHT ×
BODY_LENGTH`, which covers the lower body and not the canopy; and the **cockpit
eye** (`COCKPIT_UP`, `COCKPIT_BACK` in `glisteel.camera`) has to land behind the
steering wheel and under the roof of a cabin that now exists.

## The player's car

**One volume, cab-forward, tapering to a ducktail.** The silhouette is a single
falling curve from a 0.62 m nose over a canopy peaking at 1.15 m above the road,
down to a cut-off tail at 0.95 m. Nothing on it is decorative: the nose splitter,
the sill channels along the flanks and the rear diffuser are the shapes that
would make the downforce the car is tuned with (`VehicleTuning.downforce`), and
there is no grille because there is no engine to cool — a shallow slot under the
splitter feeds the coolers and that is the only opening in the front.

**The canopy wraps.** The windscreen carries on around the A-pillars and into
the door tops as one surface, so the driver's view to either side is glass out
past the shoulder rather than a pillar at the corner of the eye. The pillars
behind it are as slim as a roof over two people allows. This is the shape the
whole model exists for: it is what the cockpit view looks *through*, and it is
the surface the refraction is on.

**No mirrors.** Nothing is drawn that would have to show a reflection to be
right: a wing mirror needs a second render of the world behind the car, and a
mirror-shaped lump of bodywork showing the sky is worse than a flank with
nothing on it. Cameras where the mirrors would be is what an aerodynamic
electric coupé looks like in any case.

**The paint is the model's.** The car is painted in the `.blend` and the
material is used as it arrives. `CarSpec.paint` stays as what the fallback
primitive body is painted and nothing repaints the model: a colour that is a
runtime parameter is a colour that cannot have a flake, a clearcoat or a
two-tone in it, and the paint is one of the two things — with the canopy — that
say what kind of car this is. The traffic is the other way round for the same
reason, since ten vehicles that differ only in colour are one model recoloured.

**Two seats, and a dashboard that says nothing.** The seats are one-piece
buckets with visible side bolsters and integrated headrests, sitting in a tub
floor with a centre spine between them. The dashboard is an unbroken matte
sweep from door to door — no vents, no switches, no screens, no badges. What
the driver is told is the road, and the four numbers the HUD carries.

**The wheel is a racing wheel.** A flat-bottomed D-shaped rim, two spokes into a
deep hub, and in the hub a blank dark panel where an instrument goes. The speed
stays on the HUD for now; the panel is modelled so that the readout is later a
change to the glyphs and not to the wheel — see *Future work*.

### Named subtrees

`hero.glb` carries three top-level named nodes, which
`load_gltf(path).getDEF(name)` returns as individual Transforms:

| Name | Holds | Drawn in cockpit view |
|---|---|---|
| `body` | bodywork, lights, splitter, sills, diffuser | no |
| `interior` | tub, seats, dash, steering wheel and column | yes |
| `glass` | canopy, side and rear glass — the transmissive material | yes |

Under `interior`, two names matter and they nest. `steering` carries the column
— where it is and how far it rakes — and is never written to at runtime; its
child `steering_wheel` holds the rim and the spokes, and is what turns.
Splitting them is what keeps the rake: writing a rotation onto a node that
already carries one overwrites it, which is why a road wheel is a steer
transform with a spin transform inside it, and this is that arrangement again.

`hidden` on `Car` currently switches the whole shell off for the cockpit view.
It becomes "the exterior is left out of the frame": the interior and the glass
stay, which is what puts a dashboard and a windscreen in front of the driver.
The chase and bonnet views draw all three.

### Wheels

Separate files because they are placed four times and animated: two variants
sharing a rim design, the rear 40 mm wider than the front, both at
`CarSpec.wheel_radius`. Each is a rim (five twin spokes, a dished face, a
machined lip), a brake disc and caliper visible through it, and a tyre with a
shoulder and a sidewall — the shoulder is what makes a wheel read as turning
rather than as a rolling cylinder.

A wheel is modelled with its hub at the origin and its axle along +X, so the
game mounts it under the transform pair it already builds and nothing needs a
correcting rotation. **Wider at the back, one diameter all round**: width is
not simulated, so a staggered fitment costs nothing and is what a rear-driven
car looks like, where a staggered *diameter* would mean a `wheel_radius` per
axle in `CarSpec` and in `omi_physics` — a change to the vehicle spec rather
than to its art.

### Glass, and the refraction

The canopy material is a Principled BSDF with transmission at 1.0, an IOR of
1.52 (flat automotive glass), a light neutral tint and a low roughness. It is
**not** baked: `bake_asset` in the `arsenal.py` pattern only bakes materials
flagged for it, so the glass arrives as the exporter wrote it, and the exporter
writes `KHR_materials_transmission` and `KHR_materials_ior` from those inputs.
The engine's loader reads both (`loaders/gltf/materials.py`) and its PBR pass
samples the captured opaque backdrop at the refracted screen position.

**`KHR_materials_volume` needs asking for by name.** Thickness and attenuation
are what make thick glass tint and bend along the path rather than only at its
surface, and a Principled shader alone does not carry them out: transmission and
IOR export from the shader's own inputs, and volume exports only when the
material also has

- a **Volume Absorption** node in the Material Output's `Volume` socket, whose
  colour becomes `attenuationColor` and whose density becomes
  `attenuationDistance` as its reciprocal — density 0.5 is a distance of 2 m;
- a **`glTF Material Output`** node group with a `Thickness` input, which
  becomes `thicknessFactor` in metres.

That group is the one `arsenal.py` already builds to carry occlusion, with a
second socket on it. With both in place Blender 5.0.1 writes
`KHR_materials_transmission`, `KHR_materials_ior` and `KHR_materials_volume`
together, so the `.blend` stays the single source of truth and the finished
binary needs no patching.

Two things need checking on a real GPU before the material is settled, and both
are tasks below: that transmissive glass on a *moving* object is captured and
sorted correctly by the transmission pass, and what ten traffic cars' worth of
glass costs per frame.

### The steering wheel

The rim turns with the steering, and it turns **fractionally**: a quarter of a
turn of lock is a quarter of the rim's travel, continuously. A rim that stepped
between three positions would be the one thing in the cockpit moving like a
machine rather than like a car.

**The travel is an animation clip in the model, not an angle in the game.** The
file carries one LINEAR clip named `steer`, three keyframes on
`steering_wheel`'s rotation: full left at t=0, centred at t=0.5, full right at
t=1. The game poses it rather than playing it —

```python
player = scene.player(index, loop=False)     # clamped, not wrapped
player.evaluate((0.5 + 0.5 * fraction) * player.duration)
```

— where `fraction` is -1 at full left lock and +1 at full right. The engine's
`Sampler` interpolates and slerps between keys and clamps past the ends, so
every fraction is a valid pose and no value drives the rim past its stop.

**The fraction is the front wheels' own angle**, `wheel.steer_angle` over
`VehicleTuning.maximum_steer`, rather than the key the driver is holding. The
steering lock eases off as the speed rises (`steer_falloff_speed`), so a rim
driven from the input would show full lock at 180 km/h while the front wheels
were barely turned; driven from the wheels, it shows what the car is doing.

Carrying the travel in the clip is what makes the rim's lock an art decision: a
developer who wants 180° of rotation rather than 150° moves two keyframes in
the `.blend` and no code changes. It is also the mechanism anything else that
should move with the steering needs — the column, a set of paddles — since they
join the clip as further channels instead of arriving as further game code.

**The rim turns about its own local Z**, which the column's placement points
along the steering axis, and each end of the travel is less than half a turn
from centre so that a posed rotation says which way the wheel is turned.

**Exporting it.** `arsenal.py`'s `export_glb` exports no animation, since a
weapon has none; the car's export turns `export_animations` on and the rim's
action is keyed on the object's rotation so the exporter has a channel to write.
Three keys and LINEAR interpolation, so the two segments slerp evenly either
side of centre.

**Selecting the clip.** `scene.player_named('steer', loop=False)` — the loader
finds a clip by the name it was authored under, so re-exporting the model with
the clips in another order changes nothing here.

## The traffic

Five kinds, deliberately plain: nothing on them is styled, because their job is
to be recognisably an ordinary vehicle at a glance and at speed, and because
five bland shapes read as "traffic" where five interesting ones read as a car
show. Boxy volumes, flat glazing, painted metal and bright metal trim.

| Kind | Length × width × height (m) | Notes |
|---|---|---|
| `saloon` | 4.6 × 1.80 × 1.45 | three boxes: bonnet, cabin, boot |
| `hatchback` | 3.9 × 1.72 × 1.50 | short nose, tail cut off vertically |
| `estate` | 4.8 × 1.80 × 1.55 | the saloon with the roof carried to the tail |
| `van` | 5.2 × 1.95 × 2.15 | flat front, no side glass behind the doors |
| `pickup` | 5.4 × 1.90 × 1.80 | cab and an open bed with a dropped tailgate |

Each carries, because it is what the request is about and what a player sees
through the windows: **two front seats with headrests, a rear bench where the
kind has one, a dashboard bar and a steering wheel.** Below the glass line the
interior is a floor and a bulkhead — enough that the cabin is a room and not a
hollow shell.

Materials, three per vehicle and shared across all five so the fleet costs one
texture set rather than five: `paint` (metallic body colour, the material the
game recolours per car), `trim` (bright steel for the bumpers, mirrors, door
handles and wheel rims) and `glass`. Traffic glass is tinted and **thin** — the
thickness and attenuation that make the player's canopy worth looking at buy
nothing on a car passing at a closing speed of 200 km/h, and transmission on
ten vehicles at once is the case worth keeping cheap.

Traffic wheels are modelled in place and do not turn, which is what the game
already does and what nobody reads at speed.

Budgets: 1,200–2,000 triangles a vehicle, so ten of them cost less than the
player's car; the player's car gets 25,000 all in (10k exterior, 6k interior,
2k glass, 2.5k a wheel), which is a fraction of one forest tile.

## Changes in the game

| File | Change |
|---|---|
| `glisteel/models.py` | new: which asset is which, loading and caching them, and finding a named subtree |
| `glisteel/car.py` | draw the loaded model; split `hidden` into exterior-only; pose the `steer` clip from the front wheels' angle; keep the primitive car as the fallback when an asset will not load |
| `glisteel/traffic.py` | a `Kind` per vehicle carrying its file *and its dimensions*; one collider shape per kind instead of one shared box; recolour `paint` per car |
| `glisteel/camera.py` | cockpit eye placed against the real interior |
| `pyproject.toml` | `[tool.setuptools.package-data]` so `assets/**/*.glb` ships in the wheel |

**A model that will not load is not an error.** The primitive body, cabin and
wheels stay in `car.py` as what is drawn when an asset is missing or corrupt:
the game runs from a checkout either way, which is the property the current code
has and that is worth keeping.

**Loading, caching and recolouring are engine work, and are in the engine.**
`OpenGLContext.loaders.assets.AssetLibrary` is a directory of models addressed
by relative name: `shared()` hands one copy to every caller that only draws a
model, `load()` hands back a copy of its own to a caller that will change one,
and either returns `None` and logs rather than raising when a file is missing or
will not parse. `recolour()` and `brighten()` paint a whole subtree.

Alongside it, the names an asset is driven by now survive the file:

- `scene.materials[name]` is the `PBRMaterial` the document named, so the
  traffic's `paint` is repainted without touching its glass, and the writer
  writes a material's `DEF` as its glTF name so the round trip holds.
- `scene.player_named(name, loop=False)` is the clip by name, which is what
  poses `steer` without every caller scanning `scene.animations`.

`glisteel/models.py` is the table of filenames on top of that and nothing more.
Moving `twig_bb.art` onto the same library is its own piece of work.

## Testing

Red first: the contract tests below are written and failing before `tools/cars.py`
produces anything, because they are the specification the script is written to.

`tests/test_models.py`, windowless, running against the shipped `.glb` files:

- every asset named in `glisteel.models` loads, and yields the named subtrees
- the player's car's bounding box matches the table above within 20 mm, and its
  nose is at -Z: the geometry ahead of the origin outweighs the geometry behind
- wheel assets are centred on their hub within 2 mm and span their radius
- the glass material reports `transmission > 0` and `ior` near 1.52; the
  traffic glass reports transmission and no volume
- triangle counts are inside the budgets
- each traffic kind's declared dimensions match its model's bounding box, and
  the collider built from it matches too
- the `steer` clip is there, drives `steering_wheel`, and has three keys; posed
  at 0.0, 0.5 and 1.0 it gives full left, centre and full right; posed at 0.25
  it gives half the left travel to within a degree; posed outside 0..1 it clamps
  rather than wrapping

`tests/test_car_and_camera.py` gains: the cockpit eye sits inside the cabin's
bounding box and behind the steering wheel's; `hidden` leaves the interior and
the glass in the scene and takes the exterior out; and the rim follows the front
wheels — a car steering half lock poses the clip half way to its stop, a car
running straight centres it, and full lock either way reaches the keyframe and
goes no further.

A build test for `tools/cars.py` runs only where Blender is installed
(`pytest.mark.skipif`), builds one asset into a temporary directory with
`--only`, and asserts the same contract against the fresh output — so the script
and the shipped files are checked against one specification rather than two.

Looking at it, once, on a real GPU: the engine's own capture fixtures drive a
cockpit frame and a chase frame with `--capture` (a hidden window; the suite's
existing settle-waiting applies) and the frames are reviewed by eye. Reference
images are proposed only after the model is settled — a reference image of art
still being shaped is a test that fails every time the art improves.

Performance, measured the way the README's table was measured — twenty seconds
of autopilot at 1080p, before and after, with traffic at ten: the models are
expected to cost frame time, and the number goes in the README rather than being
discovered by a player.

## Building it: Blender

**Blender 5.0.1 is here as the `bpy` module**, in the virtualenv at
`/workspaces/OpenGL-dev/.venv-bpy` (Python 3.11). There is no `blender` binary
on the path, so the script is run as a plain Python program with that
interpreter. It is the one interpreter here that can `import bpy`, as
`/workspaces/OpenGL-dev/.venv` is the one that can `import OpenGL` — the build
and the game do not share a virtualenv, and neither needs the other's.

The script keeps the `blender --background --python` entry point as well, since
`_script_args()` costs a line and a developer with an install should not have to
care which one they have.

Verified on 5.0.1, against a transmissive Principled material: the exporter
writes `KHR_materials_transmission` and `KHR_materials_ior` from the shader's
`Transmission Weight` and `IOR` inputs, and `KHR_materials_volume` once the
material carries the Volume Absorption node and the `Thickness` socket described
above. The engine's loader reads all three.

Determinism: every random used in generation is drawn from a seeded generator,
so two builds of the same script produce the same bytes and a rebuild showing a
diff is a real change.

## Licensing and provenance

The models are ours, written from the dimensions above, and ship under the
project's BSD-3-Clause with a `CREDITS.md` beside them saying so. No third-party
car model, mesh or texture is copied or traced, and no copyleft-licensed asset
or source is opened in the course of this work — a shape taken from a
photograph of a real car is a design question, not a licensing one, but a mesh
taken from someone else's file is both. If a compatibility fact ever has to come
out of a copyleft source, `CLEAN-ROOM.md` applies and a spec goes in
`glisteel/specs/`.

## Documentation

Part of the work, not a follow-up:

- `README.md`: the module table gains `models.py`; the sentence about the car
  not being drawn in the cockpit view becomes what is actually true (the
  exterior is left out, the interior and glass stay); a short section on where
  the art comes from and how to rebuild it; the frame-rate table re-measured.
- `glisteel/car.py`'s module docstring: it currently says the car is drawn from
  primitives rather than loaded from a file. It becomes: loaded, with the
  primitives as the fallback.
- `glisteel/models.py` and `tools/cars.py` carry the conventions table — axes,
  origins, what each named subtree is for — because that is what a developer
  opening the `.blend` needs.
- `glisteel/assets/cars/CREDITS.md`: authorship and licence.
- OpenGLContext's `docs/` and `plans/`, if the asset-loading capability lands in
  the engine.
- This plan records what was decided and what landed.

## Future work: the instrument

The hub carries a blank panel and no readout, and the speed stays on the HUD
where the game already puts it.

The shape it takes when it goes in: three digit positions, each a `Switch` over
eleven small meshes (blank, and 0–9), grouped as `speedo_d0` … `speedo_d2` on an
emissive material, the game setting `whichChoice` from the speed. Three shapes
drawn, and nothing needed from the engine. The alternative to weigh then is a
world-space `Text` node — the engine has `scenegraph.text`, but the PBR pass has
no path for it, so that is engine work, and it is what any game wanting a sign,
a number board or a label in the world needs.

## Decided

- The paint is the model's; `CarSpec.paint` is what the fallback body is
  painted.
- Wider wheels at the back, one diameter all round.
- Five traffic kinds.
- No mirrors, and no instrument in the hub yet.
- The steering wheel turns fractionally, from a clip carried in the model,
  posed from the front wheels' own angle rather than from the driver's input.
- The column and the rim are two nodes: `steering` carries the rake and is left
  alone, `steering_wheel` is what turns.

## Tasks

| # | Task | Done |
|---|---|---|
| 1 | ~~Find Blender and establish what its exporter writes for glass~~ **Done**: `bpy` 5.0.1 in `/workspaces/OpenGL-dev/.venv-bpy`; transmission, IOR and volume all export, volume by way of a Volume Absorption node and a `Thickness` socket on the `glTF Material Output` group | ☑ |
| 2 | ~~Decide where asset loading lives~~ **Done**: in the engine — `OpenGLContext.loaders.assets`, plus `scene.materials` and `scene.player_named()`, with `docs/gltf.html` and `docs/baking.html` updated | ☑ |
| 3 | ~~Write the contract tests against the specification above; watch them fail~~ **Done**: `tests/test_models.py` and the `glisteel/models.py` table it asserts against — 55 red, every one of them "the model does not load" | ☑ |
| 4 | ~~`tools/cars.py`~~ **Done**: CLI, asset table, `.blend` saved for editing, `--only`, `--preview`. No π turn and no bake — see *What changed* | ☑ |
| 5 | ~~Materials~~ **Done**: paint, accent, trim, interior, rubber, lights and two glasses (thick for the canopy, thin for the traffic) | ☑ |
| 6 | ~~The player's car — exterior~~ **Done**: blade nose, arches at both axles, sill channels, haunch, ducktail, splitter, diffuser, light bars | ☑ |
| 7 | ~~The player's car — interior~~ **Done**: tub, spine, sills, bulkhead, two bolstered seats with headrests, blank dash, column, D-rim, blank hub panel | ☑ |
| 8 | ~~The `steer` clip~~ **Done**: three linear keys at 0.0/0.5/1.0 s, ±150° about the rim's own axis | ☑ |
| 9 | ~~The two wheels~~ **Done**: one diameter, the rear 40 mm wider, hub at the origin, axle along X | ☑ |
| 10 | ~~The canopy's volume~~ **Done**: Volume Absorption + a `Thickness` socket; the file carries transmission, ior and volume | ☑ |
| 11 | ~~The five traffic vehicles~~ **Done**: saloon, hatchback, estate, van, pickup, one material set, 700–770 triangles each | ☑ |
| 12 | ~~`models.py` and `car.py` on the loaded model~~ **Done**, with the primitive car as the fallback | ☑ |
| 13 | ~~`hidden` split to exterior-only; the clip posed from the front wheels~~ **Done** | ☑ |
| 14 | ~~Cockpit eye and collider~~ **Done**: the eye moves to the driver's seat (`COCKPIT_SIDE`), asserted against the model's own column; the collider stays the lower body, and `car.py` says why | ☑ |
| 15 | ~~`traffic.py` on the fleet~~ **Done**: a kind per car, its own collider, its own paint, standing on the road rather than centred in it | ☑ |
| 16 | ~~Package data and `CREDITS.md`~~ **Done** | ☑ |
| 17 | ~~Capture a cockpit and a chase frame~~ **Done**: `--view` starts the game in a view, and both frames were looked at. The cockpit showed the wheels floating with the bodywork hidden, which is fixed: the wheels switch with the shell | ☑ |
| 18 | ~~Re-measure the frame rate~~ **Done**: see *What it costs* | ☑ |
| 19 | ~~Documentation~~ **Done** for what has landed: `README.md` (the cockpit view, the module table, where the art comes from), `car.py`'s docstring, `models.py`, `assets/cars/CREDITS.md`, the engine's `docs/gltf.html` and `docs/baking.html`, and this plan | ☑ |

## What changed while it was built

- **No half turn on the way out, and no bake.** Blender's exporter converts
  *every* node's local transform, not only the root's, so a rotation left on the
  root does not reach a child's local space and a named part measured on its own
  is measured in an unrotated one. The vehicles are therefore authored nose
  along **+Y**, which the exporter maps to -Z with nothing to correct, and each
  named part's local space is the model's own. Nothing is textured, so there is
  no bake: the paint is smooth, the files are 14–38 kB, and the wear
  `arsenal.py` bakes for a weapon held at arm's length would not be read on a
  car passing at a hundred and thirty.
- **The rim turns about its own local Y**, not Z: the exporter's Y-up
  conversion maps the Blender Z it is authored about onto Y.
- **What says which way a vehicle faces is the wheel in front of the driver.**
  The canopy runs back past the seats on a fastback, so the screen is not
  reliably ahead of them; the steering wheel always is.
- **A vehicle model stands on the road** — origin at the contact patch — where
  the primitive car it replaces was drawn about its middle. The traffic's
  collider is placed half a vehicle height above the node.
- **Five materials, not three.** A traffic vehicle carries `interior` and
  `rubber` as well as `paint`, `trim` and `glass`: seats in bright steel read as
  a bumper, and tyres are not trim.
- **The traffic's glass is dark and partly transmissive** (0.55). Fully
  transmissive glass reads as a hole where a window should be.

## The shape, and where its proportions came from

The first version of the body was shaped by hand against perspective renders,
and it read as amateurish: a greenhouse perched on a deck like a bubble, a nose
that drooped into a wedge, and a body that tapered continuously from nose to
tail like a boat. Two tools fixed that, and both are kept:

- **`tools/elevation.py`** draws a true orthographic elevation straight from a
  `.glb`, with a half-metre grid and the road line. A perspective render
  flatters a silhouette; the first elevation showed the whole front end sitting
  0.2–0.3 m too low, with the bonnet *below* the tops of the wheels, which is
  why the wheels looked bolted on.
- **`tools/measure_form.py`** measures a reference car's proportions and prints
  them as a section table in our own numbers. Three things it showed that
  guesswork had wrong: a sports car is **nearly constant in width** from the
  front arches to the tail rather than tapering; it is **much lower** than the
  spec assumed (roof 0.52 above the body centre, not 0.73); and its **front
  arches stand above the bonnet** between them.

The reference was a CC-BY model, "Lamborghini 2.0" by NewlyNewNewbie on
BlendSwap (blend/25453). **Only proportions
crossed** -- a table of numbers -- so nothing this project ships carries that
model's geometry, material or texture, and everything here stays BSD-3-Clause.
The provenance is recorded in `glisteel/assets/cars/CREDITS.md`.

What is deliberately *not* the reference's is the canopy: a long, hard-raked
screen over a short flat roof, narrow enough that the bodywork carries a
shoulder either side, left faceted rather than smoothed. The cabin seats two in
single file down the centreline, which is what a canopy that narrow has room
for, and it puts the driver's eye and the wheel on the car's own axis.

Constants that moved with the measured form: `CABIN_HEIGHT` 0.42 → 0.19 (the
car is lower), and the cockpit eye to the centreline. `BODY_LENGTH`,
`BODY_WIDTH`, `BODY_HEIGHT` and every `CarSpec` number are unchanged -- the
reference's wheels, scaled to our length, came out at radius 0.326, tyre width
0.243 and track 1.52 against our 0.33, 0.24 and 1.58, so the physics needed no
adjustment at all.

## The finish

The paint is a **CC0 material from ambientCG** (`Metal032`, public domain),
fetched through `OpenGLContext.loaders.cc0` and carried at 512 px: its colour,
roughness and normal maps give the finish its grain, the car's colour is
multiplied over them at part strength, and a clear coat sits on top as
`KHR_materials_clearcoat`. The bodywork is smoothed by angle rather than
faceted, so panels are smooth and the crease lines between them stay sharp.
The credit and the one-line fetch are in `glisteel/assets/cars/CREDITS.md`.

Two candidates were rejected first: `PaintedMetal011` and `PaintedMetal012` are
both weathered and rusted, which is a finish for a wreck rather than for a car
whose paint is the second thing a player looks at.

## The finish

The paint is built on a **CC0 material from ambientCG** (`Metal032`, public
domain), fetched through `OpenGLContext.loaders.cc0` and carried at 512 px: its
colour, roughness and normal maps give the finish its grain, the car's colour is
multiplied over them at part strength, and over that sits a clear coat. The
numbers are what a car's paint is -- fully metallic, base roughness 0.15, coat
weight 1.0, coat roughness 0.03 -- and the bodywork is smoothed by angle, so
panels are smooth and the creases between them stay sharp.

Two candidates were rejected first: `PaintedMetal011` and `PaintedMetal012` are
weathered and rusted, which is a finish for a wreck rather than for a car whose
paint is the second thing a player looks at.

**Blender's exporter writes the coat's weight and not its roughness.** A coat
exported from it sits at the extension's default of zero, which is a mirror
rather than a lacquer, so `coat_roughness()` puts the number into the finished
file -- the third thing this build patches in after export, alongside the
canopy's volume and the steering clip's name.

## What a wheel needs to stop looking like a bicycle's

Three faults, each with a different cause, and worth writing down because they
are not obvious from a perspective render:

- **Nothing behind the spokes.** Daylight through a wheel is what makes it read
  as a bicycle's. A car's is filled by the barrel the rim is pressed from and
  the brake disc turning inside it, so both are modelled, along with the
  caliper -- the one part of a wheel that is a different colour.
- **The barrel faced the wrong way.** A cylinder built with its normals
  outward is invisible from inside, which is exactly where it is seen from:
  through the gaps in its own spokes. Its material is double-sided
  (``use_backface_culling = False``, which the exporter writes as
  ``doubleSided``).
- **The tyre was painted with the rim.** ``join`` collapses every part it is
  given into one material, and the tyre was in that list -- so a black tyre came
  out in the rim's bright metal. The rim is its own object now, parented to the
  tyre.
- **The tyre was painted with the rim.** ``join`` collapses every part it is
  given into one material, and the tyre was in that list -- so a black tyre came
  out in the rim's bright metal. The rim is its own object now, parented to the
  tyre, which keeps its rubber.
- **The sidewall was too shallow.** At a fifth of the radius a tyre reads as a
  hoop; ``BEAD_FRACTION`` puts the bead at 0.68 of it, so a third of the wheel
  is rubber.

And the wheels sit **in wells under the bodywork** rather than beside it:
``car_section``'s ``well`` lifts the outer edge of the body clear of the top of
the tyre, the lip of that well is the full width of the car, and the fenders
either side stand about 0.10 above the bonnet and the deck between them. A
first attempt left the arch as a 6 cm flange with the flank tucking straight in
above it, which still read as a wheel bolted to the outside.

## What the car reflects

A painted metal surface is almost entirely its surroundings: the colour decides
very little of what reaches the eye. So the car was reading as a toy in part
because everything it reflected was one sky gradient, the same in a bore as
under a canopy.

`glisteel/reflections.py` draws a small equirectangular panorama for each sort
of place the road runs through — canopy overhead with sky broken through it,
a bore as a dark tube with a lit portal fore and aft, a viaduct as open sky over
a distant treeline — and hands it to the engine's IBL probe, which is
generation-counted and rebuilds itself when the environment changes. The road's
own `structures` say which place the car is in, so the switch happens at a
portal rather than on a timer, and a lap crosses a handful of them.

They are **drawn rather than captured**: small, deterministic, testable without
a GPU, and the probe convolves away everything but the broad shape of the light
anyway. A captured panorama — the tunnel being *this* tunnel — drops into the
same place, since what the renderer is handed is an array.

## What it costs

Measured on a freshly baked 2048 m, depth-3 world, driving the autopilot, with
`DRIVE_STATS` -- the median recent frame rate the game now prints alongside
`--capture`. Eight-second drives, since a longer one spends more of its time
streaming than drawing:

| View | Size | No traffic | Ten vehicles |
|---|---|---|---|
| cockpit | 900×520 | 148 fps | 86–94 fps |
| chase | 900×520 | 21.6 fps | 23.7 fps |
| chase | 1920×1080 | 20.3 fps | 23.7 fps |

**The chase view is streaming-bound on this bake**, not drawing-bound: the same
numbers at both resolutions, and adding ten vehicles does not lower them. What
sets it is how much world a camera seven metres up and behind pulls in, and a
twenty-second drive at the same settings measures 13–14 fps because it covers
more ground and streams more of it.

**The cockpit view draws much less world, and there the traffic is visible in
the frame time**: ten vehicles cost roughly three to five milliseconds a frame,
about half a millisecond each. That is not their geometry -- 700 triangles
apiece -- and it is not their glass: forcing the refraction path off
(`OPENGLCONTEXT_TRANSMISSION=off`) changes nothing measurable. What each vehicle
does cost is its own loaded copy, which is what lets it be repainted: seven or
so shapes with their own materials, ten times over.

Sharing one loaded copy per kind and overriding only the paint per car is the
obvious next step; `AssetLibrary.shared()` is already there for the draw side,
and what it needs is a way to vary one material per instance.

## Open questions

- **What half a millisecond a vehicle is made of.** Ten traffic vehicles cost
  three to five milliseconds a frame in the cockpit view, and neither their
  geometry nor their glass accounts for it. The next thing to try is one shared
  copy per kind with the paint varied per car, which needs a way to override one
  material per instance rather than per model.
- **Interior lighting.** A cabin under a canopy is shaded by the canopy, and the
  sky rig lights the world outside it. The captures on the GPU read well in
  daylight; whether the interior wants a little emissive fill in poorer light is
  still open.
