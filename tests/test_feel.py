"""How the car feels, as numbers a budget can be written against.

"Jerky" and "it will not hold a line" are real properties with real numbers
behind them: how fast the wheel moves, how sharply the view swings, and where
the car ends up after an input a player actually gave. Each test here scripts a
drive somebody complained about and measures what came of it.

The tests marked ``xfail`` are the ones the game does not pass yet. Each is a
defect written down as the run that shows it, so that fixing it turns a marker
off rather than needing a test written afterwards; see
``plans/GAMEPLAY-TEST-HARNESS.md`` for what the fix is expected to be.
"""

import numpy as np
import pytest

from glisteel import scenarios
from glisteel.scripted import Script
from glisteel.session import PHYSICS_STEP, Session
from glisteel.trace import drive

#: How fast the car is going when a control is tested at speed, in km/h, and
#: how long the throttle is held to get there.
UP_TO_SPEED = 6.0


def _drive(line, piece=None, seconds=None, view='cockpit', assist=None):
    """Drive a scripted line on a piece of road and bring back the trace.

    ``assist`` is how much of the steering the game puts in
    (:mod:`glisteel.assist`); the default is the shipped one. A test about what
    the car does when nobody corrects it passes 0, since with the assist on
    nobody has to.
    """
    piece = piece or scenarios.straight(length=1600.0)
    named = {} if assist is None else {'assist': assist}
    session = Session(piece.world(), view=view, **named)
    script = Script.parse(line)
    return drive(session, script,
                 seconds=seconds if seconds is not None else script.duration)


class TestTheWheel:
    """The keys give full lock or none; what makes that drivable is the wheel
    they wind, so what it does over time is the whole of how steering feels."""

    def test_letting_go_brings_it_back_to_centre(self) -> None:
        trace = _drive('throttle 0..10; left 4..5', seconds=10.0)
        assert trace.time_to_centre(after=5.0) < 0.5

    def test_a_tap_is_a_nudge_rather_than_a_lock(self) -> None:
        trace = _drive('throttle 0..8; left 6..6.15', seconds=8.0)
        assert trace.steer.max() < 0.4

    def test_the_wheel_never_moves_faster_than_it_is_wound(self) -> None:
        from glisteel.steering import CENTRE
        trace = _drive('throttle 0..10; left 4..5; right 6..7', seconds=10.0)
        assert trace.steering_rate() <= CENTRE * 1.01, trace.report()


class TestACarDrivenStraight:
    """Throttle and nothing else, on a straight road, for twelve seconds.

    Whatever else a car does, it goes where it is pointed. A road is crowned so
    that it drains, so the two sides of the car stand on ground tilted opposite
    ways the whole way along -- and a car that cannot hold that line wanders off
    a road nobody steered it away from, which the player then has to correct for
    without ever having asked it to turn.
    """

    def test_it_stays_on_the_line(self) -> None:
        trace = _drive('throttle 0..12', seconds=12.0)
        assert trace.worst_off_line() < 0.5, trace.report()

    def test_it_stays_pointed_where_it_started(self) -> None:
        trace = _drive('throttle 0..12', seconds=12.0)
        assert trace.heading_change() < 0.5, trace.report()

    def test_and_the_view_is_steady_while_it_does(self) -> None:
        trace = _drive('throttle 0..12', seconds=12.0)
        assert trace.camera_yaw_rate() < 0.02, trace.report()

    def test_over_a_crest_as_well(self) -> None:
        trace = _drive('throttle 0..8', piece=scenarios.crest(), seconds=8.0)
        assert trace.worst_off_line() < 0.5, trace.report()


