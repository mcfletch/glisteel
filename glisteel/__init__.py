"""GLinting Steel: a racing game on OpenGLContext.

A car, a circuit, and a world too big to load: the track streams in around the
player as they drive it, and every tile it pages in becomes collision the car
drives on.

    glisteel-bake --output /tmp/world    # bake a world (glisteel-editor)
    glisteel /tmp/world/tileset.json     # drive it

The game is deliberately thin. Streaming, rendering, roads and physics all
belong to the engine underneath -- ``OpenGLContext`` and ``omi_physics`` -- and
what is here is what makes it a *game*: the car's shape and handling, where the
camera watches from, the lap timing, and the HUD.

``world``    a baked world: its tiles, its physics, and the roads it carries
``car``      the car -- its body, its wheels, and how it is drawn
``camera``   where the player watches from
``race``     lap timing that a shortcut does not fool
``hud``      the four numbers a driver acts on
``game``     the window, the loop, and the keys
"""

__version__ = "0.1.0a1"
__author__ = "Michael Colin Fletcher"
__license__ = "BSD-Style, see license.txt for details"
