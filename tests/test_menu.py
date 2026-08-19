"""The screens around the outside of the race.

Everything worth asserting about a menu is structural -- which buttons it has,
what each one does, which tracks it offers, what the finish says -- so none of
it needs a window. Building a panel touches no GL.
"""
import pytest

from glisteel import menu
from glisteel.records import Record
from glisteel.session import Result
from glisteel.tracks import Track


def widget(panel, name):
    """The named widget somewhere under ``panel``, or None."""
    def walk(node):
        if getattr(node, 'name', None) == name:
            return node
        for child in getattr(node, 'children', ()) or ():
            found = walk(child)
            if found is not None:
                return found
        return None
    return walk(panel)


def names(panel):
    found = []

    def walk(node):
        name = getattr(node, 'name', '')
        if name:
            found.append(name)
        for child in getattr(node, 'children', ()) or ():
            walk(child)
    walk(panel)
    return found


def texts(panel):
    found = []

    def walk(node):
        text = getattr(node, 'text', '')
        if text:
            found.append(str(text))
        value = getattr(node, 'value', None)
        if isinstance(value, str) and value:
            found.append(value)
        for child in getattr(node, 'children', ()) or ():
            walk(child)
    walk(panel)
    return found


def _track(name='Ashdown', **named):
    return Track(name=name, directory='/w/' + name.lower(),
                 tileset='/w/%s/tileset.json' % name.lower(), **named)


class TestTheMainMenu:
    def test_it_offers_a_drive(self):
        assert 'drive' in names(menu.main_menu())

    def test_driving_is_the_first_thing_offered(self):
        found = names(menu.main_menu())
        assert found.index('drive') < found.index('quit')

    def test_it_offers_the_tracks(self):
        assert 'tracks' in names(menu.main_menu())

    def test_it_offers_the_settings(self):
        assert 'settings' in names(menu.main_menu())

    def test_it_offers_quit(self):
        assert 'quit' in names(menu.main_menu())

    def test_each_button_calls_its_handler(self):
        called = []
        panel = menu.main_menu(
            on_drive=lambda: called.append('drive'),
            on_tracks=lambda: called.append('tracks'),
            on_settings=lambda: called.append('settings'),
            on_quit=lambda: called.append('quit'))
        for name in ('drive', 'tracks', 'settings', 'quit'):
            widget(panel, name).on_activate(None)
        assert called == ['drive', 'tracks', 'settings', 'quit']

    def test_a_button_with_no_handler_is_harmless(self):
        widget(menu.main_menu(), 'drive').on_activate(None)

    def test_it_says_what_game_this_is(self):
        assert menu.GAME_TITLE in texts(menu.main_menu())

    def test_a_race_in_progress_can_be_resumed(self):
        assert 'resume' in names(menu.main_menu(on_resume=lambda: None))

    def test_and_resuming_is_offered_before_driving_afresh(self):
        found = names(menu.main_menu(on_resume=lambda: None))
        assert found.index('resume') < found.index('drive')

    def test_with_nothing_running_there_is_nothing_to_resume(self):
        assert 'resume' not in names(menu.main_menu())

    def test_escape_resumes_the_race_behind_it(self):
        """A player who pressed Escape meaning "close this" must never find
        they have thrown the race away instead."""
        called = []
        panel = menu.main_menu(on_resume=lambda: called.append('resume'))
        panel.on_close(None)
        assert called == ['resume']

    def test_with_no_race_behind_it_escape_does_nothing(self):
        assert not menu.main_menu().closeOnEscape

    def test_it_can_say_which_track_is_loaded(self):
        assert 'Ashdown' in ' '.join(texts(menu.main_menu(subtitle='Ashdown')))


