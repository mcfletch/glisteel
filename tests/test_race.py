"""Lap timing that a shortcut does not fool."""

import math

import numpy as np
import pytest

from glisteel.race import Lap, RaceTiming, off_course
from glisteel.world import Course


def _oval(points=64, radius=100.0):
    angle = np.linspace(0.0, 2 * math.pi, points, endpoint=False)
    line = np.stack([radius * np.cos(angle), np.zeros(points),
                     radius * np.sin(angle)], axis=-1)
    return Course(name='circuit', centreline=line, carriageway_width=8.0,
                  total_width=16.0, closed=True,
                  length=float(2 * math.pi * radius))


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
