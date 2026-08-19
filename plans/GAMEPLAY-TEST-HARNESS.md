# A harness for testing the game as it is played

**Status:** agreed 2026-08-19. The loop comes out of the window into `Session`
(§2.0), and the map work goes into the engine's `MiniMap` (§4.6). Hoisting logic
out of window-bound classes is now the workspace's standing practice rather than
a decision taken here — see the root `CLAUDE.md`.

A session at the wheel turned up a list: the steering is jerky and does not
settle, the car drops out of the world in places, being *mired* stops the clock
but not the car, there is no countdown, the map is a line with a dot on it, and
an empty road is the default. Every one of those is a defect in something the
test suite already covers — and the suite is green, because it covers each piece
standing still.

This plan is for the layer that is missing: a way to put a car on a small piece
of road, hold a key down for four hundred milliseconds, and assert what the
whole game does about it over the next ten seconds.


## 1. What the suite tests now, and what it does not

The existing tests are thorough and cheap. `tests/test_driver.py` builds a
`Course` out of numpy, drops a real `Car` into a real `PhysicsWorld` and drives
a real lap; `tests/test_race.py` walks a position round a circuit and checks the
timing; `tests/test_traffic.py` fills a road and empties it again;
`tests/test_hud.py` lays out readouts against a viewport with no window at all.
Between them they cover most of what each module *is*.

Three things are outside all of it.

**The loop is not tested, because it is not reachable.**
`GlisteelContext.advance()` holds the game: the fixed-step accumulator, the
order of physics and camera and streaming, `_read_the_ground`,
`_recover_if_stuck`, `_watch_for_a_crash`, the run-ending checks. It lives on a
class whose `OnInit` opens a window, so every method in it carries
`# pragma: no cover - needs a window` and nothing exercises it. The reported
defects are, without exception, in there or in what it fails to do.

**Nothing drives from a player's inputs.** The one closed-loop driver under test
is `Autopilot`, which reads the road and produces a smooth continuous signal. A
player produces a square wave through `KeyboardWheel`, and the two controllers
fail in different ways. `tests/test_controls.py` samples `driver_input` on a
stub context with no car attached, which tests the *arithmetic* of the pedals
and stops there.

**Nothing measures how it feels.** "Jerky" is a real, numerical property — the
rate of change of what the eye and the hands see — and there is no test that
would notice it getting worse.


## 2. Shape of the harness

Four layers, each usable without the one above it.

```
  Layer 3   pictures        the real window, offscreen, HUD and map compared
  Layer 2   traces          metrics and budgets over a recorded run
  Layer 1   scripted input  a timeline of held keys, sampled in the loop
  Layer 0   Session         the game loop as a plain object, no GL
            scenarios       tiny worlds, synthetic or baked
```

### 2.0 `glisteel/session.py` — the loop, lifted out of the window

The enabling move, and a change worth making on its own account. A `Session`
holds what a run *is* — world, car, camera, timing, off-road watch, collisions,
traffic, reflections, run state — and advances it:

As built:

```python
class Session:
    def __init__(self, world: RaceWorld, spec: CarSpec | None = None,
                 view: str = 'cockpit', driver: Controller | None = None,
                 viewport: tuple[int, int] = (1280, 720)) -> None: ...
    driver: Controller | None                   # swap it to hand the car over
    def advance(self, elapsed: float) -> CameraPose: ...
    def readout(self) -> Readings: ...          # what the HUD is told
    def traffic_ahead(self) -> tuple[float, float] | None: ...
    def return_to_track(self) -> None: ...
```

The driver is held rather than passed each frame, because handing the car over
mid-run -- drive to the corner on the autopilot, then take it with these keys --
is one assignment that way.

`Controller` is a protocol with one method, `controls(session, dt) ->
(throttle, brake, steer)`. `Autopilot` satisfies it; so does a keyboard, so does
a script. `GlisteelContext` keeps the window, the event bindings, the view
platform, the streaming call and the HUD nodes, and becomes a thin shell around
a `Session` — which is what the workspace's own rule about demos being thin
wrappers asks for anyway.

No OpenGL is imported by `session.py`. The scenegraph nodes the car and the
traffic build are data until something draws them, so they cost nothing here.

### 2.1 `glisteel/scenarios.py` — tiny worlds, two grades

A `Scenario` is a named piece of road and the ground under it:

