"""E2E tests for deferred annotation page load (#377).

Verifies the skeleton-first loading pattern:
- Content appears after background task completes
- Spinner is gone once content is loaded
- Error handling for invalid workspace IDs

Traceability:
- annotation-deferred-load-377.AC1.2 (content loads via background task)
- annotation-deferred-load-377.AC3.1 (content appears after load)
- annotation-deferred-load-377.AC3.2 (error handling)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from promptgrimoire.config import get_settings
from tests.e2e.conftest import _authenticate_page
from tests.e2e.db_fixtures import _create_workspace_via_db

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]


_WORKSPACE_TITLE = "Deferred Load Test Workspace"


@pytest.fixture
def workspace_page(browser: Browser, app_server: str) -> Generator[tuple[Page, str]]:
    """Authenticated page with a workspace for deferred load testing."""
    import os

    from sqlalchemy import create_engine, text

    context = browser.new_context()
    page = context.new_page()

    unique_id = uuid4().hex[:8]
    email = f"e2e-deferred-{unique_id}@test.example.edu.au"

    _authenticate_page(page, app_server, email=email)

    workspace_id = _create_workspace_via_db(email, "<p>Deferred load test content</p>")

    # Set workspace title so the header update test can verify it.
    db_url = os.environ["DATABASE__URL"]
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE workspace SET title = :title WHERE id = CAST(:ws AS uuid)"),
            {"title": _WORKSPACE_TITLE, "ws": workspace_id},
        )
    engine.dispose()

    yield page, f"{app_server}/annotation?workspace_id={workspace_id}"

    page.goto("about:blank")
    page.close()
    context.close()


class TestDeferredPageLoad:
    """Verify skeleton-first loading pattern."""

    def test_content_loads_and_spinner_gone(
        self, workspace_page: tuple[Page, str]
    ) -> None:
        """AC1.2 + AC3.1: background task loads content, spinner is gone.

        The spinner is a transient state that may vanish before Playwright
        can observe it (especially on Firefox where socket timing differs).
        Instead of asserting the spinner is visible mid-load, we verify the
        end state: __loadComplete is set, spinner is gone, content is present.
        """
        page, url = workspace_page
        page.goto(url)

        # Wait for background task to complete
        page.wait_for_function("() => window.__loadComplete === true", timeout=30000)

        # Spinner should be gone (container cleared and replaced with content)
        spinner = page.get_by_test_id("workspace-loading-spinner")
        expect(spinner).not_to_be_visible(timeout=5000)

        # Verify usable annotation UI actually loaded — not just
        # spinner disappearing.  doc-container holds the rendered
        # document; tag toolbar holds the tag buttons.
        doc = page.locator('[data-testid="doc-container"]')
        expect(doc).to_be_visible(timeout=5000)

    def test_page_header_shows_workspace_title(
        self, workspace_page: tuple[Page, str]
    ) -> None:
        """Page header and browser title update to workspace name.

        The skeleton renders "Annotation Workspace" immediately.
        After the background task completes, both the visible header
        and document.title should reflect the actual workspace name.
        """
        page, url = workspace_page
        page.goto(url)

        # Wait for deferred load to finish
        page.wait_for_function(
            "() => window.__loadComplete === true",
            timeout=30_000,
        )

        # Visible header should show the workspace title, not
        # the generic skeleton "Annotation Workspace".
        header = page.get_by_test_id("page-header-title")
        expect(header).to_be_visible(timeout=5000)
        expect(header).to_have_text(_WORKSPACE_TITLE, timeout=5000)

        # Browser tab title should match the visible header
        doc_title = page.title()
        assert doc_title == _WORKSPACE_TITLE, (
            f"document.title {doc_title!r} != expected {_WORKSPACE_TITLE!r}"
        )

    def test_invalid_workspace_shows_not_found(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC3.2: error handling for invalid workspace ID."""
        context = browser.new_context()
        page = context.new_page()

        unique_id = uuid4().hex[:8]
        email = f"e2e-deferred-err-{unique_id}@test.example.edu.au"
        _authenticate_page(page, app_server, email=email)

        # Navigate to a workspace that doesn't exist
        fake_id = uuid4()
        page.goto(f"{app_server}/annotation?workspace_id={fake_id}")

        # Should show "not found" message (rendered by _resolve_db_context)
        status_msg = page.get_by_test_id("workspace-status-msg")
        expect(status_msg).to_be_visible(timeout=15000)
        expect(status_msg).to_contain_text("not found")

        page.goto("about:blank")
        page.close()
        context.close()
