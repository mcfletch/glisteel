"""``glisteel-diagnose``'s report, which is what a change is judged from.

A lap is chaotic, so the tool drives a world against several sets of traffic
and prints one line each. Those lines are the evidence, so the summary has to
survive whatever the runs came to -- including two runs that came to the same
thing.
"""
import numpy as np
import pytest

from glisteel.diagnose import Report, summarise


def _report(world='beacon', seconds=100.0, outcome=None, speeds=(10.0, 20.0)):
    return Report(world=world, seconds=seconds, outcome=outcome,
                  speeds=np.asarray(speeds, dtype='d'))


class TestTheSummaryOfAHandfulOfRuns:
    def test_it_says_how_many_finished(self) -> None:
        found = summarise([_report(), _report(outcome='mired off the road')])
        assert 'beacon: 1 of 2 finished' in found

    def test_and_one_line_for_each_seed(self) -> None:
        lines = summarise([_report(), _report(), _report()]).split('\n')
        assert [line.strip().split(':')[0] for line in lines[1:]] \
            == ['seed 0', 'seed 1', 'seed 2']

    def test_two_runs_that_came_to_the_same_thing_are_still_two_runs(self) -> None:
        """Every seed is numbered by where it is in the list. Looking a report
        up by *value* asks two of them whether they are equal, and a report
        carries its speeds as an array -- which answers with an array."""
        same = [_report(), _report()]
        lines = summarise(same).split('\n')
        assert 'seed 0' in lines[1] and 'seed 1' in lines[2]

    def test_the_outcome_is_named_where_there_was_one(self) -> None:
        assert 'HIT A CAR' in summarise([_report(outcome='HIT A CAR')])

    def test_a_run_that_finished_says_so(self) -> None:
        assert 'finished' in summarise([_report()])

    def test_nothing_driven_is_said_rather_than_crashed_on(self) -> None:
        assert summarise([]) == 'nothing was driven'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
