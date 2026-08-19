"""What arrives from outside, and what the game does with it that is unwise.

A track is a *shared* artefact by design: the manifest, the picture and the
library exist so that a player collects worlds, and a world someone else baked
is a world someone else wrote the manifest for. A tileset can also be a URL. So
the paths and the numbers in those files are input rather than data, and the
rules about them belong somewhere a test can read.
"""
import json

import pytest
from OpenGLContext.loaders.tiles3d.manifest import MANIFEST

from glisteel import tracks
from glisteel.world import _baked_luminaires


class TestAManifestCannotReachOutOfItsOwnDirectory:
    """``../../..`` in a manifest is a file outside the track it came with."""

    def _track_dir(self, tmp_path, manifest):
        where = tmp_path / 'world'
        where.mkdir()
        (where / 'tileset.json').write_text('{}', encoding='utf-8')
        (where / MANIFEST).write_text(json.dumps(manifest),
                                      encoding='utf-8')
        return where

    def test_a_picture_outside_the_track_is_refused(self, tmp_path) -> None:
        outside = tmp_path / 'secret.png'
        outside.write_bytes(b'not really a picture')
        where = self._track_dir(tmp_path, {
            'name': 'Ashdown', 'tileset': 'tileset.json',
            'picture': '../secret.png'})
        found = tracks.Track.at(str(where))
        assert found is None or found.picture is None

    def test_a_tileset_outside_the_track_is_refused(self, tmp_path) -> None:
        outside = tmp_path / 'elsewhere.json'
        outside.write_text('{}', encoding='utf-8')
        where = self._track_dir(tmp_path, {
            'name': 'Ashdown', 'tileset': '../elsewhere.json'})
        assert tracks.Track.at(str(where)) is None

    def test_an_absolute_path_is_refused(self, tmp_path) -> None:
        where = self._track_dir(tmp_path, {
            'name': 'Ashdown', 'tileset': 'tileset.json',
            'picture': '/etc/hostname'})
        found = tracks.Track.at(str(where))
        assert found is None or found.picture is None

    def test_an_ordinary_picture_beside_the_tileset_is_kept(self, tmp_path) -> None:
        where = self._track_dir(tmp_path, {
            'name': 'Ashdown', 'tileset': 'tileset.json',
            'picture': 'track.png'})
        (where / 'track.png').write_bytes(b'a picture')
        found = tracks.Track.at(str(where))
        assert found is not None and found.picture is not None

    def test_one_in_a_subdirectory_of_the_track_is_kept(self, tmp_path) -> None:
        where = self._track_dir(tmp_path, {
            'name': 'Ashdown', 'tileset': 'tileset.json',
            'picture': 'art/track.png'})
        (where / 'art').mkdir()
        (where / 'art' / 'track.png').write_bytes(b'a picture')
        found = tracks.Track.at(str(where))
        assert found is not None and found.picture is not None


class TestNumbersOutOfATileset:
    """``extras`` is whatever the baker wrote, and a baker may be someone else."""

    def test_lamps_that_are_not_triples_are_refused_clearly(self) -> None:
        with pytest.raises(ValueError, match='luminaires'):
            _baked_luminaires({'luminaires': [1.0, 2.0, 3.0, 4.0]})

    def test_lamps_that_are_not_numbers_are_refused_clearly(self) -> None:
        with pytest.raises(ValueError, match='luminaires'):
            _baked_luminaires({'luminaires': [['a', 'b', 'c']]})

    def test_a_sensible_set_of_lamps_is_read(self) -> None:
        found = _baked_luminaires({'luminaires': [[1.0, 2.0, 3.0],
                                                  [4.0, 5.0, 6.0]]})
        assert found.shape == (2, 3)
        assert found[1][2] == pytest.approx(6.0)

    def test_no_lamps_at_all_is_not_an_error(self) -> None:
        assert _baked_luminaires({}).shape == (0, 3)

    def test_an_absurd_number_of_lamps_is_refused(self) -> None:
        # A world cannot have more lamps than it has road; what this catches is
        # a number that would be an allocation rather than a world.
        with pytest.raises(ValueError, match='luminaires'):
            _baked_luminaires({'luminaires': [[0.0, 0.0, 0.0]] * 2_000_001})
