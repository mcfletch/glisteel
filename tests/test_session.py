"""The game's loop, with nobody watching it.

A run is a car on a course, a driver at the controls and a clock: physics at a
fixed step with the controls sampled inside it, a camera that follows, a lap
that is timed, and the rules about leaving the road and getting stuck. None of
that is about a window, and :class:`~glisteel.session.Session` is where it
lives, so all of it can be driven a step at a time and read back.
"""

import numpy as np
import pytest

from glisteel import scenarios
from glisteel.run import COUNTDOWN
from glisteel.session import (
    MAXIMUM_CATCHUP,
    PHYSICS_STEP,
    RACE_LAPS,
    Session,
)

FRAME = 1.0 / 60.0


class _Pedals:
    """A driver that holds one set of controls and counts how often it is asked."""

    def __init__(self, throttle: float = 0.0, brake: float = 0.0,
                 steer: float = 0.0) -> None:
        self.held = (throttle, brake, steer)
        self.calls = 0
        self.steps: list[float] = []

    def controls(self, session, dt):
        self.calls += 1
        self.steps.append(dt)
        return self.held


def _grid(piece=None, traffic=0, **named):
    """A session as a player gets one: on the grid, on the lights."""
    piece = piece or scenarios.straight(length=600.0)
    return Session(piece.world(traffic=traffic), **named)


def _session(piece=None, traffic=0, **named):
    """A session already racing, with nothing driving it unless asked.

    The start sequence is its own thing (:class:`TestTheStart`); a test about
    the loop, the camera or the clock wants the car drivable on the first frame
    rather than six seconds of lamps in front of it.
    """
    session = _grid(piece, traffic=traffic, **named)
    session.run.go()
    return session


def _drive(session, seconds, frame=FRAME):
    """Advance a session in frames, as a game running at that rate would."""
    for _ in range(int(round(seconds / frame))):
        session.advance(frame)


class TestTheLoopRuns:
    def test_holding_the_throttle_moves_the_car(self) -> None:
        session = _session(driver=_Pedals(throttle=1.0))
        start = session.car.position.copy()
        _drive(session, 4.0)
        assert float(np.linalg.norm(session.car.position - start)) > 10.0

    def test_holding_nothing_leaves_it_where_it_is(self) -> None:
        session = _session(driver=_Pedals())
        start = session.car.position.copy()
        _drive(session, 2.0)
        assert float(np.linalg.norm(session.car.position - start)) < 1.0

    def test_the_controls_are_sampled_once_a_physics_step(self) -> None:
        """Not once a frame: a controller running at the frame rate holds full
        lock for a quarter of a second on a slow frame."""
        driver = _Pedals()
        session = _session(driver=driver)
        driver.calls = 0
        _drive(session, 1.0)
        assert driver.calls == pytest.approx(1.0 / PHYSICS_STEP, abs=1)

    def test_it_is_sampled_over_the_physics_step_not_the_frame(self) -> None:
        driver = _Pedals()
        session = _session(driver=driver)
        driver.steps = []
        session.advance(FRAME)
        assert set(driver.steps) == {PHYSICS_STEP}

    def test_time_left_over_is_carried_to_the_next_frame(self) -> None:
        driver = _Pedals()
        session = _session(driver=driver)
        driver.calls = 0
        session.advance(PHYSICS_STEP * 0.5)
        assert driver.calls == 0
        session.advance(PHYSICS_STEP * 0.6)
        assert driver.calls == 1

    def test_a_long_frame_does_not_run_away(self) -> None:
        """Past the catch-up limit the game runs slow rather than spiralling: a
        frame that tries to make up a lost second takes longer than a second."""
        driver = _Pedals()
        session = _session(driver=driver)
        driver.calls = 0
        session.advance(5.0)
        assert driver.calls <= int(MAXIMUM_CATCHUP / PHYSICS_STEP) + 1