```python
@dataclass(frozen=True)
class Scenario:
    name: str
    plan: np.ndarray            # (N,2) XZ, what a designer drew
    closed: bool = False
    relief: Relief = FLAT       # a height function, or one of the named ones
    structures: bool = False    # build bridges and bores where the earthworks would be
    props: bool = False         # boulders on the verges
    signs: bool = False
    design_speed: float = 47.0
```

**Grade A — synthetic, no bake, milliseconds.** `scenario.world()` returns a
`RaceWorld` built through `RaceWorld.from_course` rather than off a tileset: the
same swept `RoadColliders` the game drives on, a `HeightField` for the ground
cut into chunks by the same `HeightFieldColliders`, the same `PropColliders`, and
the same `Traffic`. Only the tile tree is missing, and nothing a car touches
comes from it. That is what a flat box cannot do: the seam between the road's own
surface and the landscape is exactly where a car drops out of the world.
Everything in §4 that is not about pixels runs at this grade.

The road carries the shipped world's own cross-section rather than one inferred
from two widths, so the verge falls 35 cm to meet the ground instead of 1.2 m.

**Grade B — baked, tiny, real.** `ProceduralWorld` already takes `route`,
`closed`, `structures` and `relief` as arguments, so the same `Scenario` bakes
into a genuine streamable world through `bake_world`, and the game loads it
through `RaceWorld` with nothing stubbed: tile streaming, the height-field
colliders and their bore openings, props out of `extras`, signs, the gantry, and
the road's cross-section round-tripped through the tileset.

Measured in this container: a 512 m world at depth 1 with no trees bakes in
**9 seconds** and drives offscreen at 640×360 at **214 fps**. A bake goes into a
cache directory keyed by the hash of its `Scenario`, so it happens once and
every later run loads it.

**The catalogue.** Each is a few hundred metres and answers one question.

| Scenario | Road | What it is for |
|---|---|---|
| `straight` | 400 m, flat | steering feel, centring, top speed, drag |
| `sweeper` | 120 m radius | steady-state cornering, the line, lateral jerk |
| `chicane` | left-right at 60 m | transient response, steering rate, catch-and-recover |
| `hairpin` | 300 m into 25 m radius | braking distance, entry stability |
| `crest` | vertical curve at the design limit | wheels down over the top, camera pitch |
| `dip` | the same inverted | compression, bottoming |
| `bore` | 200 m tunnel with its ground opening | dropping through the hole cut for it |
| `viaduct` | 150 m deck over a valley | leaving the deck sideways, the fall |
| `verge` | flat, boulders either side | surfaces, mired, hitting something |
| `circuit` | 800 m closed, all of the above | laps, sectors, start/finish, the map, traffic |

### 2.2 Scripted input

A script is a list of holds, sampled inside the fixed step and fed through the
same `KeyboardWheel` and held-key set the window fills:

```python
script = Script([
    Hold('w', 0.0, 12.0),
    Hold('a', 3.0, 3.4),        # a tap at speed
    Hold('a', 6.0, 8.0),        # and a hold
])
```

A `MouseScript` gives pointer positions across the window for `--mouse`, and an
`Autopilot` is a controller like any other, so a script can hand over: *drive to
the corner on the autopilot, then take it with these keys*, which is how a test
reaches a specific state without hand-placing the car there.

### 2.3 Traces and budgets

A run returns a `Trace`: one row per physics step, as numpy columns.

```
t, position, velocity, speed, yaw, yaw_rate, lateral_g,
throttle, brake, steer_input, wheel_angle, front_steer_angle,
surface, off_line, on_road, camera_position, camera_heading, camera_pitch,
run_state, lap, sector, ended
```

Assertions read the trace. So do the *measures*, which are numbers with budgets
rather than pass/fail — the way the frame rates in the README are numbers:

| Measure | Read from | Why it is watched |
|---|---|---|
| steering rate | `d(wheel_angle)/dt`, 95th percentile | a wheel that snaps is a car that spins |
| **camera yaw jerk** | `d²(camera_heading)/dt²` | what the eye actually sees |
| lateral jerk | `d(lateral_g)/dt` | what the hands feel |
| time to centre | `t` from key release to \|steer\| < 0.02 | the reported symptom, as a number |
| yaw overshoot | peak/steady `yaw_rate` through `chicane` | twitchiness at the limit |
| catch rate | scripted recoveries that end on the road | whether a slide is drivable |
| worst drop | lowest `position.y` under the road surface | dropping out of the world |

