"""What every test in this suite is given, whether it asks or not."""
import pytest

from glisteel import content


@pytest.fixture(autouse=True)
def content_store_is_not_the_real_one(tmp_path_factory, monkeypatch):
    """Keep the suite out of the player's own downloaded content.

    A downloaded track is a track like any other, so `tracks.library` lists
    them beside the ones on disk wherever it is pointed -- which is right for
    a player and wrong for a test, because the answer then depends on what the
    machine running it happens to have fetched. A test that wants downloaded
    tracks builds a store and says so, as `test_content` does.
    """
    root = tmp_path_factory.mktemp('content')
    monkeypatch.setattr(content, 'store',
                        lambda root=str(root): content.ContentStore(
                            content.NAMESPACE, root=root))
