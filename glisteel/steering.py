"""Steering with a pointer, until there is a wheel or a pad to steer with.

A keyboard gives three states -- full left, straight, full right -- and no
amount of tuning in the vehicle makes that feel like a car. A pointer gives a
*position*, and turning sideways movement into lock is what mouse-look already
does for a head.

The wheel is **centred on the window** rather than accumulated from the
movements. An accumulated angle drifts, and a pointer that has to be walked back
to the middle before the car will go straight is a pointer nobody can drive
with: where the pointer is across the window *is* where the wheel is, and
letting go of it in the middle is straight ahead.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

__all__ = ['CONTROLS', 'KEY_FOR', 'KeyboardDriver', 'KeyboardWheel',
           'MouseWheel', 'TRAVEL', 'CURVE', 'WIND_ON', 'CENTRE']

#: How much of the window's half-width is full lock. Under 1 so a driver does
#: not have to reach the very edge of the screen to get all of it.
TRAVEL = 0.8

#: How the lock is shaped across that travel. 1 is proportional; above it the
#: middle is gentler and the ends are as far as ever, which is what keeps a
#: twitch at speed a twitch rather than a spin.
CURVE = 1.8


class MouseWheel:
    """Where the steering is, from where the pointer is across the window.

    ``width`` is the window's width in pixels, ``travel`` how much of its half
    is full lock, and ``curve`` how the lock is shaped across that. Positive is
    left, which is the direction a positive steering input turns towards.
    """

    def __init__(self, width: int = 1280, travel: float = TRAVEL,
                 curve: float = CURVE) -> None:
        self.width = max(int(width), 1)
        self.travel = max(float(travel), 1e-3)
        self.curve = max(float(curve), 1e-3)
        #: Where the wheel was last put, so a physics step reads the same
        #: answer however often it asks between one frame and the next.
        self.position = 0.0

    def resize(self, width: int) -> None:
        """The window changed size; the middle of it moved with it."""
        self.width = max(int(width), 1)

    def moved(self, x: int) -> float:
        """The pointer is here: turn the wheel to match, and say where it is."""
        self.position = self.steer(x)
        return self.position

    def steer(self, x: int) -> float:
        """What the wheel reads with the pointer at ``x`` pixels across."""
        half = self.width / 2.0
        offset = (half - float(x)) / (half * self.travel)
        offset = max(-1.0, min(1.0, offset))
        shaped = abs(offset) ** self.curve
        return float(shaped if offset >= 0.0 else -shaped)


#: How quickly the keyboard wheel winds on toward a lock the driver is holding,
#: in wheel units -- full lock is one -- a second. Slow: it is a hand moving a
#: wheel, and a hand does not put a road car on full lock in half a second. It
#: also has to be slower than the shortest input a player can actually give,
#: which is one frame; at thirty frames a second that is a thirtieth of full
#: lock, and at ten it is a tenth.
WIND_ON = 0.9

#: How quickly it returns to centre with nothing held, brisker than it winds on
#: so letting go of a key straightens the car promptly.
CENTRE = 4.5


class KeyboardWheel:
    """A steering wheel driven by on/off keys, kept as a smoothed position.

    Left and right are a key each, so the only inputs are full left, straight
    and full right. Handed to the car as they are, that is a wheel yanked to the
    stop and back, and at speed a tap is a spin. :meth:`toward` makes it a wheel
    that *winds*: it moves toward the held lock at ``wind_on`` wheel units a
    second and back to centre at ``centre``, so a tap is a small angle and a
    hold builds to full lock.

    ``position`` is where the wheel is, from -1 (full right) to +1 (full left),
    the sign a positive steering input turns towards -- the same convention as
    :class:`MouseWheel`, so the two are interchangeable where the car is
    steered.
    """

    def __init__(self, wind_on: float = WIND_ON, centre: float = CENTRE) -> None:
        self.wind_on = max(float(wind_on), 1e-3)
        self.centre = max(float(centre), 1e-3)
        #: Where the wheel is, read once a physics step.
        self.position = 0.0

    def toward(self, target: float, dt: float) -> float:
        """Wind the wheel toward ``target`` over ``dt`` seconds, and say where
        it now is.

        ``target`` is where the keys are asking for it: +1 for left held, -1 for
        right, 0 for neither. Coming back to centre, or crossing it to the other
        lock, uses the quicker ``centre`` rate; winding further into a lock uses
        ``wind_on``.
        """
        target = max(-1.0, min(1.0, float(target)))
        returning = target == 0.0 or (
            self.position != 0.0 and (self.position > 0.0) != (target > 0.0))
        rate = self.centre if returning else self.wind_on
        step = rate * max(float(dt), 0.0)
        if self.position < target:
            self.position = min(target, self.position + step)
        else:
            self.position = max(target, self.position - step)
        return self.position


#: How slowly the car has to be going before the brake becomes a reverse, in
#: metres per second. Walking pace: below it the car has stopped as far as the
#: driver is concerned, and holding the key means "go backwards".
ROLLING = 0.4

#: Which keys do what. Each is a frozen set of names, so the arrows and WASD
#: are the same control rather than two.
#:
#: Frozen, and a mapping rather than a dict: this is the *default*, and a game
#: whose keys could be rebound by anything that got hold of it would be a game
#: where one screen's rebinding changed every other. A driver that wants
#: different keys is handed them (:class:`KeyboardDriver`).
CONTROLS: Mapping[str, frozenset[str]] = MappingProxyType({
    'throttle': frozenset({'w', '<up>'}),
    'brake': frozenset({'s', '<down>'}),
    'left': frozenset({'a', '<left>'}),
    'right': frozenset({'d', '<right>'}),
    'handbrake': frozenset({' '}),
})


#: Which key stands for each control when something presses one on a driver's
#: behalf -- a written-down drive, or an autopilot at the controls. Settled here
#: rather than chosen per step: a control is a set of keys that mean the same
#: thing, so any of them will do, and picking one is not a decision to make a
#: hundred and twenty times a second.
KEY_FOR = {control: sorted(keys)[0] for control, keys in CONTROLS.items()}


class KeyboardDriver:
    """Whoever is at the keyboard, as a driver a run can be handed.

    Holds the keys that are down and the wheel they wind, and answers the
    pedals and the steering once per physics step -- a
    :class:`~glisteel.session.Controller`, so a session neither knows nor cares
    whether a person or the autopilot is driving.

    ``pointer`` is a :class:`MouseWheel` for steering with the mouse, or None
    for the keys alone. The keys take the wheel back from the pointer while one
    is down, because a driver reaching for a key has decided the pointer is not
    where they want it.
    """

    def __init__(self, pointer: MouseWheel | None = None,
                 controls: Mapping[str, frozenset[str]] | None = None) -> None:
        #: The names of the keys that are down.
        self.held: set[str] = set()
        self.keys = KeyboardWheel()
        self.pointer = pointer
        #: Which keys this driver answers to. :data:`CONTROLS` unless a caller
        #: says otherwise, which is where rebinding goes.
        self.controls_for = dict(controls if controls is not None else CONTROLS)

    def press(self, name: str) -> None:
        self.held.add(name)

    def release(self, name: str) -> None:
        self.held.discard(name)

    def release_all(self) -> None:
        """Let go of everything.

        For losing the window: a key whose release nobody saw is a key held
        down for ever, and a wheel wound to full lock that never comes back.
        """
        self.held.clear()

    def holding(self, control: str) -> bool:
        """Whether any of the keys for a control is down."""
        return bool(self.held & self.controls_for[control])

    def pedals(self, session: object) -> tuple[float, float]:
        """The throttle and the brake, from whatever is held down.

        Separate from the wheel because every way of driving the car wants the
        same two pedals (:mod:`glisteel.schemes`), and only some of them want
        the steering to mean a steering lock.
        """
        throttle = 1.0 if self.holding('throttle') else 0.0
        brake = 0.0
        if self.holding('brake'):
            # One pedal, two meanings: it stops a car that is moving forward
            # and reverses one that has stopped, which is what an arrow key on
            # a keyboard has to do.
            car = getattr(session, 'car', None)
            if car is not None and car.forward_speed() > ROLLING:
                brake = 1.0
            else:
                throttle = -1.0
        if self.holding('handbrake'):
            brake = 1.0
        return throttle, brake

    def key_axis(self) -> float:
        """Which way the steering keys are asking for: 1 left, -1 right, 0 none.

        The keys as they are, before :class:`KeyboardWheel` winds a wheel out
        of them. What a way of driving that steers by *position* wants is the
        request itself, since the winding is what turns a request into a lock.
        """
        return ((1.0 if self.holding('left') else 0.0)
                - (1.0 if self.holding('right') else 0.0))

    def pointer_axis(self) -> float | None:
        """Where the pointer is asking for, or None where nothing steers by it."""
        return None if self.pointer is None else float(self.pointer.position)

    def axis(self) -> float:
        """What the driver is asking for with the steering, from -1 to 1.

        The keys where one is down, and the pointer otherwise: a driver
        reaching for a key has decided the pointer is not where they want to be.
        """
        keys = self.key_axis()
        if keys or self.pointer is None:
            return keys
        return float(self.pointer.position)

    def controls(self, session: object, dt: float) -> tuple[float, float, float]:
        """The pedals and the wheel, from whatever is held down.

        ``dt`` is the step the steering is wound over: the keys give full lock
        or none, and :class:`KeyboardWheel` turns that into a wheel that eases
        on and off rather than a switch.
        """
        throttle, brake = self.pedals(session)
        target = self.key_axis()
        if self.pointer is not None and not target:
            return throttle, brake, self.pointer.position
        return throttle, brake, self.keys.toward(target, dt)
