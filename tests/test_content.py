"""What this game offers to download, and what of it is already here.

glisteel ships its code and fetches its data: a track is 22 MB and the four
together with the art they share are 90 MB, which is not a wheel. The facility is the engine's
(:mod:`OpenGLContext.contentpacks`); what is here is which registry, which
namespace, and how a downloaded track reaches the chooser.
"""

import os

import pytest

from glisteel import content


def release_assets():
    """``release-assets.py``, as a module.

    The command is spelled with a hyphen, as a command is, so it is loaded by
    path rather than imported by name.
    """
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
        __file__))), 'release-assets.py')
    spec = importlib.util.spec_from_file_location('release_assets', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheShippedRegistry:
    def test_it_loads(self) -> None:
        assert content.registry()

    def test_every_pack_is_this_game_s(self) -> None:
        assert {one.namespace for one in content.registry()} == {content.NAMESPACE}

    def test_the_cars_are_the_base_pack(self) -> None:
        """What the game cannot start without: there is nothing to draw."""
        base = [one for one in content.registry() if one.base]
        assert [one.key for one in base] == ['glisteel/cars']

    def test_every_track_needs_the_art_it_shares(self) -> None:
        """A track fetched without it renders as bare ground."""
        tracks = [one for one in content.registry() if one.marker == 'tileset.json']
        assert tracks, 'the registry offers no tracks'
        for one in tracks:
            assert 'glisteel/forest-art' in one.needs, one.key

    def test_every_pack_states_its_terms(self) -> None:
        for one in content.registry():
            assert one.copyright.strip(), one.key

    def test_every_pack_carries_a_digest(self) -> None:
        """Ours to publish, so the bytes are known and are checked."""
        for one in content.registry():
            assert len(one.sha256) == 64, one.key

    def test_the_sizes_are_real(self) -> None:
        """`approximate_bytes` sets the fetch cap; a wrong one fails a download
        on its last megabyte."""
        for one in content.registry():
            assert one.approximate_bytes > 1024, one.key


class TestWhatIsAlreadyHere:
    @pytest.fixture
    def store(self, tmp_path):
        return content.store(root=str(tmp_path / 'content'))

    def test_nothing_is_installed_to_begin_with(self, store) -> None:
        assert content.installed(store=store) == []
        assert len(content.missing(store=store)) == len(content.registry())

    def test_a_first_run_needs_the_base_pack(self, store) -> None:
        wanted = content.needed_to_start(store=store)
        assert [one.key for one in wanted] == ['glisteel/cars']

    def test_and_stops_needing_it_once_it_is_here(self, store, tmp_path) -> None:
        self.unpack(store, 'glisteel/cars')
        assert content.needed_to_start(store=store) == []

    def test_a_track_that_is_here_is_offered_as_a_track(self, store) -> None:
        where = self.unpack(store, 'glisteel/ashdown', world=True)
        found = content.installed_tracks(store=store)
        assert [one.directory for one in found] == [where]
        assert found[0].name == 'Ashdown'

    def test_one_that_is_not_here_is_not(self, store) -> None:
        assert content.installed_tracks(store=store) == []

    def unpack(self, store, key, world=False):
        """Put a pack's content where the store looks, without a download."""
        from OpenGLContext.contentpacks import catalog
        pack = catalog.pack_for_key(key, content.registry())
        where = store.directory_for(pack)
        os.makedirs(where, exist_ok=True)
        marker = os.path.join(where, pack.marker)
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, 'w') as handle:
            handle.write('{}')
        if world:
            import json
            with open(os.path.join(where, 'world.json'), 'w') as handle:
                json.dump({'name': 'Ashdown', 'tileset': 'tileset.json'}, handle)
        return where


class TestTheChooserSeesDownloadedTracks:
    """A track fetched as a pack is a track like one baked by hand."""

    def test_the_library_reads_both(self, tmp_path, monkeypatch) -> None:
        import json

        from glisteel import tracks
        own = tmp_path / 'tracks' / 'mine'
        own.mkdir(parents=True)
        (own / 'tileset.json').write_text('{}')
        (own / 'world.json').write_text(json.dumps(
            {'name': 'Mine', 'tileset': 'tileset.json'}))
        store = content.store(root=str(tmp_path / 'content'))
        TestWhatIsAlreadyHere().unpack(store, 'glisteel/beacon', world=True)
        found = tracks.library(directory=str(tmp_path / 'tracks'), store=store)
        assert sorted(one.name for one in found) == ['Ashdown', 'Mine']


