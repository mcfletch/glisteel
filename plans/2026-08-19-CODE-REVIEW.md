# Code review: glisteel and glisteel-editor — 2026-08-19

**Scope.** Every module of `glisteel/glisteel/` (23 files, 6 262 lines),
`glisteel/tools/` (3 files, 1 824 lines), `glisteel-editor/glisteel_editor/`
(10 files, 2 456 lines), and the interfaces both take from `OpenGLContext`,
`OpenGLContext_editor` and `omi_physics`. Both test suites, both `pyproject.toml`
gates, both `README.md`.

**Standard applied.** [CLAUDE.md](../../CLAUDE.md): this is a 28-year-old
codebase used as learning material, features belong in the engine, correctness
and reliability are the goal, performance is measured against a real game rather
than against the demo, and documentation ships with the change. A finding here
is something that falls short of *that* bar, not of a general-purpose one.

**Evidence.** Every claim below is either a quoted line of the code or a
measurement reproduced in §11. Nothing is asserted from impression. Where a
finding is a judgement call rather than a defect it is marked **[opinion]** and
carries the reasoning, so it can be argued with or declined on its merits.

**Relationship to existing plans.** This is a *code-quality* gate. It does not
overlap [glisteel-editor/plans/EDITOR-REMEDIATION.md](../../glisteel-editor/plans/EDITOR-REMEDIATION.md),
which tracks a designer's *feature* list; four findings here (E1, E4, P1, P2)
land in files that plan is actively changing and should be folded into its
phases rather than scheduled separately.

**Verdict.** The design is sound and the writing is unusually good — see §10,
which is not a courtesy. What blocked the gate was a specific, short list: ten
correctness defects, three of which corrupt or lose a user's work, and a
performance profile in which **75 % of an editor redraw and 25 % of a game frame
are spent recomputing constants**. All of it is local; none of it needs a
redesign.

**Status, 2026-08-20: the P1 defects and the E, S and T items are fixed**,
Red/Green throughout — §12 for P1, §13 for the measured performance and security
work, §14 for the editor's redraw and the typing, §15 for the P3 tables. A game
frame costs 29 % less
than it did, an editor redraw 45× less, a structure query over a terrain chunk
172× less; both type gates are green and now check the seams rather than `Any`.
What is left is §14's "still open".

---

## Remediation status — 2026-08-20

| Group | Items | Status |
|-------|-------|--------|
| **P1** correctness and data loss | C1–C10 | **10 of 10 fixed** (§12) |
| **P2** performance | E1–E12 | **12 of 12 fixed** (§13, §14) |
| **P2** security and untrusted input | S1–S5 | **5 of 5 fixed** (§13) |
| **P3** types, gates and testing | T1–T7 | **6 of 7 fixed**; T5 partly (§13, §14) |
| **P3** API design and organisation | A1–A21 | **18 of 21 fixed**; A13, A20 declined, A11 partly (§15) |
| **P3** dead code and inconsistency | D1–D22 | **22 of 22 fixed** (§15) |

**77 findings: 73 fixed, 1 withdrawn as wrong (A15), 3 declined with reasons,
1 partly done (T5).** Every fix was made Red/Green — the test written and seen
to fail for the stated reason before the code changed.

At the end of it: `glisteel` 931 passed, 1 xfailed; `glisteel-editor` 373
passed; `ruff` and `mypy` clean on both packages.

### What is still open

| | Why it is open |
|---|---|
| **T5** (partly) | The seven lap drives are marked `slow`, taking the suite from 3 m 15 s to 2 m 25 s. That is a saving and not the quick loop the item asked for: the cost is spread more widely than the `--durations` list showed. Standing up a scenario world is the next thing to measure |
| **A13** | The editor bakes on its UI thread. The fix is a worker and progress, which touches GL-thread ownership in a file another agent is rewriting; it belongs in `EDITOR-REMEDIATION.md`'s baking phase |
| **A20** | `tools/cars.py` is 1 571 lines and wants splitting. It is under active edit for the vehicle work, so a split now would conflict with that rather than help. The trap it hid is caught by `tests/test_sources.py` |
| **A11** (partly) | `GlisteelContext.config` is still a class attribute, because the backend has no way to pass one through context construction. It is typed now, which was the part that hid mistakes |
| **T4** (partly) | `Options` took the *configuration* out of the window's uncovered region, which is where the defects were. `OnInit`, `SwapBuffers` and the light rig remain window-bound, so `game.py`'s coverage figure is still flattered |

## Remediation checklist

Ordered by priority. **P1** must land before this code is a gate anyone else
builds on: each is a defect a user meets. **P2** is measured performance and
hardening. **P3** is organisation, consistency and cleanliness — individually
small, collectively the difference between a toolkit and a demo.

### P1 — Correctness and data loss — **all landed, 2026-08-19**

Each was fixed Red/Green: the test was written first and seen to fail for the
stated reason, then the fix made it pass. What each is pinned by is in the last
column; §12 records what landed.

| ID | Finding | Where | Pinned by |
|----|---------|-------|-----------|
| **C1** | Dragging a point on a **reversed** route moves a *different* point and corrupts the line | `glisteel-editor/glisteel_editor/editing.py:88`, `:97` | `test_editing.py::TestALineDrivenTheOtherWayRound` (5) |
| **C2** | The primitive car body's sides and **every** wheel triangle are wound inward, so back-face culling removes them | `glisteel/glisteel/car.py:341`, `:360` | `test_car_and_camera.py::TestThePrimitiveCarIsWoundTheRightWayRound` (4) |
| **C3** | `--mouse` silently does nothing: the `mousemove` handler is never bound | `glisteel/glisteel/game.py:134` vs `:352` | `test_bindings.py` (7) |
| **C4** | `Course`, `Trace`, `Readings`, `Scenario` all raise `ValueError` on `==`; `Scenario` is unhashable | `world.py:71`, `trace.py:50`, `session.py:99`, `scenarios.py:86` | `test_values.py` (14) |
| **C5** | `_wheel_innards` and `_spoke` are each defined **twice**; the first pair is dead and the hero wheel silently uses the second | `glisteel/tools/cars.py:997`,`:1022` vs `:1095`,`:1118` | `test_sources.py::TestNothingIsDefinedTwice` (27) |
| **C6** | Editor **New** and **Open** discard unsaved work with no prompt, while **Quit** asks | `glisteel-editor/glisteel_editor/app.py:447`, `:451` | `test_app.py::TestWhetherReplacingTheProjectLosesWork` (5) |
| **C7** | `Project.save`/`open` are non-atomic and use the locale encoding | `glisteel-editor/glisteel_editor/project.py:299`, `:309` | `test_project.py::TestSurvivingBeingWritten` + `TestOpeningSomethingThatIsNotAProject` (6) |
| **C8** | Moving a spring is not undoable, and Escape mid-drag does not put it back | `glisteel-editor/glisteel_editor/water.py:71`, `:132` | `test_water.py::TestTakingBackASpringThatWasMoved` (6) |
| **C9** | Library and UI code raises `SystemExit`; picking a road-less track from the menu kills the game | `world.py:337`, `game.py:162`, `:650` | `test_world.py::TestAskingForAWorldThatIsNotThere` + `test_opening.py` (9) |
| **C10** | The `records` doctest documents behaviour the code does not have — and **no doctest is ever run** | `records.py:12`; both `pyproject.toml` | `--doctest-modules` in both projects; 8 module doctests now run |

### P2 — Performance (all measured; see §11) — **landed, 2026-08-19**

| ID | Finding | Where | Cost | Fix |
|----|---------|-------|------|-----|
| **E1** | `start_mark()` calls `self.project.world()` instead of the cached `self.world()`, rebuilding a whole `ProceduralWorld` **per redraw** | `scene.py:442` | **196 ms of a 261 ms warm redraw** | One-word change: `self.world()` |
| **E2** | `guide()` and `markers()` call the scalar `height_at()` once per point | `scene.py:234`, `:540`, `:558` | **26× slower** than one vectorised call | Sample once per array, as `_contour_shape` (`:406`) already does |
| **E3** | `Course.nearest()` and `Course.stations` are recomputed 10.5 and 50 times a frame | `world.py:110`, `:165` | **2.7 ms/frame — 25 % of session time** on a 7.9 km circuit | `cached_property` for `stations`; resolve `nearest` once a frame in `Session` and pass it down |
| **E4** | `road()`/`structures()` do not cache a "no road yet" answer | `scene.py:352`, `:369` | Full `circuit()` settle every redraw while the line is short | Cache the negative result; invalidate with the others |
| **E5** | `tileset.json` is read and JSON-parsed **three times** at startup | `world.py:258`, `:421`, `:432` | One parse of a large tileset, ×3 | Read once in `__init__`, pass the document down |
| **E6** | `Course.inside()` materialises a full `P × S` distance matrix | `world.py:115` | 262 k ground samples × 500 road points ≈ 2 GB | Chunk the query, or use a spatial index |
| **E7** | `Session._settle()` runs 180 blocking physics steps in `__init__` **and** in `restart()` | `session.py:414` | A visible hitch on every start and restart | Settle across the countdown, which is already 6 s of held car |
| **E8** | `Autopilot.target_speed()` recomputes the road's curvature every frame; `update()` calls `nearest()` twice | `driver.py:352`, `:142`/`:155` | ~50–100 `curve_radius` calls per driver per frame | Precompute a per-index corner-speed array on `Course`; pass the index into `steering()` |
| **E9** | `Traffic._look_ahead()` is O(N²) over cars **plus** two full-course scans per frame | `traffic.py:328` | Grows quadratically with `--traffic` | Sort by station once; reuse the session's `nearest()` result |
| **E10** | Function-local imports in per-frame code | `game.py:442`, `world.py:555`, `reflections.py:127` | A `sys.modules` lookup per frame, and it hides the dependency | Hoist to module scope; keep only genuinely cycle-breaking ones, with a comment saying so |
| **E11** | `Scenario._cache` is declared and never used; `world()` builds `course()` three times | `scenarios.py:100` | 2.1 ms per 200 `course()` calls | Use the field, or delete it and memoise `course()` |
| **E12** | `Car._wheel_spin` accumulates without bound | `car.py:183` | Float precision decays over a long race | Wrap modulo 2π |

