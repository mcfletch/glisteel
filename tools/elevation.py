"""Orthographic elevations of a model, rasterised straight from its triangles.

A perspective render flatters and distorts a silhouette, and a shape judged
from one is a shape tuned by guesswork. This draws the true outline -- side,
front or top -- with a half-metre grid and the road line, so a profile can be
read against the numbers it was built from.

    python tools/elevation.py glisteel/assets/cars/hero.glb /tmp/side.png side

Colours follow the material names the vehicles use, so paint, glass, trim and
rubber can be told apart. Anything else is drawn grey.
"""
import sys

import numpy as np
from OpenGLContext.capture import save_png
from OpenGLContext.loaders.assets import bounds
from OpenGLContext.loaders.gltf import load_gltf
from OpenGLContext.loaders.gltf.transforms import _local_matrix_rv


def main(argv: list[str] | None = None) -> None:
    """Draw one elevation of a model, as the command line asked."""

    wanted = list(sys.argv[1:] if argv is None else argv)
    if len(wanted) < 2:
        raise SystemExit(
            'usage: elevation.py MODEL.glb OUT.png [side|front|top]')
    PATH, OUT = wanted[0], wanted[1]
    VIEW = wanted[2] if len(wanted) > 2 else 'side'
    SCALE = 220                       # pixels per metre
    ROAD = -0.50                      # where the road is, relative to the body centre

    scene = load_gltf(PATH)
    axes = {'side': (2, 1), 'front': (0, 1), 'top': (2, 0)}[VIEW]
    #: The axis the view looks along, and which way is towards the viewer.
    DEPTH = {'side': (0, 1.0), 'front': (2, -1.0), 'top': (1, 1.0)}[VIEW]
    groups = []


    def collect(node, matrix):
        """Every triangle in world space: a wheel is where its node puts it."""
        world = (_local_matrix_rv(node) @ matrix
                 if getattr(node, 'translation', None) is not None else matrix)
        geometry = getattr(node, 'geometry', None)
        points = getattr(geometry, 'positions', None)
        if points is not None and len(points):
            local = np.asarray(points, dtype='d').reshape(-1, 3)
            placed = (np.column_stack([local, np.ones(len(local))]) @ world)[:, :3]
            index = np.asarray(geometry.indices, dtype=np.int64).reshape(-1, 3)
            material = getattr(getattr(node.appearance, 'material', None), 'DEF', '')
            groups.append((material, placed[:, axes], index, placed[:, DEPTH[0]]))
        for child in (getattr(node, 'children', None) or ()):
            collect(child, world)


    collect(scene.group, np.eye(4))

    low, high = bounds(scene.group)
    u0, u1 = low[axes[0]] - 0.15, high[axes[0]] + 0.15
    v0, v1 = min(low[axes[1]], ROAD) - 0.15, high[axes[1]] + 0.15
    width, height = int((u1 - u0) * SCALE), int((v1 - v0) * SCALE)
    image = np.full((height, width, 3), 250, dtype=np.uint8)

    #: Roughly what each material looks like, so parts can be told apart in an
    #: elevation. Anything not named here is drawn mid-grey.
    SHADE = {'glass': (150, 185, 205), 'paint': (120, 125, 135),
             'accent': (58, 59, 62), 'dark': (38, 39, 42),
             'trim': (200, 200, 205), 'rubber': (60, 60, 65),
             'interior': (95, 95, 100), 'lights': (240, 235, 180),
             'tail': (180, 40, 45)}


    def fill(triangle, colour):
        """Rasterise one triangle, flat."""
        xs, ys = triangle[:, 0], triangle[:, 1]
        x0, x1 = int(np.floor(xs.min())), int(np.ceil(xs.max()))
        y0, y1 = int(np.floor(ys.min())), int(np.ceil(ys.max()))
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[max(y0, 0):min(y1, height), max(x0, 0):min(x1, width)]
        if not yy.size:
            return
        (ax, ay), (bx, by), (cx, cy) = triangle
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-9:
            return
        w0 = ((bx - ax) * (yy - ay) - (by - ay) * (xx - ax)) / area
        w1 = ((cx - bx) * (yy - by) - (cy - by) * (xx - bx)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        image[yy[inside], xx[inside]] = colour


    # Painter's order: the far side of the model first, so what the viewer would
    # actually see is what survives. Without it the interior paints over the glass
    # it is behind.
    faces = []
    for material, points, index, depth in groups:
        colour = SHADE.get(material, (140, 140, 145))
        screen = np.empty_like(points)
        screen[:, 0] = (points[:, 0] - u0) * SCALE
        screen[:, 1] = height - (points[:, 1] - v0) * SCALE
        for triangle, away in zip(screen[index], depth[index].mean(axis=1), strict=True):
            faces.append((away * DEPTH[1], triangle, colour))
    faces.sort(key=lambda face: face[0])
    for _away, triangle, colour in faces:
        fill(triangle, colour)

    # A metre grid, and the road the car stands on.
    for metre in np.arange(np.ceil(u0), u1, 0.5):
        column = int((metre - u0) * SCALE)
        if 0 <= column < width:
            image[:, column] = np.minimum(image[:, column], 215)
    for metre in np.arange(np.ceil(v0 * 2) / 2, v1, 0.5):
        row = height - int((metre - v0) * SCALE)
        if 0 <= row < height:
            image[row, :] = np.minimum(image[row, :], 215)
    road = height - int((ROAD - v0) * SCALE)
    if 0 <= road < height:
        image[road - 1:road + 2, :] = (40, 40, 40)

    save_png(OUT, image)
    print('wrote %s  (%d x %d, %.0f px/m)' % (OUT, width, height, SCALE))


if __name__ == '__main__':
    main()
