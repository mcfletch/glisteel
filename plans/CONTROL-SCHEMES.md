# Ways of driving it: control schemes to build and to try

**Status:** experiments, 2026-08-20. The switch (§9.1) is built and every
scheme reached through it is a **candidate, not a decision**: what the game
finally offers is settled by the measurements of §8 and by driving them, and a
scheme that does not earn its place comes out again. §2 is the shape the rest is
written in; §3 to §5 are the options; §8 is how they are judged and §10 is what
still needs deciding.

Nothing here is to be read as a commitment to ship a mode. The point of building
the switch first, rather than building one scheme properly, is that the cost of
being wrong about any of them is deleting a class.

Someone new to the game arrives at a keyboard, holds a key, and puts the car in
the trees. This is a plan for the ways of driving that would not do that, for
which of them belong to `glisteel` and which belong to the engine underneath,
and for how the choice between them gets made from measurements rather than from
opinion.


## 1 What the controls ask of a driver now

The car is steered by a key that means **full lock**. `KeyboardWheel` winds a
wheel toward that lock at 0.9 of its travel a second and back to centre at 4.5,
and `VehicleTuning.steer_lock` closes the lock down with the square of the speed
(`steer_falloff_speed` is 10 m/s on this car). What the driver is holding is
therefore a *rate*, and where the car ends up across the road is that rate
integrated twice — once into a heading, once into a position. A player closing
that loop is doing it by eye, at 40 m/s, on a 7.2 m carriageway with trees 0.8 m
past the verge.

Three consequences, each measured:

- **A tap is a permanent change of direction.** The wheel centres, the car keeps
  the heading the tap bought, and it crosses the road at a constant rate. A
  0.3 s tap at 86 km/h leaves the car 7.0 m off the line and still going with the
  aid off — the width of the road, from the shortest input a player can give.
- **The aid that fixes it is a single scalar.** `Straighten` puts the car back on
  the line it was let go on, at `--assist` (0.55 by default), and it brings that
  same tap down to 0.4 m. It is doing the whole job of making the car placeable,
  and it is doing it *behind* a control that still means "lock".
- **The punishment is immediate.** Two and a half seconds off the carriageway
  ends the run (`race.PATIENCE`), and twice the road's width from the centreline
  ends it at once (`race.LOST`). A novice's first mistake is the end of the race.

Overtaking compounds all of it. The road is two lanes of 3.6 m
(`RoadProfile(lanes=2)`), so passing means the *oncoming* lane, and the game
does not currently answer the one question a driver needs before going there —
what is coming the other way. `Traffic.ahead_of` filters to a car's width so that
the other lane is excluded, which is right for following and leaves passing
unadvised.

None of this is a defect in the physics. It is a control interface that hands
the player an open loop and an aid bolted on behind it.


## 2 Three layers, not one setting

Everything below is a rearrangement of the same three questions, and keeping
them apart is what makes a mode cheap to add and a feature like mouse steering
available in every mode rather than in one.

| Layer | The question | Today |
|---|---|---|
| **Source** | what produces a number between −1 and 1 | `KeyboardWheel` (a key pair), `MouseWheel` (pointer across the window) |
| **Scheme** | what that number *means* to the car | always the steering lock |
| **Assists** | what the game adds to what the driver asked for | `Straighten`, at one strength |

A **source** is an axis and nothing else: a key pair that winds, a pointer
position, a pointer delta, a gamepad stick. It knows nothing about cars.

A **scheme** is the meaning: lock, or a position across the road, or a lane, or a
heading. A scheme that means a *position* closes the loop the player is closing
by eye today, and that single change is most of what "easy mode" is.

Everything a position means is measured against the **drivable zone** — see
§2.1, which is where the multi-lane case is settled.

An **assist** acts on what comes out of a scheme: trimming the line, capping the
speed to what the corner allows, keeping the tyres inside the grip they have.
Assists are independent of both other layers, so a preset is a set of them
rather than a mode of its own.

### 2.1 The road is a zone, not a line

A driver does not follow a line. What a road offers is a **width** with lanes
marked across it, and where the car sits in that width is a decision made and
remade — own lane, out towards the crown to see past what is in front, over to
the other side to pass, back again. Any scheme that steers by *where the car is*
needs that width written down, and a "drivable line" is the wrong abstraction
for it: it is the degenerate one-lane case, and it answers none of the questions
a multi-lane road asks.

`glisteel.zone.DrivableZone` is that width. It answers four things, and each is
a question a scheme asks every step:

- **how far out may the car go** — the carriageway's half-width drawn in by a
  margin, so a commanded line is never one with two wheels on the grass;
- **where are the lanes** — `centres()`, from the road's own lane count and lane
  width rather than from an assumption of two;
- **which lane is the car in** — `lane_at()`, from where it *is*, so a driver
  who has drifted across a line asks for the lane beside them rather than for
  wherever the last request left them, and `step()` for the one over;
- **which lanes have something coming** — `oncoming()` and `own_lanes()`. On a
  two-lane road every pass crosses the crown; on a four-lane road two of them
  are the driver's own and passing is an ordinary manoeuvre. The scheme's
  behaviour, the advice on the HUD and the risk of a pass are all different
  between those two roads, and nothing else in the game can tell them apart.

The lane count is real data: the baker writes the road's whole cross-section
into the tileset's `extras` (`openglcontext-editor`'s `RoadLayer`), so
`Course.lanes` reads what the world actually has and a four-lane world behaves
as one. A world that wrote no section is one lane each way, which is what a road
with a crown is.

**What is still one-lane-shaped**, and is work rather than a decision: `Course`
carries a single `carriageway_width` and one profile for the whole road, so a
road that gains a lane part-way along is a zone that changes with the station
and the zone is built once. Traffic keeps a fixed offset rather than a lane, and
`Traffic.ahead_of` filters by a car's width rather than by lane membership. Both
want doing before a multi-lane world is raced on, and neither blocks the
experiment on the two-lane roads that exist.

