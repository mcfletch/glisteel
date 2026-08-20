# Playing it: a review, and what came of it

2026-08-19. A drive of the shipped 4 km world, written up as ten complaints,
and what each one turned out to be. Six of the ten were faults in the engine or
the baker rather than in the game -- the road's own geometry, the structures
built along it, and what a world says about itself -- and are fixed where they
belong.

The world used throughout is `oglc-bake` at its defaults — 4096 m, depth 4,
seed 11 — and the pictures were taken from the driver's seat with
`OPENGLCONTEXT_HIDDEN=1 OPENGLCONTEXT_NO_VSYNC=1`.

## 1. "Pull to the right of the road is extreme … constantly fighting you"

**What it was.** The steering aid held a lane of its own — the middle of the
car's own half of the carriageway, or the centreline on an empty road — and put
the car back on it whenever the player let go of the wheel. Anywhere else on the
road, that is a pull the player has to fight for as long as they want to be
there; and the pull is felt as *the road* pulling, because it comes back the
moment a key goes down and the crossfall takes over.

The crossfall is real and measurable: a car standing in its own lane on the
shipped road, driven straight with the aid off, slides 0.65 m towards the verge
in sixteen seconds and is still accelerating. That is what the aid is for. What
it must not also do is choose the line.

**What changed.** `glisteel.assist.Straighten` now holds **the line the car is
on**: it takes the car's own offset across the road each time the player lets go
of the wheel, drawn back inside the carriageway's edge by half a car
(`MARGIN`), and holds that. The `lane` argument is gone — `Session` stands the
car on its own side of a road with traffic on it, and the aid holds it there
without ever being told which side that is.

## 2. "Passing is extremely difficult, switching lanes needs a support"

The same defect, felt from the other side: pulling out to overtake meant fighting
the aid the whole way past and being dragged back the moment the wheel came back
to centre. Steering out and letting go is now how a lane is changed.

## 3. "Start half-off road on a very bumpy shoulder"

**What it was.** The baker writes the station its chequered line and its gantry
are built at (`extras.roads[].start`), and the game did not read it: the car was
stood at whatever point the centreline array happened to begin at, and the lap
was timed from there too. On the shipped world those are the same place, so the
grid looked right; on any world whose designer moved the start line they are
not, and the car is stood somewhere else on the circuit entirely.

**What changed.** `Course` carries `start`, `Course.start_index` is the point
nearest it, and `RaceTiming` measures progress and sectors from that point
rather than from index zero.

**Not reproduced as reported.** On a default bake the car stands 1.8 m right of
the crown, mid-lane, on tarmac, with the shoulder 1.8 m further out; the
surface under it is smooth to within 2 mm over the first 300 m. If the shoulder
start persists on a world that declares no start line, it is something else.

## 4. "The hood looks nothing like a car hood, looks like a weird U of metal"

**What it was.** The driver's eye sits 0.40 above the body's centre and the front
arches top out at 0.34, so the eye is a hand's width over them. The bonnet's
crown left the base of the screen at 0.2245 — six centimetres *below* where the
glass meets it — and fell away from there, so the whole length of it subtended
under three degrees. Seen that flat it is a bar of metal, with the arches
standing up at each end of it and the road showing between them.

**What changed.** `tools/cars.py`: the crown leaves the screen at the height the
glass meets it (0.300 at the front axle, 0.246 at 1.43) and falls to the nose
over the next metre. The arches are untouched and still stand proud of it, by
0.04 rather than 0.11. Nothing else about the car moved, and the bounding box is
the same.

## 5. "Traffic cars were jumping along the oncoming lane, bouncing a metre"

