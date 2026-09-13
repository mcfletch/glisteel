# What the drive is missing, and one thing the bake gets wrong

**Status: Planned**

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

**The mountain over a tunnel is pushed down to road level**, so what should be
a hole through a hill is a cutting with a lid, and the skyline is wrong from
every viewpoint that is not on the road.

This is a **recorded decision, not a regression**.
[2026-08-19-PLAY-REVIEW.md §7](2026-08-19-PLAY-REVIEW.md) states the cost
plainly: `RoadPath.reshaped_segments` puts every segment inside a bore under the
earthwork, so the cutting runs the length of the tunnel; the batter is 0.6, so a
bore 30 m below the surface opens about 50 m either side. It was accepted
because *from the road* — the only place a player was — the tunnel reads as a
tunnel.

That is no longer the whole of where a player is, and the review already names
the right answer: **a hole in the ground mesh, with the bore's own outside
plugging it.** The field terrain is a height field and a splat map, so a hole in
it is a change to the terrain renderer — which puts this in **OpenGLContext**,
not here, per the workspace rule that a capability a game would want lives in
the engine.

Beacon is where it shows worst: 1774 m of its 3.02 km is inside the hill.

- [ ] Holes in `scenegraph/terrain` — the height field, the splat map, the
      collider and the LOD all have to agree about a cell that is not there.
- [ ] `_bore_corridor` stops flattening once the renderer can carry a hole.
- [ ] A capture from beside the circuit, not on it, as the check — the defect is
      invisible from the driving seat, which is how it survived.

## 2. Road diversity: half arrived, half never built

Two questions wearing one coat, and they have different answers.

**The lanes are there.** `CIRCUIT_PROFILE` is `lane_width=3.6, lanes=2`, with a
0.7 m shoulder and a 1.0 m verge, and `CLIMBING_LANE` adds a third 3.6 m lane on
any sustained climb — `CLIMBING_LANE_GRADE` 0.04 over `CLIMBING_LANE_RUN` 400 m.
Both reach the baked geometry of every track in the launch set. So the question
is not "was it built" but **"why can nobody see it"**, and that is a
measurement, not a redesign:

- [ ] How much of each shipped circuit actually earns a climbing lane? A world
      whose gradients never sustain 4% over 400 m has the feature and no
      occasion to use it, and the answer decides whether this is a rendering
      problem or a world-generation one.
- [ ] Are lane markings drawn at all? Two lanes with no line between them read
      as one wide road, which would explain the whole complaint on its own.
- [ ] A capture of a climbing lane, from the road and from above, so the next
      person can see what is there.

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

- [ ] The car's own sounds, driven by the physics that already computes slip,
      load and speed.
- [ ] The world's sounds as emitters in the scene, so they are positioned and
      the existing spatial mixer does the work.
- [ ] Licensing checked before anything is committed: BSD-compatible or CC0
      only, per [CLAUDE.md](../../CLAUDE.md), recorded where the tree art's
      attributions already are.
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

- [ ] A control chooser in the front end, offering each scheme with the summary
      it already carries.
- [ ] Decide the default on evidence. `CONTROL-SCHEMES.md` §8.1 has the first
      numbers off the feel harness; "on trial" has to end in a choice.
- [ ] Remember it, beside the track library and the best times.

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
