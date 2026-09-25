"""What the car sounds like, and why it sounds like that.

All of it is arithmetic on four numbers a frame -- road speed, how much the
tyres are scrubbing, how hard the motor is being asked to work, and whether the
wheels are on anything -- so the whole of it is tested here with no device, no
window and no audio thread.
"""
import numpy as np
import pytest

from glisteel.sound import (
    MOTOR_HZ,
    SETTLE,
    CarSound,
    impact_clip,
    motor_clip,
    tyre_clip,
    wind_clip,
)

FRAME = 1.0 / 60.0


def settled(sound, seconds=2.0, **state):
    """Hold one set of conditions until the gains stop moving."""
    for _ in range(int(seconds / FRAME)):
        sound.update(FRAME, **state)
    return sound


def _driving(speed=30.0, slip=0.0, throttle=0.0, grounded=True):
    return {'speed': speed, 'slip': slip, 'throttle': throttle,
            'grounded': grounded}


class TestTheClipsAreLoopable:
    """A continuous sound is a short clip played round and round, so the join
    has to be inaudible. A clip that ramps in and out pulses at the loop rate,
    which is a sound of its own and not the one that was wanted."""

    def test_the_motor_is_a_whole_number_of_cycles(self):
        """Then the wrap from the last sample to the first is one more step of
        the same sine, and the loop cannot be heard."""
        clip = motor_clip(sample_rate=8000)
        cycles = MOTOR_HZ * len(clip.samples) / clip.sample_rate
        assert cycles == pytest.approx(round(cycles))

    def test_and_it_does_not_fade_at_the_ends(self):
        clip = motor_clip(sample_rate=8000)
        samples = np.abs(np.asarray(clip.samples))
        edge = max(float(samples[:50].max()), float(samples[-50:].max()))
        assert edge > float(samples.max()) * 0.5

    def test_the_tyres_hold_their_level_throughout(self):
        """Noise joins to noise, so what matters is that it does not decay."""
        samples = np.asarray(tyre_clip(sample_rate=8000).samples)
        third = len(samples) // 3
        head = float(np.sqrt((samples[:third] ** 2).mean()))
        tail = float(np.sqrt((samples[-third:] ** 2).mean()))
        assert tail == pytest.approx(head, rel=0.25)

    def test_and_so_does_the_wind(self):
        samples = np.asarray(wind_clip(sample_rate=8000).samples)
        third = len(samples) // 3
        head = float(np.sqrt((samples[:third] ** 2).mean()))
        tail = float(np.sqrt((samples[-third:] ** 2).mean()))
        assert tail == pytest.approx(head, rel=0.25)

    def test_an_impact_is_the_one_that_should_decay(self):
        """It is a hit, not a hum: it plays once and is gone."""
        samples = np.abs(np.asarray(impact_clip(sample_rate=8000).samples))
        assert float(samples[-200:].max()) < float(samples[:200].max()) * 0.2

    def test_the_wind_is_lower_than_the_tyres(self):
        """Wind over a body is a roar and tyres on tarmac are a hiss. Told
        apart by where the energy sits, since both are noise."""
        def centroid(clip):
            samples = np.asarray(clip.samples)
            power = np.abs(np.fft.rfft(samples)) ** 2
            freqs = np.fft.rfftfreq(len(samples), 1.0 / clip.sample_rate)
            return float((power * freqs).sum() / power.sum())
        assert centroid(wind_clip(sample_rate=8000)) < centroid(
            tyre_clip(sample_rate=8000))


class TestAParkedCarIsQuiet:
    def test_nothing_plays_when_nothing_is_happening(self):
        sound = settled(CarSound(), **_driving(speed=0.0))
        assert sound.motor.gain == pytest.approx(0.0, abs=1e-3)
        assert sound.tyres.gain == pytest.approx(0.0, abs=1e-3)
        assert sound.wind.gain == pytest.approx(0.0, abs=1e-3)

    def test_but_the_motor_answers_the_throttle_before_it_moves(self):
        """A car held on the brake with the power on is a car making a noise,
        which is what the grid sounds like."""
        sound = settled(CarSound(), **_driving(speed=0.0, throttle=1.0))
        assert sound.motor.gain > 0.05


