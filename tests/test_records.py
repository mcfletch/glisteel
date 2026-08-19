"""The best times driven on each track, kept between one session and the next."""
import json
import os

import pytest

from glisteel.records import KEPT, Record, Records, records_path


def _records(tmp_path, name='times.json'):
    return Records(str(tmp_path / name))


class TestOneTime:
    def test_a_record_is_a_time_and_when_it_was_driven(self):
        found = Record(seconds=84.115, when='2026-08-19')
        assert (found.seconds, found.when) == (84.115, '2026-08-19')

    def test_it_reads_as_a_driver_reads_a_clock(self):
        assert Record(seconds=84.115).clock() == '1:24.115'

    def test_a_time_under_a_minute_still_has_its_minute(self):
        assert Record(seconds=42.5).clock() == '0:42.500'

    def test_a_long_one_carries_its_minutes(self):
        assert Record(seconds=605.25).clock() == '10:05.250'


class TestKeepingTheBest:
    def test_a_fresh_table_has_nothing_on_it(self, tmp_path):
        assert _records(tmp_path).best('ashdown') == []

    def test_the_first_time_driven_takes_the_top(self, tmp_path):
        table = _records(tmp_path)
        assert table.offer('ashdown', 84.1) == 1

    def test_a_quicker_one_displaces_it(self, tmp_path):
        table = _records(tmp_path)
        table.offer('ashdown', 84.1)
        assert table.offer('ashdown', 80.0) == 1

    def test_and_the_slower_one_is_still_there(self, tmp_path):
        table = _records(tmp_path)
        table.offer('ashdown', 84.1)
        table.offer('ashdown', 80.0)
        assert [record.seconds for record in table.best('ashdown')] == [80.0, 84.1]

    def test_a_slower_time_takes_the_place_it_earned(self, tmp_path):
        table = _records(tmp_path)
        table.offer('ashdown', 80.0)
        assert table.offer('ashdown', 84.1) == 2

    def test_only_so_many_are_kept(self, tmp_path):
        table = _records(tmp_path)
        for seconds in range(100, 100 + KEPT + 3):
            table.offer('ashdown', float(seconds))
        assert len(table.best('ashdown')) == KEPT

    def test_and_they_are_the_quick_ones(self, tmp_path):
        table = _records(tmp_path)
        for seconds in (95.0, 80.0, 90.0, 85.0, 99.0, 82.0, 88.0):
            table.offer('ashdown', seconds)
        assert [r.seconds for r in table.best('ashdown')] == \
            [80.0, 82.0, 85.0, 88.0, 90.0]

    def test_a_time_too_slow_for_the_table_takes_no_place(self, tmp_path):
        table = _records(tmp_path)
        for seconds in range(50, 50 + KEPT):
            table.offer('ashdown', float(seconds))
        assert table.offer('ashdown', 900.0) is None

    def test_and_does_not_lengthen_the_table(self, tmp_path):
        table = _records(tmp_path)
        for seconds in range(50, 50 + KEPT):
            table.offer('ashdown', float(seconds))
        table.offer('ashdown', 900.0)
        assert len(table.best('ashdown')) == KEPT

    def test_each_track_keeps_its_own(self, tmp_path):
        table = _records(tmp_path)
        table.offer('ashdown', 84.1)
        table.offer('beacon', 60.0)
        assert [r.seconds for r in table.best('ashdown')] == [84.1]

    def test_a_track_never_driven_has_no_times(self, tmp_path):
        table = _records(tmp_path)
        table.offer('ashdown', 84.1)
        assert table.best('cwm') == []

    def test_the_quickest_is_offered_on_its_own(self, tmp_path):
        table = _records(tmp_path)
        for seconds in (95.0, 80.0, 90.0):
            table.offer('ashdown', seconds)
        assert table.record('ashdown').seconds == 80.0

    def test_a_track_never_driven_has_no_record(self, tmp_path):
        assert _records(tmp_path).record('ashdown') is None

    def test_a_time_that_is_not_a_time_is_refused(self, tmp_path):
        for bad in (0.0, -1.0):
            assert _records(tmp_path).offer('ashdown', bad) is None


class TestBetweenOneSessionAndTheNext:
    def test_what_was_saved_comes_back(self, tmp_path):
        table = _records(tmp_path)
        table.offer('ashdown', 84.1, when='2026-08-19')
        table.save()
        again = _records(tmp_path)
        assert [r.seconds for r in again.best('ashdown')] == [84.1]

    def test_with_the_day_it_was_driven(self, tmp_path):
        table = _records(tmp_path)
        table.offer('ashdown', 84.1, when='2026-08-19')
        table.save()
        assert _records(tmp_path).best('ashdown')[0].when == '2026-08-19'

    def test_saving_makes_the_directory_it_needs(self, tmp_path):
        table = Records(str(tmp_path / 'deep' / 'down' / 'times.json'))
        table.offer('ashdown', 84.1)
        table.save()
        assert os.path.exists(table.path)

    def test_a_file_that_is_not_there_is_an_empty_table(self, tmp_path):
        assert _records(tmp_path, 'never-written.json').best('ashdown') == []

    def test_a_file_that_will_not_parse_is_an_empty_table(self, tmp_path):
        """A corrupt score file loses the scores, not the game."""
        (tmp_path / 'times.json').write_text('{not json', encoding='utf-8')
        assert _records(tmp_path).best('ashdown') == []

    def test_what_is_written_is_readable_by_a_person(self, tmp_path):
        table = _records(tmp_path)
        table.offer('ashdown', 84.1)
        table.save()
        text = (tmp_path / 'times.json').read_text(encoding='utf-8')
        assert '\n' in text and 'ashdown' in text

    def test_a_time_from_a_document_missing_its_date_still_loads(self, tmp_path):
        (tmp_path / 'times.json').write_text(
            json.dumps({'ashdown': [{'seconds': 84.1}]}), encoding='utf-8')
        assert _records(tmp_path).best('ashdown')[0].seconds == pytest.approx(84.1)

    def test_a_document_that_is_not_a_table_at_all_is_empty(self, tmp_path):
        (tmp_path / 'times.json').write_text('[1, 2, 3]', encoding='utf-8')
        assert _records(tmp_path).best('ashdown') == []


class TestWhereTheyAreKept:
    def test_beside_the_player_s_other_files(self, monkeypatch, tmp_path):
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
        from glisteel.tracks import home
        assert os.path.dirname(records_path()) == home()

    def test_asking_where_does_not_make_the_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
        assert not os.path.exists(records_path())


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
