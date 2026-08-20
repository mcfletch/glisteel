"""The command line, checked where a test can reach it.

Everything the game is configured by arrives as an ``argparse`` namespace and is
then read all over the window, which no test enters. So two things happened:
options were read with ``getattr(self.config, name, default)``, which quietly
duplicates a default argparse already guarantees -- ``--traffic`` had two, six
in the parser and zero at the point that read it -- and a malformed one gave a
traceback out of the middle of ``main`` rather than a usage message.

:class:`~glisteel.options.Options` is what the window reads instead: built from
the namespace once, checked once, and a plain object a test can make.
"""
import argparse

import pytest

from glisteel.options import Options, window_size
from glisteel.traffic import DEFAULT_TRAFFIC


def _parsed(argv=()):
    from glisteel.game import build_parser
    return build_parser().parse_args(list(argv))


class TestTheSizeOfTheWindow:
    def test_it_reads_the_ordinary_form(self) -> None:
        assert window_size('1280x720') == (1280, 720)

    def test_it_does_not_mind_a_capital(self) -> None:
        assert window_size('1920X1080') == (1920, 1080)

    def test_a_missing_height_is_a_usage_error(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError, match='WIDTHxHEIGHT'):
            window_size('1280')

    def test_something_that_is_not_a_number_is_too(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError, match='WIDTHxHEIGHT'):
            window_size('wide x tall')

    def test_a_size_of_nothing_is_refused(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError):
            window_size('0x720')

    def test_a_negative_size_is_refused(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError):
            window_size('-100x720')

    def test_the_parser_uses_it(self) -> None:
        with pytest.raises(SystemExit):
            _parsed(['--size', 'enormous'])


class TestWhatTheWindowReads:
    def test_it_carries_the_parsers_own_defaults(self) -> None:
        found = Options.from_namespace(_parsed())
        assert found.traffic == DEFAULT_TRAFFIC
        assert found.hud is True
        assert found.view

    def test_the_traffic_default_is_the_one_the_parser_promises(self) -> None:
        # It was six in the parser and zero at the point that read it, so
        # --traffic's documented default was not the one a player got.
        assert Options.from_namespace(_parsed()).traffic == \
            _parsed().traffic == DEFAULT_TRAFFIC

    def test_what_was_asked_for_survives(self) -> None:
        found = Options.from_namespace(
            _parsed(['--traffic', '3', '--laps', '5', '--no-hud',
                     '--view', 'chase', '--assist', '0.25']))
        assert (found.traffic, found.laps, found.hud) == (3, 5, False)
        assert found.view == 'chase'
        assert found.assist == pytest.approx(0.25)

    def test_the_size_comes_through_as_two_numbers(self) -> None:
        found = Options.from_namespace(_parsed(['--size', '800x600']))
        assert found.size == (800, 600)

    def test_a_track_to_photograph_is_optional(self) -> None:
        assert Options.from_namespace(_parsed()).picture_track is None

    def test_it_can_be_made_without_a_command_line(self) -> None:
        # What a test wants: no parser, no namespace, just the run to set up.
        found = Options(world='/tmp/world/tileset.json', traffic=0, laps=2)
        assert found.traffic == 0 and found.laps == 2
        assert found.view      # the same default the parser has


class TestWhatIsRefused:
    def test_a_negative_lap_count_is_refused(self) -> None:
        with pytest.raises(ValueError, match='laps'):
            Options(world='x', laps=-1)

    def test_negative_traffic_is_refused(self) -> None:
        with pytest.raises(ValueError, match='traffic'):
            Options(world='x', traffic=-2)

    def test_an_assist_outside_nought_to_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match='assist'):
            Options(world='x', assist=1.5)

    def test_a_view_the_game_does_not_have_is_refused(self) -> None:
        with pytest.raises(ValueError, match='view'):
            Options(world='x', view='helicopter')

    def test_the_edges_are_allowed(self) -> None:
        assert Options(world='x', assist=0.0).assist == 0.0
        assert Options(world='x', assist=1.0).assist == 1.0
        assert Options(world='x', laps=0).laps == 0