class TestWhatTheCameraSees:
    def test_advancing_says_where_to_watch_from(self) -> None:
        session = _session(view='chase')
        pose = session.advance(FRAME)
        assert pose is not None
        assert len(pose.position) == 3

    def test_it_follows_the_car(self) -> None:
        session = _session(view='chase', driver=_Pedals(throttle=1.0))
        _drive(session, 4.0)
        pose = session.advance(FRAME)
        assert float(np.linalg.norm(pose.position - session.car.position)) < 20.0

    def test_the_driver_s_own_car_is_left_out_of_the_cockpit_view(self) -> None:
        session = _session(view='cockpit')
        session.advance(FRAME)
        assert session.car.hidden

    def test_and_drawn_from_behind_it(self) -> None:
        session = _session(view='chase')
        session.advance(FRAME)
        assert not session.car.hidden


class TestTheClock:
    def test_the_lap_clock_runs_while_the_car_is_racing(self) -> None:
        session = _session(scenarios.circuit(), driver=_Pedals(throttle=1.0))
        _drive(session, 3.0)
        assert session.timing.current > 0.0

    def test_it_stops_once_the_run_is_over(self) -> None:
        session = _session(scenarios.circuit(), driver=_Pedals(throttle=1.0))
        _drive(session, 2.0)
        session.watch.ended = 'mired off the road'
        stopped = session.timing.current
        _drive(session, 1.0)
        assert session.timing.current == pytest.approx(stopped)

    def test_the_run_says_why_it_ended(self) -> None:
        session = _session()
        assert session.ended is None
        session.watch.ended = 'mired off the road'
        assert session.ended == 'mired off the road'


class TestTheStart:
    """A player is handed a car standing still with the lights running."""

    def test_a_session_begins_on_the_lights(self) -> None:
        assert _grid().run.phase == COUNTDOWN

    def test_the_car_does_not_move_while_they_are_on(self) -> None:
        session = _grid(driver=_Pedals(throttle=1.0))
        start = session.car.position.copy()
        _drive(session, 4.0)
        assert float(np.linalg.norm(session.car.position - start)) < 0.5

    def test_the_clock_does_not_run_either(self) -> None:
        session = _grid(scenarios.circuit(), driver=_Pedals(throttle=1.0))
        _drive(session, 4.0)
        assert session.timing.current == 0.0

    def test_the_lamps_come_on_as_the_count_goes_by(self) -> None:
        session = _grid()
        # Read a little after each second rather than on it: the loop advances
        # in whole physics steps, so "one second of frames" lands just short of
        # one and a lamp read exactly on the boundary is a coin toss.
        _drive(session, 0.1)
        lit = []
        for _ in range(5):
            _drive(session, 1.0)
            lit.append(session.readout().lit)
        assert lit == [1, 2, 3, 4, 5]

    def test_and_then_the_car_is_the_players(self) -> None:
        session = _grid(driver=_Pedals(throttle=1.0))
        start = session.car.position.copy()
        _drive(session, 10.0)
        assert float(np.linalg.norm(session.car.position - start)) > 10.0


class TestTheFinish:
    """The laps asked for, and then the race stops being one."""

    def test_a_race_is_one_lap_unless_asked_otherwise(self) -> None:
        assert _grid().run.laps == RACE_LAPS

    def test_the_laps_asked_for_are_the_laps_run(self) -> None:
        assert _grid(laps=4).run.laps == 4

    def test_a_finished_car_is_no_longer_driven(self) -> None:
        session = _session(scenarios.circuit(), driver=_Pedals(throttle=1.0))
        # Enough to be moving, and no more: what is measured is that the
        # throttle stops reaching the car, not how far it rolls afterwards --
        # and coasting down from this car's full pull is a very long way.
        _drive(session, 0.8)
        # The flag, wherever the car has got to: what is being tested is what
        # the phase does to the controls, not how long a lap of this takes.
        session.run.update(0.0, laps=session.run.laps)
        _drive(session, 4.0)
        assert session.car.speed() < 1.0

    def test_the_clock_stops_with_it(self) -> None:
        session = _session(scenarios.circuit(), driver=_Pedals(throttle=1.0))
        _drive(session, 2.0)
        session.run.update(0.0, laps=session.run.laps)
        stopped = session.timing.current
        _drive(session, 2.0)
        assert session.timing.current == stopped

    def test_starting_again_puts_the_car_back_on_the_grid(self) -> None:
        session = _session(scenarios.circuit(), driver=_Pedals(throttle=1.0))
        _drive(session, 3.0)
        session.restart()
        assert (session.run.phase, session.timing.current) == (COUNTDOWN, 0.0)

    def test_and_stands_it_on_the_grid_from_wherever_it_got_to(self) -> None:
        """The surfaces a car drives on are held near it and dropped behind
        it, so a grid the player left a kilometre back has nothing under it
        until the world is brought in around it again. A car put there without
        that falls through the world and keeps falling."""
        session = _session(scenarios.straight(length=1600.0),
                           driver=_Pedals(throttle=1.0))
        _drive(session, 25.0)
        session.restart()
        _drive(session, 1.0)
        road = session.course.point(session.grid)[1]
        assert abs(float(session.car.position[1]) - road) < 1.0, \
            session.car.position


