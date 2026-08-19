# glisteel plans

| Plan | Status | Description |
|------|--------|-------------|
| [2026-08-19-CODE-REVIEW.md](2026-08-19-CODE-REVIEW.md) | P1 landed, P2/P3 open (2026-08-19) | A gating code review of `glisteel` and `glisteel-editor` and the engine interfaces they use: ten correctness defects, a measured performance profile (75 % of an editor redraw and 25 % of a game frame spent recomputing constants), security and untrusted-input hardening, the state of the type and lint gates, and what the coverage figures hide. Priority-ordered remediation checklist at the top; the ten P1 correctness defects are fixed and pinned, and §12 records what landed. |
| [CAR-MODELS.md](CAR-MODELS.md) | — | The shapes, names and budgets the vehicles are built to, and what `tools/cars.py` produces from them. |
| [FRONT-END-AND-WORLD.md](FRONT-END-AND-WORLD.md) | — | The menus, the track library and the times table, and how a baked world reaches them. |
| [GAMEPLAY-TEST-HARNESS.md](GAMEPLAY-TEST-HARNESS.md) | — | Driving to a script and measuring what happened: the `Trace` measures, their units, and the budgets held against them. |