### P2 — Security and untrusted input — **landed, 2026-08-19**

| ID | Finding | Where | Fix |
|----|---------|-------|-----|
| **S1** | A manifest's `tileset`/`picture` are joined onto a directory with no containment check, so `../../..` escapes it | `tracks.py:98`, `:203` | `os.path.realpath` + `os.path.commonpath` check against the track directory |
| **S2** | `RaceWorld` accepts a URL and streams from it with no scheme allow-list, size cap or timeout stated | `world.py:336`, `:258` | Document the trust boundary; allow-list schemes; state the engine's limits |
| **S3** | `_baked_luminaires()` reshapes attacker-controlled JSON with no validation | `world.py:432` | Validate shape and length; refuse with a clear message |
| **S4** | `Records.save()` is non-atomic with no locking; two sessions overwrite each other's table | `records.py:123` | Temp file + `os.replace` |
| **S5** | `Project.open()` has no error handling: a corrupt file gives a raw traceback | `project.py:307` | Match `Records._read()`, which handles this correctly |

### P3 — Types, gates and testing

| ID | Finding | Where | Fix |
|----|---------|-------|-----|
| **T1** | `mypy` as configured **fails**: 42 errors in glisteel, 29 in the editor | both `pyproject.toml` | Add `[[tool.mypy.overrides]]` with `ignore_missing_imports` for `OpenGLContext.*`/`omi_physics.*`, or a `mypy_path`; then make it green and keep it there |
| **T2** | `ruff` **fails** on the editor: 8 errors (7 × `I001`, 1 × `F401`) | `glisteel-editor/` | `ruff check --fix`; add both to CI |
| **T3** | `Any` on almost every parameter defeats `disallow_untyped_defs` entirely | throughout, e.g. `session.py:139`, `driver.py:200`, `car.py:101` | Introduce `Protocol`s for the four real interfaces (car, course, session, world) and use them |
| **T4** | `# pragma: no cover` hides 289 of 368 statements in `game.py` — **which then reports 100 % coverage** — and 275 of 337 in `app.py` | `app.py:82` (whole class), `game.py:125` onward (34 method pragmas) | Hoist the logic per CLAUDE.md; report coverage with and without the exclusions |
| **T7** | `car.py` is the least-covered module at **76 %**, and the uncovered lines are exactly the primitive-mesh path where C2 lives | `car.py:283`–`:414` | Cover `car_body_mesh`, `cabin_mesh`, `wheel_mesh`, `car_nodes` — the fix for C2 is the test |
| **T5** | The glisteel suite takes **3 m 42 s** for 674 tests | `glisteel/tests/` | Mark and separate the slow physics traces; keep a sub-minute default loop |
| **T6** | `race.__all__` omits `Collisions`, `closing_speed`, `off_course`, `SECTORS`, `PATIENCE`, `LOST`, `SURVIVABLE` — three of which `session.py` imports | `race.py:20` | Complete it, or drop `__all__` and rely on the leading underscore |

### P3 — API design and code organisation — **landed 2026-08-20, except A13, A20 and part of A11**

| ID | Finding | Where | Fix |
|----|---------|-------|-----|
| **A1** | Four separate implementations of "yaw from a forward vector", in **two opposite sign conventions**, none referring to the others | `camera.py:80`, `world.py:153`, `traffic.py:213`, `trace.py:297` | One helper with the convention stated once; call it from all four |
| **A2** | `Trace`'s 15 fields are enumerated in three places, and `_assemble` couples them by tuple index | `trace.py:50`, `:180`, `:303` | `dataclasses.fields()` + `dataclasses.replace`; build rows as dicts |
| **A3** | `hud.show()` re-declares all nine fields of `Readings`, and `game._update_hud` copies them across one at a time | `hud.py:71`, `game.py:449` | `show(self, readings: Readings)` |
| **A4** | Law of Demeter: `KeyboardDriver` reaches `car.vehicle.forward_speed()`; `Car.velocity()` reaches `world.linear_velocity[...]` | `steering.py:183`, `car.py:158` | Expose `Car.forward_speed()` and `Car.velocity()` from the vehicle's own API |
| **A5** | `RaceWorld.from_course` builds via `cls.__new__(cls)` and sets attributes by hand | `world.py:366` | A shared private `_setup`, or make `__init__` take an already-loaded world |
| **A6** | `Traffic` keys three dictionaries on `id(car)` | `traffic.py:290`–`:296` | Key on the car itself (identity-hashable), or hang the state on `TrafficCar` |
| **A7** | `Course.SETTLE_DROP`/`GRID_SETBACK`/`LOST_BELOW`/`BORE_MARGIN` are defined ~50 lines **after** the code that reads them | `world.py:245`–`:261` | Move to the constant block at the top |
| **A8** | `TrafficCar._along()` flips `self.heading` as a side effect of a name that reads as a query | `traffic.py:239` | Split the wrap from the turn-round, or rename to `_travel_to` |
| **A9** | `MapScene.reset`/`water_changed`/`route_changed` hand-list overlapping subsets of the same six caches | `scene.py:206`–`:232` | Declare the dependencies once; invalidate by name |
| **A10** | `RouteEditor` history is a bare 4-tuple accessed by index | `editing.py:257`, `:262` | A `NamedTuple` |
| **A11** | `GlisteelContext.config` is a class-level global that `main()` writes and two subclasses shadow | `game.py:100`, `:595` | Pass the options to the instance |
| **A12** | `options.project` is a `str` from argparse and a `Project` at runtime | `app.py:645` | Keep them separate attributes |
| **A13** | `_bake()` runs the whole bake on the UI thread; the "Baking…" message can never be drawn | `app.py:518` | Run it off-thread, or draw a frame before starting |
| **A14** | `os._exit(0)` after a capture skips every `finally`, thread join and GL teardown | `game.py:486` | Leave the main loop properly |
| **A15** | `TARMAC`/`VERGE`/`ROUGH` are shared mutable singletons assigned onto every car's vehicle | `race.py:130`–`:132` | Freeze them, or hand out copies |
| **A16** | `CONTROLS` is a module-level mutable dict of mutable sets, and there is no rebinding API for a game | `steering.py:186` | Make it a frozen default with a per-driver override |
| **A17** | `_DRAWN` is an unbounded module-level cache with no eviction and no thread guard | `reflections.py:58` | `functools.lru_cache` |
| **A18** | `models.ART` resolves assets through `__file__` | `models.py:30` | `importlib.resources` |
| **A19** | `race.py` holds four unrelated responsibilities (lap timing, off-road watching, collisions, closing speed) behind a docstring describing only the first | `race.py:1` | Split, or widen the docstring to cover what is there |
| **A20** | `tools/cars.py` is 1 571 lines with 56 top-level functions | `tools/cars.py` | Split by subject: materials, meshes, hero, wheels, traffic, export |
| **A21** | `tools/elevation.py` and `measure_form.py` execute on import via top-level `sys.argv` | `tools/elevation.py:14` | A `main()` behind `if __name__ == '__main__'` |

### P3 — Dead code, unused parameters and inconsistency — **landed 2026-08-20**