Budgets live in one table in the harness, printed on failure with the measured
value, so a regression says *what* got worse and by how much.

### 2.4 Pictures

For the HUD and the map only. Two grades again:

- **No window.** `MiniMap.at()`, `.strokes()` and `.marked()` are arithmetic over
  a viewport, and `tests/test_hud.py` already asserts layout that way. A start
  line at the right place on the map, a heading arrow pointing the right way, a
  car mark inside the box: all of it is testable with no GL at all, and that is
  where most map tests belong.
- **The real window, offscreen.** `OPENGLCONTEXT_HIDDEN=1` with `--capture`
  renders the game and exits, which works today. The engine's
  `OpenGLContext.testing.event_injector` already delivers scripted keyboard and
  mouse events into a running context over a socket, and
  `framebuffer_comparison` already compares frames to references. A handful of
  cases — the countdown, the map with a car on it, the mired banner — get a
  reference image and nothing more. Marked `@pytest.mark.picture` and off by
  default, because they want a GPU.


## 3. Iterating, not only asserting

The same harness runs from a command line, so a human can watch the exact run a
test asserts on:

```bash
glisteel-scenario chicane --script "w 0..12; a 3..3.4; d 4..4.6" --plot trace.png
glisteel-scenario chicane --script "..." --record chicane.mp4     # watch it
glisteel-scenario chicane --script "..." --measure                # the table
```

`--plot` writes the trace as graphs; `--record` uses the recorder the game
already has, whose frame-stepped clock makes the video exactly the run that was
measured. Tuning `WIND_ON`, `CENTRE`, `steer_falloff_speed` or a camera damping
constant becomes: change the number, run one command, look at the measures and
at twelve seconds of video.


## 4. The defects this is being built to catch

Each with the test that would have caught it, and where the fix belongs.
Findings marked **found by reading** were located while writing this plan and
are not yet confirmed by a run.

### 4.1 Held keys survive losing focus — *engine* — **fixed**

`EventHandlerMixin.clearHeldKeys` (`OpenGLContext/events/glfwevents.py`) drops
its own held-key map when the window loses focus, and emits nothing. Anything
downstream that tracks held keys — `GlisteelContext.held`, and the engine's own
movement modes — never sees the release, so the key stays down for ever. Alt-tab
away mid-corner and the wheel is wound to full lock when you come back.

`EventHandlerMixin.clearHeldKeys` now sends a `state=0` event for each key it was
holding as focus goes away, so an application's own held-key set empties the way
an ordinary release empties it. The cases are in
`openglcontext/tests/unit/test_glfw_key_repeat.py`, and the guarantee is written
down in the engine's `docs/eventmodel.html`.

### 4.2 The cockpit is bolted rigidly to the chassis — *glisteel* — found by reading

`ChaseCamera.update` sets `_position = wanted` outright whenever `onboard` is
true, which is both the cockpit and the bonnet, and aims along the car's
*instantaneous* forward vector. Every yaw wobble, kerb strike and suspension
event is therefore a whole-frame swing, at the physics rate, with no damping
anywhere between the chassis and the eye — and the cockpit is the default view.

Fix: damp the head's yaw and pitch against the chassis, with a bias that lets it
lead into a corner. Test: camera yaw jerk on `straight` and `chicane`, budgeted.

### 4.3 Steering that does not settle — *measured; see §4.10*

The wheel itself is not the problem. `WIND_ON` is 2.2 and `CENTRE` 4.5, so full
lock winds on in 450 ms and comes off in 220 ms, and the harness confirms the
wheel is back to centre within half a second of the key coming up every time.
What does not come back is the *car*: §4.10 has the numbers and the decision
they ask for.

### 4.4 A run that has ended does not end — *glisteel* — **fixed**

`glisteel/run.py`. `Run` owns which part of the race is happening and what it
lets through: once a run is `ended` the controls are replaced by the brake, the
lap clock stops, and the stuck-recovery no longer picks the car up and puts it
back into a race that is over. `r` is how a player chooses to carry on and `n`
starts a fresh race.

The strict xfail is gone. What replaced it says what actually happens: a mired
car brakes to a stop, its speed never rises again on the way there, and it takes
between three and twelve seconds about it — it is on rough ground, and grip is
what it has left. See [FRONT-END-AND-WORLD.md](FRONT-END-AND-WORLD.md) §1.

### 4.5 No start sequence — *glisteel* — **fixed**

