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
    # Fixture screenshot tests use clipboard paste simulation (same as above)
    # and DOM introspection (data-speaker element counts, scroll positions).
    "test_fixture_screenshots.py",
    # Browser feature gate test: Playwright only ships supported browsers
    # (Chromium, Firefox, WebKit all support CSS.highlights). Simulating an
    # unsupported browser requires deleting CSS.highlights via evaluate().
    "test_browser_gate.py",
    # Highlight rendering tests: AC1.4 validates JS error handling (invalid
    # offsets logged as warning, no crash) by calling applyHighlights()
    # directly with crafted inputs — no user action produces these inputs.
    # Other tests use evaluate() for CSS.highlights introspection and
    # text selection simulation (no Playwright API for CSS.highlights).
    "test_highlight_rendering.py",
    # Text selection tests: AC2.1 uses evaluate() to locate text node
    # bounding rects for precise mouse selection. AC2.2 uses evaluate()
    # to emit synthetic selection events spanning block boundaries.
    # CSS.highlights introspection requires evaluate() (no Playwright API).
    "test_text_selection.py",
    # Integration test for full CSS Highlight API flow: uses evaluate()
    # to locate text node bounding rects for mouse selection and to
    # introspect CSS.highlights entries (no Playwright API for either).
    "test_annotation_highlight_api.py",
    # Remote presence rendering tests: CSS.highlights introspection has no
    # Playwright native API. Custom JS functions (renderRemoteCursor,
    # renderRemoteSelection, removeAllRemotePresence) can only be invoked
    # via page.evaluate() — no Playwright equivalent exists.
    "test_remote_presence_rendering.py",
    # Remote presence E2E smoke test: CSS.highlights.has() and DOM element
    # inspection for remote presence indicators require page.evaluate() — no
    # Playwright native API exists for CSS Custom Highlight API introspection.
    "test_remote_presence_e2e.py",
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
