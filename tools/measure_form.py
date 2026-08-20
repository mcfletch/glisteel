"""Measure a car's proportions and print them as a section table.

Run against a reference model, it reports where that car is wide, where its
flanks and its top surface sit, where its floor is, and where its wheels and
greenhouse are -- scaled to the length our own physics uses, and printed in the
form :func:`~tools.cars.car_section` takes.

    python tools/measure_form.py reference.glb

**Only proportions cross.** The output is a table of numbers describing a
shape; no geometry, material or texture of the model measured is read into
anything this project ships. That is what makes it safe to take the form of a
car whose licence would otherwise travel with its mesh -- see the provenance
note in ``plans/CAR-MODELS.md``.
"""
import sys

import numpy as np
from OpenGLContext.loaders.assets import bounds
from OpenGLContext.loaders.gltf import load_gltf
from OpenGLContext.loaders.gltf.transforms import _local_matrix_rv


def main(argv: list[str] | None = None) -> None:
    """Measure the donor named on the command line, and print the table."""
    wanted = list(sys.argv[1:] if argv is None else argv)
    DONOR = wanted[0] if wanted else 'reference.glb'
    GLASS = ('No see Glass', 'No see Glass.001')
    TYRE = ('Tire',)
    OUR_LENGTH = 4.20                     # BODY_LENGTH
    ROAD = -0.50                          # where the road is in our body space
    STATIONS = 22

    scene = load_gltf(DONOR)
    wanted = {id(scene.materials[name]): kind
              for names, kind in ((GLASS, 'glass'), (TYRE, 'tyre'))
              for name in names if name in scene.materials}
    parts = {'body': [], 'glass': [], 'tyre': []}


    def collect(node, matrix):
        world = (_local_matrix_rv(node) @ matrix
                 if getattr(node, 'translation', None) is not None else matrix)
        geometry = getattr(node, 'geometry', None)
        points = getattr(geometry, 'positions', None)
        if points is not None and len(points):
            local = np.asarray(points, dtype='d').reshape(-1, 3)
            placed = (np.column_stack([local, np.ones(len(local))]) @ world)[:, :3]
            material = getattr(node.appearance, 'material', None)
            parts[wanted.get(id(material), 'body')].append(placed)
        for child in (getattr(node, 'children', None) or ()):
            collect(child, world)


    collect(scene.group, np.eye(4))
    for key in parts:
        parts[key] = np.vstack(parts[key]) if parts[key] else np.zeros((0, 3))
    low, high = bounds(scene.group)
    donor_length = high[2] - low[2]
    scale = OUR_LENGTH / donor_length
    nose = high[2]                        # the donor's nose is at its greatest z


    def to_ours(points):
        """Donor space to ours: nose at +Y, the floor on the road, our length."""
        out = np.empty_like(points)
        out[:, 0] = points[:, 0] * scale                  # across
        out[:, 1] = OUR_LENGTH / 2.0 - (nose - points[:, 2]) * scale     # along, +Y forward
        out[:, 2] = (points[:, 1] - low[1]) * scale + ROAD              # height
        return out


    body, glass, tyre = (to_ours(parts[key]) for key in ('body', 'glass', 'tyre'))
    print('# donor scaled by %.4f: %.2f long, %.2f wide, %.2f tall'
          % (scale, OUR_LENGTH, (high[0] - low[0]) * scale, (high[1] - low[1]) * scale))

    if len(tyre):
        across = np.abs(tyre[:, 0])
        middle_y = (tyre[:, 1].min() + tyre[:, 1].max()) / 2.0
        front = tyre[tyre[:, 1] > middle_y]
        back = tyre[tyre[:, 1] <= middle_y]
        radius = (tyre[:, 2].max() - tyre[:, 2].min()) / 2.0
        print('# wheels: track %.3f, wheelbase %.3f, radius %.3f, width %.3f'
              % (across.max() + across[across > 0].min(),
                 front[:, 1].mean() - back[:, 1].mean(), radius,
                 (across.max() - across[across > 0].min())))
    if len(glass):
        print('# greenhouse: y %.2f .. %.2f, top %.3f'
              % (glass[:, 1].min(), glass[:, 1].max(), glass[:, 2].max()))

    print('# %8s %8s %8s %8s %8s' % ('y', 'half_w', 'floor', 'arch', 'crest'))
    edges = np.linspace(body[:, 1].min(), body[:, 1].max(), STATIONS + 1)
    for start, stop in zip(edges[:-1], edges[1:], strict=True):
        slab = body[(body[:, 1] >= start) & (body[:, 1] < stop)]
        if len(slab) < 8:
            continue
        half = np.abs(slab[:, 0]).max()
        middle = slab[np.abs(slab[:, 0]) < half * 0.30]
        flank = slab[np.abs(slab[:, 0]) > half * 0.74]
        print('  %8.2f %8.3f %8.3f %8.3f %8.3f'
              % ((start + stop) / 2.0, half, slab[:, 2].min(),
                 flank[:, 2].max() if len(flank) else slab[:, 2].max(),
                 middle[:, 2].max() if len(middle) else slab[:, 2].max()))

    # --- the tables, in the form cars.py takes -----------------------------------
    LIFT = 0.07                # so the measured floor lands on our own FLOOR
    BELT = 0.31                # where our bodywork stops and the canopy starts
    CABIN = (-0.90, 1.28)      # the greenhouse, from the measurement above
    print()
    print('BODY = (')
    rows = []
    for start, stop in zip(edges[:-1], edges[1:], strict=True):
        slab = body[(body[:, 1] >= start) & (body[:, 1] < stop)]
        if len(slab) < 8:
            continue
        y = (start + stop) / 2.0
        half = np.abs(slab[:, 0]).max()
        half = min(half, 0.92)                       # the mirrors are not the body
        middle = slab[np.abs(slab[:, 0]) < half * 0.30]
        flank = slab[np.abs(slab[:, 0]) > half * 0.74]
        floor = slab[:, 2].min() + LIFT
        arch = (flank[:, 2].max() if len(flank) else slab[:, 2].max()) + LIFT
        crest = (middle[:, 2].max() if len(middle) else slab[:, 2].max()) + LIFT
        rows.append((y, half, floor, arch, crest))
    rows.sort(key=lambda row: -row[0])
    for y, half, floor, arch, crest in rows:
        inside = CABIN[0] <= y <= CABIN[1]
        body_crest = min(crest, BELT) if inside else crest
        body_arch = min(arch, max(body_crest, BELT)) if inside else arch
        print('    (%6.2f, car_section(%.3f, %+.3f, %+.3f, %+.3f, %.2f)),'
              % (y, half, floor, body_arch, body_crest, half * 0.74))
    print(')')
    print()
    print('GLASS = (')
    for y, half, _floor, _arch, crest in rows:
        if not CABIN[0] <= y <= CABIN[1]:
            continue
        print('    (%6.2f, car_section(%.3f, %+.3f, %+.3f, %+.3f, %.2f)),'
              % (y, half * 0.86, BELT - 0.02, max(crest - 0.03, BELT), crest,
                 half * 0.72))
    print(')')


if __name__ == '__main__':
    main()
