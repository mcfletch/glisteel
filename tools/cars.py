#!/usr/bin/env python
"""Generate the vehicles GLinting Steel drives, and the ones it drives past.

Seven assets out of one run: the player's car, its two wheels, and the five
ordinary vehicles that use the same road. One script because they share every
material, every mesh helper and every convention: a road full of cars built by
two scripts is a road whose cars stop matching.

Everything is in metres, in Blender's Z-up space, **nose along +Y**. The
exporter's Y-up conversion maps that to **-Z**, which is where
``omi_physics.car_wheels`` puts a front axle, and it converts every node's own
transform the same way -- so nothing here carries a correcting rotation and each
named part's local space is the model's own. Blender's Back view (Ctrl-Numpad-1)
looks the vehicle in the face.

The player's car is built to the numbers ``glisteel.car`` already holds, so the
bodywork is the box the chassis collider is and the wheels are the radius the
suspension rides on:

=====================  ========  =====================================
Body length            4.20 m    ``BODY_LENGTH``
Body width             1.85 m    ``BODY_WIDTH``
Lower body height      0.62 m    ``BODY_HEIGHT``
Cabin above that       0.42 m    ``CABIN_HEIGHT``
Wheelbase              2.55 m    ``WHEELBASE``
Wheel radius           0.33 m    ``WHEEL_RADIUS``
=====================  ========  =====================================

**The names are the interface.** Each vehicle exports three named subtrees --
``body``, ``interior`` and ``glass`` -- with ``seats``, ``pillars`` and the
steering column inside the interior, and its materials are named ``paint``,
``trim``, ``glass``, ``interior`` and ``rubber``. The player's car carries a
fourth top-level subtree, ``bonnet``: the shell forward of the windscreen,
split from ``body`` because it is the one piece of the outside a driver still
sees from inside. ``glisteel.models`` names them from the other side and
``tests/test_models.py`` asserts every one of them, along with the dimensions,
the budgets and the steering travel.

**The steering travel is a clip, not a number.** The rim carries an action named
``steer``: full left at its first key, centred at its second, full right at its
third, turning about the rim's own local Z. The game poses it at the fraction of
lock the front wheels are actually turned to, so how far the rim moves is an
edit to two keyframes rather than to code.

**The paint is a finish, not a colour.** It is built on a CC0 material from
ambientCG (``Metal032``), which
:func:`OpenGLContext.loaders.cc0.material` downloads and caches; ``--paint-maps``
says where those maps are and a build without them paints flat colour instead.
The car's own colour multiplies over the map's grain, and a clear coat rides on
top as ``KHR_materials_clearcoat``. The bodywork is smoothed by angle, so the
panels are smooth and the crease lines between them stay sharp.

**The glass refracts.** Its Principled shader gives the exporter
``KHR_materials_transmission`` and ``KHR_materials_ior``; the Volume Absorption
node and the ``Thickness`` socket on the ``glTF Material Output`` group give it
``KHR_materials_volume``, which is what makes thick glass bend and tint along
the path rather than only at its surface. The traffic's glass is thin and skips
the volume, because ten cars' worth of it passes at a closing speed of two
hundred.

Run it with an interpreter that can ``import bpy`` -- in this container, the
virtualenv at ``/workspaces/OpenGL-dev/.venv-bpy`` -- or through a Blender
install::

    /workspaces/OpenGL-dev/.venv-bpy/bin/python tools/cars.py
    blender --background --python tools/cars.py -- --output-dir models

It writes ``models/cars.blend`` with everything in it for editing, and the
``.glb`` files straight into the game's own assets, so building a model and
updating the game's copy of it are not two things to remember.
"""
import argparse
import json
import math
import os
import struct
import sys
from contextlib import contextmanager

import bpy
import numpy as np
from mathutils import Vector

# --- What the vehicles are built to -----------------------------------------
#
# These are ``glisteel.car``'s own constants. The bodywork is the box the
# chassis collider is, so a model that drifts from them is a car whose paint
# and whose physics disagree about where it ends.

BODY_LENGTH = 4.20
BODY_WIDTH = 1.85
BODY_HEIGHT = 0.62
CABIN_HEIGHT = 0.19
WHEELBASE = 2.55
TRACK = 1.58
WHEEL_RADIUS = 0.33
RIDE_HEIGHT = 0.14

HALF_L = BODY_LENGTH / 2.0        # 2.10, the nose at +Y and the tail at -Y
NOSE, TAIL = HALF_L, -HALF_L
HALF_W = BODY_WIDTH / 2.0         # 0.925, the widest point of the haunches
FLOOR = -BODY_HEIGHT / 2.0        # -0.31, the underbody
BELT = BODY_HEIGHT / 2.0          # +0.31, where the bodywork stops and glass starts
ROOF = BELT + CABIN_HEIGHT        # +0.50, the top of the canopy

#: Where the canopy starts and ends, and where it peaks. Cab-forward: the peak
#: is ahead of the middle of the car and the tail runs a long way behind it.
SCREEN_BASE = 1.30
CANOPY_PEAK = 0.10
CANOPY_REAR = -1.00

#: Where the axles are, which is where the arches have to be: the body is drawn
#: in at both so the wheels stand proud of it, and the widest point of the car
#: is the haunch just ahead of the rear axle rather than the arch itself.
FRONT_AXLE = WHEELBASE / 2.0
REAR_AXLE = -WHEELBASE / 2.0

#: Where the driver sits: on the centreline, with the passenger behind rather
#: than beside. A canopy this narrow has no room for two abreast, and a car
#: driven from the middle is aimed the way the driver is looking rather than
#: from a corner of it.
DRIVER_X = 0.0

#: Where each seat's cushion starts, along the car. The driver is ahead of the
#: axle line and the passenger behind, which is what puts both under the roof.
SEAT_FRONT = 0.34
SEAT_REAR = -0.42

#: How far the rim turns from centre at full lock, and the rake of the column
#: it turns on. Less than half a turn either way, so a posed rotation says
#: which way the wheel is turned.
STEER_LOCK = math.radians(150.0)
COLUMN_RAKE = math.radians(68.0)

#: How many sides a traffic vehicle's tyre has, and how wide it is. Twelve
#: because it puts a vertex at the bottom of the wheel: a polygon with none
#: there stands the vehicle a centimetre off the road it is supposed to be on.
TRAFFIC_SEGMENTS = 12
TRAFFIC_TYRE_WIDTH = 0.20

#: Where the bodywork stops on the way down at the arches: clear of the top of
#: a tyre, so a wheel stands in a well under the car rather than beside it.
WELL = -BODY_HEIGHT / 2.0 + RIDE_HEIGHT + WHEEL_RADIUS + 0.05

#: How sharp the clear coat's reflections are. Low, because a lacquer over
#: paint reflects almost as cleanly as a mirror. Blender's exporter writes the
#: coat's weight but not its roughness, so :func:`coat_roughness` puts this into
#: the finished file -- see the note there.
COAT_ROUGHNESS = 0.03

#: What the player's car is painted. A metallic paint's base colour tints what
#: it reflects rather than colouring a surface, so it reads darker than the same
#: value would on a matte panel: this is a deep blue.
HERO_COLOUR = (0.16, 0.22, 0.42)

#: How large the paint's CC0 maps are carried at. A car's paint is a finish
#: rather than a pattern, and 512 across is enough to read as one while keeping
#: the file a tenth of what the source maps weigh.
PAINT_TEXTURE_SIZE = 512

#: Where those maps are, as ``OpenGLContext.loaders.cc0`` leaves them.
PAINT_MAPS = os.path.join(os.path.expanduser('~'), '.config', 'OpenGLContext',
                          'cc0', 'Metal032_1K')

#: How many spokes a wheel face carries, and how deep its tyre's sidewall is as
#: a fraction of the wheel's radius. A third of the radius is a sports car's;
#: much less and the wheel reads as a hoop with spokes in it.
WHEEL_SPOKES = 5
BEAD_FRACTION = 0.68

#: How finely the round things are drawn. A wheel seen at a hundred and thirty
#: is a dark disc with a bright rim; the segments are what the silhouette is
#: made of, and past this they cost triangles nobody sees.
WHEEL_SEGMENTS = 20
RIM_SEGMENTS = 24

#: The tyres, front and rear. One diameter, because the physics carries one
#: radius; wider at the back, because width is not simulated and that is what a
#: rear-driven car looks like.
TYRE_WIDTH_FRONT = 0.24
TYRE_WIDTH_REAR = 0.26

#: Where this script writes, when it is not told otherwise.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
ASSET_DIR = os.path.join(_PROJECT, 'glisteel', 'assets', 'cars')
BLEND_DIR = os.path.join(_PROJECT, 'models')


# --- Mesh construction -----------------------------------------------------