class TestPuttingTheCarBack:
    def test_a_car_through_the_floor_of_the_world_is_put_back(self) -> None:
        session = _session()
        session.car.place((0.0, session.world.floor - 20.0, 0.0))
        session.advance(FRAME)
        assert session.world.course.on_road(session.car.position)

    def _mired(self, seconds=5.0):
        """A session whose car has been left well off the road."""
        session = _session()
        index, _ = session.world.course.nearest(session.car.position)
        session.car.place(session.world.course.lane_point(index, 20.0)
                          + np.array([0.0, 0.5, 0.0]))
        _drive(session, seconds)
        return session

    def test_a_car_that_has_mired_ends_the_run(self) -> None:
        assert self._mired().run.over

    def test_and_it_is_left_where_it_stopped(self) -> None:
        """A race that is over is not one to be put back into.

        Being picked up and set down on the road belongs to a run still being
        driven. Once the run is over the result stands, and moving the car would
        only hide that it is.
        """
        session = self._mired()
        assert not session.world.course.on_road(session.car.position)

    def test_and_asking_to_go_back_puts_it_on_the_road_and_racing(self) -> None:
        session = self._mired()
        session.return_to_track()
        assert (session.world.course.on_road(session.car.position),
                session.run.over) == (True, False)

    def test_a_car_stopped_on_the_road_is_left_alone(self) -> None:
        """A driver who has stopped on purpose is not rescued from it."""
        session = _session()
        _drive(session, 1.0)
        where = session.car.position.copy()
        _drive(session, 5.0)
        assert float(np.linalg.norm(session.car.position - where)) < 1.0

    def test_going_back_to_the_track_abandons_the_lap(self) -> None:
        session = _session(scenarios.circuit(), driver=_Pedals(throttle=1.0))
        _drive(session, 3.0)
        assert session.timing.current > 0.0
        session.return_to_track()
        assert session.timing.current == 0.0

    def test_and_forgives_having_left_the_road(self) -> None:
        session = _session()
        session.watch.ended = 'mired off the road'
        session.return_to_track()
        assert session.ended is None

    def test_and_puts_it_on_the_road_facing_along_it(self) -> None:
        session = _session()
        session.car.place((0.0, 60.0, 0.0))
        session.return_to_track()
        course = session.world.course
        assert course.on_road(session.car.position)
        index, _ = course.nearest(session.car.position)
        along = course.point(index + 1) - course.point(index)
        along[1] = 0.0
        forward = np.asarray(session.car.forward(), dtype='d')
        forward[1] = 0.0
        assert float(np.dot(forward / np.linalg.norm(forward),
                            along / np.linalg.norm(along))) > 0.9


