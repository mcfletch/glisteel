# Recorded sessions

A session journal written by
[OpenGLContext's telemetry](https://github.com/mcfletch/openglcontext/blob/main/docs/telemetry.html):
every frame's time, the seed the session's randomness came from, and every input
the platform delivered. Replaying one drives the engine's clock from the
recorded frame times and puts the randomness back, so the drive plays out the
same way on any machine.

```bash
OPENGLCONTEXT_TELEMETRY_REPLAY=sessions/doc-lap.jsonl \
  glisteel baked-world/tileset.json --view chase --autopilot
```

## `doc-lap.jsonl`

An autopilot lap of the default baked world: 1,680 frames over 115 seconds,
62&nbsp;KB. It is what the documentation pictures of this game are taken from,
so that a picture can be produced again rather than fished for.

A picture also needs the capture to happen at the same *point in the drive*, and
`--capture-delay` is a wall clock — it waits for the world to stream in, which is
what it is for, and it lands the car near a place rather than on it. `--capture-frame`
captures on frame N instead:

```bash
OPENGLCONTEXT_TELEMETRY_REPLAY=sessions/doc-lap.jsonl \
  glisteel baked-world/tileset.json --size 1600x900 --view chase --no-hud \
  --autopilot --capture-frame 1297 --capture viaduct.png
```

Two runs of that write the same bytes. Frames worth knowing:

| Frame | World time | Where |
|---|---|---|
| 569 | 45 s | a straight through mixed forest |
| 770 | 60 s | the approach to a tunnel portal |
| 910 | 70 s | inside the bore |
| 1069 | 78 s | leaving the bore onto the viaduct |
| 1297 | 90 s | mid-viaduct, over the valley |

The journal is tied to the world it was driven on: replaying it against a
differently baked world replays the same clock and the same input against
different ground, and the car goes somewhere else. Re-bake the world and the
session wants recording again:

```bash
OPENGLCONTEXT_TELEMETRY=sessions/doc-lap.jsonl \
  glisteel baked-world/tileset.json --size 1600x900 --view chase --no-hud \
  --autopilot --drive-seconds 110 --capture /tmp/end.png
```
