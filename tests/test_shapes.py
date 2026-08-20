"""One idea, one spelling.

Several of these are the same thought written out more than once: which way a
thing is pointing, what a frame's read-outs are, what a recorded drive holds.
Each copy is a place the next change has to be made and a place it can be
forgotten, and where the copies had drifted apart -- two sign conventions for
one angle -- a reader had no way to tell which was meant.
"""
import dataclasses

import numpy as np
import pytest

from glisteel.geometry import yaw_of, yaw_to_face
from glisteel.session import Readings
from glisteel.trace import Trace


class TestWhichWayAThingIsPointing:
    """Two conventions, because there are two questions.

    :func:`yaw_of` reads an angle *off* a direction, the way a view platform
    wants one. :func:`yaw_to_face` gives the rotation that *turns* a mesh to
    point that way, and a mesh's nose is down -Z. They are each other's
    negation, which is exactly why having four unnamed copies between them was
    a trap.
    """

    def test_reading_an_angle_off_a_direction(self) -> None:
        assert yaw_of((0.0, 0.0, -1.0)) == pytest.approx(0.0)
        assert yaw_of((1.0, 0.0, 0.0)) == pytest.approx(np.pi / 2)

    def test_turning_a_mesh_to_face_one(self) -> None:
        assert yaw_to_face((0.0, 0.0, -1.0)) == pytest.approx(0.0)
        assert yaw_to_face((-1.0, 0.0, 0.0)) == pytest.approx(np.pi / 2)

    def test_the_two_are_each_others_negation(self) -> None:
        for direction in [(1.0, 0.0, 0.0), (0.3, 0.0, -0.9), (-0.5, 2.0, 0.5)]:
            assert yaw_of(direction) == pytest.approx(-yaw_to_face(direction))

    def test_the_vertical_does_not_come_into_it(self) -> None:
        """A crest ahead is not a reason to turn."""
        assert yaw_of((1.0, 5.0, 0.0)) == pytest.approx(yaw_of((1.0, 0.0, 0.0)))

    def test_a_mesh_turned_that_far_points_where_it_was_asked(self) -> None:
        for direction in [(1.0, 0.0, 0.0), (0.3, 0.0, -0.9), (-0.7, 0.0, 0.7)]:
            angle = yaw_to_face(direction)
            # A yaw of t sends the nose, down -Z, to (-sin t, 0, -cos t).
            pointed = np.array([-np.sin(angle), 0.0, -np.cos(angle)])
            wanted = np.array([direction[0], 0.0, direction[2]])
            wanted = wanted / np.linalg.norm(wanted)
            assert np.allclose(pointed, wanted, atol=1e-9)


class TestEveryoneUsesTheOneSpelling:
    def test_the_camera_does(self) -> None:
        from glisteel.camera import CameraPose
        pose = CameraPose(position=np.zeros(3),
                          target=np.array([1.0, 0.0, 0.0]))
        assert pose.heading() == pytest.approx(yaw_of((1.0, 0.0, 0.0)))

    def test_the_road_does(self) -> None:
        from glisteel.world import Course
        line = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        course = Course(name='c', centreline=line, carriageway_width=7.0,
                        total_width=12.0, closed=False, length=1.0)
        assert course.heading_at(0) == pytest.approx(
            yaw_to_face((1.0, 0.0, 0.0)))

    def test_a_traffic_car_does(self) -> None:
        from glisteel.traffic import TrafficCar
        from glisteel.world import Course
        line = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]])
        course = Course(name='c', centreline=line, carriageway_width=7.0,
                        total_width=12.0, closed=False, length=100.0)
        car = TrafficCar(course, station=10.0, heading=1, limit=20.0)
        assert car.heading_angle() == pytest.approx(yaw_to_face(car.forward()))


class TestARecordedDriveKnowsItsOwnColumns:
    """Adding one must not mean editing three lists that have to agree."""

    def _trace(self, rows=5):
        empty = np.arange(float(rows))
        return Trace(t=empty.copy(), position=np.zeros((rows, 3)),
                     speed=empty.copy(), yaw=empty.copy(),
                     throttle=empty.copy(), brake=empty.copy(),
                     steer=empty.copy(), wheel_angle=empty.copy(),
                     camera=np.zeros((rows, 3)), camera_yaw=empty.copy(),
                     camera_pitch=empty.copy(), off_line=empty.copy(),
                     on_road=np.zeros(rows, dtype=bool),
                     ended=np.zeros(rows, dtype=object))

    def test_a_window_of_it_carries_every_column(self) -> None:
        window = self._trace(rows=10).between(2.0, 5.0)
        for field in dataclasses.fields(Trace):
            if field.name in ('step', 'laps'):
                continue
            assert len(getattr(window, field.name)) == 4, field.name

    def test_the_window_is_the_part_that_was_asked_for(self) -> None:
        window = self._trace(rows=10).between(2.0, 5.0)
        assert list(window.t) == [2.0, 3.0, 4.0, 5.0]

    def test_it_keeps_the_step_and_the_laps(self) -> None:
        whole = self._trace()
        whole.laps.append('a lap')
        window = whole.between(0.0, 2.0)
        assert window.step == whole.step
        assert window.laps == ['a lap']

    def test_an_empty_window_is_still_a_trace(self) -> None:
        window = self._trace().between(99.0, 100.0)
        assert len(window) == 0
        assert window.measures()['top_speed'] == 0.0


class TestTheReadoutsAreOneThing:
    def test_the_hud_takes_a_frames_readings(self) -> None:
        from glisteel.hud import RaceHUD
        hud = RaceHUD()
        hud.show(Readings(speed_kph=88.0, off=True))
        assert hud.speed.value.strip() == '88'
        assert hud.warning.value == 'OFF TRACK'

    def test_what_it_is_told_is_what_a_session_answers(self) -> None:
        """Neither side may grow a field the other does not know about."""
        import inspect

        from glisteel.hud import RaceHUD
        wanted = inspect.signature(RaceHUD.show).parameters
        assert list(wanted) == ['self', 'reading']
