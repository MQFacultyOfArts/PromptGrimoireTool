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

    def test_help_button_opens_dialog(self, authenticated_page: Page) -> None:
        """Clicking help button opens an iframe dialog with docs site (AC5.3).

        The mkdocs backend renders a dialog containing an iframe that
        loads the docs URL. We verify the dialog appears and contains
        an iframe with the expected src.
        """
        help_btn = authenticated_page.get_by_test_id("help-btn")
        help_btn.wait_for(state="visible", timeout=10_000)
        help_btn.click()

        # Dialog should appear with an iframe
        iframe = authenticated_page.locator("iframe")
        iframe.wait_for(state="visible", timeout=5_000)

        src = iframe.get_attribute("src") or ""
        assert "github.io" in src or "/docs" in src, (
            f"Expected docs URL in iframe src, got: {src}"
        )
