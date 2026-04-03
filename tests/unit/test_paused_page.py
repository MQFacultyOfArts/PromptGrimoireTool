"""Tests for /paused raw Starlette HTML page.

Verifies:
- AC3.1: Resume button points to the original page
- AC3.4: Open-redirect guard rejects malicious return URLs
- AC3.5: Missing return param defaults to /
- AC3.6: Raw Starlette handler, no NiceGUI client
- XSS prevention: HTML entities in return URL are escaped
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Minimal Starlette app with just the paused page route."""
    from starlette.applications import Starlette
    from starlette.routing import Route

    from promptgrimoire.queue_handlers import paused_page_handler

    app = Starlette(
        routes=[Route("/paused", paused_page_handler, methods=["GET"])],
    )
    return TestClient(app)


class TestPausedPageStructure:
    """AC3.6: raw Starlette HTML, no NiceGUI overhead."""

    def test_returns_html_200(self, client: TestClient) -> None:
        resp = client.get("/paused")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_contains_paused_message(self, client: TestClient) -> None:
        resp = client.get("/paused")
        assert "paused" in resp.text.lower()
        assert "inactivity" in resp.text.lower()

    def test_no_nicegui_in_response(self, client: TestClient) -> None:
        resp = client.get("/paused")
        assert "nicegui" not in resp.text.lower()


class TestPausedPageReturnUrl:
    """AC3.1: Resume link honours return URL. AC3.5: defaults to /."""

    def test_resume_link_with_annotation_path(self, client: TestClient) -> None:
        resp = client.get("/paused?return=/annotation/some-uuid")
        assert 'href="/annotation/some-uuid"' in resp.text

    def test_resume_link_with_courses_path(self, client: TestClient) -> None:
        resp = client.get("/paused?return=/courses/123")
        assert 'href="/courses/123"' in resp.text

    def test_no_return_param_defaults_to_root(self, client: TestClient) -> None:
        resp = client.get("/paused")
        assert 'href="/"' in resp.text


class TestPausedPageOpenRedirectGuard:
    """AC3.4: malicious return URLs default to /."""

    def test_absolute_url_rejected(self, client: TestClient) -> None:
        resp = client.get("/paused?return=https://evil.com")
        assert "evil.com" not in resp.text
        assert 'href="/"' in resp.text

    def test_protocol_relative_rejected(self, client: TestClient) -> None:
        resp = client.get("/paused?return=//evil.com")
        assert "evil.com" not in resp.text
        assert 'href="/"' in resp.text

    def test_javascript_protocol_rejected(self, client: TestClient) -> None:
        resp = client.get("/paused?return=javascript:alert(1)")
        assert "javascript:" not in resp.text
        assert 'href="/"' in resp.text


class TestPausedPageXSSPrevention:
    """Return URL with HTML entities is properly escaped."""

    def test_html_entities_escaped_in_href(self, client: TestClient) -> None:
        resp = client.get('/paused?return=/foo"onmouseover="alert(1)')
        # The raw " must be escaped to &quot; so it can't break out of
        # the href attribute — the word "onmouseover" may appear as
        # literal text but never as an unquoted attribute.
        assert 'href="/foo"' not in resp.text
        assert "&quot;" in resp.text
