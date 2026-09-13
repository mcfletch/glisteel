# What the drive is missing, and one thing the bake gets wrong

**Status: §1 (the bore) has landed, and §6's chooser with it — the five ways of
driving are reachable from the menu at last. §2 is measured and diagnosed to a
line of code. §3, §4, §5 and §7 are open.**

Seven things between the game as it is and the game it is meant to be, gathered
from playing it. They are not one body of work — a terrain-renderer feature, a
traffic defect, a sound system and an editor trial have nothing in common but
the player who meets all of them — so each section stands alone and can be
taken in any order.

A theme runs through three of them, and it is worth naming because it is
cheap to fix and expensive to leave: **the work exists and nothing can reach
it.** The lane-switch control scheme, the climbing lane and the two-lane
profile are all built, tested and invisible.

## 1. A bore does not bore

**The mountain over a tunnel is pushed down to road level**, so a bore reads as
a valley with a lid rather than as a hole through a hill. It is visually broken
and logically wrong: the hill is *there*, and the road goes *under* it.

### What is already built

More than the [2026-08-19 review](2026-08-19-PLAY-REVIEW.md) suggests, which
called the fix "a terrain feature" and left it. Three of the four pieces exist:

- **The collider already has holes.** `physics/heightfield.HeightFieldColliders`
  takes `holes(x, z) -> mask`, "true where the ground is not to be collided
  against -- over a tunnel's bore, say", and drops a triangle when its centre
  falls in one.
- **The game already computes the mask.** `glisteel.world._bores()` returns
  exactly that callable, over every course with a tunnel, and passes it to the
  collider today.
- **The portal already has a face.** `TunnelProfile.portal_border` is "how far
  the portal's face stands out around the arch where the bore meets the
  hillside" — the thing that plugs the opening.

**What is missing is one of the four: the drawn surface cannot skip a cell.**
`HeightField.mesh()` builds a regular grid of quads with no way to leave one
out, so the visible ground has no hole even where the collider does. The
flattening is the workaround for that, and `world._bores()` already says so in
its own docstring: the field terrain "keeps the hill a tunnel passes through,
which is right to look at and a wall to drive into."

### The fix

Replace the terrain cells at each portal and run the bore under the surface
everywhere else. In the three repositories:

- [x] **OpenGLContext** — `HeightField.mesh(holes=...)` drops a *triangle*
      whose centre is in a hole, which is the collider's rule to the letter, so
      the two agree by construction rather than by care. `SplatTerrain` takes
      it; `TilesTerrain.holes` is settable after construction, since a game
      reads a tileset to stand the ground up and reads it again to find the
      roads, and only the roads know where a bore runs.
- [x] **glisteel** — `_bores()` goes to the terrain as well as the collider,
      computed **once** and shared: two closures over the same courses would
      answer alike today and drift apart on any change.
- [x] **openglcontext-editor** — the earthwork reshapes what stands on the land
      and nothing else. `_bore_corridor` went with it, and so did the three
      things that read it: the vegetation clearing (a tree stands on the hill
      again, and how deep the bore is no longer changes what is cleared — the
      tell that the clearing was sized by earthworks nobody digs), the road
      layer painted on the bore's floor, and the boulder rule.

### How it is checked

The defect is invisible from the driving seat, which is how it survived a play
review. So the check is not a drive:

- [x] A capture from *beside* the circuit: a sand-coloured trench gouged
      through the hill before, unbroken hillside after. The deepest bore in the
      shipped world carries 53.5 m of cover.
- [x] The portal from the road: an open arch with hill above it and the road
      running in, driven to at 50 s of a lap.
- [x] A drive through: at 56 s the car is inside the bore — lining, ceiling
      luminaires, traffic ahead, daylight at the far end.
- [ ] Beacon is the case that shows it worst: 1774 m of its 3.02 km is inside
      the hill.

### Left open: the mask is the game's, and belongs to the world

The bore is right **in glisteel** and wrong in `oglc-view`, which shows the hill
filling the entrance. That is not the viewer's fault: holes reach the terrain
only because `RaceWorld` hands `_bores()` over, and a generic tileset viewer
knows nothing about bores. Before this change it showed a trench; now it shows
a wall. `oglc-view` is the tool anyone reaches for to look at a baked world, so
that matters.

The knowledge is in the wrong place, and the tileset already holds what is
needed: `extras.roads[*]` carries `centreline`, `totalWidth`, `closed` and
`structures` — `{"kind": "tunnel", "from": 1177.4, "to": 1466.8}` in the
shipped world. So:

- [ ] `TilesTerrain` derives its own holes from the extras it already loads, and
      every consumer of a baked world gets a bore that is a bore. A caller may
      still pass its own.
- [ ] Which means hoisting the geometry `glisteel.world.Course.inside` does —
      distance to a centreline within a station range, with a margin and an
      approach — into the engine, where the workspace rule says a capability a
      game would want belongs. It is written to answer a whole chunk of terrain
      at once without materialising a distance matrix, and that property has to
      survive the move.
