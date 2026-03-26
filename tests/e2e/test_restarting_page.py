"""E2E tests for the /restarting holding page.

Traceability:
- Issue: #355 (Graceful restart)
- Phase: 4 (Restarting page)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


def _wait_for_redirect(page: Page, *, timeout: int = 15000) -> None:
    """Wait until the page URL no longer contains '/restarting'.

    Uses ``wait_for_function`` to poll ``window.location.href`` from the
    browser, avoiding Playwright's navigation-event-based ``wait_for_url``
    which can miss JS-driven ``window.location.href`` redirects in NiceGUI's
    SPA environment.
    """
    page.wait_for_function(
        "() => !window.location.href.includes('/restarting')",
        timeout=timeout,
    )


class TestRestartingPage:
    """Tests for /restarting healthz polling and redirect."""

    def test_shows_restarting_message(self, fresh_page: Page, app_server: str) -> None:
        """AC3.1: /restarting displays the updating message."""
        fresh_page.goto(f"{app_server}/restarting?return=/")
        expect(fresh_page.get_by_test_id("restarting-message")).to_be_visible()
        expect(fresh_page.get_by_test_id("restarting-status")).to_be_visible()

    def test_redirects_to_return_url(self, fresh_page: Page, app_server: str) -> None:
        """AC3.1: page polls /healthz and redirects to return URL."""
        fresh_page.goto(f"{app_server}/restarting?return=/")

        # Dev server /healthz is already up: poll (2s) + jitter (1-5s)
        # = 3-7s expected redirect time.
        _wait_for_redirect(fresh_page)

    def test_redirect_not_instant(self, fresh_page: Page, app_server: str) -> None:
        """AC3.2: redirect includes jitter (not instant)."""
        fresh_page.goto(f"{app_server}/restarting?return=/")

        # Should NOT redirect within 1s (poll=2s + jitter>=1s = 3s min)
        time.sleep(1.0)
        assert "/restarting" in fresh_page.url

        # But should redirect eventually
        _wait_for_redirect(fresh_page)

    def test_missing_return_param_defaults_to_home(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """AC3.3: no return param redirects to /."""
        fresh_page.goto(f"{app_server}/restarting")

        # Should eventually redirect to home (root path)
        _wait_for_redirect(fresh_page)
        # URL should be at root or auth redirect from root — not /restarting
        from urllib.parse import urlparse

        path = urlparse(fresh_page.url).path
        assert path in ("/", "/login") or path.startswith("/authenticate"), (
            f"Expected redirect to / or auth page, got {path}"
        )
