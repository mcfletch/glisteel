"""Which model is which, and the names a game drives one by.

The art this game draws is a table of filenames, and everything else about
loading one belongs to the engine: :class:`~OpenGLContext.loaders.assets.AssetLibrary`
finds a model under :data:`ART`, hands back a copy to draw or a copy to repaint,
and returns nothing rather than raising when a file will not load. What is here
is the table, and the names inside a file that the game reaches for.

**The names are the interface between the art and the game.** A vehicle model
carries its bodywork, its interior and its glass as named subtrees -- and the
player's car its bonnet as a fourth, because that is the one thing on the
outside a driver still sees from inside -- with its seats, its pillars and its
steering column inside the interior, and its paint, trim and glass as three
named materials. Re-exporting a model, restyling it or replacing it
outright changes nothing here as long as those names come with it; what each one
has to be is asserted in ``tests/test_models.py``.

Every model is built by ``tools/cars.py`` and the shapes are described in
``plans/CAR-MODELS.md``.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

from OpenGLContext.loaders.assets import AssetLibrary

__all__ = ['ART', 'BONNET', 'HERO', 'HERO_WHEEL_FRONT', 'HERO_WHEEL_REAR',
           'PILLARS', 'STEER_CLIP', 'TRAFFIC', 'VEHICLE_MATERIALS', 'TrafficKind']

#: The art that ships with the game.
#:
#: Found through the package rather than through ``__file__``: that is what
#: :mod:`importlib.resources` is for, and it is the spelling that keeps working
#: when the package is not a directory of files on a disk.
ART = AssetLibrary(str(resources.files('glisteel') / 'assets'))

#: The player's car: bodywork, interior and glass in one file.
HERO = 'cars/hero.glb'

#: Its wheels, mounted four times. Both are the radius the physics rides on;
#: the rear is the wider of the two, as a rear-driven car's is.
HERO_WHEEL_FRONT = 'cars/hero-wheel-front.glb'
HERO_WHEEL_REAR = 'cars/hero-wheel-rear.glb'

#: The clip the steering wheel's travel is carried in, posed rather than played:
#: its first key is full left lock, its last full right, and the game poses it at
#: the fraction of lock the front wheels are actually turned to.
STEER_CLIP = 'steer'

#: The shells of a vehicle. The exterior is left out of the frame for the view
#: from the driver's seat, which is a point inside it; the interior and the
#: glass are what that view looks at and through.
BODY = 'body'
INTERIOR = 'interior'
GLASS = 'glass'

#: The bodywork forward of the windscreen, as its own shell. It is the outside
#: of the car and painted like the rest of it, and it is also the thing a driver
#: sees most of: a view from a seat with no bonnet under it is a camera flying
#: down the road. So it is named apart from :data:`BODY` and survives the
#: cockpit view, which drops everything else on the outside.
#:
#: A vehicle without one is drawn without one -- only the player's car needs a
#: view from inside it.
BONNET = 'bonnet'

#: Inside the interior: the pillars framing the windscreen. Named so the game
#: can say whether the model it loaded carries them.
PILLARS = 'pillars'

#: Inside the interior: what the driver sits in, the column, and the rim that
#: turns on it. The column carries the rake and is left alone; the rim is what
#: the clip moves, about its own local Y, which the column's placement points
#: along the steering axis. Each end of the travel is less than half a turn from
#: centre, so a posed rotation says which way the wheel is turned.
SEATS = 'seats'
COLUMN = 'steering'
RIM = 'steering_wheel'

#: The materials a vehicle is made of. The paint is the one a traffic car is
#: repainted in, which is why the trim and the glass are their own: a road full
#: of cars is one model painted a dozen ways, and painting its windows would
#: cost it its windows.
PAINT = 'paint'
TRIM = 'trim'
INTERIOR_MATERIAL = 'interior'
RUBBER = 'rubber'

#: What an ordinary vehicle is made of. The hero carries these and more; a
#: traffic vehicle carries these and nothing else, so that a road full of them
#: costs one set of materials rather than five.
VEHICLE_MATERIALS = (PAINT, TRIM, GLASS, INTERIOR_MATERIAL, RUBBER)


@dataclass(frozen=True)
class TrafficKind:
    """One ordinary vehicle using the road: its model, and how big it is.

    The dimensions are the model's own, in metres, and they are also what the
    player hits: the collider is built from them rather than from one box shared
    by every vehicle, so a van is as big to hit as it is to see.
    """

    name: str
    model: str
    length: float
    width: float
    height: float

    def size(self) -> tuple[float, float, float]:
        """The vehicle's extent, in the (x, y, z) order a collider box takes."""
        return (self.width, self.height, self.length)


#: The road's ordinary traffic. Five plain shapes rather than five interesting
#: ones: what a player needs from an oncoming vehicle is to recognise it at a
#: glance and at speed, and a fleet of show cars reads as a car show.
TRAFFIC = (
    TrafficKind('saloon', 'cars/traffic/saloon.glb', 4.6, 1.80, 1.45),
    TrafficKind('hatchback', 'cars/traffic/hatchback.glb', 3.9, 1.72, 1.50),
    TrafficKind('estate', 'cars/traffic/estate.glb', 4.8, 1.80, 1.55),
    TrafficKind('van', 'cars/traffic/van.glb', 5.2, 1.95, 2.15),
    TrafficKind('pickup', 'cars/traffic/pickup.glb', 5.4, 1.90, 1.80),
)
