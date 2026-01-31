"""E2E test configuration.

Auto-applies the 'e2e' marker to all tests in this directory.
Skip with: pytest -m "not e2e"

Provides standardized fixtures for test isolation:
- fresh_page: Fresh browser context + page per test (use instead of raw 'page')
- db_test_user: Creates a test user in the database (requires TEST_DATABASE_URL)
- authenticated_page: fresh_page pre-authenticated with db_test_user
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
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

    Use this instead of the default 'page' fixture for all E2E tests
    that involve NiceGUI pages with WebSocket connections.

    TODO: When user-level isolation is implemented, this fixture should
    also create a fresh test user per test (except for tests specifically
    verifying same-user behavior across sessions).

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


def _run_async_in_thread(coro):
    """Run an async coroutine in a separate thread with its own event loop.

    This avoids conflicts with pytest-asyncio's event loop management.
    """

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        return future.result()


@pytest.fixture
def db_test_user() -> dict:
    """Create a test user in the database for workspace creation tests.

    Requires TEST_DATABASE_URL to be set.
    Uses a separate thread to avoid event loop conflicts with pytest-asyncio.

    Returns:
        Dict with 'id' (UUID), 'email' (str), and 'display_name' (str).
    """
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL not set - skipping database E2E tests")

    async def _create():
        from promptgrimoire.db.users import create_user

        unique_id = uuid4().hex[:8]
        email = f"e2e-test-{unique_id}@test.example.edu.au"
        user = await create_user(
            email=email,
            display_name="E2E Test User",
        )
        return {"id": user.id, "email": user.email, "display_name": user.display_name}

    return _run_async_in_thread(_create())


@pytest.fixture
def authenticated_page(
    browser: Browser, app_server: str, db_test_user: dict
) -> Generator[Page]:
    """Provide a fresh page pre-authenticated with the test user.

    Uses mock auth tokens (AUTH_MOCK=true) to authenticate.
    The mock client accepts tokens in format: mock-token-{email}

    Args:
        browser: Playwright browser instance.
        app_server: Base URL of the test server.
        db_test_user: Test user created in the database.

    Yields:
        Authenticated Page instance.
    """
    context = browser.new_context()
    page = context.new_page()

    # Authenticate via mock magic link token
    email = db_test_user["email"]
    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")

    # Wait for redirect after successful auth (should go to home)
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

    yield page

    # Clean teardown
    page.close()
    context.close()
