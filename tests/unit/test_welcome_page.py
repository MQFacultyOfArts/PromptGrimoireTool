"""Tests for /welcome raw Starlette pre-auth landing page.

Verifies:
- AC7.1: Returns HTML with Login button linking to /login?return=/
- AC7.2: Raw Starlette handler, no NiceGUI client
- AC7.3: Login link includes return=/ query parameter
- AC7.4: Contains PromptGrimoire heading
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Minimal Starlette app with just the welcome page route."""
    from starlette.applications import Starlette
    from starlette.routing import Route

    from promptgrimoire.queue_handlers import welcome_page_handler

    app = Starlette(
        routes=[Route("/welcome", welcome_page_handler, methods=["GET"])],
    )
    return TestClient(app)


class TestWelcomePageStructure:
    """AC7.2: raw Starlette HTML, no NiceGUI overhead."""

    def test_returns_html_200(self, client: TestClient) -> None:
        resp = client.get("/welcome")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_contains_promptgrimoire_heading(self, client: TestClient) -> None:
        """AC7.4: heading text present."""
        resp = client.get("/welcome")
        assert "PromptGrimoire" in resp.text

    def test_no_nicegui_in_response(self, client: TestClient) -> None:
        resp = client.get("/welcome")
        assert "nicegui" not in resp.text.lower()


class TestWelcomePageLoginLink:
    """AC7.1, AC7.3: Login button links to /login?return=/."""

    def test_login_link_present(self, client: TestClient) -> None:
        resp = client.get("/welcome")
        assert "/login?return=/" in resp.text

    def test_login_link_has_return_param(self, client: TestClient) -> None:
        resp = client.get("/welcome")
        assert 'href="/login?return=/"' in resp.text