def _finish(name, verts, faces, material, smooth=False):
    """One object from points and faces, with its normals pointing outward."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([Vector(v) for v in verts], [], [list(f) for f in faces])
    mesh.validate()
    if material is not None:
        mesh.materials.append(material)
    if smooth:
        for polygon in mesh.polygons:
            polygon.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    _outward(obj)
    return obj


def _outward(obj):
    """Face every polygon away from the middle of the object it belongs to."""
    mesh = obj.data
    centre = sum((Vector(v.co) for v in mesh.vertices), Vector()) / max(len(mesh.vertices), 1)
    for polygon in mesh.polygons:
        middle = Vector(polygon.center) - centre
        if polygon.normal.dot(middle) < 0.0:
            polygon.flip()
    mesh.update()


def box(name, low, high, material, name_suffix=''):
    """A rectangular solid between two opposite corners."""
    (x0, y0, z0), (x1, y1, z1) = low, high
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return _finish(name + name_suffix, verts, faces, material)


def pane(name, half_w, lower, upper, material, thickness=0.02):
    """A flat panel across the car between two edges, as a windscreen is.

    ``lower`` and ``upper`` are ``(y, z)``: where the glass meets the bodywork
    and where it meets the roof. A panel built between the two edges fills its
    opening whatever the rake, which a box turned to the same angle does not.
    """
    (y0, z0), (y1, z1) = lower, upper
    span = math.hypot(y1 - y0, z1 - z0) or 1.0
    # The normal of the panel in the y-z plane, which is the way it thickens.
    ny, nz = (z1 - z0) / span * thickness, -(y1 - y0) / span * thickness
    verts = [(-half_w, y0, z0), (half_w, y0, z0), (half_w, y1, z1), (-half_w, y1, z1),
             (-half_w, y0 + ny, z0 + nz), (half_w, y0 + ny, z0 + nz),
             (half_w, y1 + ny, z1 + nz), (-half_w, y1 + ny, z1 + nz)]
    faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return _finish(name, verts, faces, material)


def loft(name, sections, material, smooth=False):
    """A hull drawn through a series of cross-sections.

    ``sections`` is ``(y, ring)`` pairs, nose first; every ring is the same
    number of ``(x, z)`` points, in the same order round. The ends are capped,
    so what comes out is a closed solid rather than a sheet with a boundary.
    """
    width = len(sections[0][1])
    verts, faces = [], []
    for y, ring in sections:
        assert len(ring) == width, 'ring %r is not %d points' % (ring, width)
        verts.extend((x, y, z) for x, z in ring)
    for index in range(len(sections) - 1):
        here, there = index * width, (index + 1) * width
        for j in range(width):
            k = (j + 1) % width
            faces.append((here + j, here + k, there + k, there + j))
    faces.append(tuple(range(width - 1, -1, -1)))
    faces.append(tuple(range(len(verts) - width, len(verts))))
    return _finish(name, verts, faces, material, smooth=smooth)


def split_loft(sections, at):
    """Cut a loft's cross-sections in two at ``at``, nose-first sections either side.

    ``at`` is a Y value between two of ``sections``' own stations, or one of
    them exactly. The boundary ring is the two neighbours' rings blended by
    where ``at`` falls between them -- the same blend :func:`loft` already
    draws its ruled surface through there, so the cut adds no surface of its
    own and leaves no gap: it only names the seam.
    """
    for index in range(len(sections) - 1):
        (y0, ring0), (y1, ring1) = sections[index], sections[index + 1]
        if not y1 <= at <= y0:
            continue
        if at == y0:
            boundary = ring0
        elif at == y1:
            boundary = ring1
        else:
            fraction = (y0 - at) / (y0 - y1)
            boundary = [(x0 + (x1 - x0) * fraction, z0 + (z1 - z0) * fraction)
                       for (x0, z0), (x1, z1) in zip(ring0, ring1, strict=True)]
        forward = sections[:index + 1] + ([] if at == y0 else [(at, boundary)])
        aft = ([] if at == y1 else [(at, boundary)]) + sections[index + 1:]
        return forward, aft
    raise ValueError('%.3f is not between any of the loft\'s own stations' % (at,))


def car_section(half_w, low, arch, crest, top_w, camber=0.0, tuck=0.62,
                shoulder=0.62, well=None):
    """One cross-section of a sports car: arches either side of a lower top.

    What makes a car read as a car from the side and the front is that the
    flanks stand **higher than the middle** over the axles -- the bonnet dips
    between the front arches and the deck between the rear ones -- and lower
    than it through the cabin. So a section carries two heights: ``arch``, the
    top of the flank, and ``crest``, where the top surface sits across
    ``top_w``. ``camber`` lifts the centre of that surface, which keeps a wide
    bonnet from reading as a flat plate.

    ``low`` is the floor and ``tuck`` how far the floor is drawn in under the
    flanks. ``well`` is where the bodywork stops on the way down at its outer
    edge: over an axle it is lifted clear of the top of the tyre, which opens
    the arch the wheel stands **inside**. Without it the flank runs down past
    the wheel to the floor, and the wheel reads as bolted to the outside of the
    car rather than housed under it.

    ``shoulder`` is how high up the section its widest point is: high on an
    arch, low through the sills.
    """
    rise = max(arch - low, 1e-3)
    lip = half_w if well is not None else half_w * 0.94
    haunch = half_w * (0.99 if well is not None else 0.94)
    well = low if well is None else well
    # The widest point cannot sit below the lip of the well, or the outline
    # doubles back on itself and the surface through it folds.
    waist = max(low + rise * shoulder, well + 0.01)
    return [(-half_w * tuck, low), (half_w * tuck, low),
            (lip, well),
            (half_w, waist), (haunch, arch),
            (top_w, crest), (0.0, crest + camber), (-top_w, crest),
            (-haunch, arch), (-half_w, waist),
            (-lip, well)]


def ring(half_w, low, high, top_w=None, tuck=0.86, shoulder=0.5, crown=0.72):
    """One cross-section of a body: a rectangle with its corners taken off.

    ``half_w`` is the widest point and ``top_w`` the width at the top; ``tuck``
    draws the floor in under the flanks, which is what makes a car look like it
    is standing on its wheels rather than sitting on a box.
    """
    top_w = half_w if top_w is None else top_w
    rise = high - low
    return [(-half_w * tuck, low), (half_w * tuck, low),
            (half_w, low + rise * shoulder), (top_w, high - rise * 0.14),
            (top_w * crown, high), (-top_w * crown, high),
            (-top_w, high - rise * 0.14), (-half_w, low + rise * shoulder)]


def revolve(name, profile, material, segments=WHEEL_SEGMENTS, smooth=True):
    """A solid of revolution about the X axis, for a wheel lying on its side.

    ``profile`` is ``(x, radius)`` pairs describing the surface from one face
    round to the other; the ends are joined through the axis, so a profile that
    starts and finishes at radius 0 comes out closed.
    """
    verts, faces = [], []
    for step in range(segments):
        angle = 2.0 * math.pi * step / segments
        for across, radius in profile:
            verts.append((across, radius * math.cos(angle), radius * math.sin(angle)))
    width = len(profile)
    for step in range(segments):
        here, there = step * width, ((step + 1) % segments) * width
        for j in range(width - 1):
            faces.append((here + j, here + j + 1, there + j + 1, there + j))
    return _finish(name, verts, faces, material, smooth=smooth)


def disc(name, across, radius, material, segments=WHEEL_SEGMENTS, inner=0.0):
    """A flat face across the X axis: a wheel's own, or a ring around a hub."""
    verts, faces = [], []
    for step in range(segments):
        angle = 2.0 * math.pi * step / segments
        verts.append((across, inner * math.cos(angle), inner * math.sin(angle)))
        verts.append((across, radius * math.cos(angle), radius * math.sin(angle)))
    for step in range(segments):
        here, there = step * 2, ((step + 1) % segments) * 2
        faces.append((here, here + 1, there + 1, there))
    return _finish(name, verts, faces, material)


def roundel(name, x, y, z, radius, material, segments=16, inner=0.0):
    """A flat circular face across the car's length, for a dial or a vent.

    ``disc`` and ``revolve`` build round the vehicle's own X axis, which is
    where a wheel spins; a roundel builds round Y instead, at its own
    ``(x, y, z)`` centre, for something set into the dash and looked at from
    behind rather than from the side. Built this way it faces **-Y**, back
    toward the driver's seat, which is the only direction anything on a dash
    needs to face.
    """
    verts, faces = [], []
    for step in range(segments):
        angle = 2.0 * math.pi * step / segments
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        verts.append((x + inner * cos_a, y, z + inner * sin_a))
        verts.append((x + radius * cos_a, y, z + radius * sin_a))
    for step in range(segments):
        here, there = step * 2, ((step + 1) % segments) * 2
        faces.append((here, here + 1, there + 1, there))
    return _finish(name, verts, faces, material)


def bezel(name, x, y, z, radius, tube, material, segments=24):
    """A rounded ring facing along Y, for a dial's bezel: a torus, not a flat disc.

    A flat ring shows one flat tone under a cabin's own low light; a rounded
    one sweeps light and dark around its own curve the way a chromed bezel
    does, which is what keeps a bright material reading as a ring rather than
    disappearing into the moulding behind it. Built the way :func:`_rim`
    builds the steering wheel's own hoop, with the ring's plane turned from
    the vehicle's XY to its XZ.
    """
    verts, faces = [], []
    for step in range(segments):
        angle = 2.0 * math.pi * step / segments
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        centre = Vector((x + cos_a * radius, y, z + sin_a * radius))
        out = Vector((cos_a, 0.0, sin_a))
        for face in range(4):
            turn = 2.0 * math.pi * face / 4.0
            verts.append(tuple(centre + out * (math.cos(turn) * tube)
                               + Vector((0.0, math.sin(turn) * tube, 0.0))))
    for step in range(segments):
        here, there = step * 4, ((step + 1) % segments) * 4
        for j in range(4):
            k = (j + 1) % 4
            faces.append((here + j, here + k, there + k, there + j))
    return _finish(name, verts, faces, material, smooth=True)


def parent_to(children, parent, keep_place=True):
    """Hang objects under one parent.

    ``keep_place`` leaves each child where it already stands, which is what
    parts built in the vehicle's own coordinates want. Without it a child keeps
    its own local transform and takes its place from the parent -- which is what
    a rim on a raked column wants, and the only way the rim's local rotation
    stays a turn about its own Z. glTF has no parent-inverse to carry the
    difference: the exporter folds it into the child, and a rim exported that
    way turns about an axis nobody chose.
    """
    for child in children:
        child.parent = parent
        if keep_place:
            child.matrix_parent_inverse = parent.matrix_world.inverted()
    return parent


def empty(name, location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)):
    """A node with no geometry: a name in the file, and a place to hang things."""
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = 'PLAIN_AXES'
    obj.empty_display_size = 0.12
    obj.location = location
    obj.rotation_euler = rotation
    bpy.context.scene.collection.objects.link(obj)
    return obj


def join(name, parts, material):
    """One mesh out of several, so a shell costs one draw rather than nine."""
    bpy.ops.object.select_all(action='DESELECT')
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    joined = parts[0]
    joined.name = name
    joined.data.name = name
    joined.data.materials.clear()
    joined.data.materials.append(material)
    bpy.ops.object.select_all(action='DESELECT')
    return joined