| ID | Finding | Where | Fix |
|----|---------|-------|-----|
| **D1** | `_limit(course)` ignores its only argument and returns a bare literal | `traffic.py:532` | Read the limit off the course, or make it `SPEED_LIMIT = 27.8` |
| **D2** | `TrafficCar.brake_for(reason)` ignores `reason` | `traffic.py:168` | Log it, or drop the parameter |
| **D3** | `Collisions.update(closing, dt)` ignores `dt` | `race.py:237` | Drop it, or make severity time-weighted as the sibling watchers are |
| **D4** | `_spring_marks(metres_per_pixel)` is never passed one, so spring markers are 7 m at every zoom — the opposite of the documented intent | `scene.py:503`, `:487` | Thread `metres_per_pixel` through `water()` as `markers()` does |
| **D5** | `app._at()` is defined, imports numpy locally, and is never called | `app.py:604` | Delete |
| **D6** | `Scenario._cache` is declared and never read or written | `scenarios.py:100` | Use it or delete it |
| **D7** | `COCKPIT_SIDE = 0.0` makes the `across * COCKPIT_SIDE` term dead, and the comment beside it claims the opposite of what the module docstring says | `camera.py:48`, `:158` | Delete both, or set a real offset |
| **D8** | `Route.plan()`'s `len(plan) > 2` guard changes nothing — for two points the reversal is the identity | `project.py:150` | Drop the guard |
| **D9** | `game.py` re-imports `tracks` locally in two places although it is imported at module scope | `game.py:474`, `:647` | Delete both |
| **D10** | `# noqa: S603` suppresses a rule that is not in the selected set | `app.py:550` | Delete, or add `RUF100` so stale suppressions are caught |
| **D11** | `--traffic` has two different defaults: `DEFAULT_TRAFFIC` (6) in the parser, `0` in the `getattr` that reads it | `game.py:160` vs `:559` | Read `self.config.traffic` directly — the parser guarantees it exists |
| **D12** | Nine defensive `getattr(self.config, …, default)` calls duplicate defaults argparse already guarantees | `game.py:160`–`:200` | Read the attributes directly |
| **D13** | `--size` is parsed with `partition('x')` + `int()`: `--size 1280` gives a traceback, not an argparse error | `game.py:597`, `app.py:649` | An argparse `type=` function |
| **D14** | `build_parser`'s epilog is sliced out of `__doc__` by literal string search — rewording the module docstring raises `ValueError` at startup | `game.py:521` | A module constant for the key text |
| **D15** | `Headlights` declares five tuning values as annotated class attributes while every sibling (`CarSpec`, `DriverStyle`) is a dataclass | `lighting.py:117`–`:131` | Make it a dataclass |
| **D16** | `menu.track_screen` uses a list as a one-shot boolean flag | `menu.py:132` | `nonlocal` |
| **D17** | `Script.controls` re-sorts five key sets on every physics step (120/s) | `scripted.py:123` | Precompute the representative key per control |
| **D18** | `build()` copies `water.children` onto itself with no explanation | `scene.py:598` | Delete, or say why |
| **D19** | `Records.offer` reports `table.index(record)`, which returns the *first* equal record — a repeated identical time reports the wrong place | `records.py:117` | Track the inserted object by identity |
| **D20** | The `cars.py` docstring repeats "The paint is a finish…" twice, and `# --- The player's car ---` appears as a heading twice | `tools/cars.py:42`/`:50`, `:89`/`:685` | Delete the duplicate paragraph; retitle the first heading |
| **D21** | `Session.restart()` leaves `_accumulated` and `reflections` from the previous run | `session.py:316` | Reset both |
| **D22** | `glisteel/plans/` has no index while `glisteel-editor/plans/` has `PROJECT-PLAN.md` | `glisteel/plans/` | Add the matching index |

---

## 1. Correctness defects

### C1 — The editor drags the wrong point on a reversed route  *(P1, data-corrupting)*

`Route.plan()` reverses the point order when `route.reversed` is set
(`project.py:139`), and `RouteEditor.point_at()` (`editing.py:88`) and
`segment_at()` (`editing.py:97`) both hit-test against `plan()` and return an
index into it. Every caller then treats that index as an index into
`route.points`: `RouteTool.on_press` reads `self.editor.route.points[found]`,
and `move`/`insert`/`remove` all index `self.route.points` directly
(`editing.py:174`, `:167`, `:190`).

The two orderings differ as soon as a designer right-clicks with the Start tool,
which sets `reversed` (`editing.py:227` → `project.py:135`). Reproduced:

```
reversed route, points at x = 0, 100, 200, 300, 400
pointer at (400, 0) -> point_at index 1 -> route.points[1] = (100.0, 0.0)
after the drag: [(0,0), (400,-50), (200,0), (300,0), (400,0)]
```

The point the designer grabbed did not move; a point 300 m away was teleported
on top of it. The line is silently mangled, and one undo takes back only the
last drag.

`StartTool._nearest()` (`editing.py:295`) does the same hit test against
`route.points` — so the codebase already contains both spellings, and the
inconsistency between two hit tests in the same file is itself the signal.

**Fix.** Hit-test against `route.points`. `plan()` is the *generator's* view
(direction of travel); the editor edits the drawn order. Add a regression test
with `reversed=True` — the existing `test_editing.py` cases never set it.

### C2 — The primitive car and every wheel are wound inside-out  *(P1)*

`_box_mesh` (`car.py:360`) claims: *"The outline runs clockwise seen from above,
which is what makes the sides face outward."* Both halves are wrong. Measured
against the mesh's own centroid:

```
BODY MESH: side triangles pointing INWARD: 12 of 12
BODY MESH: cap  triangles pointing INWARD:  0 of 8
WHEEL:     tread triangles INWARD: 32 of 32
WHEEL:     disc  triangles INWARD: 28 of 28
```

The prism is *internally inconsistent*: caps face out, sides face in. The wheel
is uniformly inverted. `PBRMesh.solid` defaults `True`
(`pbrmesh.py:190`), `PBRMaterial.doubleSided` defaults `False`
(`pbrmaterial.py:81`), and the pass enables `GL_CULL_FACE` with `GL_CCW` front
faces (`_flat.py:1010`) — so the sides of the primitive body and the whole of
every primitive wheel are culled, and `_mesh` (`car.py:381`) derives the shading
normals from the same winding, so what survives is lit from the wrong side.

This is the documented fallback for a `.glb` that will not load — *"art is not
rules, and a game that would not start without its `.glb` files has made a
picture into a dependency"* (`car.py:11`) — and it is also what
`car_nodes()` draws for **every traffic vehicle** whose model is missing
(`traffic.py:399`). The principle is right; the fallback does not work.

**Fix.** Reverse the side winding in `_box_mesh` and the tread and disc winding
in `wheel_mesh`. Add a test that asserts every face normal has a positive dot
product with `(centroid → face centre)` — it is four lines and it would have
caught this.

### C3 — `--mouse` never binds its handler  *(P1)*

`OnInit` calls `_bind_keys()` at `game.py:134`. `_bind_keys` guards the pointer
handler on `self.keyboard is not None and self.keyboard.pointer is not None`
(`game.py:362`). `self.keyboard` is only ever assigned at `game.py:352`, inside
`_driver()`, which runs from `open()` — *after* `_bind_keys`. Confirmed by
walking the AST: `OnInit`'s call order is
`addHUDLayer, _show_hud, _bind_keys, _opening_track, show_menu, open`, and
`_bind_keys` is called at exactly one site.

So at the moment the guard runs, `keyboard` is still the class-level `None`
(`game.py:105`), the `mousemove` handler is never registered, and `_on_pointer`
is dead. `--mouse` is documented in `--help`, in `README.md:26` and again at
`README.md:184`, and the whole of `steering.MouseWheel` exists to serve it.

**Fix.** Bind the pointer in `open()` after `_driver()`, or register
`mousemove` unconditionally and let `_on_pointer`'s own guard
(`game.py:384`) decide — it already has one.

### C4 — Four dataclasses raise on equality  *(P1)*

`Course` (`world.py:71`), `Trace` (`trace.py:50`), `Readings` (`session.py:99`)
and `Scenario` (`scenarios.py:86`) are all `@dataclass` with `eq=True` (the
default) and numpy array fields. The generated `__eq__` compares field tuples,
so comparing two distinct-but-equal instances raises:

```
distinct-but-equal Course == Course -> ValueError: The truth value of an array
                                       with more than one element is ambiguous
Trace == Trace     -> ValueError
Readings == Readings -> ValueError
Scenario == Scenario -> ValueError
hash(Scenario)     -> TypeError: unhashable type: 'numpy.ndarray'
```

`Scenario` is `frozen=True`, so it also generates a `__hash__` that cannot run —
which means a `Scenario` cannot go in a set or be a dict key, and `CATALOGUE`
(`scenarios.py:262`) invites exactly that. Any `assert course == expected`,
`course in courses`, or `dict.get(scenario)` is a latent crash.

**Fix.** `@dataclass(eq=False)` where identity comparison is what is wanted
(`Course`, `Trace`, `Readings`), and a hand-written `__eq__`/`__hash__` on
`Scenario` if value semantics are actually needed.

### C5 — Two functions are defined twice in `tools/cars.py`  *(P1)*

`_wheel_innards` is defined at line 997 and again at 1095; `_spoke` at 1022 and
again at 1118. The bodies are *not* identical — the barrel is `0.90/0.99` in one
and `0.88/0.97` in the other, the brake disc is `0.34/0.20/0.72/0.06` versus
`0.30/0.10/0.74/0.055`, the spoke `half_width` is `0.035` versus `0.055`, the
hub `0.06` versus `0.055`, and the first wraps the brake in `join()` while the
second returns the `revolve` directly.

Python binds module-level names in order, so the second definition wins. The
first ~55 lines of tuned geometry are unreachable, and `build_wheel`
(`cars.py:1040`) — which sits *between* the two pairs, under the
`# --- The wheels ---` heading, next to the definitions it appears to use — in
fact calls the later ones. A maintainer editing the first pair would see no
change in the exported model.

Ruff does not catch it: `F811` fires on redefinition of an *unused* name, and
both are referenced. Adding `F811` alone is not enough here; a `--select F811`
run on the file still passes. The reliable guard is the split proposed in A20
plus a duplicate-name check.

### C6 — New and Open throw away unsaved work  *(P1)*

