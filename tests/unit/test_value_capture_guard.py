"""Structural guard: prevent server-side .value reads on ui.input in handlers.

Detects the vulnerable pattern where an async event handler reads
``some_input.value`` server-side instead of receiving the value
client-side via ``on_submit_with_value``.  See the design doc at
``docs/design-plans/2026-03-11-value-capture-hardening.md``.

The guard uses Python's ``ast`` module to walk source files and flag
``.value`` attribute **reads** (not writes) on variables that look
like UI input references — either by type annotation (``ui.input``,
``Input``) or by naming convention (``*_input``, ``input_field``).

Only async functions nested inside other functions are checked,
since those are the event handler closures where the race applies.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Directories containing NiceGUI page code with event handlers.
_PAGES_DIR = Path("src/promptgrimoire/pages")

# Known-safe .value reads in async handlers.  Each entry is
# (filename_stem, variable_name) with a comment explaining why
# the read is safe.
#
# These are medium-risk sites with large time gaps between last
# keystroke and submit (dialog forms, auth flows, inline edits).
# See design doc § "Additional Considerations" for rationale.
_ALLOWLIST: set[tuple[str, str]] = {
    # Inline para_ref editor: blur handler, user edits then clicks away
    ("cards", "field"),
    # Magic-link auth: user types email, clicks send (large gap)
    ("auth", "email_input"),
    # Course settings dialog: multi-field form save (large gap)
    ("courses", "word_min_input"),
    ("courses", "word_limit_input"),
    # Navigator title edit: reads current value as rollback, not submit
    ("_cards", "title_input"),
}


def _is_input_annotation(annotation: ast.expr) -> bool:
    """Check if a type annotation references a UI input type."""
    # ui.input, ui.textarea
    if isinstance(annotation, ast.Attribute) and annotation.attr in (
        "input",
        "textarea",
    ):
        return True
    # Input (bare import)
    return isinstance(annotation, ast.Name) and annotation.id in (
        "Input",
        "Textarea",
    )


def _is_input_name(name: str) -> bool:
    """Heuristic: does this variable name look like a UI input?"""
    lower = name.lower()
    return (
        lower.endswith("_input")
        or lower == "input_field"
        or lower.endswith("_textarea")
    )


def _is_value_read(node: ast.Attribute, parent_map: dict[int, ast.AST]) -> bool:
    """Check if an attribute access is a .value READ (not write).

    A .value on the left side of an assignment (``inp.value = ""``)
    is a write and is safe.  Everything else is a read.
    """
    if node.attr != "value":
        return False
    parent = parent_map.get(id(node))
    # Assignment target: `inp.value = ...`
    if isinstance(parent, ast.Assign):
        return node not in parent.targets
    # Augmented assignment target: `inp.value += ...`
    if isinstance(parent, ast.AugAssign):
        return node is not parent.target
    # Annotated assignment target: `inp.value: str = ...`
    if isinstance(parent, ast.AnnAssign):
        return node is not parent.target
    # Delete target
    if isinstance(parent, ast.Delete):
        return node not in parent.targets
    return True


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    """Map each node's id() to its parent."""
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _find_input_param_names(func: ast.AsyncFunctionDef) -> set[str]:
    """Find parameter names annotated as UI input types."""
    names: set[str] = set()
    for arg in func.args.args + func.args.kwonlyargs:
        if arg.annotation and _is_input_annotation(arg.annotation):
            names.add(arg.arg)
    return names


def _find_violations_in_func(
    func: ast.AsyncFunctionDef,
    parent_map: dict[int, ast.AST],
    file_stem: str,
) -> list[tuple[str, int, str]]:
    """Find .value reads on input-like variables in an async function.

    Returns list of (variable_name, line_number, context) tuples.
    """
    violations: list[tuple[str, int, str]] = []

    # Params with input type annotations
    annotated_inputs = _find_input_param_names(func)

    for node in ast.walk(func):
        if not isinstance(node, ast.Attribute):
            continue
        if not _is_value_read(node, parent_map):
            continue
        # The object of the .value access
        if not isinstance(node.value, ast.Name):
            continue

        var_name = node.value.id

        # Check allowlist
        if (file_stem, var_name) in _ALLOWLIST:
            continue

        # Flag if annotated as input type
        if var_name in annotated_inputs:
            violations.append(
                (
                    var_name,
                    node.lineno,
                    "type-annotated as ui.input",
                )
            )
            continue

        # Flag if name matches input naming convention
        if _is_input_name(var_name):
            violations.append(
                (
                    var_name,
                    node.lineno,
                    "name matches input convention",
                )
            )

    return violations


def _is_nested_async_def(
    node: ast.AsyncFunctionDef,
    parent_map: dict[int, ast.AST],
) -> bool:
    """Check if an async def is nested inside another function."""
    current = parent_map.get(id(node))
    while current is not None:
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef):
            return True
        current = parent_map.get(id(current))
    return False


def test_no_value_reads_on_inputs_in_handlers() -> None:
    """No async handler should read .value on a ui.input variable.

    The server-side .value may be stale due to concurrent event
    dispatch (python-socketio async_handlers=True).  Use
    ``on_submit_with_value`` to capture the DOM value client-side.

    If this test fails, either:
    1. Use ``on_submit_with_value`` to wire the handler (preferred), or
    2. Add the variable to ``_ALLOWLIST`` with a comment explaining
       why the read is safe (e.g., not in an event handler path).
    """
    all_violations: list[str] = []

    for py_file in sorted(_PAGES_DIR.rglob("*.py")):
        source = py_file.read_text()
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        parent_map = _build_parent_map(tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not _is_nested_async_def(node, parent_map):
                continue

            violations = _find_violations_in_func(
                node,
                parent_map,
                py_file.stem,
            )
            for var_name, lineno, reason in violations:
                all_violations.append(
                    f"  {py_file}:{lineno}: "
                    f"{var_name}.value read in async handler "
                    f"{node.name}() ({reason})"
                )

    if all_violations:
        msg = (
            "Server-side .value reads on ui.input variables in async "
            "handlers.\n"
            "Use on_submit_with_value() to capture DOM value "
            "client-side.\n"
            "See docs/design-plans/"
            "2026-03-11-value-capture-hardening.md\n\n" + "\n".join(all_violations)
        )
        raise AssertionError(msg)