class TestWhatATapAtSpeedDoes:
    """A tenth of a second on a steering key at a hundred and ten is an input a
    player gives without meaning anything by it. What comes of it is what "the
    steering is too jerky" is about."""

    #: What the car can actually hold, in g: the tyres' own grip plus what the
    #: aerodynamics press on at this speed. Past it something has slipped in the
    #: arithmetic rather than in the corner.
    GRIP = 3.2

    def test_it_corners_within_the_grip_the_car_has(self) -> None:
        trace = _drive('throttle 0..12; left 6..6.15', seconds=12.0)
        assert trace.lateral_g() < self.GRIP, trace.report()

    def test_it_is_a_small_change_of_direction(self) -> None:
        trace = _drive('throttle 0..12; left 6..6.15', seconds=12.0)
        assert trace.heading_change(5.9, 8.0) < 2.0, trace.report()

    def test_and_the_run_survives_it(self) -> None:
        trace = _drive('throttle 0..12; left 6..6.15', seconds=12.0)
        assert trace.why_it_ended() is None, trace.report()

    def test_and_a_driver_who_never_corrects_stays_on_the_road(self) -> None:
        """Which is what the steering assist is for: the wheel centres, and the
        game puts the car back the way the road goes rather than leaving it
        crossing the carriageway until the road runs out."""
        trace = _drive('throttle 0..12; left 6..6.15', seconds=12.0)
        assert not trace.left_the_road(), trace.report()

    def test_and_without_the_assist_a_longer_one_does_not(self) -> None:
        """The defect the assist exists for, kept as a measurement.

        Six tenths of a second, which is what a player gives when the frame
        rate is what decides how briefly they can press a key: the wheel
        centres afterwards and nothing brings the heading back, so the car
        crosses the carriageway and keeps going.
        """
        trace = _drive('throttle 0..12; left 6..6.6', seconds=12.0, assist=0.0)
        assert trace.left_the_road(), trace.report()

    def test_and_with_it_the_same_hold_stays_on(self) -> None:
        trace = _drive('throttle 0..12; left 6..6.6', seconds=12.0)
        assert not trace.left_the_road(), trace.report()

    def test_a_tap_and_a_counter_tap_bring_it_back(self) -> None:
        """Which is what a driver actually does, and what has to be meterable:
        the same touch of the other key puts the car back on the line."""
        trace = _drive('throttle 0..12; left 6..6.15; right 6.6..6.75',
                       seconds=12.0)
        assert not trace.left_the_road(), trace.report()
        assert trace.heading_change(8.0, 12.0) < 0.5, trace.report()


class TestTheViewFromTheDriversSeat:
    """The cockpit is the default view and the one the game is for, so what it
    costs the eye is what most players get."""

    LINE = 'throttle 0..12; left 4..4.6; right 6..6.6'

    def test_a_car_going_straight_does_not_swing_the_view(self) -> None:
        trace = _drive('throttle 0..8', seconds=8.0)
        assert trace.camera_yaw_rate() < 0.05, trace.report()

    @pytest.mark.xfail(strict=True, reason=(
        "the cockpit and bonnet cameras are bolted rigidly to the chassis -- "
        "position and aim are taken from it every frame with nothing between "
        "-- so the eye gets every bump and every twitch of yaw the body does. "
        "See plans/GAMEPLAY-TEST-HARNESS.md section 4.2."))
    def test_it_is_no_harsher_than_watching_from_behind(self) -> None:
        inside = _drive(self.LINE, seconds=12.0, view='cockpit')
        behind = _drive(self.LINE, seconds=12.0, view='chase')
        assert inside.camera_bounce() <= behind.camera_bounce() * 1.5, (
            'from the seat:\n%s\nfrom behind:\n%s'
            % (inside.report(), behind.report()))

    def test_it_is_measured_over_the_same_drive(self) -> None:
        """The two views are the same run seen from two places, so anything
        about the car itself has to come back identical."""
        inside = _drive(self.LINE, seconds=12.0, view='cockpit')
        behind = _drive(self.LINE, seconds=12.0, view='chase')
        assert inside.worst_off_line() == pytest.approx(behind.worst_off_line())


class TestBeingMired:
    """A car that has stayed off the road is mired and the run is over. What
    that has to mean is that the run is over.

    Driven with the steering assist off, because with it on the car does not
    leave the road at all -- which is the point of it, and no way to test what
    happens when a car does.
    """

    LINE = 'throttle 0..14; left 6..6.8'

    def test_a_run_ends_when_the_car_stays_off_the_road(self) -> None:
        trace = _drive(self.LINE, seconds=14.0, assist=0.0)
        assert trace.why_it_ended() is not None

    def _after_it_ended(self, seconds=24.0):
        """The speeds recorded from the moment the run was over.

        Long enough for the slide to finish: the car reaches the verge at a
        hundred and fifty and the whole of what is being measured is what
        happens after that, so the record has to outlast it.
        """
        trace = _drive(self.LINE, seconds=seconds, assist=0.0)
        over = [index for index, why in enumerate(trace.ended) if why]
        assert over, "the run did not end at all"
        return trace, trace.speed[over[0]:]

    def test_and_the_car_stops_being_driven(self) -> None:
        """The throttle is no longer connected to anything."""
        trace, after = self._after_it_ended()
        assert after[-1] < 0.5, trace.report()

    def test_and_it_is_never_driven_again_on_the_way_there(self) -> None:
        """Slowing all the way down, rather than slowing and being picked up.

        A car put back on the road would show up here as the speed rising
        again, which is the thing that made a mired run something a player
        could drive out of.
        """
        trace, after = self._after_it_ended()
        gained = float(np.diff(after).max())
        assert gained < 0.05, trace.report()

    def test_and_how_long_that_takes_is_the_grip_it_has_left(self) -> None:
        """Off the road, so it is a long slide rather than a stop."""
        trace, after = self._after_it_ended()
        stopped = int(np.argmax(after < 0.5)) * PHYSICS_STEP
        assert 3.0 < stopped < 12.0, trace.report()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


