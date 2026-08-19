"""The keys that drive the car, from the names the window actually sends.

The steering felt dead because the arrows were bound under bare names --
``left``, ``right`` -- while the backend delivers them as ``<left>`` and
``<right>``.  Nothing here needs a window: the key handler only touches the set
of held keys, and reading the pedals off it is plain arithmetic.
"""
import pytest

from glisteel.game import GlisteelContext
from glisteel.steering import KeyboardWheel

STEP = 1.0 / 120.0


class _Event:
    def __init__(self, name: str, state: int) -> None:
        self.name = name
        self.state = state


def _context() -> GlisteelContext:
    """A context with just enough of itself to route a keypress to a pedal."""
    context = GlisteelContext.__new__(GlisteelContext)
    context.held = set()
    context.wheel = None
    context.keys = KeyboardWheel()
    context.car = None
    context.triggerRedraw = lambda *args, **named: None
    return context


def _press(context: GlisteelContext, name: str) -> None:
    context._on_key(_Event(name, 1))


def _release(context: GlisteelContext, name: str) -> None:
    context._on_key(_Event(name, 0))


def _steer_for(context: GlisteelContext, seconds: float) -> float:
    """Sample the controls for ``seconds`` and return the steering it settles at."""
    steer = 0.0
    for _ in range(int(round(seconds / STEP))):
        steer = context.driver_input(STEP)[2]
    return steer


class TestTheKeysThatDriveIt:
    def test_the_left_arrow_winds_on_to_full_left(self) -> None:
        context = _context()
        _press(context, '<left>')
        assert _steer_for(context, 1.5) == pytest.approx(1.0)

    def test_the_right_arrow_winds_on_to_full_right(self) -> None:
        context = _context()
        _press(context, '<right>')
        assert _steer_for(context, 1.5) == pytest.approx(-1.0)

    def test_a_tap_is_only_a_nudge(self) -> None:
        """A brief press must not fling the car to full lock."""
        context = _context()
        _press(context, '<left>')
        assert 0.0 < _steer_for(context, 0.05) < 0.2

    def test_releasing_the_wheel_returns_it_to_centre(self) -> None:
        context = _context()
        _press(context, '<right>')
        _steer_for(context, 1.5)
        _release(context, '<right>')
        assert _steer_for(context, 1.5) == pytest.approx(0.0)

    def test_the_up_arrow_is_the_throttle(self) -> None:
        context = _context()
        _press(context, '<up>')
        assert context.driver_input(STEP)[0] == pytest.approx(1.0)

    def test_a_and_d_still_steer(self) -> None:
        """The arrows and WASD are the same control, so both have to work."""
        context = _context()
        _press(context, 'a')
        assert _steer_for(context, 1.5) == pytest.approx(1.0)
        _release(context, 'a')
        _press(context, 'd')
        assert _steer_for(context, 3.0) == pytest.approx(-1.0)

    def test_w_is_the_throttle(self) -> None:
        context = _context()
        _press(context, 'w')
        assert context.driver_input(STEP)[0] == pytest.approx(1.0)
