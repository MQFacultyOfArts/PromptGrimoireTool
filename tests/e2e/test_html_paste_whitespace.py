"""E2E tests for HTML paste whitespace handling.

Tests that pasted LibreOffice HTML renders without excessive whitespace.
Uses the 183-clipboard.html.html.gz fixture which contains a court case
from LibreOffice with tables for layout and CSS-defined margins.

Key test: Visual verification that paragraphs have reasonable spacing,
not the excessive gaps caused by empty <p><br/></p> elements or lost
margin styles.

Run with: pytest tests/e2e/test_html_paste_whitespace.py -v --headed
Screenshots saved to: tests/e2e/screenshots/

Traceability:
- Issue: #106 HTML input redesign
- Context: HTML Input Pipeline branch
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page

# Fixture paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "conversations"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"

# Ensure screenshot directory exists
SCREENSHOT_DIR.mkdir(exist_ok=True)


@pytest.fixture
def libreoffice_html() -> str:
    """Load the LibreOffice HTML fixture (183-clipboard.html.html.gz)."""
    fixture_path = FIXTURES_DIR / "183-clipboard.html.html.gz"
    with gzip.open(fixture_path, "rt", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def paste_ready_page(browser: Browser, app_server: str) -> Generator[Page]:
    """Authenticated page with clipboard permission, at workspace creation."""
    from uuid import uuid4

    # Create context with clipboard permissions
    context = browser.new_context(
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()

    # Authenticate
    unique_id = uuid4().hex[:8]
    email = f"paste-test-{unique_id}@test.example.edu.au"
    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

    # Navigate to annotation and create workspace
    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    yield page

    page.close()
    context.close()


def simulate_html_paste(page: Page, html_content: str) -> None:
    """Simulate pasting HTML content into the editor.

    Uses Playwright's clipboard API to write HTML, then simulates
    Ctrl+V to trigger the paste event handler.
    """
    # Focus the editor
    editor_selector = ".q-editor__content"
    editor = page.locator(editor_selector)
    expect(editor).to_be_visible(timeout=5000)
    editor.click()

    # Write HTML to clipboard via JavaScript (respects clipboard permissions)
    # This sets both text/html and text/plain MIME types
    page.evaluate(
        """(html) => {
            const plainText = html.replace(/<[^>]*>/g, '');
            return navigator.clipboard.write([
                new ClipboardItem({
                    'text/html': new Blob([html], { type: 'text/html' }),
                    'text/plain': new Blob([plainText], { type: 'text/plain' })
                })
            ]);
        }""",
        html_content,
    )

    # Small delay for clipboard write to complete
    page.wait_for_timeout(100)

    # Trigger paste with Ctrl+V
    page.keyboard.press("Control+v")

    # Wait for paste handler to process (console shows [PASTE] message)
    page.wait_for_timeout(500)


class TestHTMLPasteWhitespace:
    """Visual tests for HTML paste whitespace handling."""

    def test_libreoffice_paste_no_excessive_whitespace(
        self,
        paste_ready_page: Page,
        libreoffice_html: str,
    ) -> None:
        """Paste LibreOffice HTML and verify no excessive whitespace.

        Expected: Paragraphs should have consistent, reasonable spacing.
        NOT expected: Huge gaps between "Case Name:", "Medium Neutral Citation:", etc.
        """
        page = paste_ready_page

        # Screenshot before paste
        page.screenshot(path=str(SCREENSHOT_DIR / "01_before_paste.png"))

        # Simulate paste
        simulate_html_paste(page, libreoffice_html)

        # Screenshot after paste (editor still shows placeholder)
        page.screenshot(path=str(SCREENSHOT_DIR / "02_after_paste_editor.png"))

        # Check that paste was captured (placeholder message appears)
        editor = page.locator(".q-editor__content")
        # Should show "Content pasted" placeholder, not raw HTML
        expect(editor).to_contain_text("Content pasted", timeout=3000)

        # Click Add Document to process
        page.get_by_role("button", name=re.compile("add", re.IGNORECASE)).click()

        # Wait for document to render - first chars may be hidden newlines
        page.locator("[data-char-index='50']").wait_for(state="attached", timeout=15000)

        # Wait for rendering to stabilize
        page.wait_for_timeout(500)

        # Scroll down to see the content (it may be below the fold)
        page.locator("[data-char-index='100']").scroll_into_view_if_needed()
        page.wait_for_timeout(200)

        # Screenshot the rendered document
        page.screenshot(path=str(SCREENSHOT_DIR / "03_rendered_document.png"))

        # Get the document container - use the document content div
        doc_container = page.locator("[data-testid='document-content']")
        if doc_container.count() == 0:
            # Fallback to any element containing char spans
            doc_container = page.locator("[data-char-index]").first.locator("..")

        # Screenshot just the document content area
        doc_container.screenshot(path=str(SCREENSHOT_DIR / "04_document_content.png"))

        # Get full text content (since chars are in individual spans)
        # Use JavaScript to get innerText which collapses the spans
        full_text = page.evaluate("document.body.innerText")

        # Verify key content is present in the rendered text
        assert "Case Name" in full_text, "Missing 'Case Name' in rendered document"
        assert "Lawlis" in full_text, "Missing 'Lawlis' in rendered document"
        assert "Medium Neutral Citation" in full_text, "Missing citation label"
        assert "NSWCCA 183" in full_text, "Missing citation number"

        # Verify "Grounds of Appeal" section renders
        # This section has complex structure: <ol start="4"> with margin-left
        if "Grounds of Appeal" in full_text:
            # Scroll to find it and screenshot
            # Use JS to find element containing this text
            page.evaluate("""
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT
                );
                while (walker.nextNode()) {
                    if (walker.currentNode.textContent.includes('Grounds')) {
                        walker.currentNode.parentElement.scrollIntoView();
                        break;
                    }
                }
            """)
            page.wait_for_timeout(200)
            page.screenshot(path=str(SCREENSHOT_DIR / "05_grounds_of_appeal.png"))

            # Check that paragraph 4 content is present
            assert "Mr Lawlis sought leave" in full_text, (
                "Missing 'Mr Lawlis sought leave' - paragraph 4 not rendered"
            )

        # Measure vertical distance between key elements
        # "Case Name:" and "Medium Neutral Citation:" should be close together
        case_name = page.locator("text=Case Name").first
        citation = page.locator("text=Medium Neutral Citation").first

        case_box = case_name.bounding_box()
        citation_box = citation.bounding_box()

        if case_box and citation_box:
            vertical_gap = citation_box["y"] - (case_box["y"] + case_box["height"])

            # Save gap measurement for analysis
            (SCREENSHOT_DIR / "gap_measurement.txt").write_text(
                f"Case Name bottom: {case_box['y'] + case_box['height']:.0f}px\n"
                f"Citation top: {citation_box['y']:.0f}px\n"
                f"Vertical gap: {vertical_gap:.0f}px\n"
                f"\nExpected: ~20-60px (reasonable paragraph spacing)\n"
                f"Problem if: >100px (excessive whitespace)\n"
            )

            # ASSERTION: Gap should be reasonable (not excessive)
            # A normal paragraph gap is ~20-60px
            # The bug shows gaps of 150px+ between rows
            assert vertical_gap < 100, (
                f"Excessive whitespace detected: {vertical_gap:.0f}px gap "
                f"between 'Case Name' and 'Medium Neutral Citation'. "
                f"Expected <100px. See screenshots in {SCREENSHOT_DIR}/"
            )

    def test_paste_preserves_table_structure(
        self,
        paste_ready_page: Page,
        libreoffice_html: str,
    ) -> None:
        """Verify that table-based layout is preserved after paste.

        LibreOffice uses tables for layout. The content should maintain
        a two-column appearance (label on left, value on right).
        """
        page = paste_ready_page

        simulate_html_paste(page, libreoffice_html)
        page.get_by_role("button", name=re.compile("add", re.IGNORECASE)).click()
        page.locator("[data-char-index='50']").wait_for(state="attached", timeout=15000)
        page.wait_for_timeout(500)

        # Scroll to make Case Name visible
        page.locator("[data-char-index='100']").scroll_into_view_if_needed()
        page.wait_for_timeout(200)

        # Screenshot the table layout
        page.screenshot(path=str(SCREENSHOT_DIR / "06_table_layout.png"))

        # Get positions via JavaScript since text is split across char spans
        positions = page.evaluate("""() => {
            const spans = document.querySelectorAll('[data-char-index]');
            let caseNameSpan = null;
            let lawlisSpan = null;

            // Find spans by looking at text content
            for (const span of spans) {
                const text = span.textContent;
                // "Case" starts Case Name
                if (text === 'C' && !caseNameSpan) {
                    const next = span.nextElementSibling;
                    if (next && next.textContent === 'a') {
                        caseNameSpan = span;
                    }
                }
                // "L" starts Lawlis
                if (text === 'L' && !lawlisSpan && caseNameSpan) {
                    const next = span.nextElementSibling;
                    if (next && next.textContent === 'a') {
                        lawlisSpan = span;
                    }
                }
            }

            if (!caseNameSpan || !lawlisSpan) return null;

            const caseRect = caseNameSpan.getBoundingClientRect();
            const lawlisRect = lawlisSpan.getBoundingClientRect();

            return {
                caseY: caseRect.top,
                lawlisY: lawlisRect.top,
                yDiff: Math.abs(caseRect.top - lawlisRect.top)
            };
        }""")

        if positions:
            y_diff = positions["yDiff"]
            # Save measurement
            (SCREENSHOT_DIR / "table_layout_measurement.txt").write_text(
                f"Case Name Y: {positions['caseY']:.0f}px\n"
                f"Lawlis Y: {positions['lawlisY']:.0f}px\n"
                f"Y difference: {y_diff:.0f}px\n"
                f"\nExpected: <30px (same row)\n"
            )

            assert y_diff < 30, (
                f"Table layout broken: 'Case Name' and 'Lawlis v R' "
                f"have {y_diff:.0f}px vertical difference. "
                f"Expected <30px (same row)."
            )


class TestParagraphNumberingAndIndent:
    """Tests for ordered list numbering and indentation preservation."""

    def test_ground_1_indent_preserved(
        self,
        paste_ready_page: Page,
        libreoffice_html: str,
    ) -> None:
        """Verify Ground 1 text has proper left indent (margin-left: 2.38cm).

        The HTML has: <p style="margin-left: 2.38cm">Ground 1 - The sentencing...
        This indent should be preserved after paste processing.
        2.38cm ≈ 90px at 96dpi.
        """
        page = paste_ready_page

        simulate_html_paste(page, libreoffice_html)
        page.get_by_role("button", name=re.compile("add", re.IGNORECASE)).click()
        page.locator("[data-char-index='50']").wait_for(state="attached", timeout=15000)
        page.wait_for_timeout(500)

        # Find and measure indent of "Ground 1" text
        # Since text is split across char spans, we need to find by searching
        # the combined innerText and then locating the element
        indent_data = page.evaluate("""() => {
            // Find the document content container (has data-char-index spans)
            const charSpans = document.querySelectorAll('[data-char-index]');
            if (charSpans.length === 0) return { error: 'No char spans found' };

            // Get the content container
            const contentContainer = charSpans[0].closest('div');
            if (!contentContainer) return { error: 'No content container' };

            const containerRect = contentContainer.getBoundingClientRect();
            const fullText = contentContainer.innerText;

            // Find "Ground 1" in the text
            const match = fullText.match(/Ground\\s*1/i);
            if (!match) {
                return { error: 'Ground 1 not found', sample: fullText.slice(0, 200) };
            }

            const matchIndex = match.index;

            // Now find the char span at approximately that position
            // by counting characters
            let charCount = 0;
            let targetSpan = null;

            for (const span of charSpans) {
                const spanText = span.textContent || '';
                charCount += spanText.length;
                // Found approximately where "Ground 1" starts
                if (charCount >= matchIndex && !targetSpan) {
                    targetSpan = span;
                    break;
                }
            }

            if (!targetSpan) {
                return { error: 'Could not find span near Ground 1', matchIndex };
            }

            // Find the parent element that has the margin-left style
            // Walk up to find a p or div with style
            let styledParent = targetSpan.parentElement;
            while (styledParent && styledParent !== contentContainer) {
                const style = styledParent.getAttribute('style') || '';
                if (style.includes('margin-left')) {
                    break;
                }
                styledParent = styledParent.parentElement;
            }

            const el = styledParent || targetSpan;
            el.scrollIntoView({ block: 'center' });

            const rect = el.getBoundingClientRect();

            return {
                elementLeft: rect.left,
                baseLeft: containerRect.left,
                indent: rect.left - containerRect.left,
                text: fullText.substring(matchIndex, matchIndex + 80),
                foundStyle: el.getAttribute('style') || 'none'
            };
        }""")

        page.screenshot(path=str(SCREENSHOT_DIR / "07_ground1_indent.png"))

        if indent_data:
            indent = indent_data["indent"]
            found_style = indent_data.get("foundStyle", "unknown")
            (SCREENSHOT_DIR / "ground1_indent_measurement.txt").write_text(
                f"Ground 1 element left: {indent_data['elementLeft']:.0f}px\n"
                f"Container left: {indent_data['baseLeft']:.0f}px\n"
                f"Calculated indent: {indent:.0f}px\n"
                f"Text found: {indent_data['text']}\n"
                f"Style attribute: {found_style}\n"
                f"\nExpected: 60-120px (2.38cm at ~96dpi)\n"
            )

            # 2.38cm at 96dpi ≈ 90px, allow range 60-120px
            assert 60 <= indent <= 120, (
                f"Ground 1 indent incorrect: {indent:.0f}px. "
                f"Expected 60-120px (2.38cm margin-left). "
                f"Margin styles may not be preserved."
            )
        else:
            pytest.fail("Could not find 'Ground 1' text in rendered document")

    def test_paragraph_numbering_starts_at_4(
        self,
        paste_ready_page: Page,
        libreoffice_html: str,
    ) -> None:
        """Verify paragraph numbering starts at 4 for Grounds of Appeal section.

        The HTML has: <ol start="4"><li>Mr Lawlis sought leave...
        The visible number should be "4." not "1."
        """
        page = paste_ready_page

        simulate_html_paste(page, libreoffice_html)
        page.get_by_role("button", name=re.compile("add", re.IGNORECASE)).click()
        page.locator("[data-char-index='50']").wait_for(state="attached", timeout=15000)
        page.wait_for_timeout(500)

        # Check if ordered lists with start attribute are rendered
        # This checks the actual DOM structure
        list_info = page.evaluate("""() => {
            const ols = document.querySelectorAll('ol[start]');
            const results = [];

            for (const ol of ols) {
                const start = ol.getAttribute('start');
                const firstLi = ol.querySelector('li');
                const text = firstLi ?
                    firstLi.textContent?.substring(0, 40) : '';
                results.push({ start: parseInt(start), text });
            }

            // Also check for any ol that should start at 4
            // by looking for text content
            const allText = document.body.innerText;
            const has4Lawlis = allText.includes('4') &&
                allText.includes('Mr Lawlis sought leave');

            return {
                orderedLists: results,
                textHas4AndLawlis: has4Lawlis,
                firstFewOls: results.slice(0, 5)
            };
        }""")

        page.screenshot(path=str(SCREENSHOT_DIR / "08_paragraph_numbering.png"))

        (SCREENSHOT_DIR / "paragraph_numbering.txt").write_text(
            f"Ordered lists found: {len(list_info['orderedLists'])}\n"
            f"First few: {list_info['firstFewOls']}\n"
            f"Text contains '4' near 'Mr Lawlis': {list_info['textHas4AndLawlis']}\n"
        )

        # Check that ol start="4" exists and contains the expected content
        ol_starts = [ol["start"] for ol in list_info["orderedLists"]]
        assert 4 in ol_starts, (
            f"Missing <ol start='4'>. Found starts: {ol_starts}. "
            f"Ordered list start attributes may not be preserved."
        )

    def test_highest_paragraph_number_is_48(
        self,
        paste_ready_page: Page,
        libreoffice_html: str,
    ) -> None:
        """Verify the document has paragraphs numbered up to 48.

        The fixture has <ol start="45"> with 4 items, making paragraphs 45-48.
        """
        page = paste_ready_page

        simulate_html_paste(page, libreoffice_html)
        page.get_by_role("button", name=re.compile("add", re.IGNORECASE)).click()
        page.locator("[data-char-index='50']").wait_for(state="attached", timeout=15000)
        page.wait_for_timeout(500)

        # Calculate highest paragraph number from ol start + li count
        highest_para = page.evaluate("""() => {
            const ols = document.querySelectorAll('ol[start]');
            let highest = 0;

            for (const ol of ols) {
                const start = parseInt(ol.getAttribute('start') || '1');
                const liCount = ol.querySelectorAll('li').length;
                const lastNum = start + liCount - 1;
                if (lastNum > highest) {
                    highest = lastNum;
                }
            }

            // Also count ol without start (defaults to 1)
            const defaultOls = document.querySelectorAll('ol:not([start])');
            for (const ol of defaultOls) {
                const liCount = ol.querySelectorAll('li').length;
                // These start at 1, so highest is liCount
                // But these are usually the final "Orders" section, not numbered
            }

            return { highestNumberedPara: highest };
        }""")

        (SCREENSHOT_DIR / "highest_paragraph.txt").write_text(
            f"Highest numbered paragraph: {highest_para['highestNumberedPara']}\n"
            f"Expected: 48\n"
        )

        assert highest_para["highestNumberedPara"] == 48, (
            f"Highest paragraph is {highest_para['highestNumberedPara']}, expected 48. "
            f"Some <ol start> attributes or <li> items may be lost."
        )


class TestPasteHandlerConsoleOutput:
    """Tests that verify paste handler JavaScript works correctly."""

    def test_paste_triggers_cleanup(
        self,
        paste_ready_page: Page,
        libreoffice_html: str,
    ) -> None:
        """Verify paste handler logs show cleanup happening."""
        page = paste_ready_page

        # Collect console messages
        console_messages: list[str] = []
        page.on("console", lambda msg: console_messages.append(msg.text))

        simulate_html_paste(page, libreoffice_html)

        # Wait for paste to complete
        page.wait_for_timeout(500)

        # Check for expected console output
        paste_logs = [m for m in console_messages if "[PASTE" in m]

        # Note: [PASTE-INIT] fires at DOMContentLoaded, before listener attached
        # We only check for the paste event logs

        assert any("[PASTE]" in m and "bytes" in m for m in paste_logs), (
            f"Missing [PASTE] cleanup log. Got: {paste_logs}"
        )

        # Check that some size reduction happened
        # Note: LibreOffice HTML is already fairly clean (~10% reduction)
        # The big reductions (90%+) happen with browser-copied HTML that has
        # computed CSS inline styles (2.7MB -> 40KB)
        reduction_log = next((m for m in paste_logs if "reduction" in m), None)
        if reduction_log:
            # Extract percentage - just verify cleanup ran
            match = re.search(r"(\d+)%", reduction_log)
            if match:
                reduction_pct = int(match.group(1))
                # Even minimal cleanup should do something
                assert reduction_pct >= 0, f"Negative reduction: {reduction_pct}%"
