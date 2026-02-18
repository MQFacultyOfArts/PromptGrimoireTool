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

import gzip
import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page


def select_chars(page: Page, start_char: int, end_char: int) -> None:
    """Select a character range using mouse events.

    Uses the text walker (annotation-highlight.js) to convert char offsets
    to screen coordinates, then performs a mouse click-drag selection.

    Ensures the text walker is ready before attempting coordinate lookup,
    since tab switches can momentarily destroy and rebuild the DOM.

    Args:
        page: Playwright page.
        start_char: Index of first character to select.
        end_char: Index of last character to select (inclusive).
    """
    # Ensure text walker and doc-container are ready (tab switches can
    # rebuild the DOM after _textNodes was cached).
    wait_for_text_walker(page, timeout=10000)

    # Get bounding rectangles for start and end positions via text walker.
    # charOffsetToRect() handles StaticRange -> live Range conversion
    # internally (charOffsetToRange() returns StaticRange which does NOT
    # have getBoundingClientRect()).
    coords = page.evaluate(
        """([startChar, endChar]) => {
            const container = document.getElementById('doc-container');
            if (!container || typeof walkTextNodes === 'undefined') return null;
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


def setup_workspace_with_content(
    page: Page, app_server: str, content: str, *, timeout: int = 15000
) -> None:
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
        timeout: Max wait for text walker init (ms). Increase for late-running tests.

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
    wait_for_text_walker(page, timeout=timeout)
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


def _load_fixture_via_paste(page: Page, app_server: str, fixture_path: Path) -> None:
    """Load an HTML fixture into a new workspace via clipboard paste.

    Expects an already-authenticated page. Creates a new workspace, loads
    the HTML fixture via clipboard paste (simulating real user interaction),
    handles content type confirmation, and waits for text walker readiness.

    Args:
        page: Playwright page (must be already authenticated).
        app_server: Base URL of the app server.
        fixture_path: Path to HTML fixture (.html or .html.gz).

    Note:
        The browser context MUST have been created with clipboard permissions:
        ``permissions=["clipboard-read", "clipboard-write"]``
        This is the caller's responsibility.

    Traceability:
        Part of E2E test migration (#156) to unify fixture loading patterns
        and reduce test code duplication.
    """
    # Navigate and create workspace
    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    # Read fixture HTML (handle both .html.gz and plain .html)
    if fixture_path.suffix == ".gz":
        with gzip.open(fixture_path, "rt", encoding="utf-8") as f:
            html_content = f.read()
    else:
        html_content = fixture_path.read_text(encoding="utf-8")

    # Focus the editor
    editor = page.locator(".q-editor__content")
    expect(editor).to_be_visible()
    editor.click()

    # Write HTML to clipboard (same pattern as test_html_paste_whitespace.py)
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
    page.wait_for_timeout(100)

    # Trigger paste
    page.keyboard.press("Control+v")
    page.wait_for_timeout(500)

    # Wait for "Content pasted" confirmation
    expect(editor).to_contain_text("Content pasted", timeout=5000)

    # Click "Add Document" button. For pasted HTML, the content type dialog
    # is skipped (content_form.py auto-detects paste as HTML). The app
    # processes the input and navigates back to the annotation page.
    page.get_by_role("button", name=re.compile("add document", re.IGNORECASE)).click()

    # Wait for text walker readiness (large fixtures like AustLII need time).
    wait_for_text_walker(page, timeout=30000)


def wait_for_text_walker(page: Page, *, timeout: int = 15000) -> None:
    """Wait for the text walker to initialise (readiness gate).

    This is a synchronisation wait, not a test assertion. It ensures
    the text walker has built its node map before any interactions that
    depend on character offsets or highlight rendering.

    Args:
        page: Playwright page.
        timeout: Maximum wait time in milliseconds.
    """
    try:
        page.wait_for_function(
            "() => document.getElementById('doc-container')"
            " && window._textNodes && window._textNodes.length > 0",
            timeout=timeout,
        )
    except Exception as exc:
        if "Timeout" not in type(exc).__name__:
            raise
        # Capture diagnostic state for debugging
        url = page.url
        doc_html = page.evaluate(
            "() => { const d = document.getElementById('doc-container');"
            " return d ? d.innerHTML.substring(0, 200) : 'NO #doc-container'; }"
        )
        msg = (
            f"Text walker timeout ({timeout}ms). URL: {url} doc-container: {doc_html!r}"
        )
        raise type(exc)(msg) from None
