"""E2E tests for the /banned suspension page and ban-check redirect.

Traceability:
- Issue: #102 (Ban User CLI)
- Phase: 2 (Banned page + page_route guard)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page


def _ban_user_by_email(email: str) -> None:
    """Ban a user via direct DB update (sync, for E2E tests)."""
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE__URL", "")
    if not db_url:
        pytest.skip("DATABASE__URL not configured")
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                'UPDATE "user" SET is_banned = true, banned_at = now()'
                " WHERE email = :email"
            ),
            {"email": email},
        )
    engine.dispose()


class TestBannedPage:
    """Tests for the /banned suspension page."""

    def test_banned_page_displays_suspension_message(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Navigate to /banned directly, verify suspension text appears."""
        fresh_page.goto(f"{app_server}/banned")

        expect(fresh_page.get_by_test_id("suspension-message")).to_be_visible()
        expect(fresh_page.get_by_test_id("suspension-contact")).to_be_visible()

    def test_banned_user_redirected_to_banned_page(
        self, browser: Browser, app_server: str
    ) -> None:
        """Authenticate, ban, navigate to /, verify redirect."""
        context = browser.new_context()
        page = context.new_page()

        try:
            # Authenticate with a unique email
            unique_id = uuid4().hex[:8]
            email = f"e2e-ban-{unique_id}@test.example.edu.au"
            _authenticate_page(page, app_server, email=email)

            # Ban the user in the DB
            _ban_user_by_email(email)

            # Navigate to a protected page (navigator / home)
            page.goto(f"{app_server}/")
            page.wait_for_url(lambda url: "/banned" in url, timeout=10000)

            # Verify the suspension message is shown
            expect(page.get_by_test_id("suspension-message")).to_be_visible()
        finally:
            page.goto("about:blank")
            page.close()
            context.close()