class TestSpeedIsHeard:
    def test_the_motor_rises_in_pitch_with_speed(self):
        """One reduction gear and no clutch: the note is the road speed."""
        slow = settled(CarSound(), **_driving(speed=10.0)).motor.rate
        fast = settled(CarSound(), **_driving(speed=50.0)).motor.rate
        assert fast > slow * 1.5

    def test_and_never_falls_to_nothing_at_a_standstill(self):
        """A rate of zero is a clip that does not advance, which is a click and
        then silence rather than a motor idling."""
        assert settled(CarSound(), **_driving(speed=0.0)).motor.rate > 0.1

    def test_the_wind_rises_faster_than_the_road_speed(self):
        """Drag goes as the square, and so does the noise it makes: that is
        most of what makes speed feel like speed."""
        at30 = settled(CarSound(), **_driving(speed=30.0)).wind.gain
        at60 = settled(CarSound(), **_driving(speed=60.0)).wind.gain
        assert at60 > at30 * 2.5

    def test_the_tyres_are_heard_rolling_before_anything_slides(self):
        assert settled(CarSound(), **_driving(speed=40.0)).tyres.gain > 0.02


class TestALetGoTyreIsHeard:
    """What ``Wheel.slip`` is actually worth, against numbers measured off the
    car rather than picked.

    Driving a circuit it averages 0.09 m/s and never passes 0.19; an autopilot
    pushed 80% past its own grip limit reaches 0.38. A slide is a different
    order: full lock at 30 m/s runs at 1.0 and peaks at 3.2, and a handbrake
    turn averages 2.4 and peaks at 5.0. The band scrub comes in over sits
    above the first and reaches full scale in the second, which is what these
    pin.
    """

    def test_driving_it_properly_scrubs_at_nothing(self):
        """A clean lap has no tyre squeal in it. 0.19 m/s is the worst an
        autopilot produces getting round."""
        clean = settled(CarSound(), **_driving(speed=30.0, slip=0.19))
        rolling = settled(CarSound(), **_driving(speed=30.0, slip=0.0))
        assert clean.tyres.gain == pytest.approx(rolling.tyres.gain, abs=1e-3)

    def test_and_pushing_past_the_limit_barely_does(self):
        """0.38 m/s is an autopilot 80% over its own grip. It is understeer,
        not a slide, and it should not sound like one."""
        pushing = settled(CarSound(), **_driving(speed=30.0, slip=0.38))
        sliding = settled(CarSound(), **_driving(speed=30.0, slip=3.2))
        assert pushing.tyres.gain < sliding.tyres.gain * 0.4

    def test_but_a_slide_is_unmistakable(self):
        """Full lock at 30 m/s peaks at 3.2 m/s of scrub."""
        rolling = settled(CarSound(), **_driving(speed=30.0)).tyres.gain
        sliding = settled(CarSound(), **_driving(speed=30.0, slip=3.2))
        assert sliding.tyres.gain > rolling * 3.0

    def test_and_a_handbrake_turn_is_as_loud_as_it_gets(self):
        """5.0 m/s, the worst measured, is past full scale rather than short
        of it: the loudest slide the car can produce is the loudest sound."""
        from glisteel.sound import TYRE_SCRUB
        worst = settled(CarSound(), **_driving(speed=30.0, slip=5.0))
        assert worst.tyres.gain > TYRE_SCRUB

    def test_more_of_it_is_louder_still(self):
        little = settled(CarSound(), **_driving(speed=30.0, slip=1.0))
        lots = settled(CarSound(), **_driving(speed=30.0, slip=3.0))
        assert lots.tyres.gain > little.tyres.gain

    def test_a_car_in_the_air_makes_no_tyre_noise(self):
        """Nothing is touching anything. The wind does not care."""
        flying = settled(CarSound(),
                         **_driving(speed=40.0, slip=9.0, grounded=False))
        assert flying.tyres.gain == pytest.approx(0.0, abs=1e-3)
        assert flying.wind.gain > 0.05