Five lamps a second apart, holding 1.4 s, then out: 6.4 s from the grid to the
green, on the physics clock so it counts the same on any machine. The car is
held on the brake and the lap clock does not start until the lamps go out.
The rig is `OpenGLContext.ui.hudwidgets.LampRow`, which is engine furniture:
lamps rather than a numeral, because a driver reads a start rig with their eyes
on the road. See [FRONT-END-AND-WORLD.md](FRONT-END-AND-WORLD.md) §2.

**Still open:** a jump start — throttle before the last lamp goes out — is a
question `Run` is the right place to answer and does not answer yet.

### 4.6 The map is a line and a dot — *engine and glisteel*

`MiniMap` draws a route and coloured discs, which is all it is asked for. What a
driver needs from it: where the start/finish line is, which way the car is
pointing, how far round the lap it is, and enough of the world's shape —
structures, sectors, the corner ahead — to read what is coming.

Fix in the engine, since `MiniMap` is engine furniture that a rally stage or a
delivery round would want the same way: mark kinds beyond a disc (a heading
arrow, a gate), a second polyline for structures, and an optional course-up
orientation. glisteel supplies the data. Test: geometry assertions with no
window, plus one reference picture.

### 4.7 An empty road by default — *glisteel*

`--traffic` defaults to 0. Whether the default changes is a design decision, not
a defect; that the traffic is untested *in the loop* is the defect — nothing
asserts that with traffic on, cars appear ahead, are overtaken, and are hit at
closing speed. Test: `circuit` with traffic, scripted overtakes.

### 4.8 Dropping out of the world — *wherever it turns out to be*

`bore`, `viaduct` and `crest` at grade B, with the trace asserting that the car
never passes below the road's own surface, that `return_to_track` is never
called, and that `_recover_if_stuck` never fires on a clean lap. The seam
between the road's swept collider and the landscape's chunks is the first place
to look; the hole cut for a bore (`BORE_MARGIN`, `BORE_APPROACH`) is the second.


### 4.9 Found while building the harness

Two defects the first scenario turned up, both fixed as part of step 2:

- **A car was put on the last metre of an open road.** `Session` placed it at
  centreline point 0, which on a circuit is the start line and on an open road is
  the very end of it -- the back wheels hang over nothing, the car pitches onto
  its tail and slides off. `Course.start_index` now sets the grid back far enough
  along an open road for all four wheels to be on it.
- **The grid always reported that its ground had not arrived.** A car is dropped
  onto the grid from six metres, and `RaceWorld.settled` asks whether there is
  ground within four; the answer was always no, and the game logged a warning
  about the world not having loaded on every start. The question is now asked
  about the road's own surface, which is where the car is going to land.

Neither is a scenario's problem: both are what the game does with any world.


### 4.10 What "too jerky" actually measures — **decided: less lock at speed**

The harness answers it, and the answer is not what §4.3 assumed. A tenth of a
second on a steering key, at 31 m/s (113 km/h), on level straight road:

| | |
|---|---|
| wheel reached | 0.33 of lock |
| front wheels reached | 4.5° |
| peak yaw rate | 0.9 rad/s |
| peak lateral acceleration | 2.9 g |
| direction changed by | 6.3° |
| off the carriageway | 0.3 s later |
| run over | at 8 s, "mired off the road" |

Two things make that so, and neither is a fault in the code:

**The car has 2.9 g at that speed, and it is meant to.** The tyres' own grip is
1.9 g and `downforce=6.0` presses on the rest; `omi_physics` shares one friction
budget between driving and cornering and the corner is inside it. The response is
also exactly kinematic — the radius comes out as wheelbase over steer angle to
three figures — so nothing is slipping and nothing is spiking. It is a car with
more grip than a road car, doing what it was told.

**Nothing brings the heading back, and nothing should.** The wheel centres by
itself; the *car* keeps whichever way the input left it pointing, which is what
a real one does. What a real driver does next is counter-steer by the right
amount, and a keyboard cannot meter that: the only inputs are none and all, over
a wheel that winds at a fixed rate.

So 4.5° of front wheel at speed buys 6° of heading, and 6° crosses a
seven-metre road in about thirty metres. The car is not badly behaved; it is
**over-geared for the input device**. The choices, in the order I would try them:

1. **Less lock at speed.** `steer_falloff_speed` is 26 m/s and already takes the
   lock from 0.52 to 0.24 rad at 31 m/s. Taking it further is one number and
   costs nothing anywhere else.