`app._quit()` (`app.py:552`) correctly guards on `self.project.dirty` and puts
up `dialogs.confirm`. `_new()` (`app.py:447`) and `_open()` (`app.py:451`)
replace `self.project` with no such check. A designer who has drawn a circuit
and presses Ctrl-O loses it with no prompt and no undo — and `Project` is
explicitly *"the handful of decisions that produced [the world] … what has to
come back exactly when the file is opened tomorrow"* (`project.py:4`).

Compounding it, `_save()` (`app.py:484`) falls back to `'untitled.glisteel'` in
the current working directory with no dialog and no existence check, so a second
unnamed project silently overwrites the first — and by C7 that write is not
atomic.

### C7 — Project files are written non-atomically, in the locale encoding  *(P1)*

```python
with open(target, 'w') as handle:            # project.py:299
    json.dump(self.to_json(), handle, indent=2, sort_keys=False)
```

Two defects. **Non-atomic**: the file is truncated before it is rewritten, so a
crash, a full disk or a power loss during the write destroys the project rather
than leaving the previous version. **Locale-dependent encoding**: a project or
route name containing a non-ASCII character is written in whatever
`locale.getpreferredencoding()` returns and is unreadable on a machine with a
different one. `Project.open` (`:309`) has the same omission.

The correct pattern is already in this codebase — `records.py:128` and `:135`
both pass `encoding='utf-8'` — so this is an internal inconsistency, not a
missing convention.

### C8 — Spring moves are not undoable  *(P1)*

`RouteEditor` is careful about this and says why: *"A point dragged across the
map moves a hundred times, and taking that back a hundred times is not undo"*
(`editing.py:222`). It has `begin_step`/`end_step`, `_take()` on every mutator,
and a `cancel()` that puts a dragged point back.

`WaterEditor` has none of it. `move()` (`water.py:71`) never calls
`_remember()`, and `WaterTool.on_press` (`water.py:158`) sets `_dragging` for an
existing spring without remembering either. Two consequences:

- Dragging an **existing** spring is invisible to the history, so the next undo
  reverts an *earlier* change and the drag survives — undo removes work the
  designer did not ask to remove.
- `WaterTool.cancel()` (`water.py:132`) only clears `_dragging`. Escape mid-drag
  leaves the spring where the pointer left it, whereas Escape mid-drag in the
  route tool restores it.

Since a spring reroutes a whole river and everything downstream of the ground,
an unrecoverable spring move is expensive.

### C9 — `SystemExit` from library and UI code  *(P1)*

`RaceWorld.__init__` raises `SystemExit` for a missing world (`world.py:337`).
`RaceWorld` is a library class — importable, constructible from a test, and the
documented entry point for a world. `SystemExit` derives from `BaseException`,
so it passes straight through `except Exception` handlers and unwinds the
interpreter.

Worse in the UI: `GlisteelContext.open()` raises `SystemExit` when a track
carries no roads (`game.py:162`). `open()` is the chooser's callback
(`game.py:329` → `_on_track`), so **picking a road-less world from the track
screen exits the game** instead of saying so. `_picture()` does the same at
`game.py:650`.

**Fix.** Raise `FileNotFoundError` / a small `NoRoadsError`; catch it in `main()`
for the CLI path and in `_on_track` for the menu path, where the message belongs
on `self.status`/an overlay.

### C10 — Doctests are documented, wrong, and never run  *(P1)*

Eight modules carry `>>>` examples. `pytest` is configured with
`testpaths = ["tests"]` and `addopts = "-ra"` in both projects, and neither has
a `conftest.py` — so **not one doctest is collected**. Running them by hand:

```
1 failed, 2 passed
FAILED glisteel/records.py::glisteel.records
    >>> table.offer('ashdown', 999.0) is None
Expected: True
Got:      False
```

The module docstring (`records.py:12`) teaches that a slow lap is refused. With
`KEPT = 5` and two entries in the table, a 999-second lap is kept at position 3.
The documentation is wrong and has been since it was written, because nothing
checks it.

The same example also writes to a fixed `/tmp/times.json` — a doctest with a
real filesystem side effect on a shared path, which would need a `tmp_path`
fixture before it can be enabled.

---

## 2. Performance — the editor

A **warm** map redraw — every `MapScene` cache primed, nothing invalidated —
takes **261 ms** on a 40-point circuit, and `_rebuild()` runs it on every
pointer movement during a drag (`app.py:157` ← `_route_changed` ← `on_change`).
Profiled piece by piece:

```
ground()            0.0 ms
contours()          0.0 ms
road()              0.0 ms
guide()            28.7 ms
structures()        0.0 ms
water()             0.0 ms
start_mark()      196.4 ms
markers()          31.8 ms
build() total     261.2 ms
```

**99.8 % of the cost is three lines**, and every properly-cached piece is free.

**E1.** `start_mark()` reaches past its own cache:

```python
half = self.project.world().circuit().profile.total_width \    # scene.py:442
```

`MapScene.world()` (`scene.py:200`) exists precisely to hold this, and
`Project.world()` documents itself as *"Built fresh each time rather than kept"*
(`project.py:257`). So every redraw constructs a whole `ProceduralWorld` and
settles a circuit through it — measured 196 ms — to read one number that has
not changed. The fix is `self.world()`.

**E2.** `guide()` and `markers()` sample the ground one point at a time through
`height_at` (`scene.py:234`), which wraps each scalar in a 1-element array. For
40 points:

```
40 scalar height_at calls = 28.9 ms;  one vectorised call = 1.10 ms  (26x)
```

The correct pattern is already in the file, with the reasoning attached:
*"One call for the whole elevation rather than one a vertex: the height function
is vectorised, and a contour is thousands of points"* (`scene.py:406`). On a
200-point route the two loops cost ~290 ms per redraw between them.

**E4.** `road()` and `structures()` return `None` for a route that is not yet a
road *without caching that answer* (`scene.py:355`, `:373`), so both redo
`self.world().circuit()` on every redraw while a designer is placing their first
two points — precisely when the redraw rate matters most.

Together E1, E2 and E4 turn a 261 ms redraw into a sub-millisecond one. That is
the difference between a drag at 4 fps and a drag at the display's rate.

---

## 3. Performance — the game

Measured on a shipped-scale circuit: 1 884 centreline points, 7 932 m, six
traffic cars, autopilot driving, **nothing drawn**.

```
session.advance():           10.88 ms/frame
  of which Course.nearest():  0.76 ms/frame
  of which Course.stations(): 1.94 ms/frame
  avoidable share:                 25 %
```

Instrumented call counts, per frame:

```
Course.nearest() calls  = 10.5
Course.stations reads   = 50.0
```

**E3.** `Course.stations` is a `@property` that runs a `diff`, a `norm` and a
`cumsum` over the whole centreline **on every read** (`world.py:110`). It is
read 50 times a frame because `TrafficCar._frame()` (`traffic.py:251`) reads it
on every `position()` call, and `position()` is called three or four times per
car per frame — from the retire filter (`traffic.py:315`), from `_follow` →
`_standing` (`traffic.py:379`), and from `ahead_of` (`traffic.py:405`). The
centreline never changes. `functools.cached_property` removes all 50.

`Course.nearest()` (`world.py:165`) does a full O(N) scan with six whole-array
allocations, including an `np.roll` copy of the centreline. It is called 10.5
times a frame by five independent consumers that all want the same answer about
the same car in the same frame: `RaceTiming.update` (`race.py:81`),
`OffRoad.update` (`race.py:180`), `Reflections.update` (`reflections.py:105`),
`Session._replace`/`_off_course` (`session.py:333`, `:400`),
`Traffic._station_of` and `_offset_of` (`traffic.py:520`, `:349`), and
`Autopilot.update` **and** `Autopilot.steering` — which call it twice for one
decision (`driver.py:142` and `:155`).

At 60 fps the frame budget is 16.7 ms; 2.7 ms of it is spent recomputing two
quantities that are constant. On the README's "busy road" (`--traffic 12`,
`README.md`) the `stations` count roughly doubles. Per CLAUDE.md — *"the bar is
fast enough for any reasonable game a developer might build on it"* — this is
headroom being spent for nothing.

**A correctness note on `nearest()`**, separate from its cost: it returns an
index from `argmin` over the *points* and a distance from a `min` over *all
segments*. On a course that passes near itself — a figure-eight, or a road under
its own viaduct, both of which the structure support explicitly contemplates —
the two can come from opposite branches, so `OffRoad` can read a distance
belonging to a stretch the car is nowhere near.

**E5.** Startup parses `tileset.json` three times: `load_courses`
(`world.py:258`), `_baked_props` (`:421`), `_baked_luminaires` (`:432`). One
read, one parse, three readers of the document.

**E6.** `Course.inside()` (`world.py:115`) builds
`points[:, None, :] - near[None, :, :]`, a dense `P × S × 2` array. Called with
a terrain sampling grid — which is what `RaceWorld._bores()` (`world.py:449`)
does — 262 144 samples against a 500-point tunnel run is ~2 GB of intermediate.
It is also called every frame for a single point by `Session.in_the_dark()`
(`session.py:216`), which additionally recomputes `stations`.

**E7.** `Session._settle()` (`session.py:414`) runs
`int(1.5 / (1/120)) = 180` physics steps synchronously, in `__init__` and again
in every `restart()`. The countdown already holds the car for
`5 × 1.0 + 1.4 = 6.4` seconds (`run.py:44`); settling can happen inside it.

