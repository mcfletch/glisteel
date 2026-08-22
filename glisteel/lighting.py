"""What lights a bore, and what the car carries into one.

A renderer binds a handful of lights in a frame -- :data:`BUDGET` of them -- and
a tunnel has one every twenty-five metres. So a bore is lit **twice**, and the
two halves do different jobs:

**The lining lights itself.** The pool each luminaire throws is baked onto the
lining's vertices when the world is built
(:func:`OpenGLContext.scenegraph.roadworks.bore_shade`), so the whole length of
a bore is lit at any distance and costs nothing to draw. What that cannot do is
light anything *in* the bore: a car under a lamp has no idea it is under one.

**The few fittings the driver is among become real lights.** That is
:class:`Luminaires`, and it is the whole reason the lamp positions travel in the
tileset rather than being left in the geometry.

The budget then divides:

======  =========================================
2       the sun and its sky fill
4       the luminaires the car is among
1       the headlights
======  =========================================

which is seven of eight, leaving one for whatever a world wants next.

Neither class touches OpenGL or the scenegraph: they answer *which* lights and
*where*, and the window puts them there.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = ['BUDGET', 'Headlights', 'Luminaires', 'LAMP_COLOUR', 'BEAM_COLOUR']

#: How many lights a frame may bind. The renderer's own ceiling
#: (:attr:`OpenGLContext.passes.shaderpass.VRML97ShaderProgram.MAX_LIGHTS`), and
#: what everything here is divided out of.
BUDGET = 8

#: Sodium: what a tunnel is lit with nearly everywhere it is lit at all, and
#: what makes a bore read as a bore rather than as a grey corridor.
LAMP_COLOUR = (1.0, 0.72, 0.36)

#: A headlight is cool and slightly blue, the way a discharge lamp is, so it
#: reads as the car's own light against the sodium.
BEAM_COLOUR = (0.92, 0.95, 1.0)


def _fade(share: float) -> float:
    """One at the lamp, nothing at the edge of the reach, smooth between.

    Smooth in its *slope* as well as its value, so a lamp neither appears nor
    goes out with an edge to it: what the eye catches is the change in the
    rate of change as much as the change itself.
    """
    left = 1.0 - min(max(float(share), 0.0), 1.0)
    return float(left * left * (3.0 - 2.0 * left) * left)


class Luminaires:
    """The lamps in a world's bores, and which of them are worth a real light.

    ``lamps`` is (N,3) world points, as the bake wrote them; None or empty is a
    world with no bores, which is not an error. ``count`` is how many may burn
    at once and ``reach`` how far away one is still worth spending a light on.

    It holds no state, so the same one serves a whole race.
    """

    def __init__(self, lamps: Any, count: int = 4, reach: float = 120.0) -> None:
        found = np.zeros((0, 3)) if lamps is None else np.asarray(lamps, dtype='d')
        #: Every lamp in the world, as (N,3) world points.
        self.lamps = found.reshape(-1, 3)
        self.count = max(0, int(count))
        self.reach = float(reach)

    def __repr__(self) -> str:
        return 'Luminaires(%d lamps, %d at a time)' % (len(self.lamps), self.count)

    def nearest(self, position: Any) -> list[int]:
        """Which lamps to light from where the car is, nearest first.

        A list of indices rather than points, so a caller can keep one light per
        slot and only move it when the answer changes -- which it does rarely,
        since a lamp is twenty-five metres of road.
        """
        if not len(self.lamps) or not self.count:
            return []
        away: np.ndarray = np.linalg.norm(
            self.lamps - np.asarray(position, dtype='d')[:3], axis=1)
        within = np.flatnonzero(away <= self.reach)
        if not len(within):
            return []
        order = within[np.argsort(away[within])][:self.count]
        return [int(one) for one in order]

    def burning(self, position: Any) -> list[tuple[int, float]]:
        """Which lamps to light from where the car is, and how brightly.

        Each is paired with a *share* of full strength that falls to nothing
        by :attr:`reach`, so a lamp is already out by the time it stops being
        one of the nearest and the next one arrives dark. Bound at full
        strength and dropped at full strength, the set changing is a step
        change in the picture -- and in a bore it changes every twenty-five
        metres, which is the whole length of it flickering.

        Nearest first, so a caller can hold one light per slot and move it.
        """
        at = np.asarray(position, dtype='d')[:3]
        if not len(self.lamps) or not self.count:
            return []
        away: np.ndarray = np.linalg.norm(self.lamps - at, axis=1)
        order = np.argsort(away)[:self.count + 1]
        near = away[order]
        # Nothing left by the first lamp there is no light for, so the one on
        # its way out is already dark when it goes and the one arriving is
        # dark when it arrives. Where every lamp in the world fits at once,
        # that is the reach instead.
        horizon = float(near[-1]) if len(near) > self.count else self.reach
        horizon = min(max(horizon, 1e-6), self.reach)
        return [(int(index), _fade(float(distance) / horizon))
                for index, distance in zip(order[:self.count], near,
                                          strict=False)
                if distance < horizon]

    def at(self, index: int) -> np.ndarray:
        """Where one lamp hangs."""
        lamp: np.ndarray = self.lamps[int(index)]
        return lamp


@dataclass
class Headlights:
    """The light the car carries, for when the road has none.

    One light rather than two: a pair costs twice the budget and, dipped and
    converged the way a car's are, throws very nearly the same pool. What sells
    them is that the pool *sweeps* as the car turns, and one does that.

    Its numbers are fields rather than class attributes, as
    :class:`~glisteel.car.CarSpec` and :class:`~glisteel.driver.DriverStyle`
    are: a car with a different beam is a different set of numbers, not a
    subclass.
    """

    #: Whether the car has any at all, and whether they burn in daylight too;
    #: otherwise they come on where it is dark.
    fitted: bool = True
    always: bool = False

    #: Where the beam comes from, in the car's own frame: the front of it, at
    #: about the height of a headlamp. Negative Z is forward.
    offset: tuple[float, float, float] = (0.0, -0.05, -1.9)

    #: How far below the car's own direction the beam points. Dipped, because a
    #: beam on the horizon lights the sky and blinds whatever is coming.
    dip: float = 0.11

    #: How far it reaches, in metres, and how wide the pool is, in radians.
    reach: float = 70.0
    spread: float = 0.42

    #: How hard it burns.
    intensity: float = 3.2

    def __repr__(self) -> str:
        return 'Headlights(%s)' % ('fitted' if self.fitted else 'none')

    @property
    def count(self) -> int:
        """How much of the budget this spends."""
        return 1 if self.fitted else 0

    def wanted(self, dark: bool) -> bool:
        """Whether the beam should be burning."""
        return self.fitted and (self.always or bool(dark))

    def aim(self, forward: Any) -> np.ndarray:
        """Which way the beam points, given which way the car does."""
        ahead = np.asarray(forward, dtype='d')[:3].astype('d')
        length = float(np.linalg.norm(ahead))
        ahead = ahead / length if length > 1e-9 else np.array([0.0, 0.0, -1.0])
        beam = ahead + np.array([0.0, -self.dip, 0.0])
        aimed: np.ndarray = beam / float(np.linalg.norm(beam))
        return aimed