class TestThePicturesAChooserShowsFirst:
    """A pack's own art is inside the archive being chosen, so a screen
    offering one has nothing to show it with unless the registry carries a
    thumbnail. These ship in the wheel -- 87 KB against the 90 MB they
    describe."""

    def test_every_track_has_one(self) -> None:
        for pack in content.track_packs():
            assert pack.preview, pack.key

    def test_and_it_is_a_file_that_is_there(self) -> None:
        """`preview` comes back resolved, and empty for one that is named and
        absent -- so a non-empty value is a file."""
        for pack in content.track_packs():
            assert os.path.isfile(pack.preview), pack.key

    def test_the_art_and_the_cars_need_none(self) -> None:
        """Nobody chooses between them: one is the floor and one comes with
        whatever needs it."""
        for pack in content.registry():
            if pack not in content.track_packs():
                assert not pack.preview, pack.key

    def test_they_are_small_enough_to_ship(self) -> None:
        total = sum(os.path.getsize(one.preview)
                    for one in content.track_packs())
        assert total < 512 * 1024, '%d bytes of thumbnails' % (total,)


class TestWhatAFirstRunDoes:
    """The cars are not in the wheel, so a fresh install has nothing to draw.

    The base pack is fetched before the menu -- one download, asked for, rather
    than a stall at the first frame that wants a model.
    """

    @pytest.fixture
    def store(self, tmp_path):
        return content.store(root=str(tmp_path / 'content'))

    def test_a_fresh_install_needs_the_cars(self, store) -> None:
        assert [one.key for one in content.needed_to_start(store=store)] \
            == ['glisteel/cars']

    def test_what_it_needs_states_its_size_and_terms(self, store) -> None:
        """It is put in front of somebody before anything is fetched."""
        for one in content.needed_to_start(store=store):
            assert one.human_size() and one.copyright.strip()

    def test_the_base_pack_carries_a_digest(self, store) -> None:
        """Ours to publish; a truncated download of the one thing the game
        cannot start without should be a refusal, not a missing car."""
        for one in content.needed_to_start(store=store):
            assert len(one.sha256) == 64

    def test_a_run_with_the_cars_here_asks_for_nothing(self, store) -> None:
        from OpenGLContext.contentpacks import catalog
        pack = catalog.pack_for_key('glisteel/cars', content.registry())
        where = store.directory_for(pack)
        os.makedirs(os.path.join(where, 'cars'), exist_ok=True)
        with open(os.path.join(where, pack.marker), 'w') as handle:
            handle.write('x')
        assert content.needed_to_start(store=store) == []

    def test_the_art_comes_from_the_wheel_until_the_pack_is_here(
            self, store) -> None:
        """Both, deliberately: the art leaves the wheel when the release
        carrying it exists, and until that day an install has to work."""
        where = content.art_directory(store=store)
        assert os.path.isdir(os.path.join(where, 'cars'))
        assert not where.startswith(store.root)

    def test_and_from_the_pack_once_it_is(self, store) -> None:
        from OpenGLContext.contentpacks import catalog
        pack = catalog.pack_for_key(content.BASE, content.registry())
        root = store.directory_for(pack)
        os.makedirs(os.path.join(root, 'cars'), exist_ok=True)
        with open(os.path.join(root, pack.marker), 'w') as handle:
            handle.write('x')
        assert content.art_directory(store=store) == root


class TestTheRegistryAsOneFile:
    """What an installed game is pointed at to be offered content it never
    shipped with.

    A document and some thumbnails -- 89 KB against the 90 MB it describes --
    so fetching one gives a chooser every pack's title, size, terms and picture
    while downloading none of the content. Attached to the same release as the
    archives, which is what lets a later set of tracks reach a game that is
    already installed.
    """

    def bundle(self, tmp_path):
        from OpenGLContext.contentpacks import publish
        return publish.bundle_registry(
            content.CATALOG_PATH, str(tmp_path / 'glisteel-registry.zip'))

    def test_it_holds_the_registry_and_its_pictures(self, tmp_path) -> None:
        import zipfile
        inside = zipfile.ZipFile(self.bundle(tmp_path)).namelist()
        assert 'packs.json' in inside
        assert sum(one.endswith('.jpg') for one in inside) == \
            len(content.track_packs())

    def test_the_engine_reads_back_what_this_writes(self, tmp_path) -> None:
        """The property that matters: built here, read there."""
        from OpenGLContext.contentpacks import catalog
        packs = catalog.load_bundle(self.bundle(tmp_path),
                                    str(tmp_path / 'unpacked'))
        assert [one.key for one in packs] == \
            [one.key for one in content.registry()]

    def test_and_the_pictures_come_back_resolved(self, tmp_path) -> None:
        from OpenGLContext.contentpacks import catalog
        packs = catalog.load_bundle(self.bundle(tmp_path),
                                    str(tmp_path / 'unpacked'))
        shown = [one for one in packs if one.preview]
        assert len(shown) == len(content.track_packs())
        for one in shown:
            assert os.path.isfile(one.preview), one.key

    def test_it_is_small_enough_to_be_worth_fetching_first(self,
                                                           tmp_path) -> None:
        """A bundle the size of the content would be no saving at all."""
        assert os.path.getsize(self.bundle(tmp_path)) < 1024 * 1024