# --- Materials -------------------------------------------------------------

def _principled(material):
    return next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')


def _add(tree, kind, location, label=None, **settings):
    """One shader node, placed and named so the .blend is readable."""
    node = tree.nodes.new(kind)
    node.location = location
    if label:
        node.name = node.label = label
    for key, value in settings.items():
        setattr(node, key, value)
    return node


def _socket(node, name):
    """One named input of a node, whichever index it happens to be at."""
    return node.inputs[name]


def _settings_group():
    """The node group the glTF exporter reads a thickness from.

    The exporter takes ``KHR_materials_volume``'s thickness from this group's
    input rather than from the Principled shader, which has nowhere to put it.
    """
    group = bpy.data.node_groups.get('glTF Material Output')
    if group is None:
        group = bpy.data.node_groups.new('glTF Material Output', 'ShaderNodeTree')
        group.interface.new_socket('Thickness', in_out='INPUT',
                                   socket_type='NodeSocketFloat')
        group.nodes.new('NodeGroupInput').location = (-200, 0)
    return group


def unwrap(obj, angle=66.0, margin=0.01):
    """Lay an object out in UV space, so a texture has somewhere to sit."""
    layer = bpy.context.view_layer
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    return obj


def _map(path, colour_space, size=PAINT_TEXTURE_SIZE):
    """One texture off disk, scaled to what a car needs rather than what it is."""
    image = bpy.data.images.load(path, check_existing=True)
    image.colorspace_settings.name = colour_space
    if size and max(image.size) > size:
        image.scale(size, size)
    return image


def _tinted(image, tint, name):
    """A copy of a colour map in another colour, keeping its grain.

    The tint is carried in the pixels rather than in a node upstream of them.
    A shader graph that mixes a colour into a texture is not something glTF can
    say, and Blender's exporter answers by writing the texture alone -- which
    paints the car whatever colour the source material happened to be. So the
    map is divided by its own average and multiplied by the colour wanted: the
    same grain, in this car's paint.
    """
    pixels = np.empty(len(image.pixels), dtype='f')
    image.pixels.foreach_get(pixels)
    rgba = pixels.reshape(-1, 4)
    average = rgba[:, :3].mean(axis=0)
    average[average < 1e-4] = 1.0
    rgba[:, :3] = np.clip(rgba[:, :3] / average * np.asarray(tint, dtype='f'),
                          0.0, 1.0)
    out = bpy.data.images.new(name, image.size[0], image.size[1], alpha=False)
    out.colorspace_settings.name = image.colorspace_settings.name
    out.pixels.foreach_set(rgba.ravel())
    out.update()
    return out


def car_paint(name, tint, maps, metallic=0.25, roughness=0.32, coat=1.0,
              coat_roughness=COAT_ROUGHNESS):
    """Paint: a CC0 metal under a clear coat, tinted the car's own colour.

    The finish comes from a public-domain material rather than from invented
    numbers -- its fine surface in the normal map, its variation in the
    roughness -- and the colour is this car's, multiplied over it. Over that sits
    the coat.

    **Metallic paint is not a metal.** A fully metallic surface has no colour of
    its own; it only tints what it reflects. A car set to 1.0 therefore comes
    out as chrome in the colour of the sky above it, whatever it was painted.
    What makes paint read as paint here is a mostly dielectric base carrying the
    colour, a roughness glossy without being a mirror, and the coat over it
    doing the sharp reflections. ``KHR_materials_clearcoat`` carries that coat,
    and its factor is defined over 0..1: a weight above that does not survive
    the export, so 1.0 is as much coat as a glTF can hold.

    ``maps`` is ``{'color', 'roughness', 'normal'}`` of file paths, or None for
    a car built where those files are not to hand, which gets the tint alone.
    The map's own colour is replaced by this car's, keeping its grain -- see
    :func:`_tinted`.
    """
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    bsdf = _principled(material)
    material.use_backface_culling = True
    bsdf.inputs['Base Color'].default_value = (*tint, 1.0)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    for socket, value in (('Coat Weight', coat), ('Coat Roughness', coat_roughness)):
        if socket in bsdf.inputs:
            bsdf.inputs[socket].default_value = value
    if not maps:
        return material

    if maps.get('color'):
        image = _add(tree, 'ShaderNodeTexImage', (-760, 320), 'Paint Color',
                     image=_tinted(_map(maps['color'], 'sRGB'), tint,
                                   name + '_baseColor'))
        tree.links.new(image.outputs['Color'], _socket(bsdf, 'Base Color'))
    if maps.get('roughness'):
        rough = _add(tree, 'ShaderNodeTexImage', (-760, 0), 'Paint Roughness',
                     image=_map(maps['roughness'], 'Non-Color'))
        scale = _add(tree, 'ShaderNodeMapRange', (-420, 0), 'Roughness Range')
        scale.inputs['To Min'].default_value = roughness * 0.7
        scale.inputs['To Max'].default_value = roughness * 1.4
        tree.links.new(rough.outputs['Color'], scale.inputs['Value'])
        tree.links.new(scale.outputs['Result'], _socket(bsdf, 'Roughness'))
    if maps.get('normal'):
        relief = _add(tree, 'ShaderNodeTexImage', (-760, -320), 'Paint Normal',
                      image=_map(maps['normal'], 'Non-Color'))
        tangent = _add(tree, 'ShaderNodeNormalMap', (-420, -320))
        tangent.inputs['Strength'].default_value = 0.35
        tree.links.new(relief.outputs['Color'], _socket(tangent, 'Color'))
        tree.links.new(tangent.outputs['Normal'], _socket(bsdf, 'Normal'))
    return material


def surface(name, colour, metallic=0.0, roughness=0.5, emission=None,
            both_sides=False):
    """An ordinary opaque material: a colour, and how it takes the light.

    ``both_sides`` keeps a surface visible from behind. The inside of a wheel's
    barrel is seen through the gaps in its own spokes, and a barrel drawn one
    side out is a hole with the sky behind it.
    """
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.use_backface_culling = not both_sides
    bsdf = _principled(material)
    bsdf.inputs['Base Color'].default_value = (*colour, 1.0)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    if emission is not None:
        bsdf.inputs['Emission Color'].default_value = (*colour, 1.0)
        bsdf.inputs['Emission Strength'].default_value = emission
    return material


def glazing(name, tint=(0.72, 0.80, 0.84), roughness=0.03, ior=1.52,
            thickness=0.0, attenuation=None, transmission=1.0):
    """Glass. With a ``thickness`` it refracts through its volume as well.

    ``thickness`` is the pane's own, in metres, and ``attenuation`` how far
    light travels through the glass before the tint has taken it -- the two
    numbers ``KHR_materials_volume`` carries. Without them the glass still
    refracts at its surface, which is what a car passing at speed needs.
    """
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    bsdf = _principled(material)
    bsdf.inputs['Base Color'].default_value = (*tint, 1.0)
    bsdf.inputs['Metallic'].default_value = 0.0
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Transmission Weight'].default_value = float(transmission)
    bsdf.inputs['IOR'].default_value = ior
    if thickness > 0.0:
        absorb = tree.nodes.new('ShaderNodeVolumeAbsorption')
        absorb.location = (-200, -300)
        absorb.inputs['Color'].default_value = (*tint, 1.0)
        absorb.inputs['Density'].default_value = 1.0 / float(attenuation or 2.0)
        tree.links.new(absorb.outputs['Volume'],
                       tree.nodes['Material Output'].inputs['Volume'])
        settings = tree.nodes.new('ShaderNodeGroup')
        settings.node_tree = _settings_group()
        settings.name = settings.label = 'glTF Material Output'
        settings.location = (200, -300)
        settings.inputs['Thickness'].default_value = float(thickness)
    return material


def paint_maps(directory):
    """The CC0 finish the paint is built on, or None when it is not to hand.

    The maps come from ambientCG through
    :func:`OpenGLContext.loaders.cc0.material`, which downloads, caches and
    records them; this only reads what that left on disk. A build without them
    is a car in flat colour rather than a build that fails.
    """
    if not directory or not os.path.isdir(directory):
        return None
    found = {kind: os.path.join(directory, kind + '.jpg')
             for kind in ('color', 'roughness', 'normal')}
    found = {kind: path for kind, path in found.items() if os.path.isfile(path)}
    return found or None


def build_materials(paint=None):
    """Everything the vehicles are made of, named as the game asks for them.

    Two families, because the player's car and the traffic want different
    glass: the canopy is thick and worth looking through, and ten cars passing
    the other way are not. Each family's names are prefixed so that the whole
    fleet can live in one file; :func:`export_glb` strips the prefix, and what
    lands in a ``.glb`` is ``paint``, ``trim``, ``glass``, and the rest.
    """
    return {
        # The player's car: silver over a dark carbon underbody, the accent
        # picked out on the sills and the wheel centres.
        'hero:paint': car_paint('hero:paint', HERO_COLOUR, paint),
        # The lower body, in the near-black a car's cladding, sills and
        # diffuser are, so the paint above it reads as paint.
        'hero:accent': surface('hero:accent', (0.055, 0.056, 0.060), 0.35, 0.52),
        'hero:dark': surface('hero:dark', (0.030, 0.031, 0.034), 0.20, 0.66),
        'hero:tail': surface('hero:tail', (0.52, 0.03, 0.04), 0.0, 0.30,
                             emission=3.0),
        'hero:trim': surface('hero:trim', (0.68, 0.70, 0.72), 1.0, 0.18),
        'hero:interior': surface('hero:interior', (0.055, 0.057, 0.062), 0.0, 0.62),
        'hero:rubber': surface('hero:rubber', (0.042, 0.042, 0.046), 0.0, 0.86),
        # What fills a wheel behind its spokes: the barrel it is pressed from,
        # a brake disc turning inside it, and the caliper gripping that.
        'hero:barrel': surface('hero:barrel', (0.085, 0.087, 0.092), 0.70, 0.44,
                               both_sides=True),
        'hero:brake': surface('hero:brake', (0.36, 0.37, 0.39), 0.90, 0.34,
                              both_sides=True),
        'hero:caliper': surface('hero:caliper', (0.46, 0.05, 0.05), 0.30, 0.34),
        'hero:lights': surface('hero:lights', (0.85, 0.88, 0.95), 0.0, 0.18,
                               emission=2.4),
        'hero:glass': glazing('hero:glass', tint=(0.62, 0.70, 0.74), roughness=0.02,
                              thickness=0.012, attenuation=1.6),
        # The traffic: one set, five vehicles. The paint is the material the
        # game repaints per car, which is why nothing else shares it.
        'traffic:paint': surface('traffic:paint', (0.60, 0.60, 0.62), 0.75, 0.30),
        'traffic:trim': surface('traffic:trim', (0.62, 0.64, 0.66), 1.0, 0.24),
        'traffic:interior': surface('traffic:interior', (0.10, 0.10, 0.11), 0.0, 0.70),
        'traffic:rubber': surface('traffic:rubber', (0.048, 0.048, 0.052), 0.0, 0.88),
        # Darker and less transmissive than the canopy: car glass seen from
        # outside is a dark panel with the cabin faint behind it, and a window
        # that transmits everything reads as a hole where a window should be.
        'traffic:glass': glazing('traffic:glass', tint=(0.30, 0.36, 0.40),
                                 roughness=0.08, transmission=0.55),
    }


