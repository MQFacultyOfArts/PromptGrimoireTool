"""JS/Python text walker parity tests.

Verifies that the JS walkTextNodes() function (in annotation-highlight.js)
produces identical character counts to Python extract_text_from_html() for
all workspace fixtures. Uses Playwright to run JS in a real browser via
page.set_content() -- no NiceGUI server needed.

Traceability:
- AC: css-highlight-api.AC7.1, css-highlight-api.AC7.2, css-highlight-api.AC7.3
- Design: docs/implementation-plans/2026-02-11-css-highlight-api/phase_02.md
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from promptgrimoire.input_pipeline.html_input import extract_text_from_html

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Page


# --- Override autouse async fixture from integration/conftest.py ---
# The reset_db_engine_per_test fixture is async and conflicts with
# Playwright's sync event loop. This module does not use the database.
@pytest.fixture(autouse=True)
def reset_db_engine_per_test() -> Generator[None]:
    """No-op override: parity tests don't use the database."""
    yield


# --- Fixture discovery ---

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
_JS_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "promptgrimoire"
    / "static"
    / "annotation-highlight.js"
)


def _discover_workspace_fixtures() -> list[Path]:
    """Glob all workspace_*.html fixtures, sorted by name for determinism."""
    fixtures = sorted(_FIXTURES_DIR.glob("workspace_*.html"))
    if not fixtures:
        pytest.fail("No workspace_*.html fixtures found in tests/fixtures/")
    return fixtures


def _fixture_ids() -> list[str]:
    """Return fixture stem names for readable test IDs."""
    return [p.stem for p in _discover_workspace_fixtures()]


# --- JS evaluation snippet ---

_JS_CHAR_COUNT = """
(() => {
    const nodes = walkTextNodes(document.body);
    return nodes.length ? nodes[nodes.length - 1].endChar : 0;
})()
"""


@pytest.mark.e2e
@pytest.mark.parametrize(
    "fixture_path",
    _discover_workspace_fixtures(),
    ids=_fixture_ids(),
)
class TestTextWalkerParity:
    """JS walkTextNodes() must match Python extract_text_from_html()."""

    def test_char_count_matches(self, page: Page, fixture_path: Path) -> None:
        """Char count from JS walkTextNodes equals Python extract_text_from_html.

        AC7.1: workspace_lawlis_v_r.html parity
        AC7.2: workspace_edge_cases.html parity (br, tables, empty p, nbsp)
        AC7.3: workspace_empty.html parity (0 chars)
        """
        html = fixture_path.read_text(encoding="utf-8")

        # Python side
        py_chars = extract_text_from_html(html)
        py_count = len(py_chars)

        # JS side: load HTML into browser, inject script, evaluate
        page.set_content(html)
        page.add_script_tag(path=str(_JS_PATH))
        js_count = page.evaluate(_JS_CHAR_COUNT)

        assert js_count == py_count, (
            f"Parity mismatch for {fixture_path.name}: JS={js_count}, Python={py_count}"
        )
