"""What the car reflects, and when that changes.

A metal surface is almost entirely its surroundings, so a car under a canopy
should carry the canopy in it and a car in a bore should carry the bore. The
road already knows which of those it is in at any distance along itself; this
turns that into an environment for the renderer to light and reflect the car
with, and changes it only when the road does.

No window: an environment is an array, and a transition is a station crossing a
number.
"""
import numpy as np
import pytest

from glisteel import reflections
from glisteel.world import Course, Structure


def _course(length=1000.0, count=101, structures=()):
    z = np.linspace(0.0, length, count)
    return Course(name='road', centreline=np.stack(
        [np.zeros(count), np.zeros(count), z], axis=-1),
        carriageway_width=7.2, total_width=10.6, closed=False, length=length,
        structures=tuple(structures))


ROAD = _course(structures=(Structure('tunnel', 300.0, 500.0),
                           Structure('bridge', 700.0, 800.0)))


class TestWhereTheRoadIs:
    def test_inside_a_bore_it_is_a_tunnel(self) -> None:
        assert reflections.context_at(ROAD, 400.0) == reflections.TUNNEL

    def test_over_a_bridge_it_is_a_viaduct(self) -> None:
        assert reflections.context_at(ROAD, 750.0) == reflections.VIADUCT

    def test_and_between_them_it_is_the_forest(self) -> None:
        assert reflections.context_at(ROAD, 100.0) == reflections.FOREST
        assert reflections.context_at(ROAD, 600.0) == reflections.FOREST

    def test_the_ends_of_a_structure_belong_to_it(self) -> None:
        assert reflections.context_at(ROAD, 300.0) == reflections.TUNNEL
        assert reflections.context_at(ROAD, 500.0) == reflections.TUNNEL
        assert reflections.context_at(ROAD, 500.1) == reflections.FOREST


class TestWhatEachPlaceLooksLike:
    @pytest.fixture(params=reflections.CONTEXTS)
    def sky(self, request):
        return request.param, reflections.panorama(request.param)

    def test_it_is_an_equirectangular_image(self, sky) -> None:
        _context, image = sky
        assert image.ndim == 3 and image.shape[2] == 3
        assert image.shape[1] == image.shape[0] * 2, 'not equirectangular'
        assert np.isfinite(image).all() and (image >= 0.0).all()

    def test_it_is_the_same_every_time(self, sky) -> None:
        """A car does not shimmer because the environment was regenerated."""
        context, image = sky
        assert np.array_equal(image, reflections.panorama(context))

    def test_a_bore_is_darker_than_the_open_road(self) -> None:
        assert (reflections.panorama(reflections.TUNNEL).mean()
                < reflections.panorama(reflections.FOREST).mean())

    def test_the_wood_closes_the_horizon_in(self) -> None:
        """Trees stand around a forest road, not open sky.

        A bright band at eye level is what a car reflects along its flanks, and
        a car that reflects sky all the way round washes out to silver wherever
        it is -- which would make the environment pointless.
        """
        assert (_horizon(reflections.panorama(reflections.FOREST))
                < 0.5 * _horizon(reflections.panorama(reflections.VIADUCT)))

    def test_a_canopy_is_darker_overhead_than_open_sky(self) -> None:
        """Which is the whole point: the car carries the trees above it."""
        assert (_overhead(reflections.panorama(reflections.FOREST))
                < _overhead(reflections.panorama(reflections.VIADUCT)))

    def test_in_the_open_the_sky_is_brighter_than_the_road_under_it(self) -> None:
        for context in (reflections.VIADUCT, reflections.OPEN):
            image = reflections.panorama(context)
            assert _overhead(image) > _underfoot(image), context

    def test_and_under_cover_it_is_not(self) -> None:
        """A canopy overhead and a bore around are darker than the road they
        stand over, which is the whole reason for drawing them."""
        for context in (reflections.FOREST, reflections.TUNNEL):
            image = reflections.panorama(context)
            assert _overhead(image) < _underfoot(image) * 1.6, context


class TestChangingItOnTheWay:
    def _watcher(self):
        applied = []
        return applied, reflections.Reflections(ROAD, apply=applied.append)

    def test_it_sets_an_environment_to_begin_with(self) -> None:
        applied, watching = self._watcher()
        watching.update((0.0, 0.0, 100.0))
        assert len(applied) == 1
        assert watching.context == reflections.FOREST

    def test_it_changes_when_the_road_does(self) -> None:
        applied, watching = self._watcher()
        watching.update((0.0, 0.0, 100.0))
        watching.update((0.0, 0.0, 400.0))
        assert watching.context == reflections.TUNNEL
        assert len(applied) == 2

    def test_and_not_while_the_road_stays_the_same(self) -> None:
        """A probe rebuilt every frame is a probe rebuilt for nothing."""
        applied, watching = self._watcher()
        for station in (100.0, 120.0, 180.0, 240.0):
            watching.update((0.0, 0.0, station))
        assert len(applied) == 1

    def test_it_hands_over_the_panorama_for_where_it_is(self) -> None:
        applied, watching = self._watcher()
        watching.update((0.0, 0.0, 400.0))
        assert np.array_equal(applied[-1], reflections.panorama(reflections.TUNNEL))


def _overhead(image):
    """The mean of the top eighth of an equirectangular image."""
    return float(image[: max(image.shape[0] // 8, 1)].mean())


def _horizon(image):
    """The mean of the band around eye level."""
    middle = image.shape[0] // 2
    return float(image[middle - 2:middle + 2].mean())


def _underfoot(image):
    return float(image[-max(image.shape[0] // 8, 1):].mean())
