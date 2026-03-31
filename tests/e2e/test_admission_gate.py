"""E2E tests for the admission gate queue page and status API.

These tests verify the raw Starlette endpoints (/queue and /api/queue/status)
that serve queued users. They do NOT test the gate redirect itself (that's
thoroughly covered in unit tests for _check_admission_gate in registry.py).

Run with: uv run grimoire e2e run -m perf
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.perf,
]


class TestQueuePage:
    """Tests for the /queue HTML page (raw Starlette, no NiceGUI)."""

    def test_queue_page_renders_with_server_busy_heading(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Queue page shows 'Server is busy' heading and position text."""
        fresh_page.goto(f"{app_server}/queue?t=fake-token&return=/")

        heading = fresh_page.locator("h1")
        expect(heading).to_have_text("Server is busy")

        position = fresh_page.locator("#position")
        expect(position).to_be_visible()

    def test_queue_page_shows_expired_for_invalid_token(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Queue page polls /api/queue/status and shows expired state for bad token."""
        fresh_page.goto(f"{app_server}/queue?t=nonexistent&return=/")

        # The JS polls after 1 second; wait for the expired div to appear
        expired_div = fresh_page.locator("#expired")
        expect(expired_div).to_be_visible(timeout=10_000)

        # Position text should be hidden
        position = fresh_page.locator("#position")
        expect(position).to_be_hidden()

        # Expired message should be visible
        expect(expired_div).to_contain_text("Your place in the queue has expired")

    def test_queue_page_rejoin_link_uses_return_url(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Rejoin link points to the return URL, not just /."""
        fresh_page.goto(
            f"{app_server}/queue?t=fake&return=/annotation%3Fworkspace_id%3Dabc"
        )

        rejoin = fresh_page.locator("#rejoin")
        expect(rejoin).to_have_attribute("href", "/annotation?workspace_id=abc")

    def test_queue_page_open_redirect_guard(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Return URL with protocol-relative path is sanitised to /."""
        fresh_page.goto(f"{app_server}/queue?t=fake&return=//evil.com/steal")

        rejoin = fresh_page.locator("#rejoin")
        expect(rejoin).to_have_attribute("href", "/")


class TestQueuePageXSS:
    """XSS resistance tests for the /queue page token and return URL."""

    def test_script_break_in_token(self, fresh_page: Page, app_server: str) -> None:
        """Token containing </script> does not break out of the JS block."""
        malicious = "</script><script>alert(1)</script>"
        fresh_page.goto(f"{app_server}/queue?t={malicious}&return=/")
        # Page should still render the heading (JS block intact)
        heading = fresh_page.locator("h1")
        expect(heading).to_have_text("Server is busy")
        # No injected script alert — page rendered normally
        # The expired div should appear (invalid token)
        expired_div = fresh_page.locator("#expired")
        expect(expired_div).to_be_visible(timeout=10_000)

    def test_quotes_in_token(self, fresh_page: Page, app_server: str) -> None:
        """Token with quotes does not escape the JSON string literal."""
        fresh_page.goto(f'{app_server}/queue?t=";alert(1);//&return=/')
        heading = fresh_page.locator("h1")
        expect(heading).to_have_text("Server is busy")

    def test_null_bytes_in_token(self, fresh_page: Page, app_server: str) -> None:
        """Token with null bytes handled safely."""
        fresh_page.goto(f"{app_server}/queue?t=abc%00def&return=/")
        heading = fresh_page.locator("h1")
        expect(heading).to_have_text("Server is busy")


class TestQueueStatusAPI:
    """Tests for the /api/queue/status JSON endpoint."""

    def test_unknown_token_returns_expired(self, app_server: str) -> None:
        """Unknown token returns expired status with correct shape."""
        resp = httpx.get(
            f"{app_server}/api/queue/status", params={"t": "no-such-token"}
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["admitted"] is False
        assert data["expired"] is True
        assert "position" in data
        assert "total" in data

    def test_empty_token_returns_expired(self, app_server: str) -> None:
        """Missing token parameter returns expired status."""
        resp = httpx.get(f"{app_server}/api/queue/status")
        assert resp.status_code == 200

        data = resp.json()
        assert data["expired"] is True
        assert data["admitted"] is False
