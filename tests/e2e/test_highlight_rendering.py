"""E2E tests for CSS Custom Highlight API highlight rendering.

Verifies that annotation highlights render via the CSS Custom Highlight API
without any ``<span class="char">`` elements in the DOM.

Acceptance criteria:
- css-highlight-api.AC1.1: Highlights paint on correct text ranges without char spans
- css-highlight-api.AC1.2: Multiple tags render with distinct colours
- css-highlight-api.AC1.3: Highlights span across block boundaries
- css-highlight-api.AC1.4: Invalid offsets silently skipped with warning
- css-highlight-api.AC1.5: Overlapping highlights both visible

Traceability:
- Design: docs/implementation-plans/2026-02-11-css-highlight-api-150/phase_03.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.e2e.fixture_loaders import setup_workspace_with_content_highlight_api
from tests.e2e.highlight_tools import select_text_range

if TYPE_CHECKING:
    from playwright.sync_api import Page


class TestHighlightRendering:
    """Tests for CSS Custom Highlight API rendering."""

    def test_highlights_paint_without_char_spans(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC1.1: Highlights render via CSS.highlights without span.char in DOM.

        Creates a workspace with content, makes a text selection, creates a
        highlight, then verifies:
        1. No ``<span class="char">`` elements exist in the DOM
        2. The highlight is registered in ``CSS.highlights``
        """
        page = authenticated_page
        setup_workspace_with_content_highlight_api(
            page, app_server, "The court held that the defendant was liable."
        )

        # Select text and create highlight via tag button
        select_text_range(page, "defendant")

        # Wait for and click first tag button (Jurisdiction)
        tag_btn = page.locator("[data-testid='tag-toolbar'] button").first
        tag_btn.wait_for(state="visible")
        tag_btn.click()

        # Verify no char spans in DOM
        char_spans = page.locator("#doc-container span.char")
        expect(char_spans).to_have_count(0)

        # Wait for and verify highlight is registered in CSS.highlights
        page.wait_for_function(
            """() => {
                for (const name of CSS.highlights.keys()) {
                    if (name.startsWith('hl-')) return true;
                }
                return false;
            }"""
        )

    def test_multiple_tags_render_with_distinct_highlights(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC1.2: Multiple tags render with distinct CSS.highlights.

        Creates highlights with two different tags and verifies both are
        registered as separate entries in ``CSS.highlights``.
        """
        page = authenticated_page
        setup_workspace_with_content_highlight_api(
            page,
            app_server,
            "The jurisdiction is New South Wales. The legal issue is negligence.",
        )

        # Create highlight with first tag (index 0 = jurisdiction)
        select_text_range(page, "New South Wales")
        tag_btn_0 = page.locator("[data-testid='tag-toolbar'] button").nth(0)
        tag_btn_0.wait_for(state="visible")
        tag_btn_0.click()

        # Wait for first highlight to be applied
        page.wait_for_function(
            """() => {
                for (const name of CSS.highlights.keys()) {
                    if (name.startsWith('hl-')) return true;
                }
                return false;
            }"""
        )

        # Create highlight with second tag (index 1)
        select_text_range(page, "negligence")
        tag_btn_1 = page.locator("[data-testid='tag-toolbar'] button").nth(1)
        tag_btn_1.wait_for(state="visible")
        tag_btn_1.click()

        # Wait for and verify two distinct hl-* entries in CSS.highlights
        page.wait_for_function(
            """() => {
                const names = [];
                for (const name of CSS.highlights.keys()) {
                    if (name.startsWith('hl-')) names.push(name);
                }
                return names.length >= 2;
            }"""
        )

    def test_highlight_spans_across_block_boundaries(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC1.3: Highlight spanning block boundaries renders as continuous highlight.

        Creates a highlight that crosses a paragraph boundary and verifies
        it registers as a single entry in ``CSS.highlights``.
        """
        page = authenticated_page
        # Use HTML with paragraph boundary
        html_content = "<p>First paragraph text.</p><p>Second paragraph text.</p>"
        setup_workspace_with_content_highlight_api(page, app_server, html_content)

        # Select text spanning both paragraphs using JS evaluation
        # (native mouse selection across block boundaries is hard to automate)
        page.evaluate(
            """() => {
                const q = '[data-testid="doc-container"]';
                const container = document.querySelector(q);
                const textNodes = walkTextNodes(container);
                // Select from char 10 to char 30 (spans the paragraph boundary)
                const totalChars = textNodes.length
                    ? textNodes[textNodes.length - 1].endChar : 0;
                const endChar = Math.min(30, totalChars);
                emitEvent('selection_made', {start_char: 10, end_char: endChar});
            }"""
        )

        # Wait for and click first tag button
        tag_btn = page.locator("[data-testid='tag-toolbar'] button").first
        tag_btn.wait_for(state="visible")
        tag_btn.click()

        # Wait for and verify a highlight entry exists
        page.wait_for_function(
            """() => {
                let count = 0;
                for (const name of CSS.highlights.keys()) {
                    if (name.startsWith('hl-')) count++;
                }
                return count >= 1;
            }"""
        )

    def test_invalid_offsets_silently_skipped(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC1.4: Invalid char offsets are silently skipped with console warning.

        Calls ``applyHighlights()`` directly with invalid offsets and verifies
        no crash occurs and a warning is logged. This is an algorithm validation
        test using ``page.evaluate()``.
        """
        page = authenticated_page
        setup_workspace_with_content_highlight_api(
            page, app_server, "Short test document."
        )

        # Capture console warnings
        warnings: list[str] = []
        page.on(
            "console",
            lambda msg: warnings.append(msg.text) if msg.type == "warning" else None,
        )

        # Call applyHighlights with various invalid offsets
        page.evaluate(
            """() => {
                const c = document.querySelector('[data-testid=\"doc-container\"]');
                applyHighlights(c, {
                    test_tag: [
                        {start_char: -1, end_char: 5},      // negative start
                        {start_char: 5, end_char: 3},        // start >= end
                        {start_char: 99999, end_char: 99999}, // beyond doc length
                    ]
                });

                // Signal completion by creating a dummy element or just resolving
                window.__applyHighlightsDone = true;
            }"""
        )
        page.wait_for_function("() => window.__applyHighlightsDone === true")

        # Should not crash — verify page is still responsive
        title = page.evaluate("() => document.title")
        assert title is not None, (
            "Page should still be responsive after invalid offsets"
        )

        # Verify warnings were logged
        assert len(warnings) >= 2, (
            f"Expected 2+ console warnings for invalid offsets, "
            f"got {len(warnings)}: {warnings}"
        )

    def test_overlapping_highlights_both_visible(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC1.5: Overlapping highlights from different tags are both visible.

        Creates two overlapping highlights with different tags and verifies
        both are registered in ``CSS.highlights``.
        """
        page = authenticated_page
        setup_workspace_with_content_highlight_api(
            page,
            app_server,
            "The defendant was negligent in their duty of care.",
        )

        # Create first highlight on "defendant was negligent" (tag 0)
        select_text_range(page, "defendant was negligent")
        tag_btn_0 = page.locator("[data-testid='tag-toolbar'] button").nth(0)
        tag_btn_0.wait_for(state="visible")
        tag_btn_0.click()

        # Wait for first highlight
        page.wait_for_function(
            """() => {
                for (const name of CSS.highlights.keys()) {
                    if (name.startsWith('hl-')) return true;
                }
                return false;
            }"""
        )

        # Create second highlight on "negligent in their" (tag 1, overlaps first)
        select_text_range(page, "negligent in their")
        tag_btn_1 = page.locator("[data-testid='tag-toolbar'] button").nth(1)
        tag_btn_1.wait_for(state="visible")
        tag_btn_1.click()

        # Wait for and verify both highlight entries exist with distinct names
        page.wait_for_function(
            """() => {
                const names = [];
                for (const name of CSS.highlights.keys()) {
                    if (name.startsWith('hl-')) names.push(name);
                }
                return names.length >= 2;
            }"""
        )