class TestATrackAndTheArtItShares:
    """A world is one directory, and the art is part of the world.

    Every path inside a baked track -- the tree meshes, their impostors, the
    ground cover -- resolves against the track's own root, so the art the four
    tracks share unpacks *into* each of them rather than beside them. It is one
    download either way: what repeats is the extraction.
    """

    @pytest.fixture
    def store(self, tmp_path):
        return content.store(root=str(tmp_path / 'content'))

    def track(self, key='glisteel/ashdown'):
        from OpenGLContext.contentpacks import catalog
        return catalog.pack_for_key(key, content.registry())

    def test_choosing_one_fetches_it_and_the_art(self, store) -> None:
        assert [one.key for one in content.wanted_for(self.track(), store)] == \
            ['glisteel/ashdown', 'glisteel/forest-art']

    def test_the_art_belongs_under_the_track(self, store) -> None:
        art = self.track('glisteel/forest-art')
        assert store.directory_for(art, within=self.track()) == \
            store.directory_for(self.track())

    def test_and_under_each_track_separately(self, store) -> None:
        """Having driven Ashdown says nothing about Beacon's trees."""
        one, two = self.track(), self.track('glisteel/beacon')
        art = self.track('glisteel/forest-art')
        os.makedirs(os.path.join(store.directory_for(one), art.marker))
        assert store.root_for(art, within=one) is not None
        assert store.root_for(art, within=two) is None

    def test_the_download_screen_does_not_offer_the_art_alone(self,
                                                              store) -> None:
        """A player cannot drive the art, and it never reads as arrived: it
        lives under the tracks rather than in a place of its own."""
        assert 'glisteel/forest-art' not in [one.key
                                             for one in content.offered(store)]
        assert [one.key for one in content.offered(store)] == [
            one.key for one in content.registry()
            if one.key != 'glisteel/forest-art']


class TestWhatTheRegistrySaysAWorldIsMadeOf:
    """A baked world's ``CREDITS.txt``, carried into the registry.

    Most of the art in a track is somebody else's under CC-BY, and the
    condition of using it is that the credit travels with it. The registry is
    where a player meets that credit -- the download screen reads it out of
    the entry before they agree to fetch anything -- so what the entry says
    has to be the whole notice.
    """

    def credit(self, tmp_path, text):
        os.makedirs(str(tmp_path), exist_ok=True)
        with open(os.path.join(str(tmp_path), 'CREDITS.txt'), 'w',
                  encoding='utf-8') as handle:
            handle.write(text)
        return release_assets()._world_credit(str(tmp_path))

    def test_it_is_what_the_bake_wrote(self, tmp_path) -> None:
        assert self.credit(tmp_path, 'Ground: ambientCG, CC0 1.0.') == \
            'Ground: ambientCG, CC0 1.0.'

    def test_a_long_notice_arrives_whole(self, tmp_path) -> None:
        """A credit is as long as the number of people owed one, and the
        four shipped tracks each owe five. Cutting it leaves an attribution
        that names a work and not who made it."""
        said = '; '.join("'Work %d' by Someone, CC-BY 4.0" % (one,)
                         for one in range(40))
        assert len(said) > 600
        assert self.credit(tmp_path, said) == said

    def test_a_bake_that_recorded_none_falls_back_to_the_trees(
            self, tmp_path) -> None:
        assert self.credit(tmp_path, '   ') == release_assets().TREE_CREDIT


class TestACreditReadsAsText:
    """A credit is shown to a player in the game, where a Markdown link is
    brackets and a path relative to a file they do not have."""

    def test_a_link_in_the_cars_credits_is_its_text(self, tmp_path) -> None:
        os.makedirs(str(tmp_path / 'cars'))
        with open(str(tmp_path / 'cars' / 'CREDITS.md'), 'w',
                  encoding='utf-8') as handle:
            handle.write('# Cars\n\nOurs, built by '
                         '[`tools/cars.py`](../../../tools/cars.py).\n')
        assert release_assets()._credits(str(tmp_path)) == \
            'Ours, built by tools/cars.py.'

    def test_and_so_is_one_in_a_track_s(self, tmp_path) -> None:
        assert TestWhatTheRegistrySaysAWorldIsMadeOf().credit(
            tmp_path, 'Ground by [ambientCG](https://ambientcg.com), CC0.') \
            == 'Ground by ambientCG, CC0.'

    def test_the_shipped_registry_carries_none(self) -> None:
        for one in content.registry():
            assert '](' not in one.copyright and '`' not in one.copyright, \
                one.key
