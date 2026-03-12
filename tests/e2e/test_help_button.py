"""E2E tests for the in-app help button.

Verifies the help button renders in the header and is clickable when
``HELP__HELP_ENABLED=true``.  Tests use the ``mkdocs`` backend (no
Algolia credentials required).

The disabled state (``help_enabled=False``) is covered by unit tests
in ``tests/unit/test_help_button.py`` — per-test env-var switching is
not feasible because the E2E server's config is fixed at startup.

Traceability:
- Issue: #281 (Documentation Flight Rules)
- AC: docs-flight-rules-230.AC5.1, docs-flight-rules-230.AC5.3
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


class TestHelpButton:
    """Help button visibility and click behaviour in mkdocs mode."""

    def test_help_button_visible_when_enabled(self, authenticated_page: Page) -> None:
        """Help button renders in header when help_enabled=True (AC5.1)."""
        help_btn = authenticated_page.get_by_test_id("help-btn")
        help_btn.wait_for(state="visible", timeout=10_000)

    def test_help_button_clickable(self, authenticated_page: Page) -> None:
        """Clicking help button in mkdocs mode opens docs URL in new tab (AC5.3).

        The mkdocs backend calls ``ui.navigate.to(url, new_tab=True)`` which
        invokes ``window.open(url, "_blank")``.  We intercept ``window.open``
        to capture the target URL without relying on the docs server being
        reachable from the test environment.
        """
        help_btn = authenticated_page.get_by_test_id("help-btn")
        help_btn.wait_for(state="visible", timeout=10_000)

        # Intercept window.open to capture the URL without actually opening
        # a new tab (the docs server is not running during E2E tests).
        authenticated_page.evaluate(
            """() => {
                window.__helpOpenedUrl = null;
                window.__origOpen = window.open;
                window.open = (url, target) => {
                    window.__helpOpenedUrl = url;
                    return null;
                };
            }"""
        )

        # Capture console errors during click
        errors: list[str] = []
        authenticated_page.on("pageerror", lambda exc: errors.append(str(exc)))

        help_btn.click()

        # Give NiceGUI WebSocket time to deliver the open command
        authenticated_page.wait_for_function(
            "() => window.__helpOpenedUrl !== null",
            timeout=5_000,
        )

        opened_url = authenticated_page.evaluate("() => window.__helpOpenedUrl")
        assert "/docs/" in opened_url, f"Expected docs URL, got: {opened_url}"

        # Restore original window.open
        authenticated_page.evaluate("() => { window.open = window.__origOpen; }")

        # No JS errors should have occurred
        assert not errors, f"JS errors after clicking help button: {errors}"