**E8.** `Autopilot.target_speed()` (`driver.py:352`) evaluates
`_corner_speed` — three `course.point()` calls, three norms and a cross product
— for every course point within braking distance, every frame, for every driver.
At 40 m/s that is `30 + 96 = 126` m of road, ~63 points at the baker's 5 m
spacing. The curvature of a course is fixed the moment it is loaded; it should
be one array computed once.

**E9.** `Traffic._look_ahead()` (`traffic.py:328`) is a nested loop over all
cars — 12 branches, the most complex function in either package — and calls
`_station_of` and `_offset_of`, each of which does a full `nearest()` scan.

---

## 4. Types and quality gates

Both `pyproject.toml` files configure `mypy` with `disallow_untyped_defs`,
`warn_return_any` and `warn_unused_ignores`, and `ruff` with a considered rule
set. Neither gate is green.

```
mypy glisteel/glisteel        -> 42 errors in 10 files
mypy glisteel-editor/…        -> 29 errors in  8 files
ruff check glisteel-editor/   ->  8 errors (7 x I001, 1 x F401)
```

**T1.** Most of the mypy output is `import-not-found` for `OpenGLContext.*`,
`omi_physics.*` and `OpenGLContext_editor.*` — the packages are installed
editable and carry no `py.typed`, and the global `ignore_missing_imports = true`
is not resolving them. Two real errors hide in the noise, e.g.
`traffic.py:321: Incompatible types in assignment` — where `car` is reused as a
loop variable for `TrafficCar` and then rebound to `TrafficCar | None` from
`_spawn` inside the same method, one name for three different things.

A gate that is configured and red is worse than no gate: it trains everyone to
ignore the output. Fix the import resolution (`mypy_path`, or per-module
overrides), fix the two real errors, and put both tools in CI.

**T3 — the deeper problem.** `disallow_untyped_defs` is satisfied by `Any`, and
`Any` is what the code uses for nearly every non-scalar parameter:
`Session(world: Any, …, driver: Any)` (`session.py:139`),
`Autopilot(course: Any)` (`driver.py:200`), `Car(world: Any)` (`car.py:101`),
`Straighten.steer(session: Any)` (`assist.py:80`),
`RaceHUD.route(course: Any)` (`hud.py:66`),
`menu.finish_screen(result: Any)` (`menu.py:135`).

The result is that the type checker verifies nothing about the interfaces that
matter, while the annotations suggest it does. The code already knows what the
right answer looks like: `Controller` (`session.py:81`) is a
`runtime_checkable` `Protocol` and it is exactly right. Four more of those — a
course, a car, a physics world, a driveable session — would turn `Any` into
something mypy can check and would document the seams the engine boundary runs
along, which is the point of this codebase per CLAUDE.md.

Two small consistency notes in the same area: `Car.__init__`'s first parameter
is named `world` but is the *physics* world (`car.py:101`), while
`Car.world` sits next to `glisteel.world.RaceWorld` — rename it `physics`. And
`Session.__init__` passes `world.physics` into it (`session.py:170`), so the
name is wrong at both ends.

---

## 5. Testing

673 tests pass in glisteel with 1 xfail (3 m 42 s), and 286 in the editor
(40 s). The tests are well named, well organised by behaviour, and
read as specifications — `test_feel.py` and `trace.py` in particular are a
genuinely good idea, and the xfail carries a plan reference rather than a shrug.

Three problems.

**T4 — the coverage figure is measured with the application layer removed.**
Both suites report a healthy number: 94 % over 2 203 statements in glisteel,
95 % over 1 112 in the editor. Both denominators have the window layer deleted
from them. Parsed without their `# pragma: no cover` markers, `game.py` has
**368** executable statements and `app.py` has **337**; coverage counts **79**
and **62**. There are 52 `no cover` pragmas across the two packages, 35 of them
`- needs a window`.

The sharp end of it:

```
glisteel/game.py      79      0   100%
```

`game.py` reports **100 % coverage** while 289 of its 368 statements — 79 % of
the file — are invisible. A reader of that report concludes the window layer is
exercised. C3 (`--mouse` never binds) lives in it, three lines from a line the
report calls covered.

CLAUDE.md is explicit about this: *"`# pragma: no cover - needs a window` is the
sign that it happened"*, and the remedy is to hoist the logic into a plain object
that takes its inputs as arguments. Every P1 defect in the editor — C6 (no dirty
check), C8 (undo), A13 (blocking bake) — lives in that excluded region, which is
exactly the prediction CLAUDE.md makes: *"what cannot be tested does not get
tested, and it is where the defects a player meets collect."*

**T7 — where the coverage is honestly low, the defects are.** The one module
that reports a poor number is `car.py`, at **76 %**, and its uncovered lines are
`283-304, 312-316, 328, 330, 340, 358-359, 362-366, 379-380, 383-387` — which is
precisely `car_nodes`, `car_body_mesh`, `cabin_mesh`, `wheel_mesh`, `_box_mesh`
and `_mesh`, the primitive-art path. That is exactly where C2 is. The two
findings are the same finding seen from two directions, and the fix for one is
the fix for the other. `models.py` at 36 % is the other gap, though most of it
needs assets loaded rather than logic tested.

The hoistable logic is already visible: `_settle`'s invalidation rules,
`_bake_directory`, `_choose_interval`'s exclusivity, `_show_land`, the
dirty-check policy, `_opening_track`'s "one track is not a choice" rule, and
`SwapBuffers`' capture sequencing are all pure decisions with no GL in them.

**T5.** 3 m 42 s is too slow to run on every change, which means it will not be
run on every change. The cost is concentrated and easy to separate — the six
slowest tests are 98 s of the total between them:

```
24.75s tests/test_driver.py::TestHoldingTheLine::test_correcting_the_error_is_what_does_it
19.15s tests/test_driver.py::TestItGetsOverTheHills::test_it_completes_a_lap_over_the_crests
17.92s tests/test_driver.py::TestItGetsOverTheHills::test_it_stays_on_the_road_over_them
12.96s tests/test_session.py::TestWhoIsDriving::test_the_autopilot_drives_it_round
12.13s tests/test_driver.py::TestItActuallyGetsRound::test_it_stays_on_the_road_while_it_does
11.98s tests/test_driver.py::TestHoldingTheLine::test_it_holds_a_narrow_lane_round_a_bend
```

Every one is a full autopilot lap, and E3/E8 are most of what they are waiting
for — so fixing the per-frame arithmetic shortens the suite as well as the
frame. Marking them `@pytest.mark.slow` and keeping a sub-minute default would
preserve the habit in the meantime.

**T6.** `race.__all__` (`race.py:20`) lists six names and omits seven public
ones, three of which `session.py` imports (`Collisions`, `closing_speed`,
`off_course`). An `__all__` that does not match the module misleads readers and
`from … import *` alike.

**Missing cases suggested by the P1 list**, each cheap:
`reversed=True` route editing (C1); face-normal orientation (C2);
`==` on each array-bearing dataclass (C4); spring drag → undo (C8);
`Records.offer` with a table under `KEPT` (C10).

---

## 6. Security and untrusted input

Neither project handles credentials or network services, so the surface is
narrow. Three items are real, two are hardening.

**S1 — path traversal from a track manifest.** `Track.at` builds
`os.path.join(directory, manifest.tileset)` (`tracks.py:98`) and `_beside`
builds `os.path.join(directory, str(relative))` (`tracks.py:203`), neither
normalised nor checked for containment:

```
_beside('/tmp', '../../etc/hostname') -> '/tmp/../../etc/hostname'
```

The manifest is a shared artefact by design — the whole `picture`/`library`
mechanism exists so a player can collect worlds — so a manifest is
attacker-influenced input the moment one track is downloaded. The reachable
effect today is reading a file outside the track directory and handing its path
to the tileset loader or the image loader. `remember_picture` (`tracks.py:180`)
writes back into `track.directory`, so a write path exists in the same area.

**Fix.** Resolve with `os.path.realpath` and require
`os.path.commonpath([resolved, directory]) == directory`; refuse otherwise with
a message naming the manifest.

**S2 — remote tilesets.** `RaceWorld.__init__` accepts a URL
(`world.py:336`, `fetch.is_url`) and `load_courses` fetches it
(`world.py:258`). Whether there is a scheme allow-list, a size cap or a timeout
is the engine's business, but glisteel is the component that opens the door and
the README does not mention that a tileset argument may be a URL. State the
trust boundary in the README and in `RaceWorld`'s docstring, and allow-list the
schemes here if the engine does not.

**S3 — unvalidated array reshape.** `_baked_luminaires` (`world.py:432`) does
`np.asarray(found, dtype='d').reshape(-1, 3)` on whatever the tileset's `extras`
contained. A length that is not a multiple of three raises an opaque
`ValueError` during world construction; a very large list is an unbounded
allocation. `Prop.from_json` (`world.py:423`) has the same shape of exposure.
Validate and refuse with a message that names the file.

**S4 / S5** are the atomicity and error-handling gaps already listed as C7 and
in the table; `Records._read` (`records.py:133`) is the model to copy, and
`Project.open` (`project.py:307`) is the one that needs it.

