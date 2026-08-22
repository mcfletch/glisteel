"""The road as somewhere to be, rather than as a line to be on.

A driver does not follow a line. A road is a *width* with lanes marked across
it, and where a car sits in that width is a decision the driver makes and remakes
-- their own lane, the middle of it, out towards the crown to see past what is in
front, over to the other side to pass, back again. Anything that steers a car by
where it *is* across the road rather than by how far its wheels are turned
(:mod:`glisteel.schemes`) needs that width written down: how far out it may go,
where the lanes are, and which of them have something coming the other way.

    >>> zone = DrivableZone(width=14.4, lanes=4)
    >>> [round(one, 2) for one in zone.centres()]
    [-5.4, -1.8, 1.8, 5.4]
    >>> zone.own_lanes()
    (2, 3)
    >>> round(zone.step(-1.8, 1), 2)
    1.8

**Offsets are metres to the road's own right**, which is the frame the whole
game measures across a road in -- :meth:`glisteel.world.Course.across`, the
grid, the traffic and the line the steering aid holds. Right-hand traffic, so a
driver's own lanes are the right-hand ones and the crown is the line they cross
to pass.

A zone is a value: it is worked out from a course once and describes a road that
does not change shape while it is being driven.
"""
from __future__ import annotations

from dataclasses import dataclass

from glisteel.interfaces import CourseLike

__all__ = ['DrivableZone', 'LANES', 'MARGIN']

#: How far inside the carriageway's own edge a car may be asked to sit, in
#: metres. About half a car: a line the far side of this is a line with two
#: wheels on the grass, and nothing that places a car across a road means to ask
#: for that. The rest of the road is the driver's to use.
MARGIN = 1.0

#: How a road is divided when it does not say: one lane each way, which is what
#: a road with a crown and something coming the other way is.
LANES = 2


@dataclass(frozen=True)
class DrivableZone:
    """How wide a road is, how it is divided, and which way its lanes go.

    ``width`` is the carriageway, edge to edge, and ``lanes`` how many lanes are
    marked across it. ``margin`` is how far inside the edge a car may be placed,
    and ``two_way`` says whether the lanes left of the crown carry traffic the
    other way -- which is what makes a pass on a two-lane road a different
    decision from a pass on a dual carriageway.
    """

    width: float
    lanes: int = LANES
    margin: float = MARGIN
    two_way: bool = True

    @classmethod
    def of(cls, course: CourseLike, margin: float = MARGIN,
           two_way: bool | None = None) -> DrivableZone:
        """The zone a course's carriageway offers.

        Two-way unless the course says otherwise: a closed course is a circuit
        and a circuit is lapped one way round, so every lane of it is a lane to
        drive in. A course that does not say how it is divided gets
        :data:`LANES`, on the same footing: what a road cannot answer about
        itself is the road an unmarked one is.
        """
        if two_way is None:
            two_way = not bool(getattr(course, 'closed', False))
        return cls(width=float(course.carriageway_width),
                   lanes=int(getattr(course, 'lanes', LANES) or LANES),
                   margin=margin, two_way=bool(two_way))

    @property
    def lane_width(self) -> float:
        """How wide one lane is, in metres."""
        return float(self.width) / max(int(self.lanes), 1)

    @property
    def edge(self) -> float:
        """How far either side of the crown a car may be placed, in metres.

        Never negative: a road narrower than two margins is a road whose only
        line is its own crown, and answering with a negative half-width would
        make :meth:`clamp` put the car on the wrong side of where it was asked
        for.
        """
        return max(float(self.width) / 2.0 - float(self.margin), 0.0)

    def clamp(self, offset: float) -> float:
        """That offset, brought onto the road if it is not already on it."""
        return max(-self.edge, min(self.edge, float(offset)))

    def centres(self) -> tuple[float, ...]:
        """The middle of each lane, in metres right of the crown, left to right.

        Brought onto the road like any other line, so a road too narrow for the
        lanes it declares still answers with lines a car can be driven on.
        """
        count = max(int(self.lanes), 1)
        half = self.lane_width / 2.0
        return tuple(self.clamp(-float(self.width) / 2.0 + half
                                + index * self.lane_width)
                     for index in range(count))

    def centre_of(self, index: int) -> float:
        """The middle of one lane. Lanes beyond the road are its outside ones."""
        found = self.centres()
        return found[max(0, min(len(found) - 1, int(index)))]

    def lane_at(self, offset: float) -> int:
        """Which lane a car sitting at that offset is in.

        The nearest one, so a car placed between two lanes -- which is where a
        car halfway through changing lanes is -- is in the one it is closest to
        rather than in none.
        """
        found = self.centres()
        gaps = [abs(centre - float(offset)) for centre in found]
        return int(gaps.index(min(gaps)))

    def step(self, offset: float, direction: int) -> float:
        """The middle of the next lane over from where a car is.

        ``direction`` is 1 for the road's right and -1 for its left. Counted
        from the lane the car is *in* rather than from wherever the last step
        was asked for, so a driver who has drifted asks for the lane beside
        them. The road running out is an answer, not an error: the step stops
        at the outside lane.
        """
        return self.centre_of(self.lane_at(offset) + int(direction))

    def oncoming(self, index: int) -> bool:
        """Whether that lane carries traffic the other way.

        The lanes left of the crown, on a two-way road. A lane that straddles
        the crown -- the middle one of an odd number -- is not counted as
        oncoming: what runs down the middle of a road is a decision the road
        makes, and a zone that has not been told cannot make it.
        """
        return bool(self.two_way and self.centre_of(index) < 0.0)

    def own_lanes(self) -> tuple[int, ...]:
        """The lanes a driver may use without meeting anybody."""
        return tuple(index for index in range(len(self.centres()))
                     if not self.oncoming(index))
