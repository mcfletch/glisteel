"""The switch between ways of driving, and what each one does with a key.

Nothing here needs a window. A scheme is a
:class:`~glisteel.session.Controller` handed a session and a step, so what it
makes of a held key is arithmetic over a course and the aid that holds a line.
"""
import math

import numpy as np
import pytest

from glisteel import scenarios, schemes
from glisteel.assist import Straighten
from glisteel.schemes import QUEUED_FOR
from glisteel.session import Session
from glisteel.steering import CONTROLS
from glisteel.zone import DrivableZone

STEP = 1.0 / 120.0


class _Vehicle:
    """What is simulated under the car, as a way of driving reads one.

    The real thing is ``omi_physics``' :class:`RaycastVehicle`; what a lane
    change asks it is how tightly it may turn at the speed it is doing, which
    is the same bicycle-model answer at a steering lock that closes with speed.
    """

    def __init__(self, wheelbase: float = 2.55, lock: float = 0.52,
                 falloff: float = 10.0) -> None:
        self.base = wheelbase
        self.lock = lock
        self.falloff = falloff

    def turning_radius(self, speed: float = 0.0) -> float:
        share = abs(float(speed)) / self.falloff
        lock = self.lock / (1.0 + share * share)
        return self.base / math.tan(lock)


class _Car:
    """A car standing on the crown of a straight road, pointing along it."""

    def __init__(self, across: float = 0.0, speed: float = 30.0) -> None:
        self.position = np.array([across, 0.0, 0.0])
        self.vehicle = _Vehicle()
        self._speed = float(speed)

    def forward_speed(self) -> float:
        return self._speed

    def speed(self) -> float:
        return self._speed

    def forward(self) -> np.ndarray:
        return np.array([0.0, 0.0, -1.0])


class _Session:
    """The little of a run a scheme reads: a car, a road, and the line aid."""

    def __init__(self, across: float = 0.0, speed: float = 30.0) -> None:
        self.course = scenarios.straight(length=800.0).course()
        self.car = _Car(across, speed)
        self.assist = Straighten(self.course)


def _wide():
    """A four-lane road, for the lanes there are on one."""
    from glisteel.world import Course
    line = scenarios.straight(length=800.0).centreline()
    return Course(
        name='wide', centreline=line, carriageway_width=14.4, total_width=18.0,
        closed=False,
        length=float(np.linalg.norm(np.diff(line, axis=0), axis=1).sum()),
        profile=dict(scenarios.PROFILE, lanes=4, laneWidth=3.6))


def _hold(scheme, control, seconds, session=None):
    """Hold a control for that long, and give back the session driven."""
    session = session if session is not None else _Session()
    key = sorted(CONTROLS[control])[0] if control else None
    if key is not None:
        scheme.source.press(key)
    for _ in range(int(round(seconds / STEP))):
        scheme.controls(session, STEP)
    if key is not None:
        scheme.source.release(key)
    return session


class TestTheSwitch:
    def test_every_scheme_is_offered_by_name(self) -> None:
        assert 'wheel' in schemes.available()

    def test_each_name_builds_one(self) -> None:
        for name in schemes.available():
            assert schemes.named(name).name == name

    def test_and_each_says_what_it_is(self) -> None:
        assert all(schemes.named(name).summary
                   for name in schemes.available())

    def test_a_name_that_is_not_a_scheme_says_which_are(self) -> None:
        with pytest.raises(ValueError) as raised:
            schemes.named('hovercraft')
        assert 'wheel' in str(raised.value)

    def test_the_default_is_the_one_the_game_has_always_had(self) -> None:
        assert schemes.DEFAULT == 'wheel'

    def test_a_scheme_carries_the_keys_it_is_driven_by(self) -> None:
        """The window presses keys on the source, whichever scheme is on."""
        scheme = schemes.named('line')
        scheme.source.press('a')
        assert scheme.source.holding('left')


