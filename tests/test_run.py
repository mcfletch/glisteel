"""Where a run is: on the lights, racing, home, or over."""

import pytest

from glisteel.run import (
    COUNTDOWN,
    ENDED,
    FINISHED,
    LIGHTS,
    RACING,
    Run,
)


def _count_down(run, dt=1.0 / 120.0):
    """Run the lights out, and answer how long they took."""
    elapsed = 0.0
    while run.phase == COUNTDOWN:
        run.update(dt)
        elapsed += dt
        assert elapsed < 60.0, "the lights never went out"
    return elapsed


class TestTheLights:
    """A standing start: the lamps come on one at a time, hold, and go out."""

    def test_a_run_begins_on_the_lights(self):
        assert Run().phase == COUNTDOWN

    def test_none_are_lit_to_begin_with(self):
        assert Run().lit == 0

    def test_they_come_on_one_at_a_time(self):
        run = Run(lights=5, interval=1.0)
        seen = []
        for _ in range(5):
            run.update(1.0)
            seen.append(run.lit)
        assert seen == [1, 2, 3, 4, 5]

    def test_the_last_one_does_not_start_the_race(self):
        """Five lit is the moment before the start, not the start."""
        run = Run(lights=5, interval=1.0, hold=1.4)
        run.update(5.0)
        assert (run.lit, run.phase) == (5, COUNTDOWN)

    def test_they_go_out_together_and_that_is_the_start(self):
        run = Run(lights=5, interval=1.0, hold=1.4)
        run.update(5.0)
        run.update(1.5)
        assert (run.lit, run.phase) == (0, RACING)

    def test_the_whole_sequence_takes_the_lamps_plus_the_hold(self):
        run = Run(lights=5, interval=1.0, hold=1.4)
        assert _count_down(run) == pytest.approx(6.4, abs=0.05)

    def test_a_shorter_rig_starts_sooner(self):
        assert _count_down(Run(lights=3, interval=0.5, hold=0.5)) \
            == pytest.approx(2.0, abs=0.05)

    def test_the_default_rig_is_five_lamps(self):
        assert Run().lights == LIGHTS


class TestWhatReachesTheCar:
    """The controls belong to the phase, not to whoever is holding the keys."""

    def test_the_car_is_held_on_the_lights(self):
        assert Run().allow(1.0, 0.0, 0.8) == (0.0, 1.0, 0.0)

    def test_and_that_is_true_however_hard_the_key_is_held(self):
        assert Run().allow(-1.0, -1.0, -1.0) == (0.0, 1.0, 0.0)

    def test_everything_goes_through_while_racing(self):
        run = Run()
        _count_down(run)
        assert run.allow(0.7, 0.2, -0.5) == (0.7, 0.2, -0.5)

    def test_a_finished_car_brakes_and_is_not_steered(self):
        run = Run(laps=1)
        _count_down(run)
        run.update(0.1, laps=1)
        assert (run.phase, run.allow(1.0, 0.0, 1.0)) == (FINISHED, (0.0, 1.0, 0.0))

    def test_a_car_whose_run_is_over_is_not_driven_either(self):
        run = Run()
        _count_down(run)
        run.update(0.1, ended='mired off the road')
        assert (run.phase, run.allow(1.0, 0.0, 1.0)) == (ENDED, (0.0, 1.0, 0.0))


class TestTheClock:
    """A lap time is time spent racing, and nothing else."""

    def test_it_does_not_run_on_the_lights(self):
        assert not Run().timed

    def test_it_runs_while_racing(self):
        run = Run()
        _count_down(run)
        assert run.timed

    def test_it_stops_at_the_finish(self):
        run = Run(laps=1)
        _count_down(run)
        run.update(0.1, laps=1)
        assert not run.timed

    def test_it_stops_when_the_run_ends(self):
        run = Run()
        _count_down(run)
        run.update(0.1, ended='wrecked')
        assert not run.timed


class TestTheEndOfIt:
    def test_the_laps_asked_for_are_the_laps_raced(self):
        run = Run(laps=3)
        _count_down(run)
        for done in (1, 2):
            run.update(0.1, laps=done)
            assert run.phase == RACING
        run.update(0.1, laps=3)
        assert run.phase == FINISHED

    def test_a_race_of_no_laps_never_finishes(self):
        """Free driving: there is no line to come home to."""
        run = Run(laps=0)
        _count_down(run)
        run.update(0.1, laps=40)
        assert run.phase == RACING

    def test_why_it_ended_is_kept(self):
        run = Run()
        _count_down(run)
        run.update(0.1, ended='mired off the road')
        assert run.outcome == 'mired off the road'

    def test_finishing_is_not_an_outcome_to_apologise_for(self):
        run = Run(laps=1)
        _count_down(run)
        run.update(0.1, laps=1)
        assert run.outcome is None

    def test_the_first_ending_is_the_one_that_sticks(self):
        run = Run()
        _count_down(run)
        run.update(0.1, ended='mired off the road')
        run.update(0.1, ended='wrecked')
        assert run.outcome == 'mired off the road'

    def test_over_covers_both_ways_of_stopping(self):
        finished, ended = Run(laps=1), Run()
        for run in (finished, ended):
            _count_down(run)
        finished.update(0.1, laps=1)
        ended.update(0.1, ended='wrecked')
        assert (finished.over, ended.over) == (True, True)

    def test_a_race_in_progress_is_not_over(self):
        run = Run()
        _count_down(run)
        assert not run.over


class TestPickingItUpAgain:
    def test_resuming_puts_a_mired_car_back_in_the_race(self):
        run = Run()
        _count_down(run)
        run.update(0.1, ended='mired off the road')
        run.resume()
        assert (run.phase, run.outcome) == (RACING, None)

    def test_resuming_does_not_reopen_a_finished_race(self):
        """The flag has fallen; there is nothing to go back to."""
        run = Run(laps=1)
        _count_down(run)
        run.update(0.1, laps=1)
        run.resume()
        assert run.phase == FINISHED

    def test_the_lights_can_be_dropped_at_once(self):
        run = Run()
        run.go()
        assert (run.phase, run.lit) == (RACING, 0)

    def test_dropping_them_on_a_race_already_run_changes_nothing(self):
        run = Run(laps=1)
        _count_down(run)
        run.update(0.1, laps=1)
        run.go()
        assert run.phase == FINISHED

    def test_restarting_puts_the_lights_back_up(self):
        run = Run()
        _count_down(run)
        run.update(0.1, ended='wrecked')
        run.restart()
        assert (run.phase, run.lit, run.outcome) == (COUNTDOWN, 0, None)


class TestSayingSo:
    def test_it_names_its_phase(self):
        assert repr(Run()).startswith('Run(countdown')

    def test_a_rig_of_no_lamps_starts_at_once(self):
        run = Run(lights=0, hold=0.0)
        run.update(1.0 / 120.0)
        assert run.phase == RACING


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
