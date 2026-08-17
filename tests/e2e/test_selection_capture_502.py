"""E2E regression tests for event-carried selection in tag application (#502).

python-socketio dispatches socket events as concurrent tasks, so a
tag-apply could be processed before its ``selection_made`` event and
silently no-op (~7-11% of highlight actions under load, per
docs/investigations/2026-08-16-production-pool-load-curve.md).

These tests deliver the tag-apply with ``selection_made`` suppressed
entirely — the limiting case of "apply processed first" — and assert
exactly one highlight lands at the intended offsets, because the apply
event itself carries the offsets captured client-side at trigger time.

Acceptance criteria (issue #502):
- Apply delivered before/without ``selection_made`` still creates
  exactly one highlight at the intended offsets (toolbar + keyboard).
- A genuinely selection-less apply gets visible ``ui.notify`` feedback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from promptgrimoire.docs.helpers import select_chars
from tests.e2e.fixture_loaders import setup_workspace_with_content
from tests.e2e.highlight_tools import find_text_range, wait_for_css_highlight

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Test-side JS interception, justified per the no-JS-injection rule:
# the #502 race is a server-side task-ordering hazard (apply processed
# before its selection_made).  No behavioural driver can force that
# ordering deterministically — a real race would flake by construction.
# Dropping selection_made delivery is the reproducible limiting case of
# "apply arrives first"; everything else in these tests (selection,
# clicks, key presses, assertions) is real browser behaviour.
_SUPPRESS_SELECTION_MADE_JS = """() => {
    const orig = window.emitEvent;
    window.emitEvent = function(name, ...args) {
        if (name === 'selection_made') return;
        return orig.apply(this, [name, ...args]);
    };
}"""

_REGISTERED_HIGHLIGHT_OFFSETS_JS = """() => {
    const c = document.querySelector('[data-testid="doc-container"]');
    const nodes = walkTextNodes(c);
    const out = [];
    for (const [name, hl] of CSS.highlights.entries()) {
        if (!name.startsWith('hl-')) continue;
        for (const r of hl) {
            out.push([
                rangePointToCharOffset(nodes, r.startContainer, r.startOffset),
                rangePointToCharOffset(nodes, r.endContainer, r.endOffset),
            ]);
        }
    }
    return out;
}"""

_CONTENT = "The plaintiff suffered a workplace injury on the first day."


class TestSelectionCapture502:
    """Tag application must not depend on selection_made event ordering."""

    def test_toolbar_apply_without_selection_made_event(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Toolbar click with selection_made suppressed creates the highlight.

        The click's js_handler carries the offsets captured client-side,
        so the server never needs the separate selection event.
        """
        page = authenticated_page
        setup_workspace_with_content(page, app_server, _CONTENT)

        page.evaluate(_SUPPRESS_SELECTION_MADE_JS)
        start, end = find_text_range(page, "workplace injury")
        select_chars(page, start, end)

        page.locator("[data-testid='tag-toolbar'] button").first.click()

        wait_for_css_highlight(page)
        offsets = page.evaluate(_REGISTERED_HIGHLIGHT_OFFSETS_JS)
        # select_chars drags through its end index inclusively, so the
        # browser action covers [start, end + 1) in exclusive offsets.
        assert offsets == [[start, end + 1]], (
            f"expected exactly one highlight at [{start}, {end + 1}], got {offsets}"
        )

    def test_keyboard_apply_without_selection_made_event(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Keyboard shortcut carries the selection in its own event args."""
        page = authenticated_page
        setup_workspace_with_content(page, app_server, _CONTENT)

        page.evaluate(_SUPPRESS_SELECTION_MADE_JS)
        start, end = find_text_range(page, "first day")
        select_chars(page, start, end)

        page.keyboard.press("1")

        wait_for_css_highlight(page)
        offsets = page.evaluate(_REGISTERED_HIGHLIGHT_OFFSETS_JS)
        # See toolbar test: select_chars' end index is drag-inclusive.
        assert offsets == [[start, end + 1]], (
            f"expected exactly one highlight at [{start}, {end + 1}], got {offsets}"
        )

    def test_apply_with_no_selection_notifies(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """A click with no browser selection shows visible feedback."""
        page = authenticated_page
        setup_workspace_with_content(page, app_server, _CONTENT)

        page.locator("[data-testid='tag-toolbar'] button").first.click()

        expect(page.locator(".q-notification")).to_contain_text("No selection")
