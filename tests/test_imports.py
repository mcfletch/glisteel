"""Where a module says what it depends on.

The import block at the head of a file is how a reader finds out what a module
needs, and an import inside a function hides that. Inside a function that runs
every frame it also costs a dictionary lookup and a name binding per call, for
no benefit at all.

Some are necessary: :mod:`glisteel.game` sets the ``OPENGLCONTEXT_*``
environment the engine reads at import time, and a handful break a genuine
import cycle. Those carry a comment saying so, on the line, which is what this
asks for.
"""
import ast
import pathlib

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / 'glisteel'
MODULES = sorted(PACKAGE.glob('*.py'))

#: Functions that run once a frame or oftener. An import in one of these is a
#: cost paid at the frame rate.
PER_FRAME = {
    ('world.py', 'ground_under'), ('world.py', 'view_projection'),
    ('reflections.py', '_register'), ('reflections.py', 'update'),
    ('game.py', '_aim'), ('game.py', '_move_the_lights'),
    ('session.py', 'advance'), ('session.py', '_stream'),
    ('traffic.py', 'update'), ('traffic.py', '_follow'),
    ('car.py', 'follow'), ('driver.py', 'update'), ('driver.py', 'steering'),
}


def _local_imports(path):
    """Every import inside a function, as (function, line, is it explained)."""
    source = path.read_text(encoding='utf-8')
    lines = source.splitlines()
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, (ast.Import, ast.ImportFrom)):
                near = ' '.join(lines[max(inner.lineno - 3, 0):inner.lineno + 1])
                explained = any(word in near.lower() for word in
                                ('cycle', 'circular', 'environment', 'optional',
                                 'only when', 'lazily', 'import time'))
                found.append((node.name, inner.lineno, explained))
    return found


@pytest.mark.parametrize('path', MODULES, ids=lambda one: one.name)
def test_nothing_is_imported_inside_a_per_frame_function(path) -> None:
    offenders = [(name, line) for name, line, _ in _local_imports(path)
                 if (path.name, name) in PER_FRAME]
    assert not offenders, '\n'.join(
        '%s:%d imports inside %s(), which runs every frame'
        % (path.name, line, name) for name, line in offenders)