class TestTheWheel:
    """What ships: the key is the steering lock, and the aid trims the line."""

    def test_it_asks_for_the_lock_the_keys_have_wound_on(self) -> None:
        scheme = schemes.named('wheel')
        session = _Session()
        scheme.source.press('a')
        for _ in range(60):
            steer = scheme.controls(session, STEP)[2]
        assert steer == pytest.approx(scheme.source.keys.position)

    def test_and_it_leaves_the_aid_at_the_strength_it_was_given(self) -> None:
        scheme = schemes.named('wheel', trim=0.4)
        session = _Session()
        scheme.controls(session, STEP)
        assert session.assist.strength == pytest.approx(0.4)

    def test_the_throttle_is_still_the_throttle(self) -> None:
        scheme = schemes.named('wheel')
        scheme.source.press('w')
        assert scheme.controls(_Session(), STEP)[0] == pytest.approx(1.0)


class TestLoose:
    def test_it_takes_the_aid_off_altogether(self) -> None:
        scheme = schemes.named('loose', trim=0.55)
        session = _Session()
        scheme.controls(session, STEP)
        assert not session.assist.helping

    def test_and_still_steers(self) -> None:
        scheme = schemes.named('loose')
        session = _Session()
        scheme.source.press('a')
        for _ in range(60):
            steer = scheme.controls(session, STEP)[2]
        assert steer > 0.0


class TestTheLine:
    """The key moves the car's place across the road, not its wheels."""

    def test_it_hands_the_steering_to_the_aid(self) -> None:
        scheme = schemes.named('line')
        session = _Session()
        scheme.source.press('a')
        assert scheme.controls(session, STEP)[2] == pytest.approx(0.0)

    def test_and_asks_the_aid_for_all_of_the_correction(self) -> None:
        session = _Session()
        schemes.named('line', trim=0.2).controls(session, STEP)
        assert session.assist.strength == pytest.approx(1.0)

    def test_holding_left_moves_the_line_to_the_left(self) -> None:
        session = _hold(schemes.named('line'), 'left', 0.5)
        assert session.assist.line < -0.1

    def test_holding_right_moves_it_to_the_right(self) -> None:
        session = _hold(schemes.named('line'), 'right', 0.5)
        assert session.assist.line > 0.1

    def test_letting_go_leaves_the_line_where_it_was_put(self) -> None:
        scheme = schemes.named('line')
        session = _hold(scheme, 'left', 0.5)
        moved = session.assist.line
        for _ in range(240):
            scheme.controls(session, STEP)
        assert session.assist.line == pytest.approx(moved)

    def test_a_second_of_holding_is_about_a_lane_across(self) -> None:
        """The rate is a hand moving a car across a lane, not a wheel."""
        session = _hold(schemes.named('line'), 'left', 1.2)
        assert 2.5 < abs(session.assist.line) < 5.0

    def test_the_line_never_leaves_the_road(self) -> None:
        session = _hold(schemes.named('line'), 'left', 20.0)
        zone = DrivableZone.of(session.course)
        assert abs(session.assist.line) <= zone.edge + 1e-9

    def test_it_starts_from_the_line_the_car_is_on(self) -> None:
        scheme = schemes.named('line')
        session = _Session(across=1.8)
        scheme.controls(session, STEP)
        assert session.assist.line == pytest.approx(1.8, abs=0.05)

    def test_the_pointer_moves_the_line_as_well(self) -> None:
        from glisteel.steering import MouseWheel
        pointer = MouseWheel(width=1000)
        scheme = schemes.named('line', pointer=pointer)
        session = _Session()
        pointer.moved(100)                       # well to the left of centre
        for _ in range(60):
            scheme.controls(session, STEP)
        assert session.assist.line < -0.1


