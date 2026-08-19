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
| `F2` | screenshot |

`glisteel --autopilot` drives itself, which is the quickest way to see a lap and
the same code an opponent car would use.

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
bonnet; the chase view is what a player catching a slide wants. The player's own
car is not drawn for the cockpit view, because the eye is inside its shell.

## What is where

The game is deliberately thin. Streaming, rendering, roads and physics belong to
the engine underneath — `OpenGLContext` and `omi_physics` — and what is here is
what makes it a *game*.

| Module | Holds |
|---|---|
| `world.py` | a baked world: its tiles, its physics, and the roads it carries |
| `car.py` | the car — its body, its wheels, and how it is drawn |
| `camera.py` | where the player watches from |
| `driver.py` | the autopilot: pure pursuit, and a speed the corner allows |
| `race.py` | lap timing that a shortcut does not fool, and leaving the road |
| `hud.py` | the four numbers a driver acts on |
| `game.py` | the window, the loop, and the keys |

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
instead, so a tap is a nudge and a hold builds to lock, and the lock the front
wheels reach eases off as the car speeds up. `--mouse` steers with the pointer:
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

## Licence

BSD-3-Clause; see [license.txt](license.txt).
