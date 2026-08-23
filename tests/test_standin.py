"""An autopilot at the controls, driving the way a player does.

A way of driving is only worth what it is like to drive, and the only honest
way to find that out without a person is to have something press the same keys
a person would and see what the car does about it. That is what a stand-in is:
it decides what a driver decides -- how fast, and when to pull out -- and then
asks for it through the controls rather than reaching past them.
"""
import dataclasses
from typing import Any

import numpy as np
import pytest

from glisteel import scenarios, schemes
from glisteel.driver import (
    ALONGSIDE,
    CROSSING_MARGIN,
    FOLLOWING_LEAST,
    FOLLOWING_SECONDS,
    PASSING_GAP,
    PASSING_REACH,
    SLIP_LONGEST,
    STILL_ON,
    DriverStyle,
    StandIn,
)
from glisteel.schemes import CROSSING
from glisteel.session import Session

STEP = 1.0 / 120.0


def _session(piece='circuit', traffic=0, **named):
    session = Session(scenarios.named(piece).world(traffic=traffic), **named)
    session.run.go()
    return session


def _open_road(traffic=6):
    """A circuit with straights on it, whose bends allow more than the traffic
    on it is doing.

    Both halves matter. Passing is a decision about *speed*, so a road where
    the corners hold a car under the limit has nothing on it worth the other
    lane. And it is a decision about *sight*: the view round a bend of radius
    *r* runs `sqrt(8 * r * clear)`, which on a ring small enough to drive round
    in a test is a hundred metres, against the hundred and forty that getting
    by an 80 km/h car at racing speed wants. A ring is a road nobody overtakes
    on, whoever is driving, and a test of overtaking held on one is a test of
    the road (:func:`~glisteel.scenarios.oval`).
    """
    session = Session(scenarios.oval().world(traffic=traffic))
    session.run.go()
    return session


def _crossable(stand_in, session, speed=0.0, margin=1.2):
    """A gap comfortably longer than the road a pass needs to cross in.

    Read from the speed the car is actually doing rather than written down. A
    test about *sight*, or about what is coming the other way, has to get past
    the crossing-room check before it reaches the check it is about
    (:meth:`~glisteel.driver.StandIn.room_to_cross`), and a distance chosen for
    one tune of the car stops meaning "comfortably" when the car is retuned.

    Comfortably, and no more: a gap far longer than the crossing needs is one
    the pass spends its whole allowance closing, and the answer comes back
    "it would take too long" instead of the reason the test is about.
    """
    crossing = CROSSING * CROSSING_MARGIN
    closing = max(float(session.car.speed()) - float(speed), 0.0)
    pull = max(stand_in.pilot.style.pull, 1e-6)
    return margin * (closing * crossing + 0.5 * pull * crossing * crossing)


def _driving(session, seconds, driver=None):
    if driver is not None:
        session.driver = driver
    for _ in range(int(round(seconds / STEP))):
        session.advance(STEP)
    return session


#: Where along the watched lap the questions below are asked, in seconds.
MARKS = (30.0, 40.0, 45.0, 60.0)


@dataclasses.dataclass
class _Lap:
    """A minute of an open road, and what the stand-in was seen to do with it.

    Written down as it happened, because most of it cannot be read afterwards:
    how long the car spent on the other side of the road, and what was true at
    the moment it first got by something, are gone by the time the lap ends.
    """

    session: Any
    stand_in: Any
    #: Seconds spent on the other side of the road.
    across_seconds: float = 0.0
    #: The throttle, sampled every step spent out in the other lane.
    throttle_out: list = dataclasses.field(default_factory=list)
    #: What was true the first time a car was got by, or empty for a lap in
    #: which none was.
    first_pass: dict = dataclasses.field(default_factory=dict)
    #: What the drive looked like at each of :data:`MARKS`.
    at: dict = dataclasses.field(default_factory=dict)


def _reading(session, stand_in):
    """The state of the drive, as of now."""
    index, _distance = session.course.nearest(session.car.position)
    return {'passes': stand_in.passes,
            'speed': session.car.speed(),
            'corner_speed': session.course.corner_speed(index),
            'ahead': session.traffic_ahead(PASSING_REACH)}


@pytest.fixture(scope='module')
def open_road_lap():
    """One minute of an open road, driven once and watched all the way.

    Several of the questions below are about the same drive -- how long the car
    spent in the other lane, how many cars it got by, what the throttle was
    doing while it was out there, and what the road allowed at the moment it
    was asked. A lap is a minute of physics whatever is asked about it, so it
    is driven once and written down; the marks are far enough apart that each
    is the drive a test used to make for itself.
    """
    session = _open_road()
    stand_in = StandIn(schemes.named('lanes'))
    session.driver = stand_in
    lap = _Lap(session=session, stand_in=stand_in)
    marks = list(MARKS)
    for step in range(int(round(max(MARKS) / STEP))):
        session.advance(STEP)
        if stand_in.across(session) * session.lane < 0.0:
            lap.across_seconds += STEP
        if stand_in.overtaking:
            lap.throttle_out.append(bool(stand_in.source.holding('throttle')))
        if stand_in.passes and not lap.first_pass:
            lap.first_pass = {
                'overtaking': stand_in.overtaking,
                'holding_right': stand_in.source.holding('right')}
        if marks and (step + 1) * STEP >= marks[0] - 1e-9:
            lap.at[marks.pop(0)] = _reading(session, stand_in)
    return lap


class TestItDrivesThroughTheControls:
    def test_it_is_somebody_a_run_can_be_handed_to(self) -> None:
        session = _session()
        stand_in = StandIn(schemes.named('lanes'))
        session.driver = stand_in
        assert len(session.advance(STEP).position) == 3

    def test_it_presses_the_throttle_rather_than_asking_for_one(self) -> None:
        """What reaches the car is what the *scheme* made of a held key, which
        is the whole point: a stand-in that returned a pedal would be measuring
        the road rather than the controls."""
        session = _session()
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        assert stand_in.source.holding('throttle')

    def test_and_lifts_off_once_it_is_going_fast_enough(self) -> None:
        session = _session()
        stand_in = StandIn(schemes.named('lanes'),
                           style=DriverStyle(maximum_speed=1.0))
        _driving(session, 2.0, stand_in)
        assert not stand_in.source.holding('throttle')

    @staticmethod
    @pytest.fixture(scope='class')
    def round_a_circuit():
        """Forty seconds of a circuit, driven once: whether the run survived
        it and where on the road it ended up are two readings of one lap."""
        return _driving(_session(), 40.0, StandIn(schemes.named('lanes')))

    def test_it_gets_a_car_round_a_circuit(self, round_a_circuit) -> None:
        assert round_a_circuit.ended is None
        assert round_a_circuit.timing.laps

    def test_and_stays_on_the_road_while_it_does(self, round_a_circuit) -> None:
        session = round_a_circuit
        _index, off = session.course.nearest(session.car.position)
        assert off < session.course.carriageway_width / 2.0

    def test_it_carries_the_advice_its_way_of_driving_gets(self) -> None:
        assert StandIn(schemes.named('lanes')).advises
        assert not StandIn(schemes.named('wheel')).advises


