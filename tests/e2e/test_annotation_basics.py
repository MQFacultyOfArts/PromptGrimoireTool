"""E2E tests for /annotation page basics: loading, workspace/document creation.

These tests verify the foundational functionality that all other annotation
features depend on: the page loads, workspaces can be created, and documents
can be added to workspaces.

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/design-plans/2026-01-30-workspace-model.md
- Acceptance criterion: "Using the new /annotation route: upload 183.rtf, annotate it,
  click export PDF, and get a PDF with all annotations included."

Why these tests exist:
- TestAnnotationPageBasic: Verifies the /annotation route is accessible and shows
  appropriate UI states (create button when no workspace, not-found when invalid).
  Regression: broken routes would block all annotation functionality.
- TestWorkspaceAndDocumentCreation: Verifies the Workspace and WorkspaceDocument
  entities work correctly via the UI. These are the core data model from Seam A.
  Regression: broken CRUD would prevent any annotation work.
"""

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
    """Basic page load tests - no authentication required.

    These tests verify the page is accessible and shows appropriate UI states.
    They don't require database or authentication, so they run fast and catch
    basic routing/rendering issues.

    Invariants tested:
    - /annotation route exists and renders without errors
    - Page shows "create workspace" option when no workspace_id in URL
    - Page shows "not found" when workspace_id doesn't exist in database
    """

    def test_annotation_page_loads(self, fresh_page: Page, app_server: str) -> None:
        """Page loads without errors.

        Regression guard: Ensures the /annotation route is registered and
        the page component renders without throwing exceptions.
        """
        fresh_page.goto(f"{app_server}/annotation")
        expect(fresh_page.locator("body")).to_be_visible()

    def test_page_shows_create_workspace_option(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Page shows option to create workspace when no workspace_id.

        Regression guard: When navigating to /annotation without a workspace_id,
        users need a clear way to create a new workspace. This tests the entry
        point to the workspace creation flow.
        """
        fresh_page.goto(f"{app_server}/annotation")

        # Should show create workspace button or form
        create_button = fresh_page.get_by_role(
            "button", name=re.compile("create", re.IGNORECASE)
        )
        expect(create_button).to_be_visible()

    def test_page_shows_not_found_for_invalid_workspace(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Page shows not found message for non-existent workspace.

        Regression guard: When a workspace_id in the URL doesn't exist in the
        database, users should see a clear error rather than a blank page or
        cryptic exception. This is important for shared links to deleted workspaces.
        """
        test_uuid = "12345678-1234-1234-1234-123456789abc"
        fresh_page.goto(f"{app_server}/annotation?workspace_id={test_uuid}")

        # Should show not found message (workspace doesn't exist in DB)
        expect(fresh_page.locator("text=not found")).to_be_visible()


class TestWorkspaceAndDocumentCreation:
    """Tests for workspace and document creation (requires auth + database).

    These tests verify the Workspace and WorkspaceDocument CRUD operations
    work correctly through the UI. They're the foundation for all annotation
    functionality.

    Invariants tested:
    - Creating a workspace generates a valid UUID and redirects to it
    - Workspace ID is displayed on page (proves DB round-trip works)
    - Pasting content creates a WorkspaceDocument with word spans
    - Documents persist after page reload (proves CRDT persistence works)
    """

    @pytestmark_db
    def test_create_workspace_redirects_and_displays(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Creating workspace redirects to URL with workspace_id and displays it.

        Regression guard: The workspace creation flow must:
        1. Call create_workspace() API
        2. Get back a valid UUID
        3. Redirect to URL with that UUID
        4. Display the UUID on page (proves the workspace was saved to DB)

        If any step fails, users can't start annotation work.
        """
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

    @pytestmark_db
    def test_paste_content_creates_document_and_persists(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Pasting content creates a WorkspaceDocument with word spans that persists.

        Regression guard: The document creation flow must:
        1. Accept pasted text content
        2. Create a WorkspaceDocument in the database
        3. Render content with word-level spans (data-word-index attributes)
        4. Persist across page reloads (proves CRDT state is saved)

        Word spans are critical for annotation positioning - without them,
        highlights can't be created or would be positioned incorrectly.
        """
        # Create workspace first
        authenticated_page.goto(f"{app_server}/annotation")
        authenticated_page.get_by_role(
            "button", name=re.compile("create", re.IGNORECASE)
        ).click()
        authenticated_page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)

        # Save the URL for reload test
        workspace_url = authenticated_page.url

        # Find textarea/input for content
        content_input = authenticated_page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        expect(content_input).to_be_visible()

        # Paste content
        test_content = "This is my test document content for annotation."
        content_input.fill(test_content)

        # Submit
        authenticated_page.get_by_role(
            "button", name=re.compile("add|submit", re.IGNORECASE)
        ).click()

        # Content should appear with word spans
        authenticated_page.wait_for_selector("[data-word-index]", timeout=10000)
        word_spans = authenticated_page.locator("[data-word-index]")
        expect(word_spans.first).to_be_visible()
        assert word_spans.count() >= 8  # At least the words in test_content

        # Reload page to verify persistence
        authenticated_page.goto(workspace_url)

        # Content should still be there with word spans
        authenticated_page.wait_for_selector("[data-word-index]", timeout=10000)
        expect(authenticated_page.locator("text=document")).to_be_visible()
