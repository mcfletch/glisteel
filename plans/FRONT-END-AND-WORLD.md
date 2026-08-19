# The shell round the race, and the world it is driven through

**Status: §1–§5, §7, §8 (lakes), §9 and §10 have landed, along with the traffic,
steering and autopilot defects found on the way. §11 (the frame rate), §12.2
(the cockpit), rivers and the autopilot's overtaking are open.**

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

### §3 The finish — **landed**

`menu.finish_screen`. Two things a driver wants and no more: **the time**, and
**whether it beat anything**. Where the lap landed in this track's table is the
whole content of it, so the table is shown with it, and a lap that did not make
the table says neither — that is not a failure and is not dressed as one. Over
the world it was driven in, with nothing behind it, so Escape does not close it:
the race is over and the choice of what happens next has to be made.

### §4 The menu — **landed**

`glisteel/menu.py`, built from `OpenGLContext.ui` the way twig-bb's screens are:
plain functions returning a `Panel`, all of it tested with no window because
building a panel touches no GL. Drive, Tracks, Settings, Quit — and Resume first
when a race is running, with Escape meaning what Resume means, because a player
who pressed it meaning "close this" must never find they have thrown the race
away instead. Settings is the engine's own generated render-options screen.

### §5 A library of tracks, and what has been driven on them — **landed**

Three pieces, and the first is the one everything else reads:

1. **The manifest.** `oglc-bake` writes `world.json` beside the tileset — name,
   seed, extent, how long the road is, how many metres of it are on bridges,
   bores and causeways, and which picture shows it. The *format* is the
   engine's (`OpenGLContext.loaders.tiles3d.manifest`), so anything that loads a
   baked world can read one without depending on the authoring package.
2. **The picture.** `glisteel <tileset> --picture` drives the world,
   photographs the car on it from behind, and records the picture's name in the
   manifest. `Carousel` shows the band.
3. **The library.** Every world directory under `tracks_directory()`, which is
   `OpenGLContext.userpaths` plus `glisteel/tracks` — the same rule the engine's
   settings and asset cache follow. Starting with no arguments offers what is
   there; with exactly one world in it, drives that, since choosing between one
   thing is not a choice.

**Records**: five times a track, quickest first, with the day each was driven, in
JSON a person can read. A lap is offered when a race finishes and the table
answers where it came, which is what the finish says. A corrupt file loses the
times, not the game.

### §6 What the shell cost

All of it, and the order held: the manifest and the picture mode first, because
everything else in the library reads what they write; records next, because the
finish is made of them; the menu last, because it needs the tracks and the
records to have something to offer.

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

### §8 Rivers and lakes — **lakes landed, rivers open**

A lake is its own surface now (`OpenGLContext.scenegraph.water`), not the ground
clamped flat and painted blue. The terrain is meshed as it is, dipping under,
and the water laid over it — which is what gives the world a **shoreline**, since
the shore is the line where the land passes through the surface and a levelled
ground has no such line to draw. The sheet is flat and its normals carry a
swell, which breaks the specular highlight into the glitter a still picture
reads as water while leaving the shoreline exactly at the waterline; the swell
is a function of world position, so two sheets that meet agree along their seam.

`ProceduralWorld.water_level` is a field rather than a constant, so a world can
flood its valleys or drain them. The shore is a band — dirt from the bed up to
1.5 m above the waterline, grass no lower, feathered between — and that band is
also what keeps the ground cover out of the lake: the cover grows on the two
soft layers, so a waterline the *layers* respect is one the grass respects
without ever being told where the water is.

**What is left.** Seen from above and from a bank it reads; from road level it
is still flat, because at a grazing angle a lake is the reflection of a bright
sky and the engine's analytic environment gives that as a wash. What would sell
it is a visible waterline against the shore — foam, or a darkening with depth.

**Rivers are open.** A channel is a *route* — a polyline with a width and a bed
profile, carved into the height function the way a road cutting already is.
`RoadPath` and the earthworks machinery are most of the shape of it.

### §9 The bore takes the sun — **fixed**

`SplatTerrain` returned immediately from the shadow pass, so **the ground cast
nothing**: no hill shading the valley behind it, no rock keeping the sun out of
a bore, and no tree shadows on the tarmac. The baked sun and canopy terms the
node carries shade *itself* and say nothing to anything standing on it or
running through it. It writes depth now, through a second vertex array over the
same buffers — the depth program reads the position from a different attribute
than the splat program does, and the ground is the largest mesh in the world, so
no second copy of it.

Measured inside a 390 m bore, the lit wall went from **121 to 45** of 255.

