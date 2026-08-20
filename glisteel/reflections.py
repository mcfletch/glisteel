"""What the car reflects, and what changes it.

A painted metal surface is almost entirely its surroundings: the colour a car
is painted decides very little of what reaches the eye, and the environment
around it decides the rest. A car lit by a bare sky gradient therefore reads as
a toy however carefully it is modelled, because nothing in it is a place.

The road knows what sort of place it is in -- its structures say where the
bores and the bridges are, and everywhere else is the forest it was cut
through. This turns that into an environment the renderer lights and reflects
with, and changes it only when the road changes rather than every frame.

**The environments are drawn rather than photographed.** Each is a small
equirectangular panorama built from what the place is: a canopy overhead with
the sky broken through it, trunks around the horizon, road below; a bore is a
dark tube with a lit portal at either end; a viaduct is open sky over a
treeline a long way down. Small, because a reflection at speed is a suggestion
rather than a picture, and because :class:`~OpenGLContext.passes.ibl.IBLProbe`
convolves what it is given -- the sharpest thing it keeps is the shape of the
light, not its detail.

Where a captured panorama would be better -- the tunnel really being *this*
tunnel -- it drops into the same place: what the renderer is handed is an array,
and where it came from is this module's business alone.
"""
from __future__ import annotations

import functools
import math
from collections.abc import Callable
from typing import Any

import numpy as np
from OpenGLContext.passes import ibl

__all__ = ['CONTEXTS', 'FOREST', 'TUNNEL', 'VIADUCT', 'OPEN',
           'Reflections', 'context_at', 'panorama']

#: The sorts of place a road runs through, as far as what it reflects goes.
FOREST = 'forest'
TUNNEL = 'tunnel'
VIADUCT = 'viaduct'
OPEN = 'open'
CONTEXTS = (FOREST, TUNNEL, VIADUCT, OPEN)

#: What a structure of each kind means to look at. A causeway is a road on a
#: wall over low ground: open above, and nothing near enough to reflect.
BY_KIND = {'tunnel': TUNNEL, 'bridge': VIADUCT, 'causeway': OPEN}

#: How large a panorama is drawn, in pixels across. Held small on purpose: the
#: probe blurs everything but the broadest shape of the light, and a car at a
#: hundred and thirty reflects a suggestion rather than a picture.
WIDTH = 128
HEIGHT = WIDTH // 2

#: The seed the flecks and trunks are placed with, so a build of a panorama is
#: the same panorama every time and a car does not shimmer between frames.
SEED = 20260818




def context_at(course: Any, station: float) -> str:
    """Which sort of place the road is in, this far along it.

    A structure wins over the forest around it, and the first one that holds
    the station wins over any later one -- a bore inside a causeway is a bore.
    """
    for structure in getattr(course, 'structures', ()) or ():
        if bool(structure.holds(station)):
            return BY_KIND.get(structure.kind, OPEN)
    return FOREST


@functools.lru_cache(maxsize=len(CONTEXTS) * 4)
def panorama(context: str, width: int = WIDTH) -> np.ndarray:
    """The environment for one sort of place, as linear RGB.

    An ``(H, W, 3)`` equirectangular image: rows run from straight up to
    straight down, columns all the way round.

    Built once and kept. Bounded, because a cache with no ceiling is a leak
    waiting for a caller that asks for a size nobody thought of: there are four
    sorts of place, and room here for a few widths of each.
    """
    return _draw(context, width)


class Reflections:
    """The environment the car is lit and reflected by, kept up with the road.

    ``apply`` is what the environment is handed to -- by default the engine's
    IBL probe, which notices it changed and rebuilds. Rebuilding costs a few
    milliseconds, so it happens when the road changes and not otherwise: a lap
    crosses a handful of portals, not a thousand frames.
    """

    def __init__(self, course: Any, apply: Callable[[Any], Any] | None = None) -> None:
        self.course = course
        self.apply = apply if apply is not None else _register
        #: Where the car was last seen to be, or None before the first update.
        self.context: str | None = None

    def update(self, position: Any) -> str | None:
        """Say where the car is; returns the new context when it changed.

        Cheap enough for every frame: finding the nearest point of a course is
        one pass over its centreline, and nothing else happens unless the answer
        is different from last time.
        """
        if self.course is None:                  # pragma: no cover - no road
            return None
        index, _off = self.course.nearest(position)
        context = context_at(self.course, float(self.course.stations[index]))
        if context == self.context:
            return None
        self.context = context
        self.apply(panorama(context))
        return context


def _register(environment: np.ndarray) -> None:
    """Hand an environment to the renderer's probe."""
    ibl.set_equirect_env(environment)


