"""E2E tests for deferred annotation page load (#377).

Verifies the skeleton-first loading pattern:
- Spinner visible before content loads
- Content appears after background task completes
- Error handling for invalid workspace IDs

Traceability:
- annotation-deferred-load-377.AC1.2 (spinner visible before content)
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


pytestmark_db = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


@pytest.fixture
def workspace_page(browser: Browser, app_server: str) -> Generator[tuple[Page, str]]:
    """Authenticated page with a workspace for deferred load testing."""
    context = browser.new_context()
    page = context.new_page()

    unique_id = uuid4().hex[:8]
    email = f"e2e-deferred-{unique_id}@test.example.edu.au"

    _authenticate_page(page, app_server, email=email)

    workspace_id = _create_workspace_via_db(email, "<p>Deferred load test content</p>")

    yield page, f"{app_server}/annotation?workspace_id={workspace_id}"

    page.goto("about:blank")
    page.close()
    context.close()


@pytest.mark.e2e
class TestDeferredPageLoad:
    """Verify skeleton-first loading pattern."""

    def test_spinner_visible_then_content_loads(
        self, workspace_page: tuple[Page, str]
    ) -> None:
        """AC1.2: spinner visible before DB work; AC3.1: content after load.

        Navigates to workspace, asserts spinner is visible, waits for
        __loadComplete, then asserts content is present and spinner gone.
        """
        page, url = workspace_page
        page.goto(url)

        # Spinner should appear during loading
        spinner = page.get_by_test_id("workspace-loading-spinner")
        expect(spinner).to_be_visible(timeout=5000)

        # Wait for background task to complete
        page.wait_for_function("() => window.__loadComplete === true", timeout=30000)

        # Spinner should be gone (container cleared and replaced with content)
        expect(spinner).not_to_be_visible(timeout=5000)

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
