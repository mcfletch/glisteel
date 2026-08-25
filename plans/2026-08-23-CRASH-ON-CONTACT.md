# A crash is contact, and the physics already knows how hard

*Landed 2026-08-23.*

## The complaint

Driving square into the back of a traffic car at speed pushed it along and
bounced the player backwards, and the run carried on. Clipping the same car off
centre ended it.

## What it was

`Session._watch_for_a_crash` decided a crash from geometry: the nearest traffic
car within `CONTACT_REACH` (6 m) and `CONTACT_WIDTH` (2 m), and the closing
speed worked out from the two cars' positions and velocities. It ran **once a
frame**, after the frame's physics substeps.

Three things follow from that, and together they are the bug:

- **The measurement is destroyed by the thing it is measuring.** Resolving a
  contact is precisely cancelling the velocity along it, so one step after the
  impact a square-on hit measures as nothing — the player is now travelling
  *away* — while a glancing one measures almost undiminished, because the
  impulse was sideways and the speed along the line between the two cars
  survived. Exactly the reported asymmetry.
- **The rule ran on the display's clock, not the physics clock**, alone among
  the rules the session steps. Every other one is inside the fixed step.
- **The window is shorter than a frame at racing speed.** Reach is measured
  centre to centre and a car is about 4.5 m long, so there was roughly 1.5 m in
  which to catch the approach. At 95 m/s a 30 Hz frame covers 3.2 m.

Measured before the change, on `scenarios.straight`, driving square into the
back of a car at 95 m/s: with nothing varying between runs but the distance the
other car started at — which moves where the frames land against the approach —
6 of 12 runs registered the crash at 30 fps and 8 of 12 at 70 m/s. Whether the
game noticed came down to phase.

A fourth thing, found on the way: traffic bodies are kinematic and were
teleported along the road with a bare write to `position`, carrying **no
velocity**. To the solver a car ahead was a wall, so the player bounced off one
doing 100 km/h exactly as off a parked one.

## What landed

**In `omi_physics`** — how hard two bodies met is a property of the moment they
met, and the engine is the only thing standing at that moment:

- `Contact.approach`: the closing speed along the contact normal, written by the
  solver *before* it resolves anything. Both solve paths already assemble what
  it needs, so it is folded into them rather than added as a pass — about
  0.23 ms at 1600 contacts, 0.65 % of that step. Restitution reads the same
  number instead of recomputing it.
- `PhysicsWorld.impact_on(i, above=, skip_static=, among=)`: the heaviest blow a
  body took in the step just run, as `(other body, closing speed)`. `above` is
  the floor below which a contact is not a blow — a body held against something
  re-acquires `g·dt` every step. `among` narrows it to a set of bodies, because
  only the heaviest is answered and a heavier irrelevant blow would otherwise
  hide the one the caller asked about.

**In `glisteel`**:

- `_watch_for_a_crash` moved inside the fixed step and now asks the physics what
  the car struck among the traffic bodies, and how hard. `CONTACT_REACH`,
  `CONTACT_WIDTH` and `race.closing_speed` go with the guesswork they served.
- `Traffic._follow` places bodies with `place_body` and gives each one its
  velocity, so a car ahead is a moving car: what the two do to each other on
  contact is right, and the impact speed is the one between the pair rather than
  the player's own.
- `Traffic.put_out`, `car_of` and `bodies`: a caller's own car put on the road
  the way a spawned one is, and the body index the physics answers with turned
  back into the car it belongs to.

After: 12 of 12 at every phase, speed and frame rate tried.

## What it changes for a player

A run ends when the two cars *touch* and were closing faster than `SURVIVABLE`
(9 m/s), and not otherwise. Two consequences worth knowing:

- Catching a car up and nudging it is a scrape, not a crash — the speed that
  counts is the difference between the two, so touching a car doing 100 km/h at
  105 is a five km/h impact.
- A car passed in its own lane on a two-way road cannot end a run at any speed,
  because the two never touch. Nothing has to decide how far apart is far
  enough any more.
