"""E2E tests for /annotation page basics: loading, workspace/document creation.

These tests verify the foundational functionality that all other annotation
features depend on: the page loads, workspaces can be created, and documents
can be added to workspaces.

Uses pytest-subtests to share expensive browser setup across related assertions.

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

SKIPPED: Pending #106 HTML input redesign. These tests use plain text textarea
input which will change to HTML clipboard paste. Reimplement after #106.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from playwright.sync_api import expect

from promptgrimoire.config import get_settings

# Skip all tests in this module pending #106 HTML input redesign
pytestmark = pytest.mark.skip(reason="Pending #106 HTML input redesign")

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestAnnotationPageBasic:
    """Basic page load tests - no authentication required.

    These tests verify the page is accessible and shows appropriate UI states.
    They don't require database or authentication, so they run fast and catch
    basic routing/rendering issues.

    Uses subtests to share the page load across related assertions.

    Invariants tested:
    - /annotation route exists and renders without errors
    - Page shows "create workspace" option when no workspace_id in URL
    - Page shows "not found" when workspace_id doesn't exist in database
    """

    def test_annotation_page_states(
        self, subtests, fresh_page: Page, app_server: str
    ) -> None:
        """Page load states and UI elements for different URL patterns."""
        # --- Subtest: page loads without errors ---
        with subtests.test(msg="page_loads"):
            fresh_page.goto(f"{app_server}/annotation")
            expect(fresh_page.locator("body")).to_be_visible()

        # --- Subtest: shows create workspace option ---
        with subtests.test(msg="shows_create_workspace_option"):
            # Already on /annotation from previous subtest
            create_button = fresh_page.get_by_role(
                "button", name=re.compile("create", re.IGNORECASE)
            )
            expect(create_button).to_be_visible()

        # --- Subtest: shows not found for invalid workspace ---
        with subtests.test(msg="shows_not_found_for_invalid_workspace"):
            test_uuid = "12345678-1234-1234-1234-123456789abc"
            fresh_page.goto(f"{app_server}/annotation?workspace_id={test_uuid}")
            expect(fresh_page.locator("text=not found")).to_be_visible()


class TestWorkspaceAndDocumentCreation:
    """Tests for workspace and document creation (requires auth + database).

    These tests verify the Workspace and WorkspaceDocument CRUD operations
    work correctly through the UI. They're the foundation for all annotation
    functionality.

    Uses subtests to share authenticated session across workspace creation tests.

    Invariants tested:
    - Creating a workspace generates a valid UUID and redirects to it
    - Workspace ID is displayed on page (proves DB round-trip works)
    - Pasting content creates a WorkspaceDocument with word spans
    - Documents persist after page reload (proves CRDT persistence works)
    """

    @pytestmark_db
    def test_workspace_and_document_crud(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Workspace creation and document CRUD operations."""
        page = authenticated_page

        # --- Subtest: create workspace redirects and displays ID ---
        with subtests.test(msg="create_workspace_redirects_and_displays"):
            page.goto(f"{app_server}/annotation")
            page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
            page.wait_for_url(re.compile(r"workspace_id="), timeout=10000)

            # Verify URL contains valid UUID
            url = page.url
            assert "workspace_id=" in url
            workspace_id_str = url.split("workspace_id=")[1].split("&")[0]
            UUID(workspace_id_str)  # Validates it's a valid UUID

            # Verify the workspace ID is shown on page
            expect(page.locator(f"text={workspace_id_str}")).to_be_visible()

        # Save URL for persistence test
        workspace_url = page.url

        # --- Subtest: paste content creates document with word spans ---
        with subtests.test(msg="paste_content_creates_document"):
            content_input = page.get_by_placeholder(
                re.compile("paste|content", re.IGNORECASE)
            )
            expect(content_input).to_be_visible()

            test_content = "This is my test document content for annotation."
            content_input.fill(test_content)

            page.get_by_role(
                "button", name=re.compile("add|submit", re.IGNORECASE)
            ).click()

            # Content should appear with word spans
            page.wait_for_selector("[data-char-index]", timeout=10000)
            word_spans = page.locator("[data-char-index]")
            expect(word_spans.first).to_be_visible()
            assert word_spans.count() >= 8  # At least the words in test_content

        # --- Subtest: document persists after reload ---
        with subtests.test(msg="document_persists_after_reload"):
            page.goto(workspace_url)
            page.wait_for_selector("[data-char-index]", timeout=10000)
            expect(page.locator("text=document")).to_be_visible()
