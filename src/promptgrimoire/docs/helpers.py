"""Playwright interaction helpers shared between guide scripts and E2E tests.

These functions are pure Playwright interactions (mouse events, page
evaluations, DOM waits) with no test-specific dependencies, making them
suitable for the production docs package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


def wait_for_annotation_ready(page: Page, *, timeout: int = 15000) -> None:
    """Wait for the annotation page's deferred load to complete.

    The annotation page uses ``background_tasks.create()`` to load
    workspace content after the page handler returns.  This helper
    waits for the background task to signal completion via
    ``window.__loadComplete``.

    Must be called after navigating to ``/annotation?workspace_id=…``.
    No-op if the current URL does not contain ``workspace_id=``
    (non-deferred pages like the create-workspace form).

    Fails fast with diagnostic state when the load doesn't complete
    within *timeout* ms.

    Args:
        page: Playwright page.
        timeout: Maximum wait time in milliseconds.
    """
    if "workspace_id=" not in page.url:
        return

    try:
        page.wait_for_function(
            "() => window.__loadComplete === true",
            timeout=timeout,
        )
    except Exception as exc:
        if "Timeout" not in type(exc).__name__:
            raise
        url = page.url
        diag = page.evaluate(
            "() => ({"
            "  loadComplete: window.__loadComplete,"
            "  spinner: !!document.querySelector("
            "    '[data-testid=\"workspace-loading-spinner\"]'),"
            "  statusMsg: (document.querySelector("
            "    '[data-testid=\"workspace-status-msg\"]')"
            "    || {}).textContent || null,"
            "  scripts: Array.from("
            "    document.querySelectorAll('script[src]'))"
            "    .map(s => s.src)"
            "    .filter(s => s.includes('annotation'))"
            "})"
        )
        msg = (
            f"Annotation page deferred load timeout"
            f" ({timeout}ms). URL: {url}"
            f" __loadComplete: {diag['loadComplete']}"
            f" spinner visible: {diag['spinner']}"
            f" status: {diag['statusMsg']!r}"
            f" scripts: {diag['scripts']}"
        )
        raise type(exc)(msg) from None


def wait_for_text_walker(page: Page, *, timeout: int = 15000) -> None:
    """Wait for the text walker to initialise (readiness gate).

    This is a synchronisation wait, not a test assertion. It ensures
    the text walker has built its node map before any interactions that
    depend on character offsets or highlight rendering.

    On annotation pages with deferred loading, waits for
    ``__loadComplete`` first (via :func:`wait_for_annotation_ready`).

    Args:
        page: Playwright page.
        timeout: Maximum wait time in milliseconds.
    """
    # Gate on deferred load completion before checking text walker
    wait_for_annotation_ready(page, timeout=timeout)

    try:
        page.wait_for_function(
            "() => document.querySelector('[data-testid=\"doc-container\"]')"
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
            " const d = document.querySelector('[data-testid=\"doc-container\"]');"
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
            const container = document.querySelector('[data-testid="doc-container"]');
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

    # Scroll to the start position so it is in viewport.
    # Uses instant scroll (no animation) so coordinates are immediately
    # stable — avoids a fragile wait_for_timeout after smooth scroll.
    # Scrolls both vertically AND horizontally to handle content that
    # renders outside the viewport (e.g. AustLII inline styles).
    page.evaluate(
        """([startChar, endChar]) => {
            const container = document.querySelector('[data-testid="doc-container"]');
            const nodes = walkTextNodes(container);
            const sr = charOffsetToRange(nodes, startChar, endChar);
            if (!sr) return;
            const r = document.createRange();
            r.setStart(sr.startContainer, sr.startOffset);
            r.setEnd(sr.endContainer, sr.endOffset);
            const rect = r.getBoundingClientRect();
            const targetY = rect.top + window.scrollY
                - window.innerHeight / 2 + rect.height / 2;
            const targetX = rect.left + window.scrollX
                - window.innerWidth / 2 + rect.width / 2;
            window.scrollTo({
                top: Math.max(0, targetY),
                left: Math.max(0, targetX),
                behavior: 'instant',
            });
        }""",
        [start_char, end_char],
    )

    # Re-query coordinates after scroll (positions change)
    coords = page.evaluate(
        """([startChar, endChar]) => {
            const container = document.querySelector('[data-testid="doc-container"]');
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
