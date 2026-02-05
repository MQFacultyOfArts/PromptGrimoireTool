"""Verify E2E tests comply with CLAUDE.md guidelines."""

import ast
from pathlib import Path

# Tests that are allowed to use page.evaluate() for legitimate technical reasons.
# Each exception requires justification.
ALLOWED_JS_FILES = {
    # Clipboard API (navigator.clipboard.write) has no Playwright equivalent.
    # HTML paste simulation requires JavaScript to write text/html MIME type.
    # Bounding box measurements for visual regression also require evaluate().
    "test_html_paste_whitespace.py",
}


def test_no_js_injection_in_e2e_tests() -> None:
    """E2E tests must not use page.evaluate or ui.run_javascript.

    Per CLAUDE.md: "NEVER inject JavaScript in E2E tests."
    Tests must simulate real user behavior through Playwright events.

    Exceptions: Files listed in ALLOWED_JS_FILES with documented justification.

    Note: This only checks actual code, not comments or docstrings.
    """
    e2e_dir = Path(__file__).parent.parent / "e2e"
    violations: list[str] = []

    # Forbidden method calls
    forbidden_methods = {"evaluate", "run_javascript"}

    for test_file in e2e_dir.glob("test_*.py"):
        # Skip files with documented exceptions
        if test_file.name in ALLOWED_JS_FILES:
            continue

        content = test_file.read_text()
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # Check for method calls like page.evaluate() or ui.run_javascript()
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
                if method_name in forbidden_methods:
                    violations.append(
                        f"{test_file.name}:{node.lineno} - {method_name}()"
                    )

    assert not violations, (
        "E2E tests must not inject JavaScript (CLAUDE.md):\n"
        + "\n".join(f"  {v}" for v in violations)
    )
