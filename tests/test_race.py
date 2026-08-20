"""Lap timing that a shortcut does not fool."""

import math

import numpy as np
import pytest

from glisteel.race import Lap, RaceTiming, off_course
from glisteel.world import Course


def _oval(points=64, radius=100.0, start=0.0):
    angle = np.linspace(0.0, 2 * math.pi, points, endpoint=False)
    line = np.stack([radius * np.cos(angle), np.zeros(points),
                     radius * np.sin(angle)], axis=-1)
    return Course(name='circuit', centreline=line, carriageway_width=8.0,
                  total_width=16.0, closed=True,
                  length=float(2 * math.pi * radius), start=start)


def _drive(timing, course, start=0, stop=None, step=1, dt=0.1):
    """Move a car through a stretch of the course; return any laps completed."""
    stop = len(course.centreline) if stop is None else stop
    finished = []
    for index in range(start, stop, step):
        lap = timing.update(course.point(index), dt)
        if lap is not None:
            finished.append(lap)
    return finished


def _lap(timing, course, dt=0.1):
    """One whole circuit, finishing with the car back across the line."""
    order = list(range(1, len(course.centreline))) + [0]
    finished = []
    for index in order:
        lap = timing.update(course.point(index), dt)
        if lap is not None:
            finished.append(lap)
    return finished


class TestALap:
    def test_it_reads_as_a_driver_reads_it(self) -> None:
        assert Lap(1, 83.456).clock() == '1:23.456'

    def test_under_a_minute_still_shows_the_minute(self) -> None:
        assert Lap(1, 9.5).clock() == '0:09.500'


class TestGoingRound:
    def test_a_full_lap_counts(self) -> None:
        course = _oval()
        timing = RaceTiming(course)
        _drive(timing, course, stop=1)               # on the grid
        laps = _lap(timing, course)
        assert len(laps) == 1
        assert laps[0].number == 1

    def test_the_clock_runs_while_it_goes(self) -> None:
        course = _oval()
        timing = RaceTiming(course)
        _drive(timing, course, stop=20, dt=0.25)
        assert timing.current == pytest.approx(19 * 0.25)

    def test_a_second_lap_counts_too(self) -> None:
        course = _oval()
        timing = RaceTiming(course)
        _drive(timing, course, stop=1)
        laps = _lap(timing, course) + _lap(timing, course)
        assert [lap.number for lap in laps] == [1, 2]

    def test_the_clock_restarts_at_the_line(self) -> None:
        course = _oval()
        timing = RaceTiming(course)
        _drive(timing, course, stop=1)
        _lap(timing, course)
        assert timing.current == 0.0

    def test_it_reports_the_best_and_the_last(self) -> None:
        course = _oval()
        timing = RaceTiming(course)
        _drive(timing, course, stop=1)
        _lap(timing, course, dt=0.1)                 # a slow lap
        _lap(timing, course, dt=0.05)                # a quick one
        assert len(timing.laps) == 2
        assert timing.laps[1].seconds < timing.laps[0].seconds
        assert timing.best is timing.laps[1]         # the quick one
        assert timing.last is timing.laps[1]         # and the most recent

    def test_before_any_lap_there_is_no_best(self) -> None:
        assert RaceTiming(_oval()).best is None


class TestTheLineTheWorldDrew:
    """A lap is timed across the line the world put down, wherever that is.

    A world says where its start line is; timed from the point the centreline
    array happens to begin at instead, the clock turns over somewhere down the
    back of the circuit and the time is for a lap nobody drove.
    """

    def _round(self, timing, course, dt=0.1):
        """A lap starting and ending at the line the course names."""
        first = course.start_index
        total = len(course.centreline)
        order = [(first + step) % total for step in range(1, total + 1)]
        return [lap for lap in
                (timing.update(course.point(index), dt) for index in order)
                if lap is not None]

    def test_a_lap_turns_over_at_that_line(self) -> None:
        course = _oval(start=300.0)
        timing = RaceTiming(course)
        timing.update(course.point(course.start_index), 0.1)
        assert len(self._round(timing, course)) == 1

    def test_and_not_at_the_start_of_the_array(self) -> None:
        """Round from the world's line to just short of it: no lap yet."""
        course = _oval(start=300.0)
        timing = RaceTiming(course)
        timing.update(course.point(course.start_index), 0.1)
        first = course.start_index
        total = len(course.centreline)
        found = [timing.update(course.point((first + step) % total), 0.1)
                 for step in range(1, total)]
        assert not any(lap is not None for lap in found)

    def test_the_car_is_on_the_line_when_the_lap_starts(self) -> None:
        course = _oval(start=300.0)
        timing = RaceTiming(course)
        timing.update(course.point(course.start_index), 0.1)
        assert timing.progress == pytest.approx(0.0, abs=1.0 / 64)