2. **Less downforce.** `downforce=6.0` is what puts the cornering at 2.9 g; a
   road car's figure would put a tap back inside the road on its own.
3. **A stability assist**: a small yaw damping while no steering key is held, so
   letting go straightens the car rather than only the wheel. This is what an
   arcade racer does and what a keyboard really wants, and it is the one that
   changes what the car *is* rather than how much of it the player gets.

**Decided: the first lever, taken properly.** The lock now falls with the
*square* of the speed rather than in step with it — cornering is `v**2 / radius`,
so a radius that only widens as fast as the speed rises is a demand on the tyres
that still doubles with it. Against `steer_falloff_speed` squared, what full lock
asks for settles at a corner the car can hold. `steer_falloff_speed` is 10 m/s
here, chosen so that full lock at the top end asks for about two g against the
2.9 g the tyres and the wings have.

The turning circle full lock will give: **5 m** standing, 10 m at 10 m/s, 25 m at
20, 49 m at 30, 87 m at 41. A tap at speed is now a lane change:

| 0.15 s on a steering key at speed | before | after |
|---|---|---|
| direction changed by | 4.5° | **1.2°** |
| the run ended | mired off the road | **it did not** |
| autopilot lap, 420×300 m circuit at 47 m/s | 57.7 s, 0.40 m off the line | 57.9 s, **1.89 m** |

Two of the three tests it was written against now pass and their markers are off.
The third stands: a driver who *never* corrects still runs out of road, six
seconds later rather than one, because the wheel centres and the car keeps the
direction the tap left it pointing — which is what a real one does.
`test_a_tap_and_a_counter_tap_bring_it_back` is the other half of that, and it
passes: the same touch of the other key puts the car back on the line. Whether
the game should straighten the car for a player who cannot meter a counter-tap —
the third lever — is still open, and is now a smaller question than it was.

Two smaller findings from the same runs:

- **The camera from the driver's seat passes on 5.5× the vertical acceleration
  the chase view does** — 88 m/s² against 16 through a chicane, 2.7 against 1.4
  over a crest — and about 1.4× the yaw jerk. That is §4.2, now with numbers.
- **A car given no steering at all drifts six metres off the crown in twelve
  seconds**, down the road's 2% camber, which takes it off a 7.2 m carriageway.
  Physically right, and worth knowing before the camber is blamed on something
  else.


### 4.11 Three defects under the car — *omi_physics* — **fixed**

Chasing "the car will not hold a line" with the harness found that most of it was
not steering at all. All three are in `omi_physics`' `RaycastVehicle`, which is
where they belong: any game on it had them.

**Each wheel was worked out against a body the wheel before it had moved.** Four
wheels push on one chassis in one step, and each one's impulse was applied as it
was calculated, so the second wheel answered about a body the first had already
shifted. The four stopped being symmetric and the car wandered to whichever side
was worked out first — **five metres in eight seconds** of straight-line
acceleration, and to the *other* side if the wheels were listed in reverse. A
step now reads one stance of the body, asks every wheel about that, and applies
what they all asked for together.

**The air was carried in equal quarters.** Drag is a body force handed to the
contacts so that a tyre with nothing to push against cannot hold the car back
with it — but split four ways, the wheel the weight has come off under
acceleration was asked for a quarter of it with almost no friction to spend, and
what it gave up to find that was the *sideways* hold, since driving and gripping
share one budget. It is now shared by what each wheel is carrying.

**Four wheels each took the whole car's speed off.** The clamp that keeps a brake
from driving the car backwards through a stop was written for the whole car and
applied per wheel, so four braked wheels removed four times the speed there was
and threw the car the other way — a little harder every step, which is a
divergence rather than a wobble. It is now divided among the wheels doing the
stopping.

Together, on a flat floor at full throttle for twelve seconds:

| | before | after |
|---|---|---|
| wandered sideways | 6.9 m | **0.000 m** |
| heading bought by a 0.15 s key tap at 113 km/h | 6.3° | **1.8°** |

**And the tyres were infinitely stiff.** With the three above fixed, the four
wheels all corrected the same body at the same instant against sideways scrub —
each taking all of what it could see, which together is more yaw and more roll
than the car had. The car put some back the other way and shook its head at the
rate of the physics loop, worst on a crowned road, which is every road. A tyre
does not build its side force instantly either: the tread has to be laid down
and deflected over about a third of a metre. `SCRUB_RELAXATION` is both facts at
once, and with it a car driven straight down a crowned road holds the line
exactly:

