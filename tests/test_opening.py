"""Opening a world, and what happens when one cannot be opened.

A track comes from a chooser, and a chooser offers whatever is on disk: a world
that has been moved, half-baked, or baked without a circuit in it is a thing a
player can pick. None of those is a reason to take the game down, so what
decides here is a sentence to show them -- and the window puts it up and stays
running.

Nothing here needs a window: which worlds can be raced, and what to say about
the ones that cannot, is a question about a world and a track.
"""
import pytest

from glisteel.game import main, opening_fault
from glisteel.world import RaceWorld


class _World:
    def __init__(self, course=None):
        self.course = course


class _Track:
    def __init__(self, tileset='/worlds/ashdown/tileset.json'):
        self.tileset = tileset
        self.name = 'Ashdown'


class TestWhetherAWorldCanBeRaced:
    def test_a_world_with_a_road_has_nothing_wrong_with_it(self) -> None:
        assert opening_fault(_World(course=object()), _Track()) is None

    def test_a_world_with_no_road_cannot_be_raced(self) -> None:
        assert opening_fault(_World(), _Track()) is not None

    def test_it_says_which_world_and_what_to_do_about_it(self) -> None:
        found = opening_fault(_World(), _Track())
        assert '/worlds/ashdown/tileset.json' in found
        assert 'bake' in found.lower()


class TestAWorldThatIsNotThere:
    """The chooser's own failure mode: a track that has moved since it was listed."""

    def test_loading_it_is_an_error_a_menu_can_catch(self, tmp_path) -> None:
        with pytest.raises(Exception) as caught:
            RaceWorld(str(tmp_path / 'gone' / 'tileset.json'))
        assert isinstance(caught.value, Exception)

    def test_the_command_line_still_exits_rather_than_traps(self, tmp_path, capsys) -> None:
        # What a *shell* wants: a message on stderr and a non-zero status,
        # rather than a traceback.
        assert main([str(tmp_path / 'gone' / 'tileset.json')]) == 1
        assert 'gone' in capsys.readouterr().err
