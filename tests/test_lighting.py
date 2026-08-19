"""What lights a bore, and what the car carries into one.

A bore's lamps are baked onto its lining, which lights the *tunnel* at any
distance for nothing. What that cannot do is light anything **in** the tunnel --
a car under a lamp has no idea it is -- and a renderer will bind only a handful
of lights in a frame. So the few fittings the driver is actually among become
real lights, and the car carries its own.
"""
import numpy as np
import pytest

from glisteel.lighting import (
    BUDGET,
    Headlights,
    Luminaires,
)


def _lamps(count=20, spacing=25.0):
    """A line of lamps up the Z axis, five metres over the road."""
    return np.stack([np.zeros(count), np.full(count, 5.0),
                     np.arange(count) * spacing], axis=-1)


class TestWhichLampsAreWorthALight:
    def test_a_road_with_no_lamps_lights_nothing(self):
        assert Luminaires(np.zeros((0, 3))).nearest((0.0, 0.0, 0.0)) == []

    def test_it_lights_the_ones_the_car_is_among(self):
        found = Luminaires(_lamps()).nearest((0.0, 0.0, 250.0))
        assert set(found) <= {8, 9, 10, 11, 12}

    def test_it_never_lights_more_than_it_is_allowed(self):
        found = Luminaires(_lamps(count=60, spacing=4.0), count=4)
        assert len(found.nearest((0.0, 0.0, 120.0))) == 4

    def test_the_nearest_is_among_them(self):
        found = Luminaires(_lamps()).nearest((0.0, 0.0, 252.0))
        assert 10 in found

    def test_a_car_nowhere_near_a_bore_lights_none_of_them(self):
        assert Luminaires(_lamps()).nearest((0.0, 0.0, 5000.0)) == []

    def test_how_far_it_reaches_is_its_own(self):
        near = Luminaires(_lamps(), reach=30.0)
        far = Luminaires(_lamps(), reach=200.0)
        assert len(near.nearest((0.0, 0.0, 250.0))) < \
            len(far.nearest((0.0, 0.0, 250.0)))

    def test_it_answers_the_same_way_twice(self):
        found = Luminaires(_lamps())
        assert found.nearest((0.0, 0.0, 250.0)) == found.nearest((0.0, 0.0, 250.0))

    def test_it_says_where_a_lamp_it_chose_is(self):
        found = Luminaires(_lamps())
        assert tuple(found.at(10)) == pytest.approx((0.0, 5.0, 250.0))

    def test_the_lamps_it_was_given_are_what_it_lights(self):
        assert len(Luminaires(_lamps(count=7)).lamps) == 7

    def test_a_world_with_no_bores_is_not_an_error(self):
        assert Luminaires(None).nearest((0.0, 0.0, 0.0)) == []


class TestTheBudget:
    """Eight lights in a frame, and the sun and its fill take two of them."""

    def test_the_lamps_and_the_headlights_fit_beside_the_sky(self):
        assert Luminaires(_lamps()).count + Headlights().count + 2 <= BUDGET

    def test_a_bore_is_lit_by_more_than_one_lamp(self):
        """One is a spot the car sits in; several is a tunnel going somewhere."""
        assert Luminaires(_lamps()).count >= 2


class TestTheHeadlights:
    def test_they_are_off_in_daylight(self):
        assert not Headlights().wanted(dark=False)

    def test_and_on_in_the_dark(self):
        assert Headlights().wanted(dark=True)

    def test_they_are_always_on_if_a_driver_asks(self):
        assert Headlights(always=True).wanted(dark=False)

    def test_they_can_be_switched_off_altogether(self):
        assert not Headlights(fitted=False).wanted(dark=True)

    def test_and_then_cost_nothing(self):
        assert Headlights(fitted=False).count == 0

    def test_they_point_where_the_car_points(self):
        aim = Headlights().aim((0.0, 0.0, -1.0))
        assert tuple(aim) == pytest.approx((0.0, -Headlights().dip, -1.0),
                                           abs=0.3)

    def test_and_a_little_down_at_the_road(self):
        """Dipped, because a beam on the horizon lights the sky."""
        assert Headlights().aim((0.0, 0.0, -1.0))[1] < 0.0

    def test_they_sit_at_the_front_of_the_car(self):
        assert Headlights().offset[2] < 0.0

    def test_a_beam_that_reaches_nowhere_is_no_beam(self):
        assert Headlights().reach > 10.0


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