class TestTheLanes:
    """A press asks for the lane over, and the steering takes the car there.

    That is the whole of what it does: it does not look for traffic, it does
    not touch the pedals, and it will not stop the driver arriving at a corner
    too fast. What it does have to be is *clean* -- a change no faster than the
    car can hold, easing in and out, so that whatever else puts the car off the
    road it is never the steering that did it.
    """

    @staticmethod
    def _arrive(scheme, session, seconds=8.0):
        """Drive on until the manoeuvre is over, and say how long it took."""
        for count in range(int(round(seconds / STEP))):
            scheme.controls(session, STEP)
            if scheme.taking is None:
                return (count + 1) * STEP
        return seconds

    @staticmethod
    def _across(scheme, session, seconds=8.0):
        """Where the line is at every step of a manoeuvre, in metres."""
        found = [session.assist.line]
        for _ in range(int(round(seconds / STEP))):
            scheme.controls(session, STEP)
            found.append(session.assist.line)
        return np.asarray(found, dtype='d')

    def test_a_tap_asks_for_the_lane_to_the_left(self) -> None:
        scheme = schemes.named('lanes')
        _hold(scheme, 'left', 0.1, _Session(across=1.8))
        assert scheme.taking == pytest.approx(-1.8, abs=0.01)

    def test_and_the_car_arrives_in_it(self) -> None:
        scheme = schemes.named('lanes')
        session = _hold(scheme, 'left', 0.1, _Session(across=1.8))
        self._arrive(scheme, session)
        assert session.assist.line == pytest.approx(-1.8, abs=0.01)
        assert scheme.taking is None

    def test_and_stays_there_once_it_has(self) -> None:
        scheme = schemes.named('lanes')
        session = _hold(scheme, 'left', 0.1, _Session(across=1.8))
        self._arrive(scheme, session)
        assert self._across(scheme, session, 2.0) == pytest.approx(-1.8, abs=0.01)

    def test_the_move_is_a_manoeuvre_rather_than_a_jump(self) -> None:
        """Put on the new lane at once, the aid is asked to be a lane sideways
        of where the car is, and at speed that is all the lock there is."""
        scheme = schemes.named('lanes')
        session = _hold(scheme, 'left', 0.1, _Session(across=1.8))
        assert 1.0 < session.assist.line < 1.8

    @staticmethod
    def _change(scheme, session, seconds=6.0):
        """A whole lane change, from the press, as the line at every step."""
        scheme.controls(session, STEP)           # the aid takes the car's line
        scheme.source.press('a')
        return TestTheLanes._across(scheme, session, seconds)

    def test_it_starts_and_finishes_at_rest(self) -> None:
        """Cleanly: the car is not thrown sideways at either end of it, which is
        what a constant rate does -- a step in lateral speed at both ends."""
        scheme = schemes.named('lanes')
        line = self._change(scheme, _Session(across=1.8))
        rate = np.abs(np.diff(line)) / STEP
        assert rate[0] < 0.02 * rate.max()
        assert rate[-1] < 0.02 * rate.max()

    def test_and_never_asks_for_more_than_the_car_is_comfortable_with(self
                                                                     ) -> None:
        scheme = schemes.named('lanes')
        line = self._change(scheme, _Session(across=1.8))
        sideways = np.abs(np.diff(line, 2)) / (STEP * STEP)
        assert sideways.max() <= schemes.LANE_CHANGE_G * 1.05

    def test_it_takes_longer_at_walking_pace_than_at_speed(self) -> None:
        """Speed aware: what a car may ask of its front wheels is a corner of
        the radius its lock allows, and at walking pace that is a smaller
        sideways push than the same lock buys at eighty."""
        quick = schemes.named('lanes')
        _hold(quick, 'left', 0.1, quick_session := _Session(across=1.8))
        crawling = schemes.named('lanes')
        _hold(crawling, 'left', 0.1, slow := _Session(across=1.8, speed=2.0))
        assert (self._arrive(crawling, slow)
                > self._arrive(quick, quick_session) * 1.2)

    def test_and_a_car_that_is_stopped_still_answers(self) -> None:
        scheme = schemes.named('lanes')
        session = _Session(across=1.8, speed=0.0)
        _hold(scheme, 'left', 0.1, session)
        assert scheme.taking == pytest.approx(-1.8, abs=0.01)
        assert session.assist.line <= 1.8

    def test_and_a_tap_back_takes_the_first_one_again(self) -> None:
        scheme = schemes.named('lanes')
        session = _hold(scheme, 'left', 0.1, _Session(across=1.8))
        _hold(scheme, 'right', 0.1, session)
        self._arrive(scheme, session)
        assert session.assist.line == pytest.approx(1.8, abs=0.01)

    def test_a_second_tap_part_way_across_is_a_second_lane(self) -> None:
        scheme = schemes.named('lanes')
        session = _hold(scheme, 'left', 0.1, _Session(across=5.4))
        _hold(scheme, 'left', 0.1, session)
        assert scheme.taking == pytest.approx(-1.8, abs=0.01)

    def test_a_tap_at_the_edge_of_the_road_stays_on_it(self) -> None:
        scheme = schemes.named('lanes')
        session = _hold(scheme, 'left', 0.1, _Session(across=-1.8))
        self._arrive(scheme, session)
        assert session.assist.line == pytest.approx(-1.8, abs=0.01)

    def test_a_car_put_back_on_the_road_forgets_where_it_was_going(self) -> None:
        """A restart, or being put back: the lane it was taking is a lane on the
        road it was on, and dragging the car there is driving it into the
        oncoming side of a road it has just been stood on."""
        scheme = schemes.named('lanes')
        session = _hold(scheme, 'left', 0.1, _Session(across=1.8))
        session.assist.release()
        scheme.controls(session, STEP)
        assert scheme.taking is None
        assert session.assist.line == pytest.approx(1.8, abs=0.05)

    def test_holding_the_key_takes_the_lanes_one_at_a_time(self) -> None:
        """A lane switch switches lanes: held down it goes on doing that, one
        lane at a time, rather than sliding the car across the road."""
        scheme = schemes.named('lanes')
        session = _Session(across=5.4)
        session.course = _wide()
        scheme.source.press('a')
        for _ in range(int(round(12.0 / STEP))):
            scheme.controls(session, STEP)
        assert session.assist.line == pytest.approx(-5.4, abs=0.05)

    def test_and_stops_when_the_road_runs_out(self) -> None:
        scheme = schemes.named('lanes')
        session = _Session(across=1.8)
        scheme.source.press('a')
        for _ in range(int(round(12.0 / STEP))):
            scheme.controls(session, STEP)
        assert session.assist.line == pytest.approx(-1.8, abs=0.05)

    def test_one_press_is_one_lane_however_long_the_step(self) -> None:
        scheme = schemes.named('lanes')
        session = _Session(across=1.8)
        scheme.source.press('a')
        scheme.controls(session, 1.0 / 30.0)
        scheme.controls(session, 1.0 / 30.0)
        scheme.source.release('a')
        self._arrive(scheme, session)
        assert session.assist.line == pytest.approx(-1.8, abs=0.01)

    def test_the_pointer_picks_the_lane_it_is_nearest(self) -> None:
        from glisteel.steering import MouseWheel
        pointer = MouseWheel(width=1000)
        scheme = schemes.named('lanes', pointer=pointer)
        session = _Session(across=1.8)
        scheme.controls(session, STEP)
        pointer.moved(100)                       # well to the left of centre
        scheme.controls(session, STEP)
        assert scheme.taking == pytest.approx(-1.8, abs=0.01)

    def test_and_a_pointer_nobody_has_touched_asks_for_nothing(self) -> None:
        """A pointer sits in the middle of the window until it is moved, and a
        car sent to the middle of the road as the run starts is a car sent into
        the oncoming lane by nobody."""
        from glisteel.steering import MouseWheel
        scheme = schemes.named('lanes', pointer=MouseWheel(width=1000))
        session = _Session(across=1.8)
        for _ in range(60):
            scheme.controls(session, STEP)
        assert scheme.taking is None
        assert session.assist.line == pytest.approx(1.8, abs=0.05)