class TestWhatTheHudIsTold:
    def test_it_is_told_how_fast_the_car_is_going(self) -> None:
        session = _session(driver=_Pedals(throttle=1.0))
        _drive(session, 4.0)
        assert session.readout().speed_kph > 10.0

    def test_and_where_the_car_is_for_the_map(self) -> None:
        session = _session()
        session.advance(FRAME)
        assert np.allclose(session.readout().at, session.car.position)

    def test_and_whether_it_is_off_the_road(self) -> None:
        session = _session()
        assert session.readout().off is False

    def test_and_why_the_run_ended(self) -> None:
        session = _session()
        session.watch.ended = 'HIT A CAR'
        assert session.readout().ended == 'HIT A CAR'

    def test_and_where_the_traffic_is(self) -> None:
        session = _session(scenarios.circuit(), traffic=4)
        session.advance(FRAME)
        assert len(session.readout().others) == 4


class TestWhoIsDriving:
    @pytest.mark.slow
    def test_the_autopilot_drives_it_round(self) -> None:
        """The same loop, with the driver swapped: a lap of a small circuit."""
        from glisteel.driver import Autopilot
        piece = scenarios.circuit()
        session = Session(piece.world())
        session.driver = Autopilot(session.world.course)
        for _ in range(int(90.0 / FRAME)):
            session.advance(FRAME)
            if session.timing.laps:
                break
        assert session.timing.laps, "the autopilot did not get round"

    def test_the_driver_can_be_changed_mid_run(self) -> None:
        from glisteel.driver import Autopilot
        session = _session(scenarios.circuit())
        session.driver = Autopilot(session.world.course)
        _drive(session, 3.0)
        moving = session.car.speed()
        session.driver = _Pedals(brake=1.0)
        _drive(session, 4.0)
        assert session.car.speed() < moving


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


class TestHowARunCameOut:
    """What a finish screen is made of, and what a record is offered from."""

    def test_a_race_still_being_driven_has_no_result(self) -> None:
        assert _session(scenarios.circuit()).result() is None

    def test_a_race_driven_home_has_one(self) -> None:
        session = _session(scenarios.circuit())
        session.run.update(0.0, laps=session.run.laps)
        assert session.result() is not None

    def test_and_it_is_a_finish_rather_than_a_reason(self) -> None:
        session = _session(scenarios.circuit())
        session.run.update(0.0, laps=session.run.laps)
        assert session.result().finished

    def test_a_run_that_ended_carries_why(self) -> None:
        session = _session(scenarios.circuit())
        session.run.update(0.0, ended='mired off the road')
        result = session.result()
        assert (result.finished, result.outcome) == (False, 'mired off the road')

    def test_a_race_with_no_lap_completed_has_no_time(self) -> None:
        session = _session(scenarios.circuit())
        session.run.update(0.0, ended='wrecked')
        assert session.result().seconds is None

    def test_a_completed_lap_is_the_time_it_carries(self) -> None:
        from glisteel.race import Lap
        session = _session(scenarios.circuit())
        session.timing.laps.append(Lap(number=1, seconds=84.115))
        session.run.update(0.0, laps=1)
        assert session.result().seconds == pytest.approx(84.115)

    def test_and_the_quickest_of_several(self) -> None:
        from glisteel.race import Lap
        session = _session(scenarios.circuit(), laps=3)
        for number, seconds in enumerate((90.0, 84.1, 88.0), start=1):
            session.timing.laps.append(Lap(number=number, seconds=seconds))
        session.run.update(0.0, laps=3)
        assert session.result().seconds == pytest.approx(84.1)

    def test_it_says_how_many_laps_were_driven(self) -> None:
        from glisteel.race import Lap
        session = _session(scenarios.circuit(), laps=2)
        for number in (1, 2):
            session.timing.laps.append(Lap(number=number, seconds=90.0))
        session.run.update(0.0, laps=2)
        assert session.result().laps == 2


class TestWhenTheCarNeedsItsOwnLight:
    def test_out_on_the_open_road_it_does_not(self) -> None:
        assert not _session().in_the_dark()

    def test_a_course_with_no_bores_is_never_dark(self) -> None:
        assert not _session(scenarios.circuit()).in_the_dark()