class TestChoosingATrack:
    TRACKS = None

    def setup_method(self):
        self.TRACKS = [_track('Ashdown', length=8306.9),
                       _track('Beacon', length=4200.0),
                       _track('Cwm', length=6100.0)]

    def test_it_offers_every_track(self):
        panel = menu.track_screen(self.TRACKS)
        assert list(widget(panel, 'track').optionLabels) == \
            ['Ashdown', 'Beacon', 'Cwm']

    def test_the_chooser_carries_each_track_s_tileset(self):
        panel = menu.track_screen(self.TRACKS)
        assert widget(panel, 'track').options[0] == self.TRACKS[0].tileset

    def test_the_one_already_loaded_is_the_one_selected(self):
        panel = menu.track_screen(self.TRACKS, chosen=self.TRACKS[1])
        assert widget(panel, 'track').value == self.TRACKS[1].tileset

    def test_with_nothing_loaded_it_starts_at_the_first(self):
        panel = menu.track_screen(self.TRACKS)
        assert widget(panel, 'track').value == self.TRACKS[0].tileset

    def test_choosing_one_hands_it_back(self):
        chosen = []
        panel = menu.track_screen(self.TRACKS, on_choose=chosen.append)
        widget(panel, 'track').value = self.TRACKS[2].tileset
        widget(panel, 'track').on_change(widget(panel, 'track'))
        widget(panel, 'drive').on_activate(None)
        assert chosen == [self.TRACKS[2]]

    def test_cancelling_hands_back_nothing(self):
        called = []
        panel = menu.track_screen(self.TRACKS, on_choose=called.append,
                                  on_cancel=lambda: called.append(None))
        widget(panel, 'cancel').on_activate(None)
        assert called == [None]

    def test_escape_cancels(self):
        called = []
        panel = menu.track_screen(self.TRACKS, on_cancel=lambda: called.append(1))
        panel.on_close(None)
        assert called == [1]

    def test_it_says_how_long_each_track_is(self):
        assert any('8.3 km' in one for one in texts(menu.track_screen(self.TRACKS)))

    def test_with_no_tracks_it_says_so_rather_than_offering_nothing(self):
        assert menu.NO_TRACKS in ' '.join(texts(menu.track_screen([])))

    def test_and_offers_no_way_to_drive_one(self):
        assert not widget(menu.track_screen([]), 'drive').enabled

    def test_the_best_time_on_a_track_is_shown_with_it(self):
        panel = menu.track_screen(self.TRACKS,
                                  records={'ashdown': Record(seconds=84.115)})
        assert any('1:24.115' in one for one in texts(panel))

    def test_a_track_never_driven_says_that_instead(self):
        panel = menu.track_screen(self.TRACKS, records={})
        assert menu.NEVER_DRIVEN in ' '.join(texts(panel))


class TestTheFinish:
    def test_a_race_driven_home_says_so(self):
        panel = menu.finish_screen(Result(seconds=84.115, laps=1))
        assert menu.FINISHED in ' '.join(texts(panel))

    def test_and_shows_the_time(self):
        panel = menu.finish_screen(Result(seconds=84.115, laps=1))
        assert any('1:24.115' in one for one in texts(panel))

    def test_a_run_that_ended_says_why_instead(self):
        panel = menu.finish_screen(Result(outcome='mired off the road'))
        assert any('mired off the road' in one.lower() for one in texts(panel))

    def test_a_new_best_is_worth_saying(self):
        panel = menu.finish_screen(Result(seconds=84.115, laps=1), place=1)
        assert menu.BEST in ' '.join(texts(panel))

    def test_so_is_a_place_that_is_not_the_top(self):
        panel = menu.finish_screen(Result(seconds=84.115, laps=1), place=3)
        assert any('3' in one for one in texts(panel))

    def test_a_time_that_did_not_make_the_table_says_neither(self):
        panel = menu.finish_screen(Result(seconds=84.115, laps=1), place=None)
        assert menu.BEST not in ' '.join(texts(panel))

    def test_it_offers_another_go(self):
        assert 'again' in names(menu.finish_screen(Result(seconds=84.0, laps=1)))

    def test_and_a_different_track(self):
        assert 'tracks' in names(menu.finish_screen(Result(seconds=84.0, laps=1)))

    def test_and_a_way_out(self):
        assert 'quit' in names(menu.finish_screen(Result(seconds=84.0, laps=1)))

    def test_another_go_is_the_first_thing_offered(self):
        found = names(menu.finish_screen(Result(seconds=84.0, laps=1)))
        assert found.index('again') < found.index('tracks')

    def test_each_button_calls_its_handler(self):
        called = []
        panel = menu.finish_screen(
            Result(seconds=84.0, laps=1),
            on_again=lambda: called.append('again'),
            on_tracks=lambda: called.append('tracks'),
            on_quit=lambda: called.append('quit'))
        for name in ('again', 'tracks', 'quit'):
            widget(panel, name).on_activate(None)
        assert called == ['again', 'tracks', 'quit']

    def test_the_table_of_times_is_shown_with_it(self):
        panel = menu.finish_screen(
            Result(seconds=84.115, laps=1), place=2,
            records=[Record(seconds=80.0, when='2026-08-01'),
                     Record(seconds=84.115, when='2026-08-19')])
        assert any('0:80' in one or '1:20.000' in one for one in texts(panel))

    def test_a_first_ever_run_shows_a_table_of_one(self):
        panel = menu.finish_screen(Result(seconds=84.115, laps=1), place=1,
                                   records=[Record(seconds=84.115)])
        assert any('1:24.115' in one for one in texts(panel))

    def test_it_cannot_be_escaped_out_of(self):
        """There is nothing behind it to go back to: the race is over."""
        assert not menu.finish_screen(Result(seconds=84.0, laps=1)).closeOnEscape


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
