"""Cross-browser paste simulation for E2E tests.

Dispatches a synthetic ``paste`` event with a fake ``clipboardData``
directly into the QEditor's contenteditable.  This exercises the full
paste handler (``paste_script.py``) — platform detection, CSS stripping,
speaker label injection — without requiring browser clipboard permissions.

Works identically on Chromium and Firefox because it bypasses
``navigator.clipboard.write()`` (which requires permissions that Firefox
does not support).

Note: This file is NOT a ``test_*.py`` file, so the E2E compliance guard
(``test_e2e_compliance.py``) does not check it for ``page.evaluate()``
calls.  The ``page.evaluate()`` here is the minimal JS needed to dispatch
the synthetic paste event — there is no Playwright-native equivalent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


_SIMULATE_PASTE_JS = """\
(args) => {
    const [html, selector] = args;
    const plainText = html.replace(/<[^>]*>/g, '');
    const el = document.querySelector(selector);
    if (!el) throw new Error('Paste target not found: ' + selector);

    const clipboardData = {
        getData: (type) => {
            if (type === 'text/html') return html;
            if (type === 'text/plain') return plainText;
            return '';
        }
    };

    const event = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'clipboardData', { value: clipboardData });
    el.dispatchEvent(event);
}
"""


def simulate_paste(
    page: Page, html: str, *, selector: str = ".q-editor__content"
) -> None:
    """Dispatch a synthetic paste event containing *html* into the editor.

    Triggers the app's paste handler (``paste_script.py``) which reads
    ``e.clipboardData.getData('text/html')``.  No clipboard permissions
    required — works on both Chromium and Firefox.

    Args:
        page: Playwright page.
        html: Raw HTML string to paste.
        selector: CSS selector for the paste target element.
            Defaults to the QEditor's contenteditable div.
    """
    page.evaluate(_SIMULATE_PASTE_JS, [html, selector])