def smooth_by_angle(obj, degrees=38.0):
    """Smooth the panels and keep the creases between them.

    A car body is curved surfaces meeting at hard lines. Shading it all smooth
    rounds the shoulder line off into a bar of soap; shading it all flat turns
    the curves into facets. The angle is where one becomes the other.
    """
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(degrees))
    except (AttributeError, RuntimeError):     # pragma: no cover - older Blender
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    bpy.ops.object.select_all(action='DESELECT')
    return obj


# --- The player's car ------------------------------------------------------

def build_hero(materials):
    """The car the player drives: bonnet, bodywork, interior and canopy.

    One volume, cab-forward, falling from a low blade of a nose over a canopy
    that peaks ahead of the middle of the car and running back into a long
    tail. The flanks are cut away between the wheels into sill channels, and
    the haunches over the rear wheels are the widest part of it.
    """
    bonnet, body = _hero_body(materials)
    root = empty('hero')
    parent_to([body, bonnet, _hero_interior(materials),
               _hero_glass(materials)], root)
    return root


#: The hull's own cross-sections, nose first -- the proportions of a real
#: sports car, measured off a CC-BY donor and scaled to our own length: see
#: ``plans/CAR-MODELS.md``. None of the donor's geometry is here -- what
#: crossed is a table of where a car of this kind is wide, where its flanks
#: and its top surface sit, and where its floor is. The three things that make
#: it read as a car and that guesswork got wrong: the width is nearly constant
#: from the front arches to the tail, the whole body is low, and the front
#: arches stand above the bonnet between them.
#:
#: **The bonnet leaves the screen at the belt line and falls from there.** The
#: driver's eye is a hand's width over the front arches, so a bonnet that
#: starts below the base of the screen is seen edge-on for its whole length and
#: reads as a bar of metal with the arches standing up at each end of it, with
#: the road showing between them. Leaving the screen at the height the glass
#: meets it and falling to the nose over the next metre gives the eye the
#: *surface*, which is what a driver sees over. The arches still stand proud of
#: it, by four centimetres rather than eleven.
_HULL_SECTIONS = [
    (NOSE, car_section(0.42, -0.300, -0.060, 0.020, 0.30, 0.01, tuck=0.86)),
    (2.00, car_section(0.558, -0.306, -0.011, 0.078, 0.41, 0.01, tuck=0.86)),
    (1.81, car_section(0.751, -0.310, 0.088, 0.128, 0.56, 0.01, tuck=0.82)),
    (1.62, car_section(0.831, -0.310, 0.167, 0.186, 0.62, 0.01, tuck=0.78)),
    (1.43, car_section(0.906, -0.310, 0.290, 0.246, 0.62, tuck=0.72,
                       well=WELL - 0.07)),
    (FRONT_AXLE, car_section(HALF_W, -0.310, 0.340, 0.300, 0.62, tuck=0.62,
                             shoulder=0.74, well=WELL)),
    (1.05, car_section(0.906, -0.310, 0.330, 0.270, 0.62, tuck=0.62,
                       shoulder=0.74, well=WELL - 0.07)),
    (0.86, car_section(0.861, -0.306, 0.310, 0.310, 0.64, tuck=0.58)),
    (0.67, car_section(0.920, -0.294, 0.310, 0.310, 0.68, tuck=0.54)),
    (0.48, car_section(0.920, -0.293, 0.310, 0.310, 0.68, tuck=0.50)),
    (0.29, car_section(0.857, -0.293, 0.270, 0.310, 0.63, tuck=0.48)),
    (0.10, car_section(0.856, -0.293, 0.292, 0.310, 0.63, tuck=0.48)),
    (-0.10, car_section(0.852, -0.293, 0.310, 0.310, 0.63, tuck=0.48)),
    (-0.29, car_section(0.866, -0.306, 0.310, 0.310, 0.64, tuck=0.52)),
    (-0.48, car_section(0.884, -0.296, 0.310, 0.310, 0.65, tuck=0.56)),
    (-0.67, car_section(0.888, -0.297, 0.310, 0.310, 0.66, tuck=0.58)),
    (-0.86, car_section(0.889, -0.306, 0.310, 0.310, 0.66, tuck=0.60)),
    (-1.05, car_section(0.910, -0.308, 0.470, 0.480, 0.64, tuck=0.62,
                        well=WELL - 0.07)),
    (REAR_AXLE, car_section(HALF_W, -0.310, 0.480, 0.430, 0.64, tuck=0.62,
                            shoulder=0.72, well=WELL)),
    (-1.43, car_section(0.910, -0.310, 0.450, 0.400, 0.64, tuck=0.68,
                        well=WELL - 0.07)),
    (-1.62, car_section(0.886, -0.270, 0.358, 0.370, 0.66, tuck=0.74)),
    (-1.81, car_section(0.840, -0.182, 0.333, 0.346, 0.62, tuck=0.80)),
    (-2.00, car_section(0.669, -0.185, 0.316, 0.328, 0.49, tuck=0.84)),
    (TAIL, car_section(0.55, -0.190, 0.300, 0.310, 0.40, tuck=0.86)),
]


def _hero_body(materials):
    """The bonnet and the shell behind it: what the world sees of the car.

    A mid-engined sports car's proportions: a low full-width nose, the bonnet
    dipping between raised front arches, a waist drawn in at the sills, the
    widest point a haunch over the rear axle, and a tail cut off short behind
    it. The stations are close enough together that the silhouette is a curve
    rather than a set of facets, which costs a few hundred triangles.

    The hull is one loft, cut in two at ``SCREEN_BASE`` rather than modelled as
    two: the bonnet is what a driver still sees over the wheel once the rest
    of the outside drops out of the cockpit view, and the cut is where the two
    halves already meet, so nothing needs to line up by hand and no surface is
    drawn twice.
    """
    bonnet_stations, body_stations = split_loft(_HULL_SECTIONS, SCREEN_BASE)
    bonnet_shell = smooth_by_angle(
        loft('hero:bonnet_shell', bonnet_stations, materials['hero:paint']),
        degrees=34.0)
    unwrap(bonnet_shell)
    shell = smooth_by_angle(
        loft('hero:body_shell', body_stations, materials['hero:paint']),
        degrees=34.0)
    unwrap(shell)

    # The underbody, following the floor line: what gives the car its two tones
    # and its floor an edge for the light to catch.
    accent = loft('hero:body_accent', [
        (1.72, car_section(0.72, -0.310, -0.200, -0.220, 0.60, tuck=0.86)),
        (FRONT_AXLE, car_section(0.84, -0.310, -0.150, -0.190, 0.70, tuck=0.80)),
        (0.30, car_section(0.83, -0.294, -0.120, -0.160, 0.66, tuck=0.62)),
        (REAR_AXLE, car_section(0.87, -0.310, -0.140, -0.180, 0.72, tuck=0.80)),
        (-1.86, car_section(0.78, -0.190, -0.060, -0.090, 0.62, tuck=0.86)),
    ], materials['hero:accent'])

    lights = join('hero:body_lights', [
        box('hero:lamp_front_l', (-0.62, 1.90, 0.03), (-0.26, 1.78, 0.10),
            materials['hero:lights']),
        box('hero:lamp_front_r', (0.26, 1.90, 0.03), (0.62, 1.78, 0.10),
            materials['hero:lights']),
    ], materials['hero:lights'])

    # The back of a car is what most of the road sees of it, so it gets a
    # full-width lamp bar, a dark valance under it and vents let into the deck
    # over the engine -- three materials where there was one flat panel.
    rear = join('hero:body_rear', [
        box('hero:lamp_rear', (-0.72, TAIL + 0.09, 0.20),
            (0.72, TAIL + 0.01, 0.27), materials['hero:tail']),
        box('hero:lamp_rear_upper', (-0.30, TAIL + 0.08, 0.29),
            (0.30, TAIL + 0.02, 0.32), materials['hero:tail']),
    ], materials['hero:tail'])

    vents = join('hero:body_vents', [
        box('hero:vent%d' % index, (-0.46, -1.06 - index * 0.09, 0.44),
            (0.46, -1.11 - index * 0.09, 0.47), materials['hero:dark'])
        for index in range(4)
    ] + [
        box('hero:valance', (-0.68, TAIL + 0.12, 0.02),
            (0.68, TAIL, 0.19), materials['hero:dark']),
        box('hero:intake_left', (-0.92, -0.30, 0.00), (-0.78, -0.86, 0.22),
            materials['hero:dark']),
        box('hero:intake_right', (0.78, -0.30, 0.00), (0.92, -0.86, 0.22),
            materials['hero:dark']),
    ], materials['hero:dark'])

    # A splitter under the nose and a diffuser under the tail, each following
    # the bodywork it hangs off.
    aero = join('hero:body_trim', [
        loft('hero:splitter', [
            (NOSE - 0.02, car_section(0.44, -0.310, -0.290, -0.295, 0.38,
                                      tuck=0.94)),
            (1.86, car_section(0.66, -0.310, -0.295, -0.300, 0.58, tuck=0.94)),
            (1.66, car_section(0.80, -0.310, -0.300, -0.305, 0.70, tuck=0.94)),
        ], materials['hero:trim']),
        loft('hero:diffuser', [
            (-1.68, car_section(0.72, -0.300, -0.240, -0.250, 0.62, tuck=0.94)),
            (-1.92, car_section(0.66, -0.220, -0.160, -0.170, 0.56, tuck=0.94)),
            (TAIL + 0.02, car_section(0.52, -0.200, -0.140, -0.150, 0.44,
                                      tuck=0.94)),
        ], materials['hero:trim']),
    ], materials['hero:trim'])

    bonnet = parent_to([bonnet_shell], empty('hero:bonnet'))
    body = parent_to([shell, accent, lights, rear, vents, aero],
                     empty('hero:body'))
    return bonnet, body