class TestWhatTheCarHasToPassWith:
    """An electric supercar's numbers, which is what a pass is made of.

    Getting by somebody is a speed *difference* built in the length of road the
    driver can see, so what decides whether passing is a manoeuvre or a chore
    is the thrust left at the speed the pass happens at -- not the standstill
    figure, where nobody overtakes. A car with a hot hatch's power spends ten
    seconds alongside and makes every pass a bet on a road nobody can see that
    far down.

    Read from the tuning rather than driven, so the budget is cheap enough to
    keep: the shape is ``min(engine_force, power / v) - drag * v**2`` and the
    figures it gives are the ones a drive measures.
    """

    def _car(self):
        from glisteel.car import CarSpec
        return CarSpec()

    def thrust(self, spec, kph):
        """Newtons left over at that speed, after the air."""
        v = float(kph) / 3.6
        tuning = spec.tuning
        power = tuning.engine_force * tuning.base_speed
        engine = min(tuning.engine_force, power / v)
        return engine - tuning.drag * v * v

    def test_it_has_a_supercar_s_power(self) -> None:
        spec = self._car()
        power = spec.tuning.engine_force * spec.tuning.base_speed
        assert power >= 400_000, '%.0f kW is not a supercar' % (power / 1000)

    def test_there_is_thrust_left_at_passing_speed(self) -> None:
        """Half a g at 140 km/h: a pass measured in seconds, not in tens."""
        spec = self._car()
        pull = self.thrust(spec, 140.0) / spec.mass
        assert pull >= 0.45 * 9.81, '%.2f g at 140 km/h' % (pull / 9.81)

    def test_and_still_at_the_speed_the_circuit_is_driven_at(self) -> None:
        spec = self._car()
        pull = self.thrust(spec, 200.0) / spec.mass
        assert pull > 0.0, 'nothing left at the design speed'

    def test_the_top_end_clears_the_speed_the_road_is_built_for(self) -> None:
        """The circuit is laid out for 200 km/h; a car that tops out near it
        is one the road is driving rather than the driver."""
        spec = self._car()
        power = spec.tuning.engine_force * spec.tuning.base_speed
        top = (power / spec.tuning.drag) ** (1.0 / 3.0) * 3.6
        assert top >= 260.0, 'tops out at %.0f km/h' % top


class TestItSlidesRatherThanRolls:
    """A car on flat tarmac runs out of grip before it runs out of stability.

    A body tips when the sideways pull passes ``(track / 2) / h``, where ``h``
    is how high its mass sits. Below what the tyres can ask for, that is not a
    limit a driver can feel and recover from -- it is the car going over,
    from a steering input on flat ground with nothing to trip on. The limit
    has to be the tyres, so that losing grip is a slide.
    """

    def _flat(self, spec=None):
        from omi_physics.world import PhysicsWorld
        from glisteel.car import Car
        from OpenGLContext.scenegraph import basenodes as _bn  # noqa: F401
        import tests.test_driver as td
        world = PhysicsWorld()
        td.static_ground(world, size=3000.0)
        return world, Car(world, spec, position=(0.0, 2.0, 0.0))

    def settled_height(self):
        """How high the mass sits once the car is standing on its springs."""
        world, car = self._flat()
        for _ in range(int(3.0 / PHYSICS_STEP)):
            car.control(0.0, 0.0, 0.0)
            car.update(PHYSICS_STEP)
            world.step(PHYSICS_STEP)
        return float(car.position[1])

    def test_the_mass_sits_low_enough_to_corner_on(self) -> None:
        """Well clear of what a corner asks for.

        Not clear of the tyres' own peak, which this car cannot reach: the
        wheels have to hang below the mass they carry, and that bounds how low
        the mass can go while the body's origin is also its collider. What it
        has to clear is the road: a car that tips at less than a hard corner
        is one that goes over rather than sliding, and 1.4 g is half again
        what a road corner asks. The check that the car actually stays on its
        wheels is the one below.
        """
        from glisteel.car import CarSpec
        spec = CarSpec()
        tips = (spec.track / 2.0) / self.settled_height()
        assert tips > 1.4, 'tips at %.2f g' % tips

    def test_full_lock_at_speed_does_not_put_it_on_its_roof(self) -> None:
        """The hardest input there is, on flat ground, at the speed it
        happens at: the car should slide, and stay on its wheels."""
        rolled = []
        for speed in (20.0, 30.0, 45.0, 60.0):
            world, car = self._flat()
            while car.speed() < speed:
                car.control(1.0, 0.0, 0.0)
                car.update(PHYSICS_STEP)
                world.step(PHYSICS_STEP)
            for _ in range(int(4.0 / PHYSICS_STEP)):
                car.control(0.0, 0.0, 1.0)
                car.update(PHYSICS_STEP)
                world.step(PHYSICS_STEP)
                if car.upside_down():
                    rolled.append(speed)
                    break
        assert not rolled, 'rolled over at %s m/s' % rolled