def _traffic_at(session, across, station=45.0, speed=8.0, heading=1):
    """One car on the road at ``across`` metres right of the crown.

    ``station`` is how far up the road from the player it starts.  ``lane`` is
    how far to a car's *own* right it sits, so one heading the other way holds
    the negative of where it is on the road.
    """
    from glisteel.traffic import TrafficCar
    course = session.world.course
    index, _distance = course.nearest(session.car.position)
    here = float(course.stations[index])
    other = TrafficCar(course, here + station, heading=heading,
                       limit=speed, speed=speed)
    other.lane = float(across) * heading
    assert other.side() == pytest.approx(across, abs=1e-6)
    session.world.traffic.release()
    return session.world.traffic.put_out(other)


def _hold(session, speed):
    """Put the car back at ``speed`` along its own nose, keeping its rise."""
    upright = float(session.world.physics.linear_velocity[session.car.body][1])
    session.world.physics.linear_velocity[session.car.body] = (
        session.car.forward() * float(speed) + np.array([0.0, upright, 0.0]))


def _drive_into(session, speed, frame=FRAME, seconds=6.0):
    """Launch the car up the road at ``speed`` and let it arrive.

    The speed is put on the car rather than driven up to: what these are about
    is how fast it was going when it got there, and a hundred metres of
    accelerating first is a hundred metres of nothing being tested.
    """
    _hold(session, speed)
    for _ in range(int(seconds / frame)):
        session.advance(frame)
        if session.crashes.ended is not None:
            break
    return session.crashes.ended


def _touching(session, other):
    """Whether the car and that one are in contact this step."""
    pair = {session.car.body, session.world.traffic.body_of(other)}
    return any({contact.a, contact.b} == pair
               for contact in session.world.physics.contacts)


class TestHittingACar:
    """A run ends where the two cars *touch*, and how hard they were closing
    when they did is what decides it.

    Asked of the physics rather than worked out from how near the two are and
    how fast: a pair either met or did not, and a rule reading a closing speed
    off their positions has to be sampled at exactly the right moment to see
    the impact at all -- one step later the solver has already taken that
    velocity away, and square-on is the case it takes all of.
    """

    def test_running_into_the_back_of_one_ends_the_run(self) -> None:
        session = _session(traffic=1)
        session.advance(FRAME)
        _traffic_at(session, session.across())
        assert _drive_into(session, 40.0) == 'HIT A CAR'

    @pytest.mark.parametrize('fps,speed', [(60, 40.0), (60, 95.0),
                                           (30, 40.0), (30, 95.0)])
    def test_and_does_so_wherever_the_frames_happen_to_fall(self, fps, speed
                                                            ) -> None:
        """Nothing changes between these drives but the distance the other car
        starts at, which moves where the frames land against the approach.

        A car at ninety-five metres a second covers three of them in a frame at
        thirty, and the last stretch before two bumpers touch is shorter than
        that. So a rule sampled once a frame reads the approach on some of
        these runs and reads the rebound on the rest, and a player driving into
        the back of a lorry finds out whether the game noticed by how the
        frames happened to fall. The rule runs on the physics clock instead,
        which every one of these drives shares.
        """
        for shift in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5):
            session = _session(traffic=1)
            session.advance(1.0 / fps)
            _traffic_at(session, session.across(), station=45.0 + shift)
            assert _drive_into(session, speed, frame=1.0 / fps) == 'HIT A CAR', (
                'no crash at %d fps and %.0f m/s with the car %.1f m further on'
                % (fps, speed, shift))

    def test_clipping_one_off_centre_ends_it_too(self) -> None:
        """A glancing blow is contact: half a car's width over is still a car
        being hit rather than a car being passed."""
        session = _session(traffic=1)
        session.advance(FRAME)
        _traffic_at(session, session.across() + 1.2)
        assert _drive_into(session, 40.0) == 'HIT A CAR'

    def test_catching_one_up_and_touching_it_does_not(self) -> None:
        """Two cars going nearly the same speed meet at the difference between
        them, which is a nudge. The car ahead is a car, not a wall: what it is
        doing counts against what the player is doing -- read as a wall, this
        is a thirty metre a second impact and the end of the run."""
        session = _session(traffic=1)
        session.advance(FRAME)
        other = _traffic_at(session, session.across(), station=12.0, speed=26.0)
        met = False
        for _ in range(int(6.0 / FRAME)):
            # Held up to the moment they touch and not past it: what happens
            # after contact is the game's, not the harness leaning on it.
            if not met:
                _hold(session, 30.0)
            session.advance(FRAME)
            met = met or _touching(session, other)
        assert met, 'the two never met'
        assert session.crashes.ended is None

    def test_one_going_the_other_way_in_its_own_lane_is_a_pass(self) -> None:
        """Both on their own side of a two-lane road: they never touch,
        however fast they close."""
        session = _session(traffic=1)
        session.advance(FRAME)
        _traffic_at(session, session.across() - 3.6, station=120.0,
                    speed=30.0, heading=-1)
        assert _drive_into(session, 40.0) is None


