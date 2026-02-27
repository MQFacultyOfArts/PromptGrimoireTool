"""E2E tests for three-tab annotation interface.

Tests verify that the annotation page renders three tabs (Annotate, Organise,
Respond) with correct names and default selection.

Most tab-interaction tests (organise columns, locate/warp, cross-tab reactivity,
respond editor, CRDT sync) have been folded into persona test workflows:
- test_law_student.py (organise depth, locate/warp, drag-to-retag, respond)
- test_history_tutorial.py (cross-tab sync, CRDT sync, concurrent drag)

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_01.md
- AC: three-tab-ui.AC1.1
- AC: tags-qa-95.AC1.4 (empty toolbar when seed_tags=False)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.config import get_settings
from tests.e2e.annotation_helpers import (
    _create_workspace_via_db,
    setup_workspace_with_content,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page


# Skip if no database configured
pytestmark_db = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


@pytest.fixture
def workspace_page(authenticated_page: Page, app_server: str) -> Generator[Page]:
    """Authenticated page with a workspace containing document content.

    Reuses the authenticated_page fixture and setup_workspace_with_content helper
    to create a workspace with plain text content. Yields a page ready for tab testing.
    """
    setup_workspace_with_content(
        authenticated_page,
        app_server,
        "Tab test content for annotation workspace verification",
    )
    yield authenticated_page


class TestTabHeaders:
    """Verify three tab headers render with correct names and default selection.

    Verifies: three-tab-ui.AC1.1
    """

    @pytestmark_db
    def test_tab_headers(self, workspace_page: Page) -> None:
        """Page renders Annotate, Organise, Respond tabs with Annotate selected."""
        page = workspace_page

        # Assert three tab elements exist
        tabs = page.locator("[data-testid^='tab-']")
        expect(tabs).to_have_count(3, timeout=5000)

        # Verify tab names
        expect(tabs.nth(0)).to_contain_text("Annotate")
        expect(tabs.nth(1)).to_contain_text("Organise")
        expect(tabs.nth(2)).to_contain_text("Respond")

        # Verify Annotate is the selected/active tab
        annotate_tab = tabs.nth(0)
        expect(annotate_tab).to_have_attribute("aria-selected", "true")


class TestEmptyTagToolbar:
    """Verify that a workspace created without seeded tags has an empty toolbar.

    Verifies: tags-qa-95.AC1.4
    """

    @pytestmark_db
    def test_empty_toolbar_when_no_seed_tags(
        self, browser: Browser, app_server: str
    ) -> None:
        """Tag toolbar contains zero tag buttons when seed_tags=False.

        Creates a workspace via DB with seed_tags=False and navigates to the
        annotation page. Asserts the tag toolbar is visible but contains no
        buttons with data-tag-id attributes (i.e. no tag buttons seeded).
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            # Authenticate via mock auth
            user_email = _authenticate_page(page, app_server)

            # Create a workspace without seeding tags
            workspace_id = _create_workspace_via_db(
                user_email,
                "<p>Empty toolbar test content.</p>",
                seed_tags=False,
            )

            # Navigate to the annotation page for this workspace
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            # The toolbar should be visible
            toolbar = page.locator("[data-testid='tag-toolbar']")
            expect(toolbar).to_be_visible(timeout=5000)

            # No tag buttons should be present (data-tag-id marks tag buttons)
            tag_buttons = toolbar.locator("[data-tag-id]")
            assert tag_buttons.count() == 0, (
                f"Expected 0 tag buttons in unseeded workspace, "
                f"got {tag_buttons.count()}"
            )
        finally:
            page.goto("about:blank")
            page.close()
            context.close()