**What it was.** A traffic car was stood on whatever a downward raycast found
under it. The ray does not exclude the car's own collider, so about a third of
the time it found the roof of the very car it was placing — a metre up — and the
fleet bounced between the road and itself. Measured over ten seconds of the
shipped world: 31 % of samples more than 0.2 m off the road surface, 1.5 % more
than a metre, worst case 23 m (a car over a viaduct, answered about the valley
floor because the deck's collider had not been built that far from the player).

**What changed.** Traffic rides the road's own surface: the centreline's height
at its station, dropped by the camber at the distance across it keeps
(`Course.surface_offset`, on the engine's
`RoadProfile.section_offset`). The road knows where its surface is everywhere it
goes, so nothing is asked of the physics. Worst single-frame step over the same
run: 23.7 m → 0.046 m.

## 6. "Traffic cars seen stuck in the woods"

A car pulling off aimed for `OFF_ROAD` (1.6 m) past the carriageway's edge —
measured from the centreline — and that was then *added* to the side of the road
it was already keeping. It ended up 7.0 m out on a road whose verge ends at
5.3 m and whose trees start at 6.1 m, so it parked inside the forest. It now
travels the difference and stops on the verge, at 5.2 m.

## 7. "The mouth of the first tunnel is entirely blocked with the terrain"

**What it was.** Two faults, one on top of the other.

*The portal was in the wrong place.* `PORTAL_COVER` was 2 m, measured to the
carriageway — so a bore whose crown is 7.5 m over the road opened where there
were two metres of soil over the tarmac, with five and a half metres of hillside
across the opening. Measured on the shipped world: at the portal the ground was
at road level and six metres further on it was 4.9 m over the road, rising to
36 m within ninety. The road ran into a bank, the arch stood in the air behind
it, and the only reason a car got through was that the *collider* has the bore
taken out of it.

*The ground was left inside the bore.* Even with the portal in the right place,
a height field draws straight lines between its samples: the line from the last
cut sample outside the portal up to the untouched hill is a bank across the
opening.

**What changed**, both in the editor:

- `PORTAL_COVER` is measured to the crown of the bore
  (`TunnelProfile().clearance + PORTAL_SOIL` = 9.0 m). The stretch between there
  and the surface is an ordinary cutting, which is how a portal is reached.
- `RoadPath.reshaped_segments` puts every segment inside a bore under the
  earthwork, so the cutting runs the length of the tunnel with the lining
  standing inside it. Trees and boulders are cleared out of what was dug
  (`_bore_corridor`), since the ground they stood on is the ground that came out.

**The cost, stated plainly.** The hill over a long bore is opened into a broad
cutting — the batter is 0.6, so a bore 30 m under the surface opens about 50 m
either side. From the road, which is the only place a player is, the tunnel now
reads as a tunnel. What would keep the hill whole is a **hole** in the ground
mesh with the bore's own outside plugging it; that is a terrain feature — the
field terrain is a height field and a splat map, and holes in it are a change to
the terrain renderer — and it is the right long-term answer.

## 8. "A black horizontal line that stretches across the entire screen"

**What it was.** The causeway's own wall, on both sides of the crossing at once.

What stands on the edge of a causeway is a low solid wall, and it was built from
`barrier_material()` — the material for a viaduct's *railing*, which is dark on
purpose, because a parapet is the thing closest to the camera for a whole span
and structural concrete there comes out white. On a vertical face at a tenth
albedo there is nothing but sky to light it whichever way the sun is, so both
flanks come out near black: measured off the frame, 35–40 against 90 for the
sunlit top of the same wall and 43 for the tarmac. From the driver's seat the
two of them meet the eye at the same height and read as one line across the
whole frame.

**What changed.** A causeway's wall is built from the same material as the fill
it stands on. `causeway_meshes` no longer takes a `barrier`; a deck's parapet
still does, and is still dark. Measured off the same frame, same station, same
camera: the sunlit wall 90 → 125, the shaded flank 33 → 43, against tarmac at
43 and the water beyond at 178.

**What is left of it.** The shaded flank is still a good deal darker than a
concrete face under an open sky ought to be: 43 is 5.5 % of the sunlit top of
the same wall, where a vertical surface turned away from the sun should be
nearer 15 %. That is the ambient the renderer gives a vertical face, not
anything about the causeway, and it wants its own look rather than a guess made
here.

**And a second fault found on the way there, which was not this one.** `_swept`
winds its triangles in the order the section is written, and the two sides of a
road are built by mirroring one section — which reverses it. So the wall was
right down one side and inside out down the other, and the causeway's fill and
the bridge decks were inside out on both. It does not show as darkness, because
`pbr.frag` flips the geometric normal on a back-facing fragment; what it does
mean is that a solid with backface culling on draws its *far* surface, so the
depth these structures write, and the shadows they cast, are of the wrong face.
`_swept` now takes `facing` and orients the section itself, so a section written
in whichever order reads best comes out facing the way it is meant to; the
bore's lining asks for `INWARD` and everything else takes the default. Checked
as the signed volume each part encloses, per side of the road.

## 9. "Redrive spawns below the world and falls away"

**What it was.** The surfaces a car meets — the carriageway swept from the
centreline and the ground cut from the height field — are held near the car and
dropped behind it, 260 m of road and 320 m of ground. A restart stood the car on
a grid the player had left a kilometre back, where there was nothing, and the
1.5 s settle ran with the world still streaming somewhere else. The car fell,
the floor-of-the-world check put it back on the same empty grid, and it fell
again.

**What changed.** `Session._stand_the_car` streams the world around the spot
before the car arrives, and both the restart and the put-back go through it.

## 10. "Redrive again leaves the dialog up and the car stuck"

The finish screen was pushed as an overlay and never taken off. It is modal, so
it sank every key: the race behind it restarted and the player could not reach
it. The screen now dismisses itself when a choice is made, before the handler
runs, and answers once however often a button is pressed.

## Left as it is

- **A fringe of ground cover at a portal.** The splat control map paints the
  road's own corridor as dirt and grows nothing on it, but the bore's cutting is
  wider than that corridor, so the cut floor either side of the carriageway
  comes out as grass and the cover grows on it — a green fringe across the
  bottom of the opening. Painting the whole of what was dug as dirt needs the
  field terrain's road corridor to follow the cut rather than being one number.
- **The forest comes up to the verge** (`ROAD_CLEARANCE` 0.8 m past the road's
  own width), which is deliberate and is most of what makes the circuit hard.
  It is a world-authoring number, not a defect.
- **The hole in the ground over a bore**, above.
