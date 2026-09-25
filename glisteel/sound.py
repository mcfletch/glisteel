"""What the car sounds like: the engine's vehicle sound, tuned to this car.

A GLinting Steel car is an EV, and its sound is a motor whine whose pitch is
the road speed, tyres that hiss rolling and roar scrubbing, and wind that goes
as the square of speed. The engine makes all of it from arithmetic
(:mod:`omi_audio.vehicle` for the levels, :mod:`OpenGLContext.audio.vehicle`
for the scene nodes), so the car's sound ships in the wheel with no licence,
no attribution and no content pack. What is here is this car's figures,
:data:`TUNING`, and the names the session uses.

:class:`CarSound` is the behaviour and touches nothing: speed, scrub, throttle
and ground contact in, gains and rates out. :class:`Soundtrack` owns the nodes
and reads the car once a frame.
"""
from __future__ import annotations

from typing import Any

from omi_audio import vehicle
from omi_audio.clip import DEFAULT_SAMPLE_RATE, Clip
from omi_audio.vehicle import VehicleSound, VehicleSoundTuning, Voice
from OpenGLContext.audio.vehicle import VehicleSoundtrack

__all__ = ['Voice', 'CarSound', 'Soundtrack', 'TUNING',
           'motor_clip', 'tyre_clip', 'wind_clip', 'impact_clip',
           'MOTOR_HZ', 'SETTLE', 'TYRE_SCRUB']

#: This car's sound. Speeds are m/s, gains 0 to 1, pitches Hz.
#:
#: The scrub band is set from this car's own ``Wheel.slip``: ordinary driving
#: stays under 0.2 m/s and a driver pushing past the grip limit under 0.4,
#: while a slide runs from about 1 m/s to 5. So scrub is silent up to 0.25 and
#: full at 3.5, and what is heard is a tyre letting go rather than a corner
#: being approached fast; the number does not rise progressively towards the
#: limit. The measurements are in ``plans/DRIVING-AND-PLACE.md``.
TUNING = VehicleSoundTuning(
    loop=2.0, motor_hz=400.0, motor_at=25.0, motor_partials=7,
    motor_idle=0.2, motor_load=0.16, motor_roll=0.05,
    tyre_roll=0.12, tyre_roll_at=30.0,
    tyre_scrub=0.5, tyre_scrub_from=0.25, tyre_scrub_at=3.5,
    wind=0.35, wind_at=60.0, settle=0.15, hit_at=25.0, hit_floor=1.0)

MOTOR_HZ = TUNING.motor_hz
SETTLE = TUNING.settle
TYRE_SCRUB = TUNING.tyre_scrub


def motor_clip(sample_rate: int = DEFAULT_SAMPLE_RATE) -> Clip:
    """The motor's whine, as a loop of whole cycles."""
    found: Clip = vehicle.motor_clip(TUNING, sample_rate)
    return found


def tyre_clip(sample_rate: int = DEFAULT_SAMPLE_RATE) -> Clip:
    """Tarmac under a tyre, level throughout the loop."""
    found: Clip = vehicle.tyre_clip(TUNING, sample_rate)
    return found


def wind_clip(sample_rate: int = DEFAULT_SAMPLE_RATE) -> Clip:
    """Air over the body, lower than the tyres."""
    found: Clip = vehicle.wind_clip(TUNING, sample_rate)
    return found


def impact_clip(sample_rate: int = DEFAULT_SAMPLE_RATE) -> Clip:
    """Hitting something: a decaying bang, played once."""
    found: Clip = vehicle.impact_clip(TUNING, sample_rate)
    return found


class CarSound(VehicleSound):
    """The car's three continuous voices, at this car's :data:`TUNING`."""

    def __init__(self) -> None:
        super().__init__(TUNING)


class Soundtrack(VehicleSoundtrack):
    """The car's voices as a piece of scene, fed from the car once a frame.

    Mount :attr:`node` anywhere in the world; with no audio device the nodes
    traverse and nothing plays.
    """

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        super().__init__(TUNING, sample_rate)

    def update(self, dt: float, car: Any, speed: float | None = None) -> None:
        """Read the car's vehicle and write this frame's levels onto the nodes."""
        super().update(dt, car.vehicle,
                       speed=car.speed() if speed is None else speed)
