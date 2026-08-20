# -*- mode: python ; coding: utf-8 -*-
"""Freeze GLinting Steel into one directory that needs no Python installed

    pyinstaller packaging/glisteel.spec

The result is ``dist/glisteel/``: the executables named in ``packaging/entry.py``
beside an ``_internal`` directory holding Python, the engine, the game and the
libraries under them. Zip that directory and it runs on a machine with a
graphics driver and nothing else.

Almost nothing about the engine is described here. PyOpenGL and OpenGLContext
carry their own PyInstaller hooks -- for the plug-in registries, the generated
resource modules, the shader sources and the GLFW library -- which PyInstaller
finds through their ``pyinstaller40`` entry points. What is left for a game to
say is which commands it offers, which of its own files it opens at run time,
and which backends it does not use.
"""

import os
import runpy

from PyInstaller.utils.hooks import collect_data_files

from OpenGLContext import packaging

PROJECT = os.path.dirname(SPECPATH)  # noqa: F821 -- PyInstaller defines SPECPATH
ENTRY = os.path.join(SPECPATH, 'entry.py')  # noqa: F821

# The entry script is read rather than imported: it declares the commands, and
# `runpy` leaves its `__main__` guard alone, so the table is not copied here to
# fall out of step with the one the bundle actually dispatches on.
DECLARED = runpy.run_path(ENTRY)

analysis = Analysis(  # noqa: F821
    [ENTRY],
    pathex=[PROJECT],
    # The cars: glTF beside the package, opened by path (`glisteel.models`).
    datas=collect_data_files('glisteel'),
    hiddenimports=DECLARED['MODULES'],
    # The game opens its window with GLFW. The engine registers every backend
    # it knows and imports the Qt one for its registration side effect, so
    # without this a bundle carries the whole of Qt -- a quarter of a gigabyte
    # against a game that never calls it. The engine's own backend modules stay:
    # they are kilobytes, and they report themselves unavailable.
    excludes=packaging.unused_backend_modules(keep=['glfw']) + [
        # Development tooling that some library or other imports conditionally.
        'IPython',
        'matplotlib',
        'pytest',
        'tkinter',
    ],
    noarchive=False,
)
pyz = PYZ(analysis.pure)  # noqa: F821

# One executable per command, all sharing the single `_internal` directory that
# COLLECT assembles. Console applications: both commands are driven by their
# arguments and report what they are doing, and a windowed build on Windows
# would drop `--help` and every error message on the floor.
executables = [
    EXE(  # noqa: F821
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        console=True,
        debug=False,
        strip=False,
        # UPX shrinks a bundle by a third and has a long history of producing
        # one that a virus scanner quarantines or that will not start at all.
        upx=False,
    )
    for name in sorted(DECLARED['COMMANDS'])
]

COLLECT(  # noqa: F821
    *executables,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name='glisteel',
)