def _hero_glass(materials):
    """The canopy: screen, roof and rear window over the cabin.

    It follows the same measured roofline the bodywork stops short of, so the
    greenhouse is the top of the car from the base of the screen back to the
    engine deck.
    """
    return loft('hero:glass', [
        # Not a bubble on a deck: a long, shallow screen running most of the
        # way back over the cabin to a short flat roof, narrow enough that the
        # bodywork carries a shoulder either side of it. Left faceted, because
        # what the shape is for is to look cut rather than blown.
        (SCREEN_BASE, car_section(0.62, 0.290, 0.300, 0.310, 0.50, tuck=0.96,
                                  shoulder=0.5)),
        (0.95, car_section(0.68, 0.290, 0.360, 0.380, 0.56, tuck=0.96,
                           shoulder=0.5)),
        (0.55, car_section(0.72, 0.290, 0.430, 0.450, 0.58, tuck=0.96,
                           shoulder=0.5)),
        (CANOPY_PEAK, car_section(0.72, 0.290, 0.480, ROOF, 0.56, tuck=0.96,
                                  shoulder=0.5)),
        (-0.35, car_section(0.70, 0.295, 0.480, ROOF, 0.52, tuck=0.96,
                            shoulder=0.5)),
        (-0.72, car_section(0.66, 0.300, 0.420, 0.440, 0.46, tuck=0.96,
                            shoulder=0.5)),
        (CANOPY_REAR, car_section(0.60, 0.305, 0.350, 0.365, 0.40, tuck=0.96,
                                  shoulder=0.5)),
    ], materials['hero:glass'])


def _hero_interior(materials):
    """What the driver sits in: the tub, two seats, the dash, the pillars and the wheel."""
    inside = materials['hero:interior']
    tub = join('hero:interior_tub', [
        box('hero:floor', (-0.52, 1.16, FLOOR + 0.03),
            (0.52, -1.05, FLOOR + 0.09), inside),
        box('hero:bulkhead', (-0.52, -0.94, FLOOR + 0.03),
            (0.52, -1.04, BELT - 0.02), inside),
        # The toeboard: closes the gap a flat floor and a raised dash would
        # otherwise leave between them, from the true floor up past the dash's
        # own underside, so there is no line of sight past the pedals to the
        # road. Without it a dash this shallow is a shelf floating in the air.
        box('hero:toeboard', (-0.58, 0.88, FLOOR),
            (0.58, 1.18, FLOOR + 0.40), inside),
        # The sills run the cabin's full length now, up to the toeboard, and
        # widen out towards the car's own sides -- level with the toeboard's
        # own top rather than rising to the belt line, so what closes the road
        # out from beside the pedals reads as a sill well under the driver's
        # eye rather than as a door card standing over it.
        box('hero:sill_left', (-0.90, 1.18, FLOOR + 0.03),
            (-0.50, -0.94, FLOOR + 0.40), inside),
        box('hero:sill_right', (0.50, 1.18, FLOOR + 0.03),
            (0.90, -0.94, FLOOR + 0.40), inside),
    ], inside)

    seats = join('hero:seats', [
        part for index, along in enumerate((SEAT_FRONT, SEAT_REAR))
        for part in _seat(DRIVER_X, along, FLOOR + 0.09, inside,
                          'hero:seat%d' % index, width=0.46, back=0.44,
                          head=0.12)], inside)
    return parent_to([tub, _hero_dash(materials), seats,
                      _hero_wheel_column(materials), _hero_pillars(materials)],
                     empty('hero:interior'))


def _hero_dash(materials):
    """The dashboard: a hooded binnacle, a centre stack, and an eyeball vent each end.

    A dashboard modelled as one unbroken sweep reads, driven, as a grey slab
    across the bottom third of every frame -- the HUD is what the driver
    *reads*, and the dashboard is what tells them they are sitting in a car at
    all. So the sweep stays as the base and carries, all in mouldings and
    discs since the car has no textures: a cowl over the column with two
    recessed dials in it, a stack on the centreline with vents and switches,
    and a round vent at each outboard end.
    """
    inside, trim = materials['hero:interior'], materials['hero:trim']
    sweep = join('hero:dash_sweep', [
        box('hero:dash_face', (-0.58, 1.16, FLOOR + 0.16),
            (0.58, 1.02, FLOOR + 0.40), inside),
        box('hero:dash_top', (-0.58, 1.16, FLOOR + 0.38),
            (0.58, 0.94, FLOOR + 0.43), inside),
    ], inside)

    # The binnacle: a cowl hooding forward over the steering column. The dials
    # sit *inside* the rim's opening, which is where a driver reads them from
    # and where they cost nothing: the eye is at COCKPIT_UP, 0.40 above the
    # body's centre, and anything mounted near that height between the driver
    # and the screen is a slab across the road rather than an instrument. The
    # hood tops out a good hand's width below the eye for the same reason.
    #
    # Each bezel is a rounded ring rather than a flat one, since a flat ring
    # faced square at the eye shows one flat tone under this cabin's own low
    # light and a rounded one sweeps light around its curve the way the rim's
    # own hoop does -- that sweep is what a bright material needs to read as a
    # ring rather than sink into the moulding behind it.
    dial_z = FLOOR + 0.44
    binnacle = join('hero:dash_binnacle', [
        box('hero:dash_hood', (-0.19, 0.86, FLOOR + 0.34), (0.19, 1.04, FLOOR + 0.56),
            inside),
        bezel('hero:dash_dial_big_bezel', -0.085, 0.82, dial_z, 0.0875, 0.0125, trim,
             segments=24),
        roundel('hero:dash_dial_big_face', -0.085, 0.85, dial_z, 0.075, inside,
                segments=24),
        bezel('hero:dash_dial_small_bezel', 0.115, 0.82, dial_z, 0.0565, 0.0085, trim,
             segments=20),
        roundel('hero:dash_dial_small_face', 0.115, 0.85, dial_z, 0.048, inside,
                segments=20),
    ], inside)

    # The centre stack: a console standing proud of the dash on the
    # centreline, carrying the vents and switches a wide dash would put either
    # side of a passenger who, in this cab, is not sitting there.
    vent_positions = [(x, z) for z in (FLOOR + 0.30, FLOOR + 0.24)
                     for x in (-0.055, 0.055)]
    stack = join('hero:dash_stack', [
        box('hero:dash_stack_console', (-0.11, 0.96, FLOOR + 0.16),
            (0.11, 1.02, FLOOR + 0.36), inside),
    ] + [
        part
        for index, (vx, vz) in enumerate(vent_positions)
        for part in (
            box('hero:dash_vent%d_frame' % index, (vx - 0.022, 0.950, vz - 0.018),
                (vx + 0.022, 0.955, vz + 0.018), trim),
            box('hero:dash_vent%d_slat' % index, (vx - 0.022, 0.948, vz - 0.002),
                (vx + 0.022, 0.951, vz + 0.002), trim),
        )
    ] + [
        box('hero:dash_button%+d' % side, (side * 0.04 - 0.012, 0.950, FLOOR + 0.185),
            (side * 0.04 + 0.012, 0.958, FLOOR + 0.205), trim)
        for side in (-1, 1)
    ], inside)

    # The eyeball vents: one at each end of the dash, aimed at the driver the
    # way a real dash's are, mounted the same rounded-bezel, recessed-face way
    # as the binnacle's dials.
    vents = join('hero:dash_eyeballs', [
        part
        for side in (-1.0, 1.0)
        for part in (
            bezel('hero:dash_eyeball%+d_bezel' % side, side * 0.48, 0.925,
                 FLOOR + 0.40, 0.0405, 0.0045, trim),
            roundel('hero:dash_eyeball%+d_face' % side, side * 0.48, 0.945,
                    FLOOR + 0.40, 0.034, inside),
        )
    ], inside)

    return parent_to([sweep, binnacle, stack, vents], empty('hero:dash'))


def _hero_pillars(materials):
    """The screen's frame: two slim A-pillars and the header rail over them.

    Each pillar is lofted through the same Y stations the canopy's own loft
    climbs through, following its outboard corner up from the belt line to
    where the roof begins; the header bridges the gap between the pillars'
    tops on up to the roof, the way a real windscreen's top rail does. Both
    stay well inboard of the glass, so nothing here fights it for the same
    surface.
    """
    inside = materials['hero:interior']
    # (y, x, z) of the canopy's own outboard corner at each of its own
    # stations between the screen base and the roof, drawn in by 0.025 m in x
    # and 0.01 m in z so the pillar sits just inside the glass rather than on it.
    edge = [(SCREEN_BASE, 0.62 - 0.025, 0.300 - 0.010),
            (0.95, 0.68 - 0.025, 0.325 - 0.010),
            (0.55, 0.72 - 0.025, 0.360 - 0.010),
            (CANOPY_PEAK, 0.72 - 0.025, 0.385 - 0.010)]
    half_x, half_z = 0.016, 0.022

    def post(name, side):
        sections = [(y, [(side * cx - half_x, cz - half_z),
                         (side * cx + half_x, cz - half_z),
                         (side * cx + half_x, cz + half_z),
                         (side * cx - half_x, cz + half_z)])
                    for y, cx, cz in edge]
        return loft(name, sections, inside)

    # Kept above COCKPIT_UP (0.40 m): a header this close to the eye and this
    # wide would stand across the driver's own sightline rather than framing
    # it, the one thing a screen's frame must not do.
    header = box('hero:header_rail', (-0.70, 0.03, 0.44), (0.70, 0.18, 0.485), inside)
    return parent_to([post('hero:pillar_left', -1.0), post('hero:pillar_right', 1.0),
                      header], empty('hero:pillars'))


