"""Shared helper functions for annotation E2E tests.

These helpers extract common patterns used across annotation test files,
reducing duplication and ensuring consistent test setup.

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/design-plans/2026-01-30-workspace-model.md
- Test consolidation: docs/design-plans/2026-01-31-test-suite-consolidation.md
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


def select_chars(page: Page, start_char: int, end_char: int) -> None:
    """Select a character range using mouse events.

    Uses the text walker (annotation-highlight.js) to convert char offsets
    to screen coordinates, then performs a mouse click-drag selection.

    Args:
        page: Playwright page.
        start_char: Index of first character to select.
        end_char: Index of last character to select (inclusive).
    """
    # Get bounding rectangles for start and end positions via text walker.
    # charOffsetToRect() handles StaticRange -> live Range conversion
    # internally (charOffsetToRange() returns StaticRange which does NOT
    # have getBoundingClientRect()).
    coords = page.evaluate(
        """([startChar, endChar]) => {
            const container = document.getElementById('doc-container');
            if (typeof walkTextNodes === 'undefined') return null;
            const nodes = walkTextNodes(container);
            const startRect = charOffsetToRect(nodes, startChar);
            const endRect = charOffsetToRect(nodes, endChar);
            if (startRect.width === 0 && startRect.height === 0) return null;
            if (endRect.width === 0 && endRect.height === 0) return null;
            return {
                startX: startRect.left + 1,
                startY: startRect.top + startRect.height / 2,
                endX: endRect.right - 1,
                endY: endRect.top + endRect.height / 2
            };
        }""",
        [start_char, end_char],
    )
    if coords is None:
        msg = (
            "Could not get char coordinates"
            " -- text walker not loaded or offsets out of range"
        )
        raise RuntimeError(msg)

    # Scroll to the start position first so it is in viewport
    page.evaluate(
        """([startChar, endChar]) => {
            const container = document.getElementById('doc-container');
            const nodes = walkTextNodes(container);
            scrollToCharOffset(nodes, startChar, endChar);
        }""",
        [start_char, end_char],
    )
    page.wait_for_timeout(300)

    # Re-query coordinates after scroll (positions change)
    coords = page.evaluate(
        """([startChar, endChar]) => {
            const container = document.getElementById('doc-container');
            const nodes = walkTextNodes(container);
            const startRect = charOffsetToRect(nodes, startChar);
            const endRect = charOffsetToRect(nodes, endChar);
            return {
                startX: startRect.left + 1,
                startY: startRect.top + startRect.height / 2,
                endX: endRect.right - 1,
                endY: endRect.top + endRect.height / 2
            };
        }""",
        [start_char, end_char],
    )

    # Perform mouse-based selection (real user interaction)
    page.mouse.click(coords["startX"], coords["startY"])
    page.mouse.move(coords["startX"], coords["startY"])
    page.mouse.down()
    page.mouse.move(coords["endX"], coords["endY"])
    page.mouse.up()


def create_highlight(page: Page, start_char: int, end_char: int) -> None:
    """Select characters and click the first tag button to create a highlight.

    Args:
        page: Playwright page.
        start_char: Index of first character to select.
        end_char: Index of last character to select.
    """
    select_chars(page, start_char, end_char)
    tag_button = page.locator("[data-testid='tag-toolbar'] button").first
    tag_button.click()


def create_highlight_with_tag(
    page: Page, start_char: int, end_char: int, tag_index: int
) -> None:
    """Select characters and click a specific tag button to create a highlight.

    Args:
        page: Playwright page.
        start_char: Index of first character to select.
        end_char: Index of last character to select.
        tag_index: 0-based index of tag button to click
            (0=Jurisdiction, 1=Procedural History, etc).
    """
    select_chars(page, start_char, end_char)
    tag_button = page.locator("[data-testid='tag-toolbar'] button").nth(tag_index)
    tag_button.click()


def setup_workspace_with_content(page: Page, app_server: str, content: str) -> None:
    """Navigate to annotation page, create workspace, and add content.

    Common setup pattern shared by all annotation tests:
    1. Navigate to /annotation
    2. Click create workspace
    3. Wait for workspace URL
    4. Fill content
    5. Submit and wait for text walker initialisation

    Args:
        page: Playwright page (can be from any browser context).
        app_server: Base URL of the app server.
        content: Text content to add as document.

    Traceability:
        Extracted from repetitive setup code across 15+ test classes.
    """
    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
    content_input.fill(content)
    page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()

    # Confirm the content type dialog
    confirm_btn = page.get_by_role("button", name=re.compile("confirm", re.IGNORECASE))
    confirm_btn.wait_for(state="visible", timeout=5000)
    confirm_btn.click()

    # Wait for the text walker to initialise
    page.wait_for_function(
        "() => window._textNodes && window._textNodes.length > 0",
        timeout=10000,
    )
    page.wait_for_timeout(200)


# Alias kept for callers that imported the _highlight_api variant.
# Both functions are now identical (char spans are gone).
setup_workspace_with_content_highlight_api = setup_workspace_with_content


def select_text_range(page: Page, text: str) -> None:
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