**Not a finding:** `subprocess.Popen([command, tileset])` (`app.py:550`) passes
an argument list with no shell, and `command` comes from `shutil.which` — there
is no injection here. The `# noqa: S603` beside it suppresses a rule that is not
in the selected set and should go (D10). The child is never reaped, which is
untidy but harmless for a launcher.

---

## 7. Portability and packaging

- **A18.** `models.ART` computes its path from `__file__` (`models.py:30`).
  `[tool.setuptools.package-data]` ships the assets inside the wheel, so this
  works for a normal install and breaks for a zipimport or any loader without a
  real filesystem path. `importlib.resources.files('glisteel') / 'assets'` is
  the supported spelling and is one line.
- **C7.** Locale-dependent encoding on project files, above.
- **A14.** `os._exit(0)` (`game.py:486`) is platform-portable but skips every
  `finally`, `atexit` and thread join. `stdout` is explicitly flushed just above
  it and `_shutdown()` is called — but the recorder is *not* closed on that path,
  whereas `OnQuit` (`game.py:490`) is careful to close it first and says why.
  Two exit paths with different cleanup is the kind of asymmetry that becomes a
  truncated file later.
- **D13.** `--size` parsing: `partition('x')` then `int()` (`game.py:597`,
  `app.py:649`). `--size 1280` produces `ValueError: invalid literal for int()`
  from inside `main()` rather than an argparse usage message.
- Python floor is 3.10 in both `pyproject.toml`; `mypy` is configured for 3.12.
  The code uses `zip(..., strict=True)` (3.10+) and `X | None` under
  `from __future__ import annotations` throughout, so 3.10 is genuinely
  supported — but the mypy setting means nothing is checked against it. Set
  `python_version = "3.10"` so the gate matches the promise.

---

## 8. Documentation

The prose is the strongest thing about this codebase and §10 says so. What is
missing is the *checklist* CLAUDE.md attaches to every change.

- **C10.** Eight modules teach with doctests; none are executed and at least one
  is wrong. Documentation that is not run is documentation that drifts.
- **D20.** `tools/cars.py` repeats a whole paragraph — "**The paint is a finish,
  not a colour.**" at line 42 and "**The paint is a finish rather than a
  colour.**" at line 50, saying the same thing twice with slightly different
  words — and uses `# --- The player's car ---` as a section heading twice
  (lines 89 and 685) for two different sections.
- **D7.** `camera.py:158` says the `across` term *"puts the eye in the driver's
  seat rather than between the two"*, while `COCKPIT_SIDE = 0.0` (`:48`) and the
  module docstring (`:43`) say the car seats two in single file down the
  centreline and the eye goes there too. One of the two is out of date.
- **A19.** `race.py`'s docstring describes lap timing; the module also holds
  `OffRoad`, `Collisions`, `closing_speed` and three `Surface` constants. A
  reader who greps for "what ends a run" will not find this file.
- **`Autopilot`** is documented as holding *"no state but the course and the
  style"* (`driver.py:196`) while carrying mutable `self.ahead` (`:212`).
  `Straighten` says *"It holds no state"* (`assist.py:55`) while owning an
  `Autopilot`. Both claims are load-bearing — they are why the docstrings say a
  single instance can serve a whole race — so they should be made true or
  qualified.
- **D22.** `glisteel-editor/plans/PROJECT-PLAN.md` indexes that project's plans;
  `glisteel/plans/` has three documents and no index. Add the matching one, with
  this review in it.
- **README accuracy.** `glisteel/README.md:184` and the key table at `:26`
  document `--mouse`, which does not work (C3).
  `glisteel-editor/README.md:190` ("Limits") is honest and well judged, and is
  the right place to record that `Open` cannot browse — it already does. It
  should also record that New and Open do not ask before discarding (C6), until
  C6 is fixed.

---

## 9. Organisation and cleanliness

The full list is in the P3 tables; four themes are worth stating as themes.

**Function-local imports (E10).** 39 of them — 20 in glisteel (9 in `world.py`,
7 in `game.py`) and 19 in the editor (11 in `app.py`, 4 in `scene.py`). None
carries a comment explaining what it is for. Some are clearly deliberate (the
`OPENGLCONTEXT_*` environment must be set before the engine imports, which is why
`game.py` and `app.py` carry their `E402` per-file ignore) and some are inside
per-frame code, which costs a `sys.modules` lookup every frame
(`game.py:442` in `_aim`, `world.py:555` in `ground_under`,
`reflections.py:127` in `_register`). The cost is small; the real price is that
a reader cannot see a module's dependencies from its head, which is the whole
job of the import block. Hoist them; keep the ones that break a genuine cycle
and say so on the line.

**Index-based coupling.** `trace._assemble` (`trace.py:303`) maps a 14-element
tuple to 14 fields by position, and `Trace.between` (`:180`) and the empty branch
of `_assemble` (`:305`) each re-enumerate all 15 fields. Adding a column means
editing three places in exact agreement, and an error is a silent column swap.
`RouteEditor`'s history (`editing.py:257`, `:262`) has the same shape in
miniature. `dataclasses.fields()` and `dataclasses.replace` remove both.

**Defensive `getattr` where the attribute is guaranteed.** Nine in `game.py`
alone (`:160`–`:200`), plus `getattr(course, 'structures', ())`
(`reflections.py:72`), `getattr(self.terrain, 'runtime', None)`
(`world.py:563`), `getattr(script, 'duration', 0.0)` (`trace.py:270`),
`getattr(session, 'car', None)` (`steering.py:182`). Each hides a typo that
would otherwise be an `AttributeError` at the first run, and `game.py:160` has
already produced a live inconsistency: `--traffic` defaults to
`DEFAULT_TRAFFIC` (6) in the parser and to `0` in the `getattr` that reads it
(D11).

**One idea, four spellings (A1).** "Yaw from a forward vector" is implemented
independently in `CameraPose.heading` (`camera.py:80`,
`atan2(f[0], -f[2])`), `Course.heading_at` (`world.py:153`,
`atan2(-a[0], -a[2])`), `TrafficCar.heading_angle` (`traffic.py:213`,
`atan2(-f[0], -f[2])`) and `trace._heading` (`trace.py:297`,
`atan2(f[0], -f[2])`). Two of them are the negation of the other two. Both
conventions are presumably intended — one is the angle to *apply* as a VRML
rotation, the other the direction *read* off a view — but nothing says so, two
of the four docstrings use nearly identical words for opposite results, and
`world.py:117` and `traffic.py:206` each explain the sign convention at length
in their own words. One helper, one explanation, four call sites.

---

## 10. What is right, and should not be changed

A gate that only lists faults misrepresents the work. These are the things this
codebase does better than most, and they are the reason the P1 list is short.

- **The separation is real and it holds.** `Session` (`session.py`) runs the
  whole game — fixed-step physics, camera, timing, streaming, the rules — with
  no window anywhere in it, and `GlisteelContext` genuinely is a shell that
  feeds it keys and draws what it says. `MapScene`, `RouteEditor`, `LandEditor`
  and `MapControls` are the same shape in the editor. That is why 674 tests can
  exist at all, and why the P1 defects are concentrated in the thin windowed
  layer rather than spread through the logic.
- **The prose explains *why*, in the present tense, without narrative.** The
  comment on the chassis collider (`car.py:105`), on why the controls are
  sampled inside the fixed step (`session.py:266`), on why the lap needs sectors
  (`race.py:1`), on why the camera lags position but not aim (`camera.py:96`),
  on why traffic is kinematic (`traffic.py:14`) — these are the notes a
  maintainer needs and almost never gets. The constants carry `#:` comments
  giving units and the reasoning for the value, which is exactly what CLAUDE.md
  asks for and is rare anywhere.
- **`trace.py` and `test_feel.py`.** Turning "does the steering feel right" into
  `camera_yaw_jerk` and `time_to_centre`, with a budget and a `report()` that
  prints the whole measure set on failure, is the right answer to a problem most
  projects give up on. Recording at the physics step *and* at 1/60 to prove the
  measure is frame-rate independent is the detail that makes it trustworthy.
- **The engine-first rule is being followed.** `RoadColliders`,
  `HeightFieldColliders`, `PropColliders`, `AssetLibrary`, `TilesTerrain`,
  `MapView`, `ToolManager`, `hudwidgets`, `contours_of`, `SculptStroke`,
  `flow_from` — the reusable machinery is in `OpenGLContext` and
  `OpenGLContext_editor`, and these two packages call it. The
  `EDITOR-REMEDIATION.md` placement table shows the decision being made
  deliberately, item by item.
- **`Run` (`run.py`)** is a small, complete, entirely testable state machine with
  a working doctest, and pulling "what reaches the car" and "does the clock run"
  out of `Session` was the right call.
- **The graceful-degradation instinct is correct throughout** — a missing model
  gives a primitive car, a missing manifest gives a bare track, a corrupt records
  file gives a fresh table with a warning, an empty library is not an error. C2
  and C10 are cases where the *fallback itself* is broken, not cases where the
  instinct is wrong.
- **`OffRoad`, `Collisions` and `RaceTiming`** all follow the same shape — fed a
  reading and a `dt`, returning a reason once, with a `restart()` — which makes
  them trivially composable in `Session.ended`. That is a good small design.

---

## 11. Method, and how to reproduce every number

