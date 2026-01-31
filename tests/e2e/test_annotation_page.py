"""E2E tests for /annotation page."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


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


class TestWorkspaceCreation:
    """Tests for workspace creation flow (requires authentication and database)."""

    @pytestmark_db
    def test_create_workspace_redirects_and_displays(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Creating workspace redirects to URL with workspace_id and displays it."""
        authenticated_page.goto(f"{app_server}/annotation")

        # Click create button
        authenticated_page.get_by_role(
            "button", name=re.compile("create", re.IGNORECASE)
        ).click()

        # Wait for redirect to URL with workspace_id
        authenticated_page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)

        # Verify URL contains valid UUID
        url = authenticated_page.url
        assert "workspace_id=" in url
        workspace_id_str = url.split("workspace_id=")[1].split("&")[0]
        UUID(workspace_id_str)  # Validates it's a valid UUID

        # Verify the workspace ID is shown on page (proves it loaded from DB)
        expect(authenticated_page.locator(f"text={workspace_id_str}")).to_be_visible()