class TestHowFastItMeansToGo:
    """It is racing, not driving home. What the road is posted at is what
    everything else on it is doing; a racer is going twice that where the
    corners let it."""

    def test_it_aims_at_two_hundred(self) -> None:
        from glisteel.driver import RACING_KPH
        session = _open_road()
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        assert stand_in.pilot.style.maximum_speed == pytest.approx(
            RACING_KPH / 3.6)

    def test_a_pace_it_was_given_is_the_pace_it_drives(self) -> None:
        session = _open_road()
        wanted = DriverStyle(maximum_speed=33.0)
        stand_in = StandIn(schemes.named('lanes'), style=wanted)
        stand_in.controls(session, STEP)
        assert stand_in.pilot.style.maximum_speed == pytest.approx(33.0)

    def test_and_it_is_far_faster_than_the_traffic_it_shares_the_road_with(
            self) -> None:
        from glisteel.traffic import SPEED_LIMIT
        session = _open_road()
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        assert stand_in.pilot.style.maximum_speed > SPEED_LIMIT * 2.0

    def test_the_corners_still_decide_what_it_actually_does(
            self, open_road_lap) -> None:
        """Two hundred is what it *aims* for; a bend is still a bend."""
        found = open_road_lap.at[30.0]
        assert found['speed'] <= found['corner_speed'] * 1.05


class TestKeepingBack:
    """A following distance is a distance, not a speed to match.

    The racing rule -- the fastest you could still stop from in the room you
    have -- says "go their speed" at every gap shorter than the one you want, so
    a gap closed up in a corner is a gap that never opens again. A road driver
    backs off until it has its distance.
    """

    @staticmethod
    def _following(speed=30.0):
        """A stand-in that has been driven, so it knows what gap it wants."""
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        stand_in.pilot.style.standing_gap = max(FOLLOWING_SECONDS * speed,
                                                FOLLOWING_LEAST)
        return stand_in, stand_in.pilot.style.standing_gap

    def test_the_gap_it_wants_is_a_time_rather_than_a_distance(self) -> None:
        """A gap that is comfortable at a crawl is a second and a half at two
        hundred, which is no gap at all.

        Asked of the driver rather than of one field: how far back to sit is
        every driver's rule now
        (:meth:`~glisteel.driver.Autopilot.following_gap`), and what a stand-in
        adds to it is that a *pass* is not a follow.
        """
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        session.driver = stand_in
        for _ in range(int(round(8.0 / STEP))):
            session.advance(STEP)
        speed = session.car.speed()
        assert speed > 20.0, 'never got up to a speed worth a time gap'
        assert stand_in.pilot.following_gap(speed) == pytest.approx(
            max(FOLLOWING_SECONDS * speed, FOLLOWING_LEAST), abs=1.0)

    def test_and_a_pass_is_not_a_follow(self) -> None:
        """Out getting by something, the gap is the racing one: held to a
        following distance all the way past, the car never draws alongside."""
        from glisteel.driver import PASSING_GAP
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        session.driver = stand_in
        session.advance(STEP)
        stand_in.overtaking = True
        stand_in.pedals(session, STEP)
        assert stand_in.pilot.following_gap(60.0) == pytest.approx(PASSING_GAP)

    def test_at_its_own_distance_it_asks_for_nothing(self) -> None:
        """Matching the car in front at the gap it wants is already the racing
        rule's answer; this is only about being closer than that."""
        stand_in, gap = self._following()
        assert stand_in.keeping_back(40.0, gap, 25.0) == 40.0

    def test_closer_than_that_it_aims_slower(self) -> None:
        stand_in, gap = self._following()
        assert stand_in.keeping_back(40.0, gap / 2.0, 25.0) < 25.0

    def test_and_the_closer_it_is_the_slower_it_aims(self) -> None:
        stand_in = StandIn(schemes.named('lanes'))
        near = stand_in.keeping_back(40.0, 5.0, 25.0)
        further = stand_in.keeping_back(40.0, 15.0, 25.0)
        assert near < further

    def test_further_back_it_is_the_road_that_decides(self) -> None:
        stand_in, gap = self._following()
        assert stand_in.keeping_back(30.0, gap * 3, 25.0) == 30.0

    def test_and_it_never_asks_to_go_backwards(self) -> None:
        stand_in = StandIn(schemes.named('lanes'))
        assert stand_in.keeping_back(40.0, 0.0, 25.0) >= 0.0

    def test_it_opens_a_gap_it_has_closed_up(self, open_road_lap) -> None:
        """Which is the whole point: a lap spent six metres off somebody's
        bumper is a lap one touch of their brakes ends."""
        found = open_road_lap.at[40.0]['ahead']
        assert found is None or found[0] > 10.0