class TestTheChauffeur:
    """It drives; the player interrupts."""

    def _session(self):
        session = Session(scenarios.straight(length=800.0).world(traffic=0))
        session.run.go()
        return session

    def test_it_drives_the_car_with_nobody_touching_it(self) -> None:
        session = self._session()
        scheme = schemes.named('chauffeur')
        assert scheme.controls(session, STEP)[0] > 0.0

    def test_a_key_takes_the_car_off_it_at_once(self) -> None:
        session = self._session()
        scheme = schemes.named('chauffeur')
        scheme.controls(session, STEP)
        scheme.source.press('s')
        assert scheme.controls(session, STEP)[0] <= 0.0

    def test_and_it_takes_the_car_back_once_the_player_stops(self) -> None:
        session = self._session()
        scheme = schemes.named('chauffeur')
        scheme.source.press('s')
        scheme.controls(session, STEP)
        scheme.source.release('s')
        for _ in range(int(round((schemes.HANDBACK + 0.5) / STEP))):
            throttle = scheme.controls(session, STEP)[0]
        assert throttle > 0.0


class TestWhoTheWindowHandsTheCarTo:
    """Which driver a command line asks for, without a window to ask it in."""

    def _session(self):
        return Session(scenarios.straight(length=800.0).world(traffic=0))

    def _config(self, **named):
        from glisteel.options import Options
        return Options(world='x', **named)

    def test_it_is_the_way_of_driving_that_was_asked_for(self) -> None:
        from glisteel.game import driver_for
        found = driver_for(self._config(control='lanes'), self._session())
        assert isinstance(found, schemes.Lanes)

    def test_and_it_carries_the_aid_the_player_asked_for(self) -> None:
        from glisteel.game import driver_for
        found = driver_for(self._config(assist=0.3), self._session())
        assert found.trim == pytest.approx(0.3)

    def test_the_pointer_goes_with_whichever_way_it_is(self) -> None:
        from glisteel.game import driver_for
        found = driver_for(self._config(control='line', mouse=True),
                           self._session())
        assert found.source.pointer is not None

    def test_and_without_it_there_is_no_pointer_to_steer_with(self) -> None:
        from glisteel.game import driver_for
        assert driver_for(self._config(), self._session()).source.pointer is None

    def test_a_car_that_drives_itself_in_easy_mode_is_a_stand_in(self) -> None:
        """A way of driving that steers for the driver is a way of driving to be
        *judged*, so the autopilot drives it the way a player would: through the
        controls, not past them."""
        from glisteel.driver import StandIn
        from glisteel.game import driver_for
        found = driver_for(self._config(control='lanes', autopilot=True),
                           self._session())
        assert isinstance(found, StandIn)
        assert found.scheme.name == 'lanes'

    def test_a_car_that_drives_itself_is_the_autopilot(self) -> None:
        """Where the way of driving is the wheel, the autopilot turns it:
        pressing a steering key to wind a wheel it could turn directly is a
        worse driver rather than a truer one."""
        from glisteel.driver import Autopilot
        from glisteel.game import driver_for
        found = driver_for(self._config(autopilot=True), self._session())
        assert isinstance(found, Autopilot)

    def test_which_ways_of_driving_hold_the_line_for_the_driver(self) -> None:
        assert schemes.named('lanes').holds_the_line
        assert schemes.named('line').holds_the_line
        assert not schemes.named('wheel').holds_the_line
        assert not schemes.named('chauffeur').holds_the_line


