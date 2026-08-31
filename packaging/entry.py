#! /usr/bin/env python
"""What a frozen GLinting Steel bundle runs

The bundle holds the game and the baker that makes a world for it to drive, in
one directory with one copy of the engine, Python and the libraries beneath
them. Each command is an executable of its own beside that directory and is
recognised by the name it was run under -- see
:mod:`OpenGLContext.packaging.multicall`.

The baker travels with the game deliberately: a world is baked rather than
shipped (they are hundreds of megabytes, and the one worth driving is the one
you made), so a game delivered without it would open on an empty track list and
name a command that is nowhere on the machine.
"""

import sys

from OpenGLContext.packaging.multicall import command_modules, run

#: Executable name -> the ``module:attribute`` it runs. ``packaging/glisteel.spec``
#: builds one executable per key and hands ``command_modules(COMMANDS)`` to
#: PyInstaller, so this table is the only place a command is declared.
COMMANDS = {
    'glisteel': 'glisteel.game:main',
    'glisteel-bake': 'glisteel_editor.bake:main',
}

#: The modules to tell a freezer about, since the table above names them as
#: strings. Read from the ``.spec``.
MODULES = command_modules(COMMANDS)

if __name__ == '__main__':
    sys.exit(run(COMMANDS))
