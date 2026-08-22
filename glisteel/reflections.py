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
           'Reflections', 'context_at', 'panorama', 'mix_at', 'blended',
           'TRANSITION']

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

#: How far a change of surroundings is spread over, in metres.
#:
#: A portal is a line on the ground and the light does not change on it: coming
#: out from under a canopy the daylight arrives over the length of the
#: approach, and going in the shade closes over the car. Exchanged at the line
#: instead, the whole picture changes brightness in one frame -- this
#: environment lights the scene and not only the car, and a forest and a
#: viaduct differ by more than three times in how much light they carry.
TRANSITION = 90.0

#: How many places along that stretch are asked about.
#:
#: Enough that a structure shorter than the transition is still noticed as the
#: car goes through it. It does not have to be many: what the blend is smooth
#: *in* is the distance along the road, which moves continuously, so the
#: samples decide what is noticed rather than how gradually it arrives.
SAMPLES = 9

#: How much the light has to change before the probe is rebuilt, as a fraction
#: of what it was.
#:
#: The blend is spread over the *road* rather than over the frames: a rebuild
#: costs a few milliseconds, so a portal is worth a handful of them and not one
#: per frame for as long as the crossing lasts. Measured on the light rather
#: than on the mixture because that is what is being kept smooth -- an equal
#: step of mixture is a small change between two dark places and a large one
#: leaving a dark place for a bright one.
STEP = 0.10




def context_at(course: Any, station: float) -> str:
    """Which sort of place the road is in, this far along it.

    A structure wins over the forest around it, and the first one that holds
    the station wins over any later one -- a bore inside a causeway is a bore.
    """
    for structure in getattr(course, 'structures', ()) or ():
        if bool(structure.holds(station)):
            return BY_KIND.get(structure.kind, OPEN)
    return FOREST


def mix_at(course: Any, station: float, span: float = TRANSITION,
           samples: int = SAMPLES) -> dict[str, float]:
    """What sort of place the road is in *around* here, and in what proportion.

    The places within ``span`` metres, weighted by how near they are: a car in
    the middle of a bore is entirely in a bore, one at the mouth is half in it,
    and one a transition away has left it. What turns a line on the ground into
    a stretch of road over which the light arrives.
    """
    offsets = np.linspace(-span / 2.0, span / 2.0, max(int(samples), 1))
    near = 1.0 - np.abs(offsets) / max(span / 2.0, 1e-6)
    found: dict[str, float] = {}
    length = float(getattr(course, 'length', 0.0) or 0.0)
    closed = bool(getattr(course, 'closed', False))
    for offset, weight in zip(offsets, near, strict=True):
        at = float(station) + float(offset)
        if closed and length > 0.0:
            at %= length
        found[context_at(course, at)] = (found.get(context_at(course, at), 0.0)
                                         + float(weight))
    total = sum(found.values()) or 1.0
    return {context: share / total for context, share in found.items()}


@functools.lru_cache(maxsize=len(CONTEXTS) * 4)
def _brightness(context: str, width: int = WIDTH) -> float:
    """How much light one place carries, as the mean of its panorama."""
    return float(panorama(context, width).mean())


def _level(mix: dict[str, float]) -> float:
    """How much light a mixture of places carries.

    The mean of what :func:`blended` would build, without building it: the
    mean of a sum is the sum of the means, and this is asked every frame while
    the image is wanted only when it has moved.
    """
    return sum(_brightness(context) * float(share)
               for context, share in mix.items())


def blended(mix: dict[str, float], width: int = WIDTH) -> np.ndarray:
    """One environment from a mixture of places, in the same proportions."""
    found = None
    for context, share in mix.items():
        one = panorama(context, width) * float(share)
        found = one if found is None else found + one
    return found if found is not None else panorama(FOREST, width)


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
        #: Which place the car is most in, or None before the first update.
        self.context: str | None = None
        self._mix: dict[str, float] = {}

    def update(self, position: Any) -> str | None:
        """Say where the car is; returns the place it is most in when that
        changed.

        Cheap enough for every frame: finding the nearest point of a course is
        one pass over its centreline, and nothing else happens unless the
        mixture of places around the car has moved by :data:`STEP`.
        """
        if self.course is None:                  # pragma: no cover - no road
            return None
        mix = mix_at(self.course, self.course.station_of(position))
        # Far enough, or arrived: a blend whose last few per cent are under the
        # step is a bore lit like most of a bore for as long as it lasts, so
        # settling on one place is worth a rebuild of its own.
        if self._moved(mix) < STEP and not (len(mix) == 1 and mix != self._mix):
            return None
        self._mix = mix
        self.apply(blended(mix))
        context = max(mix, key=lambda one: mix[one])
        if context == self.context:
            return None
        self.context = context
        return context

    def _moved(self, mix: dict[str, float]) -> float:
        """How far the light is from what the probe was last built for.

        As a fraction of the dimmer of the two, so a change is judged against
        what the eye is adapted to rather than against the brightest thing on
        the road.
        """
        if not self._mix:
            return 1.0
        was, now = _level(self._mix), _level(mix)
        return abs(now - was) / max(min(was, now), 1e-6)


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