def _draw(context: str, width: int) -> np.ndarray:
    """Draw one place: sky or roof above, surroundings around, road below."""
    height = max(width // 2, 2)
    rng = np.random.default_rng(SEED)
    # Elevation from +pi/2 at the top row to -pi/2 at the bottom, and azimuth
    # all the way round -- the equirectangular convention the probe projects.
    elevation = np.linspace(math.pi / 2, -math.pi / 2, height)[:, None]
    azimuth = np.linspace(0.0, 2.0 * math.pi, width, endpoint=False)[None, :]
    up = np.sin(elevation) + np.zeros_like(azimuth)
    image = np.zeros((height, width, 3), dtype='f')

    if context == TUNNEL:
        # A bore: dark rock all round, wet road beneath, and the two portals --
        # the way out ahead and the way in behind -- as the only light in it.
        image[:] = np.array([0.055, 0.050, 0.045], dtype='f')
        image += (0.05 * np.clip(-up, 0.0, 1.0))[:, :, None]      # road sheen
        for facing in (0.0, math.pi):
            towards = np.cos(azimuth - facing) * np.cos(elevation)
            portal = np.clip((towards - 0.955) / 0.045, 0.0, 1.0) ** 2
            image += portal[:, :, None] * np.array([0.75, 0.80, 0.92], dtype='f')
        return image

    sky = _sky(up)
    if context == FOREST:
        # A canopy: the sky is up there and mostly not visible through it, and
        # what is around the car at eye level is trunks.
        leaves = np.array([0.030, 0.055, 0.024], dtype='f')
        gaps = _flecks(rng, height, width, density=0.16, softness=1.6)
        cover = np.clip((up - 0.10) / 0.55, 0.0, 1.0)[:, :, None]
        canopy = leaves * (0.6 + 0.8 * gaps[:, :, None])
        image = sky * (1.0 - cover) + (canopy + sky * gaps[:, :, None] * 0.55) * cover
        image = _trunks(image, rng, elevation, azimuth, height, width)
        # A wall of wood at eye level. Without it the horizon is open sky all
        # the way round, and a car reflects that band along its flanks and
        # washes out to silver under trees -- which is the one thing a forest
        # environment must not do.
        wood = np.array([0.036, 0.052, 0.030], dtype='f')
        thicket = np.clip(1.0 - np.abs(up) / 0.40, 0.0, 1.0)[:, :, None] ** 0.5
        image = image * (1.0 - thicket * 0.93) + wood * thicket * 0.93
    elif context == VIADUCT:
        # Nothing near: open sky, and the forest far enough below and away to be
        # a band on the horizon.
        image = sky
        band = np.clip(1.0 - np.abs(up) / 0.16, 0.0, 1.0)[:, :, None]
        image = image * (1.0 - band) + np.array([0.045, 0.062, 0.040], 'f') * band
    else:
        image = sky
        image = _trunks(image, rng, elevation, azimuth, height, width, thin=0.35)

    ground = np.clip(-up / 0.35, 0.0, 1.0)[:, :, None]
    road = np.array([0.055, 0.055, 0.058], dtype='f')
    return (image * (1.0 - ground) + road * ground).astype('f')


def _sky(up: np.ndarray) -> np.ndarray:
    """A daylight gradient: brighter and bluer overhead, pale at the horizon."""
    high = np.clip(up, 0.0, 1.0)[:, :, None]
    zenith = np.array([0.20, 0.34, 0.72], dtype='f')
    horizon = np.array([0.62, 0.70, 0.82], dtype='f')
    return np.asarray(horizon + (zenith - horizon) * high ** 0.7, dtype='f')


def _flecks(rng: np.random.Generator, height: int, width: int,
            density: float, softness: float) -> np.ndarray:
    """Holes in a canopy: sky seen through leaves, in patches rather than dots."""
    coarse = rng.random((max(height // 4, 2), max(width // 4, 2))).astype('f')
    grown = np.repeat(np.repeat(coarse, 4, axis=0), 4, axis=1)[:height, :width]
    if grown.shape != (height, width):           # pragma: no cover - odd sizes
        grown = np.resize(grown, (height, width))
    return np.clip((grown - (1.0 - density)) * softness / max(density, 1e-3), 0.0, 1.0)


def _trunks(image: np.ndarray, rng: np.random.Generator, elevation: np.ndarray,
            azimuth: np.ndarray, height: int, width: int,
            thin: float = 1.0) -> np.ndarray:
    """Trees around the horizon: dark verticals where the eye finds the wood."""
    out = image.copy()
    bark = np.array([0.038, 0.030, 0.022], dtype='f')
    near = np.clip(1.0 - np.abs(np.sin(elevation)) / 0.30, 0.0, 1.0)
    for _ in range(int(round(26 * thin))):
        centre = float(rng.random()) * 2.0 * math.pi
        breadth = 0.02 + 0.05 * float(rng.random())
        gap = np.abs((azimuth - centre + math.pi) % (2.0 * math.pi) - math.pi)
        trunk = np.clip(1.0 - gap / breadth, 0.0, 1.0) * near
        out = out * (1.0 - trunk[:, :, None]) + bark * trunk[:, :, None]
    return np.asarray(out, dtype='f')
