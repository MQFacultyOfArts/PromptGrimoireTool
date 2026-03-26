"""Highlight creation and text selection helpers for annotation E2E tests.

Provides functions to create highlights, find text ranges, select text,
scroll to positions, and wait for CSS Highlight API updates.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from promptgrimoire.docs.helpers import select_chars, wait_for_text_walker

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)


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


def find_text_range(page: Page, needle: str) -> tuple[int, int]:
    """Find a text substring in the document and return its char offsets.

    Walks the browser's text nodes (the same nodes used by select_chars
    and the highlight system), concatenates their content, and searches
    for ``needle``.  Returns ``(start_char, end_char)`` suitable for
    passing to ``select_chars`` or ``create_highlight_with_tag``.

    This avoids hardcoding char offsets that break when fixture HTML
    changes or when CSS layout shifts content to different positions.

    Args:
        page: Playwright page with text walker initialised.
        needle: The text to search for in the document's visible content.

    Returns:
        Tuple of (start_char, end_char) for the first occurrence.

    Raises:
        ValueError: If the needle is not found in the document text.
    """
    wait_for_text_walker(page, timeout=10000)
    result = page.evaluate(
        """(needle) => {
            const container = document.querySelector('[data-testid=\"doc-container\"]');
            if (!container || typeof walkTextNodes === 'undefined')
                return { error: 'text walker not ready' };
            const nodes = walkTextNodes(container);
            const total = nodes.length > 0
                ? nodes[nodes.length - 1].endChar : 0;

            // Build the collapsed text and a parallel array mapping
            // each code-point index to its walker char offset.
            // IMPORTANT: iterate with for-of (code points), matching
            // the production walkTextNodes which uses for-of.  A plain
            // for(i) loop iterates UTF-16 code units and miscounts
            // surrogate pairs (emoji), causing early termination.
            const codePoints = [];   // codePoints[i] = one code point
            const offsetMap = [];    // offsetMap[i] = walker char offset
            for (const entry of nodes) {
                const len = entry.endChar - entry.startChar;
                const raw = entry.node.textContent;
                let prev = false;
                let col = 0;
                for (const ch of raw) {
                    if (col >= len) break;
                    if (/[\\s\\u00a0]/.test(ch)) {
                        if (!prev) {
                            offsetMap.push(entry.startChar + col);
                            codePoints.push(' ');
                            col++; prev = true;
                        }
                    } else {
                        offsetMap.push(entry.startChar + col);
                        codePoints.push(ch);
                        col++; prev = false;
                    }
                }
            }
            // Search using code-point array (not string indexOf which
            // counts UTF-16 code units for .length and index).
            const needleCPs = [...needle];
            let idx = -1;
            outer: for (let i = 0; i <= codePoints.length - needleCPs.length; i++) {
                for (let j = 0; j < needleCPs.length; j++) {
                    if (codePoints[i + j] !== needleCPs[j]) continue outer;
                }
                idx = i;
                break;
            }
            if (idx === -1)
                return { error: 'not found', textLength: total };
            const endIdx = idx + needleCPs.length;
            // Use the next code point's offset if available; otherwise
            // use the last matched code point's offset.
            const end = endIdx < offsetMap.length
                ? offsetMap[endIdx]
                : offsetMap[endIdx - 1];
            return { start: offsetMap[idx], end };
        }""",
        needle,
    )
    if "error" in result:
        snippet = result.get("snippet", "")
        msg = (
            f"find_text_range: {result['error']} for {needle!r}"
            f" (textLength={result.get('textLength')},"
            f" first 500 chars: {snippet!r})"
        )
        raise ValueError(msg)
    return (result["start"], result["end"])


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

    # Log the coordinates that select_chars computed for the mouse drag.
    coord_state = page.evaluate(
        """([startChar, endChar]) => {
            const c = document.querySelector('[data-testid=\"doc-container\"]');
            if (!c) return { error: 'no doc-container' };
            const nodes = walkTextNodes(c);
            const sr = charOffsetToRect(nodes, startChar);
            const er = charOffsetToRect(nodes, endChar);
            // Also grab the text at those offsets
            let text = '';
            try {
                const range = charOffsetToRange(nodes, startChar, endChar);
                if (range) {
                    const r = document.createRange();
                    r.setStart(range.startContainer, range.startOffset);
                    r.setEnd(range.endContainer, range.endOffset);
                    text = r.toString().substring(0, 80);
                }
            } catch(e) { text = 'error: ' + e.message; }
            return {
                startRect: { x: sr.left, y: sr.top, w: sr.width, h: sr.height },
                endRect: { x: er.left, y: er.top, w: er.width, h: er.height },
                text: text,
                scrollY: window.scrollY,
                viewportH: window.innerHeight,
            };
        }""",
        [start_char, end_char],
    )
    logger.debug(
        "create_highlight_with_tag PRE-SELECT coords=%s",
        coord_state,
    )

    sel_state = page.evaluate(
        """() => {
            const s = window.getSelection();
            return {
                exists: !!s,
                isCollapsed: s ? s.isCollapsed : null,
                rangeCount: s ? s.rangeCount : 0,
                text: s ? s.toString().substring(0, 80) : '',
                anchorNode: s && s.anchorNode ? s.anchorNode.nodeName : null,
            };
        }"""
    )
    toolbar_state = page.evaluate(
        """() => {
            const tb = document.querySelector('[data-testid="tag-toolbar"]');
            if (!tb) return { found: false };
            const btns = tb.querySelectorAll('button');
            return {
                found: true,
                buttonCount: btns.length,
                buttonTexts: Array.from(btns).slice(0, 12)
                    .map(b => b.textContent.trim().substring(0, 30)),
            };
        }"""
    )
    logger.debug(
        "create_highlight_with_tag chars=%d-%d tag_index=%d selection=%s toolbar=%s",
        start_char,
        end_char,
        tag_index,
        sel_state,
        toolbar_state,
    )

    tag_button = page.locator("[data-testid='tag-toolbar'] button").nth(tag_index)
    tag_button.click()


def select_text_range(page: Page, text: str) -> None:
    """Select a text substring in the document container by evaluating JS.

    Uses the browser's native selection API to select the given text
    within the doc-container. This approach works without char spans.

    Args:
        page: Playwright page.
        text: The text substring to select.
    """
    page.evaluate(
        """(text) => {
            const container = document.querySelector('[data-testid=\"doc-container\"]');
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
    page.locator("[data-testid='tag-toolbar']").wait_for(state="visible", timeout=5000)


def scroll_to_char(page: Page, char_offset: int) -> None:
    """Scroll the document so that the given character offset is visible.

    Uses ``scrollToCharOffset()`` from annotation-highlight.js.
    After scrolling, waits briefly for card positioning to update
    (cards are hidden when their highlight is off-screen).

    Args:
        page: Playwright page.
        char_offset: Character index to scroll into view.
    """
    wait_for_text_walker(page, timeout=10000)
    page.evaluate(
        """(charIdx) => {
            const c = document.querySelector('[data-testid=\"doc-container\"]');
            if (!c) return;
            const nodes = walkTextNodes(c);
            scrollToCharOffset(nodes, charIdx, charIdx);
        }""",
        char_offset,
    )
    page.wait_for_function("new Promise(r => requestAnimationFrame(r))")


def wait_for_css_highlight(page: Page, *, timeout: int = 5000) -> None:
    """Wait until at least one ``hl-*`` entry exists in ``CSS.highlights``.

    Use after clicking a tag button to ensure the highlight round-trip
    (server save + CRDT broadcast + client CSS update) has completed.
    Replaces fragile ``wait_for_timeout`` sleeps.
    """
    page.wait_for_function(
        """() => {
            for (const k of CSS.highlights.keys()) {
                if (k.startsWith('hl-')) return true;
            }
            return false;
        }""",
        timeout=timeout,
    )


def wait_for_css_highlight_count(
    page: Page, count: int, *, timeout: int = 5000
) -> None:
    """Wait until exactly *count* ``hl-*`` entries exist in ``CSS.highlights``."""
    page.wait_for_function(
        """(expected) => {
            let n = 0;
            for (const k of CSS.highlights.keys()) {
                if (k.startsWith('hl-')) n++;
            }
            return n >= expected;
        }""",
        arg=count,
        timeout=timeout,
    )
