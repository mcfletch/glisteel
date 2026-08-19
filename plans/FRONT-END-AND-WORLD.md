# The shell round the race, and the world it is driven through

**Status: for review. §1, §2 and §7 have landed; everything else is open.**

Two bodies of work that arrived together and stay together because they answer
the same question — *what is it like to sit down and play this?*

* **§1–§6 the shell**: a menu, a countdown, a finish, a library of tracks and a
  record of what has been driven on each. Today the game is a command line that
  drops you onto a circuit already moving and never tells you that you have
  finished.
* **§7–§12 the world**: what the drive looks like out of the windscreen. A
  viaduct you cannot see off, a bore the sun shines into, and water that is
  ground painted blue.

Measurements below are from the shipped procedural world, seed 11, extent 4096,
baked at depth 4 — 8.3 km of circuit carrying 1.5 km of viaduct, 0.8 km of bore
and 0.5 km of causeway.

---

## Part one — the shell

### §1 The parts of a race — **landed**

`glisteel/run.py`. `Run` is a plain dataclass: fed the length of a physics step
and what the world has done since the last one — how many laps are in, whether
anything has ended the run — it answers with a phase, with `allow()` for what
reaches the car and `timed` for whether the lap clock runs.

    countdown  held on the grid, brake down, clock stopped
    racing     everything the driver asks for, clock running
    finished   the laps asked for are done
    ended      mired, or wrecked

`Session` builds one, steps it inside the fixed loop and gates both the controls
and `RaceTiming` on it. No GL, no window — the practice the root `CLAUDE.md`
requires. 31 tests on the state machine and 10 more through `Session`.

**Two rules follow from it**, and both were previously nobody's job:

* The controls belong to the phase. This closes
  [GAMEPLAY-TEST-HARNESS.md](GAMEPLAY-TEST-HARNESS.md) §4.4: its strict xfail is
  gone, replaced by three tests saying what happens instead — a mired car brakes
  to a stop, is never driven again on the way there, and takes between three and
  twelve seconds about it, because it is on rough ground and grip is what it has
  left.
* A run that is over stays over. The stuck-recovery no longer picks a mired car
  up and puts it back into a race that has ended; `r` is how a player chooses to
  carry on, and `n` starts a fresh race.

`--laps` is how many laps a race is, defaulting to one — a timed lap, which is
what a record (§5) is kept against. `--laps 0` drives on with no finish.

**Still open here:** a jump start. Throttle before the last lamp goes out is a
false start, and this is where that would be answered.

### §2 The countdown — **landed**

`OpenGLContext.ui.hudwidgets.LampRow` in the engine, driven from `RaceHUD`.
Five lamps a second apart, holding 1.4 s with the full rig lit, then out: 6.4 s
from the grid to the green.

Lamps rather than a numeral, because a driver reads the rig with their eyes on
the road and `3… 2… 1…` takes them off it. Every lamp is drawn in a housing
whether it burns or not, so an unlit rig still reads as a rig rather than as
empty screen; a burning one gets a halo, kept inside the spacing so two lit
lamps stay two. `color` recolours the burning ones and leaves the dark ones to
the skin, which is what makes the same widget a start rig here and a fuel
warning elsewhere. Documented in `openglcontext/docs/hud.html`.

The finish takes the middle of the screen with the time. That is as much of §3
as a HUD can say on its own; the panel, the records and the choice of what to do
next are still §3 and §5.

### §3 The finish

A splash on the last lap, and it has to say the only two things a driver wants:
**the time**, and **whether it beat anything**. A panel over a still-running
world (the car coasts; §1 has already taken the controls away), built from
`OpenGLContext.ui` the way twig-bb's screens are, offering *Again*, *Choose a
track* and *Quit*.

Where a lap lands among the records (§5) is the whole content of the splash, so
§5 comes with it.

### §4 The menu

twig-bb's `menu.py` is the pattern and most of it transfers unchanged: three
screens built from `Panel`, `Column`, `Row`, `Button`, `Label` and `Select`,
each a plain function returning a panel, all of it tested with no window because
building a panel touches no GL. `TwigContext` shows the wiring — `pushOverlay`,
Escape putting the menu up over a running match without ending it, every screen
*replacing* the menu rather than stacking on it.

glisteel's version:

    main_menu      Drive, Tracks, Settings, Quit — and Resume when a run is up
    track_screen   the library (§5), as a Carousel of track pictures
    records_screen the best times on the chosen track

`OpenGLContext.ui.settings.open_settings` is already a complete settings screen
generated from the render options; the menu offers it and writes none of it.

**Escape must not throw the run away.** twig-bb's rule, and the reason for it,
applies here exactly.

### §5 A library of tracks, and what has been driven on them

Today a track is a positional argument naming a `tileset.json`. A library needs
three things a directory of tiles does not carry:

1. **A manifest.** `oglc-bake` writes `world.json` beside the tileset: the
   name, the seed, the extent, the length of the circuit, how much of it is
   viaduct/bore/causeway, and the name of its picture. This is **editor work** —
   the baker knows all of it already and prints most of it as its summary — and
   it makes a baked world self-describing for anything that reads one, not only
   for this game.
