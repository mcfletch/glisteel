"""Which events the window asks for, and which it does not.

A binding that is never made is a control that does nothing, and there is no way
to notice from inside the window: nothing raises, the key or the pointer simply
has no effect. So the table of what to bind is worked out here, where a test can
read it, and the window's job is to hand each entry to the runtime.
"""
from glisteel.game import bindings
from glisteel.steering import CONTROLS


def _kinds(found):
    return {one.kind for one in found}


def _named(found, kind, name=None):
    return [one for one in found
            if one.kind == kind and (name is None or one.name == name)]


class TestTheDrivingControls:
    def test_every_control_key_is_asked_for(self) -> None:
        wanted = {name for keys in CONTROLS.values() for name in keys}
        assert wanted <= {one.name for one in _named(bindings(), 'keyboard')}

    def test_each_is_asked_for_going_down_and_coming_up(self) -> None:
        # A key whose release nobody saw is a key held down for ever.
        for name in CONTROLS['throttle']:
            states = {one.state for one in _named(bindings(), 'keyboard', name)}
            assert states == {0, 1}


class TestSteeringWithThePointer:
    """``--mouse`` is a documented control, so the pointer has to be asked for.

    It was bound behind a test on whoever is driving, and whoever is driving is
    not chosen until a world is opened -- which happens after the bindings are
    made. The answer is not to test earlier but not to test at all: the handler
    guards itself, and a pointer event with no wheel to turn is ignored.
    """

    def test_the_pointer_is_asked_for(self) -> None:
        assert _named(bindings(), 'mousemove')

    def test_it_is_asked_for_whether_or_not_anyone_is_driving_yet(self) -> None:
        # The bindings are made once, before a world is open. Nothing about them
        # may depend on state that does not exist yet.
        assert bindings() == bindings()


class TestTheRest:
    def test_the_camera_the_reset_and_the_restart_are_bound(self) -> None:
        pressed = {one.name for one in _named(bindings(), 'keypress')}
        assert {'c', 'r', 'n'} <= pressed

    def test_escape_brings_up_the_menu(self) -> None:
        assert _named(bindings(), 'keyboard', '<escape>')

    def test_every_binding_names_a_handler_the_window_has(self) -> None:
        from glisteel.game import GlisteelContext
        for one in bindings():
            assert hasattr(GlisteelContext, one.handler), one.handler
