"""Structural guard: prevent ``await run_javascript()`` in production code.

``await ui.run_javascript(...)`` blocks the Python asyncio event loop while
waiting for the browser round-trip.  All call sites must use fire-and-forget
(bare ``run_javascript`` without ``await``) or ``background_tasks.create``.

See ``docs/design-plans/2026-03-29-eliminate-js-await-454.md``.

The guard uses Python's ``ast`` module to walk source files and flag any
``await`` whose inner expression is a call to ``run_javascript`` in any
form (``ui.run_javascript``, ``client.run_javascript``, bare
``run_javascript``).
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_DIR = Path("src/promptgrimoire")

# Spike/demo pages excluded from scanning.  Add the filename stem here
# (not the full path) with a comment explaining why.
_ALLOWLIST: set[str] = {
    "milkdown_spike",
    "text_selection",
    "highlight_api_demo",
}


def _find_await_run_javascript(
    source: str,
    filename: str = "<string>",
) -> list[tuple[str, int, str]]:
    """Find ``await ...run_javascript(...)`` calls in *source*.

    Returns a list of ``(filename, lineno, expression)`` tuples for each
    violation found.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    violations: list[tuple[str, int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue

        call = node.value
        if not isinstance(call, ast.Call):
            continue

        func = call.func
        # bare run_javascript(...)
        if isinstance(func, ast.Name) and func.id == "run_javascript":
            violations.append((filename, node.lineno, "await run_javascript(...)"))
            continue

        # any.run_javascript(...) — covers ui.run_javascript,
        # client.run_javascript, presence.nicegui_client.run_javascript, etc.
        if isinstance(func, ast.Attribute) and func.attr == "run_javascript":
            violations.append((filename, node.lineno, "await ...run_javascript(...)"))

    return violations


def test_no_await_run_javascript_in_production() -> None:
    """No production file may ``await run_javascript()``.

    These calls block the asyncio event loop while waiting for a browser
    round-trip.  Use fire-and-forget or ``background_tasks.create``.

    If this test fails, either:
    1. Remove the ``await`` (preferred — fire-and-forget), or
    2. Add the file's stem to ``_ALLOWLIST`` with a comment explaining
       why it's acceptable (spike/demo only).
    """
    all_violations: list[str] = []

    for py_file in sorted(_SRC_DIR.rglob("*.py")):
        if py_file.stem in _ALLOWLIST:
            continue

        source = py_file.read_text()
        violations = _find_await_run_javascript(source, filename=str(py_file))

        for filepath, lineno, expr in violations:
            all_violations.append(f"  {filepath}:{lineno} — {expr}")

    if all_violations:
        count = len(all_violations)
        msg = (
            f"Found {count} `await ...run_javascript()` call(s) in production code.\n"
            "These block the asyncio event loop. "
            "See docs/design-plans/2026-03-29-eliminate-js-await-454.md.\n\n"
            "Violations:\n"
            + "\n".join(all_violations)
            + "\n\nIf this is a spike/demo page, "
            "add its stem to _ALLOWLIST in this test."
        )
        raise AssertionError(msg)


def test_allowlist_exact_set() -> None:
    """The allowlist must contain exactly the known spike/demo pages."""
    assert {"milkdown_spike", "text_selection", "highlight_api_demo"} == _ALLOWLIST


def test_synthetic_violation_detected() -> None:
    """The scanner must catch ``await ui.run_javascript(...)``."""
    snippet = """\
import nicegui.ui as ui

async def handler():
    result = await ui.run_javascript("document.title")
"""
    violations = _find_await_run_javascript(snippet, filename="<synthetic>")
    assert len(violations) == 1
    assert violations[0][0] == "<synthetic>"
    assert violations[0][1] == 4
    assert "run_javascript" in violations[0][2]