The current interface is one point in that space — key source, lock scheme, line
trim at 0.55 — and every option in §3 to §5 is another point, not a rewrite.

**Where the layers live** is §7. In short: the source layer, the drivable zone
and the schemes that only need a road to place a car on are generic vehicle
control and belong in the engine; what is glisteel's is *this* road with
something coming the other way, the race's own rules, and which combinations are
offered to a player.


## 3 The schemes

Each is named for what the driver does, since a name like "easy" tells a player
nothing about what their hands will be doing.

### 3.1 Lanes — *pick a lane, and the pedals are yours*

**What the driver does.** Throttle, brake, and a decision about when to pass.
Left and right are not steering: they are "take the lane to your left" and "take
the lane to your right". The car goes there and stays there, through the bends,
until asked for something else.

**How it is built.** The steering axis becomes a **lane request**. A path
controller — `driver.Autopilot.steering`, which already produces the steering
input that holds a car on a line at a lateral offset — is given the offset of the
requested lane and run at full strength. A tap moves the request one lane over; a
held key slides the request across continuously so the whole width of the road is
still reachable, which is what keeps it a road rather than a set of rails.

**Within the car's capability**, which is the interesting part. The controller
asks for a front-wheel angle and converts it through `steer_lock` at the current
speed, so when a corner is taken faster than the lock allows, the request
saturates and the car runs wide exactly as it would for a player. Two honest
answers to that, and they are different products:

- leave it, and the mode teaches braking for corners, because the car understeers
  off the road if the driver does not lift;
- add the corner speed limiter (§5.2), and the car is uncrashable on the road,
  which is the true novice mode and a good attract mode.

Offer both as a separate toggle rather than baking one in.

**It does the steering and nothing else — decided, 2026-08-20.** No check on
what is coming the other way, no hand on the pedals, no refusing a lane change
because the corner is close. A player can still crash it; what they cannot do is
crash it *because of the steering*. That settles §10's second question: the mode
advises, it does not enforce.

What "cleanly" means, in numbers: the held line travels to the new lane as a
**raised cosine**, so lateral speed is zero at both ends — the car leaves one
lane and arrives in the next rather than swerving and being caught — and the
duration comes from what the car can actually do at the speed it is doing. Never
more than `LANE_CHANGE_G` (2 m/s², a fifth of a g) sideways, and never more than
`LANE_CHANGE_SHARE` (a half) of `v² / turning_radius(v)`, which is what the
front wheels could ask for at that speed. The rest of the grip is left for
holding the new lane and for whatever the road is doing while the car crosses
it. At walking pace, where the lock buys a much smaller sideways push than it
does at eighty, the same change takes longer.

**Held, it takes the lanes one at a time** and stops where the road does. A lane
switch switches lanes: sliding the car to an arbitrary place across the road is
what `line` (§3.2) is for.

**What glisteel adds.** The lane to the left is the oncoming carriageway. What
is coming the other way — how far off, and how long the gap lasts at the current
closing speed — is worth telling the driver on the HUD, and is a new query on
`Traffic`, since `ahead_of` deliberately ignores the other lane. It is *advice*,
never a veto.

**Cost.** Small, and landed. The controller, the lane geometry and the assist
that holds a line all existed; what was new is the meaning of the key, the
manoeuvre, and the speed awareness.

**Risk.** A car that steers itself round corners is a car the player is not
driving. This mode has to keep the pedals genuinely load-bearing — corner entry
speed decides everything — or it is a video with a throttle. Which is what §5.2
and the caution signs are for: the road tells the driver how fast the corner is
worth, and it is then their job to be doing it.

### 3.2 Line — *steer the car's place on the road*

**What the driver does.** Steers, but the axis is *where across the road the car
is going*, not how far the wheels are turned. Full left is "cross to the left
edge at the mode's rate"; centre is "hold what you have".

**How it is built.** The same path controller as §3.1, with a continuous lateral
target instead of a discrete one: the axis sets the rate at which the held line
moves across the road, in metres per second, and the controller steers to
whatever line that is. Letting go holds the line — which is what `Straighten`
already does when the player's hands come off, so this makes the axis *agree*
with the aid instead of handing over to it at a deadzone.

**Why it is the most promising middle mode.** It removes the double integral, so
a tap is a small permanent *offset* rather than a permanent change of direction,
and it does that without taking the placing of the car away from the player. It
is also the mapping that makes an analog source shine: with the pointer, where
the pointer is across the window is where the car is across the road (§4.2).

**Cost.** Small, and largely shared with §3.1.

**Risk.** It is not how a car works, and a driver who knows cars will feel it —
there is no countersteer, and a slide is something the controller catches rather
than something the player does. That is the mode's whole point and also the
reason it must not be the only one on offer.

### 3.3 Wheel — *what ships now*

The axis is the lock; `Straighten` trims the line between the driver's inputs at
`--assist`. Keep it, name it, and let the trim be the difficulty dial it already
is (`0.0` hands the car back entirely, `1.0` holds the line for you).

The one change worth making here is to stop the aid being invisible: what it is
doing is a number the HUD can show, and a driver who can see the trim being
applied learns what their own hands are not doing.

### 3.4 Loose — *the car as the physics has it*

`--assist 0`, no scheme in the way, whatever source the player likes. The car is
already interesting at this level: a friction budget shared between driving and
cornering, load transfer through the springs, downforce over crests. What it
needs is not a change to the car but a source that can express small inputs
(§4), because with a key pair this mode is the one that put the car in the trees.

### 3.5 Chauffeur — *it drives, you interrupt*

`Autopilot` drives the car; any input from the player takes the controls
instantly, and it takes them back after a few seconds of nothing being asked for.