**Still open:** the remaining asymmetry is the ambient. A shadow map occludes
direct light only, and nothing occludes the sky term, so one wall of a bore
still reads brighter than the other.

### §10 The lights — **landed**

`glisteel/lighting.py`, and `TunnelProfile`'s lamp fields in the engine. A bore
is lit **twice**, because a renderer binds eight lights in a frame and a tunnel
has one every twenty-five metres:

* **The lining lights itself.** The pool each luminaire throws is baked onto its
  vertices when the world is built (`bore_shade`), so the whole length of a bore
  is lit at any distance and costs nothing to draw.
* **The few fittings the driver is among become real lights.** `tunnel_lamps()`
  says where they are, the bake writes them into the tileset's `extras`, and the
  game lights the nearest four. A car under a lamp has no idea it is under one,
  which is exactly what a baked pool cannot fix.

The budget divides two for the sun and its sky fill, four for the luminaires and
one for the headlights — seven of eight, one spare. One headlight rather than
two: a pair costs twice the budget and, dipped and converged the way a car's
are, throws very nearly the same pool; what sells them is that the pool sweeps
as the car turns, and one does that.

The first attempt lit the bore evenly end to end, because the point lights had
no distance falloff. With an inverse-square term the wall reads 55 of 255 and
the road 78, against 100 and 154 without it.

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
2. **The cockpit is a grey box and a wheel, and it does not close.** From the
   driver's seat — the default view — the bottom third of every frame is
   untextured grey, and below the dashboard there is *nothing*: at speed the
   road fills the whole bottom of the frame, seen straight down through where
   the driver's feet would be. The second is the view-breaking one and it is
   geometry, not decoration: the tub floor, the toeboard and the sills have to
   meet so that no line of sight from the eye point reaches outside the car
   below the dash. See [CAR-MODELS.md](CAR-MODELS.md).
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

### §13 The autopilot — **fixed on the road, open on the traffic**

It mired at 1:32 on the shipped circuit, having left the road three times in two
minutes. The cause was its own: it commanded a *stick position* while aiming at
a geometric path, so when the steering lock was cut at speed its loop gain went
with it. It works out a **front-wheel angle** now — pure pursuit from the car's
own wheelbase, which the car reports (`RaycastVehicle.wheelbase()`), so there is
nothing left to tune per car — and converts that to an input through the lock
the car actually has. Zero departures in 200 s.

**Still open: it does not overtake.** It slows for whatever is in front and
holds station behind it, so with traffic on it follows the first car it catches
for the rest of the lap. A player overtakes; the autopilot has no notion of
pulling out.

---

## Order of work

1. ~~**§1 run states**~~, ~~**§2 countdown**~~, ~~**§7 the viaduct railing**~~.
2. ~~**§5.1 the bake manifest**~~ and ~~**§5.2 the picture mode**~~, then
   ~~**§5 records**~~, ~~**§3 the splash**~~, ~~**§4 the menu**~~.
3. ~~**§9 the sun in the bore**~~ and ~~**§10 the lights**~~.
4. ~~**§8.1–8.2 water**~~ — the surface and a settable waterline.
5. **§12.2 the cockpit** — instruments, pillars, a bonnet, and a footwell that
   closes, which is the view-breaking one.
6. **§11 the frame rate** — 22.8 fps in the forest at 1280x720, and the trees
   are three quarters of it. Wants profiling before anything is decided.
7. **§13 overtaking** and **§8.3 rivers** — each large enough to be planned on
   its own.

Found and fixed on the way, none of them in this plan when it was written:
traffic off by default and reloading its art every spawn; the autopilot
commanding a stick position rather than a wheel angle; and the steering, which
took a wheel that winds and a straightening assist.

## Documentation

Written as each piece landed, not owed:

* `glisteel/README.md` — the run's parts, the steering and `--assist`, the
  lights and the budget, the track library, the records, and the new modes.
* `openglcontext/docs/hud.html` — `LampRow`.
* `openglcontext/docs/roads.html` — `BarrierProfile` and the sightline, and a
  bore lit twice.
* `openglcontext/docs/gltf.html` — `AssetLibrary.variant`.
* `openglcontext/docs/baking.html` — the world manifest, with its format.
* `openglcontext-editor/README.md` — what a bake writes beside the tiles.
* `glisteel/plans/CAR-MODELS.md` — the cockpit's second pass, and why the blank
  dashboard it originally specified is superseded.
* This file, and `GAMEPLAY-TEST-HARNESS.md` §4.4, §4.5 and §4.10.
