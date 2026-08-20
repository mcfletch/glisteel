"""Which way a thing is pointing, said once.

There are two questions here and they are each other's negation, which is
exactly why writing them out where they are needed goes wrong: four copies
appeared in this package, in two conventions, and no two of the docstrings said
which was which.

**Reading an angle off a direction** is :func:`yaw_of`. A view platform wants
one of these, and so does anything measuring how fast a frame is turning.

**Turning something to point that way** is :func:`yaw_to_face`. A mesh's nose
points down -Z, so a yaw of ``t`` sends it to ``(-sin t, 0, -cos t)`` -- and the
angle that achieves a wanted direction is therefore read off the *negated* one.
Taken from the direction itself instead, a car ends up square across the road,
which is what any road not lying along an axis finds.

Both work in the ground plane: a crest ahead is not a reason to turn.
"""
from __future__ import annotations

import math
from typing import Any

__all__ = ['yaw_of', 'yaw_to_face']


def yaw_of(direction: Any) -> float:
    """The angle a direction makes, in radians, measured from -Z about the
    vertical.

    What a view platform is set to, and what a turning rate is differenced from.
    """
    return math.atan2(float(direction[0]), -float(direction[2]))


def yaw_to_face(direction: Any) -> float:
    """The rotation about the vertical that points a mesh's nose that way.

    The negation of :func:`yaw_of`, because a mesh's nose is down -Z and a
    positive yaw swings it towards -X.
    """
    return math.atan2(-float(direction[0]), -float(direction[2]))
