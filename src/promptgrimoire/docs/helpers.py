"""Playwright interaction helpers shared between guide scripts and E2E tests.

These functions are pure Playwright interactions (mouse events, page
evaluations, DOM waits) with no test-specific dependencies, making them
suitable for the production docs package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


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
        diag = page.evaluate(
            "() => {"
            " const d = document.getElementById('doc-container');"
            " return {"
            "   doc: d ? d.innerHTML.substring(0, 200) : 'NO #doc-container',"
            "   walkDefined: typeof walkTextNodes !== 'undefined',"
            "   textNodes: window._textNodes ? window._textNodes.length : null,"
            "   scripts: Array.from(document.querySelectorAll('script[src]'))"
            "     .map(s => s.src).filter(s => s.includes('annotation'))"
            " }; }"
        )
        msg = (
            f"Text walker timeout ({timeout}ms). URL: {url}"
            f" doc-container: {diag['doc']!r}"
            f" walkTextNodes defined: {diag['walkDefined']}"
            f" _textNodes: {diag['textNodes']}"
            f" annotation scripts: {diag['scripts']}"
        )
        raise type(exc)(msg) from None


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
