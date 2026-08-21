# The car rolled over instead of sliding

*2026-08-21 — fixed*

## What happened

A hard steering correction at speed put the car on its roof. Driven by the
autopilot from six metres off the line on a flat straight, it was upside down
within three seconds and never moved again. Full lock on flat ground rolled it
at 20, 25 and 30 metres a second — from 72 km/h upward, on tarmac, with nothing
to trip on but its own tyres.

## Why

A body tips when the sideways pull passes `(track / 2) / h`, where `h` is how
high its mass sits. The simulation has no separate centre of mass — a body's
origin *is* its mass, its collider and what the art hangs off — and the car's
origin was the middle of its bodywork, 0.710 m up. With a 1.58 m track that is
**1.11 g**, against tyres worth **1.90 g**. The car found the rollover well
before it found the limit of grip, so there was no slide to catch: the limit
was the car going over.

The same arithmetic said the chassis box was floating 0.40 m above the road —
40 cm of ground clearance on a supercar, which is the same mistake seen from
the other side.

It was not the engine tune. Every power level did it, including the 135 kW the
game shipped with; the faster car only reached the tipping point more often.

## The fix

Put the mass where an electric car's is — in the floor, between the axles —
and widen the track to what a 1.85 m body would really have:

| | before | after |
|---|---|---|
| mass sits at | 0.710 m | **0.560 m** |
| track | 1.58 m | **1.70 m** |
| tips above | 1.11 g | **1.52 g** |
| floor clears the road by | 0.40 m | 0.250 m |

Full lock at 20, 30, 45 and 60 metres a second now leaves the car on its
wheels; before, it went over at every one of them.

Spent as `CarSpec.mass_drop`: the wheels hang that much higher on the body, so
the body rides that much lower between them. The bodywork is hung the same
amount above the origin (`Car._build_nodes`) and the views are measured from
there (`camera.py`), so the car looks and is sat in exactly as before — what
moved is where its weight is. The generated models are untouched and keep their
own convention, origin at the centre of the chassis box.

## What still bounds it

1.52 g is not above the tyres' own peak — `grip` is 1.9 — so the arithmetic
still allows a tip if the car ever sustained everything the tyres have. It does
not, because the steering lock falls away with speed and the tyres break away
first, which is why the drive tests come back clean.

Going lower is not available today. The wheels have to hang **below** the mass
they carry: they are mounted `ride_height` under the middle of the shell, so a
drop past about 0.17 lifts them over the centre of mass and the car pivots on
its springs on landing instead of settling — measured, not guessed:

| drop | mass at | tips above | rolls at |
|---|---|---|---|
| 0.00 | 0.710 m | 1.20 g | 20, 25, 30, 40 m/s |
| 0.10 | 0.610 m | 1.39 g | 20, 25 m/s |
| **0.15** | **0.560 m** | **1.52 g** | **nothing** |
| 0.30 | 0.410 m | 2.07 g | nothing — but tumbles on landing |

What would close the gap properly is a real centre of mass: a body's origin is
currently its mass, its collider *and* what the art hangs off, so the mass
cannot go below the wheels without taking the collider with it.
`omi_physics` already carries `centerOfMass` on `model.Motion` and reads and
writes it through glTF — nothing in the solver uses it. Honouring it would let
the mass sit in the floor while the collider stayed around the bodywork, and
the tipping point would go wherever it was wanted.

Reducing `grip` instead would stop the rolling and cost every corner speed on
every circuit, which are laid out against the grip the car has.

## Where the cases live

`tests/test_feel.py::TestItSlidesRatherThanRolls` — the mass sits low enough to
corner on, and full lock at speed leaves the car on its wheels.
`tests/test_driver.py::TestHoldingTheLine::test_a_car_put_off_the_line_comes_back_to_it`
now asserts the car is upright; it used to pass while the car was on its roof,
because the wreck happened to stop inside the two metres it allowed.
