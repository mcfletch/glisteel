"""The road as somewhere to be: its width, its lanes, and moving between them."""
import pytest

from glisteel import scenarios
from glisteel.zone import LANES, MARGIN, DrivableZone


class TestWhatItIs:
    def test_it_is_as_wide_as_the_carriageway(self) -> None:
        assert DrivableZone(width=7.2).width == pytest.approx(7.2)

    def test_its_lanes_divide_that_width(self) -> None:
        assert DrivableZone(width=7.2, lanes=2).lane_width == pytest.approx(3.6)

    def test_and_a_wider_road_carries_more_of_them(self) -> None:
        assert DrivableZone(width=14.4, lanes=4).lane_width == pytest.approx(3.6)

    def test_it_comes_off_a_course(self) -> None:
        course = scenarios.straight().course()
        zone = DrivableZone.of(course)
        assert zone.width == pytest.approx(course.carriageway_width)
        assert zone.lanes == course.lanes

    def test_a_road_of_no_width_has_a_zone_of_no_width(self) -> None:
        """A course that says nothing about how wide it is is not an error;
        it is a road with nowhere to be but its own line."""
        assert DrivableZone(width=0.0).clamp(3.0) == pytest.approx(0.0)


class TestWhereACarMayBe:
    ZONE = DrivableZone(width=7.2, lanes=2)

    def test_the_edge_is_drawn_in_by_the_margin(self) -> None:
        assert self.ZONE.edge == pytest.approx(7.2 / 2.0 - MARGIN)

    def test_a_line_off_the_road_is_brought_back_onto_it(self) -> None:
        assert self.ZONE.clamp(9.0) == pytest.approx(self.ZONE.edge)

    def test_on_either_side(self) -> None:
        assert self.ZONE.clamp(-9.0) == pytest.approx(-self.ZONE.edge)

    def test_and_one_on_the_road_is_left_alone(self) -> None:
        assert self.ZONE.clamp(1.8) == pytest.approx(1.8)

    def test_a_road_narrower_than_two_margins_still_answers(self) -> None:
        assert DrivableZone(width=1.0).clamp(4.0) == pytest.approx(0.0)


class TestTheLanes:
    ZONE = DrivableZone(width=7.2, lanes=2)
    WIDE = DrivableZone(width=14.4, lanes=4)

    def test_two_lanes_sit_either_side_of_the_crown(self) -> None:
        assert self.ZONE.centres() == pytest.approx((-1.8, 1.8))

    def test_four_lanes_run_left_to_right(self) -> None:
        assert self.WIDE.centres() == pytest.approx((-5.4, -1.8, 1.8, 5.4))

    def test_a_car_is_in_the_lane_it_is_nearest(self) -> None:
        assert self.WIDE.lane_at(1.6) == 2

    def test_and_one_beyond_the_road_is_in_the_last_lane(self) -> None:
        assert self.WIDE.lane_at(40.0) == 3

    def test_a_lane_centre_is_inside_the_zone(self) -> None:
        """A road too narrow for its own lanes is still a road to drive on."""
        narrow = DrivableZone(width=3.0, lanes=2)
        assert abs(narrow.centre_of(0)) <= narrow.edge

    def test_asking_for_a_lane_that_is_not_there_gives_the_nearest_one(self) -> None:
        assert self.ZONE.centre_of(7) == pytest.approx(self.ZONE.centre_of(1))


class TestMovingOver:
    ZONE = DrivableZone(width=14.4, lanes=4)

    def test_a_step_to_the_right_is_the_next_lane_over(self) -> None:
        assert self.ZONE.step(-1.8, 1) == pytest.approx(1.8)

    def test_and_a_step_to_the_left_is_the_one_before(self) -> None:
        assert self.ZONE.step(-1.8, -1) == pytest.approx(-5.4)

    def test_the_road_runs_out_and_the_step_stops_there(self) -> None:
        assert self.ZONE.step(-5.4, -1) == pytest.approx(-5.4)

    def test_a_car_between_lanes_steps_from_the_one_it_is_in(self) -> None:
        """Stepping from where the car *is* rather than from where the last
        step put it: a driver who has drifted asks for the lane beside them."""
        assert self.ZONE.step(-1.0, 1) == pytest.approx(1.8)


class TestWhichWayTheyGo:
    """Which lanes are this driver's own, and which have something coming."""

    TWO = DrivableZone(width=7.2, lanes=2)
    WIDE = DrivableZone(width=14.4, lanes=4)

    def test_the_right_hand_lanes_are_the_drivers_own(self) -> None:
        assert self.TWO.oncoming(1) is False

    def test_and_the_left_hand_ones_have_something_coming(self) -> None:
        assert self.TWO.oncoming(0) is True

    def test_half_of_a_four_lane_road_is_oncoming(self) -> None:
        assert [self.WIDE.oncoming(one) for one in range(4)] == [
            True, True, False, False]

    def test_a_one_way_road_has_none_of_it(self) -> None:
        assert not DrivableZone(width=14.4, lanes=4, two_way=False).oncoming(0)

    def test_the_lanes_a_driver_may_use_without_meeting_anyone(self) -> None:
        assert self.WIDE.own_lanes() == (2, 3)

    def test_and_all_of_a_one_way_road_is_theirs(self) -> None:
        zone = DrivableZone(width=14.4, lanes=4, two_way=False)
        assert zone.own_lanes() == (0, 1, 2, 3)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


def _course(closed=True, width=7.2, lanes=2):
    """A course only wide enough and closed enough to make a zone from."""
    import numpy as np

    from glisteel.world import Course
    line = np.stack([np.arange(9) * 10.0, np.zeros(9), np.zeros(9)], axis=-1)
    return Course(name='c', centreline=line, carriageway_width=width,
                  total_width=width + 3.4, closed=closed, length=80.0)


class TestWhereTheZoneComesFrom:
    def test_a_circuit_offers_every_lane_of_itself_to_drive_in(self) -> None:
        """Lapped one way round, so nothing on it is an oncoming lane."""
        zone = DrivableZone.of(_course(closed=True))
        assert not zone.two_way and not zone.oncoming(0)

    def test_a_road_keeps_half_of_itself_for_the_other_way(self) -> None:
        zone = DrivableZone.of(_course(closed=False))
        assert zone.two_way and zone.oncoming(0)

    def test_and_a_caller_can_say_which_it_is(self) -> None:
        assert not DrivableZone.of(_course(closed=False), two_way=False).two_way

    def test_a_road_that_does_not_say_how_it_is_divided_gets_the_default(self
                                                                        ) -> None:
        """The same tolerance the zone already shows a road that does not say
        whether it closes: what a course cannot answer is a road with one lane
        each way, which is what a road is.
        """
        class Narrow:
            carriageway_width = 7.2

        assert DrivableZone.of(Narrow()).lanes == LANES