class TestWritingDownACrash:
    """A run that ends against another car is read backwards from the moment
    it did, and "HIT A CAR" on its own says nothing about which car or where
    it came from. The record carries both sides of the road, so a car met
    nose to nose and one clipped on the way back into lane are told apart.
    """

    @staticmethod
    def _kept(session):
        kept: list = []

        class Keeping:
            @staticmethod
            def mark(name, **fields):
                kept.append((name, fields))

        session.telemetry = Keeping()
        return kept

    @staticmethod
    def _crash(session, across=0.0, speed=40.0, heading=1):
        """Drive into a car, having started keeping what gets written down."""
        other = _traffic_at(session, session.across() + across,
                            station=120.0 if heading < 0 else 45.0,
                            speed=30.0 if heading < 0 else 8.0, heading=heading)
        kept = TestWritingDownACrash._kept(session)
        assert _drive_into(session, speed) == 'HIT A CAR'
        return kept, other

    def test_it_says_what_the_car_hit(self) -> None:
        session = _session(traffic=1)
        session.advance(FRAME)
        kept, _other = self._crash(session)
        assert [name for name, _ in kept] == ['crash', 'drive-ended']
        fields = kept[0][1]
        assert fields['oncoming'] is False
        assert fields['closing'] > 9.0
        assert fields['gap'] < 8.0

    def test_and_that_one_was_coming_the_other_way(self) -> None:
        session = _session(traffic=1)
        session.advance(FRAME)
        kept, _other = self._crash(session, heading=-1)
        assert kept[0][1]['oncoming'] is True

    def test_and_which_side_of_the_road_each_of_them_was_on(self) -> None:
        session = _session(traffic=1)
        session.advance(FRAME)
        kept, other = self._crash(session)
        fields = kept[0][1]
        assert fields['across'] == pytest.approx(session.across(), abs=0.5)
        assert fields['theirs'] == pytest.approx(other.side(), abs=0.5)

    def test_and_whether_the_driver_was_part_way_past_something(self) -> None:
        session = _session(traffic=1, driver=_Pedals())
        session.advance(FRAME)
        session.driver.overtaking = True
        kept, _other = self._crash(session)
        assert kept[0][1]['passing'] is True

    def test_a_crash_is_written_down_once_rather_than_every_frame(self) -> None:
        session = _session(traffic=1)
        session.advance(FRAME)
        kept, _other = self._crash(session)
        for _ in range(5):
            session.advance(FRAME)
        assert [name for name, _ in kept] == ['crash', 'drive-ended']


