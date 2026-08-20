# glisteel plans

| Plan | Status | Description |
|------|--------|-------------|
| [2026-08-19-PLAY-REVIEW.md](2026-08-19-PLAY-REVIEW.md) | landed (2026-08-19) | Ten complaints from a drive of the shipped world, and what each turned out to be: a steering aid with a lane of its own, a start line the game did not read, a bonnet seen edge-on, traffic stood on its own roof, tunnel portals buried in the hillside, causeway flanks wound inside out, and a restart that dropped the car through the world. Records the one cost accepted (the hill over a long bore is opened into a cutting) and the terrain feature that would remove it. |
| [2026-08-19-CODE-REVIEW.md](2026-08-19-CODE-REVIEW.md) | P1 + measured P2/P3 landed (2026-08-19) | A gating code review of `glisteel` and `glisteel-editor` and the engine interfaces they use: ten correctness defects, a measured performance profile (75 % of an editor redraw and 25 % of a game frame spent recomputing constants), security and untrusted-input hardening, the state of the type and lint gates, and what the coverage figures hide. Priority-ordered remediation checklist at the top; the ten P1 correctness defects and the measured performance, security and gate items are fixed and pinned; §12 and §13 record what landed and what is still open. |
| [CAR-MODELS.md](CAR-MODELS.md) | — | The shapes, names and budgets the vehicles are built to, and what `tools/cars.py` produces from them. |
| [FRONT-END-AND-WORLD.md](FRONT-END-AND-WORLD.md) | — | The menus, the track library and the times table, and how a baked world reaches them. |
| [GAMEPLAY-TEST-HARNESS.md](GAMEPLAY-TEST-HARNESS.md) | — | Driving to a script and measuring what happened: the `Trace` measures, their units, and the budgets held against them. |
