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

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


def select_chars(page: Page, start_char: int, end_char: int) -> None:
    """Select a range of characters by mouse drag.

    Uses Playwright's native mouse API to drag-select text from start_char
    to end_char (inclusive).

    Args:
        page: Playwright page.
        start_char: Index of first character to select.
        end_char: Index of last character to select (inclusive).
    """
    char_start = page.locator(f"[data-char-index='{start_char}']")
    char_end = page.locator(f"[data-char-index='{end_char}']")

    char_start.scroll_into_view_if_needed()
    expect(char_start).to_be_visible(timeout=5000)

    # Get bounding boxes for precise mouse positioning
    start_box = char_start.bounding_box()
    end_box = char_end.bounding_box()

    if not start_box or not end_box:
        raise ValueError("Could not get bounding boxes for char elements")

    # Drag from left edge of start char to right edge of end char
    start_x = start_box["x"] + 1
    start_y = start_box["y"] + start_box["height"] / 2
    end_x = end_box["x"] + end_box["width"] - 1
    end_y = end_box["y"] + end_box["height"] / 2

    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y)
    page.mouse.up()


# Deprecated alias for backwards compatibility during migration
select_words = select_chars


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
    """Navigate to annotation page, create workspace, and add document content.

    This is the common 5-step setup pattern shared by all annotation tests:
    1. Navigate to /annotation
    2. Click create workspace
    3. Wait for workspace URL
    4. Fill content
    5. Submit and wait for word spans

    The helper is page-agnostic: it works with single-user tests, multi-user
    sync tests, or any other context that provides a Playwright page.

    Args:
        page: Playwright page (can be from any browser context).
        app_server: Base URL of the app server.
        content: Text content to add as document.

    Traceability:
        Extracted from repetitive setup code across 15+ test classes.
        See test_annotation_page.py commit history for original patterns.
    """
    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
    content_input.fill(content)
    page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
    page.wait_for_selector("[data-char-index]")
    page.wait_for_timeout(200)


def setup_workspace_with_content_highlight_api(
    page: Page, app_server: str, content: str
) -> None:
    """Set up a workspace and wait for CSS Highlight API initialisation.

    Unlike ``setup_workspace_with_content`` which waits for ``[data-char-index]``
    (char spans), this waits for the text walker to initialise by checking
    ``window._textNodes`` is populated.

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

    # Confirm the content type dialog that appears after adding content
    confirm_btn = page.get_by_role("button", name=re.compile("confirm", re.IGNORECASE))
    confirm_btn.wait_for(state="visible", timeout=5000)
    confirm_btn.click()

    # Wait for the text walker to initialise (replaces waiting for char spans)
    page.wait_for_function(
        "() => window._textNodes && window._textNodes.length > 0",
        timeout=10000,
    )
    page.wait_for_timeout(200)


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
