#!/usr/bin/env python
"""Catch undefined global names in the pipeline before a 16-minute run does.

    python scripts/check_pipeline_names.py

WHY THIS EXISTS. `pipeline/` had no Python linting of any kind, and its only
real test is the validator -- which needs a complete pipeline run to say
anything. So this happened, 2026-08-23:

    NameError: name 'TEX_HIST_TOLERANCE_HOURS' is not defined

A config constant was used in a log message in `cli.py` but never added to that
module's `from .config import (...)` list. The line sat on a branch that only
runs when a timeline slot has no usable source image, so it did not fire on the
happy path -- and when it did fire it killed the texture stage AFTER four minutes
of reprojection work, rolled the product back, and published nothing. Twice,
because the first time the failure was read past.

`pyflakes` would have found it in milliseconds. It is not installed and neither
is anything like it, and this check needs no third-party package: Python's own
`symtable` already knows, for every name in every scope, whether that scope
binds it or expects to find it in the module globals. Any name a function
expects globally and the module does not actually have is this bug.

WHAT IT WILL AND WILL NOT CATCH. It resolves module-global lookups only. It does
not type-check, does not follow attributes (`config.FOO` is not checked), and
deliberately says nothing about locals -- `symtable` has already proved those are
bound. `from x import *` in a checked module would make it blind to that
module's names; the pipeline uses no star imports, and adding one should be
treated as breaking this check.
"""

from __future__ import annotations

import builtins
import importlib
import pathlib
import symtable
import sys

# Names Python injects into a module namespace that symtable still reports as
# global lookups.
_IMPLICIT = {
    "__name__", "__file__", "__doc__", "__package__", "__spec__",
    "__loader__", "__builtins__", "__annotations__", "__dict__",
}


def _globals_expected(table: symtable.SymbolTable, out: set) -> None:
    """Collect every name this scope expects to find in the module globals."""
    for sym in table.get_symbols():
        # is_global() covers both an explicit `global` statement and the far
        # more common case: a free name with no binding in any enclosing
        # function scope, which Python resolves against module globals.
        if sym.is_referenced() and sym.is_global() and not sym.is_assigned():
            out.add(sym.get_name())
    for child in table.get_children():
        _globals_expected(child, out)


def check_module(path: pathlib.Path, module_name: str) -> list:
    """Return a list of (name,) problems for one module."""
    source = path.read_text(encoding="utf-8")
    top = symtable.symtable(source, str(path), "exec")

    expected: set = set()
    # The module scope itself is skipped: a name used at module level before it
    # is bound is a straightforward runtime error that any import already
    # surfaces. What hides is names used INSIDE functions.
    for child in top.get_children():
        _globals_expected(child, expected)

    # Importing is what gives us the real namespace, including everything the
    # module pulled in via `from .config import (...)`. It is also a free
    # import-time smoke test.
    module = importlib.import_module(module_name)
    have = set(vars(module)) | set(dir(builtins)) | _IMPLICIT

    return sorted(n for n in expected if n not in have)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    files = sorted((root / "pipeline").rglob("*.py"))
    if not files:
        print("no pipeline modules found -- run me from the repo", file=sys.stderr)
        return 2

    failures = 0
    checked = 0
    for path in files:
        rel = path.relative_to(root)
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module_name = ".".join(parts)
        try:
            missing = check_module(path, module_name)
        except Exception as exc:                              # noqa: BLE001
            print("  ERROR {0}: {1}: {2}".format(rel, type(exc).__name__, exc))
            failures += 1
            continue
        checked += 1
        for name in missing:
            print("  UNDEFINED {0}: {1}".format(rel, name))
            failures += 1

    print("{0} module(s) checked, {1} problem(s)".format(checked, failures))
    if failures:
        print("A name used inside a function is not in that module's globals. "
              "Usually a missing entry in `from .config import (...)`.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
