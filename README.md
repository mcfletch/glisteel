# GLinting Steel

A racing game on [OpenGLContext](https://github.com/mcfletch/openglcontext): a
car, a forest road, and a world too big to load. The world streams in around the
player as they drive it.

```bash
pip install glisteel OpenGLContext-editor
oglc-bake --output /tmp/world
glisteel /tmp/world/tileset.json
```

The first command bakes a world: hill country under half a million trees, and an
eight-kilometre circuit routed through it — on the ground where the ground
allows, on a walled causeway over the low ground, on a viaduct over the valleys
and through a bore where it does not. The second drives it.

## Driving

| | |
|---|---|
| `up` / `w` | throttle |
| `down` / `s` | brake, and reverse once stopped |
| `left` `right` / `a` `d` | steer |
| `space` | handbrake |
| mouse | steer, with `--mouse` |
| `c` | cockpit / chase / bonnet camera |
| `r` | put the car back on the track |
| `n` | a fresh race, from the grid |
| `escape` | the menu |
| `F2` | screenshot |

`glisteel --autopilot` drives itself, which is the quickest way to see a lap and
the same code an opponent car would use; `--view chase` starts in a view other
than the driver's seat.

### Recording a drive

```bash
glisteel /tmp/world/tileset.json --autopilot --record lap.mp4 \
    --record-seconds 20 --record-fps 60 --size 1280x720
```

writes an H.264 video of the drive and exits when it is done. The frame goes
from the framebuffer into a texture the GPU's video encoder reads in place, so
recording costs a blit rather than a read back through host memory.

**The recording drives the clock.** The world is advanced by exactly one frame
of time for every frame written, so the video is smooth whatever the frame rate
was and the same drive records the same way twice. That means a recorded run is
not real time — a heavy frame takes as long as it takes — which is why it is a
mode rather than something the game does while someone is playing it.
`--record-delay` (six seconds by default) lets the world stream in before the
recording starts, so the video is of a world that has arrived; `--record-bitrate`
overrides what the encoder picks from the frame size and rate.

Recording needs the engine's video extra, `pip install OpenGLContext[video]`, and
an encoder it can reach — today an NVIDIA card on Linux.

**The default view is the driver's seat.** A route is a thing you drive
*through*, and a forest read from seven metres up and behind reads as scenery
rather than as trees you are passing between. `c` cycles cockpit, chase and
bonnet; the chase view is what a player catching a slide wants. For the cockpit
view the player's own bodywork is left out of the frame — the eye is inside it —
and the interior and the canopy stay, because they are what that view is *of*: a
dashboard, a wheel that turns as you steer, and the road seen through glass the
light bends going through.

## What is where

The game is deliberately thin. Streaming, rendering, roads and physics belong to
the engine underneath — `OpenGLContext` and `omi_physics` — and what is here is
what makes it a *game*.

| Module | Holds |
|---|---|
| `world.py` | a baked world: its tiles, its physics, and the roads it carries |
| `car.py` | the car — its body, its wheels, and how it is drawn |
| `models.py` | which model is which, and the names the game drives one by |
| `reflections.py` | what the car reflects, and how that follows the road |
| `camera.py` | where the player watches from |
| `driver.py` | the autopilot: pure pursuit, and a speed the corner allows |
| `race.py` | lap timing that a shortcut does not fool, and leaving the road |
| `run.py` | which part of the race this is, and what it lets through to the car |
| `assist.py` | the steering the game puts in while the player is not steering |
| `lighting.py` | what lights a bore, and what the car carries into one |
| `tracks.py` | the worlds a player can choose between, and where their files live |
| `records.py` | the best times driven on each track |
| `menu.py` | the screens around the outside of the race |
| `hud.py` | what the driver is told, and where on the screen it goes |
| `session.py` | the run: the loop, the clock, and the rules about both |
| `scenarios.py` | small pieces of road to drive, for testing and for tuning |
| `scripted.py` | a drive written down: which controls are held, and when |
| `trace.py` | what a drive did, as numbers, and the measures over them |
| `game.py` | the window, the keys, and what is drawn |

**The car is a model, and so is everything else on the road.** The vehicles in
`glisteel/assets/cars/` are ours, built by `tools/cars.py` — a Blender script
that writes `models/cars.blend` for editing and the `.glb` files the game
loads. Each carries its bodywork, its interior and its glass as three named
subtrees, and the player's car carries the travel of its steering wheel as an
animation clip the game poses at whatever fraction of lock the front wheels are
actually turned to. The canopy is refractive glass
(`KHR_materials_transmission`, with a thickness to bend the light through), so
the cabin you see through it is the cabin that is there. A model that will not
load leaves the car drawn from primitives and the game running: art is not
rules. To rebuild them:

```bash
/workspaces/OpenGL-dev/.venv-bpy/bin/python tools/cars.py   # any bpy-capable interpreter
```

**A car reflects where it is.** Painted metal is almost entirely its
surroundings, so a car lit by a bare sky gradient reads as a toy however
carefully it is modelled. The road already knows what it is running through —
its structures say where the bores and the bridges are, and everywhere else is
forest — so `reflections.py` hands the renderer a small panorama of that place:
a canopy overhead with sky broken through it, a bore with a lit portal fore and
aft, open sky over a treeline on a viaduct. The engine's IBL probe notices the
environment changed and rebuilds, which happens at a portal rather than at a
frame.

**The road comes with the world.** A pile of triangles does not say where a
track goes, so the baker writes the centreline, the cross-section and the
structures into the tileset's `extras` and the game reads them back. That is what
puts the car on the grid, points it the right way, times the lap, steers the
autopilot, and — because it is a road and not a pile of triangles — decides what
is under the wheels.

**What the car drives on is built here, not read off the tiles.** Tile geometry
is level-of-detail geometry: two resolutions of one curve are the better part of
a metre apart, and a surface that steps under the wheels at a hundred and thirty
is a wall in the middle of an open road. So the carriageway is swept from the
centreline and the ground is cut from the landscape's own height field, each in
chunks held near the car. Nothing streams underneath it.

**The road warns you.** A generated road knows its own curvature, its own grade
and where its tunnels are, so the signs beside it are worked out from the
alignment rather than placed by hand: a bend tighter than the design speed
allows, a dip, a crest, a bore ahead. Each stands a stopping distance before
what it is about.

**And there are things to hit.** Boulders lie on the verges and in the trees
either side, close enough that a car leaving the road meets one. They come out
of the tileset rather than out of the tiles, so a rock is solid whether or not
the tile it is drawn in happens to be loaded.

**Leaving the road ends the run.** A forest road is as wide as it is and the
forest starts at the verge. A wheel on the grass loses most of its grip and picks
up drag; a car that stays off for a couple of seconds is mired, and one that goes
a long way off is gone. `r` puts it back on the grid.

**The lap has a line.** A chequered banner on a beam spans the road where the
lap begins and ends, with a chequered line painted across the tarmac under it,
so the timer turning over is something a driver saw coming. Its two legs are
solid: clip one and the run ends the way hitting anything else does.

**There is a map.** The whole circuit, bottom left, with the car on it and the
traffic marked, so a driver knows what is round the next bend and how much of
the lap is left.

**`--traffic 8` puts other people on the road.** They drive at the limit in
both directions, keep their own side, and decide for themselves: a car brakes
for something its driver can see and you cannot, or pulls off the road
altogether. None of them will drive through the car in front, and that includes
yours -- a car on the grid is a car in the road. They are placed and driven by
distance along the course rather than simulated as vehicles, which is why there
can be eight of them for nothing measurable.

**The steering keys wind a wheel on and off.** Left and right are a key each, so
the raw input is full lock or none; held straight to the car that is a spin at
speed. The keys drive a wheel that eases toward the held lock and back to centre
instead, so a tap is a nudge and a hold builds to lock.

**And the lock the front wheels reach falls with the square of the speed.** Full
lock is a car park — five metres of turning circle — and the same input at a
hundred and fifty is a request for a corner no tyre will hold. Falling this way
(`steer_falloff_speed`, in the engine's `VehicleTuning`), what full lock asks for
settles at about two g rather than growing with the speedometer: the turning
circle is 5 m standing, 10 m at thirty-six km/h, 49 m at a hundred and ten, and
87 m flat out. A touch of a key at speed is a lane change, and the same touch of
the other key puts the car back.

`--mouse` steers with the pointer:
where it is across the window is where the wheel is, the way mouse-look turns a
head, and it gives a position rather than a rate. The keys override the pointer
while one is down.

**The drivetrain is electric.** All of the force from a standstill and constant
*power* from fifteen metres a second on, so the pull falls away as the speed
rises rather than shoving as hard at a hundred and sixty as at thirty. What
decides the top speed is the air: about a hundred and ninety.

**The car is a rigid body on four spring-loaded rays** — `omi_physics`'
`RaycastVehicle`. There are no wheels in the simulation: each is a ray cast
down, a spring pushing the body up off what it finds, and a patch of friction
driving and steering at the contact. Everything about how *this* car feels is
in `CarSpec`.

**Physics runs at a fixed 120 Hz** and the controls are sampled inside that
loop, not once a frame. A steering loop that only runs when a frame is drawn is
a controller at the frame rate, and on a slow frame it holds full lock for a
quarter of a second and puts the car on its roof.

## How fast it runs

Measured in this container on an RTX-class GPU, driving the autopilot, twenty
seconds each:

| World | Instances per tile | 1000×560 | 1920×1080 |
|---|---|---|---|
| 2048 m, depth 3, no trees | 0 | 147 fps | |
| 2048 m, depth 3 | 40 | 111 fps | |
| 2048 m, depth 4 | 24 | 74 fps | 57 fps |
| 2048 m, depth 4 | 240 | 61 fps | |

The shipped 4096 m world — 575k trees, ground cover, and a shaded canopy —
drives at 62–80 fps at 1080p on the same machine, an autopilot lap of 3:32 over
8.3 km.

The vehicles are a few thousand triangles against half a million trees, and
where the world sets the frame rate they do not show up in it at all. Where it
does not — the driver's own view, which pulls in far less of the world than a
camera seven metres up — ten traffic vehicles cost a few milliseconds a frame,
because each is its own copy of a model so that each can be painted its own
colour.

The frame rate is set by how much of the world is on screen and how finely it is
drawn. `--sse` trades sharpness for speed (higher is coarser); a shallower world
(`oglc-bake --depth 3`) draws fewer tiles.

At 1080p a frame is about 10 ms of drawing, 5 ms of physics and 3 ms of
everything else. Getting there took four things, each in the engine underneath
rather than here: a glTF instancing node became *one* scenegraph node holding
every placement instead of one per tree; the same image loaded by a hundred
tiles became one texture, so the hundred draws it forced became one; a car's
four wheels are cast into the world together rather than one at a time; and a
landscape's bodies are no longer asked every step whether they have moved. The
rest of the way to 60 fps at 1080p is §I of
[GLISTEEL-WORLD-AUTHORING.md](https://github.com/mcfletch/openglcontext/blob/main/plans/GLISTEEL-WORLD-AUTHORING.md).

## Developing

```bash
pip install -e ".[dev]"
pytest
```

The suite runs headless and without a window: a car is numbers, a lap is
numbers, and a camera is numbers. `tests/test_driver.py` puts a real car on a
real circuit and asserts that the autopilot gets round it.

**The run is separate from the window.** `Session` holds the game -- fixed-step
physics with the controls sampled inside it, the camera, the lap timing, and the
rules about leaving the road and getting stuck -- and imports no OpenGL. Build
one, advance it a frame at a time, and read it back:

```python
from glisteel import scenarios
from glisteel.session import Session

session = Session(scenarios.chicane().world())
for _ in range(600):
    session.advance(1.0 / 60.0)
print(session.readout().speed_kph, session.timing.current)
```

`game.py` is the window around that: it builds a session, hands it the keyboard,
points the view where the session says and draws the result.

### The race has parts

A race is not one long moment of driving, and `Run` is which part of it is
happening. Each part decides two things -- what reaches the car, and whether the
lap clock runs:

| | the car | the clock |
|---|---|---|
| `countdown` | held on the grid, brake down | stopped |
| `racing` | everything the driver asks for | running |
| `finished` | brought to a stop | stopped |
| `ended` | brought to a stop | stopped |

The start rig is five lamps a second apart, holding for 1.4 s with all five lit
and then going out -- 6.4 s from the grid to the green. `--laps` is how many
laps the race is, one by default, which is what a timed lap is; `--laps 0`
drives on with no finish. A run that is over stays over: the car is not picked
up and put back on the road, because a race that has ended and a car still being
driven round the circuit are not both true. `r` puts the car back and carries
on, `n` starts a fresh race from the grid.

```python
from glisteel.run import Run

run = Run(laps=3)
run.update(1.0 / 120.0, laps=len(session.timing.laps), ended=session.ended)
throttle, brake, steer = run.allow(*whatever_the_driver_asked_for)
```

A scripted drive (`glisteel.trace.drive`) begins at the green light: what it
measures is the car, and a start sequence in front of it would put every hold in
the script six seconds later than it reads.

### Steering, and what the game does about it

A keyboard says a key is down or it is not, and a real driver's hands say a
great deal more than that. Two things bridge the gap:

**The wheel winds.** A key does not put the car on full lock; it moves the wheel
toward that lock at `WIND_ON` (0.9) of its travel a second, so a tap is a nudge
and a hold builds. The rate is deliberately slower than the shortest input a
player can give, which is one frame — at ten frames a second that is a tenth of
the wheel.

**The game straightens what the player is not steering.** Between the deliberate
inputs, a real driver puts in a continuous small correction holding the car on
the line, and a keyboard cannot express it. Without that, every tap is a
*permanent* change of direction: the wheel centres, the car keeps the heading,
and it crosses the road until the road runs out. So with nothing held, the wheel
is put where it needs to be to bring the car back to the way the road goes
(`glisteel.assist`).

`--assist` is how much of that correction is used, and it is the steering
difficulty dial: **0 hands the car back entirely** and is the car as the physics
has it; 1 holds the line for you. What a 0.3 s tap — about the shortest input at
the frame rates a full world runs at — does to the car:

| speed | `--assist 0` | `--assist 0.55` |
|---|---|---|
| 32 km/h | 5.4 m off the line | **0.3 m** |
| 86 km/h | 7.6 m off the line | **0.4 m** |
| 86 km/h, 0.6 s hold | 19.6 m | **1.7 m** |

The carriageway is 7.2 m wide.

### Lights, and the eight of them there are

A renderer binds eight lights in a frame and a tunnel has one every
twenty-five metres, so a bore is lit **twice**:

- **The lining lights itself.** The pool each luminaire throws is baked onto its
  vertices when the world is built, so the whole length of a bore is lit at any
  distance and costs nothing to draw.
- **The few fittings the car is among become real lights.** That is what the
  lamp positions in the tileset's `extras` are for: a car under a lamp has no
  idea it is under one, and a baked pool cannot tell it.

The budget divides two for the sun and its sky fill, four for the luminaires,
one for the headlights — seven of eight, with one left for whatever a world
wants next. `--no-headlights` drives without them; they come on where it is
dark, which in this world means inside a bore.

### Tracks, and the times driven on them

Starting the game with no arguments is a reasonable thing to do: with no world
named on the command line it offers whatever is in the library, and with exactly
one world in it, drives that.

A world is a directory of tiles plus a `world.json` manifest beside them, which
`oglc-bake` writes: what the world is called, how long its road is, how much of
that is viaduct, bore and causeway, and which picture shows it. The library is
every such directory under

```
$XDG_CONFIG_HOME/glisteel/tracks/      # or %APPDATA%\glisteel\tracks on Windows
```

which is `OpenGLContext.userpaths` — the same rule the engine's settings and
asset cache follow. Bake into it and the game offers it:

```bash
oglc-bake --output ~/.config/glisteel/tracks/ashdown-forest --seed 11
oglc-bake --output ~/.config/glisteel/tracks/beacon-hill --seed 23 --extent 3072
glisteel                       # both are offered, by their own pictures
```

**A track takes its own picture.** `glisteel <tileset> --picture` drives the
world, photographs the car on it from behind, and writes the picture's name into
the manifest, which is what the chooser then shows.

**Best times** are kept per track in `times.json` beside the library — five per
track, quickest first, with the day each was driven. A lap is offered to the
table when a race finishes and the table answers where it came, which is what
the finish screen says.

```python
from glisteel.records import Records
table = Records()
table.offer('ashdown forest', 239.407)     # 1, if it is the quickest so far
table.save()
```

**Whoever is driving is a `Controller`** -- one method, handed the session and
the length of the step, answering with the throttle, the brake and the wheel.
The autopilot is one, `KeyboardDriver` is one, and so is anything a test
scripts. Setting `session.driver` mid-run hands the car over.

### Scenarios

A scenario is a few hundred metres of road with one question in it -- does the
wheel come back to centre, does the car stay on the deck through a chicane, does
it get over a crest with its wheels down -- built in the time a test can afford.
Everything in one is the real thing: the same `Course` a baked world hands over,
the engine's own swept carriageway collider, and a height field cut into chunks
the way a field world's ground is. What is left out is the drawing, which is
what makes one cost milliseconds rather than seconds.

| Scenario | Road | What it is for |
|---|---|---|
| `straight` | 400 m, level | steering feel, centring, top speed, drag |
| `verge` | a straight with boulders either side | surfaces, being mired, hitting something |
| `sweeper` | 120 m radius | steady-state cornering, holding a line |
| `chicane` | a left and a right | transient response, catching a slide |
| `hairpin` | a straight into 28 m radius | braking, and what the car does at the apex |
| `crest` | a rise the road goes over | whether the wheels stay down at the top |
| `dip` | a hollow it runs through | the compression at the bottom |
| `circuit` | 800 m closed | laps, sectors, the map, and traffic |

```python
scenarios.named('crest').world(traffic=4)   # a world to drive it in
```

### Driving to a script, and measuring what happened

A player's input is a square wave — a key is down or it is not — and what makes
that feel like a car is everything between the key and the road. `Script` writes
a drive down and replays it through the same `KeyboardDriver` the window fills,
so the wheel winds on and centres exactly as it does for a person:

```python
from glisteel.scripted import Script
from glisteel.trace import drive

trace = drive(session, Script.parse('throttle 0..12; left 6..6.15'), seconds=12.0)
print(trace.report())
```

`drive` records a row for every physics step — where the car was, what the driver
asked for, where the wheel and the front wheels were, where the camera looked,
how far off the line it ran — and returns it as numpy columns. Recording at the
step rather than at a frame rate is what makes the same script give the same
numbers twice; passing `step=1/60` is how a measure is shown not to depend on the
frame rate.

| Measure | Is | In |
|---|---|---|
| `steering_rate` | the quickest the wheel moved | wheel units a second |
| `time_to_centre` | how long the wheel took to come back to straight | seconds |
| `camera_yaw_rate` | how fast the view swings | radians a second |
| `camera_yaw_jerk` | how sharply that swing changes | radians a second squared |
| `camera_bounce` | the eye's vertical acceleration | metres a second squared |
| `lateral_g` | the hardest the car cornered | g |
| `heading_change` | what a steering input actually bought | degrees |
| `worst_off_line` | the furthest it ran from the middle of the road | metres |

The noisy ones are read at the 95th percentile rather than at their peak, because
what a driver feels is what happens nearly all the time and not one step of one
bump. `tests/test_feel.py` writes budgets against them: each test is a drive
somebody complained about, and the ones marked `xfail` are the defects still
open — see `plans/GAMEPLAY-TEST-HARNESS.md`.

## Licence

BSD-3-Clause; see [license.txt](license.txt).
