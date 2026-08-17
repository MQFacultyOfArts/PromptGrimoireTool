"""Guard: no JavaScript injection in E2E test code without a listed reason.

Single source of truth for the JS-injection policy. Enforced twice:

- pre-commit (this file as a CLI, changed files only) — catches creep
  at commit time;
- ``tests/unit/test_e2e_compliance.py`` (imports ``find_violations``,
  whole tree) — the lane/nightly gate.

Policy (CLAUDE.md § E2E conventions, audited 2026-08-17): E2E tests
simulate real user behaviour through Playwright events. Browser-JS
execution is allowed only where no Playwright-native path exists, and
the reason must be written down. Whole-file exemptions live in
``ALLOWED_JS_FILES`` below, each with its justification. Everything in
``tests/e2e/`` is scanned — helper modules included, since that is
where the pattern concentrates.

``wait_for_function`` is deliberately NOT forbidden: read-only JS
predicates are the sanctioned epoch-wait pattern (CLAUDE.md § rebuild
epoch). The 2026-08-17 audit verified all existing bodies are pure.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Methods that execute or install JavaScript in the browser context.
FORBIDDEN_METHODS = frozenset(
    {
        "evaluate",
        "evaluate_handle",
        "run_javascript",
        "add_init_script",
        "add_script_tag",
        "dispatch_event",
    }
)

E2E_DIR = Path(__file__).resolve().parent.parent / "tests" / "e2e"

# Files allowed to execute browser JS, each with its documented reason.
# An entry sanctions the whole file — keep entries honest and specific,
# and prefer fixing a site over adding one here.
ALLOWED_JS_FILES = {
    # -- shared helpers (scanned since 2026-08-17; reasons from that audit) --
    # CSS Highlight API introspection (CSS.highlights has no DOM surface and
    # no Playwright API); rAF paint pumps; find_text_range walks text nodes
    # read-only. Known debt with an issue: select_text_range fakes the
    # selection + mouseup (#154 tracks the real-pointer rewrite) and
    # scroll_to_char calls the app's scrollToCharOffset directly.
    "highlight_tools.py",
    # Clipboard paste simulation: navigator.clipboard.write() needs
    # permissions Firefox does not grant, and Playwright has no native
    # text/html clipboard write. See module docstring.
    "paste_helpers.py",
    # Reads window.__annotationCardsEpoch / __cardEpochs (epoch-wait
    # pattern, no DOM surface) plus rAF paint pumps.
    "card_helpers.py",
    # -- test files (entries predate 2026-08-17 audit; reasons verified) --
    # Clipboard API (navigator.clipboard.write) has no Playwright equivalent.
    # HTML paste simulation requires JavaScript to write text/html MIME type.
    # Bounding box measurements for visual regression also require evaluate().
    "test_html_paste_whitespace.py",
    # Fixture screenshot tests use clipboard paste simulation (same as above)
    # and DOM introspection (data-speaker element counts, scroll positions).
    "test_fixture_screenshots.py",
    # Paragraph screenshot tests use clipboard paste simulation and
    # DOM introspection (data-para elements, scroll-to-landmark positions).
    "test_para_screenshot.py",
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
    # Navigator infinite scroll tests: Playwright has no native API to
    # set scrollTop on a scrollable div. evaluate() is needed to scroll
    # the navigator container to trigger the infinite scroll handler.
    "test_navigator.py",
    # Quasar dropdown menu items detach from DOM during NiceGUI re-renders.
    # page.locator().click() races against detachment; evaluate() finds and
    # clicks in a single synchronous frame — no Playwright-native alternative.
    "test_history_tutorial.py",
    "test_law_student.py",
    # Card layout tests read inline style.top (no Playwright-native API)
    # and programmatically scroll doc-container for positioning assertions.
    "test_card_layout.py",
    # Colour input uses input-class="hidden", so Playwright fill() cannot
    # interact with it. JS native setter injection is the only reliable way
    # to programmatically set the colour value and trigger Vue reactivity.
    "test_tag_colour.py",
    # Performance instrumentation (#377): evaluate() reads
    # window.__annotationCardsEpoch for rebuild-epoch pattern; the sole
    # add_init_script in the tree gates console.time instrumentation.
    "test_browser_perf_377.py",
    # Idle tab eviction (#471): visibilitychange simulation requires
    # evaluate() — Playwright has no native API for tab visibility.
    "test_idle_tab_eviction.py",
    # Cross-tab Vue sidebar test: reads inline style.top values and
    # checks card positioning — no Playwright-native API for this.
    "test_vue_sidebar_cross_tab.py",
}


def find_violations(files: list[Path] | None = None) -> list[str]:
    """Scan E2E Python files for browser-JS execution outside the allowlist.

    Args:
        files: Specific files to check (pre-commit mode). None scans all
            of ``tests/e2e/*.py`` (gate mode). Files outside tests/e2e
            are ignored so pre-commit can pass its whole changed set.

    Returns:
        ``"file.py:lineno - method()"`` strings, empty when compliant.
    """
    if files is None:
        candidates = sorted(E2E_DIR.glob("*.py"))
    else:
        candidates = [
            p for p in files if p.resolve().is_relative_to(E2E_DIR) and p.exists()
        ]

    violations: list[str] = []
    for path in candidates:
        if path.name not in ALLOWED_JS_FILES:
            violations.extend(_scan_file(path))
    return violations


def _scan_file(path: Path) -> list[str]:
    """Return forbidden-method call sites in one file."""
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []
    return [
        f"{path.name}:{node.lineno} - {node.func.attr}()"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in FORBIDDEN_METHODS
    ]


def main(argv: list[str]) -> int:
    """CLI entry point for the pre-commit hook."""
    files = [Path(a) for a in argv] or None
    violations = find_violations(files)
    if violations:
        print(
            "JS injection in E2E test code without a listed reason "
            "(scripts/check_js_injection.py):"
        )
        for v in violations:
            print(f"  tests/e2e/{v}")
        print(
            "Simulate the real user action via Playwright instead, or — only "
            "when no Playwright-native path exists — add the file to "
            "ALLOWED_JS_FILES with the specific reason written down."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