class TestWhatDoesNotCount:
    def test_turning_round_at_the_line_is_not_a_lap(self) -> None:
        course = _oval()
        timing = RaceTiming(course)
        # Out a little way and straight back.
        _drive(timing, course, start=0, stop=6)
        assert _drive(timing, course, start=6, stop=-1, step=-1) == []

    def test_cutting_the_middle_is_not_a_lap(self) -> None:
        """Straight across the infield touches two sectors, not all of them."""
        course = _oval()
        timing = RaceTiming(course)
        half = len(course.centreline) // 2
        _drive(timing, course, stop=4)
        # Teleport to the far side and come back the way it went out.
        laps = _drive(timing, course, start=half, stop=half + 4)
        laps += _drive(timing, course, start=len(course.centreline) - 4,
                       stop=len(course.centreline))
        laps += _drive(timing, course, stop=2)
        assert laps == []

    def test_the_first_pass_of_the_line_starts_rather_than_finishes(self) -> None:
        course = _oval()
        timing = RaceTiming(course)
        assert _drive(timing, course, stop=3) == []
        assert timing.started


class TestWhereItIs:
    def test_progress_runs_from_zero_to_one(self) -> None:
        course = _oval()
        timing = RaceTiming(course)
        _drive(timing, course, stop=1)
        assert timing.progress == pytest.approx(0.0)
        _drive(timing, course, start=32, stop=33)
        assert timing.progress == pytest.approx(0.5)

    def test_the_sector_follows_the_position(self) -> None:
        course = _oval()
        timing = RaceTiming(course, sectors=4)
        assert timing.sector_of(course.point(0)) == 0
        assert timing.sector_of(course.point(len(course.centreline) // 2)) == 2

    def test_a_restart_abandons_the_lap_in_progress(self) -> None:
        course = _oval()
        timing = RaceTiming(course)
        _drive(timing, course, stop=20)
        timing.restart()
        assert timing.current == 0.0 and not timing.started


class TestBeingOffCourse:
    def test_on_the_road_is_not_off_course(self) -> None:
        course = _oval()
        assert not off_course(course, course.point(10))

    def test_the_verge_is_not_off_course_either(self) -> None:
        """A car on the grass beside the track is still racing."""
        course = _oval()
        beside = course.point(10) * np.array([1.05, 1.0, 1.05])
        assert not off_course(course, beside)

    def test_the_infield_is_off_course(self) -> None:
        course = _oval()
        assert off_course(course, (0.0, 0.0, 0.0))


class TestLeavingTheRoad:
    """A car that puts two wheels on the grass loses grip and drags; one that
    stays off it long enough is mired, and the run is over. What ends a lap on
    a forest road is the forest."""

    def _course(self, width=7.2, total=10.6):
        from glisteel.world import Course
        line = np.stack([np.arange(60) * 8.0, np.zeros(60), np.zeros(60)],
                        axis=-1)
        return Course(name='r', centreline=line, carriageway_width=width,
                      total_width=total, closed=False, length=472.0)

    def _watch(self, **named):
        from glisteel.race import OffRoad
        return OffRoad(self._course(), **named)

    def test_a_car_on_the_carriageway_is_on_the_road(self) -> None:
        watch = self._watch()
        assert watch.update((100.0, 0.0, 0.0), 0.1) is None
        assert not watch.off

    def test_a_wheel_on_the_verge_is_off_it(self) -> None:
        watch = self._watch()
        watch.update((100.0, 0.0, 4.6), 0.1)
        assert watch.off

    def test_being_off_it_is_not_the_end_of_the_run(self) -> None:
        """A car that has slid a wheel wide is still racing."""
        watch = self._watch()
        assert watch.update((100.0, 0.0, 4.6), 0.5) is None

    def test_staying_off_it_is(self) -> None:
        watch = self._watch(patience=2.0)
        ended = None
        for _ in range(30):
            ended = ended or watch.update((100.0, 0.0, 6.0), 0.1)
        assert ended is not None

    def test_coming_back_forgives_it(self) -> None:
        watch = self._watch(patience=2.0)
        for _ in range(15):
            watch.update((100.0, 0.0, 6.0), 0.1)
        watch.update((100.0, 0.0, 0.0), 0.1)
        assert watch.time_off == 0.0
        assert not watch.off

    def test_going_a_long_way_off_ends_it_at_once(self) -> None:
        """Down a bank and into the trees: there is no coming back from that."""
        watch = self._watch()
        assert watch.update((100.0, 0.0, 60.0), 0.02) is not None

    def test_it_says_why(self) -> None:
        watch = self._watch(patience=1.0)
        reasons = [watch.update((100.0, 0.0, 6.0), 0.1) for _ in range(20)]
        said = [one for one in reasons if one]
        assert len(said) == 1, "the reason is given once, not every frame"
        assert 'off' in said[0].lower()

    def test_once_it_is_over_it_stays_over(self) -> None:
        watch = self._watch(patience=1.0)
        for _ in range(20):
            watch.update((100.0, 0.0, 6.0), 0.1)
        assert watch.ended
        assert watch.update((100.0, 0.0, 0.0), 0.1) is None
        assert watch.ended

    def test_restarting_puts_it_back(self) -> None:
        watch = self._watch(patience=1.0)
        for _ in range(20):
            watch.update((100.0, 0.0, 6.0), 0.1)
        watch.restart()
        assert not watch.ended and watch.time_off == 0.0


class TestWhatTheGroundIsUnderTheWheels:
    def test_on_the_carriageway_it_is_tarmac(self) -> None:
        from glisteel.race import OffRoad
        watch = OffRoad(TestLeavingTheRoad()._course())
        watch.update((100.0, 0.0, 0.0), 0.1)
        assert watch.surface().grip == 1.0
        assert watch.surface().rolling == 0.0

    def test_off_it_the_going_is_soft(self) -> None:
        from glisteel.race import OffRoad
        watch = OffRoad(TestLeavingTheRoad()._course())
        watch.update((100.0, 0.0, 6.0), 0.1)
        assert watch.surface().grip < 0.6
        assert watch.surface().rolling > 0.1

    def test_the_further_off_the_softer_it_gets(self) -> None:
        from glisteel.race import OffRoad
        course = TestLeavingTheRoad()._course()
        near, far = OffRoad(course), OffRoad(course)
        near.update((100.0, 0.0, 4.6), 0.1)
        far.update((100.0, 0.0, 12.0), 0.1)
        assert far.surface().rolling > near.surface().rolling


class TestHittingSomething:
    """Leaving the road ends a run and so does running into a car. What ends it
    is the *impact*, not the contact: brushing a wing at walking pace is a
    scrape, and meeting the back of a lorry at forty metres a second is not.
    """

    def _watch(self, **named):
        from glisteel.race import Collisions
        return Collisions(**named)

    def test_nothing_has_happened_yet(self) -> None:
        assert self._watch().ended is None

    def test_a_gentle_touch_is_not_a_crash(self) -> None:
        watch = self._watch()
        assert watch.update(closing=1.5, dt=0.1) is None
        assert watch.ended is None

    def test_meeting_something_at_speed_is(self) -> None:
        watch = self._watch()
        assert watch.update(closing=28.0, dt=0.1) is not None

    def test_it_says_so_once(self) -> None:
        watch = self._watch()
        watch.update(closing=28.0, dt=0.1)
        assert watch.update(closing=28.0, dt=0.1) is None

    def test_and_says_what_happened(self) -> None:
        watch = self._watch()
        assert 'car' in (watch.update(closing=28.0, dt=0.1) or '').lower()

    def test_restarting_clears_it(self) -> None:
        watch = self._watch()
        watch.update(closing=28.0, dt=0.1)
        watch.restart()
        assert watch.ended is None

    def test_a_caller_may_set_where_the_line_is(self) -> None:
        watch = self._watch(survivable=40.0)
        assert watch.update(closing=28.0, dt=0.1) is None


class TestHowFastTwoCarsAreClosing:
    """Head-on, the closing speed is the *sum*: two cars at thirty are meeting
    at sixty. Taken as the difference it is nothing at all, which is how a car
    passing the other way reads as a gentle touch and a real head-on reads as
    nothing."""

    def _closing(self, mine, theirs, offset):
        from glisteel.race import closing_speed
        return closing_speed(np.asarray(mine, 'd'), np.asarray(theirs, 'd'),
                             np.asarray(offset, 'd'))

    def test_catching_something_slower_closes_at_the_difference(self) -> None:
        assert self._closing((0, 0, -30), (0, 0, -12), (0, 0, -20)) \
            == pytest.approx(18.0)

    def test_meeting_something_head_on_closes_at_the_sum(self) -> None:
        assert self._closing((0, 0, -30), (0, 0, 30), (0, 0, -20)) \
            == pytest.approx(60.0)

    def test_something_pulling_away_is_not_closing_at_all(self) -> None:
        assert self._closing((0, 0, -12), (0, 0, -30), (0, 0, -20)) < 0.0

    def test_something_alongside_at_the_same_speed_is_not_either(self) -> None:
        assert self._closing((0, 0, -30), (0, 0, -30), (3.0, 0, 0)) \
            == pytest.approx(0.0)

    def test_two_cars_at_the_same_place_is_not_a_division(self) -> None:
        assert self._closing((0, 0, -30), (0, 0, 30), (0, 0, 0)) == 0.0
