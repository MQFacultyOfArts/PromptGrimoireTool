"""E2E tests for browser feature gate (CSS Custom Highlight API).

Verifies that the login page gates on CSS.highlights support:
- AC4.1: Supported browsers see the normal login UI
- AC4.2: Unsupported browsers see an upgrade message overlay

Traceability:
- AC: css-highlight-api.AC4.1, css-highlight-api.AC4.2
- Design: docs/implementation-plans/2026-02-11-css-highlight-api-150/phase_01.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


class TestBrowserGate:
    """Tests for the browser feature gate on /login."""

    def test_supported_browser_sees_login_ui(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """AC4.1: Supported browser (Playwright Chromium) sees login UI, no overlay.

        Playwright uses Chromium which supports CSS.highlights. The login
        page should render normally with no upgrade message visible.
        """
        fresh_page.goto(f"{app_server}/login")

        # Login UI elements should be visible
        expect(fresh_page.get_by_test_id("email-input")).to_be_visible()
        expect(fresh_page.get_by_test_id("send-magic-link-btn")).to_be_visible()

        # The upgrade overlay should NOT be present
        overlay = fresh_page.locator("#browser-gate-overlay")
        expect(overlay).to_have_count(0)

    def test_unsupported_browser_sees_upgrade_message(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """AC4.2: Unsupported browser sees upgrade overlay covering login UI.

        Simulates an unsupported browser by deleting CSS.highlights and
        re-invoking the gate check function. The overlay should appear
        and cover the login UI.
        """
        fresh_page.goto(f"{app_server}/login")

        # Verify login UI renders first (baseline)
        expect(fresh_page.get_by_test_id("email-input")).to_be_visible()

        # Simulate unsupported browser: delete CSS.highlights and re-check
        fresh_page.evaluate("""() => {
            delete CSS.highlights;
            window.__checkBrowserGate();
        }""")

        # The upgrade overlay should now be visible
        overlay = fresh_page.locator("#browser-gate-overlay")
        expect(overlay).to_be_visible()

        # Overlay should contain the upgrade message text
        expect(overlay).to_contain_text(
            "Your browser does not support features required by PromptGrimoire"
        )
        expect(overlay).to_contain_text("Chrome 105+")
        expect(overlay).to_contain_text("Firefox 140+")
        expect(overlay).to_contain_text("Safari 17.2+")
        expect(overlay).to_contain_text("Edge 105+")

        # The "Go Home" link should be present
        go_home = overlay.locator("a[href='/']")
        expect(go_home).to_be_visible()
        expect(go_home).to_contain_text("Go Home")