- [ ] glisteel then stops handing them over, or keeps doing so only to override.

Found on the way, and fixed with it: **`glisteel --capture` never ended.** It
drew no frames and produced no error. `faulthandler` on a run that had sat 100
seconds without drawing five frames put the main thread in
`glfw.swap_buffers` — a compositor throttles the swap to its own frame
callback, and a window it is not presenting never gets one. A capture draws a
fixed number of frames and writes a file, so it is no longer paced by a
display.

## 2. Road diversity: half arrived, half never built

Two questions wearing one coat, and they have different answers.

**The lanes are there, and the paint does not say so.** Measured rather than
read: `CIRCUIT_PROFILE` is `lane_width=3.6, lanes=2`, and `CLIMBING_LANE` adds a
third 3.6 m lane wherever the grade sustains 4% over 400 m. Ashdown earns
**1183 m of it** across its 7.19 km — 16.4%, in one run of 597 m and others —
and Beacon 686 m of 3.03 km. It reaches the baked geometry: the tarmac is
10.8 m wide there against the ordinary 7.2 m.

**What is missing is the marking.** `road.road_texture` paints a fixed
cross-section — two edge lines, and one dashed centre at `across == 0.5` of the
image — and `profile.section_u` maps `u = 0.5` to `across = 0` for the widened
profile exactly as for the plain one. So the single centre line is drawn at the
carriageway's *geometric centre whatever its width*: widen the road by a lane
and the line moves out with it. A three-lane stretch comes out as a very wide
two-lane road with the paint down the middle, which is what a player sees and
why the work reads as missing.

For it to read as a passing lane, two things have to change, and both are in
the engine's road texture rather than in any world:

- [ ] The centre line stays where the *original* carriageway's centre was, so
      the extra lane is plainly on one side rather than the road being fatter
      about the middle.
- [ ] A lane line between the two lanes on the widened side — a road with three
      lanes and one line painted on it is not marked, it is merely wide.

The mechanism, read off the code: `road_surface` sets

    u = np.tile(profile.section_u(), len(line))

— **the same texture row at every station**, taken from the base profile.
`widened_sections` moves the cut's vertices apart; nothing moves their `u`. So
a widened section stretches the same paint over a wider road, and the single
centre line goes with it.

That makes this a larger change than it first looks, and worth doing as its own
piece of work rather than tacked on: `u` has to vary per station against a
texture drawn for the *widest* cross-section, so the extra lane occupies its own
span and an unwidened section reaches only the part of the image that is a
two-lane road. Every road the engine draws is textured through that line, so it
wants its own before-and-after captures on a widened stretch, an ordinary one,
and the taper between them — which is where a per-station unwrap would show any
seam.

- [x] A capture of a climbing lane from the road, and one from 30 m straight
      down, which is where the single centre line is unmistakable.

**Intersections were never built.** Nothing in `OpenGLContext_editor` mentions a
road junction; the only `junction` in the tree is `hydrology`, where rivers
meet. A circuit has no need of one, which is presumably why — but a *road
network* does, and if that is wanted it is new work rather than lost work.

- [ ] Decide whether glisteel wants junctions at all. A racing circuit is a
      closed loop; the answer may be no, and saying so is worth more than
      leaving the question open.

## 3. Traffic ends up in the ditch

Often enough to be among the first things a player notices. Unknown cause; the
candidates are the lateral controller losing the centreline on a curve, the
recovery from a nudge overshooting, and the road's own edge being somewhere the
traffic model does not think it is.

- [ ] Reproduce it in the gameplay harness
      ([GAMEPLAY-TEST-HARNESS.md](GAMEPLAY-TEST-HARNESS.md)) rather than by
      watching: drive a fixed seed and count how many traffic cars leave the
      carriageway per kilometre. That number is the whole of the problem
      statement and the whole of the acceptance test.
- [ ] Find which of the three it is before changing any of them.
- [ ] A budget in the harness, so it cannot come back quietly.

## 4. Traffic drives into collisions without trying to avoid them

A traffic car holds its line into an impact that a human would swerve away
from. The physics already knows how hard a pair met —
[2026-08-23-CRASH-ON-CONTACT.md](2026-08-23-CRASH-ON-CONTACT.md) added
`Contact.approach` and `PhysicsWorld.impact_on` — but nothing reads a *closing*
situation before it becomes a contact.

- [ ] A traffic driver that looks ahead along its own lane and to the side, and
      asks for the lane over when what is in front is closing too fast. The
      manoeuvre already exists: this is the `Lanes` lane switch under an AI
      rather than a player.
- [ ] Do not make it perfect. Traffic that never crashes is traffic that reads
      as scenery; what is wanted is traffic that *tries*.

## 5. The game is silent

Nothing in `glisteel/` references audio at all. The engine's side is ready and
unused: `OpenGLContext/audio/` is a spatial audio scene on the glTF
`KHR_audio_emitter` model, and `omi_audio` is a core dependency of OpenGLContext
rather than an extra, so the capability is already installed with the game.

