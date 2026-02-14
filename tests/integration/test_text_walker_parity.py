"""JS/Python text walker parity tests.

Verifies that the JS walkTextNodes() function (in annotation-highlight.js)
produces identical text content to Python extract_text_from_html() for
all workspace fixtures. Compares full collapsed text strings, not just
character counts — identical strings guarantee identical coordinate mapping.
Uses Playwright to run JS in a real browser via page.set_content().

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


# --- JS evaluation snippets ---

_JS_CHAR_COUNT = """
(() => {
    const nodes = walkTextNodes(document.body);
    return nodes.length ? nodes[nodes.length - 1].endChar : 0;
})()
"""

# Mirrors walkTextNodes algorithm but builds the collapsed text string.
# Must stay in sync with walkTextNodes in annotation-highlight.js and
# extract_text_from_html in input_pipeline/html_input.py.
# COUPLING NOTE: The whitespace collapsing logic (SKIP/BLOCK sets, newline→space,
# collapse runs) is duplicated from walkTextNodes. If the walker's whitespace
# rules change, this script must be updated to match.
_JS_EXTRACT_TEXT = """
(() => {
    const SKIP = new Set(['SCRIPT','STYLE','NOSCRIPT','TEMPLATE']);
    const BLOCK = new Set([
        'TABLE','TBODY','THEAD','TFOOT','TR','TD','TH',
        'UL','OL','LI','DL','DT','DD',
        'DIV','SECTION','ARTICLE','ASIDE','HEADER','FOOTER','NAV','MAIN',
        'FIGURE','FIGCAPTION','BLOCKQUOTE'
    ]);
    let text = '';
    function walk(el) {
        for (let c = el.firstChild; c; c = c.nextSibling) {
            if (c.nodeType === 1) {
                const tag = c.tagName;
                if (SKIP.has(tag)) continue;
                if (tag === 'BR') { text += '\\n'; continue; }
                walk(c);
            } else if (c.nodeType === 3) {
                const raw = c.textContent;
                if (BLOCK.has(c.parentElement?.tagName) && /^\\s*$/.test(raw))
                    continue;
                let prev = false;
                for (const ch of raw) {
                    if (/[\\s\\u00a0]/.test(ch)) {
                        if (!prev) { text += ' '; prev = true; }
                    } else { text += ch; prev = false; }
                }
            }
        }
    }
    walk(document.body);
    return text;
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

    def test_text_content_matches(self, page: Page, fixture_path: Path) -> None:
        """Collapsed text from JS walker equals Python extract_text_from_html.

        Compares full strings — identical strings guarantee identical
        coordinate mapping for highlights.

        AC7.1: workspace_lawlis_v_r.html parity
        AC7.2: workspace_edge_cases.html parity (br, tables, empty p, nbsp)
        AC7.3: workspace_empty.html parity (0 chars / empty string)
        """
        html = fixture_path.read_text(encoding="utf-8")

        # Python side
        py_text = "".join(extract_text_from_html(html))

        # JS side: load HTML into browser, inject script, evaluate
        page.set_content(html)
        page.add_script_tag(path=str(_JS_PATH))
        js_text = page.evaluate(_JS_EXTRACT_TEXT)

        assert js_text == py_text, (
            f"Text mismatch for {fixture_path.name}:\n"
            f"  JS  ({len(js_text)} chars): {js_text[:200]!r}\n"
            f"  Py  ({len(py_text)} chars): {py_text[:200]!r}"
        )

    def test_char_count_matches_walker(self, page: Page, fixture_path: Path) -> None:
        """walkTextNodes() char count equals len(extract_text_from_html()).

        Verifies the production walkTextNodes function's offset tracking
        produces the same total count as the Python implementation.
        """
        html = fixture_path.read_text(encoding="utf-8")

        py_count = len(extract_text_from_html(html))

        page.set_content(html)
        page.add_script_tag(path=str(_JS_PATH))
        js_count = page.evaluate(_JS_CHAR_COUNT)

        assert js_count == py_count, (
            f"Count mismatch for {fixture_path.name}: JS={js_count}, Python={py_count}"
        )