Cheap — the autopilot exists, `Session.driver` can be swapped mid-run — and
worth more than it looks: it is the attract mode for the front end, the way a
player is shown a line through a corner they keep missing, and an accessibility
answer for anyone who wants the world without the race. It is also the honest
place for `--autopilot` to end up as a *mode* rather than a command-line switch.

### 3.6 Point — *the pointer is the car*

A two-axis pointer scheme: across the window is the car's place across the road
(§3.2's mapping, absolute rather than rate), and up the window is throttle and
brake on one axis. One hand drives the whole car, with no keys at all.

**Why try it.** It is the only proposal here that also fixes the *pedals*, which
are as on/off as the steering is and get much less attention. It is a
five-minute mode on top of §3.2 once sources are separated, and it is the mode a
touchscreen or a tablet would want if the game ever meets one.

**Risk.** Absolute position across a window is a small amount of travel for a
delicate control, and the pointer wants capturing (§4.2) before this is fair.

### 3.7 Deliberately not proposed

- **Rewind.** The novice's real complaint is that a mistake ends the run, and
  rewinding time is how many games answer it. It needs a recorded history of the
  physics world and a way to re-enter it, which is a large engine feature and
  wants its own plan. The cheap part of the same answer — being forgiving about
  the verge — is §5.5.
- **Steering that cannot leave the road.** Rails make the road a corridor and the
  world a video. §3.1 with the limiter reaches the same place while leaving the
  driver something to do.
- **Tilt, touch and wheel hardware.** Nothing here is against them; they are
  sources, and they arrive free once §4 exists and a device is worth supporting.


## 4 Sources: where the number comes from

A source is available to every scheme. That is the whole reason for separating
them, and it is what makes "mouse steer" a toggle rather than a mode.

### 4.1 Keys

`KeyboardWheel` as it stands: a wheel that winds on at 0.9/s and centres at
4.5/s. Under a *lock* scheme those rates are the feel of the car; under the
schemes of §3.1 and §3.2 they are the feel of the *hand*, and want re-tuning —
crossing a 3.6 m lane should take about the second a real lane change does, not
the four seconds a full wind-on implies.

### 4.2 The pointer

`--mouse` exists and is a position: where the pointer is across the window is
where the wheel is, with 80 % of the half-width being full lock (`TRAVEL`) and a
1.8 power curve softening the middle (`CURVE`). It is the right idea and it is
unfinished. What it wants:

- **Capture.** The pointer leaves the window today, so steering stops at the
  screen edge, and a click outside the window takes the focus. The engine already
  has the machinery — `MovementMode.capturePointer`, GLFW's disabled cursor with
  raw motion, and `suspendPointerCapture()` for when an overlay wants the pointer
  back. Using it is the single biggest improvement available here.
- **Both mappings, chosen by the player.** Absolute (where it is across the
  window) is what makes §3.6 work and is the easier to learn; relative with
  recentring is what a captured pointer wants and what a player used to
  mouse-driven games will reach for.
- **Deadzone, curve and sensitivity as declared settings**, not constants, so
  they reach the settings screen (§7) and a saved profile.
- **A visible wheel.** The cockpit view poses the car's own steering wheel from
  the front-wheel angle, and every other view shows nothing. A small steering
  indicator on the HUD, in every view, is what makes a positional control
  learnable — and it is what shows the assist working in §3.3.
- **Keys and pointer together.** Today a key overrides the pointer while it is
  down and the wheel jumps back to the pointer's position on release. Under a
  *position* scheme (§3.2) the two can be blended instead, because both are
  saying the same kind of thing.

### 4.3 Gamepad — the missing source

There is no gamepad support anywhere in the workspace, and an analog stick is
the ordinary answer to "steering that feels analog". The engine's movement-modes
plan records this exactly: *"`InputState` is keys and pointer. Adding an axis
source is a change to the sampler, not to the modes."*

GLFW's joystick API is available through the backend the game already uses. The
work is: axes and buttons on `InputState`, a device-to-axis binding beside the
key bindings, deadzone and curve handling, and hot-plug. It is an **engine**
feature, it benefits every application in the workspace, and it is the one item
here that makes §3.4 pleasant instead of punishing.


## 5 Assists: independent, and the difficulty dial

Each is on or off (or a scalar) on its own; a preset (§6) is a set of them.

**5.1 Line trim.** `Straighten`, as it is. 0 to 1.

**5.2 Corner speed limiter.** The road knows its own radii (`Course.radii`) and
`Autopilot.target_speed` already turns the road ahead into the speed it allows.
As an assist it caps the throttle, or brakes, so the car arrives at a corner at a
speed the corner permits. Two useful strengths: *brake assist* (it will brake for
you but never limit what you ask for) and *limiter* (it will not let you arrive
too fast at all).

**Telling the driver came first — landed 2026-08-20.** Before anything takes the
pedals away, the road says what it wants: `Course.corner_speed` is what a bend's
own radius will hold and `Course.caution_speed` is what a sign before it advises,
both on the engine's one rule
(`OpenGLContext.scenegraph.road.corner_speed` / `advisory_speed`) so the number
the game uses and the number on the plate beside the road are the same number.
`Course.caution_ahead` reads the tightest thing within reach — further ahead the
faster the car is going — and under `lanes` the HUD says `SLOW TO 60` at more
than 20 km/h over it (`hud.OVER_CAUTION`). Whether a way of driving is advised at
all is the scheme's own `advises`, so a player steering the car themselves reads
the signs rather than a second copy of them on the screen.

**5.3 Grip-budget limiting.** `RaycastVehicle` gives each wheel its load, its
sideways slip and the grip of what it is on, and shares one friction budget
between driving and cornering. An assist can back the throttle or the brake off
before that budget is spent, which is a friction-circle limiter rather than a
slip-ratio traction control — there is no wheel-spin state in the model to
regulate, and the plan should not pretend otherwise. It is still worth having:
the fastest way for a novice to lose the car is to add throttle mid-corner.

**5.4 Understeer limiting.** Clamp the steering *demand* to the angle the front
tyres can still use at this speed and load, so sawing at the wheel does not
scrub the front away. Small, and it works under every scheme because it acts on
what leaves the scheme.

**5.5 Verge forgiveness.** The novice's cliff edge. Three dials, all in
`glisteel.race`: how long a car may be off the carriageway before the run ends
(`PATIENCE`, 2.5 s), how far off ends it at once (`LOST`), and how much grip the
verge has (`VERGE`). An easy preset lengthens the first, widens the second, and
may add a soft return — the line controller aiming back at the road while two
wheels are off it, which is a gentler version of what §3.1 does anyway.

**5.6 What is already in the car** and needs no new work: the brake that becomes
reverse below walking pace, the handbrake, the lock that falls with speed, and
the holding force that keeps a stopped car on a slope.


## 6 Presets

A preset is a name, a scheme, a source default and a set of assists. Four is
probably right, and the middle two are where most players live.

| Preset | Scheme | Trim | Limiter | Grip | Verge | For |
|---|---|---|---|---|---|---|
| **Touring** | Lanes (§3.1) | full | limiter | on | forgiving | first drive, and the attract mode |
| **Road** | Line (§3.2) | full | brake assist | on | forgiving | someone learning the circuit |
| **Race** | Wheel (§3.3) | 0.55 | off | off | as shipped | what ships today |
| **Loose** | Loose (§3.4) | 0 | off | off | as shipped | the car as the physics has it |

**A preset that is easier must also be slower**, or it is not a difficulty
setting, it is a cheat, and the records table (`records.py`, five best per track)
stops meaning anything. Two things follow: the lap-time cost of each preset is a
measurement to take (§8), not an assumption; and a time driven under an easier
preset is recorded with the preset it was driven under.


## 7 What is generic and what is glisteel's

The rule from the workspace `CLAUDE.md` is that a capability a game would want
belongs in the engine as an owned, reusable API, and the demo calls it. Applied
here:

### Engine — `OpenGLContext.move.vehicle` (new), `events.inputstate`, `omi_physics`

| Thing | Where | Why it is generic |
|---|---|---|
| Axis sources: winding key pair, pointer position, pointer delta | `move.vehicle` | `KeyboardWheel` and `MouseWheel` are in `glisteel.steering` today and contain nothing about racing |
| Gamepad axes and buttons | `events.inputstate` | every application in the workspace wants them; §4.3 |
| A vehicle control mode as a declared node, with bindings | `move.vehicle` | subclasses `MovementMode`, so it inherits `KeyBinding`, modifier handling, the generated settings page (`ui.generate`), the rebinding screen (`ui.bindings`) and saved bindings (`move.bindingstore`) — all of which glisteel currently does without |
| Path following: pure pursuit plus a cross-track term | `move.vehicle` | this is `glisteel.driver.Autopilot`, and it is ordinary vehicle path following. It needs an **alignment** protocol beside `physics.road` — stations, radii, nearest point — which is `glisteel.world.Course` written down as an interface |
| The **drivable zone** (§2.1) | `scenegraph.road`, beside `RoadProfile` | it is a road's own cross-section read as somewhere to drive: the profile already carries `lanes` and `lane_width`, and which of them run which way is a property of the road rather than of this game. `glisteel.zone.DrivableZone` is the prototype |
| Lane and lateral-offset controllers (§3.1, §3.2) | `move.vehicle` | they are the alignment plus a zone offset, and nothing in either is about racing |
| Line trim (§5.1) | `move.vehicle` | `glisteel.assist.Straighten` mentions nothing about a race |
| Corner speed limiter (§5.2) | `move.vehicle` | reads radii and produces pedals |
| Grip-budget and understeer limiting (§5.3, §5.4) | `omi_physics.vehicle` | they read wheel load, slip and surface grip, which only the vehicle has |

### glisteel

| Thing | Why it stays |
|---|---|
| Which presets exist, what they are called, and what each turns on | it is this game's design, not a library's |
| What is coming the other way: the *clear to pass* query and what the HUD says about it | `Traffic` is the game's. Which lanes are oncoming is the zone's, and it is generic; whether there is a car in one right now, and what a driver is told about it, is this game's |
| Race rules and their forgiveness: `PATIENCE`, `LOST`, restart, records-per-preset | the rules of this race |
| HUD: the steering indicator, the lane indicator, the pass advice | this game's screen |
| The numbers: wind-on rates, lane-change duration, limiter margin for *this* car | tuning, measured against this car on this circuit |

### One caution about building in the engine first

Two of the schemes are known shapes — lock and path-following exist and are
proven. The rest are not: §3.6 in particular may not survive contact with a
player. So the engine takes the source layer, the path controllers and the
assists from the start, because those are certain; the *experiment* — which
schemes are offered, how they are tuned, what they are called — is run behind
glisteel's own `Controller` seam, and a scheme that a measurement says is worth
keeping is hoisted then. Prototyping the uncertain part in the game is not a
licence to leave a generic capability there once it is proven.


## 8 How the choice gets made

The suite already has what an experiment needs, and it needs no new
infrastructure: `scenarios` builds a few hundred metres of real road in
milliseconds, `scripted.Script` writes a drive down as held keys, `trace.drive`
records every physics step, and `Trace` reduces a drive to numbers with budgets
against them (`tests/test_feel.py`).

**The experiment.** One set of scripts, driven under every scheme, on the same
scenarios, compared on the measures that already exist:

| Question | Measure | Scenario |
|---|---|---|
| does a coarse input still cross the road? | `worst_off_line`, `heading_change` | `straight` |
| is the car placeable where the driver means? | distance from a commanded offset | `straight`, `sweeper` |
| is a corner held? | `lateral_g`, `worst_off_line` | `sweeper`, `hairpin` |
| is a transient caught? | `worst_off_line`, `steering_rate` | `chicane` |
| is the view calm enough to read? | `camera_yaw_jerk`, `camera_bounce` | all |
| what does the assistance cost? | lap time | `circuit` |

**A novice script** is the new artifact, and it is one file: inputs that are
coarse, late and over-corrected — full lock held past the apex, a correction
that arrives 400 ms after it was wanted, a lift mid-corner. The measure that
decides an easy mode is whether the car is still on the road at the end of it,
and how far the driver got from where they meant to be. A scheme that a novice
script cannot crash and a fast script cannot beat the current best time with is
the mode we want.

**And a drive to watch.** The game records video (`--record`), and each
candidate scheme driven from the same script produces comparable footage of the
same corner. Numbers decide the shortlist; the footage decides between the ones
the numbers cannot separate.

**A whole lap, driven through the controls.** A script is a few seconds of one
input; what a way of driving is finally judged on is a lap of a real world with
traffic on it. `glisteel.driver.StandIn` is what drives that: an autopilot that
presses the keys a player would — the pedals, and the lane key when there is
something worth getting past — so what the lap shows is the *scheme*, not the
road. `--autopilot --control lanes --pace 1.2` is a lap of the shipped world
driven that way, and `--pace` is the dial that answers "how fast can this way of
driving actually be driven".

### 8.1 A lap of a real world

**A lap of a 2 km world**, six other cars on the road, driven through the lane
switch by a stand-in at each pace. `--pace` is how much of what the road allows
it asks for; the lap is from the green light, so it carries whatever the traffic
did that time:

| `--pace` | Lap | Passes | Ended |
|---|---|---|---|
| 1.4 | — | 2 | **hit a car** at 25 s |
| 1.2 | **2:40.2** | 6 | round |
| 1.0 | 2:48.3 | 3 | round |
| 0.9 | 2:52.1 | 3 | round |

So the answer to "as fast as it will go without crashing" on this world is 1.2,
and what stops 1.4 is arriving at another car rather than anything about the
steering — which is the mode behaving as specified.

**The recorded lap** — `--pace 1.2`, from the grid, on the recorder's own clock —
is 2:56.9 with five cars passed and no contact. It is slower than the 2:40 above
because it is a different lap: the countdown puts the car among different
traffic, and one queue behind a slow car costs more than the pace does. That is
the mode being what it is rather than a measurement being wrong — which is why a
lap is judged by watching it and a control is judged by a script.

**Two defects the lap found**, both in the stand-in rather than in the mode, and
both fixed:

- **It stopped watching the car in front the moment it decided to pass it.** A
  lane change takes about three seconds, and a lane the car has not reached yet
  is a lane it is not in; it spent those three seconds closing on the car it was
  about to pass, with nothing on the brake, and drove into the back of it.
- **The following rule matched speed rather than holding a distance.** The
  racing rule underneath — the fastest you could still stop from in the room you
  have — says "go their speed" at every gap shorter than the one you want, so a
  gap closed up in a corner never opened again: it spent most of a lap six
  metres off another car's bumper, which one touch of their brakes ends.

### 8.1.1 A lap of the 4 km world, raced

The lap above was of a 2 km world at 100 km/h posted. The shipped world is now
4 km with an 80 km/h limit and the stand-in aims at 200 km/h
(`driver.RACING_KPH`), which is a different drive and found a different set of
defects. Measured on `--seed 11 --extent 2048 --depth 3`, one lap from the
grid, `--pace 0.88`:

| Traffic | Lap | Passes | Mean | Top | Ended |
|---|---|---|---|---|---|
| 0 | **1:34.6** | — | 141 km/h | 182 | round |
| 8 | **1:47.6** | 7 | 125 km/h | 164 | round |
| 12 | **1:52.9** | 9 | 119 km/h | 164 | round |
| 16 | — | 9 | 118 km/h | 164 | **hit a car** at 112 s |

Twelve is what `traffic.cars_for()` asks for and what measures best: a pass
every thirteen seconds, and a lap spent more than half of it in the other lane.
Sixteen is more traffic than there is road to get by it in.

**Two hundred km/h is the target, not the average**, and this road does not
give it: the harmonic mean of what its own corners hold is 199 km/h, which is
what a car would average with no braking and no traffic at all, and a clear lap
driven properly is 141. The circuit is laid out to a 200 km/h design speed but
its tightest bends come out at 178 m where that speed wants 315 — the plan is
an ellipse bent by two harmonics and the harmonics are what break the radius,
so the alignment is asked for a minimum radius it cannot reach without becoming
a plain oval. Widening the world or the corners is the lever if the average
matters; it is recorded here rather than fixed because it is the shape of the
*world*, not of the way of driving.

**Six defects the raced lap found**, all in the stand-in or the traffic:

- **Traffic ran both ways round a closed circuit.** At 200 km/h against 80 a
  safe two-lane pass needs the best part of half a kilometre of clear road, and
  the longest sight line on this circuit is 255 m; every pass was a bet. A
  closed course is now raced one way round.
- **A driver on a bend was looking down a straight line.** What was in front
  was found by perpendicular distance from the car's heading, so a car two
  hundred metres up a curving road read as nothing in front until the bend
  swung it onto the line — one arrived at 35.8 m with the car doing 139 km/h.
  Traffic is looked for along the road.
- **The look-ahead was a fixed 110 m**, and stopping from 200 km/h takes 257.
- **It pulled out too late to get across**, committing to a pass with a stopped
  car 26 m ahead at 123 km/h: 0.8 s to contact against 3 s to change lanes.
- **It came back into a lane it could not hold**, on a fixed 24 m window, which
  is half a second at the speed it was carrying.
- **A pass held the following distance all the way past**, so it sat in the
  other lane at the speed of what it was passing: measured, the throttle was
  down for 0% of the time it spent out there.

### 8.1.2 What passing is for

The lap above was driven with the traffic all going one way round. That was the
wrong call and the video showed why: with nothing coming the other way the
overtaking lane is just more road. The stand-in sat in it for **59% of the
lap** -- there was no reason to come back -- and a manoeuvre with no cost is not
a manoeuvre, it is a wider road. Nine passes a lap counted for nothing, because
none of them was a decision.

**A road has two sides, and a circuit is a road.** What makes passing worth
anything is that the lane you pull into is the lane somebody else is coming
down. The reward is the time; the stake is being on the wrong side of the road
when the road runs out. With the oncoming traffic back, time on the wrong side
drops to **17%** without anything else changing: the road takes the lane back
by itself.

**What a driver needs before pulling out is room for the whole manoeuvre.**
The first model asked only for room to pull out, look, and get back --
`StandIn.getting_back()`, 2.9 s -- on the reasoning that no bend on a real road
shows anyone the half-kilometre a 140-against-80 pass takes, so a driver who
waited for it never passes. That reasoning has a hole in it, and the telemetry
drove into the hole (§8.1.3): the way out **stops existing part-way through**.
While the other car is still in front, lifting off and dropping in behind it is
always available; from the moment the two are alongside, coming back across the
crown is coming back onto the other car, and finishing is the only half of the
choice left. An entitlement worth 2.9 s bought a commitment worth eight.

So the road that can be seen has to cover the pass that is *left*
(`StandIn.room_to_finish`), asked again every frame until the cars draw
alongside, and never less than `getting_back()` however quick the sums say the
pass is. Asked against what is left rather than what it started as, because
the requirement decays: a driver a car's length off the back bumper needs a
fraction of the road the one who pulled out did, and a bar held at its opening
value for the whole manoeuvre is a bar no straight on any circuit clears. `PASS_MARGIN` is then the **appetite for the risk** on top of that, and
the risk that remains is the honest one: a road clear to the end of a straight
is clear to the end of the straight, and what comes round the bend after it was
never there to be looked at.

| Appetite | Sight wanted for a 7 s pass at 140 km/h | What it does |
|---|---|---|
| 1.4 | 660 m | nothing is ever worth trying |
| 1.1 | 519 m | *(measured below)* |
| 0.9 | 425 m | *(measured below)* |

This is what makes the shape of the circuit part of the mechanic rather than
scenery: a world of nothing but bends has no passing in it at any appetite, and
`CIRCUIT_CORNERS` straights are what put the road back (§8.1.4).

**And a pass is planned at the speed the pass will have.** `road_speed` looks
one braking distance ahead, which is the right window for the pedals and too
short for a manoeuvre that runs two hundred metres: planned on the straight it
starts from, a pass is still out there when the car brakes for the corner it
ends on. `StandIn.planning` works the time out at the speed underfoot, then
again over the road that answer reaches, and it is the slowest the road gets
over that stretch that the sums are taken on.

**Two other things had to be right first.** The sight model measured how far the
road departs the *tangent* the car points down; a line of sight is the **chord**
between two cars, which on a bend of radius *r* runs `sqrt(8*r*clear)` rather
than `sqrt(2*r*clear)` -- twice as far, and the difference between a road that
can be passed on and one that cannot. And what the view is clear *across* is the
road's own width, not half its carriageway: on the shipped world that moves the
median sight from 48 m to 120 m, with 23% of the lap over 200 m. Those are the
few places a pass is on, which is what makes choosing them a skill.

### 8.1.3 Reading a drive back

A lap reports a time and a count of passes, and neither says what the driver
*decided*. `glisteel.session.Session.telemetry` is where a drive writes that
down (:mod:`OpenGLContext.telemetry`), and what it needs is the handful of
moments a pass is made of: `pass-begun` with the gap, the speeds and the sight
it was taken on; `pass-done`; `pass-given-up` with the reason and where across
the road the car was; `pass-refused` with **which check said no** and how long the pass it turned
down would have taken; `crash` with what the car hit -- the closing speed, and
both cars' side of the crown, so one met head-on and one clipped coming back
into lane are told apart; and `drive-ended`, which is the line a reader looks
for first.

`StandIn.refusing()` is that reason, named, and `can_pull_out` is built from it
rather than beside it -- two copies of five conditions drift apart, and the one
that drifts is the explanation. A run marks unconditionally, because
`telemetry.install()` answers None when nobody asked for a file and the calls
that get guarded away are the ones that would have explained the failure:
`telemetry.NOT_RECORDING` takes a mark and keeps nothing.

**What it found, in four runs, that a printf had not:**

| Written down | The defect |
|---|---|
| every pass given up ~2 s in, "the road ran out" | the view was taken off the end of a straight; the pass was begun on it and abandoned in the bend after it |
| `pass-given-up seconds=0.4 across=1.8` | decided and un-decided before the car had moved -- a marginal number asked sixty times a second |
| `pass-begun gap=7.4 theirs=0.0 speed=3.4` | a pass at walking pace behind a stopped car, timing out fourteen seconds later with the car across the crown, which is where the next thing coming found it |
| two reasons alternating each frame | a boundary between them, not a driver changing its mind |
| one mark in ninety seconds, and the car at 0 km/h | the test circuit had a 311 m step in a road of 5 m ones, so the car never left the line |
| `pass-done seconds=5.1` then `crash oncoming=True across=-0.89 passing=False` | the pass was counted finished with the car still across the crown, and nothing had been watching the far lane since it drew alongside: the entitlement covered 2.9 s of a manoeuvre that ran for eight |

**What a pass costs is a question about a car that accelerates.** The sum
divided the relative distance by `speed - other`, a constant, so a standing
start behind something stopped divided by nothing and answered half a minute --
and a race car that reaches a hundred in 4.8 s was told it was too slow to get
by a parked one. It now pulls at `DriverStyle.pull` up to the speed the road
allows and holds it from there; the same correction belongs in
`room_to_cross`, where the error pointed the *unsafe* way, since a driver
matching the speed in front reads the gap as lasting for ever right up until
they floor it.

**And a road nobody can overtake on is a road, not a driver.** The view round a
bend of radius *r* runs `sqrt(8 * r * clear)`, so a test ring small enough to
lap is a hundred metres of sight against the hundred and forty a pass wants:
`scenarios.oval()` is a circuit with straights on it, and on that road the
stand-in waits through the bends at 100 m of sight and takes the pass on the
straight at 480 --

    7.11 s  pass-begun    gap=111 theirs=73 speed=122 sight=480
   13.85 s  pass-done     seconds=6.7
   28.70 s  pass-refused  why=cannot see far enough  speed=140 sight=100
   37.47 s  pass-begun    gap=53 theirs=83 speed=95 sight=600
   45.23 s  pass-done     seconds=7.8

which is the mechanic: wait, and pounce where the road lets you.

**What the caution warning says (§5.2).** Driven at racing pace
the car is more than 20 km/h over the advisory speed for **about a third of the
lap**. That is arithmetic rather than a defect — the advisory is 60% of what the
bend holds, so anyone driving near the limit is 60-odd per cent over it — but a
warning that is on for a third of a lap is a warning a driver stops reading. It
wants either a threshold measured against what the *bend* allows rather than
against what the sign advises, or to be shown only where the car would actually
run out of road. That is the next thing to decide about it.

### 8.1.4 A road you can pass on

Passing is a decision about *road*, so a world with no road to take it on has
no passing in it whatever the driver does. The shipped circuit was generated
from a smoothed closed curve, which is a shape with no straight anywhere on
it: 2% of the lap ran straight, the median sight was 120 m, and 8% of it was
long enough to get by an 80 km/h car on.

Three changes put the road back, and each of them belongs where it was made
rather than in the driver:

- **The plan is a polygon of corners, filleted.** `circuit_plan` returns the
  apexes a designer would draw and `hold_corners` rounds each to the design
  radius using the full leg, so what is between two corners is a straight.
  `ProceduralWorld.ease` -- the terrain slide meant for a route that was
  *found* -- is off by default for one that was *drawn*.
- **Curvature is measured over a length of road**, `CURVE_BASELINE`, not
  between adjacent 6 m samples. A three-point circle through samples that
  close is noise, and the driver was braking to 125 km/h for a corner worth
  158.
- **A viaduct can be seen across.** What the sight line is clear over varies
  along a road -- the verge in a wood, the bore wall in a tunnel, and the whole
  valley from a deck you can see through the railing of. `sight_distances`
  takes a clear width per point rather than one figure for the course.

On the 3.4 km world that bakes:

| | before | after |
|---|---|---|
| straight | 2% | 49% |
| median sight | 120 m | 207 m |
| passable at 140 km/h | 8% | 33% |
| tightest corner | 178 m | 196 m |

The tightest corner is still under the 315 m a 200 km/h design speed asks for,
because `hold_corners` shortens a fillet where two corners share a leg. That is
the next thing to fix about the generator.

### 8.2 A written-down drive, scheme by scheme

The switch driving four scripts, each under four schemes, on the scenarios
named. Where §8.1 is a whole lap of a world, this is one input at a time. `off line` is the furthest the car ran from the middle of the road, in
metres; `heading` is how far round it came over the last four seconds, in
degrees; the last column is how the run ended.

**A novice's inputs — late, coarse and over-corrected — through the chicane**
(`throttle 0..2.5; left 3..3.9; right 5..6.1; left 8..9.4`):

| `--control` | off line | heading | ended |
|---|---|---|---|
| `wheel` | 13.2 | 126° | mired off the road |
| `loose` | 11.2 | 0° | mired off the road |
| `line` | **3.2** | 10° | on the road, at 48 km/h |
| `lanes` | **3.2** | 10° | on the road, at 48 km/h |

**The same hands sawing at the wheel on a straight**
(`throttle 0..4; left 5..5.9; right 6.4..7.3; left 7.8..8.4`):

| `--control` | off line | heading | ended |
|---|---|---|---|
| `wheel` | 16.3 | 30° | mired off the road |
| `loose` | 16.7 | 0° | mired off the road |
| `line` | **3.0** | 2° | on the road, at 68 km/h |
| `lanes` | **3.0** | 2° | on the road, at 68 km/h |

**A 0.3 s tap at speed on a straight**, which is where the difference in *kind*
shows: under `wheel` the tap is a nudge the aid settles out of and the car ends
up back where it was; under `line` it is a step across the road that the car
then holds, with the heading unchanged.

| `--control` | off line | heading | what it is |
|---|---|---|---|
| `wheel` | 0.43 | 0.1° | a nudge, settled out |
| `loose` | 4.42 | 1.2° | a change of direction, still going |
| `line` | 1.12 | 0.0° | a step across the road, held |
| `lanes` | 2.24 | 0.0° | most of a lane, held |

**Read carefully.** These say the position schemes survive inputs the lock
scheme does not, on two pieces of road, against scripts written to be clumsy.
They do not say `line` is the mode to ship: nobody has driven it, the scripts
are not a player, and the schemes have not been measured for what they *cost* —
the lap time under each, which is §6's requirement that an easier preset be a
slower one, is not measured at all yet.

**Two things the measuring found, which is what it is for:**

- **A lane change must be a manoeuvre, not a target that jumps.** `lanes`
  first put the held line on the new lane at once; the aid then had to be 3.6 m
  sideways of where the car was, asked for all the lock there is, and spun the
  car — 20 m off the road and mired, worse than no scheme at all. The line now
  travels to the lane at the same rate a hand moves it, and the same drive keeps
  the car on the road.
- **A position scheme has no more grip than the car has.** Driven flat out into
  a 120 m sweeper — about 2 g of demand, against tyres that have about one —
  every scheme leaves the road, and `line` then keeps asking for a line the car
  cannot reach. That is §3.1's "within the car's capability" in numbers, and it
  is the argument for the corner speed limiter (§5.2) being part of an easy
  preset rather than an option on it.


## 9 Staging

**Stage 0 — the switch — landed.** §9.1. The seam, the drivable zone, and every
scheme of §3.1 to §3.5 behind `--control`, so a way of driving can be tried,
measured against the others and thrown away without anything else moving.

**Stage 1 — drive them and measure them.** Run §8 over the schemes the switch
now offers, write the numbers into this document, and cut the ones that do not
earn a place. Nothing below is worth starting before this says which schemes
survive.

**Stage 2 — sources.** Pointer capture, the two mappings, deadzone and curve as
settings, the HUD steering indicator; gamepad axes on `InputState` in the engine.
Every source, every scheme.

**Stage 3 — assists and presets.** §5.2 to §5.5 as toggles, the four presets of
§6, the preset recorded with a lap time, and the controls page on the settings
screen — which is generated from a declared mode's own fields once the modes are
engine nodes.

**Stage 4 — hoist and document.** Move what stages 1 to 3 proved into
`OpenGLContext.move.vehicle` with its own tests, and update the documentation of
§11.

Stage 1 is the one that decides anything. Stage 2 answers the complaint about
precision, stage 3 is what makes it a setting a player can live in, and stage 4
is what makes it the engine's.


### 9.1 The switch, as built

**Since 2026-08-20 the lane switch is a manoeuvre rather than a request**
(§3.1), the road carries its own speeds on Ontario-pattern signs, and `lanes`
is advised by them (§5.2). The rest of this section is the switch itself.


```bash
glisteel /tmp/world/tileset.json --control lanes          # pick a lane, drive the pedals
glisteel /tmp/world/tileset.json --control line --mouse   # place the car with the pointer
```

`--control` takes `wheel` (the default, and the controls the game has always
had), `loose`, `line`, `lanes` and `chauffeur`; `--mouse` is a *source* and goes
with any of them. `--assist` still means what it did under `wheel` and `loose`,
which are the schemes that use it.

Three modules carry it, and none of them needs a window:

| Module | Holds |
|---|---|
| `glisteel/steering.py` | the sources: keys that wind a wheel, the pointer, and the pedals every scheme shares |
| `glisteel/zone.py` | the drivable zone (§2.1): how wide the road is, where its lanes are, and which way they go |
| `glisteel/world.py` | `Course.corner_speed`, `caution_speed` and `caution_ahead`: how fast the road ahead is worth |
| `glisteel/schemes.py` | the schemes themselves, and `named()`, which is the switch |

A scheme is a `Controller` like any other, so it is set on `Session.driver` and
the window presses keys on `scheme.source` without knowing which scheme is on.
It takes the run on its first step, which is when it sets the line aid to what it
needs — 1.0 for the schemes that steer by position, 0 for `loose`, and whatever
the player asked for otherwise.

**Adding a scheme is a class**: subclass `ControlScheme`, give it a `name`, a
`summary` and a `drive()`, and it appears in `--control`, in the help and in the
tests that walk every scheme. Removing one is deleting it.

**The harness drives any of them.** `Script.parse(line, scheme='lanes')` replays
a written-down drive under a named scheme, so the same holds can be measured
each way:

```python
from glisteel.scripted import Script
from glisteel.trace import drive

for way in ('wheel', 'line', 'lanes', 'loose'):
    trace = drive(session_for(way), Script.parse('throttle 0..4; left 5..5.3'),
                  seconds=11.0)
    print(way, trace.worst_off_line(), trace.heading_change(4.9, 11.0))
```

**What it does not yet do**, and is deliberate: nothing is settable from inside
the game — a scheme is chosen when the run starts, since what the switch is for
is comparable drives rather than a settings screen. The presets of §6, the
assists of §5.2 to §5.5 and the pointer work of §4.2 are all still ahead of it.


## 10 What needs deciding

1. **How many modes ship.** Four presets is a guess; two (Road and Race) plus
   the two extremes may be the honest answer.
2. ~~**Whether Touring enforces the pass**~~ — **settled 2026-08-20: it
   advises.** The lane switch does the steering and nothing else. A player can
   still crash the car; the steering will not be what did it.
3. **Whether the limiter is in the easy preset** (§3.1) — the difference between
   a mode that teaches braking and one that cannot be crashed. The road now
   *tells* the driver either way (§5.2), which is the half of it that takes
   nothing away from them.
4. **Whether a gamepad is in scope now.** It is engine work and it benefits every
   project here, and it is also the largest single item in this plan.
5. **Whether times driven under an assisted preset share the records table** with
   times driven under Race, marked, or are kept apart.


## 11 Documentation this changes

- `glisteel/README.md` — the driving table, the `--assist` section, the steering
  section, and a new section on choosing a way to drive.
- `openglcontext/docs/navigation.html` — vehicle control modes beside the
  movement modes, and the gamepad source when it lands; indexed from
  `documentation.html` and referenced from `structure.html`.
- `openglcontext/plans/MOVEMENT-MODES.md` — its "deliberately not done" entry for
  gamepad axes is answered by §4.3.
- This plan — the measured numbers from §8, as each stage lands.
