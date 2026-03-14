"""Guard test: no silent exception swallowing in src/promptgrimoire/.

Every except block that catches an error must either:
- Log it (logger.exception/error/warning/debug or log.exception/error/warning/debug)
- Re-raise it (raise with or without argument)
- Be a bare continue (retry loops)

CLI tools are excluded — they use print for terminal output.
"""

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent.parent / "src" / "promptgrimoire"
EXCLUDED_DIRS = {"cli", "__pycache__"}
EXCLUDED_FILES = {"cli_loadtest.py"}

LOG_METHODS = frozenset({"exception", "error", "warning", "debug"})


def _has_logging_call(handler: ast.ExceptHandler) -> bool:
    """Check if the except handler body contains a logging call."""
    for child in ast.walk(handler):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in LOG_METHODS
        ):
            return True
    return False


def _only_reraises(handler: ast.ExceptHandler) -> bool:
    """Return True if handler body ends with a raise (possibly after assignments)."""
    # A re-raise block may do assignments (wrapping the error) before raising.
    # The key criterion: the block ENDS with a Raise statement.
    if not handler.body:
        return False
    last = handler.body[-1]
    # Direct raise or if/else that both raise
    if isinstance(last, ast.Raise):
        return True
    if isinstance(last, ast.If):
        # Both branches must raise
        if_raises = any(isinstance(s, ast.Raise) for s in last.body)
        else_raises = any(isinstance(s, ast.Raise) for s in last.orelse)
        return if_raises and else_raises
    return False


def _only_assigns_to_variable(handler: ast.ExceptHandler) -> bool:
    """Return True if handler only captures the exception into a variable.

    Permits deferred re-raise patterns where the exception is stored
    and raised after cleanup (e.g. thread-boundary exception forwarding).
    """
    return all(isinstance(s, ast.Assign) for s in handler.body)


def _only_continue(handler: ast.ExceptHandler) -> bool:
    """Return True if handler body is just a continue statement.

    Assumes the enclosing loop logs on eventual failure. Only permits
    bare continue — handlers that also do work must log.
    """
    return len(handler.body) == 1 and isinstance(handler.body[0], ast.Continue)


def test_no_silent_exception_swallowing() -> None:
    """Every except block must log, re-raise, or continue.

    Excludes src/promptgrimoire/cli/ (CLI tools use print for terminal output).
    """
    violations: list[str] = []

    for py_file in SRC_DIR.rglob("*.py"):
        rel = py_file.relative_to(SRC_DIR)

        # Skip excluded directories and files
        if EXCLUDED_DIRS & set(rel.parts):
            continue
        if py_file.name in EXCLUDED_FILES:
            continue

        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if _only_reraises(node):
                continue
            if _only_continue(node):
                continue
            if _only_assigns_to_variable(node):
                continue
            if _has_logging_call(node):
                continue

            violations.append(
                f"{rel}:{node.lineno} — except block without logging; "
                f"add logger.exception/warning/debug or re-raise"
            )

    assert not violations, (
        "Silent exception swallowing found in src/promptgrimoire/ (excluding cli/).\n"
        "Every except block must log the error or re-raise it.\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )
