"""Guard test: no logging.getLogger(__name__).setLevel() in src/promptgrimoire/.

Per-module setLevel calls suppress structlog debug output and are redundant —
structlog's level filtering is configured globally. Removed in #377.
"""

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent.parent / "src" / "promptgrimoire"


def _is_setlevel_call(node: ast.Call) -> bool:
    """Return True if *node* is ``logging.getLogger(...).setLevel(...)``."""
    # Shape: Call(func=Attribute(value=Call(...getLogger...), attr='setLevel'))
    # Catches both logging.getLogger(__name__) and logging.getLogger(f"{__name__}.sub")
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "setLevel":
        return False
    inner = node.func.value
    if not isinstance(inner, ast.Call) or not isinstance(inner.func, ast.Attribute):
        return False
    return (
        inner.func.attr == "getLogger"
        and isinstance(inner.func.value, ast.Name)
        and inner.func.value.id == "logging"
    )


def test_no_setlevel_calls_in_source() -> None:
    """No logging.getLogger(__name__).setLevel() calls in src/promptgrimoire/.

    structlog's global config handles level filtering. Per-module setLevel
    calls on the stdlib logger suppress debug output through the bridge.
    """
    violations: list[str] = []

    for py_file in sorted(SRC_DIR.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue

        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_setlevel_call(node):
                rel = py_file.relative_to(SRC_DIR)
                violations.append(f"{rel}:{node.lineno}")

    assert not violations, (
        "logging.getLogger(__name__).setLevel() calls found in src/promptgrimoire/.\n"
        "structlog's global config handles level filtering — per-module setLevel\n"
        "calls suppress debug output and must not be reintroduced.\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )
