"""What the game's window is: GLFW, and no navigation beside the chase camera."""
from OpenGLContext.context import Context
from OpenGLContext.ui.overlay import OverlayStackMixin

from glisteel.game import GlisteelContext


def test_it_is_a_context_with_the_overlay():
    assert issubclass(GlisteelContext, Context)
    assert issubclass(GlisteelContext, OverlayStackMixin)


def test_it_opens_a_glfw_window():
    assert GlisteelContext.windowSystemName == 'glfw'


def test_the_chase_camera_is_all_that_moves_the_view():
    """The arrow keys steer the car; nothing else is bound to them to move
    a camera the chase camera puts back each frame."""
    assert not GlisteelContext.resolveDefinition(size=(320, 180)).navigation
