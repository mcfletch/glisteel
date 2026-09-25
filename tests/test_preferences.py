"""What a player chose, kept between runs.

Choosing a way of driving and finding the wheel back next time is worse than
not offering the choice: the game has asked a question, been answered, and
thrown the answer away. This is the file that stops that, and it is deliberately
small -- one document of a player's own settings, written the way the times
table is written, because a preferences file that can be left half-written is a
preferences file that eats the choice it was made to keep.
"""

import json
import os

import pytest

from glisteel import preferences, records, schemes, tracks


@pytest.fixture
def where(tmp_path):
    return str(tmp_path / 'preferences.json')


class TestAChoiceThatSurvives:
    def test_it_starts_with_the_defaults(self, where) -> None:
        assert preferences.Preferences(where).control is None

    def test_what_is_set_reads_back(self, where) -> None:
        kept = preferences.Preferences(where)
        kept.control = 'lanes'
        kept.save()
        assert preferences.Preferences(where).control == 'lanes'

    def test_a_file_that_is_not_there_is_not_an_error(self, where) -> None:
        """A fresh install is exactly this."""
        assert preferences.Preferences(where).control is None

    def test_nor_is_one_that_cannot_be_read(self, tmp_path) -> None:
        """A corrupt preferences file must not stop the game starting: what it
        holds is a convenience, and losing it costs one menu visit."""
        path = tmp_path / 'preferences.json'
        path.write_text('{ this is not json')
        assert preferences.Preferences(str(path)).control is None

    def test_a_value_no_scheme_is_called_is_ignored(self, where) -> None:
        """A hand-edited file, or one from a build that offered more ways of
        driving than this one does."""
        with open(where, 'w') as handle:
            json.dump({'control': 'hovercraft'}, handle)
        assert preferences.Preferences(where).control is None

    def test_and_one_that_is_named_survives(self, where) -> None:
        with open(where, 'w') as handle:
            json.dump({'control': schemes.DEFAULT}, handle)
        assert preferences.Preferences(where).control == schemes.DEFAULT


class TestWritingIt:
    def test_the_file_is_readable_by_a_person(self, where) -> None:
        kept = preferences.Preferences(where)
        kept.control = 'chauffeur'
        kept.save()
        assert json.loads(open(where, encoding='utf-8').read()) \
            == {'control': 'chauffeur'}

    def test_the_directory_is_made_if_it_is_not_there(self, tmp_path) -> None:
        path = str(tmp_path / 'deep' / 'down' / 'preferences.json')
        kept = preferences.Preferences(path)
        kept.control = 'line'
        kept.save()
        assert os.path.isfile(path)

    def test_saving_nothing_chosen_writes_nothing(self, where) -> None:
        """An untouched install leaves no file to go stale."""
        preferences.Preferences(where).save()
        assert not os.path.exists(where)

    def test_it_is_written_beside_and_moved_on(self, where) -> None:
        """A write that fails part way leaves what was there, not half a file."""
        kept = preferences.Preferences(where)
        kept.control = 'lanes'
        kept.save()
        assert not [one for one in os.listdir(os.path.dirname(where))
                    if one.endswith('-new')]


class TestWhereItLives:
    def test_beside_the_times_and_the_tracks(self) -> None:
        """One directory of a player's own things, not three."""
        assert os.path.dirname(preferences.preferences_path()) \
            == os.path.dirname(records.records_path()) == tracks.home()


class TestAHomeThatCannotBeWritten:
    """Saving happens from a menu button, and a player whose home directory
    will not take the file still has the choice they made."""

    @staticmethod
    def _unwritable(tmp_path):
        blocked = tmp_path / 'not-a-directory'
        blocked.write_text('')
        return str(blocked / 'preferences.json')

    def test_saving_there_says_nothing_was_saved(self, tmp_path, caplog):
        kept = preferences.Preferences(self._unwritable(tmp_path))
        kept.control = 'lanes'
        assert kept.save() is None
        assert 'could not save' in caplog.text

    def test_and_the_choice_is_still_the_one_made(self, tmp_path) -> None:
        kept = preferences.Preferences(self._unwritable(tmp_path))
        kept.control = 'lanes'
        kept.save()
        assert kept.control == 'lanes'
