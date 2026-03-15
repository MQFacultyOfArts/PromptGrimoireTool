"""Guard test: no bare print() calls in src/promptgrimoire/.

All output must go through structlog. The CLI directory is excluded because
CLI tools legitimately use print() for terminal output.
"""

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent.parent / "src" / "promptgrimoire"
EXCLUDED_DIRS = {"cli", "__pycache__"}


def test_no_print_calls_in_source() -> None:
    """All modules under src/promptgrimoire/ must use structlog, not print().

    Excludes src/promptgrimoire/cli/ (CLI tools legitimately print to terminal).
    """
    violations: list[str] = []

    for py_file in SRC_DIR.rglob("*.py"):
        # Skip excluded directories
        if EXCLUDED_DIRS & set(py_file.relative_to(SRC_DIR).parts):
            continue

        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                rel = py_file.relative_to(SRC_DIR)
                violations.append(
                    f"{rel}:{node.lineno} — print() call; use structlog logger instead"
                )

    assert not violations, (
        "Bare print() calls found in src/promptgrimoire/ (excluding cli/).\n"
        "Use structlog logger instead.\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )
