"""Pieces of road, and a way to count what a frame asks for.

Two things most of these tests need and none of them is about. A **course** to
put a car on -- a ring or a straight, written down the way a baked world writes
one -- and, for the tests that assert what a frame *costs*, a way to count the
calls something makes without each of them growing its own wrapper and its own
``try``/``finally``.

Everything a test cares about stays at the call site: the width of the road, how
long it is and whether it closes are arguments there, because they are what the
test is about. What lives here is the arithmetic that is the same every time.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import numpy as np


def ring(points: int = 400, radius: float = 200.0,
         radius_z: float | None = None, height: float = 0.0,
         endpoint: bool = False) -> np.ndarray:
    """The centreline of a circle, or of an ellipse, in the ground plane.

    ``points`` of it, of radius ``radius`` across and ``radius_z`` along (the
    same, for a circle), at ``height`` above the ground. ``endpoint`` repeats
    the first point at the end, which is what a road written down as an open
    line that happens to meet itself looks like.

        >>> line = ring(points=4, radius=10.0)
        >>> line.shape
        (4, 3)
        >>> [round(float(v), 3) for v in line[0]]
        [10.0, 0.0, 0.0]
        >>> [round(float(v), 3) for v in line[1]]
        [0.0, 0.0, 10.0]
    """
    angle = np.linspace(0.0, 2.0 * np.pi, points, endpoint=endpoint)
    return np.stack([np.cos(angle) * radius,
                     np.full(points, height),
                     np.sin(angle) * (radius if radius_z is None else radius_z)],
                    axis=-1)


def straight(length: float = 1000.0, count: int = 101) -> np.ndarray:
    """The centreline of a level road running away along +Z.

        >>> straight(length=100.0, count=3).tolist()
        [[0.0, 0.0, 0.0], [0.0, 0.0, 50.0], [0.0, 0.0, 100.0]]
    """
    z = np.linspace(0.0, length, count)
    return np.stack([np.zeros(count), np.zeros(count), z], axis=-1)


def perimeter(line: np.ndarray, closed: bool = True) -> float:
    """How long a centreline is, measured along it.

    The distance a car covers going round, so a closed line counts the step
    from its last point back to its first.

        >>> round(perimeter(ring(points=4, radius=10.0)), 3)
        56.569
        >>> round(perimeter(straight(length=100.0, count=3), closed=False), 3)
        100.0
    """
    if closed:
        line = np.concatenate([line, line[:1]])
    return float(np.linalg.norm(np.diff(line, axis=0), axis=1).sum())


@contextlib.contextmanager
def counting(owner: Any, name: str) -> Iterator[list]:
    """Count what is asked of ``owner.name`` while the block runs.

    Yields a list that grows by one entry -- the arguments of the call -- every
    time the attribute is called, and puts the real one back afterwards however
    the block ends. ``owner`` is whatever holds the callable: a class, so that
    every instance is counted, or a module.

        >>> import math
        >>> with counting(math, 'sqrt') as asked:
        ...     math.sqrt(4.0), math.sqrt(9.0)
        ...     len(asked)
        (2.0, 3.0)
        2
        >>> math.sqrt(16.0)                    # the real one is back
        4.0

    What is being asserted with it is nearly always *how many times*, so the
    entries are there for a failure message rather than for the assertion::

        assert len(asked) == 1, 'asked %d times in one frame' % len(asked)
    """
    calls: list = []
    real = getattr(owner, name)

    def counted(*args: Any, **named: Any) -> Any:
        calls.append((args, named))
        return real(*args, **named)

    setattr(owner, name, counted)
    try:
        yield calls
    finally:
        setattr(owner, name, real)