2. **A picture.** `glisteel --capture` already renders a settled frame and
   exits. A `--track-picture` mode drives to a chosen station, points the camera
   across the circuit rather than along it, and writes the picture the manifest
   names. `Carousel` takes it from there.
3. **Somewhere to look.** A tracks directory, defaulting under
   `appdatadirectory()`, scanned for manifests. `OpenGLContext.userpaths` is the
   engine's one answer to where a per-user file goes and this uses it rather
   than inventing a second.

**Best times**: `Records`, a plain object over a JSON file in the same place,
keyed by track name, holding the best *n* (five) laps with the date and the car.
A lap is offered to it and it answers with the position it took, or none — which
is exactly what the splash in §3 needs to say. No GL, no window, and the file
format is one a person can read.

### §6 What the shell costs

The state machine and the HUD are small. The menu is a day's work with twig-bb
open beside it. The manifest and the picture mode are the two that reach into
other repositories, and they are the two worth doing first among the library
items because everything else in §5 reads what they write.

---

## Part two — the world

### §7 The viaduct — **landed**

`OpenGLContext.scenegraph.roadworks.BarrierProfile`. A barrier has to be tall
enough to hold a car and low enough to see past, and those pull opposite ways.
What settles it is that they apply to different parts of it: a solid **kerb**
(0.35 m) is what a wheel meets, and an open railing above it — two bars on posts
at 2.5 m — takes the barrier to its full height (1.1 m) while being almost
entirely holes.

What a driver sees down past is the kerb, because the railing is looked through.
`BarrierProfile.sightline(eye, offset)` is that as a number, and it is what the
tests assert:

| barrier | below horizontal | nearest ground from a deck 40 m up |
|---|---|---|
| solid wall, 0.95 m | 5.7° | 402 m |
| kerb 0.35 m + railing to 1.10 m | **14.9°** | **150 m** |

A `kerb` at or above `height` is a wall and no railing is built, which is what a
causeway a metre over a marsh wants — there is nothing under it to see, and
`CausewayProfile` keeps its own low wall for that reason.

`BridgeProfile.parapet_height` and `.parapet_width` are now `BridgeProfile.parapet`,
a `BarrierProfile`. Documented in `openglcontext/docs/roads.html`.

*The measurement that started it:* the cockpit eye sits **1.31 m** above the
carriageway and the barrier stands 3.6 m to the side, so 0.95 m of solid wall
left a driver 5.7° of downward view — and 1.5 km of the 8.3 km lap looking at
grey.

### §8 Rivers and lakes

**Lakes and sea: yes, as a waterline. Rivers: no. Neither is placeable.**

What exists is one module constant, `WATER_LEVEL = 0.0` in
`OpenGLContext.loaders.tiles3d.procedural`, used three ways:

* `HeightfieldLayer.water_level` clamps the ground mesh flat wherever it falls
  below that height, so a basin becomes a level plate.
* `terrain_colors` paints anything at or under it `(0.10, 0.27, 0.42)`.
* `choose_structures(waterline=…)` marks fill over drowned ground as a causeway
  rather than an embankment, which is why the shipped circuit has 516 m of one.

So a lake is **opaque vertex-coloured ground at roughness 1.0**. It has no
transparency, no reflection, no specular highlight, no motion and no shoreline —
the sand band in `terrain_colors` is a height ramp on the land, not a beach
against a water edge. A river is a channel, and nothing carves one: the height
function has no drainage and the waterline is a single global plane, so the only
water in a world is wherever the land happens to dip below zero.

**The editor places neither.** `glisteel_editor.project.Landscape` offers
`extent`, `seed`, `resolution` and `tree_density`; `RouteEditor` edits a plan of
`(x, z)` points. There is no water in the project format and no tool for it.

What the three questions asked for, in the order they build on each other:

1. **A water surface worth crossing.** Its own layer rather than clamped
   ground: a transparent, low-roughness, reflective plane at the waterline, with
   the terrain left to dip under it so a shoreline emerges from the geometry
   instead of from a colour test. This is the one that changes the picture most,
   and everything else here is scenery beside it.
2. **A waterline the world can choose.** `WATER_LEVEL` becomes a field on
   `ProceduralWorld` and a field on `Landscape`, so a project can flood a basin
   or drain it. Small, and it is what makes the editor able to place water at
   all.
3. **Rivers.** A channel is a *route* — a polyline with a width and a bed
   profile, carved into the height function the way a road cutting already is.
   `RoadPath` and the earthworks machinery are most of the shape of it, which
   makes this a large piece of work rather than an unbounded one. A bridge over
   a carved river is then what `choose_structures` already builds.

Seeing the bank and the trees on it while crossing is (1) plus §7: with an open
railing and a real water surface, a crossing looks like a crossing.

### §9 The bore takes the sun

Inside the tunnel the lining is lit from one side — cream-white on the right,
near-black on the left. The bore runs *inside a hill* and the sun is reaching
its walls, because the terrain it passes through is carved away for the
carriageway and nothing is left to occlude the light. The gloom that makes a
tunnel dark is baked into the lining's vertex colours
(`TunnelProfile.daylight`, `.gloom`), and the sun is applied on top of it.