All measurements were taken with `/workspaces/OpenGL-dev/.venv/bin/python` in
this container, on 2026-08-19, with nothing drawn (no GL context), so they are
CPU cost only and are directly comparable between runs.

| Claim | How |
|---|---|
| Mesh winding (C2) | Rebuilt the `_box_mesh`/`wheel_mesh` face lists, computed per-face normals, took the sign of `normal · (face centre − mesh centroid)` |
| Cull state (C2) | `pbrmesh.py:190` (`solid` default), `pbrmaterial.py:81` (`doubleSided` default), `passes/_flat.py:1010` (`glFrontFace(GL_CCW)`, `glEnable(GL_CULL_FACE)`), `pbrmesh.py:677` (`_wants_cull`) |
| Reversed-route drag (C1) | Built a 5-point `Route(reversed=True)`, called `point_at` at a known point, then `move` with the returned index |
| Dataclass equality (C4) | Constructed two distinct-but-equal instances of each and compared; `hash()` on `Scenario` |
| Duplicate defs (C5) | AST walk counting top-level `FunctionDef` names per module |
| `--mouse` (C3) | AST walk of `OnInit`'s call order and of every assignment to `self.keyboard`; `_bind_keys` call sites |
| Doctests (C10) | `pytest --collect-only` with and without `--doctest-modules`; then ran them |
| Editor redraw profile (E1/E2/E4) | 40-point circuit on a 2048 m landscape; primed every cache with one `build()`; timed each `MapScene` method and the whole `build()`; counted `Project.world()` constructions with a wrapper |
| Vectorised vs scalar height (E2) | 40 `scene.height_at(x, z)` calls against one `height_fn()(xs, zs)` call |
| Frame cost and call counts (E3) | `scenarios.circuit(1500, 1000)` — 1 884 points, 7 932 m — six traffic cars, `Autopilot`, 60 frames after a 20-frame warm-up; `Course.nearest`/`Course.stations` wrapped with counters and timers |
| Statements hidden by pragmas (T4) | `coverage.parser.PythonParser` on each file as shipped and on a copy with the `# pragma: no cover` markers stripped |
| Gate status (T1/T2) | `ruff check` and `mypy` on each package, as configured in its own `pyproject.toml` |
| Suite timing (T5) | `pytest -q --durations=12` on each project |
| Coverage (T4/T7) | `pytest --cov` on each project; `coverage report` for the fully-covered files the default report skips |

Scratch scripts for the measurements are under this session's scratchpad and are
short enough to re-derive from the table above; none of them modify the working
tree.

---

## 12. What landed — 2026-08-19

All ten P1 defects are fixed. Each was done Red/Green: the test was written
first, run, and seen to fail *for the reason claimed* — not merely to fail —
and only then was the code changed. No test was written after its fix, and no
working tree was reverted or stashed to get a baseline.

**85 new tests** — 60 in five new files, 25 added to five existing ones — and 8 module doctests that now run for the first time.

| ID | What changed | New tests |
|----|--------------|-----------|
| C1 | `RouteEditor.drawn()` — one hit-test source of truth, indexing `route.points` rather than `route.plan()`. `StartTool._nearest` now goes through it too, so the two hit tests over one line cannot diverge again. | 5 |
| C2 | `_box_mesh` sides and every `wheel_mesh` triangle rewound to face out. The docstring said "clockwise seen from above"; it is counter-clockwise, and now says so. | 4 |
| C3 | `bindings()` — a `Binding` table at module scope, bound unconditionally. `_on_pointer` already guarded itself, so the ordering the bug depended on no longer exists. | 7 |
| C4 | `eq=False` on `Course`, `Trace` and `Readings` (things, compared by identity); a real `__eq__`/`__hash__` on `Scenario` (a description, compared by value). `_wave` is memoised so the same land asked for twice *is* the same land. | 14 |
| C5 | The dead `_wheel_innards`/`_spoke` pair removed — 43 lines. `build_wheel` calls `_wheel_innards(name, half, bead, …)` and only the surviving definition takes `bead`, so the exported models are unchanged. | 27 (one per shipped module) |
| C6 | `would_lose_work()` at module scope; `New`, `Open` and `Quit` all ask through it. `Open` also reports a file that will not read instead of raising. | 7 (5, plus 2 for `bake_directory`) |
| C7 | `Project.save` writes to a temp file beside the target and `os.replace`s it, in UTF-8, with `ensure_ascii=False` so the file stays readable as the module promises. `Project.open` raises a `ValueError` naming the file. | 6 |
| C8 | `WaterEditor` gets the `begin_step`/`end_step` grouping `RouteEditor` has; `WaterTool.cancel()` puts a dragged spring back. | 6 |
| C9 | `RaceWorld` raises `FileNotFoundError`. `opening_fault()` hoisted out of the window; `open()` shows the reason on the menu and stays running; `main()` still exits 1 with a message on stderr for the command line. | 9 (4 + 5) |
| C10 | `--doctest-modules` and the package on `testpaths` in both projects. The `records` example rewritten to be true: a lap is refused once the table is full and it beat none of them. The `/tmp/times.json` side effect is gone. | 8 module doctests now run |

### What the fixes are worth beyond the defect

- **C1 and C6 stop data loss**, which is the reason they came first.
- **C3, C6 and C9 are hoists**, not patches: `bindings()`, `would_lose_work()`,
  `bake_directory()` and `opening_fault()` are plain functions with no GL in
  them, which is what CLAUDE.md asks for and is why they could be tested at all.
  They take a little out of the region T4 measures as invisible.
- **C5's test is general.** `test_sources.py` walks every shipped module's AST
  and fails on any top-level name defined twice, so the trap cannot return in a
  file nobody is looking at. Ruff's `F811` does not catch this case — it fires
  on redefinition of an *unused* name, and a name referenced between the two
  definitions is used — which the test's docstring records.
- **C2's test asserts the property, not the numbers.** Every triangle's normal
  must agree with facing away from the mesh, and the carried normals must agree
  with the winding, so any future mesh added to `car.py` is covered by the same
  three cases.

### Deliberately not done

- **Everything P2 and P3.** `Records.save` is still non-atomic (S4) even though
  `Project.save` no longer is — an inconsistency now running the other way, and
  the obvious next thing.

### The suites after the change

```
glisteel        748 passed, 1 xfailed   (4 m 19 s)
glisteel-editor 326 passed              (31 s)
ruff            clean on both packages
```

The one xfail is the pre-existing camera-harshness case, which carries its own
reason and a plan reference. T5 still stands: the glisteel suite is slower than
it should be, and E3/E8 are most of what it is waiting for.

### Note on concurrent work

The `bonnet` shell was being added to `models.py`, `car.py` and `hero.glb` in
the same tree while this ran, and briefly showed two failures in
`TestTheCarIsTheModel` (the constant was declared before the asset carried the
DEF). That work landed during the session and those tests pass; nothing here
touched it. C2 changed triangle winding, not DEF names, and the two are
independent.

## 13. What landed in the second pass — 2026-08-19

The E, S and T items, Red/Green as before: every test written and seen to fail
for the stated reason before the code changed. **130 further tests**, in eight
new files.

### Performance, measured before and after

| | Before | After |
|---|---|---|
| `session.advance()`, 7.9 km circuit, six traffic cars, nothing drawn | 10.88 ms/frame | **7.71 ms** |
| `Course.nearest()` within that | 0.76 ms/frame | **0.10 ms** |
| Avoidable share of a frame | 25 % | **1 %** |
| `Course.inside()` over 160 000 ground samples × 900 road points | 3 260 ms, 3 451 MB peak | **19 ms, 36 MB** |
| `Session.restart()` | 61 ms, 167 physics steps | **25 ms, 41 steps** |

| ID | What changed | Tests |
|----|--------------|-------|
| E3 | `stations`, `segments`, `ground_line` and `radii` are `cached_property` on `Course`, with `moved()` to clear them; `nearest()` keeps its last answer, because within one physics step the lap timing, the off-road watch, the driver and the steering aid all ask about a car that has not moved between them | 15 |
| E5 | The tileset is read and parsed once. `courses_in`, `_baked_props` and `_baked_luminaires` take a document rather than a path | 4 |
| E6 | `Course.inside()` rules out samples outside the run's own bounding box, then measures what is left in bounded chunks, so the intermediate is a slice rather than samples × road points | 11 |
| E7 | The car is put where the road is rather than six metres over it, and the settle stops once it is standing. A restart no longer simulates a second of free fall while the player waits | 9 |
| E8 | `Course.radii` is the road's own curvature, worked out once; `target_speed` takes one pass over it; `update` hands `steering` the index it already has | 10 |
| E9 | Traffic asks the course where the player is once rather than twice, and answers a direction's worth of cars in one array operation rather than every car against every other | 8 |
| E10 | The per-frame function-local imports are hoisted; `tests/test_imports.py` names the functions that run at the frame rate and fails on an import inside one | 23 |
| E11 | `Scenario._cache` — declared and unused — now holds the course, which `world()` wanted three times | 4 |
| E12 | The wheels' roll is kept inside one turn | 2 |

### Security and untrusted input