class TestDrivingOneToAScript:
    """The switch is what an experiment needs: the same drive, each way."""

    LINE = 'throttle 0..4; left 5..5.3'

    def _drive(self, scheme, seconds=11.0):
        from glisteel.scripted import Script
        from glisteel.trace import drive
        session = Session(scenarios.straight(length=1600.0).world(traffic=0))
        return drive(session, Script.parse(self.LINE, scheme=scheme),
                     seconds=seconds)

    def test_a_tap_on_the_wheel_is_a_nudge_the_car_settles_out_of(self) -> None:
        assert self._drive('wheel').worst_off_line() < 2.0

    def test_the_same_tap_on_the_line_is_a_step_across_the_road(self) -> None:
        trace = self._drive('line')
        assert 0.4 < trace.worst_off_line() < 2.0

    def test_and_the_car_is_pointed_where_it_started(self) -> None:
        """Which is the difference: the car has moved over, not turned."""
        assert self._drive('line').heading_change(4.9, 11.0) < 1.0

    def test_with_nothing_helping_the_same_tap_crosses_the_road(self) -> None:
        assert self._drive('loose').worst_off_line() > 3.0


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


class _Blocked(_Session):
    """A run with a car sitting in one of the lanes."""

    def __init__(self, *args, occupied=None, **named):
        super().__init__(*args, **named)
        self.occupied = occupied

    def lane_clear(self, across, ahead=0.0, behind=0.0):
        return self.occupied is None or abs(across - self.occupied) > 0.5

    def clears(self):
        self.occupied = None


