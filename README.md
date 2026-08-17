# GLinting Steel

A racing game on [OpenGLContext](https://github.com/mcfletch/openglcontext): a
car, a circuit, and a world too big to load. The track streams in around the
player as they drive it, and every tile that pages in becomes collision the car
drives on — the same triangles you can see.

```bash
pip install glisteel OpenGLContext-editor
oglc-bake --output /tmp/world --extent 2048 --depth 3 --max-instances 24
glisteel /tmp/world/tileset.json
```

The first command bakes a world: hills, a lake, a conifer forest and a 4.6 km
circuit through it. The second drives it.

## Driving

| | |
|---|---|
| `up` / `w` | throttle |
| `down` / `s` | brake, and reverse once stopped |
| `left` `right` / `a` `d` | steer |
| `space` | handbrake |
| `c` | chase camera / bonnet camera |
| `r` | put the car back on the track |
| `F2` | screenshot |

`glisteel --autopilot` drives itself, which is the quickest way to see a lap and
the same code an opponent car would use.

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
| `race.py` | lap timing that a shortcut does not fool |
| `hud.py` | the four numbers a driver acts on |
| `game.py` | the window, the loop, and the keys |

**The road comes with the world.** A pile of triangles does not say where a
track goes, so the baker writes the centreline into the tileset's `extras` and
the game reads it back. That is what puts the car on the grid, points it the
right way, times the lap, and steers the autopilot.

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