class TestNothingSteps:
    """A gain that jumps is a click, and a frame is where jumps come from: one
    wheel catching a kerb changes slip by metres a second between two of them.
    """

    def test_a_gain_takes_time_to_arrive(self):
        """One frame of a car sliding flat out gets nowhere near the level it
        settles at -- a tenth of the way, which is a frame's worth of it."""
        sound = CarSound()
        sound.update(FRAME, **_driving(speed=60.0, slip=9.0))
        loud = settled(CarSound(), **_driving(speed=60.0, slip=9.0)).tyres.gain
        assert sound.tyres.gain < loud * 0.25

    def test_and_gets_there_in_about_the_settling_time(self):
        sound = settled(CarSound(), seconds=SETTLE * 3.0,
                        **_driving(speed=60.0, slip=9.0))
        loud = sound.tyres.gain
        settled(sound, seconds=1.0, **_driving(speed=60.0, slip=9.0))
        assert sound.tyres.gain == pytest.approx(loud, rel=0.05)

    def test_no_single_frame_moves_a_gain_far(self):
        """Whatever is thrown at it, and from wherever it starts."""
        sound = settled(CarSound(), **_driving(speed=60.0, slip=9.0))
        worst = 0.0
        for state in (_driving(speed=0.0), _driving(speed=60.0, slip=9.0),
                      _driving(speed=0.0, grounded=False)):
            for _ in range(30):
                was = sound.tyres.gain
                sound.update(FRAME, **state)
                worst = max(worst, abs(sound.tyres.gain - was))
        assert worst <= FRAME / SETTLE + 1e-9

    def test_a_long_frame_does_not_overshoot_its_target(self):
        """A stall, a breakpoint, a first frame: dt is not always 1/60."""
        sound = CarSound()
        sound.update(2.0, **_driving(speed=0.0, throttle=1.0))
        steady = settled(CarSound(), **_driving(speed=0.0, throttle=1.0))
        assert sound.motor.gain == pytest.approx(steady.motor.gain, abs=1e-6)


class TestHittingSomething:
    def test_an_impact_is_a_one_shot_at_a_gain_the_crash_measured(self):
        sound = CarSound()
        assert sound.hit(12.0) > 0.0

    def test_a_harder_one_is_louder(self):
        assert CarSound().hit(20.0) > CarSound().hit(5.0)

    def test_a_nudge_is_not_a_crash(self):
        """Two cars touching at walking pace is not a bang."""
        assert CarSound().hit(0.3) == 0.0

    def test_and_it_is_never_louder_than_full_scale(self):
        assert CarSound().hit(500.0) <= 1.0


class _Wheel:
    def __init__(self, slip=0.0, grounded=True):
        self.slip, self.grounded = slip, grounded


class _Vehicle:
    def __init__(self, throttle=0.0, wheels=()):
        self.throttle, self.wheels = throttle, list(wheels)


class _Car:
    """As much of a car as the soundtrack reads, and no more."""

    def __init__(self, speed=0.0, throttle=0.0, slip=0.0, grounded=True):
        self._speed = speed
        self.vehicle = _Vehicle(throttle,
                                [_Wheel(slip, grounded) for _ in range(4)])

    def speed(self):
        return self._speed


class TestTheSoundtrackIsAPieceOfScene:
    def test_it_is_one_emitter_carrying_every_voice(self):
        from glisteel.sound import Soundtrack
        track = Soundtrack(sample_rate=8000)
        assert len(track.node.sources) == 4

    def test_it_is_global_rather_than_placed(self):
        """The listener is *in* this car. Panning the driver's own motor across
        their head as the car turns would be wrong, and putting it at a
        distance from them wrong twice."""
        from omi_audio import model

        from glisteel.sound import Soundtrack
        assert Soundtrack(sample_rate=8000).node.type == model.GLOBAL

    def test_driving_writes_the_gains_onto_the_nodes(self):
        from glisteel.sound import Soundtrack
        track = Soundtrack(sample_rate=8000)
        for _ in range(120):
            track.update(FRAME, _Car(speed=50.0, throttle=1.0, slip=4.0))
        assert track.motor.gain == pytest.approx(track.sound.motor.gain)
        assert track.motor.playbackRate == pytest.approx(track.sound.motor.rate)
        assert track.tyres.gain == pytest.approx(track.sound.tyres.gain)
        assert track.wind.gain == pytest.approx(track.sound.wind.gain)

    def test_a_car_in_the_air_is_read_off_its_wheels(self):
        from glisteel.sound import Soundtrack
        track = Soundtrack(sample_rate=8000)
        for _ in range(120):
            track.update(FRAME, _Car(speed=40.0, slip=9.0, grounded=False))
        assert track.tyres.gain == pytest.approx(0.0, abs=1e-3)


