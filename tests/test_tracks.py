"""The worlds a player can choose between, and where they are kept."""
import json
import os

import pytest

from glisteel.tracks import (
    Track,
    home,
    library,
    named,
    remember_picture,
    tracks_directory,
)


def _world(root, name, **extra):
    """A baked world's directory: a manifest, a tileset, and nothing else."""
    where = root / name.lower().replace(' ', '-')
    where.mkdir(parents=True, exist_ok=True)
    (where / 'tileset.json').write_text('{}', encoding='utf-8')
    document = {'name': name, 'tileset': 'tileset.json'}
    document.update(extra)
    (where / 'world.json').write_text(json.dumps(document), encoding='utf-8')
    return where


class TestOneTrack:
    def test_a_directory_with_a_manifest_is_a_track(self, tmp_path):
        assert Track.at(str(_world(tmp_path, 'Ashdown'))).name == 'Ashdown'

    def test_it_knows_where_its_tileset_is(self, tmp_path):
        where = _world(tmp_path, 'Ashdown')
        found = Track.at(str(where))
        assert found.tileset == os.path.join(str(where), 'tileset.json')

    def test_and_the_path_it_gives_is_one_that_can_be_opened(self, tmp_path):
        found = Track.at(str(_world(tmp_path, 'Ashdown')))
        assert os.path.exists(found.tileset)

    def test_a_track_with_no_picture_says_so(self, tmp_path):
        assert Track.at(str(_world(tmp_path, 'Ashdown'))).picture is None

    def test_a_picture_is_found_beside_the_manifest(self, tmp_path):
        where = _world(tmp_path, 'Ashdown', picture='track.png')
        (where / 'track.png').write_bytes(b'')
        assert Track.at(str(where)).picture == \
            os.path.join(str(where), 'track.png')

    def test_a_picture_the_manifest_promised_but_is_not_there_is_none(self, tmp_path):
        """The chooser draws a plate for it rather than failing to open."""
        where = _world(tmp_path, 'Ashdown', picture='gone.png')
        assert Track.at(str(where)).picture is None

    def test_a_directory_with_no_manifest_is_not_a_track(self, tmp_path):
        (tmp_path / 'junk').mkdir()
        assert Track.at(str(tmp_path / 'junk')) is None

    def test_a_manifest_whose_tileset_is_missing_is_not_a_track(self, tmp_path):
        where = _world(tmp_path, 'Ashdown')
        os.remove(where / 'tileset.json')
        assert Track.at(str(where)) is None

    def test_how_long_it_is(self, tmp_path):
        found = Track.at(str(_world(tmp_path, 'Ashdown', roadLength=8306.9)))
        assert found.length == pytest.approx(8306.9)

    def test_how_much_of_it_is_carried(self, tmp_path):
        found = Track.at(str(_world(tmp_path, 'Ashdown', roadLength=8000.0,
                                    structures={'bridge': 1500.0,
                                                'tunnel': 800.0})))
        assert found.carried() == pytest.approx(2300.0)

    def test_a_road_on_the_ground_carries_none_of_itself(self, tmp_path):
        assert Track.at(str(_world(tmp_path, 'Ashdown'))).carried() == 0.0


class TestWhatATrackSays:
    def test_a_lap_is_described_by_its_length(self, tmp_path):
        found = Track.at(str(_world(tmp_path, 'Ashdown', roadLength=8306.9)))
        assert '8.3 km' in found.summary()

    def test_and_by_what_carries_it(self, tmp_path):
        found = Track.at(str(_world(tmp_path, 'Ashdown', roadLength=8000.0,
                                    structures={'bridge': 1500.0})))
        assert 'bridge' in found.summary()

    def test_a_track_with_nothing_to_say_is_just_its_length(self, tmp_path):
        found = Track.at(str(_world(tmp_path, 'Ashdown', roadLength=1000.0)))
        assert found.summary() == '1.0 km'

    def test_a_track_of_unknown_length_still_describes_itself(self, tmp_path):
        assert isinstance(Track.at(str(_world(tmp_path, 'Ashdown'))).summary(), str)


class TestTheLibrary:
    def test_it_finds_every_world_under_a_directory(self, tmp_path):
        for name in ('Ashdown', 'Beacon', 'Cwm'):
            _world(tmp_path, name)
        assert [track.name for track in library(str(tmp_path))] == \
            ['Ashdown', 'Beacon', 'Cwm']

    def test_they_come_back_in_a_settled_order(self, tmp_path):
        for name in ('Cwm', 'Ashdown', 'Beacon'):
            _world(tmp_path, name)
        assert [track.name for track in library(str(tmp_path))] == \
            ['Ashdown', 'Beacon', 'Cwm']

    def test_a_directory_that_is_not_a_world_is_passed_over(self, tmp_path):
        _world(tmp_path, 'Ashdown')
        (tmp_path / 'notes').mkdir()
        assert len(library(str(tmp_path))) == 1

    def test_a_loose_file_is_passed_over(self, tmp_path):
        _world(tmp_path, 'Ashdown')
        (tmp_path / 'readme.txt').write_text('hello', encoding='utf-8')
        assert len(library(str(tmp_path))) == 1

    def test_a_directory_that_does_not_exist_holds_no_worlds(self, tmp_path):
        assert library(str(tmp_path / 'nowhere')) == []

    def test_a_world_can_be_asked_for_by_name(self, tmp_path):
        for name in ('Ashdown', 'Beacon'):
            _world(tmp_path, name)
        assert named('Beacon', str(tmp_path)).name == 'Beacon'

    def test_asking_by_name_does_not_care_about_case(self, tmp_path):
        _world(tmp_path, 'Ashdown')
        assert named('ashdown', str(tmp_path)).name == 'Ashdown'

    def test_a_name_that_is_not_there_is_nothing(self, tmp_path):
        _world(tmp_path, 'Ashdown')
        assert named('Beacon', str(tmp_path)) is None


