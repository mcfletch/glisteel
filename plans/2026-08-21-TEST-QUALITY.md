# Test quality: what the suite costs, and what it says

**Landed 2026-08-21.** A review of `tests/` for runtime, organisation and shared
code, and the changes that came of it. The suite was green before and after;
what changed is how long it takes and how much of it is written twice.

## The measurement

| | before | after |
|---|---|---|
| whole suite | 492 s | 312 s |
| `tests/test_standin.py` | 265 s | 111 s |
| `tests/test_feel.py` | 66 s | 40 s |

1164 tests before, 1168 after (the four new ones are the doctests in
`tests/support.py`). Nothing was deleted, skipped or marked slow to get there.

## Where the time was going

Almost all of it is **simulated seconds**. A lap of an open road is about 0.4 s
of wall clock per second driven, and building the world it is driven in is
0.02 s -- so what a test costs is how far the car goes, and nothing else. The
suite drove about twenty minutes of car.

Most of that was the *same* drive. Four tests each drove a minute of the same
open road and asked it a different question; three asked three questions of one
sixteen-second run; eight asked the rule about passing after eight seconds of
the same warm-up. Each is a fair test on its own and they are right to be
separate tests -- one assertion each is why a failure says what broke -- but
they are questions about one drive rather than reasons for another one.

**So a drive is driven once.**

* `tests/test_feel.py` remembers a scripted drive by its arguments. It can:
  the step is fixed, the script is the whole of the input, there is no traffic,
  and a `Scenario` is a description that compares as one -- two drives of the
  same arguments produce identical `position`, `speed`, `yaw`, `steer` and
  `wheel_angle` arrays. The traces are read and never edited.
* `tests/test_standin.py` drives **one watched lap** of the open road, writing
  down as it goes what cannot be read afterwards: how long the car spent on the
  other side of the road, what was true the first time it got by something, what
  the throttle was doing while it was out there, and a reading of the drive at
  each of four marks. Seven tests then read that record. The marks are far
  enough apart that each is the drive the test used to make for itself, and the
  simulation is deterministic, so the 45-second mark of the shared lap is the
  end of the 45-second drive it replaces.
* Where the shared thing is **mutable**, the readings are taken in the fixture
  and the tests get numbers. `TestTheLineItHolds` hands over
  `{'started', 'settled', 'held'}` rather than the `Session`, and
  `TestAPassIsABetYouCanGetOutOf` shares the driven session but gives every test
  a `StandIn` of its own -- three of those tests set what it is in the middle of
  doing, and a shared one would make each test's result depend on the order.

That last line is the rule the rest of it follows: **share what cannot change,
never share what a test writes to.**

## What was written more than once

* Seven files built a ring or an ellipse of centreline with the same five lines
  of numpy, and four wrapped a callable in a counter with the same
  `(list.append(1), real(*a, **k))[1]` trick and a `try`/`finally` to put it
  back. Both now live in `tests/support.py` -- `ring`, `straight`, `perimeter`
  and `counting(owner, name)` -- with doctests, so the worked example is one
  that runs. What a test is *about* stays at the call site: the width of the
  road, its length and whether it closes are arguments there.
* `tests/test_feel.py` and `tests/test_standin.py` each had an
  `if __name__ == '__main__'` block in the *middle* of the file, with test
  classes after it. Moved to the end, where it stops looking like the end.

## What the tests say

`TestWhatIsComingTheOtherWay` asked three questions under
`if found is not None:`. A road that happened to be empty made all three pass
without testing anything, which is the failure mode a test cannot report. A
road with eight cars on it and ten seconds of driving has something coming the
other way every time -- measured, not assumed -- so the questions are now asked
outright and an empty road is a failure of the scenario rather than a test with
nothing to say.

## Still open

* `tests/test_driver.py` is the next 40 s: six tests driving laps of a circuit,
  several of them over the same ground. The same "one lap, several questions"
  shape would apply, and the observations wanted are different enough that it
  is worth doing deliberately rather than by pattern.
* `tests/test_standin.py` still spends 24 s on the watched lap and 8 s on the
  circuit lap. Those are real seconds of car and there is nothing to remove:
  what is left is the cost of the thing being tested.