class TestDecidingToPass:
    def test_an_empty_road_is_no_reason_to_change_lanes(self) -> None:
        session = _session()
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 6.0, stand_in)
        assert not stand_in.overtaking

    def test_and_neither_is_something_going_as_fast_as_you_want_to(self
                                                                  ) -> None:
        """Worth is measured against what the *road* allows, so something
        already doing that is not worth the other lane however fast it is.

        Asked of the rule rather than of a drive: what the traffic does on a
        lap is its own business, and a car that brakes for something its driver
        saw is a car worth getting past on any road.
        """
        session = _session(traffic=6)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 6.0, stand_in)
        index, _distance = session.course.nearest(session.car.position)
        allowed = stand_in.pilot.road_speed(index, session.car.speed())
        assert not stand_in.worth_passing(
            _Ahead(session, gap=60.0, speed=allowed))

    def test_but_something_slower_than_the_road_allows_is(self) -> None:
        session = _session(traffic=6)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 6.0, stand_in)
        assert stand_in.worth_passing(_Ahead(session, gap=60.0, speed=0.0))

    def test_a_pass_puts_the_car_on_the_other_side_of_the_road(
            self, open_road_lap) -> None:
        """The thing the counter cannot say: a pass is the car *being* in the
        other lane, not a decision that one was called for."""
        assert open_road_lap.across_seconds > 1.0

    def test_and_it_gets_by_what_it_pulled_out_for(self, open_road_lap) -> None:
        """Counted only where the car it pulled out for ends up behind it."""
        assert open_road_lap.at[60.0]['passes'] > 0

    def test_it_does_not_count_a_pass_it_never_made(self) -> None:
        """An empty road offers nothing to get by, so nothing is got by."""
        session = _session()
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 30.0, stand_in)
        assert stand_in.passes == 0

    def test_something_slower_in_front_is(self, open_road_lap) -> None:
        assert open_road_lap.at[45.0]['passes'] > 0

    def test_and_it_comes_back_to_its_own_side_afterwards(
            self, open_road_lap) -> None:
        """Read the moment a pass is counted rather than at some later clock
        time: on a road there is passing to be done on, a driver a minute in
        is usually part-way through the next one, and that says nothing about
        what it did with the one before."""
        assert open_road_lap.first_pass, 'it never got by anything'
        assert not open_road_lap.first_pass['overtaking']
        assert open_road_lap.first_pass['holding_right']

    def test_a_quick_pass_needs_less_room_than_a_slow_one(self) -> None:
        """How long a pass takes is what decides whether there is room for it:
        getting by something stopped is a moment, and getting by something
        doing almost your own speed is most of a straight."""
        session = _open_road()
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        stopped = stand_in.pass_seconds(40.0, 60.0, 0.0)
        crawling = stand_in.pass_seconds(40.0, 60.0, 35.0)
        assert stopped < crawling

    def test_and_getting_by_something_stopped_is_quick(self) -> None:
        session = _open_road()
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        assert stand_in.pass_seconds(40.0, 30.0, 0.0) < 6.0

    def test_it_pulls_out_for_something_stopped_on_a_clear_road(self) -> None:
        """The case a player would shout about: the road ahead is empty and the
        thing in front is not moving."""
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        road = _Coming(session, oncoming=None)
        assert stand_in.room_to_finish(road, stand_in.planning(road, 30.0, 0.0)[0])

    def test_but_not_into_something_that_is_nearly_on_top_of_it(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        road = _Coming(session, gap=60.0, closing=60.0)
        assert not stand_in.room_to_finish(
            road, stand_in.planning(road, 30.0, 0.0)[0])

    def test_it_will_not_pull_out_into_something_coming(self) -> None:
        """The lane switch does no checks of its own, so this is the driver's
        job -- exactly as it is the player's in easy mode."""
        session = _session(traffic=6)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        road = _Coming(session, gap=30.0, closing=60.0)
        assert not stand_in.room_to_finish(
            road, stand_in.planning(road, 40.0, 10.0)[0])

    def test_and_will_where_the_road_is_clear(self) -> None:
        session = _session(traffic=6)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        road = _Coming(session, oncoming=None)
        assert stand_in.room_to_finish(road, stand_in.planning(road, 40.0, 10.0)[0])


class TestGettingOnWithThePass:
    """A pass is an acceleration. Whatever the sums said was possible was said
    about a car going the speed the road allows, so a driver that pulls out and
    then sits at the speed of what it is passing is a driver whose pass takes
    for ever and who is beside the other car when the road runs out."""

    def test_it_does_not_slow_for_the_car_it_is_passing(
            self, open_road_lap) -> None:
        out = open_road_lap.throttle_out
        assert out, 'it never pulled out'
        assert sum(out) / len(out) > 0.5, (
            'the throttle was down for %.0f%% of the time it spent passing'
            % (100.0 * sum(out) / len(out)))

    def test_it_runs_closer_to_what_it_is_passing_than_it_would_follow(self):
        """The gap that keeps a driver comfortable behind a car is the gap
        that stops them ever drawing alongside one."""
        session = _open_road()
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        following = stand_in.pilot.style.standing_gap
        stand_in.overtaking = True
        stand_in.pedals(session)
        assert stand_in.pilot.style.standing_gap == PASSING_GAP < following

    def test_and_it_is_still_a_gap(self) -> None:
        """Room to stop in, so a pass that goes wrong is a pass given up
        rather than a car driven into the back of."""
        assert PASSING_GAP > 0.0


class TestGivingAPassUp:
    """The road can stop being clear after the decision was made.

    On a road, that is: what makes a pass worth giving up is the thing coming
    the other way, and on a circuit everybody laps the same way round.
    """

    def _out_there(self, session, ahead=40.0):
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        stand_in.overtaking = True
        stand_in.passing = _Car(ahead)
        return stand_in

    def test_it_gives_up_while_it_can_still_drop_in_behind(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._out_there(session, ahead=40.0)
        assert stand_in.abandoning(_Coming(session, gap=30.0, closing=80.0))

    def test_but_finishes_once_it_is_alongside(self) -> None:
        """Swerving back across the crown onto a car that is beside you is
        worse than whatever is coming."""
        session = _open_road(traffic=0)
        stand_in = self._out_there(session, ahead=1.0)
        assert not stand_in.abandoning(_Coming(session, gap=30.0, closing=80.0))

    def test_and_carries_on_while_the_road_is_still_clear(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._out_there(session, ahead=40.0)
        assert not stand_in.abandoning(_Coming(session, oncoming=None))

    def test_a_circuit_offers_nothing_to_give_one_up_for(self) -> None:
        """Nothing comes the other way round a circuit, so the lane a racer
        pulls into stays theirs for as long as they need it."""
        session = _open_road(traffic=0)
        stand_in = self._out_there(session, ahead=40.0)
        assert not stand_in.abandoning(
            _Coming(session, gap=30.0, closing=80.0, two_way=False))


class TestRoadNobodyHasSeen:
    """An empty look-ahead is not an empty road, and how much road a driver
    has actually looked at is what the bend in front of them allows."""

    def test_what_is_not_visible_is_not_counted_as_clear(self) -> None:
        """An empty look-ahead offers the road the driver can *see*, which is
        the road's own answer, and not the whole of the reach."""
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        room, _closing = stand_in.seen(_Coming(session, oncoming=None,
                                               sight=123.0))
        assert room == pytest.approx(123.0)

    def test_and_the_road_is_what_says_how_much_that_is(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        index, _distance = session.course.nearest(session.car.position)
        assert session.sight() == pytest.approx(
            session.course.sight_ahead(index))

    def test_a_blind_bend_offers_less_of_it_than_a_straight(self) -> None:
        tight = Session(scenarios.circuit(radius_x=120.0, radius_z=120.0)
                        .world(traffic=0))
        tight.run.go()
        wide = _open_road(traffic=0)
        for one in (tight, wide):
            one.advance(STEP)
        assert (tight.course.sight_ahead(0) < wide.course.sight_ahead(0))

    def test_and_what_is_actually_seen_is_still_what_counts(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        assert stand_in.seen(_Coming(session, gap=50.0, closing=70.0)) \
            == (50.0, 70.0)


class _Car:
    """A traffic car a fixed distance up the road, standing still."""

    def __init__(self, along, speed=0.0):
        self.along = float(along)
        self.speed = float(speed)

    def position(self):
        return np.array([0.0, 0.0, 0.0])


class TestAPassIsABetYouCanGetOutOf:
    """A pass is planned to *finish*: the road that can be seen has to cover
    the whole manoeuvre before the driver is entitled to start one, because
    the way out disappears part-way through. While what is being passed is
    still in front there is always the lift-off and drop in behind it; once
    the two cars are alongside, coming back across the crown is coming back
    onto the other car, and finishing is the only half of the choice left.

    So the question is asked again every frame until that point, against what
    is *left* of the pass rather than what it started as -- and the bet is what
    the driver cannot see. A road clear to the end of a straight is clear to
    the end of the straight; what comes round the bend after it was never
    there to be looked at. The reward is the time, the stake is meeting it
    committed, and :data:`~glisteel.driver.PASS_MARGIN` is the appetite.
    """

    @staticmethod
    @pytest.fixture(scope='class')
    def rolling():
        """A car eight seconds into an open road, with nobody else on it.

        Every test in this class asks the *rule* a question -- how long a pass
        would take, and whether the road holds it -- of a car that is up to
        speed on a road with some. The eight seconds are what gets it there,
        they are the same eight seconds every time, and none of these tests
        moves the car.
        """
        session = _open_road(traffic=0)
        _driving(session, 8.0, StandIn(schemes.named('lanes')))
        return session

    @staticmethod
    @pytest.fixture
    def stand_in(rolling):
        """A stand-in of this test's own, looking at that car.

        Its own, because several of these tests set what it is in the middle
        of doing; one step in, because the rules asked about below read the
        pilot it makes on its first (:meth:`~glisteel.driver.StandIn.pilot`).
        """
        mine = StandIn(schemes.named('lanes'))
        mine.controls(rolling, STEP)
        return mine

    def test_a_road_that_lasts_the_whole_pass_is_enough(self, rolling, stand_in) -> None:
        road = _Coming(rolling, oncoming=None, sight=800.0)
        assert stand_in.room_to_finish(road, stand_in.planning(road, 40.0, 22.0)[0])

    def test_and_one_that_only_lasts_long_enough_to_get_back_is_not(self, rolling, stand_in) -> None:
        """The distinction the mechanic lives on: 260 m is room to pull out,
        look and drop in behind again, and it is not room to get by an 80 km/h
        car at racing speed -- so it is not a pass."""
        road = _Coming(rolling, oncoming=None, sight=260.0)
        seconds, _quick = stand_in.planning(road, 40.0, 22.0)
        assert seconds > stand_in.getting_back()
        assert not stand_in.room_to_finish(road, seconds)

    def test_but_a_blind_bend_is_not_even_that(self, rolling, stand_in) -> None:
        road = _Coming(rolling, oncoming=None, sight=40.0)
        assert not stand_in.room_to_finish(road, stand_in.planning(road, 40.0, 22.0)[0])

    def test_nor_is_a_car_already_coming_the_other_way(self, rolling, stand_in) -> None:
        road = _Coming(rolling, gap=90.0, closing=60.0)
        assert not stand_in.room_to_finish(road, stand_in.planning(road, 40.0, 22.0)[0])

    def test_a_pass_that_would_be_over_at_once_still_needs_getting_back(self, rolling, stand_in):
        """Whatever the sums say the manoeuvre costs, the road has to hold the
        way out of it as well."""
        assert not stand_in.room_to_finish(
            _Coming(rolling, oncoming=None, sight=20.0), 0.0)

    def test_the_bet_is_off_the_moment_it_stops_being_a_bet(self, rolling, stand_in) -> None:
        """Something appears: the pass is given up while there is still room
        to drop in behind."""
        stand_in.overtaking = True
        stand_in.passing = _Car(40.0)
        assert stand_in.abandoning(_Coming(rolling, gap=90.0, closing=60.0))

    def test_and_it_is_judged_on_what_is_left_of_the_pass(self, rolling, stand_in) -> None:
        """Half-way past, the road a driver still needs is a fraction of the
        road they needed to start: a pass nearly done is not given up on the
        length it would have taken from the beginning."""
        stand_in.overtaking = True
        road = _Coming(rolling, oncoming=None, sight=300.0)
        stand_in.passing = _Car(200.0, speed=22.0)
        assert stand_in.abandoning(road)
        stand_in.passing = _Car(ALONGSIDE + 1.0, speed=22.0)
        assert not stand_in.abandoning(road)

    def test_once_alongside_there_is_nowhere_left_to_go_but_past(self, rolling, stand_in) -> None:
        stand_in.overtaking = True
        stand_in.passing = _Car(ALONGSIDE - 1.0, speed=22.0)
        assert not stand_in.abandoning(_Coming(rolling, gap=30.0, closing=60.0))


class _Ahead:
    """A session saying exactly what is in front, and what the road offers."""

    two_way = True

    def __init__(self, session, gap=0.0, speed=0.0, sight=800.0, oncoming=None):
        self._session = session
        self._found = (gap, speed)
        self._sight = float(sight)
        self._oncoming = oncoming

    def __getattr__(self, name):
        return getattr(self._session, name)

    def traffic_ahead(self, reach=0.0):
        return self._found

    def lane_ahead(self, across, reach=0.0):
        return None

    def lane_clear(self, across, ahead=0.0, behind=0.0):
        return True

    def sight(self, over=0.0):
        return self._sight

    def oncoming(self, reach=None):
        return self._oncoming


class _Coming:
    """A session saying exactly what is coming the other way."""

    def __init__(self, session, gap=0.0, closing=0.0, oncoming=(),
                 two_way=True, sight=800.0):
        self._session = session
        self._found = (None if oncoming is None else (gap, closing))
        self.two_way = two_way
        self._sight = float(sight)

    def sight(self, over=0.0):
        return self._sight

    def __getattr__(self, name):
        return getattr(self._session, name)

    def oncoming(self, reach=0.0):
        return self._found

    def along(self, other):
        return float(getattr(other, 'along', 0.0))


class TestWhatIsComingTheOtherWay:
    """A road with eight cars on it has something coming the other way, and
    ten seconds of driving is enough to meet one -- so the questions below are
    asked outright rather than under an ``if``: a road that turns out to be
    empty is a failure of the scenario, not a test with nothing to say.
    """

    #: How far down the road the driver is looking, in metres.
    REACH = 400.0

    @staticmethod
    @pytest.fixture(scope='class')
    def two_way():
        """Ten seconds of a road with traffic both ways, driven once."""
        return _driving(_session(traffic=8), 10.0,
                        StandIn(schemes.named('lanes')))

    def test_an_empty_road_has_nothing_on_it(self) -> None:
        assert _session().oncoming() is None

    def test_a_car_the_other_way_is_seen(self, two_way) -> None:
        found = two_way.oncoming(reach=self.REACH)
        assert found is not None, 'nothing came the other way'
        assert found[0] > 0.0

    def test_and_it_is_closing_faster_than_anything_alongside(self, two_way):
        """Two cars going opposite ways close at the sum of their speeds, which
        is what decides whether there is room to pass."""
        found = two_way.oncoming(reach=self.REACH)
        assert found is not None, 'nothing came the other way'
        assert found[1] >= two_way.car.speed()

    def test_nothing_in_my_own_lane_counts_as_oncoming(self, two_way) -> None:
        ahead = two_way.traffic_ahead()
        found = two_way.oncoming(reach=self.REACH)
        assert ahead is not None and found is not None, (
            'the road had nothing in one of its lanes')
        assert not np.isclose(ahead[0], found[0])


class TestWhatCountsAsAPass:
    """Cars got past. A manoeuvre given up got past nothing, and counting it
    turns the one number a drive is judged on into a count of attempts."""

    def _out_there(self, session, ahead=40.0):
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        stand_in.overtaking = True
        stand_in.passing = _Car(ahead)
        return stand_in

    def test_one_given_up_on_is_not_counted(self) -> None:
        from glisteel.driver import PASS_LONGEST
        session = _open_road(traffic=0)
        stand_in = self._out_there(session)
        stand_in.passing_for = PASS_LONGEST + 1.0
        stand_in.lanes(session, STEP)
        assert not stand_in.overtaking and stand_in.passes == 0

    def test_and_neither_is_one_abandoned_for_something_coming(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._out_there(session)
        stand_in.lanes(_Coming(session, gap=30.0, closing=80.0), STEP)
        assert not stand_in.overtaking and stand_in.passes == 0

    def test_but_getting_by_something_is(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._out_there(session, ahead=-60.0)
        stand_in.lanes(_Coming(session, oncoming=None), STEP)
        assert not stand_in.overtaking and stand_in.passes == 1


class TestLookingAsFarAsItIsGoing:
    """A fixed look-ahead is a speed limit in disguise. Stopping from two
    hundred kilometres an hour takes a quarter of a kilometre, so a driver
    watching a hundred metres of road is a driver who meets a stopped car with
    no room left to stop in -- however early it starts braking."""

    def test_it_watches_further_the_faster_it_is_going(self) -> None:
        stand_in = StandIn(schemes.named('lanes'))
        assert stand_in.looking(55.0) > stand_in.looking(20.0)

    def test_far_enough_to_stop_in(self) -> None:
        stand_in = StandIn(schemes.named('lanes'))
        braking = stand_in.pilot.style.braking
        for speed in (20.0, 40.0, 55.0):
            assert stand_in.looking(speed) > speed * speed / (2.0 * braking)

    def test_and_never_less_than_the_road_it_passes_on(self) -> None:
        stand_in = StandIn(schemes.named('lanes'))
        assert stand_in.looking(0.0) >= PASSING_REACH


class TestNotPullingOutTooLateToGetAcross:
    """The lane change takes seconds, and a car closing on what it is passing
    covers the gap in that time or it does not. Pulling out with a car length
    to spare is arriving in the other lane after the crash."""

    def test_there_is_room_to_cross_when_the_gap_is_a_long_way_off(self):
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        assert stand_in.room_to_cross(session, gap=200.0, speed=10.0)

    def test_and_none_when_it_is_about_to_be_arrived_at(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 6.0, stand_in)
        assert session.car.speed() > 1.0
        assert not stand_in.room_to_cross(session, gap=6.0, speed=0.0)

    def test_matching_the_speed_in_front_is_not_room_by_itself(self):
        """Sitting behind something at its own speed the gap is not closing --
        until the driver floors it, which is what pulling out is. See
        :class:`TestTheCrossingCountsTheAcceleration`."""
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        assert not stand_in.room_to_cross(session, gap=12.0,
                                          speed=session.car.speed())
        assert stand_in.room_to_cross(session, gap=120.0,
                                      speed=session.car.speed())


class TestARunThatIsARace:
    """What the autopilot aims for on an open road is a racing speed, not the
    speed somebody driving there would pick. A stand-in held to an ordinary
    driver's maximum is one whose lap is decided by a number nobody chose for
    this road."""

    def _config(self, **named):
        from glisteel.options import Options
        return Options(world='x', autopilot=True, control='lanes', **named)

    def test_the_game_hands_it_a_racing_speed(self) -> None:
        from glisteel.driver import RACING_KPH
        from glisteel.game import driver_for
        session = _open_road(traffic=0)
        driver = driver_for(self._config(pace=1.0), session)
        assert driver.pilot.style.maximum_speed == pytest.approx(
            RACING_KPH / 3.6)

    def test_and_the_pace_dial_is_a_fraction_of_it(self) -> None:
        from glisteel.game import driver_for
        session = _open_road(traffic=0)
        quick = driver_for(self._config(pace=1.0), session)
        steady = driver_for(self._config(pace=0.8), session)
        assert steady.pilot.style.margin < quick.pilot.style.margin


class TestMovingIntoALaneItCanHold:
    """A lane is clear enough to move into when there is room to shed the
    speed you are carrying into it. A fixed window is a fixed *time* only at
    one speed: twenty-four metres is a second and a half at forty km/h and half
    a second at a hundred and sixty."""

    def _driving(self, session):
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 6.0, stand_in)
        return stand_in

    def test_an_empty_lane_can_always_be_moved_into(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        assert stand_in.room_in(_InLane(session, found=None), 1.8)

    def test_and_one_with_something_a_long_way_up_it(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        assert stand_in.room_in(_InLane(session, gap=400.0, speed=5.0), 1.8)

    def test_but_not_one_with_something_slow_just_inside_it(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        assert not stand_in.room_in(_InLane(session, gap=12.0, speed=0.0), 1.8)

    def test_something_going_your_own_speed_needs_no_room_to_lose(self) -> None:
        """Nothing has to be shed, so what is wanted is somewhere to sit."""
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        speed = float(session.car.speed())
        assert stand_in.room_in(_InLane(session, gap=30.0, speed=speed), 1.8)

    def test_and_the_faster_you_carry_it_in_the_more_room_it_takes(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        gaps = [gap for gap in range(10, 400, 10)
                if stand_in.room_in(_InLane(session, gap=float(gap),
                                            speed=0.0), 1.8)]
        assert gaps, 'no gap was ever big enough'
        assert min(gaps) > 20.0


class _InLane:
    """A session saying exactly what is in one lane."""

    def __init__(self, session, gap=0.0, speed=0.0, found=()):
        self._session = session
        self._found = None if found is None else (gap, speed)

    def __getattr__(self, name):
        return getattr(self._session, name)

    def lane_ahead(self, across, reach=0.0):
        return self._found


class TestDecidingOverTheRoadItHas:
    """A pass is decided from further back the faster the car is going, for the
    same reason the braking is: a fixed window is a fixed *time* only at one
    speed, and at a hundred and forty km/h a hundred metres is two seconds --
    less than the lane change alone takes."""

    def test_what_is_in_front_is_looked_for_as_far_as_it_can_act(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        assert stand_in.deciding(session) == pytest.approx(
            stand_in.looking(session.car.speed()))

    def test_which_is_further_than_the_road_a_pass_takes(self) -> None:
        stand_in = StandIn(schemes.named('lanes'))
        assert stand_in.looking(40.0) > PASSING_REACH


class TestSayingWhyItDidNotPass:
    """A drive that never passes anything is a drive with a reason, and the
    reason is the one thing a lap of numbers does not carry: it says nine
    passes or none, and never which check said no.

    :meth:`~glisteel.driver.StandIn.refusing` is that check, named. It is what
    :meth:`~glisteel.driver.StandIn.can_pull_out` is built from rather than a
    second copy of the same conditions, so the answer and the reason for it
    cannot drift apart.
    """

    def _driving(self, session):
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        return stand_in

    def test_an_empty_road_offers_nothing_to_pass(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        assert stand_in.refusing(session) == 'nothing in front'

    def test_a_blind_bend_says_so(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        assert stand_in.refusing(_Ahead(session, gap=_crossable(stand_in, session),
                                        speed=0.0, sight=30.0)
                                 ) == 'cannot see far enough'

    def test_and_a_car_coming_the_other_way_says_so(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        found = stand_in.refusing(_Ahead(session, gap=_crossable(stand_in, session),
                                         speed=0.0, sight=800.0,
                                         oncoming=(60.0, 60.0)))
        assert found == 'something is coming'

    def test_being_about_to_arrive_at_it_says_so(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        assert stand_in.refusing(_Ahead(session, gap=4.0, speed=0.0,
                                        sight=800.0)) == 'too close to cross'

    def test_and_a_clear_road_refuses_nothing(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        assert stand_in.refusing(
            _Ahead(session, gap=_crossable(stand_in, session, speed=20.0),
                   speed=20.0, sight=800.0)) is None

    def test_the_answer_and_the_reason_are_the_same_decision(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._driving(session)
        for road in (_Ahead(session, gap=_crossable(stand_in, session),
                            speed=0.0, sight=30.0),
                     _Ahead(session, gap=_crossable(stand_in, session, speed=20.0),
                            speed=20.0, sight=800.0),
                     _Ahead(session, gap=4.0, speed=0.0, sight=800.0)):
            assert stand_in.can_pull_out(road) == (stand_in.refusing(road) is None)


class TestWritingDownWhatItDid:
    """A drive that goes wrong is watched by nobody, and the numbers a lap
    reports -- a time, a count of passes -- carry none of the decisions that
    produced them. The session record does
    (:mod:`OpenGLContext.telemetry`), and what it needs from here is the
    handful of moments a pass is made of.
    """

    def _kept(self, session):
        kept: list = []

        class Keeping:
            @staticmethod
            def mark(name, **fields):
                kept.append((name, fields))

        session.telemetry = Keeping()
        return kept

    def test_a_session_marks_nowhere_until_it_is_given_somewhere(self) -> None:
        from OpenGLContext.telemetry import NOT_RECORDING
        session = _open_road(traffic=0)
        assert session.telemetry is NOT_RECORDING

    def test_pulling_out_is_written_down_with_what_it_was_for(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        kept = self._kept(session)
        gap = _crossable(stand_in, session, speed=20.0)
        stand_in.lanes(_Ahead(session, gap=gap, speed=20.0, sight=800.0), STEP)
        assert [name for name, _ in kept] == ['pass-begun']
        fields = kept[0][1]
        assert fields['gap'] == pytest.approx(gap, abs=0.1)
        assert 'sight' in fields and 'speed' in fields

    def test_giving_one_up_is_written_down_with_the_reason(self) -> None:
        from glisteel.driver import PASS_LONGEST
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        stand_in.overtaking = True
        stand_in.passing = _Car(40.0)
        stand_in.passing_for = PASS_LONGEST + 1.0
        kept = self._kept(session)
        # A road that is still clear, so the only thing wrong with the pass is
        # how long it has gone on.
        stand_in.lanes(_Coming(session, oncoming=None, sight=800.0), STEP)
        assert kept and kept[0][0] == 'pass-given-up'
        assert kept[0][1]['why'] == 'took too long'

    def test_and_so_is_getting_by_one(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        stand_in.overtaking = True
        stand_in.passing = _Car(-60.0)
        kept = self._kept(session)
        stand_in.lanes(_Coming(session, oncoming=None), STEP)
        assert [name for name, _ in kept] == ['pass-done']

    def test_a_refusal_is_written_down_once_rather_than_every_frame(self):
        """A reason that has not changed is a reason already in the file, and
        sixty of them a second is a file nobody reads."""
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        kept = self._kept(session)
        road = _Ahead(session, gap=_crossable(stand_in, session),
                      speed=0.0, sight=30.0)
        for _ in range(30):
            stand_in.lanes(road, STEP)
        assert [name for name, _ in kept] == ['pass-refused']
        assert kept[0][1]['why'] == 'cannot see far enough'

    def test_and_again_when_it_becomes_a_different_reason(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        from glisteel.driver import REASON_HOLDS
        kept = self._kept(session)
        held = int(REASON_HOLDS / STEP) + 2
        for road in (_Ahead(session, gap=_crossable(stand_in, session),
                            speed=0.0, sight=30.0),
                     _Ahead(session, gap=4.0, speed=0.0, sight=800.0)):
            for _ in range(held):
                stand_in.lanes(road, STEP)
        assert [fields['why'] for _name, fields in kept] == [
            'cannot see far enough', 'too close to cross']


class TestNotPullingOutOntoTheEndOfAStraight:
    """The view a driver takes is the one that will still be there when they
    need it. Taken off the end of a straight, a pass is begun on it and given
    up in the bend after it -- and the lap is spent crossing the crown for
    nothing."""

    def test_it_asks_for_the_view_that_lasts_the_manoeuvre(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        asked: list = []

        class Watching:
            two_way = True

            def __getattr__(self, name):
                return getattr(session, name)

            @staticmethod
            def oncoming(reach=None):
                return None

            @staticmethod
            def sight(over=0.0):
                asked.append(over)
                return 800.0

        stand_in.seen(Watching())
        assert asked and asked[0] > 0.0

    def test_and_that_is_the_road_it_covers_getting_back(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        speed = float(session.car.speed())
        assert speed > 1.0
        wanted = stand_in.getting_back() * speed
        assert wanted > 10.0


class TestNotChangingItsMindEveryFrame:
    """The room a pass needs is a number that wanders about the bar it is
    measured against, so a driver that asks the same question of it sixty
    times a second answers differently sixty times a second: it pulls out, and
    a fifth of a second later, before the car has moved, gives up.

    A decision taken is worth keeping until it is clearly wrong. The bar to
    *begin* carries the appetite for the risk; the bar to *give up* is the
    plain arithmetic of still being able to get back.
    """

    def _out_there(self, session, ahead=40.0):
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        stand_in.overtaking = True
        stand_in.passing = _Car(ahead)
        return stand_in

    def test_it_holds_a_pass_it_would_not_now_begin(self) -> None:
        from glisteel.traffic import SPEED_LIMIT
        session = _open_road(traffic=0)
        stand_in = self._out_there(session)
        # A road between the two bars: less than beginning a pass asks for,
        # more than getting back out of one does. Worked from the numbers the
        # driver is using rather than written down, because both of them move
        # with the speed the car is doing.
        closing = float(session.car.speed()) + SPEED_LIMIT
        seconds, _quick = stand_in.planning(session, 40.0, 0.0)
        needed = max(seconds * STILL_ON, stand_in.getting_back())
        assert needed * 1.1 < seconds, 'this test needs a band to sit in'
        road = _Coming(session, oncoming=None, sight=closing * needed * 1.1)
        assert not stand_in.can_pull_out(road), 'this test needs a marginal road'
        assert not stand_in.abandoning(road)

    def test_but_gives_one_up_when_it_could_not_get_back(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._out_there(session)
        assert stand_in.abandoning(_Coming(session, oncoming=None, sight=20.0))

    def test_a_reason_that_flickers_for_a_frame_is_not_written_down(self):
        """Two reasons swapping at the boundary between them is a boundary,
        not a driver changing its mind."""
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        kept: list = []

        class Keeping:
            @staticmethod
            def mark(name, **fields):
                kept.append((name, fields))

        session.telemetry = Keeping()
        blind = _Ahead(session, gap=200.0, speed=0.0, sight=30.0)
        close = _Ahead(session, gap=4.0, speed=0.0, sight=800.0)
        for _ in range(8):
            stand_in.lanes(blind, STEP)
            stand_in.lanes(close, STEP)
        assert len(kept) <= 1, [name for name, _ in kept]


class TestNotStartingWhatItCannotFinish:
    """A pass longer than the driver will stay out there ends on the patience
    limit with the car across the crown, which is where the next thing coming
    finds it. What makes one long is the *difference* the car can build, not
    the speed it happens to be doing."""

    def _crawling(self, session):
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        return stand_in

    def test_it_will_not_pull_out_for_something_barely_slower(self):
        """The sum is run at the speed the road allows rather than the speed
        the car in front has it down to, so what is refused here is a pass
        that is long even flat out."""
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        index, _distance = session.course.nearest(session.car.position)
        quick = stand_in.pilot.road_speed(index, session.car.speed())
        assert stand_in.refusing(
            _Ahead(session, gap=150.0, speed=quick - 3.5,
                   sight=800.0)) == 'it would take too long'

    def test_but_it_will_at_a_speed_that_gets_by(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        assert stand_in.refusing(_Ahead(
            session, gap=_crossable(stand_in, session, speed=20.0), speed=20.0,
                                        sight=800.0)) is None


class TestTheViewDoesNotShrinkAsItAccelerates:
    """A pass is an acceleration, and the stretch the view is taken over was
    measured from the speed the car is doing -- so pulling out widened the
    window, the wider window reached further into the bend, the sight fell, and
    the pass was given up. Accelerating made the road look worse for having
    accelerated.

    The stretch comes from the speed the *road* allows instead, which is a
    property of where the car is rather than of what it is doing.
    """

    def _asking(self, session, speed):
        asked: list = []

        class Watching:
            two_way = True

            def __getattr__(self, name):
                return getattr(session, name)

            @staticmethod
            def oncoming(reach=None):
                return None

            @staticmethod
            def sight(over=0.0):
                asked.append(over)
                return 800.0

            class car:
                @staticmethod
                def speed():
                    return speed

                position = session.car.position

        return Watching(), asked

    def test_the_stretch_is_the_same_at_any_speed_it_is_doing(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        slow, asked_slow = self._asking(session, 10.0)
        quick, asked_quick = self._asking(session, 40.0)
        stand_in.seen(slow)
        stand_in.seen(quick)
        assert asked_slow[0] == pytest.approx(asked_quick[0])

    def test_and_it_is_still_a_stretch_of_road(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        watching, asked = self._asking(session, 20.0)
        stand_in.seen(watching)
        assert asked[0] > 10.0


class TestAPassIsDrivenNotCoasted:
    """How long getting by something takes is a question about a car that
    *accelerates*. Asked at the speed the car happens to be doing, a standing
    start behind something stopped never closes at all -- the sum divides by
    nothing and answers half a minute, and a race car that can reach a hundred
    in five seconds is told it is too slow to pass a parked one.
    """

    def _standing(self, session):
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        return stand_in

    def test_a_standing_start_gets_by_something_stopped(self) -> None:
        from glisteel.driver import PASS_LONGEST
        session = _open_road(traffic=0)
        stand_in = self._standing(session)
        assert stand_in.pass_seconds(0.0, 8.0, 0.0, quick=40.0) < PASS_LONGEST

    def test_and_it_is_the_time_the_acceleration_actually_takes(self) -> None:
        """Covering the relative distance under the pull it believes it has,
        which for a race car from rest is a few seconds rather than never."""
        import math

        from glisteel.driver import CAR_LENGTHS, PASS_ACROSS, PASSED_BY
        session = _open_road(traffic=0)
        stand_in = self._standing(session)
        pull = stand_in.pilot.style.pull
        room = 8.0 + PASSED_BY + CAR_LENGTHS
        assert stand_in.pass_seconds(0.0, 8.0, 0.0, quick=40.0) == pytest.approx(
            PASS_ACROSS + math.sqrt(2.0 * room / pull), rel=0.05)

    def test_getting_by_something_nearly_as_quick_still_takes_longer(self):
        session = _open_road(traffic=0)
        stand_in = self._standing(session)
        easy = stand_in.pass_seconds(20.0, 40.0, 5.0, quick=40.0)
        hard = stand_in.pass_seconds(20.0, 40.0, 36.0, quick=40.0)
        assert hard > easy

    def test_a_car_with_more_pull_gets_by_sooner(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._standing(session)
        slow = stand_in.pass_seconds(0.0, 40.0, 0.0, quick=40.0)
        stand_in.pilot.style.pull *= 4.0
        assert stand_in.pass_seconds(0.0, 40.0, 0.0, quick=40.0) < slow

    def test_and_nothing_is_ever_refused_for_being_stopped(self) -> None:
        """A race car pulls out from a standstill; that is what it is for.

        The gap still has to be one it can cross the crown inside of -- from
        rest it covers thirty-odd metres of it while it is moving over, which
        is :meth:`~glisteel.driver.StandIn.room_to_cross` and not a question
        about how fast the car happens to be going.
        """
        session = _open_road(traffic=0)
        stand_in = self._standing(session)
        assert session.car.speed() < 1.0
        assert stand_in.refusing(_Ahead(session, gap=60.0, speed=0.0,
                                        sight=800.0)) is None


class TestTheCrossingCountsTheAcceleration:
    """A driver sitting behind something at its own speed is not closing on
    it -- until they floor it, which is what pulling out *is*. Measured at the
    speed the two of them have now, the gap looks like it will last for ever
    and the car arrives in the other lane after the crash.
    """

    def _behind(self, session):
        stand_in = StandIn(schemes.named('lanes'))
        _driving(session, 8.0, stand_in)
        return stand_in

    def test_matching_speed_still_closes_once_it_pulls(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._behind(session)
        speed = float(session.car.speed())
        assert not stand_in.room_to_cross(session, gap=2.0, speed=speed)

    def test_and_a_long_gap_is_still_a_long_gap(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._behind(session)
        speed = float(session.car.speed())
        assert stand_in.room_to_cross(session, gap=300.0, speed=speed)


class TestTheRightFootFinishesThePass:
    """Coming back in is a decision made with the pedals, not the wheel.

    A driver level with the car they pulled out for cannot simply steer back:
    the room to come back into has to be *made* first. Past it, the way in is
    forward and the throttle makes the gap; still beside it, the way in is
    backward and lifting off makes the gap. Steering across without doing
    either is steering into the side of somebody.
    """

    def _coming_in(self, session, along):
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        stand_in.overtaking = True
        stand_in.passing = _Car(along)
        stand_in.come_back(_Coming(session))
        return stand_in

    def test_past_it_the_pass_is_finished_on_the_throttle(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._coming_in(session, along=-8.0)
        stand_in.pedals(_Coming(session), STEP)
        assert stand_in.source.holding('throttle')
        assert not stand_in.source.holding('brake')

    def test_still_beside_it_the_way_in_is_backwards(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._coming_in(session, along=2.0)
        stand_in.pedals(_Coming(session), STEP)
        assert stand_in.source.holding('brake')
        assert not stand_in.source.holding('throttle')

    def test_the_pedals_go_back_to_the_road_once_there_is_room(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._coming_in(session, along=2.0)
        stand_in.pedals(_Coming(session), STEP)
        assert stand_in.slipping is not None
        # The other car is well up the road now: the gap has been made.
        stand_in._slip_car = _Car(120.0)
        stand_in.pedals(_Coming(session), STEP)
        assert stand_in.slipping is None

    def test_a_gap_that_never_opens_does_not_hold_the_pedals_for_ever(self) -> None:
        session = _open_road(traffic=0)
        stand_in = self._coming_in(session, along=2.0)
        for _ in range(int(round((SLIP_LONGEST + 1.0) / STEP))):
            stand_in.pedals(_Coming(session), STEP)
        assert stand_in.slipping is None

    def test_a_pass_that_was_never_started_slips_nowhere(self) -> None:
        session = _open_road(traffic=0)
        stand_in = StandIn(schemes.named('lanes'))
        stand_in.controls(session, STEP)
        stand_in.come_back(_Coming(session))
        assert stand_in.slipping is None


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
