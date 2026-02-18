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
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.config import get_settings
from tests.e2e.annotation_helpers import setup_workspace_with_content

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Page


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
        tabs = page.locator("role=tab")
        expect(tabs).to_have_count(3, timeout=5000)

        # Verify tab names
        expect(tabs.nth(0)).to_contain_text("Annotate")
        expect(tabs.nth(1)).to_contain_text("Organise")
        expect(tabs.nth(2)).to_contain_text("Respond")

        # Verify Annotate is the selected/active tab
        annotate_tab = tabs.nth(0)
        expect(annotate_tab).to_have_attribute("aria-selected", "true")