class TestWhereARestartStandsTheCar:
    """A restart puts the car back on the grid, on the ground that is there now.

    A streamed world's ground arrives and leaves as the car moves, so what is
    under the start line when a race restarts is not necessarily what was under
    it when the session was built. A height remembered from then is a height
    the road may no longer be at -- and the car is put through it, or dropped
    from over it.
    """

    def _grid_height(self, session):
        """Where the road's own surface is under the grid."""
        standing, _ = session.course.grid_position(
            session.grid, height=1.0, lane=session.lane)
        return session.world.ground_under(standing, skip=(session.car.body,))

    def _slab_over_the_grid(self, session, rise):
        """Ground arriving over what was there, as a finer tile does."""
        from omi_physics import model
        standing, _ = session.course.grid_position(
            session.grid, height=0.0, lane=session.lane)
        top = self._grid_height(session) + rise
        physics = session.world.physics
        shape = physics.add_shape(model.Shape.box((40.0, 2.0, 40.0)))
        physics.add_body(
            model.Motion(type=model.STATIC),
            collider=model.Collider(shape=shape),
            position=(float(standing[0]), top - 1.0, float(standing[2])))
        physics.refit_aabbs()

    def test_the_grid_is_measured_again_on_a_restart(self) -> None:
        session = _grid()
        was = float(session.car.position[1])
        self._slab_over_the_grid(session, 0.5)
        session.restart()
        assert float(session.car.position[1]) == pytest.approx(was + 0.5,
                                                               abs=0.1)

    def test_the_car_does_not_stand_on_itself(self) -> None:
        """The reason the height used to be remembered: a ray cast down the
        grid finds the car that is already parked on it."""
        session = _grid()
        first = float(session.car.position[1])
        for _ in range(5):
            session.restart()
        assert float(session.car.position[1]) == pytest.approx(first, abs=0.02)

    def test_the_ground_under_a_point_can_ignore_a_body(self) -> None:
        session = _grid()
        standing, _ = session.course.grid_position(
            session.grid, height=1.0, lane=session.lane)
        on_the_car = session.world.ground_under(standing)
        on_the_road = session.world.ground_under(standing,
                                                 skip=(session.car.body,))
        assert on_the_car is not None and on_the_road is not None
        assert on_the_car > on_the_road

class TestACarAheadIsACarRatherThanAWall:
    """Traffic is driven along the road by the game rather than by the solver,
    and a body moved that way carries its velocity or it carries nothing.

    Everything downstream reads that: what the two cars do to each other on
    contact, and how hard the physics says they met.
    """

    def test_its_body_is_told_how_fast_it_is_going(self) -> None:
        session = _session(traffic=1)
        session.advance(FRAME)
        other = _traffic_at(session, session.across(), speed=26.0)
        session.advance(FRAME)
        body = session.world.traffic.body_of(other)
        assert float(np.linalg.norm(
            session.world.physics.linear_velocity[body])) == pytest.approx(
                26.0, abs=0.5)

    def test_and_can_be_traced_back_from_the_body_that_was_hit(self) -> None:
        """What the physics answers with is a body index."""
        session = _session(traffic=1)
        session.advance(FRAME)
        other = _traffic_at(session, session.across())
        traffic = session.world.traffic
        assert traffic.car_of(traffic.body_of(other)) is other
        assert traffic.car_of(session.car.body) is None

    def test_and_a_retired_car_leaves_nothing_behind(self) -> None:
        session = _session(traffic=1)
        session.advance(FRAME)
        other = _traffic_at(session, session.across())
        body = session.world.traffic.body_of(other)
        session.world.traffic.release()
        assert session.world.traffic.car_of(body) is None

    def test_and_a_car_nobody_is_driving_any_more_stands_still(self) -> None:
        """A run that has ended stops the traffic, and a body left with a
        velocity would carry on down a road nobody is putting it on -- an
        invisible car a street away from the one being drawn."""
        session = _session(traffic=1)
        session.advance(FRAME)
        other = _traffic_at(session, session.across())
        assert _drive_into(session, 40.0) == 'HIT A CAR'
        body = session.world.traffic.body_of(other)
        stopped = session.world.physics.position[body].copy()
        drawn = np.asarray(session.world.traffic.node_of(other).translation)
        for _ in range(120):
            session.advance(FRAME)
        assert float(np.linalg.norm(
            session.world.physics.position[body] - stopped)) < 0.1
        assert float(np.linalg.norm(
            np.asarray(session.world.traffic.node_of(other).translation)
            - drawn)) < 0.1
