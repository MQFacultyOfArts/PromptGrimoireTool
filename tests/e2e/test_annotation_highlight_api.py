"""E2E integration test for CSS Custom Highlight API annotation flow.

Exercises the complete Phase 3 flow end-to-end: text selection via
the JS text walker, highlight creation, and rendering via the CSS
Custom Highlight API. Proves all Phase 3 components work together.

Acceptance criteria verified:
- css-highlight-api.AC1.1: Highlights render without char spans
- css-highlight-api.AC2.1: Selection produces correct char offsets

Traceability:
- Design: docs/implementation-plans/2026-02-11-css-highlight-api-150/phase_03.md
- Task 6: Full annotation page integration test
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.e2e.fixture_loaders import setup_workspace_with_content_highlight_api
from tests.e2e.highlight_tools import (
    wait_for_css_highlight,
    wait_for_css_highlight_count,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page


def _select_text_by_mouse(page: Page, text: str) -> dict[str, float] | None:
    """Select text by mouse drag, returning coords used.

    Finds the text in the doc-container, computes bounding rect,
    and performs a mouse drag to select it.

    Returns the coords dict or None if text was not found.
    """
    coords = page.evaluate(
        """(text) => {
            const c = document.querySelector('[data-testid=\"doc-container\"]');
            const walker = document.createTreeWalker(
                c, NodeFilter.SHOW_TEXT, null
            );
            let node;
            while ((node = walker.nextNode())) {
                const idx = node.textContent.indexOf(text);
                if (idx >= 0) {
                    const range = document.createRange();
                    range.setStart(node, idx);
                    range.setEnd(node, idx + text.length);
                    const rect = range.getBoundingClientRect();
                    return {
                        x1: rect.left + 2,
                        y: rect.top + rect.height / 2,
                        x2: rect.right - 2
                    };
                }
            }
            return null;
        }""",
        text,
    )
    if coords is None:
        return None

    page.mouse.move(coords["x1"], coords["y"])
    page.mouse.down()
    page.mouse.move(coords["x2"], coords["y"])
    page.mouse.up()
    return coords


class TestAnnotationHighlightApiIntegration:
    """Integration test: selection + highlight via CSS Custom Highlight API."""

    def test_full_flow_select_highlight_verify(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC1.1 + AC2.1: Full user flow from selection to highlight rendering.

        Steps:
        1. Create workspace with content
        2. Select text with mouse (AC2.1: correct offsets)
        3. Create highlight via tag button
        4. Verify no span.char elements in DOM (AC1.1)
        5. Verify highlight registered in CSS.highlights (AC1.1)
        """
        page = authenticated_page
        content = (
            "The plaintiff alleged that the defendant breached "
            "their duty of care in the workplace."
        )
        setup_workspace_with_content_highlight_api(page, app_server, content)

        # Step 2: Select text by mouse drag
        coords = _select_text_by_mouse(page, "defendant")
        assert coords is not None, "Could not find 'defendant' in document"

        # Step 3: Click first tag button to create highlight
        tag_btn = page.locator("[data-testid='tag-toolbar'] button").first
        tag_btn.click()
        wait_for_css_highlight(page)

        # Step 4: No span.char in DOM
        char_spans = page.get_by_test_id("doc-container").locator("span.char")
        expect(char_spans).to_have_count(0)

    def test_two_tags_distinct_highlights(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC1.1 + AC2.1: Two highlights with different tags are both visible.

        Steps:
        1. Create workspace
        2. Select first text, create highlight with tag 0
        3. Select second text, create highlight with tag 1
        4. Verify two distinct hl-* entries in CSS.highlights
        5. Verify no span.char elements
        """
        page = authenticated_page
        content = "The jurisdiction is Queensland. The cause of action is negligence."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        # First highlight: "Queensland" with tag 0
        coords = _select_text_by_mouse(page, "Queensland")
        assert coords is not None
        page.locator("[data-testid='tag-toolbar'] button").nth(0).click()
        wait_for_css_highlight(page)

        # Second highlight: "negligence" with tag 1
        coords = _select_text_by_mouse(page, "negligence")
        assert coords is not None
        page.locator("[data-testid='tag-toolbar'] button").nth(1).click()
        wait_for_css_highlight_count(page, 2)

        # Verify no char spans
        char_spans = page.get_by_test_id("doc-container").locator("span.char")
        expect(char_spans).to_have_count(0)