class TestAskingForALaneSomebodyIsIn:
    """A press with a car alongside is remembered, not thrown away.

    Easy mode is a lane *switch*, and the switch is the only thing the driver
    has: refusing the press leaves them holding a key that does nothing, and
    obeying it puts them into the side of somebody. Neither is the game. So the
    lane is kept as something asked for, and taken the moment there is room --
    which is what a driver does anyway, having lifted off to make the room. The
    press is the intention; the road decides when it happens.
    """

    def _ask(self, scheme, session, control='right', seconds=0.1):
        key = sorted(CONTROLS[control])[0]
        scheme.source.press(key)
        for _ in range(int(round(seconds / STEP))):
            scheme.controls(session, STEP)
        scheme.source.release(key)
        return session

    def test_the_car_does_not_move_into_an_occupied_lane(self) -> None:
        scheme = schemes.named('lanes')
        session = _Blocked(across=-1.8, occupied=1.8)
        self._ask(scheme, session)
        assert scheme.taking is None
        assert session.assist.line == pytest.approx(-1.8, abs=0.01)

    def test_but_the_press_is_remembered(self) -> None:
        scheme = schemes.named('lanes')
        session = _Blocked(across=-1.8, occupied=1.8)
        self._ask(scheme, session)
        assert scheme.queued == pytest.approx(1.8, abs=0.01)

    def test_and_taken_as_soon_as_there_is_room(self) -> None:
        scheme = schemes.named('lanes')
        session = _Blocked(across=-1.8, occupied=1.8)
        self._ask(scheme, session)
        session.clears()
        scheme.controls(session, STEP)
        assert scheme.queued is None
        assert scheme.taking == pytest.approx(1.8, abs=0.01)

    def test_a_lane_that_never_clears_lets_the_press_go(self) -> None:
        """Held for ever, a press taken minutes later is a car changing lane
        for no reason the driver remembers asking for."""
        scheme = schemes.named('lanes')
        session = _Blocked(across=-1.8, occupied=1.8)
        self._ask(scheme, session)
        for _ in range(int(round((QUEUED_FOR + 1.0) / STEP))):
            scheme.controls(session, STEP)
        assert scheme.queued is None
        assert scheme.taking is None

    def test_an_empty_lane_is_taken_at_once_as_before(self) -> None:
        scheme = schemes.named('lanes')
        session = _Blocked(across=-1.8, occupied=None)
        self._ask(scheme, session)
        assert scheme.taking == pytest.approx(1.8, abs=0.01)
        assert scheme.queued is None