def _seat(x, y, floor, material, name, width=0.42, back=0.56, head=0.17):
    """One seat: a cushion, bolsters either side, a back and a headrest.

    ``y`` is where the front of the cushion is; the seat runs back from there.
    The bolsters and the headrest are what make it read as a seat through a
    window rather than as a step, and they are what a passing driver sees of
    somebody else's car.
    """
    half = width / 2.0
    return [
        box(name + '_cushion', (x - half, y, floor), (x + half, y - 0.46, floor + 0.12),
            material),
        box(name + '_bolster_l', (x - half, y - 0.04, floor + 0.10),
            (x - half + 0.07, y - 0.44, floor + 0.20), material),
        box(name + '_bolster_r', (x + half - 0.07, y - 0.04, floor + 0.10),
            (x + half, y - 0.44, floor + 0.20), material),
        box(name + '_back', (x - half, y - 0.44, floor + 0.02),
            (x + half, y - 0.58, floor + back), material),
        box(name + '_head', (x - 0.13, y - 0.44, floor + back),
            (x + 0.13, y - 0.58, floor + back + head), material),
    ]


def _hero_wheel_column(materials):
    """The column and the rim on it, and the travel the rim turns through.

    The column carries the rake and never moves; the rim is its child and turns
    about its own axis, which is what the ``steer`` clip keys and what the game
    poses at a fraction of full lock.
    """
    # Far enough back that the rim, which is 0.33 across and raked, clears the
    # dash in front of it: a wheel drawn through the dashboard is the first
    # thing a driver sees.
    column = empty('hero:steering', location=(DRIVER_X, SEAT_FRONT + 0.34,
                                              FLOOR + 0.38),
                   rotation=(COLUMN_RAKE, 0.0, 0.0))
    rim = _rim(materials)
    parent_to([rim], column, keep_place=False)
    _steer_clip(rim)
    return column


def _rim(materials, radius=0.165, tube=0.019, flat=0.62):
    """A racing wheel: a flat-bottomed rim, two spokes and a blank hub panel.

    ``flat`` is how far down the rim the bottom is cut off, as a fraction of
    the radius -- the D shape a driver's knees want and a racing car has. It is
    built in its own XY plane about its own Z, which the column's rake points
    along the steering axis and the exporter's Y-up conversion turns into the
    local Y the game poses about.
    """
    inside = materials['hero:interior']
    verts, faces = [], []
    for step in range(RIM_SEGMENTS):
        angle = 2.0 * math.pi * step / RIM_SEGMENTS
        x, y = math.cos(angle), math.sin(angle)
        along = max(y * radius, -radius * flat)          # the flat bottom
        centre = Vector((x * radius, along, 0.0))
        out = Vector((x, y, 0.0)).normalized()
        for face in range(4):
            turn = 2.0 * math.pi * face / 4.0
            verts.append(tuple(centre + out * (math.cos(turn) * tube)
                               + Vector((0.0, 0.0, math.sin(turn) * tube))))
    for step in range(RIM_SEGMENTS):
        here, there = step * 4, ((step + 1) % RIM_SEGMENTS) * 4
        for j in range(4):
            k = (j + 1) % 4
            faces.append((here + j, here + k, there + k, there + j))
    hoop = _finish('hero:rim_hoop', verts, faces, inside, smooth=True)

    parts = [hoop,
             box('hero:rim_spoke_l', (-radius * 0.94, -0.024, -0.012),
                 (-0.03, 0.024, 0.012), inside),
             box('hero:rim_spoke_r', (0.03, -0.024, -0.012),
                 (radius * 0.94, 0.024, 0.012), inside),
             box('hero:rim_hub', (-0.062, -0.05, -0.026),
                 (0.062, 0.05, 0.014), inside),
             # The instrument's panel, blank: the speed is on the HUD, and this
             # is where a readout goes when there is one.
             box('hero:rim_panel', (-0.052, -0.032, 0.013),
                 (0.052, 0.030, 0.019), inside)]
    return join('hero:steering_wheel', parts, inside)


def _steer_clip(rim, frames=(0, 12, 24)):
    """Key the rim's travel: full left, centred, full right.

    Three keys and linear interpolation, so the two halves of the movement are
    even either side of centre and any fraction between the ends is a pose the
    game can ask for. The first key is at frame zero, which is what puts the
    clip's first sample at time zero for a consumer that poses it by fraction.
    """
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = frames[0], frames[-1]
    rim.rotation_mode = 'XYZ'
    action = bpy.data.actions.new('steer')
    rim.animation_data_create().action = action
    for frame, angle in zip(frames, (STEER_LOCK, 0.0, -STEER_LOCK), strict=True):
        rim.rotation_euler = (0.0, 0.0, angle)
        rim.keyframe_insert(data_path='rotation_euler', frame=frame)
    rim.rotation_euler = (0.0, 0.0, 0.0)
    for curve in _curves(action):
        for point in curve.keyframe_points:
            point.interpolation = 'LINEAR'
    return action


def _curves(action):
    """Every f-curve of an action, whichever way this Blender stores them.

    A slotted action keeps its curves in the channel bags of its layers' strips;
    an older one keeps them in a flat list on the action itself.
    """
    flat = getattr(action, 'fcurves', None)
    if flat is not None:
        return list(flat)
    return [curve for layer in action.layers for strip in layer.strips
            for bag in getattr(strip, 'channelbags', ()) for curve in bag.fcurves]


# --- The wheels ------------------------------------------------------------

def build_wheel(materials, name, width):
    """One wheel: a tyre on a rim, with a brake turning inside it.

    Modelled with its hub at the origin and its axle along X, so the game mounts
    it under the transform pair it already builds for steering and rolling, and
    the same wheel goes on both sides of the car.

    The proportions are what make it read as a car's: a sidewall a third of the
    radius deep rather than a bicycle's hoop, a face of spokes reaching right
    out to the rim flange, and **something behind those spokes** -- the barrel
    the rim is pressed from and the brake disc inside it. Spokes with daylight
    behind them are the whole of why a wheel looks wrong.
    """
    rubber, trim = materials['hero:rubber'], materials['hero:trim']
    half = width / 2.0
    bead = WHEEL_RADIUS * BEAD_FRACTION          # where the tyre meets the rim
    tyre = smooth_by_angle(revolve(name + '_tyre', [
        (-half * 0.94, bead), (-half, bead * 1.10), (-half, WHEEL_RADIUS * 0.96),
        (-half * 0.74, WHEEL_RADIUS), (half * 0.74, WHEEL_RADIUS),
        (half, WHEEL_RADIUS * 0.96), (half, bead * 1.10), (half * 0.94, bead),
    ], rubber, segments=WHEEL_SEGMENTS), degrees=64.0)

    parts = []
    for side in (-1.0, 1.0):
        # The rim flange the tyre sits against, and the dish inside it.
        parts.append(revolve(name + '_flange%+d' % side, [
            (side * half * 0.94, bead), (side * half * 0.86, bead * 1.02),
            (side * half * 0.86, bead * 0.94),
        ], trim, segments=WHEEL_SEGMENTS))
    parts.append(disc(name + '_face', half * 0.86, bead * 0.94, trim,
                      segments=WHEEL_SEGMENTS, inner=bead * 0.80))
    for spoke in range(WHEEL_SPOKES):
        angle = 2.0 * math.pi * spoke / WHEEL_SPOKES
        parts.append(_spoke('%s_spoke%d' % (name, spoke), half * 0.86, angle,
                            bead * 0.86, trim))
    # The rim is joined into one object of its own rather than into the tyre:
    # joining them would paint the tyre in the rim's bright metal, and a grey
    # tyre is the first thing that looks wrong about a wheel.
    tyre.name = name
    rim = join(name + '_rim', parts, trim)
    parent_to([rim] + _wheel_innards(name, half, bead, materials), tyre)
    wheel = tyre

    # The centre cap, in the car's own accent colour, so a wheel turning is
    # something the eye can follow.
    cap = join(name + '_cap', [
        disc(name + '_cap_face', half * 0.90, bead * 0.26,
             materials['hero:caliper'], segments=WHEEL_SEGMENTS),
        revolve(name + '_cap_rim', [
            (half * 0.90, bead * 0.26), (half * 0.82, bead * 0.26),
        ], materials['hero:caliper'], segments=WHEEL_SEGMENTS),
    ], materials['hero:caliper'])
    return parent_to([cap], wheel)


def _wheel_innards(name, half, bead, materials):
    """What a wheel has behind its spokes: a barrel, a brake and a caliper.

    Spokes with nothing behind them show the sky through the wheel, and a wheel
    you can see through reads as a bicycle's. What fills it on a car is the
    barrel the rim is pressed from and the brake turning inside that -- and the
    caliper, because it is the one part of a wheel that is a different colour
    and the eye goes straight to it.
    """
    barrel = revolve(name + '_barrel', [
        (half * 0.88, bead * 0.97), (-half * 0.88, bead * 0.97),
    ], materials['hero:barrel'], segments=WHEEL_SEGMENTS)
    back = disc(name + '_back', -half * 0.88, bead * 0.97,
                materials['hero:barrel'], segments=WHEEL_SEGMENTS, inner=0.045)
    brake = revolve(name + '_brake', [
        (-half * 0.30, 0.055), (-half * 0.30, bead * 0.74),
        (-half * 0.10, bead * 0.74), (-half * 0.10, 0.055),
    ], materials['hero:brake'], segments=WHEEL_SEGMENTS)
    caliper = box(name + '_caliper', (-half * 0.42, -0.05, bead * 0.42),
                  (-half * 0.04, 0.05, bead * 0.88), materials['hero:caliper'])
    return [barrel, back, brake, caliper]


