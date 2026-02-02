"""E2E test configuration.

Auto-applies the 'e2e' marker to all tests in this directory.
Skip with: pytest -m "not e2e"

Provides standardized fixtures for test isolation:
- fresh_page: Fresh browser context + page per test
- authenticated_page: fresh_page pre-authenticated via mock auth
- two_annotation_contexts: Two separate browser contexts viewing same workspace
- two_authenticated_contexts: Two contexts with distinct user identities

Workspace isolation: Each test creates its own workspace via the UI.
No database user creation needed - mock auth handles authentication,
and workspace UUIDs provide test-to-test isolation.

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page


def _extract_workspace_id_from_url(url: str) -> str:
    """Extract workspace_id from URL query parameter."""
    match = re.search(r"workspace_id=([^&]+)", url)
    if not match:
        raise ValueError(f"No workspace_id found in URL: {url}")
    return match.group(1)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Add e2e marker and xdist_group to all tests in this directory.

    The xdist_group ensures all E2E tests run on the same worker,
    sharing the session-scoped app_server fixture.
    """
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.xdist_group("e2e"))


@pytest.fixture
def fresh_page(browser: Browser) -> Generator[Page]:
    """Provide a completely isolated page for each test.

    Creates a fresh browser context and page per test, ensuring:
    - No shared cookies, localStorage, or session state
    - No lingering WebSocket connections from previous tests
    - Clean teardown of context after test completes

    Example:
        def test_something(fresh_page: Page, app_server: str):
            fresh_page.goto(f"{app_server}/some-page")
            # ... test code ...
    """
    context = browser.new_context()
    page = context.new_page()
    # Start with blank page to ensure no stale connections
    page.goto("about:blank")

    yield page

    # Clean teardown
    page.close()
    context.close()


@pytest.fixture
def authenticated_page(browser: Browser, app_server: str) -> Generator[Page]:
    """Provide a fresh page pre-authenticated via mock auth.

    Uses mock auth tokens (AUTH_MOCK=true) to authenticate.
    The mock client accepts tokens in format: mock-token-{email}
    and creates a session without requiring a real user in the database.

    Each test gets a unique email address to ensure isolation.

    Args:
        browser: Playwright browser instance.
        app_server: Base URL of the test server.

    Yields:
        Authenticated Page instance.
    """
    context = browser.new_context()
    page = context.new_page()

    # Generate unique email for this test (no DB user needed)
    unique_id = uuid4().hex[:8]
    email = f"e2e-test-{unique_id}@test.example.edu.au"

    # Authenticate via mock magic link token
    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")

    # Wait for redirect after successful auth (should go to home)
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

    yield page

    # Clean teardown
    page.close()
    context.close()


def _authenticate_page(page: Page, app_server: str) -> None:
    """Authenticate a page via mock auth.

    Uses mock auth tokens (AUTH_MOCK=true) to authenticate.
    """
    unique_id = uuid4().hex[:8]
    email = f"e2e-test-{unique_id}@test.example.edu.au"
    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)


@pytest.fixture
def two_annotation_contexts(
    browser: Browser, app_server: str
) -> Generator[tuple[Page, Page, str]]:
    """Two separate browser contexts viewing same workspace.

    Uses separate contexts (not tabs in one context) to simulate
    genuinely independent clients - different cookie jars, no shared
    browser process state, realistic multi-user scenario.

    Creates the workspace via the UI (page1 creates it, then shares URL with
    page2) to avoid async/event loop issues with programmatic workspace creation.

    Yields:
        tuple: (page1, page2, workspace_id)
    """
    from tests.e2e.annotation_helpers import setup_workspace_with_content

    content = "Sync test word1 word2 word3 word4 word5"

    # TWO contexts = two independent "browsers"
    context1 = browser.new_context()
    context2 = browser.new_context()
    page1 = context1.new_page()
    page2 = context2.new_page()

    # Authenticate both pages first
    _authenticate_page(page1, app_server)
    _authenticate_page(page2, app_server)

    # Page1 creates the workspace via UI
    setup_workspace_with_content(page1, app_server, content)

    # Extract workspace_id from page1's URL
    workspace_id = _extract_workspace_id_from_url(page1.url)

    # Page2 joins the same workspace
    url = f"{app_server}/annotation?workspace_id={workspace_id}"
    page2.goto(url)
    page2.wait_for_selector("[data-char-index]", timeout=10000)

    try:
        yield page1, page2, workspace_id
    finally:
        context1.close()
        context2.close()


@pytest.fixture
def two_authenticated_contexts(
    browser: Browser, app_server: str
) -> Generator[tuple[Page, Page, str, str, str]]:
    """Two separate browser contexts with distinct authenticated users.

    Unlike two_annotation_contexts which uses anonymous contexts,
    this fixture creates contexts with different authenticated identities
    to test user-specific features like attribution and presence.

    Returns user emails so tests can verify user-specific attribution.

    Yields:
        tuple: (page1, page2, workspace_id, user1_email, user2_email)
    """
    from tests.e2e.annotation_helpers import setup_workspace_with_content

    content = "Collaboration test word1 word2 word3 word4 word5"

    # Generate unique emails for test isolation
    user1_email = f"collab_user1_{uuid4().hex[:8]}@test.edu.au"
    user2_email = f"collab_user2_{uuid4().hex[:8]}@test.edu.au"

    # TWO contexts = two independent "browsers"
    context1 = browser.new_context()
    context2 = browser.new_context()
    page1 = context1.new_page()
    page2 = context2.new_page()

    # Authenticate each with distinct mock token
    page1.goto(f"{app_server}/auth/callback?token=mock-token-{user1_email}")
    page1.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

    page2.goto(f"{app_server}/auth/callback?token=mock-token-{user2_email}")
    page2.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

    # Page1 creates the workspace via UI
    setup_workspace_with_content(page1, app_server, content)

    # Extract workspace_id from page1's URL
    workspace_id = _extract_workspace_id_from_url(page1.url)

    # Page2 joins the same workspace
    url = f"{app_server}/annotation?workspace_id={workspace_id}"
    page2.goto(url)
    page2.wait_for_selector("[data-char-index]", timeout=10000)

    try:
        yield page1, page2, workspace_id, user1_email, user2_email
    finally:
        context1.close()
        context2.close()