class TestWhereAPlayersFilesLive:
    def test_the_game_keeps_them_under_the_platform_s_own_place(self, monkeypatch,
                                                                tmp_path):
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
        assert home().startswith(str(tmp_path))

    def test_and_they_are_the_game_s_own(self, monkeypatch, tmp_path):
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
        assert os.path.basename(home()) == 'glisteel'

    def test_tracks_are_kept_together_under_that(self, monkeypatch, tmp_path):
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
        assert tracks_directory() == os.path.join(home(), 'tracks')

    def test_asking_where_they_are_does_not_make_them(self, monkeypatch, tmp_path):
        """Reading a path is not a reason to create a directory."""
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
        tracks_directory()
        assert not os.path.exists(os.path.join(str(tmp_path), 'glisteel'))


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


class TestAWorldWithNoManifest:
    """A world baked before manifests, or one somebody points the game at
    directly, is still a world to drive."""

    def _bare(self, root, name='ashdown-forest'):
        where = root / name
        where.mkdir(parents=True)
        (where / 'tileset.json').write_text('{}', encoding='utf-8')
        return str(where / 'tileset.json')

    def test_it_is_a_track(self, tmp_path):
        assert Track.bare(self._bare(tmp_path)) is not None

    def test_named_after_the_directory_it_sits_in(self, tmp_path):
        assert Track.bare(self._bare(tmp_path)).name == 'Ashdown Forest'

    def test_and_it_carries_the_tileset_it_was_given(self, tmp_path):
        where = self._bare(tmp_path)
        assert Track.bare(where).tileset == where

    def test_it_says_nothing_it_does_not_know(self, tmp_path):
        found = Track.bare(self._bare(tmp_path))
        assert (found.length, found.picture, found.structures) == (None, None, {})

    def test_a_tileset_that_is_not_there_is_not_a_track(self, tmp_path):
        assert Track.bare(str(tmp_path / 'nowhere' / 'tileset.json')) is None

    def test_opening_prefers_the_manifest_when_there_is_one(self, tmp_path):
        where = _world(tmp_path, 'Ashdown')
        assert Track.opening(str(where / 'tileset.json')).name == 'Ashdown'

    def test_and_falls_back_to_the_directory_when_there_is_not(self, tmp_path):
        assert Track.opening(self._bare(tmp_path)).name == 'Ashdown Forest'

    def test_opening_nothing_is_nothing(self, tmp_path):
        assert Track.opening(str(tmp_path / 'nowhere.json')) is None


class TestATrackSOwnPicture:
    """A chooser shows each world by what it looks like, and only the world
    itself can say what that is -- so the game takes the picture and the
    manifest records the name."""

    def test_recording_it_puts_the_name_in_the_manifest(self, tmp_path):
        where = _world(tmp_path, 'Ashdown')
        track = Track.at(str(where))
        remember_picture(track, 'track.png')
        assert json.loads((where / 'world.json').read_text())['picture'] == \
            'track.png'

    def test_and_the_track_then_finds_it(self, tmp_path):
        where = _world(tmp_path, 'Ashdown')
        (where / 'track.png').write_bytes(b'')
        remember_picture(Track.at(str(where)), 'track.png')
        assert Track.at(str(where)).picture == os.path.join(str(where), 'track.png')

    def test_it_says_where_it_wrote(self, tmp_path):
        where = _world(tmp_path, 'Ashdown')
        assert remember_picture(Track.at(str(where))) == \
            os.path.join(str(where), 'world.json')

    def test_the_rest_of_the_manifest_is_left_alone(self, tmp_path):
        where = _world(tmp_path, 'Ashdown', seed=11, roadLength=8306.9)
        remember_picture(Track.at(str(where)))
        document = json.loads((where / 'world.json').read_text())
        assert (document['seed'], document['roadLength']) == (11, 8306.9)

    def test_a_world_with_no_manifest_records_nothing(self, tmp_path):
        (tmp_path / 'bare').mkdir()
        (tmp_path / 'bare' / 'tileset.json').write_text('{}', encoding='utf-8')
        track = Track.bare(str(tmp_path / 'bare' / 'tileset.json'))
        assert remember_picture(track) is None