This is a rendering defect and it is the engine's: a surface inside a closed
lining cannot see a directional light, and the lining is closed. Two candidate
fixes, and the choice wants measuring rather than arguing:

* **Occlude it properly** — the bore is inside geometry that ought to be in the
  shadow map and is not, which is worth understanding whatever else is done,
  because it may be true of other interiors.
* **Carry the darkness in the material** rather than in vertex colour, so the
  lining is not lit by anything the world's rig does.

### §10 The bore has no lights, and the car has none

No luminaires, no headlights, nowhere. The engine has `PointLight` and
`SpotLight` and binds up to eight in a frame, so the parts exist:

* **Tunnel lighting** is world content: a run of luminaires along the crown at a
  spacing, written by the bake beside the bore. Sodium-warm, and few enough at
  once to sit inside the eight-light budget — which means placing them by
  proximity to the car rather than lighting the whole bore at once.
* **Headlights** are two spotlights carried on the car body, which the game
  already owns and moves every frame. They want to come on in the dark and
  sweep the lining as the car turns, which is exactly what a spotlight parented
  to the chassis does.

Eight lights is the ceiling and both features want to live inside it together,
so what the budget is spent on is a decision to take once rather than twice.

### §11 What a lap costs to draw

Measured at 1280×720 on this machine, autopilot, shipped world:

| where | frames a second |
|---|---|
| on the grid, dense forest | **22.8** |
| inside the bore | 137.4 |
| on the viaduct | 142.6 |

The forest is the whole cost, and 22.8 is under a display refresh. Turning
shadows off takes it to 29.4 — so shadows are about a quarter of it and the
other three quarters is the trees themselves.

This wants profiling before anything is decided about it. Recording it here
because the root `CLAUDE.md` sets the bar at *headroom for a heavier game than
this one*, and a demo already under 25 fps has none.

### §12 Does it look polished and realistic?

The landscape does. The car and the cockpit do not.

**What is working.** The forest road reads as a real road: correct markings, a
shoulder, a verge, foliage that varies, bark that holds up close, canopy shade
that darkens the ground under a dense stand. Distant hills, haze that closes
the world without an edge. The tunnel genuinely goes dark and the portal
genuinely glows at the far end.

**What is not.**

1. **The car is a faceted block** with a white slab for a cabin, and it is in
   the middle of the frame in the chase view for the whole race. It is the least
   finished thing on screen by a wide margin. [CAR-MODELS.md](CAR-MODELS.md) is
   the plan for this.
2. **The cockpit is a grey box and a wheel.** From the driver's seat — the
   default view — the bottom third of every frame is untextured grey. §12's
   effect is out of proportion to the work: a dashboard with instruments, a
   windscreen frame and hands would change the game's whole impression.
3. **Nothing casts a readable shadow onto the carriageway.** Shadows are on and
   cost a quarter of the frame rate, and the light they produce is a general
   darkening of foliage rather than trunk-shadows striped across the tarmac —
   which on a sunlit forest road is the thing that most says *outdoors*. Worth
   finding out where the cascade is going.
4. **The map is an outline and a dot.** No heading, no start/finish, no
   structures, no sense of which way is coming up. Carried over as
   [GAMEPLAY-TEST-HARNESS.md](GAMEPLAY-TEST-HARNESS.md) §4.6, still open, and
   engine work in `MiniMap`.
5. ~~**§7's wall**~~ — fixed: the deck's barrier is a low kerb carrying an open
   railing, so the 1.5 km of viaduct is a crossing rather than a corridor.

### §13 The autopilot does not get round

Left to itself on the shipped circuit the autopilot mired at 1:32, in trees,
having left the road. It laps the synthetic test circuits, so this is the real
world's corners rather than the steering. It matters beyond itself: the
autopilot is what drives every capture, every recording and every track picture
(§5), so a track it cannot finish is a track that cannot photograph itself.

---

## Order of work

1. ~~**§1 run states**~~ — landed.
2. ~~**§2 countdown**~~ — landed.
3. ~~**§7 the viaduct railing**~~ — landed.
4. **§5.1 the bake manifest** and **§5.2 the picture mode** — everything else in
   the library reads what these write.
5. **§5 records**, then **§3 the splash**, which needs them.
6. **§4 the menu**, which needs the tracks and the records to have something to
   offer.
7. **§9 the sun in the bore** — a defect, and cheap if the shadow answer is the
   right one.
8. **§8.1–8.2 water** — the surface and a settable waterline.
9. **§10 lights**, **§11 the frame rate**, **§12.2 the cockpit**, **§13 the
   autopilot**, **§8.3 rivers** — each large enough to be planned on its own.

## Documentation owed

* `glisteel/README.md` — the menu, the track library, where records are kept,
  the new command-line modes.
* `openglcontext/docs/` — `LampRow` in the HUD widget documentation; the
  parapet profile in whatever documents `roadworks`.
* `openglcontext-editor` — the `world.json` manifest, as a written format.
* This file, kept as the record of what landed.
