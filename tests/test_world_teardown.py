"""Putting a world away: its workers stopped, and what it drew given back."""

from glisteel.world import RaceWorld


class _Terrain:
    def __init__(self):
        self.done = []

    def shutdown(self):
        self.done.append('shutdown')

    def dispose(self):
        self.done.append('dispose')


def _world(terrain):
    world = RaceWorld.__new__(RaceWorld)
    world.terrain = terrain
    return world


def test_shutting_down_stops_every_worker_the_terrain_has():
    """The tile loaders and the ground cover's scatter thread alike."""
    terrain = _Terrain()
    _world(terrain).shutdown()
    assert terrain.done == ['shutdown']


def test_disposing_gives_back_what_the_terrain_drew():
    terrain = _Terrain()
    _world(terrain).dispose()
    assert terrain.done == ['dispose']


def test_a_world_with_nothing_streamed_has_nothing_to_put_away():
    world = _world(None)
    world.shutdown()
    world.dispose()