def _spoke(name, across, angle, radius, material, half_width=0.055):
    """One spoke of a wheel face: a tapered bar from the hub out to the rim."""
    hub, rim = 0.055, radius
    out = np.array([math.cos(angle), math.sin(angle)])
    side = np.array([-out[1], out[0]])
    verts = []
    # Into the wheel from the face it is on, so the spokes stand proud of the
    # barrel behind them rather than lying flat against it.
    for depth in (0.0, -math.copysign(0.05, across)):
        for along, wide in ((hub, half_width * 1.7), (rim, half_width * 0.80)):
            point = out * along
            verts += [(across + depth, *(point + side * wide)),
                      (across + depth, *(point - side * wide))]
    faces = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4),
             (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    return _finish(name, verts, faces, material)


# --- The traffic -----------------------------------------------------------

#: The five ordinary vehicles, in metres. ``belt`` is where the bodywork stops
#: and the windows start, ``cab`` the front and back of the cabin, ``roof`` the
#: ends of the roof panel over it, and ``wheel`` the radius of what it stands
#: on. The overall dimensions are ``glisteel.models``' own: what the table there
#: declares is what the player hits, so the two have to agree.
TRAFFIC_KINDS = (
    dict(name='saloon', length=4.60, width=1.80, height=1.45, floor=0.34,
         belt=0.86, cab=(1.05, -1.00), roof=(0.50, -0.80), wheel=0.31, bench=True),
    dict(name='hatchback', length=3.90, width=1.72, height=1.50, floor=0.36,
         belt=0.88, cab=(0.85, -1.32), roof=(0.30, -1.24), wheel=0.32, bench=True),
    dict(name='estate', length=4.80, width=1.80, height=1.55, floor=0.90 - 0.54,
         belt=0.90, cab=(1.05, -1.95), roof=(0.50, -1.95), wheel=0.32, bench=True),
    dict(name='van', length=5.20, width=1.95, height=2.15, floor=0.55,
         belt=1.28, cab=(2.25, 0.55), roof=(2.20, -2.40), wheel=0.36, bench=False),
    dict(name='pickup', length=5.40, width=1.90, height=1.80, floor=0.45,
         belt=1.10, cab=(1.85, -0.20), roof=(1.35, -0.15), wheel=0.38, bench=True),
)


def build_traffic(materials, kind):
    """One ordinary vehicle: boxy, painted, glazed, and with somebody in it.

    Nothing on it is styled. What a player needs from an oncoming vehicle is to
    know what it is at a glance and at a closing speed of two hundred, and five
    plain shapes do that where five interesting ones read as a car show.

    It stands on the road: the wheels touch z=0 and the roof is the height the
    table declares, so the game places one by putting its origin on the ground.
    """
    root = empty('traffic_%s' % kind['name'])
    parent_to([_traffic_body(materials, kind), _traffic_interior(materials, kind),
               _traffic_glass(materials, kind)], root)
    return root


def _traffic_body(materials, kind):
    """The bodywork: a hull, a roof over the cabin, bumpers and four wheels."""
    prefix = 'traffic_%s' % kind['name']
    paint, trim = materials['traffic:paint'], materials['traffic:trim']
    half_w, half_l = kind['width'] / 2.0, kind['length'] / 2.0
    floor, belt, height = kind['floor'], kind['belt'], kind['height']
    front, rear = kind['cab']
    roof_front, roof_rear = kind['roof']

    hull = loft(prefix + ':hull', [
        (half_l, ring(half_w * 0.90, floor + 0.06, belt - 0.10,
                      top_w=half_w * 0.84, tuck=0.90)),
        (half_l * 0.72, ring(half_w, floor, belt, top_w=half_w * 0.94, tuck=0.88)),
        (-half_l * 0.72, ring(half_w, floor, belt, top_w=half_w * 0.94, tuck=0.88)),
        (-half_l, ring(half_w * 0.90, floor + 0.04, belt - 0.06,
                       top_w=half_w * 0.86, tuck=0.90)),
    ], paint)

    # The roof, and the pillars holding it up. Everything between them is glass.
    parts = [hull,
             box(prefix + ':roof', (-half_w * 0.80, roof_front, height - 0.06),
                 (half_w * 0.80, roof_rear, height), paint)]
    for x in (-half_w * 0.80, half_w * 0.80):
        for y in (front, rear):
            parts.append(box(prefix + ':pillar%+.2f%+.2f' % (x, y),
                             (x - 0.05, y - 0.05, belt - 0.02),
                             (x + 0.05, y + 0.05, height - 0.04), paint))
    if kind['name'] == 'pickup':
        # An open bed with sides and a tailgate, which is the whole of what
        # makes a pickup one.
        for name, low, high in (
                ('bed_left', (-half_w * 0.96, rear, belt),
                 (-half_w * 0.82, -half_l + 0.06, belt + 0.32)),
                ('bed_right', (half_w * 0.82, rear, belt),
                 (half_w * 0.96, -half_l + 0.06, belt + 0.32)),
                ('tailgate', (-half_w * 0.96, -half_l + 0.14, belt),
                 (half_w * 0.96, -half_l + 0.06, belt + 0.30))):
            parts.append(box(prefix + ':' + name, low, high, paint))

    body = join(prefix + ':body', parts, paint)

    bumpers = join(prefix + ':body_trim', [
        box(prefix + ':bumper_front', (-half_w * 0.94, half_l, floor + 0.02),
            (half_w * 0.94, half_l - 0.14, floor + 0.26), trim),
        box(prefix + ':bumper_rear', (-half_w * 0.94, -half_l + 0.14, floor + 0.02),
            (half_w * 0.94, -half_l, floor + 0.26), trim),
    ], trim)
    return parent_to([bumpers, _traffic_wheels(materials, kind)], body)


def _traffic_wheels(materials, kind):
    """Four wheels, standing on the road and not turning.

    Nobody reads a traffic car's wheels at speed, so they are part of its
    bodywork rather than four more nodes the game has to follow.
    """
    prefix = 'traffic_%s' % kind['name']
    radius, half = kind['wheel'], TRAFFIC_TYRE_WIDTH / 2.0
    # Tucked far enough in that the widest thing on the vehicle is its
    # bodywork, which is what the table declares and what the collider is.
    across = kind['width'] / 2.0 - half - 0.02
    base = kind['length'] / 2.0 * 0.62
    parts = []
    for side in (-1.0, 1.0):
        for end in (-base, base):
            tyre = revolve('%s:wheel%+.2f%+.2f' % (prefix, side, end),
                           [(-half, radius * 0.62), (-half, radius),
                            (half, radius), (half, radius * 0.62)],
                           materials['traffic:rubber'], segments=TRAFFIC_SEGMENTS)
            tyre.location = (side * across, end, radius)
            parts.append(tyre)
    return join(prefix + ':wheels', parts, materials['traffic:rubber'])


def _traffic_glass(materials, kind):
    """The windows: a screen, a rear window and the sides between the pillars."""
    prefix = 'traffic_%s' % kind['name']
    glass = materials['traffic:glass']
    half_w = kind['width'] / 2.0
    belt, height = kind['belt'], kind['height']
    front, rear = kind['cab']
    roof_front, roof_rear = kind['roof']
    top = height - 0.06

    # Each screen spans from the bodywork to the roof, so the rake is whatever
    # the two ends make it and the opening is filled either way.
    screen = pane(prefix + ':screen', half_w * 0.74, (front, belt), (roof_front, top),
                  glass)
    back = pane(prefix + ':rearlight', half_w * 0.74, (rear, belt), (roof_rear, top),
                glass)
    sides = [box(prefix + ':side%+.2f' % x, (x - 0.015, front - 0.04, belt),
                 (x + 0.015, rear + 0.04, top), glass)
             for x in (-half_w * 0.78, half_w * 0.78)]
    return join(prefix + ':glass', [screen, back] + sides, glass)


def _traffic_interior(materials, kind):
    """Seats, headrests, a dash and a wheel: what a window shows of a driver."""
    prefix = 'traffic_%s' % kind['name']
    inside = materials['traffic:interior']
    half_w = kind['width'] / 2.0
    floor = kind['floor'] + 0.06
    front, rear = kind['cab']
    seat_y = front - 0.30
    parts = [box(prefix + ':cabin_floor', (-half_w * 0.76, front, floor - 0.04),
                 (half_w * 0.76, rear, floor), inside),
             box(prefix + ':dash', (-half_w * 0.76, front + 0.02, floor + 0.18),
                 (half_w * 0.76, front - 0.20, floor + 0.40), inside)]
    seats = [part for side in (-1.0, 1.0)
             for part in _seat(side * half_w * 0.42, seat_y, floor, inside,
                               '%s:seat%+d' % (prefix, side),
                               width=0.44, back=0.44, head=0.16)]
    if kind['bench']:
        seats.extend([
            box(prefix + ':bench', (-half_w * 0.80, seat_y - 0.60, floor),
                (half_w * 0.80, seat_y - 1.04, floor + 0.12), inside),
            box(prefix + ':bench_back', (-half_w * 0.80, seat_y - 1.00, floor + 0.02),
                (half_w * 0.80, seat_y - 1.14, floor + 0.46), inside),
            box(prefix + ':bench_head', (-half_w * 0.60, seat_y - 1.00, floor + 0.46),
                (half_w * 0.60, seat_y - 1.14, floor + 0.60), inside),
        ])
    column = empty(prefix + ':steering',
                   location=(-half_w * 0.42, front - 0.16, floor + 0.44),
                   rotation=(math.radians(64.0), 0.0, 0.0))
    parent_to([_traffic_rim(prefix, inside)], column, keep_place=False)
    return parent_to([join(prefix + ':interior_fittings', parts, inside),
                      join(prefix + ':seats', seats, inside), column],
                     empty(prefix + ':interior'))


def _traffic_rim(prefix, material, radius=0.17):
    """A plain wheel in front of the driver, which is what says which end is the front."""
    return join(prefix + ':steering_wheel', [
        revolve(prefix + ':rim_ring', [(-0.02, radius * 0.86), (-0.02, radius),
                                       (0.02, radius), (0.02, radius * 0.86)],
                material, segments=10),
        box(prefix + ':rim_hub', (-0.05, -0.05, -0.015), (0.05, 0.05, 0.015), material),
    ], material)


def build_preview(materials):
    """The car with its wheels on, which is the only way to judge the shape.

    The game mounts the wheels itself, from their own files and at the
    positions the physics gives them, so nothing else assembles the car whole.
    This does, at those same positions, for looking at.
    """
    root = empty('preview')
    parts = [build_hero(materials)]
    for front in (True, False):
        for side in (-1.0, 1.0):
            wheel = build_wheel(
                materials, 'preview:wheel_%s%+d' % ('front' if front else 'rear', side),
                TYRE_WIDTH_FRONT if front else TYRE_WIDTH_REAR)
            wheel.location = (side * TRACK / 2.0,
                              (WHEELBASE / 2.0) * (1.0 if front else -1.0),
                              FLOOR + RIDE_HEIGHT)
            parts.append(wheel)
    return parent_to(parts, root)


# --- Output ----------------------------------------------------------------

@contextmanager
def canonical_names(root):
    """Give one asset's objects and materials the names the game asks for.

    Everything is built under a ``family:`` prefix so that seven vehicles can
    share one file without Blender renaming the second ``body`` it is given.
    What a ``.glb`` carries is the name without the prefix, which is what
    ``glisteel.models`` looks for.
    """
    blocks = [root] + list(root.children_recursive)
    for obj in list(blocks):
        for material in (getattr(obj.data, 'materials', None) or []):
            if material is not None and material not in blocks:
                blocks.append(material)
    saved = [(block, block.name) for block in blocks]
    try:
        for block, name in saved:
            if ':' in name:
                block.name = name.split(':', 1)[1]
        yield
    finally:
        for block, name in saved:
            block.name = name


def export_glb(root, path):
    """Write one asset to glTF, at its own origin.

    The asset is modelled facing where glTF wants it, so nothing is turned on
    the way out: what moves is only the display placement that spreads the fleet
    across the ``.blend``.
    """
    layer = bpy.context.view_layer
    for other in layer.objects:
        other.select_set(False)
    placement = root.location.copy()
    root.location = (0.0, 0.0, 0.0)
    root.select_set(True)
    for child in root.children_recursive:
        child.select_set(True)
    layer.objects.active = root
    layer.update()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with canonical_names(root):
        bpy.ops.export_scene.gltf(
            filepath=path, export_format='GLB', use_selection=True,
            export_apply=True, export_yup=True, export_animations=True,
            export_cameras=False, export_lights=False)
    root.location = placement
    for other in layer.objects:
        other.select_set(False)


def glb_document(path):
    """The JSON half of a ``.glb``, as a dict."""
    with open(path, 'rb') as handle:
        data = handle.read()
    length, _kind = struct.unpack('<II', data[12:20])
    return json.loads(data[20:20 + length])


def patch_glb(path, mutate):
    """Rewrite a ``.glb``'s JSON through ``mutate``; returns whether it changed."""
    with open(path, 'rb') as handle:
        data = handle.read()
    chunks, offset = [], 12
    while offset < len(data):
        length, kind = struct.unpack('<II', data[offset:offset + 8])
        chunks.append([kind, data[offset + 8:offset + 8 + length]])
        offset += 8 + length
    document = json.loads(chunks[0][1])
    if not mutate(document):
        return False
    chunks[0][1] = json.dumps(document, separators=(',', ':')).encode('utf-8')
    # Every chunk starts on a four-byte boundary and the pad is part of the
    # chunk: JSON pads with spaces so it stays parseable, binary with zeros so
    # it stays a valid tail of whatever accessor ends there.
    body = b''
    for kind, payload in chunks:
        payload += (b'\x20' if kind == 0x4E4F534A else b'\x00') * (-len(payload) % 4)
        body += struct.pack('<II', len(payload), kind) + payload
    with open(path, 'wb') as handle:
        handle.write(struct.pack('<4sII', b'glTF', 2, 12 + len(body)) + body)
    return True


def coat_roughness(path, materials, roughness=COAT_ROUGHNESS):
    """Give the named materials' clear coat its roughness in a written file.

    ``KHR_materials_clearcoat`` carries a weight and a roughness, and Blender
    writes only the weight: a coat exported from it is left at the extension's
    default of zero, which is a mirror rather than a lacquer. So the roughness
    is put in here, the same way the canopy's volume and the clip's name are.
    """
    def apply(document):
        touched = False
        for entry in document.get('materials', []):
            if entry.get('name') not in materials:
                continue
            coat = (entry.get('extensions') or {}).get('KHR_materials_clearcoat')
            if coat is not None and 'clearcoatRoughnessFactor' not in coat:
                coat['clearcoatRoughnessFactor'] = float(roughness)
                touched = True
        return touched
    return patch_glb(path, apply)


def name_the_clip(path, wanted='steer'):
    """Make sure the one animation in a file carries the name the game asks for.

    Blender names an exported animation after the action it came from, and
    decorates that name in some export modes. The game looks the clip up by
    name, so the name is worth pinning rather than hoping for.
    """
    def rename(document):
        animations = document.get('animations') or []
        if len(animations) != 1 or animations[0].get('name') == wanted:
            return False
        animations[0]['name'] = wanted
        return True
    return patch_glb(path, rename)


def triangles(root):
    """How many triangles an asset costs, counting quads as the two they are."""
    total = 0
    for obj in [root] + list(root.children_recursive):
        mesh = getattr(obj, 'data', None)
        for polygon in (getattr(mesh, 'polygons', None) or ()):
            total += max(len(polygon.vertices) - 2, 0)
    return total


# --- What gets built -------------------------------------------------------

def _assets():
    """Every asset this script writes: its name, its file, and how to build it."""
    made = [
        ('hero', 'hero.glb', build_hero),
        ('hero-wheel-front', 'hero-wheel-front.glb',
         lambda materials: build_wheel(materials, 'hero:wheel_front',
                                       TYRE_WIDTH_FRONT)),
        ('hero-wheel-rear', 'hero-wheel-rear.glb',
         lambda materials: build_wheel(materials, 'hero:wheel_rear',
                                       TYRE_WIDTH_REAR)),
    ]
    for kind in TRAFFIC_KINDS:
        made.append((kind['name'], 'traffic/%s.glb' % kind['name'],
                     lambda materials, kind=kind: build_traffic(materials, kind)))
    return made


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output-dir', default=BLEND_DIR,
                        help='where the .blend is written (default: %s)' % BLEND_DIR)
    parser.add_argument('--asset-dir', default=ASSET_DIR,
                        help='where the .glb files go, which defaults to the '
                             'game\'s own assets so that building a model and '
                             'updating the game\'s copy of it are one step')
    parser.add_argument('--name', default='cars', help='base name for the .blend')
    parser.add_argument('--only', action='append', metavar='NAME', default=None,
                        help='build and export only assets whose name contains '
                             'this (repeatable). The .blend is left alone by '
                             'such a run, since it would hold only what was '
                             'built')
    parser.add_argument('--no-export', action='store_true',
                        help='write the .blend and no .glb files')
    parser.add_argument('--paint-maps', default=PAINT_MAPS, metavar='DIR',
                        help='the CC0 finish the paint is built on, as '
                             'OpenGLContext.loaders.cc0 leaves it on disk '
                             '(default: %(default)s). Without it the car is '
                             'painted in flat colour')
    parser.add_argument('--preview', metavar='GLB', default=None,
                        help='also write the car with its wheels on to this '
                             'path, for looking at the shape whole')
    options = parser.parse_args(argv if argv is not None else _script_args())

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.length_unit = 'METERS'
    paint = paint_maps(options.paint_maps)
    if paint is None:
        print('no CC0 paint maps under %s: painting flat'
              % (options.paint_maps,))
    materials = build_materials(paint)

    wanted = [asset for asset in _assets()
              if not options.only
              or any(part.lower() in asset[0].lower() for part in options.only)]
    if not wanted:
        parser.error('--only matched none of: %s'
                     % ', '.join(name for name, _file, _build in _assets()))

    built = []
    for index, (name, relative, build) in enumerate(wanted):
        root = build(materials)
        # Spread out along X so the .blend opens with the fleet in view rather
        # than with everything in a heap at the origin. Each is put back on its
        # own origin before it is exported.
        root.location = (index * 6.0 - 12.0, 0.0, 0.0)
        built.append((name, relative, root))

    blend_dir = os.path.abspath(options.output_dir)
    os.makedirs(blend_dir, exist_ok=True)
    blend = os.path.join(blend_dir, '%s.blend' % options.name)
    if options.only:
        # A run that builds one vehicle has only that vehicle in it, and saving
        # would leave the file for editing holding one vehicle too.
        print('not writing %s: --only built %s of %d assets'
              % (blend, len(wanted), len(_assets())))
    else:
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        print('wrote %s' % blend)

    if options.no_export:
        return
    if options.preview:
        preview = os.path.abspath(options.preview)
        export_glb(build_preview(materials), preview)
        print('wrote %s' % preview)
    for _name, relative, root in built:
        path = os.path.join(os.path.abspath(options.asset_dir), relative)
        export_glb(root, path)
        name_the_clip(path)
        coat_roughness(path, ('paint',))
        print('wrote %-34s %6d triangles  %6.1f kB'
              % (path, triangles(root), os.path.getsize(path) / 1024.0))


def _script_args():
    """Arguments after ``--`` when this is run through ``blender --python``."""
    return sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]


if __name__ == '__main__':
    main()