What the drive should have:

| | |
|---|---|
| Tyres | slip-dependent, so a corner taken too fast is *heard* before it is felt |
| Motor | electric whine on load and speed — the car is a GLinting Steel EV |
| Wind | speed-dependent, which is most of what makes speed feel like speed |
| Impacts | the crash rule already measures how hard; it should be audible |
| Birdsong | placed in the forest, not on the camera — the world is a place |
| Water | at the causeways and the lake edge, which Tidewater is nearly all of |

### Where the sounds come from

Attribution is acceptable — the tree models are already CC-BY — so the licence
rule for audio is the same one the art follows: **CC0 or CC-BY yes, CC-BY-SA
never** (copyleft, [CLAUDE.md](../../CLAUDE.md)), CC-BY-NC never.

**Freesound is the source to build on.** Checked rather than assumed:

- Its `license` field is filterable and takes exactly three values —
  *Attribution*, *Attribution NonCommercial*, *Creative Commons 0*. **There is
  no ShareAlike on the platform**, so the one licence class that is forbidden
  here cannot arrive from it. `filter=license:("Creative Commons 0" OR
  "Attribution")` excludes only the NonCommercial third.
- Searching needs an API key; **downloading an original needs OAuth2**. The
  `previews` field gives `preview-hq-ogg`/`-mp3` URLs that need neither, which
  is enough for ambience and for a first pass at everything else.
- 60 requests a minute, 2000 a day — ample for assembling a pack once.

Ruled out, with the reason, so nobody re-treads it:

- **Pixabay** is *not* CC0 whatever the search results say. Its own licence
  forbids distributing content "on a Standalone basis … where no creative
  effort has been applied", which is exactly what a content pack does.
- **Kenney** is genuinely CC0 and redistributable, and has no engine, vehicle
  or nature audio — the packs are UI, impact, sci-fi and casino. Worth keeping
  in mind for menu sounds and nothing here.
- **OpenGameArt** has CC0 collections and mixed per-item licences, so every
  file has to be checked individually. A fallback, not a first stop.

### How it ships

As a **content pack**, not in the wheel: the same rule the art follows, and the
facility is already built. `copyright` on the pack carries the attributions,
which is what makes CC-BY workable — the engine requires that field of every
pack and generates the notices from it.

- [ ] The car's own sounds, driven by the physics that already computes slip,
      load and speed.
- [ ] The world's sounds as emitters in the scene, so they are positioned and
      the existing spatial mixer does the work.
- [ ] A `tools/` script that searches under the licence filter above, takes the
      previews, and writes the pack with each sound's own licence and author in
      the `copyright` — so a sound that cannot state its terms cannot get in.
- [ ] Silence stays a valid backend — `omi_audio` supports it, and a machine
      with no device must still play.

## 6. The simplified control scheme is built and unreachable

`schemes.Lanes` is exactly the model wanted: *"a press is the next lane to your
left, or right; the steering takes the car there and holds it, through the
bends, until it is asked for something else. The driver's job is the pedals and
the decision about when to pass."* `schemes.Chauffeur` drives until the player
touches anything. Five schemes exist — `Wheel`, `Loose`, `Line`, `Lanes`,
`Chauffeur`.

**And `DEFAULT = Wheel.name`, with `--control` as the only way to change it.**
`menu.py` offers no choice of scheme, so a player who starts the game the
ordinary way gets the wheel and can never reach the rest without knowing a
command-line flag exists. That is why the work reads as missing: it is.

- [x] A control chooser in the front end: **Menu → Driving**, offering each
      scheme with the summary it already carries, because a list of five names
      makes a player start five races to find out which is which. It changes
      the way of driving *under the car* rather than at the next race — a way of
      driving is something to feel, and telling somebody to restart to find out
      is telling them to judge it from memory.
- [ ] Decide the default on evidence. `CONTROL-SCHEMES.md` §8.1 has the first
      numbers off the feel harness; "on trial" has to end in a choice.
- [ ] Remember it between runs, beside the track library and the best times.
      Choosing a way of driving and finding the wheel back next time is worse
      than not offering the choice.

## 7. The editor has never been used in anger

`glisteel-editor` can draw a circuit and bake it, and no one has sat down with
the intention of building a *particular* track and found out whether it can be
built. Every other item here was found by playing; this one needs the same
treatment applied to the tool.

- [ ] Pick a real circuit to reproduce — a real-world one, or one drawn on
      paper first, so the target is not whatever the tool happens to make easy.
- [ ] Build it. Write down every point at which the tool refused, surprised, or
      needed a detour through a text editor or the command line.
- [ ] Bake it, drive it, and say whether it is the track that was drawn.
- [ ] The findings are the deliverable, in the shape of
      [2026-08-19-PLAY-REVIEW.md](2026-08-19-PLAY-REVIEW.md) — that review is
      what a play session is worth, and an editor session should be worth the
      same.
