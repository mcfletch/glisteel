"""What the source files themselves have to be true of.

One thing, checked over every module the project ships: **no name is defined
twice at the top of a file**. Python binds module-level names in order, so a
second ``def`` of a name silently replaces the first -- the earlier one becomes
unreachable, and every call that looks like it goes there goes somewhere else.
Nothing raises, no test fails, and the geometry a maintainer tunes is geometry
nobody draws.

Ruff's ``F811`` does not catch the case that matters: it fires on redefinition
of an *unused* name, and a name referenced between the two definitions is used.
"""
import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = sorted([*(ROOT / 'glisteel').glob('*.py'),
                  *(ROOT / 'tools').glob('*.py')])


def _redefined(path):
    """Every top-level name this module binds to a def or a class twice."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    seen, twice = {}, {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        if node.name in seen:
            twice.setdefault(node.name, [seen[node.name]]).append(node.lineno)
        seen[node.name] = node.lineno
    return twice


@pytest.mark.parametrize('path', SOURCES, ids=lambda one: one.name)
class TestNothingIsDefinedTwice:
    def test_no_function_or_class_is_defined_twice(self, path) -> None:
        found = _redefined(path)
        assert not found, '\n'.join(
            '%s defines %s at lines %s -- the earlier one is unreachable'
            % (path.name, name, ' and '.join(str(one) for one in lines))
            for name, lines in sorted(found.items()))


def test_there_are_sources_to_check() -> None:
    # A glob that matched nothing would make every case above vacuous.
    assert len(SOURCES) > 20
