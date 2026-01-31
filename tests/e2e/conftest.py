"""E2E test configuration.

Auto-applies the 'e2e' marker to all tests in this directory.
Skip with: pytest -m "not e2e"

Provides standardized fixtures for test isolation:
- fresh_page: Fresh browser context + page per test
- authenticated_page: fresh_page pre-authenticated via mock auth

Workspace isolation: Each test creates its own workspace via the UI.
No database user creation needed - mock auth handles authentication,
and workspace UUIDs provide test-to-test isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page


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
