"""The seams the game is built along, written down as types.

Almost everything here is handed something it does not own: a driver is handed a
session, a camera is handed a car, the steering aid is handed a course. Written
as ``Any`` those seams are invisible -- the checker verifies nothing about them,
and a reader has to find a caller to learn what a parameter must have.

These are :class:`~typing.Protocol` s, so nothing has to inherit from them and a
test double satisfies one by having the right methods. That is the point: the
suite drives most of the game through doubles, and a seam that only the real
class could pass would be a seam that could not be tested.

Each says the *least* that its users need, which is what makes it useful to
write a double against. :class:`CarLike` does not mention the physics body, and
:class:`CourseLike` does not mention the tileset it came out of, because nothing
that takes one asks.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np

__all__ = ['CarLike', 'CourseLike', 'PhysicsLike', 'SessionLike',
           'VehicleLike']


@runtime_checkable
class VehicleLike(Protocol):
    """The simulated vehicle under a car, as the game reads one."""

    @property
    def wheels(self) -> Any:
        """The wheels, each with its own spec and current state."""
        ...                                      # pragma: no cover - a protocol

    @property
    def tuning(self) -> Any:
        """The numbers that give this vehicle its handling."""
        ...                                      # pragma: no cover - a protocol

    #: What the wheels are on. Written to as well as read, so it is an
    #: attribute rather than a property: the surface is the one thing about a
    #: vehicle that something outside it decides.
    surface: Any

    def forward_speed(self) -> float:
        """How fast it is going along its own nose, signed."""
        ...                                      # pragma: no cover - a protocol

    def wheelbase(self) -> float:
        ...                                      # pragma: no cover - a protocol

    def turning_radius(self, speed: float = 0.0) -> float:
        """The tightest circle it will hold at that speed, in metres."""
        ...                                      # pragma: no cover - a protocol


@runtime_checkable
class CarLike(Protocol):
    """A car, as everything that watches or drives one sees it.

    What the camera follows, what a driver decides about, and what the lap
    timing is told the position of. Physics and scenegraph are the car's own
    business and are not here.
    """

    @property
    def vehicle(self) -> VehicleLike:
        """What is simulated under it."""
        ...                                      # pragma: no cover - a protocol

    @property
    def position(self) -> np.ndarray:
        """Where it is, in world metres."""
        ...                                      # pragma: no cover - a protocol

    def speed(self) -> float:
        """How fast it is going, in metres per second, unsigned."""
        ...                                      # pragma: no cover - a protocol

    def forward(self) -> np.ndarray:
        """Which way it is pointing, as a unit vector."""
        ...                                      # pragma: no cover - a protocol

    def forward_speed(self) -> float:
        """How fast it is going along its own nose, signed."""
        ...                                      # pragma: no cover - a protocol


@runtime_checkable
class CourseLike(Protocol):
    """A road, as everything that follows one reads it.

    :class:`~glisteel.world.Course` is the one the game uses; a scenario builds
    the same thing from a plan. What matters at this seam is that a course can
    say where its line goes, how far along it a point is, and how tight the
    bends are.
    """

    @property
    def name(self) -> str:
        ...                                      # pragma: no cover - a protocol

    @property
    def centreline(self) -> np.ndarray:
        ...                                      # pragma: no cover - a protocol

    @property
    def carriageway_width(self) -> float:
        ...                                      # pragma: no cover - a protocol

    @property
    def total_width(self) -> float:
        ...                                      # pragma: no cover - a protocol

    @property
    def lanes(self) -> int:
        """How many lanes are marked across the carriageway."""
        ...                                      # pragma: no cover - a protocol

    @property
    def closed(self) -> bool:
        ...                                      # pragma: no cover - a protocol

    @property
    def length(self) -> float:
        ...                                      # pragma: no cover - a protocol

    @property
    def stations(self) -> np.ndarray:
        """Distance along the road to each centreline point."""
        ...                                      # pragma: no cover - a protocol

    @property
    def radii(self) -> np.ndarray:
        """The radius of the bend at each point, in metres."""
        ...                                      # pragma: no cover - a protocol

    def point(self, index: int) -> np.ndarray:
        ...                                      # pragma: no cover - a protocol

    def nearest(self, position: Any) -> tuple[int, float]:
        """The nearest point's index, and how far off the road it is."""
        ...                                      # pragma: no cover - a protocol

    def across(self, index: int) -> np.ndarray:
        ...                                      # pragma: no cover - a protocol

    def lane_point(self, index: int, offset: float = 0.0) -> np.ndarray:
        ...                                      # pragma: no cover - a protocol


@runtime_checkable
class PhysicsLike(Protocol):
    """The physics world a car is built into.

    ``omi_physics``' own, named here so that what the car needs from it is
    written down rather than discovered.
    """

    @property
    def position(self) -> Any:
        ...                                      # pragma: no cover - a protocol

    @property
    def orientation(self) -> Any:
        ...                                      # pragma: no cover - a protocol

    @property
    def linear_velocity(self) -> Any:
        ...                                      # pragma: no cover - a protocol

    def add_shape(self, shape: Any) -> Any:
        ...                                      # pragma: no cover - a protocol

    def add_body(self, motion: Any, collider: Any = None,
                 position: Any = None) -> Any:
        ...                                      # pragma: no cover - a protocol

    def place_body(self, i: int, position: Any = None,
                   orientation: Any = None) -> Any:
        ...                                      # pragma: no cover - a protocol

    def impact_on(self, i: int, above: float = 0.0, skip_static: bool = False,
                  among: Any = None) -> tuple[int, float] | None:
        """What struck body ``i`` in the last step, and how fast it closed."""
        ...                                      # pragma: no cover - a protocol

    def step(self, dt: float) -> Any:
        ...                                      # pragma: no cover - a protocol


@runtime_checkable
class SessionLike(Protocol):
    """A run, as whoever is driving it sees it.

    What a :class:`~glisteel.session.Controller` is handed. Deliberately small:
    a driver looks at the car, the road it is on, and what is in front of it,
    and everything else about a session is the session's own.
    """

    @property
    def car(self) -> CarLike:
        ...                                      # pragma: no cover - a protocol

    @property
    def course(self) -> CourseLike:
        ...                                      # pragma: no cover - a protocol

    def traffic_ahead(self, reach: float = ...
                      ) -> tuple[float, float] | None:
        """What is in front in this lane: how far, and how fast."""
        ...                                      # pragma: no cover - a protocol

    def oncoming(self, reach: float = ...) -> tuple[float, float] | None:
        """What is coming the other way: how far off, and how fast it closes."""
        ...                                      # pragma: no cover - a protocol

    def lane_ahead(self, across: float, reach: float = ...
                   ) -> tuple[float, float] | None:
        """What is up the lane at that offset: how far, and how fast."""
        ...                                      # pragma: no cover - a protocol

    def lane_clear(self, across: float, ahead: float = ...,
                   behind: float = ...) -> bool:
        """Whether the lane at that offset is clear to move into."""
        ...                                      # pragma: no cover - a protocol

    def car_ahead(self, reach: float = ...) -> Any:
        """The nearest car in front in this lane, or None."""
        ...                                      # pragma: no cover - a protocol

    @property
    def two_way(self) -> bool:
        """Whether anything on this road comes the other way."""
        ...                                      # pragma: no cover - a protocol

    def sight(self, over: float = ...) -> float:
        """How far down the road the car can see, in metres."""
        ...                                      # pragma: no cover - a protocol

    def along(self, other: Any) -> float:
        """How far up the road something is from the car, in metres."""
        ...                                      # pragma: no cover - a protocol
