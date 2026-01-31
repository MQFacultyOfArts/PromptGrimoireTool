"""E2E tests for /annotation page."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


class TestAnnotationPageBasic:
    """Basic page load tests."""

    def test_annotation_page_loads(self, fresh_page: Page, app_server: str) -> None:
        """Page loads without errors."""
        fresh_page.goto(f"{app_server}/annotation")
        expect(fresh_page.locator("body")).to_be_visible()

    def test_page_shows_create_workspace_option(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Page shows option to create workspace when no workspace_id."""
        fresh_page.goto(f"{app_server}/annotation")

        # Should show create workspace button or form
        create_button = fresh_page.get_by_role(
            "button", name=re.compile("create", re.IGNORECASE)
        )
        expect(create_button).to_be_visible()

    def test_page_shows_workspace_label_with_id(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Page shows workspace ID when provided in URL."""
        test_uuid = "12345678-1234-1234-1234-123456789abc"
        fresh_page.goto(f"{app_server}/annotation?workspace_id={test_uuid}")

        # Should show the workspace ID
        expect(fresh_page.locator(f"text={test_uuid}")).to_be_visible()
