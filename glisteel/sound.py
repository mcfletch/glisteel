"""What the car sounds like, out of arithmetic rather than out of files.

A GLinting Steel car is an EV, and an EV's noise is almost entirely three
things that a physics step already knows: a motor whine whose pitch is the road
speed, tyres whose hiss is how fast they are rolling and whose roar is how much
they are scrubbing, and wind that goes as the square of how fast the body is
being pushed through the air. None of those is a recording of anything. They are
:mod:`omi_audio.synth` clips -- a tone with a harmonic series, and noise with
the top or the bottom taken off -- played round and round, with the gain and the
playback rate written every frame.

**Which is why the game has sound and no content pack.** A sound made of
arithmetic has no licence, no attribution and no download; it ships in the wheel
at the size of the code that makes it. Birdsong and water are recordings and
belong in a pack (`plans/DRIVING-AND-PLACE.md` §5); the car does not.

:class:`CarSound` is the whole of the behaviour and touches nothing: four
numbers and a time step in, gains and rates out. :class:`Soundtrack` is the thin
part that owns the nodes and writes one onto the other. That split is what lets
everything a player would describe as how the car sounds be tested with no
device, no window and no audio thread.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any

from omi_audio import model, synth
from omi_audio.clip import DEFAULT_SAMPLE_RATE, Clip
from OpenGLContext.scenegraph.audio import AudioEmitter, AudioSource

__all__ = ['Voice', 'CarSound', 'Soundtrack',
           'motor_clip', 'tyre_clip', 'wind_clip', 'impact_clip',
           'MOTOR_HZ', 'SETTLE']

#: How long a loop is, in seconds. Long enough that noise does not repeat as a
#: pattern the ear picks out, short enough to cost a few tens of kilobytes of
#: float32 each.
LOOP = 2.0

#: The motor's written pitch, in hertz, and the road speed at which it plays at
#: that pitch, in metres per second. ``MOTOR_HZ * LOOP`` is a whole number on
#: purpose: the clip then holds an exact number of cycles, the wrap from its
#: last sample to its first is one more step of the same sine, and the loop
#: cannot be heard.
MOTOR_HZ = 400.0
MOTOR_AT = 25.0

#: How many partials the whine has. A pure sine is a test tone; the ``1/n``
#: series of a sawtooth is reedy, which is what a stator under load is.
MOTOR_PARTIALS = 7

#: The slowest the motor clip is ever played, as a fraction of its written
#: pitch. A rate of zero is a clip that does not advance -- a click and then
#: silence -- rather than a motor idling, so a stationary car still hums.
MOTOR_IDLE = 0.2

#: How loud the motor gets: with the power on, and with speed alone. An EV is
#: quiet coasting and whines when it is asked for something, so most of the
#: level is the first and a little is the second.
MOTOR_LOAD = 0.16
MOTOR_ROLL = 0.05

#: Tyres: how loud rolling gets and the road speed it takes to get there, then
#: how loud scrubbing gets and the band of sideways speed at the contact patch
#: it comes in over. Scrub is much the louder of the two, which is the point of
#: reading it: a car that has let go should be unmistakable.
#:
#: **The band is measured, not chosen.** ``Wheel.slip`` is the sideways speed at
#: the contact patch, and on this car it stays very small until the tyre
#: actually breaks away: driving a circuit it is 0.09 m/s on average and 0.19 at
#: worst, and an autopilot pushed to 80% past its own grip limit still only
#: reaches 0.38. A real slide is a different order -- full lock at 30 m/s runs
#: at 1.0 and peaks at 3.2, and a handbrake turn averages 2.4 and peaks at 5.0.
#: So the floor sits above everything ordinary driving produces, and full scale
#: is where a proper slide lives. Scaled to the whole range instead, as this
#: first was, a slide reaches a twentieth of the level and nothing is ever
#: heard.
#:
#: What that makes audible is a tyre **letting go**, not a corner being
#: approached too fast: the number does not rise progressively towards the
#: limit, so nothing here can claim to warn of one.
TYRE_ROLL = 0.12
TYRE_ROLL_AT = 30.0
TYRE_SCRUB = 0.5
TYRE_SCRUB_FROM = 0.25
TYRE_SCRUB_AT = 3.5

#: Wind: how loud it gets, and the speed at which it is that loud. Squared,
#: because drag is, so it climbs slowly and then quickly -- which is most of
#: what makes speed feel like speed.
WIND = 0.35
WIND_AT = 60.0

#: How long a gain takes to travel full scale, in seconds.
#:
#: A gain that jumps is a click, and a frame is where jumps come from: one wheel
#: catching a kerb changes slip by metres a second between two of them. Short
#: enough that a slide is heard as it starts rather than after it.
SETTLE = 0.15

#: What an impact sounds like: the closing speed that is full scale, in metres
#: per second, and the one below which two cars touching is not a bang at all.
HIT_AT = 25.0
HIT_FLOOR = 1.0


def _clamped(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else (high if value > high else value)


# Built once and shared. Four clips is a megabyte or so of float32 and about
# fifteen milliseconds of numpy, and every car that ever sounds wants exactly
# the same four -- so a race, a replay and a suite full of sessions pay for
# them once between them. Nothing writes to a clip: resampling one for an
# engine at another rate returns a new clip and leaves this alone.
@cache
def motor_clip(sample_rate: int = DEFAULT_SAMPLE_RATE) -> Clip:
    """The motor's whine, as a loop of whole cycles.

    ``fade=0`` on purpose: a clip that ramps in and out pulses at the loop rate,
    which is a sound of its own and not the one that was wanted. It is safe here
    because the waveform starts and ends at the same phase.
    """
    return synth.tone(MOTOR_HZ, LOOP, sample_rate=sample_rate, amplitude=0.5,
                      fade=0.0, harmonics=MOTOR_PARTIALS)


@cache
def tyre_clip(sample_rate: int = DEFAULT_SAMPLE_RATE) -> Clip:
    """Tarmac under a tyre: a hiss with some body under it.

    ``decay=0`` holds the level for the whole loop, and noise joins to noise,
    so there is nothing at the seam to hear.
    """
    return synth.rumble(LOOP, sample_rate=sample_rate, amplitude=0.6,
                        decay=0.0, attack=0.0, tone=0.0, cutoff=3000.0,
                        floor=120.0, tilt=-2.0, seed=7)


@cache
def wind_clip(sample_rate: int = DEFAULT_SAMPLE_RATE) -> Clip:
    """Air over a body: the same noise with the top taken off.

    Lower than the tyres, which is how the ear tells two noises apart when
    neither has a pitch.
    """
    return synth.rumble(LOOP, sample_rate=sample_rate, amplitude=0.6,
                        decay=0.0, attack=0.0, tone=0.0, cutoff=600.0,
                        tilt=-4.0, seed=11)


@cache
def impact_clip(sample_rate: int = DEFAULT_SAMPLE_RATE) -> Clip:
    """Hitting something: a bang with body, not a crack.

    The one clip here that is meant to decay, because it plays once.
    """
    return synth.rumble(0.9, sample_rate=sample_rate, amplitude=0.9,
                        decay=7.0, tone=0.35, pitch=90.0, pitch_end=45.0,
                        cutoff=2200.0, tilt=-3.0, drive=1.4, seed=3)


@dataclass
class Voice:
    """One continuous sound: how loud it is, and how fast it is played.

    ``rate`` is speed and pitch together, as speeding up a record is, which is
    what ``AudioSource.playbackRate`` means.
    """

    gain: float = 0.0
    rate: float = 1.0

    def towards(self, gain: float, dt: float, settle: float = SETTLE) -> None:
        """Move ``gain`` no faster than full scale in ``settle`` seconds."""
        step = dt / max(settle, 1e-6)
        self.gain += max(-step, min(step, gain - self.gain))


class CarSound:
    """The car's three continuous voices, driven by what the physics knows.

    Fed once a frame with the road speed in metres per second, how much the
    tyres are scrubbing (the sideways speed at the contact patch, averaged over
    the wheels), how hard the motor is being asked to work from 0 to 1, and
    whether any wheel is on anything at all.

    Reading rather than being told is the point: nothing here is scripted to a
    lap or triggered by an event, so the car sounds like whatever it is
    actually doing, including things nobody wrote a case for.
    """

    def __init__(self) -> None:
        #: The whine. Its rate is the road speed; its gain is the load.
        self.motor = Voice(rate=MOTOR_IDLE)
        #: The tyres. Rolling and scrubbing together, silent off the ground.
        self.tyres = Voice()
        #: The air. Speed alone, squared.
        self.wind = Voice()

    def update(self, dt: float, speed: float, slip: float = 0.0,
               throttle: float = 0.0, grounded: bool = True) -> None:
        """Drive the voices for ``dt`` seconds of the car doing this."""
        speed, slip = abs(float(speed)), abs(float(slip))
        self.motor.rate = MOTOR_IDLE + speed / MOTOR_AT
        self.motor.towards(MOTOR_LOAD * _clamped(throttle)
                           + MOTOR_ROLL * _clamped(speed / MOTOR_AT), dt)
        rolling = TYRE_ROLL * _clamped(speed / TYRE_ROLL_AT)
        scrubbing = TYRE_SCRUB * _clamped(
            (slip - TYRE_SCRUB_FROM) / (TYRE_SCRUB_AT - TYRE_SCRUB_FROM))
        self.tyres.towards((rolling + scrubbing) if grounded else 0.0, dt)
        self.wind.towards(WIND * _clamped(speed / WIND_AT) ** 2, dt)

    def hit(self, closing: float) -> float:
        """How loud an impact at ``closing`` metres a second is, 0 for none.

        A one-shot rather than a voice: it is played once at this gain and is
        then over, so there is nothing here to keep. Two cars touching at
        walking pace is not a bang, which is what :data:`HIT_FLOOR` says.
        """
        closing = abs(float(closing))
        if closing < HIT_FLOOR:
            return 0.0
        return _clamped(closing / HIT_AT)


def _looping(clip: Clip) -> AudioSource:
    """One of the three continuous voices, ready to be mounted.

    Started once and never stopped: its level is its ``gain``, and a car that
    is making no noise is these three playing at nothing. Starting and stopping
    a loop to save a voice would put a discontinuity at each end of every
    silence, which is a click exactly where the car was quiet.
    """
    source = AudioSource(loop=True, autoplay=True, gain=0.0)
    source.useClip(clip)
    return source


class Soundtrack:
    """The car's voices as a piece of scene, and the thing that feeds them.

    Mount :attr:`node` anywhere in the world and call :meth:`update` once a
    frame with the car. There is nothing to position: the emitter is
    ``global``, because the listener is *in* this car -- panning the driver's
    own motor across their head as the car turns would be wrong, and putting it
    at a distance from them wrong twice.

    A machine with no audio device runs this unchanged: the nodes traverse, the
    engine is None, and nothing plays. That is the engine's own arrangement and
    costs nothing here.
    """

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self.sound = CarSound()
        self.motor = _looping(motor_clip(sample_rate))
        self.tyres = _looping(tyre_clip(sample_rate))
        self.wind = _looping(wind_clip(sample_rate))
        #: Hitting something: silent until :meth:`hit` arms it, and armed for
        #: exactly one frame so that a bang plays once rather than every frame.
        self.impact = AudioSource(loop=False, autoplay=False, gain=0.0)
        self.impact.useClip(impact_clip(sample_rate))
        #: What to put in the scene.
        self.node = AudioEmitter(
            type=model.GLOBAL,
            sources=[self.motor, self.tyres, self.wind, self.impact])

    def update(self, dt: float, car: Any) -> None:
        """Read the car, drive the voices, and write the result onto the nodes.

        Everything it reads, the physics already computed for its own reasons:
        ``Wheel.slip`` is the sideways speed at the contact patch, which
        :mod:`omi_physics` documents as the number to make tyre noise from.
        """
        wheels = list(getattr(car.vehicle, 'wheels', ()))
        grounded = any(wheel.grounded for wheel in wheels)
        slip = (sum(abs(float(wheel.slip)) for wheel in wheels) / len(wheels)
                if wheels else 0.0)
        self.sound.update(dt, speed=car.speed(), slip=slip,
                          throttle=abs(float(car.vehicle.throttle)),
                          grounded=grounded)
        self.motor.gain = self.sound.motor.gain
        self.motor.playbackRate = self.sound.motor.rate
        self.tyres.gain = self.sound.tyres.gain
        self.wind.gain = self.sound.wind.gain
        # Armed for one frame and no more. By the next one the emitter has
        # started it and holds a playing voice, which it will not restart; a
        # source left armed would bang again the moment that voice ended.
        self.impact.autoplay = False

    def hit(self, closing: float) -> float:
        """Bang, at a level the closing speed decides. Returns that level.

        Nought for a touch too gentle to be a crash, in which case nothing is
        armed and nothing sounds.
        """
        gain = self.sound.hit(closing)
        if gain > 0.0:
            self.impact.gain = gain
            self.impact.autoplay = True
        return gain