class TestItPlaysThroughTheEngine:
    """Through the same path a decoded clip takes, which is the whole reason
    ``AudioSource.useClip`` exists."""

    @pytest.fixture
    def engine(self):
        from omi_audio.device import NullDevice
        from omi_audio.engine import AudioEngine
        made = AudioEngine(device=NullDevice(sample_rate=8000), voices=8)
        yield made
        made.close()

    def frame(self, track, engine, car, now):
        """One frame of the game, and one frame's worth of audio to go with it.

        A silent device pulls nothing, so a voice only advances when the mixer
        is asked for samples -- which is what a real device does sixty or more
        times a second, and what makes a one-shot here actually end.
        """
        track.update(FRAME, car)
        track.node.updateAudio(engine, np.identity(4), now)
        engine.mixer.mix(int(FRAME * 8000))

    def test_the_three_loops_take_a_voice_each_and_keep_them(self, engine):
        from glisteel.sound import Soundtrack
        track = Soundtrack(sample_rate=8000)
        for step in range(120):
            self.frame(track, engine, _Car(speed=30.0), step * FRAME)
        assert engine.active_voices == 3

    def test_an_impact_sounds_once_rather_than_every_frame(self, engine):
        """Once its voice has ended it stays quiet until the next crash."""
        from glisteel.sound import Soundtrack
        track = Soundtrack(sample_rate=8000)
        self.frame(track, engine, _Car(speed=30.0), 0.0)
        assert track.hit(15.0) > 0.0
        track.node.updateAudio(engine, np.identity(4), FRAME)
        assert engine.active_voices == 4, 'the bang did not sound'
        engine.mixer.mix(int(FRAME * 8000))
        for step in range(2, 400):
            self.frame(track, engine, _Car(speed=30.0), step * FRAME)
        assert engine.active_voices == 3

    def test_a_crash_is_heard_in_the_order_a_session_runs(self, engine):
        """The physics step reports the crash, the soundtrack updates after
        the steps, and the render pass drives the node after that."""
        from glisteel.sound import Soundtrack
        track = Soundtrack(sample_rate=8000)
        self.frame(track, engine, _Car(speed=30.0), 0.0)
        track.hit(15.0)
        self.frame(track, engine, _Car(speed=30.0), FRAME)
        assert engine.active_voices == 4, 'the bang did not sound'

    def test_a_second_crash_is_heard_too(self, engine):
        from glisteel.sound import Soundtrack
        track = Soundtrack(sample_rate=8000)
        track.hit(15.0)
        self.frame(track, engine, _Car(speed=30.0), 0.0)
        for step in range(1, 400):
            self.frame(track, engine, _Car(speed=30.0), step * FRAME)
            engine.mixer.mix(int(FRAME * 8000))
        assert engine.active_voices == 3
        track.hit(15.0)
        self.frame(track, engine, _Car(speed=30.0), 400 * FRAME)
        assert engine.active_voices == 4, 'the second bang did not sound'

    def test_a_nudge_is_silent(self, engine):
        from glisteel.sound import Soundtrack
        track = Soundtrack(sample_rate=8000)
        self.frame(track, engine, _Car(speed=30.0), 0.0)
        assert track.hit(0.2) == 0.0
        self.frame(track, engine, _Car(speed=30.0), FRAME)
        assert engine.active_voices == 3

    def test_silence_is_a_valid_backend(self):
        """A machine with no device runs this unchanged: the nodes traverse,
        the engine is None, and nothing plays."""
        from glisteel.sound import Soundtrack
        track = Soundtrack(sample_rate=8000)
        track.update(FRAME, _Car(speed=30.0))
        track.node.updateAudio(None, np.identity(4), 0.0)

    def test_the_loudest_thing_the_car_can_do_does_not_clip(self, engine):
        """Sliding flat out and hitting something in the middle of it.

        The headroom is spent on purpose and this is the budget: a clean lap
        peaks at about 0.10 of full scale, a slide at 0.36, and the hardest
        crash on top of a slide at 0.81. Raise any gain and it is this that
        goes over, which is a crash that arrives as a crunch of clipping rather
        than as a bang.
        """
        from glisteel.sound import Soundtrack
        track = Soundtrack(sample_rate=8000)
        car = _Car(speed=60.0, throttle=1.0, slip=5.0)
        peak = 0.0
        for step in range(300):
            track.update(FRAME, car)
            if step == 150:
                track.hit(60.0)
            track.node.updateAudio(engine, np.identity(4), step * FRAME)
            block = engine.mixer.mix(int(FRAME * 8000))
            peak = max(peak, float(np.abs(block).max()))
        assert 0.5 < peak <= 1.0, 'peaked at %.3f' % peak