| straight road, throttle only, twelve seconds | before | after |
|---|---|---|
| off the centreline | 6.9 m | **0.000 m** |
| heading changed by | 1.26° | **0.000°** |
| the view's yaw rate | 0.19 rad/s | **0.000 rad/s** |
| top speed reached | 19 m/s (it had left the road) | **41 m/s** |

The same drive over a `crest` and through a `chicane` now ends 0.00 m and 0.09 m
off the line. `tests/test_feel.py::TestACarDrivenStraight` is the guard.

### 4.12 A car left alone rolled away — *omi_physics and glisteel* — **fixed**

Parked on the crest scenario with nothing held, the car rolled **32 metres in
twelve seconds** and was still gathering speed. A car left alone is in gear or on
its handbrake; one that coasts off makes stopping anywhere but the flat a
mistake, and turns every gentle grade into something to hold a key against.

`VehicleTuning.holding` is what a car with nothing asked of it holds its place
with, in newtons — divided by the car's weight, the steepest grade it holds on.
Zero is a vehicle out of gear. And `Session` now settles the car onto the grid
*on the brake*, because a car dropped onto a slope with the brake off is already
rolling by the time the player sees it.

| left alone for twelve seconds | before | after |
|---|---|---|
| on the `crest` | 32.2 m | **0.115 m** |
| on the `dip` | 20.5 m | **0.129 m** |

### 4.13 What is left of the drift

With those fixed, a straight, full-throttle drive still ends **6.9 m** off the
centreline over twelve seconds. It is two things, in two places:

- **4.2 m of it is the road's own 2% crown**, and the car starts balanced on the
  ridge of it. Physically that is what a cambered road does to a car nobody is
  steering; a driver holds a hair of lock against it without noticing, and a
  keyboard cannot give a hair of anything. This is §4.10's decision.
- **2.7 m of it is a launch transient on the road mesh.** Pulling away hard, the
  car acquires 0.59° of heading on the swept carriageway collider and none at
  all on a plain box floor, then holds that heading exactly for the rest of the
  drive. It is the same figure wherever along the road it starts, so it is
  systematic rather than noise. Not yet run down; the mesh's own triangulation is
  the first place to look.


## 5. Cost

| | Cost | When it runs |
|---|---|---|
| Grade A scenario, 20 s of driving | 0.1–0.4 s | every `pytest` |
| the whole grade-A catalogue | a few seconds | every `pytest` |
| Grade B bake, first time | ~9 s each, cached | on a cache miss |
| Grade B drive, offscreen | seconds | `-m world` |
| Reference pictures | seconds each | `-m picture`, needs a GPU |

The default `pytest` run stays as quick as it is now.


## 6. Order of work

1. **Done.** `glisteel/session.py` holds the run; `game.py` is the window around
   it. Whoever is driving is a `Controller`, which the autopilot, the new
   `KeyboardDriver` and anything a test scripts all satisfy.
2. **Done.** `glisteel/scenarios.py`, grade A: eight pieces of road built on
   `RaceWorld.from_course`, with the engine's own swept carriageway and a height
   field for the ground. The whole catalogue builds and drives in about a second.
3. **Done.** `glisteel/scripted.py` writes a drive down as held controls and
   replays it through the same `KeyboardDriver` a window fills;
   `glisteel/trace.py` records one row a physics step and measures it.
   `tests/test_feel.py` is the reported symptoms as runs, four of them
   `xfail(strict=True)` against the defects still open.
4. 4.1 is **fixed** in the engine. 4.2 and §4.10 are what to do next, and
   §4.10 wants a decision before any code.
5. Run state and countdown (4.4, 4.5), with tests.
6. Grade B and the cache; `bore`, `viaduct`, `crest`, `circuit`; the
   dropping-out assertions (4.8).
7. The map (4.6), engine side first.
8. `glisteel-scenario` and the picture tests.

Steps 1–4 are the ones worth doing before anything else: they turn "it feels
wrong" into numbers, and every later change is measured against them.


## 7. Documentation this owes

- `README.md` — the harness under *Developing*, and the scenario command.
- A `docs/` page, or a section of the README, for the scenario catalogue and the
  measures with their budgets: someone tuning the car needs to know what is
  being watched and what the numbers mean.
- `openglcontext/docs/` — anything added to `MiniMap` or to the GLFW event
  handling is engine documentation, and the engine's own conventions apply.
- This file records what was decided; the behaviour goes in the docs above.
