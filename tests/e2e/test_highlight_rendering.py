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
- Design: docs/implementation-plans/2026-02-11-css-highlight-api/phase_03.md
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


def _setup_workspace_with_content_highlight_api(
    page: Page, app_server: str, content: str
) -> None:
    """Set up a workspace and wait for CSS Highlight API initialisation.

    Unlike ``annotation_helpers.setup_workspace_with_content`` which waits for
    ``[data-char-index]`` (char spans), this waits for the text walker to
    initialise by checking ``window._textNodes`` is populated.

    Args:
        page: Playwright page (must be authenticated).
        app_server: Base URL of the app server.
        content: Text content to add as document.
    """
    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
    content_input.fill(content)
    page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()

    # Wait for the text walker to initialise (replaces waiting for char spans)
    page.wait_for_function(
        "() => window._textNodes && window._textNodes.length > 0",
        timeout=10000,
    )
    page.wait_for_timeout(200)


def _select_text_range(page: Page, text: str) -> None:
    """Select a text substring in the document container by evaluating JS.

    Uses the browser's native selection API to select the given text
    within ``#doc-container``. This approach works without char spans.

    Args:
        page: Playwright page.
        text: The text substring to select.
    """
    page.evaluate(
        """(text) => {
            const container = document.getElementById('doc-container');
            const walker = document.createTreeWalker(
                container, NodeFilter.SHOW_TEXT, null
            );
            let node;
            while ((node = walker.nextNode())) {
                const idx = node.textContent.indexOf(text);
                if (idx >= 0) {
                    const range = document.createRange();
                    range.setStart(node, idx);
                    range.setEnd(node, idx + text.length);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    // Trigger mouseup to fire selection handler
                    container.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                    return;
                }
            }
            throw new Error('Text not found: ' + text);
        }""",
        text,
    )
    page.wait_for_timeout(200)


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
        _setup_workspace_with_content_highlight_api(
            page, app_server, "The court held that the defendant was liable."
        )

        # Select text and create highlight via tag button
        _select_text_range(page, "defendant")
        page.wait_for_timeout(300)

        # Click first tag button (Jurisdiction)
        tag_btn = page.locator("[data-testid='tag-toolbar'] button").first
        tag_btn.click()
        page.wait_for_timeout(500)

        # Verify no char spans in DOM
        char_spans = page.locator("#doc-container span.char")
        expect(char_spans).to_have_count(0)

        # Verify highlight is registered in CSS.highlights
        has_highlight = page.evaluate(
            """() => {
                for (const name of CSS.highlights.keys()) {
                    if (name.startsWith('hl-')) return true;
                }
                return false;
            }"""
        )
        assert has_highlight, "Expected at least one hl-* entry in CSS.highlights"

    def test_multiple_tags_render_with_distinct_highlights(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC1.2: Multiple tags render with distinct CSS.highlights.

        Creates highlights with two different tags and verifies both are
        registered as separate entries in ``CSS.highlights``.
        """
        page = authenticated_page
        _setup_workspace_with_content_highlight_api(
            page,
            app_server,
            "The jurisdiction is New South Wales. The legal issue is negligence.",
        )

        # Create highlight with first tag (index 0 = jurisdiction)
        _select_text_range(page, "New South Wales")
        page.wait_for_timeout(300)
        page.locator("[data-testid='tag-toolbar'] button").nth(0).click()
        page.wait_for_timeout(500)

        # Create highlight with second tag (index 1)
        _select_text_range(page, "negligence")
        page.wait_for_timeout(300)
        page.locator("[data-testid='tag-toolbar'] button").nth(1).click()
        page.wait_for_timeout(500)

        # Verify two distinct hl-* entries in CSS.highlights
        highlight_names = page.evaluate(
            """() => {
                const names = [];
                for (const name of CSS.highlights.keys()) {
                    if (name.startsWith('hl-')) names.push(name);
                }
                return names;
            }"""
        )
        assert len(highlight_names) >= 2, (
            f"Expected at least 2 distinct hl-* highlights, got: {highlight_names}"
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
        _setup_workspace_with_content_highlight_api(page, app_server, html_content)

        # Select text spanning both paragraphs using JS evaluation
        # (native mouse selection across block boundaries is hard to automate)
        page.evaluate(
            """() => {
                const container = document.getElementById('doc-container');
                const textNodes = walkTextNodes(container);
                // Select from char 10 to char 30 (spans the paragraph boundary)
                const totalChars = textNodes.length
                    ? textNodes[textNodes.length - 1].endChar : 0;
                const endChar = Math.min(30, totalChars);
                emitEvent('selection_made', {start_char: 10, end_char: endChar});
            }"""
        )
        page.wait_for_timeout(300)

        # Click first tag button
        page.locator("[data-testid='tag-toolbar'] button").first.click()
        page.wait_for_timeout(500)

        # Verify a highlight entry exists
        highlight_count = page.evaluate(
            """() => {
                let count = 0;
                for (const name of CSS.highlights.keys()) {
                    if (name.startsWith('hl-')) count++;
                }
                return count;
            }"""
        )
        assert highlight_count >= 1, "Expected highlight to span across block boundary"

    def test_invalid_offsets_silently_skipped(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC1.4: Invalid char offsets are silently skipped with console warning.

        Calls ``applyHighlights()`` directly with invalid offsets and verifies
        no crash occurs and a warning is logged. This is an algorithm validation
        test using ``page.evaluate()``.
        """
        page = authenticated_page
        _setup_workspace_with_content_highlight_api(
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
                const c = document.getElementById('doc-container');
                applyHighlights(c, {
                    test_tag: [
                        {start_char: -1, end_char: 5},      // negative start
                        {start_char: 5, end_char: 3},        // start >= end
                        {start_char: 99999, end_char: 99999}, // beyond doc length
                    ]
                });
            }"""
        )
        page.wait_for_timeout(300)

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
        _setup_workspace_with_content_highlight_api(
            page,
            app_server,
            "The defendant was negligent in their duty of care.",
        )

        # Create first highlight on "defendant was negligent" (tag 0)
        _select_text_range(page, "defendant was negligent")
        page.wait_for_timeout(300)
        page.locator("[data-testid='tag-toolbar'] button").nth(0).click()
        page.wait_for_timeout(500)

        # Create second highlight on "negligent in their" (tag 1, overlaps first)
        _select_text_range(page, "negligent in their")
        page.wait_for_timeout(300)
        page.locator("[data-testid='tag-toolbar'] button").nth(1).click()
        page.wait_for_timeout(500)

        # Verify both highlight entries exist with distinct names
        highlight_names = page.evaluate(
            """() => {
                const names = [];
                for (const name of CSS.highlights.keys()) {
                    if (name.startsWith('hl-')) names.push(name);
                }
                return names;
            }"""
        )
        assert len(highlight_names) >= 2, (
            f"Expected 2+ hl-* highlights for overlapping ranges, "
            f"got: {highlight_names}"
        )