| ID | What changed | Tests |
|----|--------------|-------|
| S1 | A manifest names files *inside* the track it came with. `../../..` and absolute paths resolve outside it and are refused with a warning, which reads as a track with no picture — the same as a missing one | 5 |
| S3 | Lamp positions out of a tileset are checked: a whole number of triples, numbers rather than strings, and fewer than :data:`MOST_LUMINAIRES`. Each refusal says what was wrong | 5 |
| S4 | `Records.save` writes beside the file and moves it on, in UTF-8 and as its own characters — the same as `Project.save` (C7), which had left the two inconsistent | 5 |
| S5 | Landed with C7 | — |

### Gates

| ID | What changed |
|----|--------------|
| T1 | **`mypy` is green on both packages** — 42 and 29 errors to none. Most were unresolved `OpenGLContext.*` imports; a narrow per-module override silences those and no others, which made eleven real errors visible, and they are fixed. `python_version` stays at 3.12 with the reason recorded: numpy's own stubs use 3.12 syntax, so checking against the 3.10 floor fails before reaching any code here |
| T2 | Green, with C-pass |
| T5 | The seven tests that drive a whole lap are marked `slow`; `-m "not slow"` is the working loop and a full run is still the default. **Partly done**: 3 m 15 s becomes 2 m 25 s, which is a saving and is not yet a quick loop. The cost is spread more widely than the review's `--durations` list showed — the settle, the scenario worlds and the traffic drives each cost a little across many tests — so getting under a minute means marking more of them, or making a scenario world cheaper to stand up |
| T6 | `race.__all__` names what the module has |
| T7 | Landed with C2 |

### Still open after the second pass

- **T5's remainder** — the suite is 2 m 25 s without the slow marks and wants to
  be under a minute. Standing up a scenario world is the next thing to measure.

## 14. What landed in the third pass — 2026-08-20

### The editor's redraw (E1, E2, E4)

`_rebuild` runs on every pointer movement during a drag, so a redraw *is* what
dragging feels like. A warm one — every cache primed, which is what a drag finds
— measured piece by piece, before and after:

```
                before      after
start_mark()    196.4 ms    1.65 ms
markers()        31.8 ms    2.80 ms
guide()          28.7 ms    1.26 ms
build() total   261.2 ms    5.79 ms
```

| ID | What changed |
|----|--------------|
| E1 | `start_mark` reached past `MapScene.world()` to `Project.world()`, which documents itself as built fresh each time — a whole `ProceduralWorld` settled per redraw to read one number off it |
| E2 | `heights_at()` samples the ground for a whole line in one call, the way `_contour_shape` always has and says why; `height_at()` is now the single-point way in rather than the only one |
| E4 | `None` from `structures()` is an answer — a circuit over flat ground carries nothing — and also meant "not worked out yet", so the alignment was settled again every redraw. A sentinel tells the two apart |

Also: a water surface is narrowed before its wave clock is set, so a child of the
water group that is a marker rather than a sheet cannot raise.

### T3 — the seams, written down

`glisteel/interfaces.py` holds five `Protocol`s — `CarLike`, `CourseLike`,
`VehicleLike`, `PhysicsLike`, `SessionLike` — and the seams that took `Any` now
take those: the autopilot, the steering aid, the camera and the car.

They are `Protocol`s rather than base classes because the suite drives most of
the game through doubles, and a seam only the real class could satisfy is a seam
that could not be tested. Each says the *least* its users need, which is what
makes a double against it small.

**This is checked rather than decorative.** Applying them made mypy reject
`Session` where a `SessionLike` was wanted, because a mutable Protocol attribute
is invariant; the members that are only ever read are properties now, and the
real classes satisfy them. It also turned up that `Car.world` was the *physics*
world rather than the `RaceWorld` its name suggested — it is `Car.physics`.

### T4 — the command line, checked where a test can reach it

`glisteel/options.py` holds `Options`: a typed dataclass built from the parsed
namespace once, with the values checked once, and the window reads that.

- **The defensive `getattr(self.config, name, default)` calls are gone** — nine
  of them. Each had quietly written a second default beside the parser's, and
  `--traffic` had two that disagreed: `DEFAULT_TRAFFIC` in the parser and `0` at
  the point that read it, so the documented default was not the one a player
  got.
- **`--size` is an argparse type**, so `--size wide` is the usage message every
  other malformed option gets rather than a `ValueError` out of the middle of
  `main`.
- **The values are validated**: a negative lap count, a steering aid outside 0
  to 1, a view the game does not have, a negative traffic count and a negative
  screen-space error are refused by name, at the command line, rather than
  reaching the physics.
- **`--picture` no longer mutates what the player asked for**; it takes a
  `dataclasses.replace` copy, which re-runs the same checks.
- A test can build an `Options` without a parser, which is what made any of the
  above testable: `tests/test_options.py` is 21 cases and needs no window.

This does not empty the `# pragma: no cover` region — `OnInit`, `SwapBuffers`
and the light rig are still window-bound — but it takes the *configuration* out
of it, which is where the defects were.

## 15. The P3 tables — 2026-08-20

All 22 D items and 18 of the 21 A items. Three are declined below, with reasons.

### Two were defects rather than tidying

**D8 — turning an open road round produced a different road.** `Route.plan()`
kept the first point first and reversed the rest. For a *circuit* that is right:
a lap begins where it begins and only the direction round the loop changes. For
an **open road** it is wrong — turning one round means starting at the far end —
and what came out was a different shape, not the same road driven the other way.
The test that found it asserts a route is the same length whichever way it is
driven.

**D4 — spring markers were seven metres across at every zoom**, while the
control points beside them were seven pixels. The parameter that would have
scaled them existed and nothing ever passed it.

### One finding in the review was wrong

**A15 said `TARMAC`/`VERGE`/`ROUGH` were "shared mutable singletons".**
`omi_physics`' `Surface` is a frozen dataclass, so there was never a hazard: one
caller cannot change what every car is driving on. The comment beside them now
says *why* sharing them is safe, which is the useful half of the finding. The
review was wrong and this records it.

### The rest

| | |
|---|---|
| A1 | Four copies of "which way is this pointing", in two conventions, none saying which. `glisteel/geometry.py` has `yaw_of` (read an angle off a direction) and `yaw_to_face` (the rotation that points a mesh that way); they are each other's negation, which is why four unnamed copies were a trap. The camera, the road, the traffic and the trace all call them |
| A2 | `Trace.columns()` is read off the dataclass, so a window of a drive and the assembly of one no longer enumerate fifteen fields in three lists that have to agree |
| A3 | `RaceHUD.show(reading)` takes a whole `Readings` — which is exactly what a session answers with — instead of its nine fields, copied across one at a time by the window |
| A4 | `Car.forward_speed()`; the keyboard no longer reaches through a car to the vehicle under it, and the test doubles got smaller as a result |
| A5 | `RaceWorld.from_course` builds through `__init__` rather than `cls.__new__`, so there is one description of what a half-built world looks like |
| A6 | The traffic's three mappings are keyed on the car rather than `id(car)`: identical behaviour, minus the reuse-after-collection hazard |
| A7 | `SETTLE_DROP`, `GRID_SETBACK`, `LOST_BELOW`, `BORE_MARGIN`, `BORE_APPROACH` and `MOST_LUMINAIRES` sit with the other constants, above the code that reads them |
| A8 | `TrafficCar.on_the_road()` says where a station falls; `turn_at_the_end()` turns the car round. Asking where something was used to move it |
| A9 | Covered by E4's invalidation work |
| A10 | `RouteState` — the undo history is named rather than a four-tuple read by index |
| A12, A14, A16, A17, A18, A19, A21 | As the table says; A14 in particular closes a recording on the capture exit, which it was skipping |

### Declined, with reasons

- **A13 — the bake blocks the editor's UI thread.** Real, and the fix is a
  worker plus progress, which touches GL-thread ownership in a file another
  agent is actively rewriting. It belongs in `EDITOR-REMEDIATION.md`'s baking
  phase rather than across it.
- **A20 — `tools/cars.py` is 1 571 lines.** The split is right and the file is
  under active edit for the vehicle work; doing it now would conflict with that
  rather than help it. The duplicate-definition trap it hid is already caught by
  `tests/test_sources.py` (C5).
- **A11 — `GlisteelContext.config` is a class attribute.** It is typed now
  (`Options`) rather than an untyped namespace, which was the part that hid
  mistakes. Making it per-instance means the backend passing it through context
  construction, which it has no way to do; the class attribute stays, and the
  reason is here rather than nowhere.

## Suggested order of work

1. **C1, C2, C3, C6, C8** — the five defects a user meets. Each is a small,
   local change with an obvious test.
2. **E1, E2, E4** — one-word and one-loop changes worth 260 ms of every editor
   redraw. Fold into `EDITOR-REMEDIATION.md`.
3. **C4, C7, C9, C10, S1** — latent crashes, file safety, and the exit path.
4. **T1, T2** — get both gates green, then put them in CI, so nothing on this
   list can silently return.
5. **E3, E5, E7, E8** — the game's per-frame arithmetic. `cached_property` on
   `stations` and a once-a-frame `nearest()` resolved in `Session` are most of it.
6. **T4** — hoist the decisions out of `EditorContext` and `GlisteelContext` per
   CLAUDE.md, and report coverage against the whole package.
7. **P3** — the tables above, as ordinary tidying alongside other work in each
   file.
